from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from benchmark.contracts import BenchmarkReport
from benchmark.redaction import redact


_IDENTITY_FIELDS = (
    "suite", "dataset_versions", "dataset_fingerprint", "prompt_fingerprint", "model_aliases", "offline",
)


def compatibility_identity(report: BenchmarkReport) -> dict[str, object]:
    metadata = report.metadata.model_dump(mode="json")
    return {name: metadata[name] for name in _IDENTITY_FIELDS}


def compatibility_key(report: BenchmarkReport) -> str:
    payload = json.dumps(compatibility_identity(report), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _target(report: BenchmarkReport, baseline_dir: str | Path) -> Path:
    return Path(baseline_dir) / compatibility_key(report) / "baseline.json"


def _serialize(report: BenchmarkReport) -> bytes:
    return (json.dumps(redact(report.model_dump(mode="json")), ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _write_temp(destination: Path, content: bytes) -> Path:
    descriptor, raw_path = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    temporary = Path(raw_path)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return temporary


def _publish(temporary: Path, destination: Path) -> None:
    os.link(temporary, destination)


def promote(report: BenchmarkReport, baseline_dir: str | Path) -> Path:
    destination = _target(report, baseline_dir)
    if destination.exists():
        raise FileExistsError(f"baseline already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        temporary = _write_temp(destination, _serialize(report))
        _publish(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination


def load_compatible(report: BenchmarkReport, baseline_dir: str | Path) -> BenchmarkReport | None:
    path = _target(report, baseline_dir)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid baseline report {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"invalid baseline report {path}: top-level JSON must be an object")
    loaded = BenchmarkReport.model_validate(raw)
    if compatibility_key(loaded) != compatibility_key(report):
        raise ValueError(f"baseline compatibility key does not match: {path}")
    return loaded
