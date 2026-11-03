"""Candidate directories and journalled publication. Old versions are never deleted.

The journal is persisted before moving the current directory. Recovery rolls back
an interrupted publication; candidates remain available for diagnosis/resume.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from uuid import uuid4

EXCLUDED = {"node_modules", ".git", "__pycache__", ".venv"}


def _atomic_json(path: Path, value: dict) -> None:
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", encoding="utf-8") as fh:
        json.dump(value, fh, ensure_ascii=False, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(temp, path)


def _store(current: Path) -> Path:
    return current.parent / ("." + current.name + ".versions")


def snapshot(root: Path) -> dict[str, str]:
    if not root.is_dir():
        return {}
    files = {}
    for directory, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED)
        for name in sorted(names):
            path = Path(directory) / name
            if path.is_symlink():
                raise ValueError("artifact symlinks are not supported")
            files[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def recover(current: Path) -> None:
    store = _store(current)
    journal = store / "publishing.json"
    if not journal.exists():
        return
    record = json.loads(journal.read_text(encoding="utf-8"))
    backup = store / record["backup"]
    candidate = store / record["candidate"]
    if backup.parent != store or candidate.parent != store:
        raise ValueError("invalid publication journal")
    if not current.exists() and backup.is_dir():
        os.replace(backup, current)
    # If current exists and candidate vanished, publication finished successfully.
    journal.unlink()


def prepare(state: dict) -> dict:
    current = Path(state["project_dir"]).resolve()
    recover(current)
    store = _store(current)
    store.mkdir(parents=True, exist_ok=True)
    run_id = uuid4().hex
    candidate = store / (run_id + ".candidate")
    original = snapshot(current)
    if state.get("mode") == "modify" and current.is_dir():
        shutil.copytree(current, candidate, ignore=shutil.ignore_patterns(*EXCLUDED))
    else:
        candidate.mkdir()
    state.update(project_dir=str(candidate), current_project_dir=str(current),
                 artifact_run_id=run_id, artifact_base=original,
                 artifact_status="candidate")
    _atomic_json(store / (run_id + ".json"), {"run_id": run_id, "status": "candidate",
                 "mode": state.get("mode"), "base": original})
    return state


def publish(state: dict) -> dict:
    if not state.get("current_project_dir") or state.get("artifact_status") == "published":
        return state
    current = Path(state["current_project_dir"])
    candidate = Path(state["project_dir"])
    store = _store(current)
    run_id = state["artifact_run_id"]
    if candidate.parent != store or snapshot(current) != state["artifact_base"]:
        raise ValueError("current artifact changed during generation; candidate retained")
    backup = store / (run_id + ".previous")
    journal = store / "publishing.json"
    _atomic_json(journal, {"backup": backup.name, "candidate": candidate.name})
    try:
        if current.exists():
            os.replace(current, backup)
        os.replace(candidate, current)
    except BaseException:
        recover(current)
        raise
    journal.unlink()
    _atomic_json(store / (run_id + ".json"), {"run_id": run_id, "status": "published",
                 "mode": state.get("mode"), "previous": backup.name if backup.exists() else None,
                 "files": snapshot(current)})
    state.update(project_dir=str(current), artifact_status="published", previous_project_dir=str(backup))
    return state
