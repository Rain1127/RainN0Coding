"""Evaluate flexible Golden constraints without requiring an online LLM judge."""
from __future__ import annotations

from typing import Any

from agent_eval.contracts import EvaluationResult, GoldenCase, MetricAssertion


_MISSING = object()


def _lookup(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_text(item) for item in value)
    return str(value).lower()


def _metric_name(case: GoldenCase, rule: str, path: str) -> str:
    tags = case.metric_tags or {}
    return tags.get(f"{rule}.{path}", tags.get(rule, {
        "equals": "task_correctness",
        "required_paths": "output_protocol_completeness",
        "required_text": "evidence_recall",
        "forbidden_text": "safety_compliance",
    }[rule]))


def _output_metrics(case: GoldenCase, actual_output: dict[str, Any]) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for path, name in (case.output_metrics or {}).items():
        value = _lookup(actual_output, path)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            metrics[name] = float(value)
    return metrics


def evaluate_case(
    case: GoldenCase, actual_output: dict[str, Any], observed_metrics: dict[str, float] | None = None
) -> EvaluationResult:
    """Score one output using declarative equality, presence, and text constraints."""
    passed = 0
    total = 0
    failures: list[str] = []
    assertions: list[MetricAssertion] = []
    expectations = case.expectations

    for path, expected in expectations.get("equals", {}).items():
        total += 1
        actual = _lookup(actual_output, path)
        if actual == expected:
            passed += 1
            assertions.append(MetricAssertion(_metric_name(case, "equals", path), True, "equals", path))
        else:
            failures.append(f"{path}: expected {expected!r}, got {actual!r}")
            assertions.append(MetricAssertion(_metric_name(case, "equals", path), False, "equals", path))

    for path in expectations.get("required_paths", []):
        total += 1
        if _lookup(actual_output, path) is not _MISSING:
            passed += 1
            assertions.append(MetricAssertion(_metric_name(case, "required_paths", path), True, "required_paths", path))
        else:
            failures.append(f"{path}: required path is missing")
            assertions.append(MetricAssertion(_metric_name(case, "required_paths", path), False, "required_paths", path))

    for path, alternatives in expectations.get("required_text", {}).items():
        total += 1
        actual = _lookup(actual_output, path)
        rendered = "" if actual is _MISSING else _text(actual)
        if any(str(candidate).lower() in rendered for candidate in alternatives):
            passed += 1
            assertions.append(MetricAssertion(_metric_name(case, "required_text", path), True, "required_text", path))
        else:
            failures.append(f"{path}: expected one of {alternatives!r} in output")
            assertions.append(MetricAssertion(_metric_name(case, "required_text", path), False, "required_text", path))

    for path, forbidden in expectations.get("forbidden_text", {}).items():
        total += 1
        actual = _lookup(actual_output, path)
        rendered = "" if actual is _MISSING else _text(actual)
        matched = next((candidate for candidate in forbidden if str(candidate).lower() in rendered), None)
        if matched is None:
            passed += 1
            assertions.append(MetricAssertion(_metric_name(case, "forbidden_text", path), True, "forbidden_text", path))
        else:
            failures.append(f"{path}: forbidden text {matched!r} found")
            assertions.append(MetricAssertion(_metric_name(case, "forbidden_text", path), False, "forbidden_text", path))

    metrics = _output_metrics(case, actual_output)
    metrics.update({name: float(value) for name, value in (observed_metrics or {}).items() if isinstance(value, (int, float)) and not isinstance(value, bool)})
    return EvaluationResult(case, passed == total, passed, total, failures, actual_output, assertions, metrics)
