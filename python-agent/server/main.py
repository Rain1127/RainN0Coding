"""
FastAPI service for AI code generation SSE output.

Endpoints:
  POST /api/generate-code  - SSE stream for code generation
  GET  /api/health         - health check

Run:
  PYTHONPATH=D:/code/RainN0Coding/python-agent .venv/Scripts/python.exe server/main.py
  or uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload
"""
import asyncio
import importlib
import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from monitoring import ai_code_gen_active_requests, record_request, setup_monitoring
from server.codegen_type_router import route_code_gen_type
from server.generate_code_orchestrator import orchestrate_generate_code
from server.lifespan import lifespan
from server.middleware import register_middleware
from server.routes import register_routes
from tracing import (
    current_trace_context,
    get_current_trace_id,
    setup_tracing,
)
from workflow.sse_stream import stream_persistent_workflow as stream_workflow


def _config():
    return importlib.import_module("config").config


class ReloadableSemaphore:
    """Refresh local concurrency capacity when config reloads and the semaphore is idle."""

    def __init__(self, limit_getter):
        self._limit_getter = limit_getter
        self._configured_limit = 0
        self._in_flight = 0
        self._semaphore = asyncio.Semaphore(1)
        self._refresh_if_idle(force=True)

    def _desired_limit(self) -> int:
        return max(1, int(self._limit_getter()))

    def _refresh_if_idle(self, *, force: bool = False) -> None:
        desired_limit = self._desired_limit()
        if force or (self._in_flight == 0 and desired_limit != self._configured_limit):
            self._semaphore = asyncio.Semaphore(desired_limit)
            self._configured_limit = desired_limit

    async def acquire(self) -> bool:
        self._refresh_if_idle()
        await self._semaphore.acquire()
        self._in_flight += 1
        return True

    def release(self) -> None:
        self._semaphore.release()
        self._in_flight = max(0, self._in_flight - 1)
        self._refresh_if_idle()

    def locked(self) -> bool:
        self._refresh_if_idle()
        return self._semaphore.locked()

    @property
    def _value(self) -> int:
        self._refresh_if_idle()
        return self._semaphore._value


class _TraceIdFormatter(logging.Formatter):
    """Inject trace/span information into every log record."""

    def format(self, record):
        trace_id, span_id = current_trace_context(get_current_trace_id("-"))
        record.trace_id = trace_id
        record.span_id = span_id
        return super().format(record)


_handler = logging.StreamHandler()
_handler.setFormatter(
    _TraceIdFormatter("%(asctime)s [%(levelname)s] [trace=%(trace_id)s span=%(span_id)s] %(message)s")
)
logging.getLogger().handlers.clear()
logging.getLogger().addHandler(_handler)
logging.getLogger().setLevel(logging.INFO)

logger = logging.getLogger("server")

app = FastAPI(
    title="AI Code Gen Agents",
    version="1.0.0",
    description="7-Agent cooperative code generation system - Python smart backend",
    lifespan=lifespan,
)

setup_tracing(app)
setup_monitoring(app)
agent_semaphore = ReloadableSemaphore(lambda: _config().AGENT_MAX_CONCURRENT_REQUESTS)
register_middleware(app, logger=logger)


class CodeGenRequest(BaseModel):
    user_id: str = Field(default="demo", alias="userId", description="user id")
    app_id: str = Field(default="demo", alias="appId", description="app id")
    prompt: str = Field(..., description="user requirement prompt")
    code_gen_type: str = Field(default="VUE_PROJECT", alias="codeGenType", description="code generation type")
    user_role: str = Field(default="user", alias="userRole", description="user role: user/admin")
    request_id: str = Field(default="", alias="requestId", description="gateway request id")
    trace_id: str = Field(default="", alias="traceId", description="distributed trace id from Java")
    history: list = Field(default_factory=list, description="conversation history")
    resume: bool = False

    model_config = {"populate_by_name": True}


class RouteCodeGenTypeRequest(BaseModel):
    prompt: str = Field(..., description="user prompt")
    user_id: str | None = Field(default=None, alias="userId", description="user id")

    model_config = {"populate_by_name": True}


class GenerationControlRequest(BaseModel):
    user_id: str = Field(alias="userId", min_length=1, max_length=128)
    app_id: str = Field(alias="appId", min_length=1, max_length=128)
    run_id: str = Field(alias="runId", min_length=1, max_length=128)
    model_config = {"populate_by_name": True}


def _control(request, action):
    from workflow.run_control import default_run_store, RunControlError
    try:
        store = default_run_store()
        return getattr(store, action)(request.run_id, request.user_id, request.app_id)
    except RunControlError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=exc.status_code)


@app.post("/api/generation/pause")
def pause_generation(request: GenerationControlRequest):
    return _control(request, "pause")


@app.post("/api/generation/status")
def generation_status(request: GenerationControlRequest):
    return _control(request, "public_status")


class RouteCodeGenTypeResponse(BaseModel):
    code_gen_type: str = Field(alias="codeGenType", description="code generation type")

    model_config = {"populate_by_name": True}


async def generate_code(request: CodeGenRequest):
    """SSE code generation endpoint."""
    result = await orchestrate_generate_code(
        request,
        semaphore=agent_semaphore,
        stream_workflow=stream_workflow,
        record_request=record_request,
        active_requests_metric=ai_code_gen_active_requests,
        logger=logger,
    )
    if result.immediate_response is not None:
        return JSONResponse(
            result.immediate_response.body,
            status_code=result.immediate_response.status_code,
        )
    if result.event_generator is None:
        raise RuntimeError("generate_code orchestration returned no response path")
    return EventSourceResponse(result.event_generator)


async def route_code_gen_type_api(request: RouteCodeGenTypeRequest):
    code_gen_type = route_code_gen_type(request.prompt, user_id=request.user_id)
    return RouteCodeGenTypeResponse(codeGenType=code_gen_type)


async def health():
    """Health check endpoint."""
    vector_store_ok = False
    try:
        from rag.vector_store import vector_store

        vector_store.connect()
        vector_store_ok = True
    except Exception:
        pass

    sqlite_ok = False
    try:
        from rag.sqlite_store import sqlite_store

        sqlite_store.connect()
        sqlite_ok = True
    except Exception:
        pass

    return JSONResponse(
        {
            "status": "ok",
            "model": _config().DEEPSEEK_MODEL,
            "chat_model": _config().CHAT_MODEL,
            "vector_store_connected": vector_store_ok,
            "vector_db_provider": _config().VECTOR_DB_PROVIDER,
            "milvus_connected": (
                vector_store_ok
                if _config().VECTOR_DB_PROVIDER == "milvus"
                else False
            ),
            "milvus_mode": (
                _config().MILVUS_MODE
                if _config().VECTOR_DB_PROVIDER == "milvus"
                else None
            ),
            "sqlite_connected": sqlite_ok,
            "hybrid_engine": _config().USE_HYBRID_ENGINE,
        }
    )


register_routes(
    app,
    generate_code_handler=generate_code,
    route_code_gen_type_handler=route_code_gen_type_api,
    health_handler=health,
)


if __name__ == "__main__":
    import uvicorn

    logger.info(f"Starting server: http://0.0.0.0:{_config().SERVER_PORT}")
    logger.info(f"Models: {_config().DEEPSEEK_MODEL} / {_config().CHAT_MODEL}")
    logger.info(f"Milvus mode: {_config().MILVUS_MODE}")
    uvicorn.run(
        "server.main:app",
        host="0.0.0.0",
        port=_config().SERVER_PORT,
        reload=True,
        log_level="info",
    )
