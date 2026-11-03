"""Explicit build evidence shared by finalization, SSE and feedback."""
from __future__ import annotations


def build_result(status: str, log: str, project_dir: str, failure_kind: str | None = None) -> dict:
    if status not in {"succeeded", "failed", "unverified", "not_required"}:
        raise ValueError(f"invalid build status: {status}")
    return {"status": status, "success": True if status == "succeeded" else False if status == "failed" else None,
            "log": log, "project_dir": project_dir, "failure_kind": failure_kind}


def verified(build: dict) -> bool:
    return build.get("status") == "succeeded" and build.get("success") is True
