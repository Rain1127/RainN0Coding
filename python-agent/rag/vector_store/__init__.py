from rag.vector_store.base import VectorStore
from rag.vector_store.factory import create_vector_store


vector_store: VectorStore = create_vector_store()


__all__ = ["VectorStore", "create_vector_store", "vector_store"]
