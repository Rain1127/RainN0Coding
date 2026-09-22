"""Migrate the historical ``agent_eval`` golden cases to benchmark YAML."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


def _source_error(source_file: Path, message: str, *, index: int | None = None, case_id: str | None = None) -> ValueError:
    context = f"; case index {index}" if index is not None else ""
    if case_id:
        context += f"; case id {case_id}"
    return ValueError(f"{source_file}{context}: {message}")


def migrate_directory(
    source_directory: str | Path,
    destination: str | Path,
    *,
    dataset_version: str,
) -> int:
    """Convert every case in sorted JSON files under *source_directory*."""
    source = Path(source_directory)
    destination_path = Path(destination)
    migrated: list[dict[str, Any]] = []
    seen_ids: dict[str, Path] = {}

    for source_file in sorted(source.rglob("*.json"), key=lambda path: path.as_posix()):
        try:
            document = json.loads(source_file.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _source_error(source_file, f"could not read JSON: {exc}") from exc
        if not isinstance(document, dict):
            raise _source_error(source_file, "top-level JSON must be an object")
        if "version" in document and document["version"] != 1:
            raise _source_error(source_file, f"unsupported source version: {document['version']!r}")
        cases = document.get("cases")
        if not isinstance(cases, list):
            raise _source_error(source_file, "cases must be a list")
        for index, old_case in enumerate(cases):
            if not isinstance(old_case, dict):
                raise _source_error(source_file, "case must be an object", index=index)
            case_id = old_case.get("id")
            case_id_text = case_id if isinstance(case_id, str) else None
            required = ("id", "agent", "category", "input_state")
            missing = [field for field in required if field not in old_case]
            if missing:
                raise _source_error(
                    source_file,
                    f"missing required field(s): {', '.join(missing)}",
                    index=index,
                    case_id=case_id_text,
                )
            if not isinstance(case_id, str) or not case_id.strip():
                raise _source_error(source_file, "id must be a nonblank string", index=index)
            if case_id in seen_ids:
                raise _source_error(
                    source_file,
                    f"duplicate case id {case_id!r}; first defined in {seen_ids[case_id]}",
                    index=index,
                    case_id=case_id,
                )
            seen_ids[case_id] = source_file
            target = old_case["agent"]
            execution: dict[str, Any] = {"mode": "deterministic" if target == "supervisor" else "replay"}
            if target != "supervisor":
                execution["record"] = f"../../records/{old_case['id']}.json"
            migrated.append(
                {
                    "id": old_case["id"],
                    "target": target,
                    "category": old_case["category"],
                    "difficulty": "medium",
                    "tags": ["pr", "migrated"],
                    "execution": execution,
                    "input": old_case["input_state"],
                    "expectations": old_case.get("expectations", {}),
                    "metric_tags": old_case.get("metric_tags", {}),
                    "output_metrics": old_case.get("output_metrics", {}),
                    "provenance": {"source": "curated", "reviewed": True, "sanitized": True},
                }
            )

    if not migrated:
        raise ValueError(f"{source}: no migrated cases found")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    document = {"schema_version": 1, "dataset_version": dataset_version, "cases": migrated}
    destination_path.write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return len(migrated)
