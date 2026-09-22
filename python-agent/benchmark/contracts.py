from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ExecutionMode = Literal["deterministic", "replay", "live", "rag", "e2e"]
Target = Literal["intent", "coder", "reviewer", "supervisor", "rag", "e2e"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def normalize_metric_value(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("metric must be finite numeric or None")
    try:
        normalized = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError("metric must be finite numeric or None") from exc
    if not math.isfinite(normalized):
        raise ValueError("metric must be finite numeric or None")
    return normalized


class ExecutionSpec(StrictModel):
    mode: ExecutionMode
    record: str | None = None
    repeats: int = Field(default=1, ge=1, le=20)


class Expectations(StrictModel):
    equals: dict[str, Any] = Field(default_factory=dict)
    required_paths: list[str] = Field(default_factory=list)
    required_text: dict[str, list[str]] = Field(default_factory=dict)
    forbidden_text: dict[str, list[str]] = Field(default_factory=dict)
    required_files: list[str] = Field(default_factory=list)
    relevant_document_ids: list[str] = Field(default_factory=list)


class Provenance(StrictModel):
    source: Literal["curated", "historical_bug", "synthetic", "sanitized_user"]
    reviewed: bool
    sanitized: bool


class BenchmarkCase(StrictModel):
    id: str
    schema_version: int = 1
    dataset_version: str
    target: Target
    category: str
    difficulty: Literal["basic", "medium", "hard"] = "medium"
    tags: list[str] = Field(default_factory=list)
    execution: ExecutionSpec
    input: dict[str, Any] = Field(default_factory=dict)
    expectations: Expectations = Field(default_factory=Expectations)
    metric_tags: dict[str, str] = Field(default_factory=dict)
    output_metrics: dict[str, str] = Field(default_factory=dict)
    gate: dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance

    @field_validator("id", "dataset_version", "category")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class LoadedCase(StrictModel):
    case: BenchmarkCase
    source_path: Path
    record_path: Path | None = None


class RawRunRecord(StrictModel):
    case_id: str
    attempt_index: int = Field(default=0, ge=0)
    output: dict[str, Any] = Field(default_factory=dict)
    observed_metrics: dict[str, float | None] = Field(default_factory=dict)
    infrastructure_error: str | None = None
    started_at: str
    duration_ms: float

    @field_validator("case_id")
    @classmethod
    def nonblank_case_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("case_id must not be blank")
        return value

    @field_validator("duration_ms", mode="before")
    @classmethod
    def finite_duration(cls, value: object) -> float:
        try:
            normalized = normalize_metric_value(value)
        except ValueError as exc:
            raise ValueError("duration_ms must be finite") from exc
        if normalized is None or normalized < 0:
            raise ValueError("duration_ms must be non-negative")
        return normalized

    @field_validator("observed_metrics", mode="before")
    @classmethod
    def finite_metrics(cls, value: object) -> object:
        if not isinstance(value, dict):
            raise ValueError("observed_metrics must be a mapping")
        normalized: dict[str, float | None] = {}
        for name, metric in value.items():
            try:
                normalized[name] = normalize_metric_value(metric)
            except ValueError as exc:
                raise ValueError(f"observed metric {name!r} must be finite numeric or None") from exc
        return normalized


class MetricAssertion(StrictModel):
    metric: str
    passed: bool
    rule: str
    path: str


class CaseEvaluation(StrictModel):
    case_id: str
    attempt_index: int = 0
    target: Target
    category: str
    passed: bool
    assertions_passed: int
    assertions_total: int
    assertions: list[MetricAssertion] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
    output: dict[str, Any] = Field(default_factory=dict)
    observed_metrics: dict[str, float | None] = Field(default_factory=dict)
    infrastructure_error: str | None = None


class RunMetadata(StrictModel):
    report_schema_version: int = 1
    run_id: str
    suite: str
    git_sha: str
    dataset_versions: list[str]
    dataset_fingerprint: str
    prompt_fingerprint: str
    model_aliases: dict[str, str]
    offline: bool
    started_at: str


class BenchmarkReport(StrictModel):
    metadata: RunMetadata
    summary: dict[str, int | float | str | bool]
    by_target: dict[str, dict[str, int | float]]
    by_category: dict[str, dict[str, int | float]]
    metrics: dict[str, dict[str, int | float]]
    gate: dict[str, Any] = Field(default_factory=dict)
    results: list[CaseEvaluation]
