"""Data contracts shared by the offline Agent Golden Trajectory harness."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GoldenCase:
    id: str
    agent: str
    category: str
    input_state: dict[str, Any]
    expectations: dict[str, Any]
    metric_tags: dict[str, str] | None = None
    output_metrics: dict[str, str] | None = None


@dataclass(frozen=True)
class MetricAssertion:
    metric: str
    passed: bool
    rule: str
    path: str


@dataclass(frozen=True)
class EvaluationResult:
    case: GoldenCase
    passed: bool
    assertions_passed: int
    assertions_total: int
    failures: list[str]
    actual_output: dict[str, Any] | None = None
    assertions: list[MetricAssertion] | None = None
    observed_metrics: dict[str, float] | None = None
