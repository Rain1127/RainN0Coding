from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .contracts import BenchmarkCase, LoadedCase


def load_cases(dataset_path: str | Path, asset_root: str | Path | None = None) -> list[LoadedCase]:
    dataset_root = Path(dataset_path).expanduser().resolve()
    if not dataset_root.is_dir():
        raise ValueError(f"dataset path must be an existing directory: {dataset_root}")
    explicit_asset_root = asset_root is not None
    asset_boundary = Path(asset_root).expanduser().resolve() if explicit_asset_root else dataset_root
    if not asset_boundary.is_dir():
        raise ValueError(f"asset root must be an existing directory: {asset_boundary}")
    files = sorted((*dataset_root.rglob("*.yaml"), *dataset_root.rglob("*.yml")), key=lambda p: p.as_posix())
    loaded: list[LoadedCase] = []
    seen: set[str] = set()
    for source_path in files:
        try:
            raw = yaml.safe_load(source_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
            raise ValueError(f"failed to parse YAML file {source_path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise ValueError(f"dataset file must contain a top-level object: {source_path}")
        if type(raw.get("schema_version")) is not int or raw["schema_version"] != 1:
            raise ValueError(f"schema_version must be exactly 1: {source_path}")
        dataset_version = raw.get("dataset_version")
        if not isinstance(dataset_version, str) or not dataset_version.strip():
            raise ValueError(f"dataset_version must be nonblank: {source_path}")
        cases = raw.get("cases")
        if not isinstance(cases, list):
            raise ValueError(f"cases must be a list: {source_path}")
        for raw_case in cases:
            if not isinstance(raw_case, dict):
                raise ValueError(f"each case must be an object: {source_path}")
            case_data: dict[str, Any] = {**raw_case, "schema_version": 1, "dataset_version": dataset_version}
            case = BenchmarkCase.model_validate(case_data)
            if case.id in seen:
                raise ValueError(f"duplicate benchmark case id: {case.id}")
            seen.add(case.id)
            record_path = None
            if case.execution.record is not None:
                record_path = (source_path.parent / case.execution.record).resolve()
                try:
                    record_path.relative_to(asset_boundary)
                except ValueError as exc:
                    boundary_name = "asset root" if explicit_asset_root else "dataset root"
                    raise ValueError(f"record is outside {boundary_name}: {case.execution.record}") from exc
                if not record_path.is_file():
                    raise ValueError(f"record does not exist: {record_path}")
            loaded.append(LoadedCase(case=case, source_path=source_path.resolve(), record_path=record_path))
    if not loaded:
        raise ValueError("dataset contains no benchmark cases")
    return loaded
