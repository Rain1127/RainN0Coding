from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

ExecutionMode = Literal["deterministic", "replay", "live", "rag", "e2e"]
Target = Literal["intent", "coder", "reviewer", "supervisor", "rag", "e2e"]


class ExecutionSpec(BaseModel):
    mode: ExecutionMode
    record: str | None = None
    repeats: int = Field(default=1, ge=1, le=20)


class Expectations(BaseModel):
    equals: dict[str, Any] = Field(default_factory=dict)
    required_paths: list[str] = Field(default_factory=list)
    required_text: dict[str, list[str]] = Field(default_factory=dict)
    forbidden_text: dict[str, list[str]] = Field(default_factory=dict)
    required_files: list[str] = Field(default_factory=list)
    relevant_document_ids: list[str] = Field(default_factory=list)


class Provenance(BaseModel):
    source: Literal["curated", "historical_bug", "synthetic", "sanitized_user"]
    reviewed: bool
    sanitized: bool


class BenchmarkCase(BaseModel):
    id: str
    schema_version: int = 1
    dataset_version: str
    target: Target
    category: str
    difficulty: Literal["basic", "medium", "hard"] = "medium"
    tags: list[str] = Field(default_factory=list)
    execution: ExecutionSpec
    input: dict[str, Any]
    expectations: Expectations = Field(default_factory=Expectations)
    metric_tags: list[str] = Field(default_factory=list)
    output_metrics: list[str] = Field(default_factory=list)
    gate: dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance

    @field_validator("id", "dataset_version", "category")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must be nonblank")
        return value


class LoadedCase(BaseModel):
    case: BenchmarkCase
    source_path: Path
    record_path: Path | None = None
