"""JSON-friendly aggregate metrics for Golden evaluation results."""
from __future__ import annotations

from collections import defaultdict
from math import ceil

from agent_eval.contracts import EvaluationResult


def _metrics(results: list[EvaluationResult]) -> dict[str, float | int]:
    total = len(results)
    passed = sum(result.passed for result in results)
    assertions_total = sum(result.assertions_total for result in results)
    assertions_passed = sum(result.assertions_passed for result in results)
    return {
        "cases": total,
        "passed": passed,
        "pass_rate": passed / total if total else 0.0,
        "assertion_pass_rate": assertions_passed / assertions_total if assertions_total else 0.0,
    }


def build_report(results: list[EvaluationResult]) -> dict:
    by_agent: dict[str, list[EvaluationResult]] = defaultdict(list)
    by_category: dict[str, list[EvaluationResult]] = defaultdict(list)
    for result in results:
        by_agent[result.case.agent].append(result)
        by_category[result.case.category].append(result)
    def ledger(group: list[EvaluationResult]) -> dict:
        assertions: dict[str, list[bool]] = defaultdict(list)
        observed: dict[str, list[float]] = defaultdict(list)
        for result in group:
            for assertion in result.assertions or []:
                assertions[assertion.metric].append(assertion.passed)
            for name, value in (result.observed_metrics or {}).items():
                observed[name].append(value)

        assertion_report = {
            name: {"checks": len(values), "passed": sum(values), "failed": len(values) - sum(values), "rate": sum(values) / len(values)}
            for name, values in sorted(assertions.items())
        }
        observed_report = {}
        for name, values in sorted(observed.items()):
            ordered = sorted(values)
            observed_report[name] = {
                "observations": len(values), "sum": sum(values), "mean": sum(values) / len(values),
                "min": ordered[0], "max": ordered[-1], "p50": ordered[(len(ordered) - 1) // 2],
                "p95": ordered[ceil(len(ordered) * 0.95) - 1],
            }
        return {"assertions": assertion_report, "observed": observed_report}

    return {
        "summary": _metrics(results),
        "by_agent": {name: _metrics(group) for name, group in sorted(by_agent.items())},
        "by_category": {name: _metrics(group) for name, group in sorted(by_category.items())},
        "metric_ledger": {
            "overall": ledger(results),
            "by_agent": {name: ledger(group) for name, group in sorted(by_agent.items())},
            "by_category": {name: ledger(group) for name, group in sorted(by_category.items())},
        },
        "results": [
            {
                "id": result.case.id,
                "agent": result.case.agent,
                "category": result.case.category,
                "passed": result.passed,
                "assertions_passed": result.assertions_passed,
                "assertions_total": result.assertions_total,
                "failures": result.failures,
                "actual_output": result.actual_output,
                "assertions": [
                    {"metric": assertion.metric, "passed": assertion.passed, "rule": assertion.rule, "path": assertion.path}
                    for assertion in result.assertions or []
                ],
                "observed_metrics": result.observed_metrics or {},
            }
            for result in results
        ],
    }
