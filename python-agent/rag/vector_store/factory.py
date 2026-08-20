from config import config
from rag.vector_store.base import VectorStore


def create_vector_store(
    provider: str | None = None,
) -> VectorStore:
    selected = (
        provider or config.VECTOR_DB_PROVIDER
    ).strip().lower()

    if selected == "milvus":
        from rag.vector_store.milvus_store import milvus_store

        return milvus_store

    if selected == "qdrant":
        from rag.vector_store.qdrant_store import QdrantStore

        return QdrantStore()

    raise ValueError(
        f"Unsupported VECTOR_DB_PROVIDER={selected!r}; "
        "expected one of: milvus, qdrant"
    )
