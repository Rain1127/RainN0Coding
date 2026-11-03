import json

from rag.rag_cache import RagCache
from rag.code_grep import CodeGrep


class FakeRedis:
    def __init__(self):
        self.data = {}
        self.ttls = {}
        self.counts = {}

    def get(self, key):
        return self.data.get(key)

    def setex(self, key, ttl, value):
        self.data[key] = value.encode() if isinstance(value, str) else value
        self.ttls[key] = ttl

    def incr(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        self.data[key] = str(self.counts[key]).encode()
        return self.counts[key]

    def expire(self, *_args):
        key, ttl = _args
        self.ttls[key] = ttl


def _cache():
    cache = RagCache()
    cache._redis = FakeRedis()
    cache._ok = True
    return cache


def _query(**overrides):
    query = {
        "keywords": ["Redis", "Vue"], "code_gen_type": "vue_project",
        "framework": "Vue 3", "user_request": "做登录页",
        "file_info": {"path": "a.vue", "description": "页面"},
        "architecture": {"tech_stack": {"framework": "Vue 3", "lang": "TS"}},
        "embedding_model": "bge-small", "algorithm_version": "v2",
    }
    query.update(overrides)
    return query


def test_key_is_stable_for_dict_and_keyword_order_and_changes_for_dependencies():
    cache = _cache()
    base = _query()
    reordered = _query(
        keywords=["Vue", "Redis"],
        file_info={"description": "页面", "path": "a.vue"},
        architecture={"tech_stack": {"lang": "TS", "framework": "Vue 3"}},
    )
    key = cache._make_key("code", "semantic", base)
    assert key == cache._make_key("code", "semantic", reordered)
    assert key.startswith("rag:v2:")
    assert key != cache._make_key("code", "semantic", _query(architecture={"other": 1}))
    assert key != cache._make_key("code", "semantic", _query(embedding_model="new-model"))


def test_read_records_heat_and_negative_result_has_short_ttl():
    cache = _cache()
    query = _query()
    assert cache.get("code", "semantic", query) is None
    assert sum(cache._redis.counts.values()) >= 1
    cache.set("code", "semantic", query, "[]", negative=True)
    assert cache.get("code", "semantic", query) == "[]"
    key = cache._make_key("code", "semantic", query)
    assert cache._redis.ttls[key] < 1800


def test_repeated_hit_promotes_existing_key_to_hot_ttl(monkeypatch):
    from rag import rag_cache as cache_module
    cache = _cache()
    query = _query()
    monkeypatch.setattr(cache_module.config, "RAG_HOT_QUERY_THRESHOLD", 2)
    cache.set("code", "semantic", query,
              '[{"content":"example","source_collection":"design_pattern",'
              '"source_channel":"semantic","score":0.9,"metadata":{}}]')
    key = cache._make_key("code", "semantic", query)
    cache.get("code", "semantic", query)
    cache.get("code", "semantic", query)
    assert cache._redis.ttls[key] == cache_module.config.RAG_CACHE_TTL_HOT


def test_code_store_version_change_invalidates_shared_channel():
    cache = _cache()
    query = _query()
    before = cache._make_key("code", "grep_cs", query)
    cache.bump_code_store_versions()
    after = cache._make_key("code", "grep_cs", query)
    assert before != after


def test_invalid_cache_envelope_falls_back_to_source():
    cache = _cache()
    query = _query()
    cache._redis.data[cache._make_key("code", "semantic", query)] = b'{"schema_version":1,"payload":"stale"}'
    assert cache.get("code", "semantic", query) is None
    assert cache._ok is True


def test_malformed_payload_falls_back_without_disabling_redis():
    cache = _cache()
    query = _query()
    cache._redis.data[cache._make_key("code", "semantic", query)] = b"not-json"
    assert cache.get("code", "semantic", query) is None
    assert cache._ok is True


def test_valid_envelope_with_bad_results_falls_back_to_source():
    cache = _cache()
    query = _query()
    key = cache._make_key("code", "semantic", query)
    cache._redis.data[key] = b'{"schema_version":2,"payload":"broken"}'
    assert cache.get("code", "semantic", query) is None


def test_incomplete_result_record_falls_back_to_source():
    cache = _cache()
    query = _query()
    key = cache._make_key("code", "semantic", query)
    cache._redis.data[key] = b'{"schema_version":2,"payload":"[{}]"}'
    assert cache.get("code", "semantic", query) is None


def test_code_store_write_and_delete_invalidate_cache(monkeypatch, tmp_path):
    from rag.rag_cache import rag_cache
    calls = []
    monkeypatch.setattr(rag_cache, "code_store_changed", lambda: calls.append("changed"))
    store = CodeGrep(str(tmp_path))
    store.write_code("app", "main.py", "print(1)")
    assert calls == ["changed"]
    assert store.delete_code("app", "main.py")
    assert calls == ["changed", "changed"]


def test_cache_version_files_do_not_count_as_code(tmp_path):
    store = CodeGrep(str(tmp_path))
    (tmp_path / ".rag-cache-version").write_text("v1")
    (tmp_path / ".rag-cache-pending").write_text("pending")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("print(1)")
    assert store.get_file_count() == 1


def test_failed_version_bump_bypasses_until_reconnect(tmp_path):
    cache = _cache()
    cache._dirty_file = tmp_path / ".rag-cache-version"
    cache._pending_file = tmp_path / ".rag-cache-pending"

    class FailingRedis(FakeRedis):
        def incr(self, key):
            if "channel_version" in key:
                raise ConnectionError("redis down")
            return super().incr(key)

    cache._redis = FailingRedis()
    cache.code_store_changed()
    assert cache._pending_file.exists()
    assert cache.get("code", "grep_cs", _query()) is None

    cache._redis = FakeRedis()
    cache._ok = True
    cache.get("code", "grep_cs", _query())
    assert not cache._pending_file.exists()
    assert cache._redis.counts["rag:v2:channel_version:grep_cs"] == 1


def test_redis_connection_retries_after_cooldown(monkeypatch):
    import redis
    import rag.rag_cache as cache_module
    cache = RagCache()
    cache._ok = False
    cache._last_failure = 10.0
    monkeypatch.setattr(cache_module.time, "monotonic", lambda: 10.0)
    assert cache._get_redis() is None

    class Connected(FakeRedis):
        def ping(self):
            return True

    monkeypatch.setattr(redis, "Redis", lambda **_kwargs: Connected())
    monkeypatch.setattr(cache_module.time, "monotonic", lambda: 16.0)
    assert isinstance(cache._get_redis(), Connected)


def test_hybrid_negative_cache_only_for_successful_empty_search(monkeypatch):
    import rag.hybrid_engine as hybrid_module
    from rag.retrieval_common import RetrievalContext
    monkeypatch.setattr(hybrid_module, "_lazy_import_rag", lambda: None)
    monkeypatch.setattr(hybrid_module.HybridEngine, "PHASE_ROUTE",
                        {"code": {"grep": set(), "semantic": True}})
    calls = []

    class Cache:
        def get(self, *_args):
            return None
        def set(self, *args, **kwargs):
            calls.append(kwargs)

    class Success:
        def retrieve(self, *_args):
            return []

    class Failure:
        def retrieve(self, *_args):
            raise TimeoutError("vector store unavailable")

    monkeypatch.setattr(hybrid_module, "rag_cache", Cache())
    engine = hybrid_module.HybridEngine()
    ctx = RetrievalContext(phase="code", user_request="test")
    monkeypatch.setattr(hybrid_module, "_semantic_retriever", Success())
    assert engine.retrieve(ctx) == ""
    assert calls == [{"negative": True}]

    calls.clear()
    monkeypatch.setattr(hybrid_module, "_semantic_retriever", Failure())
    assert engine.retrieve(ctx) == ""
    assert calls == []
