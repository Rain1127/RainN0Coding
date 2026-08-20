from types import SimpleNamespace

from rag.vector_store.base import VectorStore
from rag.vector_store.qdrant_store import QdrantStore


class FakeQdrantClient:
    def __init__(self):
        self.collections = set()
        self.created = []
        self.upserts = []

    def get_collections(self):
        return SimpleNamespace(collections=[])

    def collection_exists(self, collection_name):
        return collection_name in self.collections

    def create_collection(self, collection_name, vectors_config):
        self.collections.add(collection_name)
        self.created.append((collection_name, vectors_config))

    def query_points(self, **kwargs):
        return SimpleNamespace(
            points=[
                SimpleNamespace(
                    id="point-1",
                    score=0.91,
                    payload={"api_name": "ref"},
                )
            ]
        )

    def upsert(self, **kwargs):
        self.upserts.append(kwargs)

    def close(self):
        return None


def test_qdrant_store_creates_512d_cosine_collection():
    client = FakeQdrantClient()
    store = QdrantStore(client=client)

    try:
        store.ensure_collection("framework_api")
    finally:
        store.close()

    assert client.created[0][0] == "framework_api"
    assert client.created[0][1].size == 512
    assert client.created[0][1].distance.value == "Cosine"


def test_qdrant_search_normalizes_existing_result_contract():
    client = FakeQdrantClient()
    client.collections.add("framework_api")
    store = QdrantStore(client=client)

    try:
        results = store.search(
            "framework_api",
            [0.0] * 512,
            limit=1,
        )
    finally:
        store.close()

    assert results == [
        {
            "id": "point-1",
            "distance": 0.91,
            "entity": {"api_name": "ref"},
        }
    ]


def test_qdrant_insert_splits_vector_from_payload():
    client = FakeQdrantClient()
    client.collections.add("framework_api")
    store = QdrantStore(client=client)

    try:
        store.insert_one(
            "framework_api",
            {
                "vector": [0.1] * 512,
                "api_name": "computed",
            },
        )
    finally:
        store.close()

    point = client.upserts[0]["points"][0]
    assert point.vector == [0.1] * 512
    assert point.payload == {"api_name": "computed"}


def test_qdrant_store_satisfies_vector_store_contract():
    client = FakeQdrantClient()
    store = QdrantStore(client=client)

    try:
        assert isinstance(store, VectorStore)
    finally:
        store.close()
