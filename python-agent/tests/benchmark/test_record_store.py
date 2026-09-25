from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmark.contracts import RawRunRecord
from benchmark.record_store import persist_raw_record


pytestmark = pytest.mark.benchmark

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


def test_raw_record_redacts_nested_generated_content_and_logs(tmp_path: Path) -> None:
    record = _record("private-output").model_copy(
        update={
            "output": {
                "code_files": [
                    {
                        "path": "config.py",
                        "content": "api_key=raw-secret-value\nURL=mysql://app:db-password@localhost/db",
                    }
                ],
                "log": "/home/alice/private/build.log token=token-value",
            }
        }
    )

    path = persist_raw_record(tmp_path, "run", record)
    persisted = json.loads(path.read_text(encoding="utf-8"))
    rendered = json.dumps(persisted)

    assert "raw-secret-value" not in rendered
    assert "db-password" not in rendered
    assert "alice" not in rendered
    assert "token-value" not in rendered


def test_raw_record_redacts_prefixed_config_keys_empty_user_uri_and_spaced_user_paths(
    tmp_path: Path,
) -> None:
    sensitive = (
        "OPENAI_API_KEY=plainvalue123\n"
        "DATABASE_PASSWORD: hunter2\n"
        "SESSION_COOKIE='session-cookie-value'\n"
        'settings = {"REFRESH_TOKEN": "json-refresh-value", "client_id": "safe-client-id"}\n'
        "REDIS_URL=redis://:password123@host/0\n"
        'windows_path = "C:\\Users\\Alice Smith\\private\\config.json", safe = true\n'
        'unix_path: "/Users/Alice Smith/private/config.json"; next'
    )
    record = _record("prefixed-secrets").model_copy(
        update={"output": {"code_files": [{"path": "config.py", "content": sensitive}]}}
    )

    path = persist_raw_record(tmp_path, "run", record)

    text = path.read_text(encoding="utf-8")
    for leaked in (
        "plainvalue123",
        "hunter2",
        "session-cookie-value",
        "json-refresh-value",
        "password123",
        "Alice Smith",
    ):
        assert leaked not in text
    assert "safe-client-id" in text
