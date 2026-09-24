"""Declarative assertion evaluation for benchmark outputs."""
from __future__ import annotations

from typing import Any

from benchmark.contracts import BenchmarkCase, CaseEvaluation, MetricAssertion
from benchmark.evaluators.code_execution import normalize_generated_path, validate_generated_files


MISSING = object()
_DEFAULT_METRICS = {
    "equals": "task_correctness",
    "required_paths": "output_protocol_completeness",
    "required_text": "evidence_recall",
    "forbidden_text": "safety_compliance",
    "required_files": "output_protocol_completeness",
}


def lookup(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return MISSING
        current = current[part]
    return current


def rendered_text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(rendered_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(rendered_text(item) for item in value)
    return str(value).lower()


def metric_name(case: BenchmarkCase, rule: str, path: str) -> str:
    tags = case.metric_tags
    return tags.get(f"{rule}.{path}", tags.get(rule, _DEFAULT_METRICS[rule]))


def _output_metrics(case: BenchmarkCase, output: dict[str, Any]) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for path, name in case.output_metrics.items():
        value = lookup(output, path)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            metrics[name] = float(value)
    return metrics


def evaluate_assertions(
    case: BenchmarkCase,
    output: dict[str, Any],
    observed_metrics: dict[str, float | None] | None = None,
    *,
    attempt_index: int = 0,
) -> CaseEvaluation:
    """Evaluate all declarative expectations and return a canonical record."""
    assertions: list[MetricAssertion] = []
    failures: list[str] = []
    passed_count = 0
    total = 0
    expectations = case.expectations

    for path, expected in expectations.equals.items():
        total += 1
        actual = lookup(output, path)
        passed = actual is not MISSING and actual == expected
        if passed:
            passed_count += 1
        else:
            failures.append(f"{path}: expected {expected!r}, got {actual!r}")
        assertions.append(MetricAssertion(metric=metric_name(case, "equals", path), passed=passed, rule="equals", path=path))

    for path in expectations.required_paths:
        total += 1
        passed = lookup(output, path) is not MISSING
        if passed:
            passed_count += 1
        else:
            failures.append(f"{path}: required path is missing")
        assertions.append(MetricAssertion(metric=metric_name(case, "required_paths", path), passed=passed, rule="required_paths", path=path))

    for path, alternatives in expectations.required_text.items():
        total += 1
        value = lookup(output, path)
        rendered = "" if value is MISSING else rendered_text(value)
        passed = any(str(candidate).lower() in rendered for candidate in alternatives)
        if passed:
            passed_count += 1
        else:
            failures.append(f"{path}: expected one of {alternatives!r} in output")
        assertions.append(MetricAssertion(metric=metric_name(case, "required_text", path), passed=passed, rule="required_text", path=path))

    for path, forbidden in expectations.forbidden_text.items():
        total += 1
        value = lookup(output, path)
        rendered = "" if value is MISSING else rendered_text(value)
        matched = next((candidate for candidate in forbidden if str(candidate).lower() in rendered), None)
        passed = matched is None
        if passed:
            passed_count += 1
        else:
            failures.append(f"{path}: forbidden text {matched!r} found")
        assertions.append(MetricAssertion(metric=metric_name(case, "forbidden_text", path), passed=passed, rule="forbidden_text", path=path))

    generated_paths: set[str] = set()
    generated_files_valid = True
    if expectations.required_files:
        try:
            generated_paths = {
                path.as_posix() for path, _content in validate_generated_files(output.get("code_files"))
            }
        except ValueError:
            generated_files_valid = False
    for path in expectations.required_files:
        total += 1
        try:
            normalized = normalize_generated_path(path).as_posix()
        except ValueError:
            normalized = None
        passed = normalized is not None and generated_files_valid and normalized in generated_paths
        if normalized is None:
            failures.append(f"{path}: required generated file path is invalid")
        elif passed:
            passed_count += 1
        elif generated_files_valid:
            failures.append(f"{path}: required generated file is missing")
        else:
            failures.append(f"{path}: generated files are invalid")
        assertions.append(
            MetricAssertion(
                metric=metric_name(case, "required_files", path),
                passed=passed,
                rule="required_files",
                path=path,
            )
        )

    metrics: dict[str, float | None] = dict(observed_metrics or {})
    metrics.update(_output_metrics(case, output))
    return CaseEvaluation(
        case_id=case.id,
        attempt_index=attempt_index,
        target=case.target,
        category=case.category,
        passed=passed_count == total,
        assertions_passed=passed_count,
        assertions_total=total,
        assertions=assertions,
        failures=failures,
        output=output,
        observed_metrics=metrics,
    )
