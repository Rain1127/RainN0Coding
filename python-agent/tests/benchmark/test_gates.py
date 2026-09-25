from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import benchmark.baseline as baseline_module
from benchmark.baseline import compatibility_key, promote
from benchmark.contracts import BenchmarkReport, CaseEvaluation, MetricAssertion, RunMetadata
from benchmark.gates import evaluate_gate
from benchmark.reporting.json_report import build_report


pytestmark = pytest.mark.benchmark

DEFAULT_POLICY = Path(__file__).parents[2] / "benchmarks" / "policies" / "default.yaml"


def _rag_report(recalls: list[float]) -> BenchmarkReport:
    metadata = _report().metadata
    evaluations = [
        CaseEvaluation(
            case_id=f"rag-{index}",
            target="rag",
            category="retrieval",
            passed=True,
            assertions_passed=0,
            assertions_total=0,
            observed_metrics={"recall_at_k": recall},
        )
        for index, recall in enumerate(recalls)
    ]
    return build_report(metadata, evaluations)

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


def test_absolute_thresholds_accept_canonical_minimum_and_maximum() -> None:
    result = evaluate_gate(
        _report(rate=0.8, latency=12), None,
        {"absolute_thresholds": {"latency.mean": {"maximum": 11}, "case_pass_rate": {"minimum": 0.9}}},
    )

    assert [(failure["metric"], failure["rule"]) for failure in result["failures"]] == [
        ("case_pass_rate", "minimum"), ("latency.mean", "maximum"),
    ]


def test_default_policy_gates_labeled_rag_recall_without_breaking_pr_replay() -> None:
    policy = yaml.safe_load(DEFAULT_POLICY.read_text(encoding="utf-8"))
    pr_report = _rag_report([1.0, 1.0])
    empty_live_report = _rag_report([1.0, 1.0, 0.0, 0.0])

    assert pr_report.metrics["recall_at_k"]["mean"] == 1.0
    assert empty_live_report.metrics["recall_at_k"]["mean"] == 0.5
    assert evaluate_gate(pr_report, None, policy)["passed"] is True
    result = evaluate_gate(empty_live_report, None, policy)
    assert result["passed"] is False
    assert result["failures"] == [{
        "type": "absolute",
        "metric": "recall_at_k.mean",
        "rule": "minimum",
        "candidate": 0.5,
        "threshold": 0.75,
    }]


def test_absolute_thresholds_reject_conflicting_alias_and_canonical_value() -> None:
    with pytest.raises(ValueError, match="conflicting"):
        evaluate_gate(_report(), None, {"absolute_thresholds": {"case_pass_rate": {"min": 0.9, "minimum": 0.8}}})


def test_hard_fail_metrics_reject_duplicates() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        evaluate_gate(_report(), None, {"hard_fail_metrics": ["route_accuracy", "route_accuracy"]})


def test_gate_output_is_canonical_across_policy_and_result_insertion_order() -> None:
    failed_a = CaseEvaluation(case_id="z", target="supervisor", category="routing", passed=False, assertions_passed=0, assertions_total=1, assertions=[MetricAssertion(metric="z_metric", passed=False, rule="equals", path="z")])
    failed_b = CaseEvaluation(case_id="a", target="supervisor", category="routing", passed=False, assertions_passed=0, assertions_total=1, assertions=[MetricAssertion(metric="a_metric", passed=False, rule="equals", path="a")])
    candidate_a = _report(rate=0.8, latency=12).model_copy(update={"results": [failed_a, failed_b]})
    candidate_b = _report(rate=0.8, latency=12).model_copy(update={"results": [failed_b, failed_a]})
    policy_a = {"hard_fail_metrics": ["z_metric", "a_metric"], "absolute_thresholds": {"latency.mean": {"maximum": 11}, "case_pass_rate": {"minimum": 0.9}}, "regression_thresholds": {"latency.mean": {"max_increase_ratio": 0.1}, "case_pass_rate": {"max_drop": 0.1}}}
    policy_b = {"regression_thresholds": {"case_pass_rate": {"max_drop": 0.1}, "latency.mean": {"max_increase_ratio": 0.1}}, "absolute_thresholds": {"case_pass_rate": {"minimum": 0.9}, "latency.mean": {"maximum": 11}}, "hard_fail_metrics": ["a_metric", "z_metric"]}

    assert evaluate_gate(candidate_a, _report(rate=1.0, latency=10), policy_a) == evaluate_gate(candidate_b, _report(rate=1.0, latency=10), policy_b)


@pytest.mark.parametrize("baseline_latency", [0, -1])
def test_increase_ratio_rejects_nonpositive_baseline(baseline_latency: float) -> None:
    with pytest.raises(ValueError, match="non-positive baseline"):
        evaluate_gate(_report(latency=1), _report(latency=baseline_latency), {"regression_thresholds": {"latency.mean": {"max_increase_ratio": 0.1}}})


def test_promote_publish_failure_leaves_no_final_or_temp_file(monkeypatch, tmp_path: Path) -> None:
    def fail_publish(temporary: Path, destination: Path) -> None:
        raise OSError("publish failed")

    monkeypatch.setattr(baseline_module, "_publish", fail_publish, raising=False)
    with pytest.raises(OSError, match="publish failed"):
        promote(_report(), tmp_path)

    assert not list(tmp_path.rglob("baseline.json"))
    assert not list(tmp_path.rglob("*.tmp"))
