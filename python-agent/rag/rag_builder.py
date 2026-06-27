"""
RAG 上下文构建器 —— Coder Agent 与检索引擎的桥梁

build_rag_context(): 为每个文件构建增强 Prompt
index_code_files():   构建成功后将代码入库（Milvus + 文件系统双写）

检索引擎：
  - USE_HYBRID_ENGINE=true → HybridEngine (grep + RAG 混合)
  - USE_HYBRID_ENGINE=false → RetrievalEngine (纯向量检索，回退)
"""
from config import config

# 延迟导入 Milvus 相关模块（无 pymilvus 时也能加载）
_retrieval_engine = None
_retrieval_context_cls = None
_embedding_service = None
_milvus_store = None


def _lazy_import_milvus():
    global _retrieval_engine, _retrieval_context_cls, _embedding_service, _milvus_store
    if _retrieval_engine is None:
        try:
            from rag.retrieval_engine import retrieval_engine, RetrievalContext
            _retrieval_engine = retrieval_engine
            _retrieval_context_cls = RetrievalContext
        except ImportError:
            pass
    if _embedding_service is None:
        try:
            from rag.embedding_service import embedding_service
            _embedding_service = embedding_service
        except ImportError:
            pass
    if _milvus_store is None:
        try:
            from rag.milvus_client import milvus_store
            _milvus_store = milvus_store
        except ImportError:
            pass


from rag.hybrid_engine import hybrid_engine
from rag.code_grep import code_grep
from dataclasses import dataclass


@dataclass
class _SimpleCtx:
    """轻量上下文，兼容 RetrievalContext 接口"""
    phase: str = "code"
    user_request: str = ""
    file_info: dict | None = None
    architecture: dict | None = None
    retry_count: int = 0
    code_gen_type: str = "vue_project"
    app_id: str = ""


def build_rag_context(
    file_info: dict,
    architecture: dict,
    phase: str = "code",
    retry_count: int = 0,
    user_request: str = "",
    code_gen_type: str = "vue_project",
    app_id: str = "",
) -> str:
    """
    为指定文件构建 RAG 增强上下文。
    USE_HYBRID_ENGINE=true 时使用 grep+RAG 混合引擎，否则回退到纯向量检索。

    Args:
        file_info: 文件信息 {'path': str, 'description': str, 'file_type': str}
        architecture: 架构方案
        phase: 当前阶段 (pm/arch/code/review)
        retry_count: 当前重试次数
        user_request: 用户原始需求
        app_id: 当前应用 ID（用于反馈追踪，P2）

    Returns:
        格式化后的 RAG Prompt 文本，失败时返回 ""
    """
    try:
        if config.USE_HYBRID_ENGINE:
            # 混合引擎：使用简单的上下文对象
            return hybrid_engine.retrieve(_SimpleCtx(
                phase=phase,
                user_request=user_request,
                file_info=file_info,
                architecture=architecture,
                retry_count=retry_count,
                code_gen_type=code_gen_type,
                app_id=app_id,
            ))
        else:
            # 回退：纯向量检索引擎
            _lazy_import_milvus()
            if _retrieval_engine is None or _retrieval_context_cls is None:
                print("[RAG] build_rag_context 失败: RetrievalEngine 不可用 (pymilvus 未安装)")
                return ""
            ctx = _retrieval_context_cls(
                phase=phase,
                user_request=user_request,
                file_info=file_info,
                architecture=architecture,
                retry_count=retry_count,
                code_gen_type=code_gen_type,
                app_id=app_id,
            )
            return _retrieval_engine.retrieve(ctx)
    except Exception as e:
        print(f"[RAG] build_rag_context 失败: {e}")
        return ""


def index_code_files(code_files: list, app_id: str, code_gen_type: str,
                     review_score: int = 0):
    """
    将生成的代码双写入 Milvus code_store + 文件系统 (供 ripgrep 搜索)。

    Args:
        code_files: [{'path': str, 'content': str}, ...]
        app_id: 应用 ID
        code_gen_type: 代码生成类型
        review_score: Reviewer 评分 (0-100)，用于记录初始质量分 (P2)
    """
    if not code_files:
        return

    # 写入文件系统（供 CodeGrep 搜索）
    for f in code_files:
        content = f.get("content", "")
        if not content:
            continue
        try:
            code_grep.write_code(app_id, f.get("path", ""), content)
        except Exception as e:
            print(f"[RAG] 文件系统写入失败 {f.get('path', '?')}: {e}")

    # 同时写入 Milvus（兼容过渡期，pymilvus 不可用时跳过）
    indexed = 0
    _lazy_import_milvus()
    if _milvus_store and _embedding_service:
        try:
            _milvus_store.connect()
            _milvus_store.ensure_collection("code_store")

            for f in code_files:
                content = f.get("content", "")
                if not content:
                    continue
                try:
                    vec = _embedding_service.embed(content)
                except Exception:
                    continue

                if all(v == 0.0 for v in vec):
                    continue

                try:
                    _milvus_store.insert_one("code_store", {
                        "vector": vec,
                        "app_id": app_id,
                        "file_path": f.get("path", ""),
                        "content": content[:10000],
                        "code_gen_type": code_gen_type,
                        "tags": "",
                    })
                    indexed += 1
                except Exception as e:
                    print(f"[RAG] 入库失败 {f.get('path', '?')}: {e}")
        except Exception as e:
            print(f"[RAG] Milvus 写入跳过: {e}")

    # 记录质量元数据到反馈追踪器 (P2)
    try:
        from rag.feedback_tracker import feedback_tracker
        for f in code_files:
            file_path = f.get("path", "")
            if file_path:
                feedback_tracker.record_ingestion(app_id, file_path, review_score)
    except Exception as e:
        print(f"[RAG] 质量元数据记录失败（不影响入库）: {e}")

    file_count = code_grep.get_file_count()
    print(f"[RAG] 已入库 {indexed}/{len(code_files)} 文件到 Milvus，文件系统共 {file_count} 文件")
