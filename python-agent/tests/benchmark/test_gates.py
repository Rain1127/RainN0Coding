from __future__ import annotations

from pathlib import Path

import pytest

from benchmark.baseline import compatibility_key, promote
from benchmark.contracts import BenchmarkReport, RunMetadata
from benchmark.gates import evaluate_gate
from benchmark.reporting.json_report import build_report


def _report(*, run_id: str = "run", git_sha: str = "sha", rate: float = 1.0, latency: float = 10.0) -> BenchmarkReport:
    return build_report(
        RunMetadata(
            run_id=run_id, suite="pr", git_sha=git_sha, dataset_versions=["v1"],
            dataset_fingerprint="dataset", prompt_fingerprint="prompt",
            model_aliases={"default": "model"}, offline=True, started_at="2026-01-01T00:00:00+00:00",
        ),
        [],
    ).model_copy(update={"summary": {"case_pass_rate": rate}, "metrics": {"latency": {"mean": latency}}})


def test_compatibility_key_excludes_git_sha_and_run_id() -> None:
    assert compatibility_key(_report(run_id="first", git_sha="old")) == compatibility_key(_report(run_id="second", git_sha="new"))


def test_gate_reports_absolute_and_regression_failures() -> None:
    result = evaluate_gate(
        _report(rate=0.8, latency=12), _report(rate=1.0, latency=10),
        {"absolute": {"case_pass_rate": {"min": 0.9}}, "regression": {"latency.mean": {"max_increase_ratio": 0.1}}},
    )

    assert result["passed"] is False
    assert {failure["type"] for failure in result["failures"]} == {"absolute", "regression"}


def test_promote_refuses_overwrite_for_same_compatibility_key(tmp_path: Path) -> None:
    report = _report()
    promote(report, tmp_path)

    with pytest.raises(FileExistsError):
        promote(report, tmp_path)
