"""Finite repair routing. Environment/dependency failures never rewrite code."""
from __future__ import annotations

import hashlib
import json
import time
from config import config


def after_validation(state: dict, source: str = "build") -> str:
    result = state.get("build_result" if source == "build" else "runtime_result") or {}
    if state.get("error") or state.get("phase") == "error":
        return "end"
    status = result.get("status")
    if source == "build" and status in ("succeeded", "not_required"):
        return "runtime_validation"
    if status != "failed" or result.get("failure_kind") != "code":
        return "end"
    now = time.time()
    started = state.setdefault("repair_started_at", now)
    count = state.get("build_repair_count", 0)
    reason = None
    fingerprint = hashlib.sha256(str(result.get("log", "")).encode()).hexdigest()
    code_hash = hashlib.sha256(json.dumps(state.get("code_files", []), sort_keys=True).encode()).hexdigest()
    history = state.get("repair_history", [])
    if count >= getattr(config, "BUILD_MAX_REPAIRS", 2):
        reason = "repair_limit"
    elif now - started >= getattr(config, "BUILD_REPAIR_TIMEOUT_SECONDS", 480):
        reason = "repair_timeout"
    elif any(h["fingerprint"] == fingerprint or h["code_hash"] == code_hash for h in history):
        reason = "repeated_error_or_no_progress"
    if reason:
        state["repair_stop_reason"] = reason
        return "end"
    state["build_repair_count"] = count + 1
    state["repair_history"] = history + [{"source": source, "fingerprint": fingerprint,
                                         "code_hash": code_hash, "attempt": count + 1}]
    state["build_repair_context"] = {
        "source": source, "attempt": count + 1, "log": str(result.get("log", ""))[-8000:],
        "steps": result.get("steps", []), "instruction": "只修复错误定位涉及的文件；保留既有功能。修复后重新审查和验证。",
    }
    if state.get("project_dir"):
        from agents.coder_agent import _collect_code_files
        state["repair_before_files"] = _collect_code_files(state["project_dir"])
    else:
        state["repair_before_files"] = state.get("code_files", [])
    # The failed outcome remains in history; the next validation supplies fresh evidence.
    state["runtime_result"] = None
    return "coder_agent"


def record_repair_diff(state: dict) -> dict:
    if not state.get("repair_before_files") or state.get("error"):
        return state
    import difflib
    before = {f["path"]: f.get("content", "") for f in state["repair_before_files"]}
    after = {f["path"]: f.get("content", "") for f in state.get("code_files", [])}
    diffs = ["".join(difflib.unified_diff(before.get(p, "").splitlines(keepends=True), after.get(p, "").splitlines(keepends=True),
                                         fromfile="before/" + p, tofile="after/" + p))
             for p in sorted(before.keys() | after.keys()) if before.get(p) != after.get(p)]
    state["repair_diffs"] = state.get("repair_diffs", []) + [{"attempt": state.get("build_repair_count"), "diff": "\n".join(diffs)}]
    state["repair_before_files"] = []
    return state
