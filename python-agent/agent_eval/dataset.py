"""Golden trajectory JSON discovery and validation."""
from __future__ import annotations

import json
from pathlib import Path

from agent_eval.contracts import GoldenCase


def load_cases(dataset_path: str | Path, ignore_paths: set[Path] | None = None) -> list[GoldenCase]:
    root = Path(dataset_path)
    ignored = {path.resolve() for path in (ignore_paths or set())}
    cases: list[GoldenCase] = []
    seen_ids: set[str] = set()
    for source in sorted(root.rglob("*.json")):
        if source.resolve() in ignored:
            continue
        payload = json.loads(source.read_text(encoding="utf-8"))
        if payload.get("version") != 1:
            raise ValueError(f"{source}: expected version 1")
        for raw_case in payload.get("cases", []):
            required = ("id", "agent", "category", "input_state", "expectations")
            missing = [field for field in required if field not in raw_case]
            if missing:
                raise ValueError(f"{source}: case missing fields: {', '.join(missing)}")
            case_id = raw_case["id"]
            if case_id in seen_ids:
                raise ValueError(f"duplicate Golden case id: {case_id}")
            seen_ids.add(case_id)
            optional = {field: raw_case.get(field) for field in ("metric_tags", "output_metrics")}
            cases.append(GoldenCase(**{field: raw_case[field] for field in required}, **optional))
    return cases
