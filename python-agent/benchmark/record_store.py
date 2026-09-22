from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path

from benchmark.contracts import RawRunRecord
from benchmark.redaction import redact


def _safe_case_id(case_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]+", "-", case_id).strip("-")
    return safe or "case"


def _safe_run_id(run_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
        raise ValueError("unsafe run id")
    return run_id


def persist_raw_record(record_dir: str | Path, run_id: str, record: RawRunRecord) -> Path:
    root = Path(record_dir).expanduser().resolve()
    safe_run_id = _safe_run_id(run_id)
    run_directory = (root / safe_run_id).resolve()
    try:
        run_directory.relative_to(root)
    except ValueError as exc:
        raise ValueError("unsafe run id") from exc
    suffix = hashlib.sha256(record.case_id.encode("utf-8")).hexdigest()[:10]
    destination = run_directory / f"{_safe_case_id(record.case_id)}-{suffix}-{record.attempt_index}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"raw record already exists: {destination}")
    payload = redact(record.model_dump(mode="json"))
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return destination
