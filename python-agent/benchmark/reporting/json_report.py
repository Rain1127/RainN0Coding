from __future__ import annotations
import json
from pathlib import Path
from typing import Iterable
from benchmark.contracts import BenchmarkReport, CaseEvaluation, RunMetadata
from benchmark.evaluators.metrics import describe
from benchmark.redaction import redact

def _group_summary(results: list[CaseEvaluation]) -> dict[str, int | float]:
    grouped: dict[str, list[CaseEvaluation]] = {}
    for result in results: grouped.setdefault(result.case_id, []).append(result)
    cases, assertions_total = len(grouped), sum(item.assertions_total for item in results)
    assertions_passed, observations = sum(item.assertions_passed for item in results), len(results)
    return {"case_pass_rate": sum(all(item.passed for item in attempts) for attempts in grouped.values()) / cases if cases else 0.0, "assertion_pass_rate": assertions_passed / assertions_total if assertions_total else 0.0, "observation_pass_rate": sum(item.passed for item in results) / observations if observations else 0.0, "cases": cases, "observations": observations}

def _group(results: list[CaseEvaluation], attr: str) -> dict[str, dict[str, int | float]]:
    grouped: dict[str, list[CaseEvaluation]] = {}
    for result in results: grouped.setdefault(str(getattr(result, attr)), []).append(result)
    return {key: _group_summary(items) for key, items in sorted(grouped.items())}

def build_report(metadata: RunMetadata, results: Iterable[CaseEvaluation], gate: dict | None = None) -> BenchmarkReport:
    ordered = sorted(
        [item.model_copy(update={"observed_metrics": {name: value for name, value in item.observed_metrics.items() if value is not None}}) for item in results],
        key=lambda item: (item.case_id, item.attempt_index),
    )
    metric_values: dict[str, list[float]] = {}
    for result in ordered:
        for name, value in result.observed_metrics.items():
            if value is not None: metric_values.setdefault(name, []).append(float(value))
    return BenchmarkReport(metadata=metadata, summary=_group_summary(ordered), by_target=_group(ordered, "target"), by_category=_group(ordered, "category"), metrics={name: describe(values) for name, values in sorted(metric_values.items()) if values}, gate=gate or {}, results=ordered)

def write_report(report: BenchmarkReport, path: str | Path) -> Path:
    destination = Path(path); destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(redact(report.model_dump(mode="json")), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destination

def read_report(path: str | Path) -> BenchmarkReport:
    return BenchmarkReport.model_validate_json(Path(path).read_text(encoding="utf-8"))
