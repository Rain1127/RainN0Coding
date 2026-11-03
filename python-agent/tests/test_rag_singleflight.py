"""Deterministic coverage for coalesced RAG reads and independent results."""
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from rag.rag_cache import RagCache
from rag.retrieval_common import PostProcessor, RetrievalContext, RetrievalResult


@pytest.fixture(autouse=True)
def offline_semantic_import(monkeypatch):
    # Unit coverage supplies its own retriever; do not load Windows ONNX DLLs.
    monkeypatch.setitem(sys.modules, 'rag.semantic_engine',
                        SimpleNamespace(semantic_retriever=None))


class MemoryRedis:
    def __init__(self):
        self.data = {}
        self.counts = {}
        self.ttls = {}
        self.lock = threading.RLock()

    def get(self, key):
        with self.lock:
            return self.data.get(key)

    def setex(self, key, ttl, value):
        with self.lock:
            self.data[key] = value.encode() if isinstance(value, str) else value
            self.ttls[key] = ttl

    def incr(self, key):
        with self.lock:
            value = int(self.data.get(key) or 0) + 1
            self.data[key] = str(value).encode()
            self.counts[key] = value
            return value

    def expire(self, key, ttl):
        with self.lock:
            self.ttls[key] = ttl


@pytest.fixture
def cache(tmp_path):
    instance = RagCache()
    instance._redis = MemoryRedis()
    instance._ok = True
    instance._dirty_file = tmp_path / '.version'
    instance._pending_file = tmp_path / '.pending'
    return instance


def payload(content='component'):
    return json.dumps([{'content': content, 'source_collection': 'component_library',
                       'source_channel': 'grep', 'score': 0.85,
                       'metadata': {'component_name': 'DataTable', 'use_count': 1}}])


def test_hybrid_instances_share_one_cold_component_load(cache, monkeypatch):
    import rag.hybrid_engine as module
    entered = threading.Event()
    joined_or_duplicate = threading.Event()
    release = threading.Event()
    calls = []
    monkeypatch.setattr(module, '_lazy_import_rag', lambda: None)
    monkeypatch.setattr(module, 'rag_cache', cache)
    monkeypatch.setattr(module.HybridEngine, 'PHASE_ROUTE',
                        {'arch': {'grep': {'component_library'}, 'semantic': False}})

    def load(_self, *_args):
        calls.append('load')
        entered.set()
        if len(calls) == 2:
            joined_or_duplicate.set()
        assert release.wait(3)
        return [RetrievalResult('component', 'component_library', 'grep', 0.85,
                                {'component_name': 'DataTable', 'use_count': 1})]

    def record(_phase, _channel, event):
        if event == 'joined':
            joined_or_duplicate.set()

    monkeypatch.setattr(cache, '_record_flight', record, raising=False)
    monkeypatch.setattr(module.HybridEngine, '_grep_component', load)
    engines = [module.HybridEngine(), module.HybridEngine()]
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(engines[0].retrieve, RetrievalContext('arch', 'DataTable'))
        try:
            assert entered.wait(2)
            second = pool.submit(engines[1].retrieve, RetrievalContext('arch', 'DataTable'))
            assert joined_or_duplicate.wait(2)
        finally:
            release.set()
        assert first.result(3) == second.result(3)
    assert calls == ['load']


def test_singleflight_shares_failure_then_allows_retry():
    from rag.singleflight import SingleFlight
    flight = SingleFlight()
    entered, joined, release = (threading.Event() for _ in range(3))
    calls = []

    def failing():
        calls.append(1)
        entered.set()
        assert release.wait(3)
        raise TimeoutError('backend timeout')

    def event(status):
        if status == 'joined':
            joined.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(flight.run, 'key', failing, event)
        try:
            assert entered.wait(2)
            second = pool.submit(flight.run, 'key', failing, event)
            assert joined.wait(2)
        finally:
            release.set()
        for future in (first, second):
            with pytest.raises(TimeoutError, match='backend timeout'):
                future.result(2)
    assert calls == [1]
    assert flight.pending_count == 0
    assert flight.run('key', lambda: 'recovered') == 'recovered'


def test_singleflight_different_keys_run_in_parallel():
    from rag.singleflight import SingleFlight
    flight = SingleFlight()
    barrier = threading.Barrier(2)

    def load(value):
        barrier.wait(timeout=2)
        return value

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(flight.run, key, lambda key=key: load(key))
                   for key in ('first', 'second')]
        assert [future.result(3) for future in futures] == ['first', 'second']
    assert flight.pending_count == 0


def test_singleflight_timeout_and_capacity_do_not_remove_owner():
    from rag.singleflight import SingleFlight
    flight = SingleFlight(wait_timeout=0.01, max_pending=1)
    entered, release = threading.Event(), threading.Event()
    events = []

    def owner():
        entered.set()
        assert release.wait(3)
        return 'owner'

    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(flight.run, 'key', owner)
        try:
            assert entered.wait(2)
            assert flight.run('key', lambda: 'timeout fallback', events.append) == 'timeout fallback'
            assert flight.run('another', lambda: 'capacity fallback', events.append) == 'capacity fallback'
            assert flight.pending_count == 1
        finally:
            release.set()
        assert first.result(2) == 'owner'
    assert events == ['joined', 'timeout', 'capacity_bypass']
    assert flight.pending_count == 0


@pytest.mark.parametrize('value', [payload(), '[]', None])
def test_cache_load_once_and_empty_or_none_semantics(cache, value):
    calls = []
    loader = lambda: (calls.append(1), value)[1]
    assert cache.get_or_load('arch', 'semantic', {'request': 'one'}, loader) == value
    assert cache.get_or_load('arch', 'semantic', {'request': 'one'}, loader) == value
    assert len(calls) == (2 if value is None else 1)
    assert sum(cache._redis.counts.values()) == 2
    if value == '[]':
        assert 30 in cache._redis.ttls.values()


def test_cache_failure_not_cached_and_next_request_retries(cache):
    def failure():
        raise RuntimeError('failed retrieval')

    with pytest.raises(RuntimeError, match='failed retrieval'):
        cache.get_or_load('arch', 'semantic', {}, failure)
    assert cache.get('arch', 'semantic', {}) is None
    assert cache.get_or_load('arch', 'semantic', {}, payload) == payload()
    assert cache._singleflight.pending_count == 0


def test_cache_without_redis_bypasses_coalescing(cache, monkeypatch):
    monkeypatch.setattr(cache, '_get_redis', lambda: None)
    events = []
    monkeypatch.setattr(cache, '_record_flight', lambda _p, _c, status: events.append(status))
    assert cache.get_or_load('arch', 'semantic', {}, payload) == payload()
    assert events == ['executed']
    assert cache._singleflight.pending_count == 0


def test_cache_fixed_version_survives_version_change_during_load(cache):
    query = {'request': 'one'}
    old_key = cache._make_key('arch', 'semantic', query)

    def load():
        cache._redis.incr('rag:v2:channel_version:semantic')
        return payload('old generation')

    assert cache.get_or_load('arch', 'semantic', query, load) == payload('old generation')
    assert old_key in cache._redis.data
    assert cache.get('arch', 'semantic', query) is None
    assert cache.get_or_load('arch', 'semantic', query, payload) == payload()


@pytest.mark.parametrize('different', [('code', 'semantic', {}),
                                      ('arch', 'grep_cl', {}),
                                      ('arch', 'semantic', {'different': True})])
def test_cache_identity_separates_phase_channel_and_query(cache, different):
    assert cache.get_or_load('arch', 'semantic', {}, payload) == payload()
    assert cache.get_or_load(*different, lambda: payload('distinct')) == payload('distinct')


def test_hybrid_channel_results_are_independent_when_reranked(cache, monkeypatch):
    import rag.hybrid_engine as module
    monkeypatch.setattr(module, '_lazy_import_rag', lambda: None)
    monkeypatch.setattr(module, 'rag_cache', cache)
    engine = module.HybridEngine()
    original = [RetrievalResult('component', 'component_library', 'grep', 0.85,
                                {'component_name': 'DataTable', 'nested': {'value': 1}})]
    first = engine._cached_channel('arch', 'grep_cl', {}, lambda: original)
    second = engine._cached_channel('arch', 'grep_cl', {}, lambda: pytest.fail('cache miss'))
    assert first[0] is not second[0]
    PostProcessor().rerank(first)
    first[0].metadata['nested']['value'] = 2
    assert second[0].score == 0.85
    assert second[0].metadata['nested']['value'] == 1
    assert original[0].score == 0.85


def test_shared_load_records_two_misses_one_execution_and_one_join(cache, monkeypatch):
    entered, joined, release = (threading.Event() for _ in range(3))
    statuses, events = [], []
    monkeypatch.setattr(cache, '_record_status', lambda p, c, status: statuses.append(status))

    def record(_phase, _channel, event):
        events.append(event)
        if event == 'joined':
            joined.set()

    monkeypatch.setattr(cache, '_record_flight', record)

    def load():
        entered.set()
        assert release.wait(3)
        return payload()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(cache.get_or_load, 'arch', 'grep_cl', {}, load)
        try:
            assert entered.wait(2)
            second = pool.submit(cache.get_or_load, 'arch', 'grep_cl', {}, load)
            assert joined.wait(2)
        finally:
            release.set()
        assert first.result(2) == second.result(2) == payload()
    assert sorted(statuses) == ['miss', 'miss']
    assert sorted(events) == ['executed', 'joined']
    assert sum(cache._redis.counts.values()) == 2
    assert cache.get_or_load('arch', 'grep_cl', {}, lambda: pytest.fail('warm miss')) == payload()
    assert statuses == ['miss', 'miss', 'hit']


def test_owner_rechecks_without_counting_a_second_cache_lookup(cache, monkeypatch):
    real_run = cache._singleflight.run
    events, statuses = [], []
    monkeypatch.setattr(cache, '_record_flight', lambda p, c, status: events.append(status))
    monkeypatch.setattr(cache, '_record_status', lambda p, c, status: statuses.append(status))

    def write_before_register(key, loader, callback):
        cache.set('arch', 'grep_cl', {}, payload())
        return real_run(key, loader, callback)

    monkeypatch.setattr(cache._singleflight, 'run', write_before_register)
    assert cache.get_or_load('arch', 'grep_cl', {}, lambda: pytest.fail('late duplicate')) == payload()
    assert statuses == ['miss']
    assert events == ['race_hit']
    assert sum(cache._redis.counts.values()) == 1


def test_version_change_does_not_join_an_old_inflight_load(cache, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    events = []
    monkeypatch.setattr(cache, '_record_flight', lambda p, c, status: events.append(status))

    def old_load():
        entered.set()
        assert release.wait(3)
        return payload('old')

    old_key = cache._make_key('arch', 'semantic', {})
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(cache.get_or_load, 'arch', 'semantic', {}, old_load)
        try:
            assert entered.wait(2)
            cache._redis.incr('rag:v2:channel_version:semantic')
            assert cache.get_or_load('arch', 'semantic', {}, lambda: payload('new')) == payload('new')
        finally:
            release.set()
        assert first.result(2) == payload('old')
    assert 'joined' not in events
    assert json.loads(cache._redis.data[old_key])['payload'] == payload('old')
    assert cache.get('arch', 'semantic', {}) == payload('new')


def test_redis_read_failure_does_not_register_or_cache(cache, monkeypatch):
    def failed_read(_key):
        raise ConnectionError('disconnected')

    monkeypatch.setattr(cache._redis, 'get', failed_read)
    assert cache.get_or_load('arch', 'semantic', {}, payload) == payload()
    assert cache._singleflight.pending_count == 0
    assert not cache._redis.data
    assert cache._ok is False


def test_disabled_singleflight_allows_overlapping_duplicate_reads(cache, monkeypatch):
    cache.singleflight_enabled = False
    barrier = threading.Barrier(2)
    events = []
    monkeypatch.setattr(cache, '_record_flight', lambda p, c, status: events.append(status))

    def load():
        barrier.wait(2)
        return payload()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(cache.get_or_load, 'arch', 'semantic', {}, load)
                   for _ in range(2)]
        assert [future.result(3) for future in futures] == [payload(), payload()]
    assert events == ['executed', 'executed']
    assert cache._singleflight.pending_count == 0
