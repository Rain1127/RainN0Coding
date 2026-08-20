from rag.milvus_client import MilvusStore


REQUIRED_METHODS = {
    "connect",
    "init_collections",
    "ensure_collection",
    "search",
    "search_multi",
    "search_async",
    "search_multi_async",
    "insert_one",
    "delete_by_filters",
    "query_by_filters",
    "count",
    "reset_all",
    "close",
}


def test_milvus_store_satisfies_vector_store_contract():
    actual_methods = set(dir(MilvusStore))

    assert REQUIRED_METHODS <= actual_methods

def test_milvus_search_multi_degrades_failed_query_to_empty_result(monkeypatch):
    store = MilvusStore()

    def fake_search(
        collection_name,
        query_vector,
        limit=5,
        output_fields=None,
    ):
        if collection_name == "broken":
            raise RuntimeError("simulated search failure")
        return [{"id": 1, "entity": {"name": "ok"}}]

    monkeypatch.setattr(store, "search", fake_search)

    try:
        results = store.search_multi([
            ("working", [0.1, 0.2]),
            ("broken", [0.3, 0.4]),
        ])
    finally:
        store.close()

    assert results == [
        [{"id": 1, "entity": {"name": "ok"}}],
        [],
    ]

def test_milvus_adapter_reexports_existing_store():
    from rag.vector_store.milvus_store import (
        MilvusStore as AdapterMilvusStore,
        milvus_store,
    )

    assert AdapterMilvusStore is MilvusStore
    assert isinstance(milvus_store, MilvusStore)