from __future__ import annotations

import json
import re
from pathlib import Path

from benchmark.contracts import RawRunRecord
from benchmark.redaction import redact


def _safe_case_id(case_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]+", "-", case_id).strip("-")
    return safe or "case"


def persist_raw_record(record_dir: str | Path, run_id: str, record: RawRunRecord) -> Path:
    destination = Path(record_dir) / run_id / f"{_safe_case_id(record.case_id)}-{record.attempt_index}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = redact(record.model_dump(mode="json"))
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return destination
