from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, field_validator, model_validator

from .contracts import ExecutionMode, StrictModel


class SuiteConfig(StrictModel):
    schema_version: Literal[1]
    name: str
    dataset_roots: list[str] = Field(min_length=1)
    allowed_modes: list[ExecutionMode] = Field(min_length=1)
    offline: bool
    allow_unreviewed: bool = False
    fail_on_infrastructure_error: bool
    policy: str
    baseline_dir: str

    @field_validator("name", "policy", "baseline_dir")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @model_validator(mode="after")
    def unreviewed_cases_require_offline_suite(self) -> "SuiteConfig":
        if self.allow_unreviewed and not self.offline:
            raise ValueError("allow_unreviewed requires an offline suite")
        return self


def load_suite(source: str | Path) -> tuple[SuiteConfig, Path]:
    path = Path(source).expanduser().resolve()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("suite must contain a top-level object")
        return SuiteConfig.model_validate(raw), path.parent
    except (OSError, UnicodeDecodeError, yaml.YAMLError, ValueError) as exc:
        raise ValueError(f"invalid benchmark suite {path}: {exc}") from exc
