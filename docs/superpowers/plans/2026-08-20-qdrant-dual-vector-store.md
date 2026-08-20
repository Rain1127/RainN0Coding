# Qdrant Dual Vector Store Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Qdrant as a selectable Python Agent vector backend while preserving Milvus/Milvus Lite and keeping the existing RAG result contract stable.

**Architecture:** Introduce a `VectorStore` protocol, a provider factory, a Qdrant adapter, and a compatibility re-export for the existing Milvus adapter. Application and seed code import one provider-selected `vector_store`; both adapters normalize hits to `id`, `distance`, and `entity`.

**Tech Stack:** Python 3.12, pytest, qdrant-client 1.18.x, Qdrant 1.18.2, pymilvus, Docker Compose, FastAPI.

---

## File map

**Create**

- `python-agent/rag/vector_store/__init__.py` — exports the selected singleton.
- `python-agent/rag/vector_store/base.py` — backend contract.
- `python-agent/rag/vector_store/factory.py` — provider validation and construction.
- `python-agent/rag/vector_store/milvus_store.py` — compatibility re-export of the existing Milvus adapter.
- `python-agent/rag/vector_store/qdrant_store.py` — Qdrant implementation and result normalization.
- `python-agent/rag/seed_vector_store.py` — provider-independent seed entrypoint.
- `python-agent/tests/test_vector_store_config.py` — environment configuration tests.
- `python-agent/tests/test_vector_store_factory.py` — provider/factory tests.
- `python-agent/tests/test_qdrant_store.py` — adapter unit tests.
- `python-agent/tests/test_qdrant_integration.py` — real Docker Qdrant tests.
- `qdrant/docker-compose.yml` — pinned local Qdrant service.

**Modify**

- `python-agent/pyproject.toml` — add `qdrant-client`.
- `python-agent/uv.lock` — lock the new client dependency.
- `python-agent/config.py` — provider and Qdrant settings.
- `python-agent/.env.example` — document both providers.
- `python-agent/rag/milvus_client.py` — add structured filters, count/reset aliases, and per-query degradation.
- `python-agent/rag/retrieval_engine.py` — use generic store singleton.
- `python-agent/rag/semantic_engine.py` — use generic store singleton.
- `python-agent/rag/rag_builder.py` — use generic store singleton and neutral naming.
- `python-agent/server/main.py` — generic health fields with legacy Milvus fields retained.
- `python-agent/server/lifespan.py` — generic close/cleanup and structured delete filters.
- `python-agent/rag/seed_milvus.py` — compatibility wrapper.
- `python-agent/tests/test_seed_chunking.py` — patch the new seed module.
- `python-agent/tests/conftest.py` — allow Qdrant integration tests under the integration marker.

Do not modify the already-dirty repository-root `pyproject.toml` or root `uv.lock`.

### Task 1: Establish the baseline and add configuration

**Files:**

- Create: `python-agent/tests/test_vector_store_config.py`
- Modify: `python-agent/config.py:38-44`
- Modify: `python-agent/.env.example:19-21`
- Modify: `python-agent/pyproject.toml:6-36`
- Modify: `python-agent/uv.lock`

- [ ] **Step 1: Record the current working tree and baseline tests**

Run from `D:\yu-ai-code-mother`:

```powershell
git status --short
$env:PYTHONPATH='D:\yu-ai-code-mother\python-agent'
& 'D:\yu-ai-code-mother\python-agent\.venv\Scripts\python.exe' -m pytest python-agent/tests/test_seed_chunking.py python-agent/tests/test_retrieval_common.py -q
```

Expected: existing unrelated changes remain visible; the focused tests pass before migration work starts.

- [ ] **Step 2: Write failing configuration tests**

Create `python-agent/tests/test_vector_store_config.py`:

```python
import importlib
import sys

import pytest


@pytest.fixture(autouse=True)
def _remove_reloaded_config_after_test():
    yield
    sys.modules.pop("config", None)


def _reload_config(monkeypatch, **env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    sys.modules.pop("config", None)
    return importlib.import_module("config").config


def test_vector_store_defaults_to_milvus(monkeypatch):
    monkeypatch.delenv("VECTOR_DB_PROVIDER", raising=False)
    config = _reload_config(monkeypatch)
    assert config.VECTOR_DB_PROVIDER == "milvus"


def test_qdrant_settings_are_read_from_environment(monkeypatch):
    config = _reload_config(
        monkeypatch,
        VECTOR_DB_PROVIDER="qdrant",
        QDRANT_URL="http://localhost:6333",
        QDRANT_API_KEY="local-key",
        QDRANT_TIMEOUT_SECONDS="7",
    )
    assert config.VECTOR_DB_PROVIDER == "qdrant"
    assert config.QDRANT_URL == "http://localhost:6333"
    assert config.QDRANT_API_KEY == "local-key"
    assert config.QDRANT_TIMEOUT_SECONDS == 7.0
```

- [ ] **Step 3: Run the test and verify failure**

```powershell
$env:PYTHONPATH='D:\yu-ai-code-mother\python-agent'
& 'D:\yu-ai-code-mother\python-agent\.venv\Scripts\python.exe' -m pytest python-agent/tests/test_vector_store_config.py -q
```

Expected: FAIL because `VECTOR_DB_PROVIDER` and Qdrant settings do not exist.

- [ ] **Step 4: Add the configuration fields**

In `python-agent/config.py`, replace the current Milvus section with:

```python
    # ===== Vector database =====
    VECTOR_DB_PROVIDER: str = os.getenv("VECTOR_DB_PROVIDER", "milvus").strip().lower()

    # ===== Milvus =====
    MILVUS_HOST: str = os.getenv("MILVUS_HOST", "localhost")
    MILVUS_PORT: int = int(os.getenv("MILVUS_PORT", "19530"))

    # ===== Qdrant =====
    QDRANT_URL: str = os.getenv("QDRANT_URL", "http://localhost:6333").rstrip("/")
    QDRANT_API_KEY: str = os.getenv("QDRANT_API_KEY", "")
    QDRANT_TIMEOUT_SECONDS: float = float(os.getenv("QDRANT_TIMEOUT_SECONDS", "10"))
```

In `python-agent/.env.example`, add above the existing Milvus settings:

```env
# Vector database provider: milvus | qdrant
VECTOR_DB_PROVIDER=milvus

# Qdrant (used when VECTOR_DB_PROVIDER=qdrant)
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
QDRANT_TIMEOUT_SECONDS=10
```

- [ ] **Step 5: Add and install the pinned client dependency**

Add this entry to `python-agent/pyproject.toml` dependencies:

```toml
    "qdrant-client>=1.18,<1.19",
```

Then run:

```powershell
uv lock --project python-agent
& 'D:\yu-ai-code-mother\python-agent\.venv\Scripts\python.exe' -m pip install 'qdrant-client>=1.18,<1.19'
```

Expected: only `python-agent/uv.lock` is regenerated; the installed client reports a 1.18.x version.

Verify:

```powershell
& 'D:\yu-ai-code-mother\python-agent\.venv\Scripts\python.exe' -c "import qdrant_client; from importlib.metadata import version; print(version('qdrant-client'))"
```

- [ ] **Step 6: Run configuration tests**

```powershell
$env:PYTHONPATH='D:\yu-ai-code-mother\python-agent'
& 'D:\yu-ai-code-mother\python-agent\.venv\Scripts\python.exe' -m pytest python-agent/tests/test_vector_store_config.py -q
```

Expected: `2 passed`.

- [ ] **Step 7: Commit only Task 1 files**

```powershell
git add python-agent/config.py python-agent/.env.example python-agent/pyproject.toml python-agent/uv.lock python-agent/tests/test_vector_store_config.py
git commit -m "feat: configure selectable vector database"
```

### Task 2: Define the contract and preserve Milvus compatibility

**Files:**

- Create: `python-agent/rag/vector_store/base.py`
- Create: `python-agent/rag/vector_store/milvus_store.py`
- Modify: `python-agent/rag/milvus_client.py`
- Create: `python-agent/tests/test_vector_store_factory.py` initially with contract tests

- [ ] **Step 1: Write the failing Milvus contract test**

Create `python-agent/tests/test_vector_store_factory.py`:

```python
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
    assert REQUIRED_METHODS <= set(dir(MilvusStore))
```

- [ ] **Step 2: Run it and verify failure**

```powershell
$env:PYTHONPATH='D:\yu-ai-code-mother\python-agent'
& 'D:\yu-ai-code-mother\python-agent\.venv\Scripts\python.exe' -m pytest python-agent/tests/test_vector_store_factory.py -q
```

Expected: FAIL listing missing structured-filter/count/reset methods.

- [ ] **Step 3: Add the VectorStore protocol**

Create `python-agent/rag/vector_store/base.py`:

```python
from typing import Protocol, runtime_checkable


FilterMap = dict[str, object]


@runtime_checkable
class VectorStore(Protocol):
    def connect(self) -> None: pass
    def init_collections(self) -> None: pass
    def ensure_collection(self, collection_name: str) -> None: pass
    def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 5,
        output_fields: list[str] | None = None,
    ) -> list[dict]: pass
    def search_multi(self, queries: list[tuple]) -> list[list[dict]]: pass
    async def search_async(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 5,
        output_fields: list[str] | None = None,
    ) -> list[dict]: pass
    async def search_multi_async(self, queries: list[tuple]) -> list[list[dict]]: pass
    def insert_one(self, collection_name: str, data: dict) -> None: pass
    def delete_by_filters(self, collection_name: str, filters: FilterMap) -> int: pass
    def query_by_filters(
        self,
        collection_name: str,
        filters: FilterMap,
        output_fields: list[str] | None = None,
        limit: int = 100,
    ) -> list[dict]: pass
    def count(self, collection_name: str) -> int: pass
    def reset_all(self) -> None: pass
    def close(self) -> None: pass
```

- [ ] **Step 4: Add structured-filter compatibility to MilvusStore**

Add `import json` near the top of `python-agent/rag/milvus_client.py`.

Add these methods before the internal-method section:

```python
    @staticmethod
    def _filters_to_expr(filters: dict[str, object]) -> str:
        if not filters:
            raise ValueError("filters must not be empty")
        return " && ".join(
            f"{field} == {json.dumps(value, ensure_ascii=False)}"
            for field, value in filters.items()
        )

    def delete_by_filters(self, collection_name: str, filters: dict[str, object]) -> int:
        return self.delete_by_expr(collection_name, self._filters_to_expr(filters))

    def query_by_filters(
        self,
        collection_name: str,
        filters: dict[str, object],
        output_fields: list[str] | None = None,
        limit: int = 100,
    ) -> list[dict]:
        return self.query(
            collection_name,
            self._filters_to_expr(filters),
            output_fields,
            limit,
        )

    def count(self, collection_name: str) -> int:
        self.connect()
        if collection_name not in self._client.list_collections():
            return 0
        self._load_collection(collection_name)
        stats = self._client.get_collection_stats(collection_name=collection_name)
        return int(stats.get("row_count", 0))

    def reset_all(self) -> None:
        self.connect()
        self._cleanup()
```

In `search_multi`, replace `results[idx] = f.result()` with per-query degradation:

```python
            try:
                results[idx] = f.result()
            except Exception as exc:
                print(f"[Milvus] search failed: {exc}")
                results[idx] = []
```

- [ ] **Step 5: Add the Milvus compatibility re-export**

Create `python-agent/rag/vector_store/milvus_store.py`:

```python
from rag.milvus_client import MilvusStore, milvus_store

__all__ = ["MilvusStore", "milvus_store"]
```

- [ ] **Step 6: Run the contract and existing tests**

```powershell
$env:PYTHONPATH='D:\yu-ai-code-mother\python-agent'
& 'D:\yu-ai-code-mother\python-agent\.venv\Scripts\python.exe' -m pytest python-agent/tests/test_vector_store_factory.py python-agent/tests/test_seed_chunking.py python-agent/tests/test_retrieval_common.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit Task 2**

```powershell
git add python-agent/rag/vector_store/base.py python-agent/rag/vector_store/milvus_store.py python-agent/rag/milvus_client.py python-agent/tests/test_vector_store_factory.py
git commit -m "refactor: define vector store contract"
```

### Task 3: Implement the Qdrant adapter with unit tests

**Files:**

- Create: `python-agent/rag/vector_store/qdrant_store.py`
- Create: `python-agent/tests/test_qdrant_store.py`

- [ ] **Step 1: Write failing adapter tests**

Create `python-agent/tests/test_qdrant_store.py`:

```python
from types import SimpleNamespace

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
            points=[SimpleNamespace(id="point-1", score=0.91, payload={"api_name": "ref"})]
        )

    def upsert(self, **kwargs):
        self.upserts.append(kwargs)

    def close(self):
        return None


def test_qdrant_store_creates_512d_cosine_collection():
    client = FakeQdrantClient()
    store = QdrantStore(client=client)
    store.ensure_collection("framework_api")
    assert client.created[0][0] == "framework_api"
    assert client.created[0][1].size == 512
    assert client.created[0][1].distance.value == "Cosine"


def test_qdrant_search_normalizes_existing_result_contract():
    client = FakeQdrantClient()
    client.collections.add("framework_api")
    store = QdrantStore(client=client)
    results = store.search("framework_api", [0.0] * 512, limit=1)
    assert results == [
        {"id": "point-1", "distance": 0.91, "entity": {"api_name": "ref"}}
    ]


def test_qdrant_insert_splits_vector_from_payload():
    client = FakeQdrantClient()
    client.collections.add("framework_api")
    store = QdrantStore(client=client)
    store.insert_one(
        "framework_api",
        {"vector": [0.1] * 512, "api_name": "computed"},
    )
    point = client.upserts[0]["points"][0]
    assert point.vector == [0.1] * 512
    assert point.payload == {"api_name": "computed"}
```

- [ ] **Step 2: Run tests and verify import failure**

```powershell
$env:PYTHONPATH='D:\yu-ai-code-mother\python-agent'
& 'D:\yu-ai-code-mother\python-agent\.venv\Scripts\python.exe' -m pytest python-agent/tests/test_qdrant_store.py -q
```

Expected: collection error because `qdrant_store.py` does not exist.

- [ ] **Step 3: Implement QdrantStore**

Create `python-agent/rag/vector_store/qdrant_store.py`:

```python
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from uuid import uuid4

from qdrant_client import QdrantClient, models

from config import config


logger = logging.getLogger(__name__)


class QdrantStore:
    COLLECTIONS = {
        "component_library": 512,
        "code_store": 512,
        "design_pattern": 512,
        "error_pattern": 512,
        "framework_api": 512,
    }

    OUTPUT_FIELDS_MAP = {
        "component_library": ["component_name", "code_snippet", "framework", "use_count"],
        "code_store": ["app_id", "file_path", "content", "code_gen_type", "tags"],
        "design_pattern": ["pattern_name", "description", "example_code", "best_for"],
        "error_pattern": ["error_signature", "fix_code", "occurrence_count"],
        "framework_api": ["api_name", "signature", "import_statement", "example", "framework"],
    }

    def __init__(self, client: QdrantClient | None = None):
        self._client = client or QdrantClient(
            url=config.QDRANT_URL,
            api_key=config.QDRANT_API_KEY or None,
            timeout=config.QDRANT_TIMEOUT_SECONDS,
        )
        self._connected = False
        self._executor = ThreadPoolExecutor(
            max_workers=config.RAG_PARALLEL_WORKERS,
            thread_name_prefix="qdrant",
        )

    def connect(self) -> None:
        if self._connected:
            return
        self._client.get_collections()
        self._connected = True

    def init_collections(self) -> None:
        self.connect()
        for collection_name in self.COLLECTIONS:
            self.ensure_collection(collection_name)

    def ensure_collection(self, collection_name: str) -> None:
        self.connect()
        if self._client.collection_exists(collection_name=collection_name):
            return
        self._client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(
                size=self.COLLECTIONS.get(collection_name, 512),
                distance=models.Distance.COSINE,
            ),
        )

    def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 5,
        output_fields: list[str] | None = None,
    ) -> list[dict]:
        self.connect()
        if not self._client.collection_exists(collection_name=collection_name):
            return []
        payload_selector = output_fields or self.OUTPUT_FIELDS_MAP.get(collection_name) or True
        response = self._client.query_points(
            collection_name=collection_name,
            query=query_vector,
            limit=limit,
            with_payload=payload_selector,
        )
        return [
            {
                "id": point.id,
                "distance": float(point.score),
                "entity": dict(point.payload or {}),
            }
            for point in response.points
        ]

    def search_multi(self, queries: list[tuple]) -> list[list[dict]]:
        if not queries:
            return []
        futures = {}
        for index, query in enumerate(queries):
            collection_name = query[0]
            query_vector = query[1]
            limit = query[2] if len(query) > 2 else 5
            output_fields = query[3] if len(query) > 3 else None
            future = self._executor.submit(
                self.search,
                collection_name,
                query_vector,
                limit,
                output_fields,
            )
            futures[future] = index
        results: list[list[dict]] = [[] for _ in queries]
        for future in as_completed(futures):
            index = futures[future]
            try:
                results[index] = future.result()
            except Exception as exc:
                logger.warning("Qdrant search failed: %s", exc)
                results[index] = []
        return results

    async def search_async(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 5,
        output_fields: list[str] | None = None,
    ) -> list[dict]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor,
            self.search,
            collection_name,
            query_vector,
            limit,
            output_fields,
        )

    async def search_multi_async(self, queries: list[tuple]) -> list[list[dict]]:
        if not queries:
            return []
        tasks = [
            self.search_async(
                query[0],
                query[1],
                query[2] if len(query) > 2 else 5,
                query[3] if len(query) > 3 else None,
            )
            for query in queries
        ]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        return [result if isinstance(result, list) else [] for result in raw_results]

    def insert_one(self, collection_name: str, data: dict) -> None:
        self.ensure_collection(collection_name)
        record = dict(data)
        vector = record.pop("vector", None)
        if vector is None:
            raise ValueError("data must contain vector")
        self._client.upsert(
            collection_name=collection_name,
            points=[
                models.PointStruct(
                    id=str(uuid4()),
                    vector=vector,
                    payload=record,
                )
            ],
            wait=True,
        )

    @staticmethod
    def _build_filter(filters: dict[str, object]) -> models.Filter:
        if not filters:
            raise ValueError("filters must not be empty")
        return models.Filter(
            must=[
                models.FieldCondition(
                    key=field,
                    match=models.MatchValue(value=value),
                )
                for field, value in filters.items()
            ]
        )

    def delete_by_filters(self, collection_name: str, filters: dict[str, object]) -> int:
        self.connect()
        if not self._client.collection_exists(collection_name=collection_name):
            return 0
        query_filter = self._build_filter(filters)
        matched = self._client.count(
            collection_name=collection_name,
            count_filter=query_filter,
            exact=True,
        ).count
        self._client.delete(
            collection_name=collection_name,
            points_selector=models.FilterSelector(filter=query_filter),
            wait=True,
        )
        return int(matched)

    def query_by_filters(
        self,
        collection_name: str,
        filters: dict[str, object],
        output_fields: list[str] | None = None,
        limit: int = 100,
    ) -> list[dict]:
        self.connect()
        if not self._client.collection_exists(collection_name=collection_name):
            return []
        points, _ = self._client.scroll(
            collection_name=collection_name,
            scroll_filter=self._build_filter(filters),
            limit=limit,
            with_payload=output_fields or True,
            with_vectors=False,
        )
        return [{"id": point.id, **dict(point.payload or {})} for point in points]

    def count(self, collection_name: str) -> int:
        self.connect()
        if not self._client.collection_exists(collection_name=collection_name):
            return 0
        return int(self._client.count(collection_name=collection_name, exact=True).count)

    def reset_all(self) -> None:
        self.connect()
        for collection_name in self.COLLECTIONS:
            if self._client.collection_exists(collection_name=collection_name):
                self._client.delete_collection(collection_name=collection_name)

    def close(self) -> None:
        self._executor.shutdown(wait=False)
        close = getattr(self._client, "close", None)
        if callable(close):
            close()
```

- [ ] **Step 4: Run Qdrant adapter tests**

```powershell
$env:PYTHONPATH='D:\yu-ai-code-mother\python-agent'
& 'D:\yu-ai-code-mother\python-agent\.venv\Scripts\python.exe' -m pytest python-agent/tests/test_qdrant_store.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit Task 3**

```powershell
git add python-agent/rag/vector_store/qdrant_store.py python-agent/tests/test_qdrant_store.py
git commit -m "feat: add qdrant vector store adapter"
```

### Task 4: Add the factory and switch application call sites

**Files:**

- Create: `python-agent/rag/vector_store/factory.py`
- Create: `python-agent/rag/vector_store/__init__.py`
- Modify: `python-agent/tests/test_vector_store_factory.py`
- Modify: `python-agent/rag/retrieval_engine.py`
- Modify: `python-agent/rag/semantic_engine.py`
- Modify: `python-agent/rag/rag_builder.py`
- Modify: `python-agent/server/main.py`
- Modify: `python-agent/server/lifespan.py`

- [ ] **Step 1: Add failing factory tests**

Append to `python-agent/tests/test_vector_store_factory.py`:

```python
import pytest

from rag.milvus_client import milvus_store
from rag.vector_store.factory import create_vector_store
from rag.vector_store.qdrant_store import QdrantStore


def test_factory_returns_existing_milvus_singleton():
    assert create_vector_store("milvus") is milvus_store


def test_factory_creates_qdrant_store():
    assert isinstance(create_vector_store("qdrant"), QdrantStore)


def test_factory_rejects_unknown_provider():
    with pytest.raises(ValueError, match="milvus, qdrant"):
        create_vector_store("unknown")
```

- [ ] **Step 2: Run and verify factory import failure**

```powershell
$env:PYTHONPATH='D:\yu-ai-code-mother\python-agent'
& 'D:\yu-ai-code-mother\python-agent\.venv\Scripts\python.exe' -m pytest python-agent/tests/test_vector_store_factory.py -q
```

Expected: FAIL because `factory.py` does not exist.

- [ ] **Step 3: Implement the factory and selected singleton**

Create `python-agent/rag/vector_store/factory.py`:

```python
from config import config
from rag.vector_store.base import VectorStore


def create_vector_store(provider: str | None = None) -> VectorStore:
    selected = (provider or config.VECTOR_DB_PROVIDER).strip().lower()
    if selected == "milvus":
        from rag.vector_store.milvus_store import milvus_store
        return milvus_store
    if selected == "qdrant":
        from rag.vector_store.qdrant_store import QdrantStore
        return QdrantStore()
    raise ValueError(
        f"Unsupported VECTOR_DB_PROVIDER={selected!r}; expected one of: milvus, qdrant"
    )
```

Create `python-agent/rag/vector_store/__init__.py`:

```python
from rag.vector_store.base import VectorStore
from rag.vector_store.factory import create_vector_store


vector_store: VectorStore = create_vector_store()

__all__ = ["VectorStore", "create_vector_store", "vector_store"]
```

- [ ] **Step 4: Run factory tests**

```powershell
$env:PYTHONPATH='D:\yu-ai-code-mother\python-agent'
& 'D:\yu-ai-code-mother\python-agent\.venv\Scripts\python.exe' -m pytest python-agent/tests/test_vector_store_factory.py -q
```

Expected: all factory and contract tests pass.

- [ ] **Step 5: Replace application imports and neutralize variable names**

In `retrieval_engine.py` and `semantic_engine.py`, replace the import with:

```python
from rag.vector_store import vector_store
```

Use the IDE's Rename Symbol operation in only those two files to rename the imported identifier `milvus_store` to `vector_store`. This changes all existing `milvus_store.search_multi` calls to `vector_store.search_multi` without changing their arguments.

In `rag_builder.py`, rename `_milvus_store` to `_vector_store`, rename `_lazy_import_milvus()` to `_lazy_import_vector_store()`, and change the lazy import to:

```python
from rag.vector_store import vector_store
_vector_store = vector_store
```

In `index_code_files`, keep the existing arguments unchanged while replacing the receiver on these calls: `_milvus_store.connect()` becomes `_vector_store.connect()`, `_milvus_store.ensure_collection("code_store")` becomes `_vector_store.ensure_collection("code_store")`, and `_milvus_store.insert_one` becomes `_vector_store.insert_one`.

In `server/lifespan.py`, replace Milvus imports with:

```python
from rag.vector_store import vector_store
```

During shutdown call:

```python
vector_store.close()
logger.info("Vector store connection closed")
```

During quality cleanup replace the Milvus expression with:

```python
count = vector_store.delete_by_filters(
    "code_store",
    {"app_id": e_app_id, "file_path": e_file_path},
)
```

Rename `deleted_milvus` to `deleted_vectors` and log “vector store delete failed”.

- [ ] **Step 6: Make health output provider-neutral while retaining old fields**

In `server/main.py`, replace the current Milvus health block with:

```python
    vector_store_ok = False
    try:
        from rag.vector_store import vector_store
        vector_store.connect()
        vector_store_ok = True
    except Exception:
        pass
```

Replace the Milvus health response fields with:

```python
            "vector_store_connected": vector_store_ok,
            "vector_db_provider": _config().VECTOR_DB_PROVIDER,
            "milvus_connected": (
                vector_store_ok if _config().VECTOR_DB_PROVIDER == "milvus" else False
            ),
            "milvus_mode": (
                _config().MILVUS_MODE if _config().VECTOR_DB_PROVIDER == "milvus" else None
            ),
```

- [ ] **Step 7: Verify no production module still directly imports the Milvus singleton**

```powershell
rg -n 'from rag\.milvus_client import milvus_store' python-agent --glob '*.py' --glob '!tests/**' --glob '!rag/seed_milvus.py'
```

Expected: no output.

- [ ] **Step 8: Run focused regression tests**

```powershell
$env:PYTHONPATH='D:\yu-ai-code-mother\python-agent'
& 'D:\yu-ai-code-mother\python-agent\.venv\Scripts\python.exe' -m pytest python-agent/tests/test_vector_store_factory.py python-agent/tests/test_qdrant_store.py python-agent/tests/test_internal_auth_and_concurrency.py python-agent/tests/test_retrieval_common.py -q
```

Expected: all selected tests pass.

- [ ] **Step 9: Commit Task 4**

```powershell
git add python-agent/rag/vector_store python-agent/rag/retrieval_engine.py python-agent/rag/semantic_engine.py python-agent/rag/rag_builder.py python-agent/server/main.py python-agent/server/lifespan.py python-agent/tests/test_vector_store_factory.py
git commit -m "refactor: route rag through selected vector store"
```

### Task 5: Make seed ingestion provider-independent

**Files:**

- Create: `python-agent/rag/seed_vector_store.py`
- Modify: `python-agent/rag/seed_milvus.py`
- Modify: `python-agent/tests/test_seed_chunking.py`

- [ ] **Step 1: Update the existing seed test to target the generic module**

In `python-agent/tests/test_seed_chunking.py`, replace:

```python
import rag.seed_milvus as seed_milvus
```

with:

```python
import rag.seed_vector_store as seed_vector_store
```

Rename `FakeMilvusStore` to `FakeVectorStore`, and replace both monkeypatches and the function call with:

```python
monkeypatch.setattr(seed_vector_store, "embedding_service", FakeEmbeddingService())
monkeypatch.setattr(seed_vector_store, "vector_store", FakeVectorStore())

seed_vector_store.seed_collection(
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
```

- [ ] **Step 2: Run and verify module import failure**

```powershell
$env:PYTHONPATH='D:\yu-ai-code-mother\python-agent'
& 'D:\yu-ai-code-mother\python-agent\.venv\Scripts\python.exe' -m pytest python-agent/tests/test_seed_chunking.py -q
```

Expected: FAIL because `seed_vector_store.py` does not exist.

- [ ] **Step 3: Create the provider-independent seed script from the existing script**

Copy the existing file:

```powershell
Copy-Item -LiteralPath 'python-agent\rag\seed_milvus.py' -Destination 'python-agent\rag\seed_vector_store.py'
```

In the new file, replace the store import with:

```python
from rag.vector_store import vector_store
```

Replace every `milvus_store` reference with `vector_store` and replace user-facing “Milvus” messages with “vector store”. Replace `seed_collection` with this complete implementation:

```python
def seed_collection(
    collection_name: str,
    data: list[dict],
    text_field: str,
) -> tuple[int, int]:
    vector_store.connect()
    vector_store.ensure_collection(collection_name)

    inserted_count = 0
    failed_count = 0
    for item in data:
        if collection_name == "component_library":
            records = expand_seed_record(
                item,
                name_field="component_name",
                content_field=text_field,
                max_chars=1200,
            )
        else:
            records = [dict(item)]

        for record in records:
            text = record.get(text_field, "")
            if not text:
                continue
            name = (
                record.get("api_name")
                or record.get("component_name")
                or record.get("pattern_name")
                or record.get("error_signature")
                or "?"
            )
            try:
                vector = embedding_service.embed(text)
            except Exception as exc:
                print(f"  [SKIP] embed 失败: {name}: {exc}")
                failed_count += 1
                continue
            try:
                vector_store.insert_one(
                    collection_name,
                    {
                        "vector": vector,
                        **{key: value for key, value in record.items() if key != "vector"},
                    },
                )
                inserted_count += 1
            except Exception as exc:
                print(f"  [FAIL] {name}: {exc}")
                failed_count += 1

    print(
        f"  {collection_name}: {inserted_count} 条向量 / "
        f"{len(data)} 个原始条目 / {failed_count} 条失败"
    )
    return inserted_count, failed_count
```

Replace `main` with:

```python
def main() -> None:
    print("=" * 50)
    print("RAG 种子数据入库")
    print("=" * 50)
    vector_store.init_collections()

    seed_jobs = [
        ("framework_api", FRAMEWORK_API_SEEDS, "example"),
        ("component_library", COMPONENT_LIBRARY_SEEDS, "code_snippet"),
        ("design_pattern", DESIGN_PATTERN_SEEDS, "description"),
        ("error_pattern", ERROR_PATTERN_SEEDS, "fix_code"),
    ]
    total_failures = 0
    for index, (collection_name, records, text_field) in enumerate(seed_jobs, start=1):
        print(f"\n[{index}/{len(seed_jobs)}] {collection_name}")
        _, failed_count = seed_collection(collection_name, records, text_field)
        total_failures += failed_count

    print("\n[SQLite] 同步写入 FTS5 索引")
    sqlite_store.seed_all(
        FRAMEWORK_API_SEEDS,
        COMPONENT_LIBRARY_SEEDS,
        ERROR_PATTERN_SEEDS,
    )

    print("\n向量集合统计:")
    for collection_name, _, _ in seed_jobs:
        try:
            print(f"  {collection_name}: {vector_store.count(collection_name)} 条")
        except Exception as exc:
            print(f"  {collection_name}: 统计失败: {exc}")
            total_failures += 1

    if total_failures:
        print(f"\n入库存在 {total_failures} 条失败记录")
        raise SystemExit(1)
    print("\n全部入库完成！")
```

Keep the existing module guard:

```python
if __name__ == "__main__":
    main()
```

This makes partial seed failure visible to shells and CI.

- [ ] **Step 4: Turn the old script into a compatibility wrapper**

Replace `python-agent/rag/seed_milvus.py` with:

```python
"""Deprecated compatibility entrypoint; use rag/seed_vector_store.py."""
import warnings

from rag.seed_vector_store import main, seed_collection


if __name__ == "__main__":
    warnings.warn(
        "seed_milvus.py is deprecated; use seed_vector_store.py",
        DeprecationWarning,
        stacklevel=1,
    )
    main()
```

- [ ] **Step 5: Run seed unit tests**

```powershell
$env:PYTHONPATH='D:\yu-ai-code-mother\python-agent'
& 'D:\yu-ai-code-mother\python-agent\.venv\Scripts\python.exe' -m pytest python-agent/tests/test_seed_chunking.py -q
```

Expected: all seed chunking tests pass.

- [ ] **Step 6: Commit Task 5**

```powershell
git add python-agent/rag/seed_vector_store.py python-agent/rag/seed_milvus.py python-agent/tests/test_seed_chunking.py
git commit -m "refactor: make rag seeding provider independent"
```

### Task 6: Add pinned local Qdrant and real integration tests

**Files:**

- Create: `qdrant/docker-compose.yml`
- Create: `python-agent/tests/test_qdrant_integration.py`
- Modify: `python-agent/tests/conftest.py:20-38`

- [ ] **Step 1: Add the pinned Docker Compose service**

Create `qdrant/docker-compose.yml`:

```yaml
services:
  qdrant:
    image: qdrant/qdrant:v1.18.2
    container_name: rainn0coding-qdrant
    ports:
      - "127.0.0.1:6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "bash", "-c", "</dev/tcp/127.0.0.1/6333"]
      interval: 10s
      timeout: 5s
      retries: 10

volumes:
  qdrant_data:
```

- [ ] **Step 2: Start Qdrant and verify health**

```powershell
docker compose -f qdrant/docker-compose.yml up -d
docker compose -f qdrant/docker-compose.yml ps
Invoke-RestMethod 'http://localhost:6333/healthz'
```

Expected: container status is healthy and the endpoint responds successfully.

- [ ] **Step 3: Write the real integration test**

Create `python-agent/tests/test_qdrant_integration.py`:

```python
from uuid import uuid4

import pytest
from qdrant_client import QdrantClient

from rag.vector_store.qdrant_store import QdrantStore


pytestmark = pytest.mark.integration


def test_qdrant_round_trip_and_persistence_boundary():
    client = QdrantClient(url="http://localhost:6333", timeout=5)
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
        assert store.query_by_filters(collection_name, {"kind": "expected"})
        assert store.delete_by_filters(collection_name, {"kind": "expected"}) == 1
        assert store.count(collection_name) == 0
    finally:
        if client.collection_exists(collection_name):
            client.delete_collection(collection_name)
        store.COLLECTIONS.pop(collection_name, None)
        store.close()
```

- [ ] **Step 4: Add the integration test to the marker allowlist**

In `python-agent/tests/conftest.py`, add this filename to `MARKER_FILE_ALLOWLIST["integration"]`:

```python
        "test_qdrant_integration.py",
```

- [ ] **Step 5: Run the real integration test**

```powershell
$env:PYTHONPATH='D:\yu-ai-code-mother\python-agent'
& 'D:\yu-ai-code-mother\python-agent\.venv\Scripts\python.exe' -m pytest python-agent/tests/test_qdrant_integration.py -v
```

Expected: `1 passed` and the temporary collection is removed.

- [ ] **Step 6: Commit Task 6**

```powershell
git add qdrant/docker-compose.yml python-agent/tests/test_qdrant_integration.py python-agent/tests/conftest.py
git commit -m "test: add local qdrant integration coverage"
```

### Task 7: Seed Qdrant and verify the application contract

**Files:**

- Modify local only: `python-agent/.env` (do not commit secrets)

- [ ] **Step 1: Switch the local provider**

In `python-agent/.env`, set:

```env
VECTOR_DB_PROVIDER=qdrant
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
QDRANT_TIMEOUT_SECONDS=10
```

- [ ] **Step 2: Seed Qdrant**

```powershell
$env:PYTHONPATH='D:\yu-ai-code-mother\python-agent'
Push-Location 'python-agent'
& '.\.venv\Scripts\python.exe' 'rag\seed_vector_store.py'
Pop-Location
```

Expected: four seeded collections report non-zero counts; `code_store` exists and may remain empty; the command exits with code 0.

- [ ] **Step 3: Inspect collection names through Qdrant**

```powershell
Invoke-RestMethod 'http://localhost:6333/collections' | ConvertTo-Json -Depth 6
```

Expected: `framework_api`, `component_library`, `design_pattern`, `error_pattern`, and `code_store` are present.

- [ ] **Step 4: Run the focused RAG regression suite**

```powershell
$env:PYTHONPATH='D:\yu-ai-code-mother\python-agent'
& 'D:\yu-ai-code-mother\python-agent\.venv\Scripts\python.exe' -m pytest python-agent/tests/test_vector_store_config.py python-agent/tests/test_vector_store_factory.py python-agent/tests/test_qdrant_store.py python-agent/tests/test_qdrant_integration.py python-agent/tests/test_seed_chunking.py python-agent/tests/test_retrieval_common.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Start Python Agent and inspect health**

```powershell
$env:PYTHONPATH='D:\yu-ai-code-mother\python-agent'
Push-Location 'python-agent'
& '.\.venv\Scripts\python.exe' 'server\main.py'
```

In a second PowerShell window:

```powershell
Invoke-RestMethod 'http://localhost:8000/api/health' | ConvertTo-Json
```

Expected fields:

```json
{
  "vector_store_connected": true,
  "vector_db_provider": "qdrant",
  "milvus_connected": false,
  "milvus_mode": null
}
```

- [ ] **Step 6: Verify container restart persistence**

Stop the Python Agent with `Ctrl+C`, then run:

```powershell
docker compose -f qdrant/docker-compose.yml restart qdrant
docker compose -f qdrant/docker-compose.yml ps
Invoke-RestMethod 'http://localhost:6333/collections' | ConvertTo-Json -Depth 6
```

Expected: Qdrant becomes healthy again and the five collections still exist.

### Task 8: Verify Milvus rollback and full Python regression

**Files:**

- Modify local only: `python-agent/.env`

- [ ] **Step 1: Switch back to Milvus Lite**

Set:

```env
VECTOR_DB_PROVIDER=milvus
MILVUS_MODE=lite
```

- [ ] **Step 2: Run the same seed entrypoint against Milvus Lite**

```powershell
$env:PYTHONPATH='D:\yu-ai-code-mother\python-agent'
Push-Location 'python-agent'
& '.\.venv\Scripts\python.exe' 'rag\seed_vector_store.py'
Pop-Location
```

Expected: the generic entrypoint seeds Milvus Lite successfully.

- [ ] **Step 3: Run the full Python suite**

```powershell
$env:PYTHONPATH='D:\yu-ai-code-mother\python-agent'
& 'D:\yu-ai-code-mother\python-agent\.venv\Scripts\python.exe' -m pytest python-agent/tests -q
```

Expected: no new failures. Record the exact passed/skipped counts rather than reusing a historical count.

- [ ] **Step 4: Check diffs and accidental Milvus coupling**

```powershell
git diff --check
rg -n 'from rag\.milvus_client import milvus_store' python-agent --glob '*.py' --glob '!tests/**' --glob '!rag/seed_milvus.py'
git status --short
```

Expected: `git diff --check` has no output; production imports use the generic store; unrelated pre-existing files remain untouched.

If Task 8 exposes a regression, return to the task that introduced the affected file, add a failing regression test there, and repeat that task's test/implementation/commit sequence. Do not create an unreviewed catch-all commit. Do not stage the root `pyproject.toml`, root `uv.lock`, `.pnpm-store`, static assets, or unrelated existing plans.

## Final acceptance checklist

- [ ] `VECTOR_DB_PROVIDER=qdrant` connects to local Docker Qdrant.
- [ ] Five collections use 512 dimensions and Cosine distance.
- [ ] Seed data is regenerated and written successfully.
- [ ] Search results preserve `id`, `distance`, and `entity`.
- [ ] Failed multi-search requests degrade to empty result lists without switching provider.
- [ ] Qdrant restart preserves data.
- [ ] Health output identifies the active provider.
- [ ] `VECTOR_DB_PROVIDER=milvus` with `MILVUS_MODE=lite` still works.
- [ ] Focused and full Python test suites pass with current counts recorded.
- [ ] No unrelated user changes are staged or committed.
