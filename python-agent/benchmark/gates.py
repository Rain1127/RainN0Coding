from __future__ import annotations

import math
from typing import Any

from benchmark.contracts import BenchmarkReport


def _numeric(report: BenchmarkReport, metric: str) -> float:
    if "." not in metric and metric in report.summary:
        value: object = report.summary[metric]
    else:
        value = report.metrics
        for component in metric.split("."):
            if not isinstance(value, dict) or component not in value:
                raise ValueError(f"metric is missing: {metric}")
            value = value[component]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"metric is not finite numeric: {metric}")
    return float(value)


def _section(policy: dict[str, Any], primary: str, alias: str) -> dict[str, Any]:
    value = policy.get(primary, policy.get(alias, {}))
    if not isinstance(value, dict):
        raise ValueError(f"policy {primary} must be an object")
    return value


def _thresholds(value: object, section: str, metric: str) -> dict[str, float]:
    if not isinstance(value, dict):
        raise ValueError(f"policy {section}.{metric} must be an object")
    output: dict[str, float] = {}
    for key, raw in value.items():
        if key not in {"min", "max", "max_drop", "max_increase_ratio"}:
            raise ValueError(f"policy {section}.{metric} has unknown threshold: {key}")
        if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(float(raw)):
            raise ValueError(f"policy {section}.{metric}.{key} must be finite numeric")
        output[key] = float(raw)
    return output


def evaluate_gate(candidate: BenchmarkReport, baseline: BenchmarkReport | None, policy: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(policy, dict):
        raise ValueError("policy must be an object")
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    comparisons: list[dict[str, Any]] = []
    hard_metrics = policy.get("hard_fail_metrics", [])
    if not isinstance(hard_metrics, list) or not all(isinstance(metric, str) and metric for metric in hard_metrics):
        raise ValueError("policy hard_fail_metrics must be an array of metric names")
    for metric in hard_metrics:
        failed = [
            {"case_id": result.case_id, "attempt_index": result.attempt_index}
            for result in candidate.results
            for assertion in result.assertions
            if assertion.metric == metric and not assertion.passed
        ]
        if failed:
            failures.append({"type": "hard", "metric": metric, "failed_assertions": failed})
    absolute = _section(policy, "absolute_thresholds", "absolute")
    for metric, configured in absolute.items():
        threshold = _thresholds(configured, "absolute_thresholds", str(metric))
        if not isinstance(metric, str) or not metric:
            raise ValueError("policy absolute_thresholds metric name must be non-empty")
        value = _numeric(candidate, metric)
        for direction in ("min", "max"):
            if direction in threshold and ((direction == "min" and value < threshold[direction]) or (direction == "max" and value > threshold[direction])):
                failures.append({"type": "absolute", "metric": metric, "rule": direction, "candidate": value, "threshold": threshold[direction]})
    regression = _section(policy, "regression_thresholds", "regression")
    if baseline is None:
        warnings.append({"type": "no_baseline"})
    else:
        for metric, configured in regression.items():
            if not isinstance(metric, str) or not metric:
                raise ValueError("policy regression_thresholds metric name must be non-empty")
            threshold = _thresholds(configured, "regression_thresholds", metric)
            candidate_value, baseline_value = _numeric(candidate, metric), _numeric(baseline, metric)
            comparison: dict[str, Any] = {"metric": metric, "candidate": candidate_value, "baseline": baseline_value, "delta": candidate_value - baseline_value}
            if "max_drop" in threshold:
                drop = baseline_value - candidate_value
                comparison["drop"] = drop
                if drop > threshold["max_drop"]:
                    failures.append({"type": "regression", "metric": metric, "rule": "max_drop", "candidate": candidate_value, "baseline": baseline_value, "threshold": threshold["max_drop"]})
            if "max_increase_ratio" in threshold:
                if baseline_value == 0:
                    raise ValueError(f"cannot calculate increase ratio with zero baseline: {metric}")
                increase_ratio = (candidate_value - baseline_value) / baseline_value
                comparison["increase_ratio"] = increase_ratio
                if increase_ratio > threshold["max_increase_ratio"]:
                    failures.append({"type": "regression", "metric": metric, "rule": "max_increase_ratio", "candidate": candidate_value, "baseline": baseline_value, "threshold": threshold["max_increase_ratio"]})
            comparisons.append(comparison)
    return {"passed": not failures, "failures": failures, "warnings": warnings, "comparisons": comparisons, "baseline_run_id": baseline.metadata.run_id if baseline else None}
