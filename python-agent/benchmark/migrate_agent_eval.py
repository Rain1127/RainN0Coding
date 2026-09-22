"""Migrate the historical ``agent_eval`` golden cases to benchmark YAML."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


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

    for source_file in sorted(source.rglob("*.json"), key=lambda path: path.as_posix()):
        document = json.loads(source_file.read_text(encoding="utf-8"))
        for old_case in document.get("cases", []):
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

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    document = {"schema_version": 1, "dataset_version": dataset_version, "cases": migrated}
    destination_path.write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return len(migrated)
