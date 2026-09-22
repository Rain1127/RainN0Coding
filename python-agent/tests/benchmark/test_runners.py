from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmark.contracts import BenchmarkCase, LoadedCase
from benchmark.runners.base import RunContext
from benchmark.runners.deterministic import DeterministicRunner
from benchmark.runners.replay import ReplayRunner


def _loaded_case(*, target: str = "supervisor", record_path: Path | None = None) -> LoadedCase:
    case = BenchmarkCase.model_validate(
        {
            "id": "runner-001",
            "dataset_version": "2026.09.1",
            "target": target,
            "category": "routing",
            "execution": {"mode": "deterministic" if target == "supervisor" else "replay"},
            "input": {"phase": "review_done", "review": {"passed": True}},
            "provenance": {"source": "synthetic", "reviewed": True, "sanitized": True},
        }
    )
    return LoadedCase(case=case, source_path=Path("cases.yaml"), record_path=record_path)


def test_deterministic_runner_uses_real_supervisor() -> None:
    record = DeterministicRunner().run(
        _loaded_case(), RunContext(run_id="run-1", offline=True)
    )[0]

    assert record.case_id == "runner-001"
    assert record.output == {"next_node": "builder_agent"}
    assert record.infrastructure_error is None
    assert record.duration_ms >= 0
    assert record.started_at.endswith("+00:00")


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


def test_offline_context_rejects_live_mode() -> None:
    with pytest.raises(ValueError, match="live mode is not allowed in an offline suite"):
        RunContext(run_id="run-1", offline=True).assert_mode_allowed("live")


def test_replay_runner_requires_record_path() -> None:
    with pytest.raises(ValueError, match="runner-001: replay record is required"):
        ReplayRunner().run(_loaded_case(target="intent"), RunContext("run-1", True))
