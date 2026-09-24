from __future__ import annotations

import json
import sys
import types
from contextlib import contextmanager
from pathlib import Path

import pytest

from benchmark.contracts import BenchmarkCase, LoadedCase
from benchmark.evaluators.metrics import retrieval_metrics
from benchmark.runners.base import RunContext
from benchmark.runners.rag import RagRunner, retrieve_with_engine


def _loaded_rag_case(
    *,
    case_id: str = "rag-replay",
    record_path: Path | None = None,
    repeats: int = 1,
    input_data: dict | None = None,
    relevant: list[str] | None = None,
) -> LoadedCase:
    case = BenchmarkCase.model_validate(
        {
            "id": case_id,
            "dataset_version": "2026.09.1",
            "target": "rag",
            "category": "retrieval",
            "execution": {"mode": "rag", "record": "fixture.json", "repeats": repeats},
            "input": input_data or {"k": 3},
            "expectations": {"relevant_document_ids": relevant or ["framework_api:watch"]},
            "provenance": {"source": "curated", "reviewed": True, "sanitized": True},
        }
    )
    return LoadedCase(case=case, source_path=Path("rag.yaml"), record_path=record_path)


def _result(api_name: str, *, content: str | None = None) -> dict:
    return {
        "content": content or f"API {api_name}",
        "source_collection": "framework_api",
        "source_channel": "intent_directed",
        "score": 0.9,
        "metadata": {"api_name": api_name},
    }


def test_retrieval_metrics_are_deterministic_and_use_standard_ir_definitions() -> None:
    metrics = retrieval_metrics(
        ["doc-b", "doc-x", "doc-a"], ["doc-a", "doc-b"], k=3
    )

    assert metrics["precision_at_k"] == pytest.approx(2 / 3)
    assert metrics["recall_at_k"] == 1.0
    assert metrics["mrr"] == 1.0
    assert metrics["ndcg_at_k"] == pytest.approx(0.919720789, rel=1e-8)


def test_retrieval_metrics_reject_empty_relevant_labels() -> None:
    with pytest.raises(ValueError, match="relevant document labels"):
        retrieval_metrics(["doc-a"], [], k=1)


def test_retrieval_metrics_validate_k_and_nonblank_ids() -> None:
    with pytest.raises(ValueError, match="k must be at least 1"):
        retrieval_metrics(["doc-a"], ["doc-a"], k=0)
    with pytest.raises(ValueError, match="retrieved document ids"):
        retrieval_metrics([" "], ["doc-a"], k=1)
    with pytest.raises(ValueError, match="relevant document labels"):
        retrieval_metrics(["doc-a"], [""], k=1)


def test_retrieval_metrics_do_not_inflate_duplicate_relevant_results() -> None:
    metrics = retrieval_metrics(["doc-a", "doc-a", "doc-a"], ["doc-a"], k=3)

    assert metrics["precision_at_k"] == pytest.approx(1 / 3)
    assert metrics["recall_at_k"] == 1.0
    assert metrics["recall_at_k"] <= 1.0


def test_retrieval_precision_divides_by_k_when_fewer_results_are_returned() -> None:
    metrics = retrieval_metrics(["doc-a"], ["doc-a", "doc-b"], k=3)

    assert metrics["precision_at_k"] == pytest.approx(1 / 3)
    assert metrics["recall_at_k"] == pytest.approx(1 / 2)


def test_rag_runner_replays_results_and_emits_labeled_metrics_for_each_attempt(tmp_path: Path) -> None:
    record_path = tmp_path / "search-results.json"
    record_path.write_text(json.dumps({"rag-replay": [_result("watch"), _result("computed")]}), encoding="utf-8")

    records = RagRunner().run(
        _loaded_rag_case(record_path=record_path, repeats=2), RunContext("run-1", offline=True)
    )

    assert [record.attempt_index for record in records] == [0, 1]
    assert records[0].output == {
        "document_ids": ["framework_api:watch", "framework_api:computed"],
        "retrieved_count": 2,
    }
    assert records[0].observed_metrics == {
        "precision_at_k": pytest.approx(1 / 3),
        "recall_at_k": 1.0,
        "mrr": 1.0,
        "ndcg_at_k": 1.0,
    }


def test_rag_runner_uses_explicit_document_id_before_stable_metadata_fallback(tmp_path: Path) -> None:
    record_path = tmp_path / "search-results.json"
    result = _result("watch")
    result["metadata"] = {"document_id": "reviewed-watch-v1", "api_name": "watch"}
    record_path.write_text(json.dumps({"rag-replay": [result]}), encoding="utf-8")

    record = RagRunner().run(_loaded_rag_case(record_path=record_path, relevant=["reviewed-watch-v1"]), RunContext("run-1", True))[0]

    assert record.output["document_ids"] == ["reviewed-watch-v1"]


def test_rag_runner_rejects_missing_relevant_labels(tmp_path: Path) -> None:
    record_path = tmp_path / "search-results.json"
    record_path.write_text(json.dumps({"rag-replay": [_result("watch")]}), encoding="utf-8")
    loaded = _loaded_rag_case(record_path=record_path)
    loaded = loaded.model_copy(update={"case": loaded.case.model_copy(update={"expectations": loaded.case.expectations.model_copy(update={"relevant_document_ids": []})})})

    with pytest.raises(ValueError, match="relevant document labels"):
        RagRunner().run(loaded, RunContext("run-1", True))


def test_rag_runner_reports_a_case_aware_missing_replay_record(tmp_path: Path) -> None:
    record_path = tmp_path / "search-results.json"
    record_path.write_text(json.dumps({"another-case": [_result("watch")]}), encoding="utf-8")

    with pytest.raises(ValueError, match="rag-replay: replay record is missing results"):
        RagRunner().run(_loaded_rag_case(record_path=record_path), RunContext("run-1", True))


def test_rag_runner_rejects_ragas_in_offline_suites(tmp_path: Path) -> None:
    record_path = tmp_path / "search-results.json"
    record_path.write_text(json.dumps({"rag-replay": [_result("watch")]}), encoding="utf-8")

    with pytest.raises(ValueError, match="rag-replay: RAGAS is not allowed in an offline suite"):
        RagRunner().run(
            _loaded_rag_case(record_path=record_path, input_data={"ragas": True}),
            RunContext("run-1", True),
        )


def test_rag_runner_uses_an_injected_retriever_without_importing_live_services() -> None:
    received: list[dict] = []

    def retrieve(input_data: dict) -> list[dict]:
        received.append(input_data)
        return [_result("watch")]

    records = RagRunner(retrieve=retrieve).run(
        _loaded_rag_case(record_path=None, input_data={"phase": "code", "user_request": "watch state"}),
        RunContext("run-1", offline=False),
    )

    assert received == [{"phase": "code", "user_request": "watch state"}]
    assert records[0].output["document_ids"] == ["framework_api:watch"]


def test_rag_runner_replay_is_offline_and_does_not_import_live_retrieval(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    record_path = tmp_path / "search-results.json"
    record_path.write_text(json.dumps({"rag-replay": [_result("watch")]}), encoding="utf-8")

    def blocked_import(name: str, *args: object, **kwargs: object) -> object:
        if name.startswith("rag.retrieval_"):
            raise AssertionError("offline replay imported live retrieval")
        return original_import(name, *args, **kwargs)

    original_import = __import__
    monkeypatch.setattr("builtins.__import__", blocked_import)
    record = RagRunner().run(_loaded_rag_case(record_path=record_path), RunContext("run-1", True))[0]

    assert record.output["retrieved_count"] == 1


def test_rag_runner_merges_only_finite_numeric_ragas_metrics(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    record_path = tmp_path / "search-results.json"
    record_path.write_text(json.dumps({"rag-replay": [_result("watch")]}), encoding="utf-8")
    ragas_module = types.ModuleType("rag.ragas_evaluator")
    ragas_module.evaluate_offline = lambda rows: [{"faithfulness": 0.8, "drop_bool": True, "drop_none": None}]
    monkeypatch.setitem(sys.modules, "rag.ragas_evaluator", ragas_module)

    record = RagRunner().run(
        _loaded_rag_case(
            record_path=record_path,
            input_data={
                "ragas": {"question": "What API?", "answer": "watch", "ground_truth": "Use watch."}
            },
        ),
        RunContext("run-1", offline=False),
    )[0]

    assert record.observed_metrics["faithfulness"] == 0.8
    assert "drop_bool" not in record.observed_metrics
    assert "drop_none" not in record.observed_metrics


def test_rag_runner_binds_ragas_request_context_for_online_evaluation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    record_path = tmp_path / "search-results.json"
    record_path.write_text(json.dumps({"rag-replay": [_result("watch")]}), encoding="utf-8")
    events: list[dict] = []

    @contextmanager
    def bind_request_context(**kwargs: str):
        events.append(kwargs)
        yield

    context_module = types.ModuleType("request_context")
    context_module.bind_request_context = bind_request_context
    ragas_module = types.ModuleType("rag.ragas_evaluator")
    ragas_module.evaluate_offline = lambda rows: []
    monkeypatch.setitem(sys.modules, "request_context", context_module)
    monkeypatch.setitem(sys.modules, "rag.ragas_evaluator", ragas_module)

    RagRunner().run(
        _loaded_rag_case(
            record_path=record_path,
            input_data={
                "ragas": {"question": "What API?", "answer": "watch", "ground_truth": "Use watch."},
                "request_context": {"request_id": "req-1", "trace_id": "trace-1", "user_id": "user-1", "app_id": "app-1"},
            },
        ),
        RunContext("run-1", offline=False),
    )

    assert events == [{"request_id": "req-1", "trace_id": "trace-1", "user_id": "user-1", "app_id": "app-1"}]


def test_real_retrieval_adapter_builds_context_and_serializes_ranked_results(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[object] = []

    class Context:
        def __init__(self, **kwargs: object):
            self.__dict__.update(kwargs)

    common_module = types.ModuleType("rag.retrieval_common")
    common_module.RetrievalContext = Context
    result = types.SimpleNamespace(
        content="API watch", source_collection="framework_api", source_channel="intent_directed",
        score=0.9, metadata={"api_name": "watch"},
    )
    engine_module = types.ModuleType("rag.retrieval_engine")
    engine_module.retrieval_engine = types.SimpleNamespace(
        retrieve_results=lambda context: captured.append(context) or [result]
    )
    monkeypatch.setitem(sys.modules, "rag.retrieval_common", common_module)
    monkeypatch.setitem(sys.modules, "rag.retrieval_engine", engine_module)

    results = retrieve_with_engine({"phase": "review", "user_request": "when to watch", "retry_count": 2})

    assert captured[0].phase == "review"
    assert captured[0].retry_count == 2
    assert results == [_result("watch")]


def test_pr_suite_runs_replay_rag_cases_without_importing_live_retrieval(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from benchmark.cli import main

    original_import = __import__

    def blocked_import(name: str, *args: object, **kwargs: object) -> object:
        if name in {"rag.retrieval_engine", "rag.embedding_service", "rag.vector_store"}:
            raise AssertionError(f"PR suite imported live dependency: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", blocked_import)
    suite = Path(__file__).resolve().parents[2] / "benchmarks" / "suites" / "pr.yaml"

    assert main(["run", "--suite", str(suite), "--output", str(tmp_path / "report.json"), "--record-dir", str(tmp_path / "records")]) == 0
