from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from benchmark.contracts import LoadedCase, RawRunRecord

from .base import RunContext


class ReplayRunner:
    def run(self, case: LoadedCase, context: RunContext) -> list[RawRunRecord]:
        context.assert_mode_allowed(case.case.execution.mode)
        case_id = case.case.id
        if case.case.execution.mode != "replay":
            raise ValueError(f"{case_id}: replay runner requires replay mode")
        if case.record_path is None:
            raise ValueError(f"{case_id}: replay record is required")

        started_at = datetime.now(timezone.utc).isoformat()
        started = perf_counter()
        try:
            raw: Any = json.loads(case.record_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"{case_id}: invalid replay envelope") from exc

        if not isinstance(raw, dict):
            raise ValueError(f"{case_id}: invalid replay envelope")
        if "output" in raw:
            output = raw.get("output")
            metrics = raw.get("metrics", {})
        else:
            output = raw
            metrics = {}
        if not isinstance(output, dict) or not isinstance(metrics, dict):
            raise ValueError(f"{case_id}: invalid replay envelope")

        observed_metrics: dict[str, float | None] = {}
        for name, value in metrics.items():
            if value is None:
                observed_metrics[name] = None
            elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{case_id}: invalid replay metric {name}")
            else:
                observed_metrics[name] = float(value)
        duration_ms = (perf_counter() - started) * 1000
        return [
            RawRunRecord(
                case_id=case_id,
                output=output,
                observed_metrics=observed_metrics,
                started_at=started_at,
                duration_ms=duration_ms,
            )
        ]
