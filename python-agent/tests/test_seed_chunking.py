import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rag.seed_chunking import expand_seed_record
import rag.seed_milvus as seed_milvus


def test_expand_seed_record_keeps_short_component_as_one_record():
    item = {
        "component_name": "SearchFilter",
        "code_snippet": "<template>...</template>",
        "framework": "vue3",
        "use_count": 1,
    }

    records = expand_seed_record(
        item,
        name_field="component_name",
        content_field="code_snippet",
        max_chars=1200,
    )

    assert len(records) == 1
    assert records[0]["component_name"] == "SearchFilter"
    assert records[0]["code_snippet"] == "<template>...</template>"


def test_expand_seed_record_splits_long_component_into_chunked_records():
    item = {
        "component_name": "BigForm",
        "code_snippet": (
            "section-a\n" + ("a" * 700) + "\n\n"
            "section-b\n" + ("b" * 700) + "\n\n"
            "section-c\n" + ("c" * 700)
        ),
        "framework": "vue3",
        "use_count": 1,
    }

    records = expand_seed_record(
        item,
        name_field="component_name",
        content_field="code_snippet",
        max_chars=1200,
    )

    assert len(records) >= 2
    assert all(len(record["code_snippet"]) <= 1200 for record in records)
    assert records[0]["component_name"].startswith("BigForm")
    assert records[-1]["component_name"].startswith("BigForm")


def test_seed_collection_chunks_component_library_records(monkeypatch):
    inserted = []

    class FakeEmbeddingService:
        def embed(self, text):
            return [0.1, 0.2, 0.3]

    class FakeMilvusStore:
        def connect(self):
            return None

        def ensure_collection(self, collection_name):
            return None

        def insert_one(self, collection_name, data):
            inserted.append((collection_name, data))

    monkeypatch.setattr(seed_milvus, "embedding_service", FakeEmbeddingService())
    monkeypatch.setattr(seed_milvus, "milvus_store", FakeMilvusStore())

    seed_milvus.seed_collection(
        "component_library",
        [
            {
                "component_name": "MegaEditor",
                "code_snippet": (
                    "section-a\n" + ("a" * 700) + "\n\n"
                    "section-b\n" + ("b" * 700) + "\n\n"
                    "section-c\n" + ("c" * 700)
                ),
                "framework": "vue3",
                "use_count": 1,
            }
        ],
        "code_snippet",
    )

    assert len(inserted) >= 2
    assert all(name == "component_library" for name, _ in inserted)
    assert all(len(payload["code_snippet"]) <= 1200 for _, payload in inserted)
    assert all(payload["component_name"].startswith("MegaEditor") for _, payload in inserted)
