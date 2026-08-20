from uuid import uuid4

import pytest
from qdrant_client import QdrantClient

from rag.vector_store.qdrant_store import QdrantStore


pytestmark = pytest.mark.integration


def test_qdrant_round_trip_and_persistence_boundary():
    client = QdrantClient(
        url="http://localhost:6333",
        timeout=5,
        check_compatibility=False,
    )
    store = QdrantStore(client=client)
    collection_name = f"integration_{uuid4().hex}"
    store.COLLECTIONS[collection_name] = 512

    try:
        store.ensure_collection(collection_name)
        store.insert_one(
            collection_name,
            {
                "vector": [1.0] + [0.0] * 511,
                "kind": "expected",
                "text": "qdrant integration",
            },
        )
        results = store.search(
            collection_name,
            [1.0] + [0.0] * 511,
            limit=1,
        )

        assert results[0]["distance"] > 0.99
        assert results[0]["entity"]["kind"] == "expected"
        assert store.count(collection_name) == 1
        assert store.query_by_filters(
            collection_name,
            {"kind": "expected"},
        )
        assert (
            store.delete_by_filters(
                collection_name,
                {"kind": "expected"},
            )
            == 1
        )
        assert store.count(collection_name) == 0
    finally:
        try:
            if client.collection_exists(collection_name):
                client.delete_collection(collection_name)
        except Exception:
            pass
        finally:
            store.COLLECTIONS.pop(collection_name, None)
            store.close()
