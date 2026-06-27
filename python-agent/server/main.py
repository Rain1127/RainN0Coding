"""
FastAPI 服务层 —— AI 代码生成 SSE 流式输出

端点：
  POST /api/generate-code  — SSE 流式代码生成（供 Java 后端透传）
  GET  /api/health         — 服务健康检查

启动：
  PYTHONPATH=D:/code/yu-ai-code-mother/python-agent .venv/Scripts/python.exe server/main.py
  或: uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload
"""
import asyncio
import time
import logging
import contextvars
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from config import config
from workflow.sse_stream import stream_workflow
from monitoring import setup_monitoring, ai_code_gen_active_requests, record_request

# ---- 日志 ----
# 全链路追踪：用 contextvars 在异步上下文中传递 trace_id
_current_trace_id: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="-")


class _TraceIdFormatter(logging.Formatter):
    """自定义 Formatter：在格式化前从 contextvars 注入 trace_id，避免 KeyError。"""
    def format(self, record):
        record.trace_id = _current_trace_id.get("-")
        return super().format(record)


_handler = logging.StreamHandler()
_handler.setFormatter(_TraceIdFormatter("%(asctime)s [%(levelname)s] [trace=%(trace_id)s] %(message)s"))
logging.getLogger().handlers.clear()
logging.getLogger().addHandler(_handler)
logging.getLogger().setLevel(logging.INFO)

logger = logging.getLogger("server")

# ---- FastAPI 应用 ----
app = FastAPI(
    title="AI Code Gen Agents",
    version="1.0.0",
    description="7-Agent 协同代码生成系统 — Python 智能体端",
)

# ---- Prometheus 指标端点 + HTTP 埋点 ----
setup_monitoring(app)

# ---- CORS（允许 Java 后端 + 前端跨域）----
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ 请求模型 ============

class CodeGenRequest(BaseModel):
    user_id: str = Field(default="demo", alias="userId", description="用户 ID")
    app_id: str = Field(default="demo", alias="appId", description="应用 ID")
    prompt: str = Field(..., description="用户原始需求描述")
    code_gen_type: str = Field(default="VUE_PROJECT", alias="codeGenType", description="代码生成类型")
    user_role: str = Field(default="user", alias="userRole", description="用户角色: user / admin")
    trace_id: str = Field(default="", alias="traceId", description="全链路追踪 ID（Java 生成的 UUID）")
    history: list = Field(default_factory=list, description="对话历史")

    model_config = {"populate_by_name": True}


# ============ 中间件：请求日志 ============

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    logger.info(f"{request.method} {request.url.path} → {response.status_code} ({duration:.2f}s)")
    return response


# ============ SSE 流式代码生成 ============

@app.post("/api/generate-code")
async def generate_code(request: CodeGenRequest):
    """SSE 流式代码生成端点。

    Java 后端通过 WebClient 调用，SSE 字节流透传给前端。
    事件格式见 workflow/sse_stream.py 文档。
    """
    _current_trace_id.set(request.trace_id)
    ai_code_gen_active_requests.inc()
    logger.info(f"收到代码生成请求: user={request.user_id}, app={request.app_id}, prompt={request.prompt[:60]}...")

    async def event_generator():
        status = "success"
        try:
            async for event in stream_workflow(
                user_request=request.prompt,
                user_id=request.user_id,
                app_id=request.app_id,
                code_gen_type=request.code_gen_type,
                user_role=request.user_role,
                trace_id=request.trace_id,
            ):
                yield {"data": event}
        except Exception:
            status = "error"
            raise
        finally:
            ai_code_gen_active_requests.dec()
            record_request(request.user_id, request.app_id, request.code_gen_type, status)

    return EventSourceResponse(event_generator())


# ============ 健康检查 ============

@app.get("/api/health")
async def health():
    """服务健康检查。返回服务状态、模型名称、Milvus 连接状态。"""
    milvus_ok = False
    try:
        from rag.milvus_client import milvus_store
        milvus_store.connect()
        milvus_ok = True
    except Exception:
        pass

    sqlite_ok = False
    try:
        from rag.sqlite_store import sqlite_store
        sqlite_store.connect()
        sqlite_ok = True
    except Exception:
        pass

    return JSONResponse({
        "status": "ok",
        "model": config.DEEPSEEK_MODEL,
        "chat_model": config.CHAT_MODEL,
        "milvus_connected": milvus_ok,
        "milvus_mode": config.MILVUS_MODE,
        "sqlite_connected": sqlite_ok,
        "hybrid_engine": config.USE_HYBRID_ENGINE,
    })


# ============ 定期清理 (P2 反馈闭环) ============

_cleanup_task: asyncio.Task | None = None


async def _periodic_quality_cleanup():
    """后台任务：定期清理低质量 code_store 条目。

    每个 QUALITY_CLEANUP_INTERVAL_HOURS 小时执行一次：
      1. 从 feedback_tracker 查询低质量条目
      2. 从 Milvus 删除
      3. 从文件系统删除
      4. 从质量表删除记录
    """
    while True:
        await asyncio.sleep(config.QUALITY_CLEANUP_INTERVAL_HOURS * 3600)
        try:
            from rag.feedback_tracker import feedback_tracker
            from rag.milvus_client import milvus_store
            from rag.code_grep import code_grep

            feedback_tracker.connect()
            feedback_tracker.init_tables()

            entries = feedback_tracker.get_low_quality_entries(
                threshold=30.0,
                min_age_days=config.QUALITY_MIN_AGE_DAYS,
            )

            if not entries:
                logger.info("[QualityCleanup] no low-quality entries to clean")
                continue

            deleted_milvus = 0
            deleted_fs = 0
            for entry in entries:
                e_app_id = entry["app_id"]
                e_file_path = entry["file_path"]

                # 从 Milvus 删除
                try:
                    milvus_store.connect()
                    expr = f'app_id == "{e_app_id}" && file_path == "{e_file_path}"'
                    count = milvus_store.delete_by_expr("code_store", expr)
                    deleted_milvus += count
                except Exception as e:
                    logger.warning(f"[QualityCleanup] Milvus delete failed "
                                   f"{e_app_id}/{e_file_path}: {e}")

                # 从文件系统删除
                try:
                    if code_grep.delete_code(e_app_id, e_file_path):
                        deleted_fs += 1
                except Exception as e:
                    logger.warning(f"[QualityCleanup] FS delete failed "
                                   f"{e_app_id}/{e_file_path}: {e}")

                # 从质量表删除
                try:
                    feedback_tracker.delete_entry(e_app_id, e_file_path)
                except Exception:
                    pass

            logger.info(f"[QualityCleanup] cleaned: {len(entries)} entries, "
                        f"Milvus={deleted_milvus}, FS={deleted_fs}")
        except Exception as e:
            logger.warning(f"[QualityCleanup] cleanup task error: {e}")


# ============ 启动入口 ============

@app.on_event("startup")
async def startup():
    """服务启动时初始化资源"""
    global _cleanup_task

    # 初始化 SQLite FTS5（grep 检索）
    try:
        from rag.sqlite_store import sqlite_store
        sqlite_store.connect()
        sqlite_store.init_tables()
        logger.info(f"SqliteStore 已就绪: {config.SQLITE_DB_PATH}")
    except Exception as e:
        logger.warning(f"SqliteStore 初始化失败（grep 检索将不可用）: {e}")

    # 确保已验证代码目录存在
    try:
        import os
        os.makedirs(config.CODE_STORE_DIR, exist_ok=True)
        logger.info(f"CodeStore 目录已就绪: {config.CODE_STORE_DIR}")
    except Exception as e:
        logger.warning(f"CodeStore 目录创建失败: {e}")

    # 初始化反馈追踪器 (P2)
    try:
        from rag.feedback_tracker import feedback_tracker
        feedback_tracker.connect()
        feedback_tracker.init_tables()
        logger.info("FeedbackTracker 已就绪")
    except Exception as e:
        logger.warning(f"FeedbackTracker 初始化失败: {e}")

    # 启动定期质量清理任务 (P2)
    _cleanup_task = asyncio.create_task(_periodic_quality_cleanup())
    logger.info(f"质量清理任务已启动 (interval={config.QUALITY_CLEANUP_INTERVAL_HOURS}h, "
                f"min_age={config.QUALITY_MIN_AGE_DAYS}d)")

    logger.info(f"检索引擎模式: {'Hybrid (grep+RAG)' if config.USE_HYBRID_ENGINE else 'Vector-only (RAG)'}")


@app.on_event("shutdown")
async def shutdown():
    """服务关闭时清理资源"""
    global _cleanup_task

    # 取消定期清理任务
    if _cleanup_task:
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass
        logger.info("质量清理任务已停止")

    try:
        from rag.milvus_client import milvus_store
        milvus_store.close()
        logger.info("Milvus 连接已关闭")
    except Exception:
        pass
    try:
        from rag.sqlite_store import sqlite_store
        sqlite_store.close()
        logger.info("SqliteStore 连接已关闭")
    except Exception:
        pass
    try:
        from rag.feedback_tracker import feedback_tracker
        feedback_tracker.close()
        logger.info("FeedbackTracker 连接已关闭")
    except Exception:
        pass


if __name__ == "__main__":
    import uvicorn
    logger.info(f"启动服务: http://0.0.0.0:{config.SERVER_PORT}")
    logger.info(f"模型: {config.DEEPSEEK_MODEL} / {config.CHAT_MODEL}")
    logger.info(f"Milvus: {config.MILVUS_MODE} mode")
    uvicorn.run(
        "server.main:app",
        host="0.0.0.0",
        port=config.SERVER_PORT,
        reload=True,
        log_level="info",
    )
