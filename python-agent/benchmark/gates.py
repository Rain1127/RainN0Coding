from __future__ import annotations

import math
import json
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
    aliases = {"min": "minimum", "minimum": "minimum", "max": "maximum", "maximum": "maximum"}
    allowed = set(aliases) if section == "absolute_thresholds" else {"max_drop", "max_increase_ratio"}
    output: dict[str, float] = {}
    for key, raw in value.items():
        if key not in allowed:
            raise ValueError(f"policy {section}.{metric} has unknown threshold: {key}")
        if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(float(raw)):
            raise ValueError(f"policy {section}.{metric}.{key} must be finite numeric")
        canonical = aliases.get(key, key)
        numeric = float(raw)
        if canonical in output and output[canonical] != numeric:
            raise ValueError(f"policy {section}.{metric} has conflicting aliases for {canonical}")
        output[canonical] = numeric
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
    if len(hard_metrics) != len(set(hard_metrics)):
        raise ValueError("policy hard_fail_metrics contains duplicate metric names")
    for metric in sorted(hard_metrics):
        failed = [
            {"case_id": result.case_id, "attempt_index": result.attempt_index}
            for result in sorted(candidate.results, key=lambda item: (item.case_id, item.attempt_index))
            for assertion in sorted(result.assertions, key=lambda item: (item.metric, item.rule, item.path, item.passed))
            if assertion.metric == metric and not assertion.passed
        ]
        if failed:
            failures.append({"type": "hard", "metric": metric, "failed_assertions": failed})
    absolute = _section(policy, "absolute_thresholds", "absolute")
    if not all(isinstance(metric, str) and metric for metric in absolute):
        raise ValueError("policy absolute_thresholds metric name must be non-empty")
    for metric in sorted(absolute):
        configured = absolute[metric]
        threshold = _thresholds(configured, "absolute_thresholds", str(metric))
        value = _numeric(candidate, metric)
        for direction in ("minimum", "maximum"):
            if direction in threshold and ((direction == "minimum" and value < threshold[direction]) or (direction == "maximum" and value > threshold[direction])):
                failures.append({"type": "absolute", "metric": metric, "rule": direction, "candidate": value, "threshold": threshold[direction]})
    regression = _section(policy, "regression_thresholds", "regression")
    if baseline is None:
        warnings.append({"type": "no_baseline"})
        if policy.get("require_baseline", False):
            failures.append({"type": "no_baseline", "message": "A compatible baseline is required"})
    else:
        if not all(isinstance(metric, str) and metric for metric in regression):
            raise ValueError("policy regression_thresholds metric name must be non-empty")
        for metric in sorted(regression):
            configured = regression[metric]
            threshold = _thresholds(configured, "regression_thresholds", metric)
            candidate_value, baseline_value = _numeric(candidate, metric), _numeric(baseline, metric)
            comparison: dict[str, Any] = {"metric": metric, "candidate": candidate_value, "baseline": baseline_value, "delta": candidate_value - baseline_value}
            if "max_drop" in threshold:
                drop = baseline_value - candidate_value
                comparison["drop"] = drop
                if drop > threshold["max_drop"]:
                    failures.append({"type": "regression", "metric": metric, "rule": "max_drop", "candidate": candidate_value, "baseline": baseline_value, "threshold": threshold["max_drop"]})
            if "max_increase_ratio" in threshold:
                if baseline_value <= 0:
                    raise ValueError(f"cannot calculate increase ratio with non-positive baseline: {metric}")
                increase_ratio = (candidate_value - baseline_value) / baseline_value
                comparison["increase_ratio"] = increase_ratio
                if increase_ratio > threshold["max_increase_ratio"]:
                    failures.append({"type": "regression", "metric": metric, "rule": "max_increase_ratio", "candidate": candidate_value, "baseline": baseline_value, "threshold": threshold["max_increase_ratio"]})
            comparisons.append(comparison)
    failures.sort(key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    warnings.sort(key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    comparisons.sort(key=lambda item: str(item["metric"]))
    return {"passed": not failures, "failures": failures, "warnings": warnings, "comparisons": comparisons, "baseline_run_id": baseline.metadata.run_id if baseline else None}
