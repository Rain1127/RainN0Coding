from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ExecutionMode = Literal["deterministic", "replay", "live", "rag", "e2e"]
Target = Literal["intent", "coder", "reviewer", "supervisor", "rag", "e2e"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


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
