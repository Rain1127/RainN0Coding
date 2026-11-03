"""Knowledge evidence is submitted after final validation (gateway publication may follow)."""
from __future__ import annotations

from workflow.build_status import verified


def finalize_evidence(state: dict) -> dict:
    from config import config
    if not config.FEEDBACK_WRITES_ENABLED:
        return state
    app_id = state.get("app_id")
    build = state.get("build_result") or {}
    runtime = state.get("runtime_result") or {}
    accepted = verified(build) and (runtime.get("status") in ("succeeded", "not_required"))
    if not app_id:
        return state
    if not accepted or not (state.get("quality_gate_result") or {}).get("passed"):
        try:
            from rag.feedback_tracker import feedback_tracker
            feedback_tracker.apply_feedback(app_id, None, run_id=state.get("artifact_run_id", ""),
                validation={"status": "unverified", "failure_kind": build.get("failure_kind")})
        except Exception:
            pass
        return state
    code_files = state.get("code_files", [])
    changed = {f["path"] for f in (state.get("change_result") or {}).get("files", [])}
    if state.get("mode") != "modify":
        changed = {f["path"] for f in code_files}
    try:
        from rag.feedback_tracker import feedback_tracker
        from rag.rag_builder import index_code_files
        feedback_tracker.apply_feedback(app_id, True, run_id=state.get("artifact_run_id", ""),
            validation={"status": "succeeded", "build": build.get("status"), "runtime": runtime.get("status")},
            code_files=code_files, changed_files=changed)
        indexing = index_code_files(code_files, app_id, state.get("code_gen_type", "generic"),
                         review_score=(state.get("review") or {}).get("score", 0))
        state["indexing_result"] = indexing or {"success": False, "message": "入库未返回可核验结果",
                                                "indexed_count": 0, "total_count": len(code_files)}
        if state.get("build_repair_count") and state.get("build_repair_context"):
            import platform
            repair = "\n".join(item["diff"] for item in state.get("repair_diffs", []))
            if repair:
                feedback_tracker.record_verified_repair(run_id=state.get("artifact_run_id", ""),
                    environment={"language": state.get("code_gen_type"), "python": platform.python_version()},
                    symptom=state["build_repair_context"].get("log"), repair=repair,
                    validation={"status": "succeeded", "build": build.get("status"), "runtime": runtime.get("status")})
    except Exception as exc:
        state["indexing_result"] = {"success": False, "message": f"知识入库失败: {exc}",
                                    "indexed_count": 0, "total_count": len(code_files)}
    return state
