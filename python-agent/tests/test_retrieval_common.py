import importlib
from contextlib import contextmanager
import sys
import types

import pytest


pytestmark = pytest.mark.harness


def _stub_retrieval_import_deps():
    milvus_module = types.ModuleType("rag.milvus_client")
    milvus_module.milvus_store = types.SimpleNamespace(search_multi=lambda queries: [])
    return {"rag.milvus_client": milvus_module}


@contextmanager
def _isolated_retrieval_imports(include_hybrid=False):
    stubbed_modules = _stub_retrieval_import_deps()
    module_names = [
        "rag.milvus_client",
        "rag.retrieval_engine",
        "rag.retrieval_common",
    ]
    if include_hybrid:
        module_names.append("rag.hybrid_engine")

    original_modules = {
        name: sys.modules.get(name)
        for name in module_names
    }

    try:
        for name in module_names:
            sys.modules.pop(name, None)
        sys.modules.update(stubbed_modules)
        retrieval_common = importlib.import_module("rag.retrieval_common")
        retrieval_engine = importlib.import_module("rag.retrieval_engine")
        if include_hybrid:
            hybrid_engine = importlib.import_module("rag.hybrid_engine")
            yield retrieval_common, retrieval_engine, hybrid_engine
        else:
            yield retrieval_common, retrieval_engine
    finally:
        for name in reversed(module_names):
            module = original_modules[name]
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def _load_hybrid_modules():
    with _isolated_retrieval_imports(include_hybrid=True) as modules:
        return modules


def _load_retrieval_modules():
    with _isolated_retrieval_imports() as modules:
        return modules


def _sample_result(result_cls):
    return result_cls(
        content="example snippet",
        source_collection="framework_api",
        source_channel="intent_directed",
        score=0.87,
        metadata={"api_name": "watch", "signature": "watch(source, callback)"},
        vector=[0.1, 0.2, 0.3],
    )


def test_retrieval_common_reexports_match_legacy_symbols():
    retrieval_common, retrieval_engine = _load_retrieval_modules()

    assert retrieval_engine.RetrievalResult is retrieval_common.RetrievalResult
    assert retrieval_engine.RetrievalContext is retrieval_common.RetrievalContext
    assert retrieval_engine.PostProcessor is retrieval_common.PostProcessor


def test_retrieval_engine_serialization_round_trips_shared_result():
    retrieval_common, retrieval_engine = _load_retrieval_modules()
    result = _sample_result(retrieval_common.RetrievalResult)

    payload = retrieval_engine.RetrievalEngine._serialize_results([result])
    round_tripped = retrieval_engine.RetrievalEngine._deserialize_results(payload)

    assert round_tripped is not None
    assert len(round_tripped) == 1
    assert type(round_tripped[0]) is retrieval_common.RetrievalResult
    assert round_tripped[0] == retrieval_common.RetrievalResult(
        content="example snippet",
        source_collection="framework_api",
        source_channel="intent_directed",
        score=0.87,
        metadata={"api_name": "watch", "signature": "watch(source, callback)"},
    )


def test_hybrid_engine_deserialization_uses_shared_result_model():
    retrieval_common, retrieval_engine, hybrid_engine = _load_hybrid_modules()
    result = _sample_result(retrieval_common.RetrievalResult)

    payload = retrieval_engine.RetrievalEngine._serialize_results([result])
    round_tripped = hybrid_engine.HybridEngine._deserialize_results(payload, "semantic")

    assert round_tripped is not None
    assert len(round_tripped) == 1
    assert type(round_tripped[0]) is retrieval_common.RetrievalResult
    assert round_tripped[0].source_channel == "intent_directed"
