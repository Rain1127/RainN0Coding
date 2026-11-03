"""Regression coverage for concurrent RAG reads of a shared SQLite store."""

import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from rag.retrieval_common import PostProcessor, RetrievalResult
from rag.sqlite_store import SqliteStore


class GuardedConnection:
    """Expose overlapping calls against one connection deterministically."""

    def __init__(self, connection):
        self.connection = connection
        self.first_execute = threading.Event()
        self._lock = threading.Lock()
        self._busy = False

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def execute(self, *args, **kwargs):
        with self._lock:
            if self._busy:
                raise RuntimeError("shared SQLite connection used concurrently")
            self._busy = True
            self.first_execute.set()
        try:
            time.sleep(0.04)
            return self.connection.execute(*args, **kwargs)
        finally:
            with self._lock:
                self._busy = False


def test_component_search_serializes_shared_connection(tmp_path):
    store = SqliteStore(str(tmp_path / "exact_search.db"))
    store.init_tables()
    store.insert_component({"component_name": "DataTable", "code_snippet": "table",
                            "framework": "Vue 3", "use_count": 1})
    store.rebuild_indexes()
    guarded = GuardedConnection(store._conn)
    store._conn = guarded
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(store.search_component, ["DataTable"])
            assert guarded.first_execute.wait(timeout=2)
            second = pool.submit(store.search_component, ["DataTable"])
            for future in (first, second):
                rows = future.result(timeout=3)
                assert len(rows) == 1
                assert rows[0]["use_count"] == 1
    finally:
        store.close()


def test_rerank_tolerates_nullable_component_use_count():
    result = RetrievalResult(content="component", source_collection="component_library",
                             source_channel="grep", score=0.9,
                             metadata={"component_name": "DataTable", "use_count": None})
    ranked = PostProcessor().rerank([result])
    assert len(ranked) == 1
    assert math.isfinite(ranked[0].score)


def test_zero_use_count_keeps_lower_rank_than_missing_count():
    zero = RetrievalResult(content="unused", source_collection="component_library",
                           source_channel="grep", score=0.9, metadata={"use_count": 0})
    missing = RetrievalResult(content="unknown", source_collection="component_library",
                              source_channel="grep", score=0.9, metadata={"use_count": None})
    processor = PostProcessor()
    assert processor._success_score(zero) < processor._success_score(missing)
