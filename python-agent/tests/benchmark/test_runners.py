from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmark.contracts import BenchmarkCase, LoadedCase, RawRunRecord
from benchmark.runners.base import RunContext
from benchmark.runners.deterministic import DeterministicRunner
from benchmark.runners.replay import ReplayRunner


def _loaded_case(
    *, target: str = "supervisor", record_path: Path | None = None, mode: str | None = None
) -> LoadedCase:
    case = BenchmarkCase.model_validate(
        {
            "id": "runner-001",
            "dataset_version": "2026.09.1",
            "target": target,
            "category": "routing",
            "execution": {"mode": mode or ("deterministic" if target == "supervisor" else "replay")},
            "input": {"phase": "review_done", "review": {"passed": True}},
            "provenance": {"source": "synthetic", "reviewed": True, "sanitized": True},
        }
    )
    return LoadedCase(case=case, source_path=Path("cases.yaml"), record_path=record_path)


def test_deterministic_runner_uses_real_supervisor() -> None:
    loaded = _loaded_case()
    original = loaded.case.input.copy()
    record = DeterministicRunner().run(
        loaded, RunContext(run_id="run-1", offline=True)
    )[0]

    assert record.case_id == "runner-001"
    assert record.output == {"next_node": "builder_agent"}
    assert record.infrastructure_error is None
    assert record.duration_ms >= 0
    assert record.started_at.endswith("+00:00")
    assert loaded.case.input == original


def test_deterministic_runner_rejects_mismatched_execution_mode() -> None:
    with pytest.raises(ValueError, match="runner-001: deterministic runner requires deterministic mode"):
        DeterministicRunner().run(
            _loaded_case(mode="replay"), RunContext(run_id="run-1", offline=True)
        )


def test_replay_runner_reads_output_and_observed_latency(tmp_path: Path) -> None:
    record_path = tmp_path / "record.json"
    record_path.write_text(
        json.dumps({"output": {"phase": "intent_done"}, "metrics": {"latency_ms": 10}}),
        encoding="utf-8",
    )

    record = ReplayRunner().run(
        _loaded_case(target="intent", record_path=record_path),
        RunContext(run_id="run-1", offline=True),
    )[0]

    assert record.output == {"phase": "intent_done"}
    assert record.observed_metrics == {"latency_ms": 10.0}


def test_replay_runner_defaults_omitted_metrics_to_empty_dict(tmp_path: Path) -> None:
    record_path = tmp_path / "record.json"
    record_path.write_text(json.dumps({"output": {"phase": "intent_done"}}), encoding="utf-8")

    record = ReplayRunner().run(
        _loaded_case(target="intent", record_path=record_path),
        RunContext(run_id="run-1", offline=True),
    )[0]

    assert record.observed_metrics == {}


def test_replay_runner_rejects_mismatched_execution_mode(tmp_path: Path) -> None:
    record_path = tmp_path / "record.json"
    record_path.write_text(json.dumps({"phase": "intent_done"}), encoding="utf-8")

    with pytest.raises(ValueError, match="runner-001: replay runner requires replay mode"):
        ReplayRunner().run(
            _loaded_case(target="intent", record_path=record_path, mode="deterministic"),
            RunContext(run_id="run-1", offline=True),
        )


def test_offline_context_rejects_live_mode() -> None:
    with pytest.raises(ValueError, match="live mode is not allowed in an offline suite"):
        RunContext(run_id="run-1", offline=True).assert_mode_allowed("live")


def test_replay_runner_requires_record_path() -> None:
    with pytest.raises(ValueError, match="runner-001: replay record is required"):
        ReplayRunner().run(_loaded_case(target="intent"), RunContext("run-1", True))


@pytest.mark.parametrize("value", [True, "10", float("nan"), float("inf"), float("-inf")])
def test_raw_run_record_rejects_invalid_metric_values(value: object) -> None:
    with pytest.raises(ValueError):
        RawRunRecord(
            case_id="runner-001",
            observed_metrics={"latency_ms": value},
            started_at="2026-09-22T00:00:00+00:00",
            duration_ms=1,
        )


def test_raw_run_record_accepts_none_and_normalizes_finite_metrics() -> None:
    record = RawRunRecord(
        case_id="runner-001",
        observed_metrics={"latency_ms": 10, "optional": None},
        started_at="2026-09-22T00:00:00+00:00",
        duration_ms=1,
    )

    assert record.observed_metrics == {"latency_ms": 10.0, "optional": None}


def test_raw_run_record_rejects_overflowing_metric() -> None:
    with pytest.raises(ValueError):
        RawRunRecord(
            case_id="runner-001",
            observed_metrics={"latency_ms": 10**1000},
            started_at="2026-09-22T00:00:00+00:00",
            duration_ms=1,
        )


@pytest.mark.parametrize(
    "field,value",
    [("case_id", ""), ("attempt_index", -1), ("duration_ms", -1), ("duration_ms", float("nan"))],
)
def test_raw_run_record_rejects_invalid_integrity_fields(field: str, value: object) -> None:
    values = {
        "case_id": "runner-001",
        "attempt_index": 0,
        "duration_ms": 1,
        "started_at": "2026-09-22T00:00:00+00:00",
    }
    values[field] = value
    with pytest.raises(ValueError):
        RawRunRecord.model_validate(values)


@pytest.mark.parametrize("value", [True, "10", float("nan"), float("inf"), float("-inf")])
def test_replay_runner_rejects_invalid_metrics(tmp_path: Path, value: object) -> None:
    record_path = tmp_path / "record.json"
    record_path.write_text(
        json.dumps({"output": {"phase": "intent_done"}, "metrics": {"latency_ms": value}}, allow_nan=True),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="runner-001: invalid replay metric"):
        ReplayRunner().run(
            _loaded_case(target="intent", record_path=record_path),
            RunContext(run_id="run-1", offline=True),
        )


def test_replay_runner_rejects_overflowing_metric(tmp_path: Path) -> None:
    record_path = tmp_path / "record.json"
    record_path.write_text(
        json.dumps({"output": {}, "metrics": {"latency_ms": 10**1000}}), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="runner-001: invalid replay metric"):
        ReplayRunner().run(
            _loaded_case(target="intent", record_path=record_path),
            RunContext(run_id="run-1", offline=True),
        )
