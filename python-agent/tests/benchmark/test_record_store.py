from __future__ import annotations

from pathlib import Path

import pytest

from benchmark.contracts import RawRunRecord
from benchmark.record_store import persist_raw_record


def _record(case_id: str) -> RawRunRecord:
    return RawRunRecord(case_id=case_id, started_at="2026-01-01T00:00:00+00:00", duration_ms=0)


@pytest.mark.parametrize("run_id", ["../escape", "..", "/absolute", "nested/run"])
def test_rejects_unsafe_run_ids(tmp_path: Path, run_id: str) -> None:
    with pytest.raises(ValueError, match="unsafe run id"):
        persist_raw_record(tmp_path, run_id, _record("case"))


def test_case_id_suffix_prevents_normalization_collisions_and_rejects_overwrite(tmp_path: Path) -> None:
    first = persist_raw_record(tmp_path, "run", _record("case/a"))
    second = persist_raw_record(tmp_path, "run", _record("case:a"))

    assert first != second
    with pytest.raises(FileExistsError):
        persist_raw_record(tmp_path, "run", _record("case/a"))
