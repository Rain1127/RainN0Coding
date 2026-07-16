from __future__ import annotations

import asyncio
import inspect
from copy import deepcopy

import config as config_module


FINAL_SUCCESS = "success"
FINAL_DEGRADED_SUCCESS = "degraded_success"
FINAL_PARTIAL_SUCCESS = "partial_success"
FINAL_FAILED = "failed"
DEGRADABLE_PHASES = {"intent", "pm", "image_collector", "reviewer", "memory", "rag"}
PARTIAL_SAFE_PHASES = {"reviewer", "builder", "coder"}
SHORT_TIMEOUT_PHASES = {"intent", "image_collector", "memory", "rag"}
MEDIUM_TIMEOUT_PHASES = {"pm", "architect", "reviewer"}
LONG_TIMEOUT_PHASES = {"coder", "builder"}
INTENT_FALLBACK_MAP = {
    "vue_project": "代码生成 / 前端代码生成 / 生成 Vue 项目",
    "html": "代码生成 / 前端代码生成 / 生成 HTML 页面",
    "multi_file": "代码生成 / 前端代码生成 / 生成多文件页面",
    "python": "代码生成 / 后端代码生成 / 生成 Python 服务",
    "java": "代码生成 / 后端代码生成 / 生成 Java 服务",
    "go": "代码生成 / 后端代码生成 / 生成 Go 服务",
    "rust": "代码生成 / 后端代码生成 / 生成 Rust 服务",
    "nodejs": "代码生成 / 后端代码生成 / 生成 Node.js 服务",
    "generic": "代码生成 / 通用代码生成 / 生成项目",
}


def _config():
    return config_module.config


def ensure_availability_defaults(state: dict) -> dict:
    state.setdefault("degraded", False)
    state.setdefault("degraded_reasons", [])
    state.setdefault("failed_phase", None)
    state.setdefault("last_good_phase", None)
    state.setdefault("partial_code_available", False)
    state.setdefault("final_status", None)
    state.setdefault("recovery_hint", None)
    state.setdefault("phase_failures", [])
    return state


def copy_state(state: dict) -> dict:
    return deepcopy(ensure_availability_defaults(state))


def classify_phase_failure(phase: str, exc: Exception, error_type: str) -> dict:
    reason_code = f"{phase}_{error_type}"
    degradable = phase in DEGRADABLE_PHASES or phase == "builder"
    partial_code_safe = phase in PARTIAL_SAFE_PHASES
    return {
        "phase": phase,
        "reason_code": reason_code,
        "error_type": error_type,
        "retryable": phase in {"coder", "reviewer"},
        "degradable": degradable,
        "partial_code_safe": partial_code_safe,
        "message": str(exc),
    }


def append_phase_failure(state: dict, failure: dict) -> dict:
    state = ensure_availability_defaults(state)
    state["phase_failures"].append(failure)
    return state


def phase_timeout_seconds(phase: str, cfg=None) -> float:
    cfg = cfg or _config()
    if phase in SHORT_TIMEOUT_PHASES:
        return float(cfg.AGENT_PHASE_TIMEOUT_SHORT_SECONDS)
    if phase in MEDIUM_TIMEOUT_PHASES:
        return float(cfg.AGENT_PHASE_TIMEOUT_MEDIUM_SECONDS)
    if phase in LONG_TIMEOUT_PHASES:
        return float(cfg.AGENT_PHASE_TIMEOUT_LONG_SECONDS)
    return float(cfg.AGENT_PHASE_TIMEOUT_MEDIUM_SECONDS)


def has_partial_code(state: dict) -> bool:
    code_files = state.get("code_files") or []
    code_gen_type = state.get("code_gen_type") or ""
    if not code_files:
        return False
    if any(item.get("path") == "src/App.vue" for item in code_files):
        return True
    return any(item.get("content", "").strip() for item in code_files) and bool(code_gen_type)


def compute_final_status(state: dict) -> dict:
    state = ensure_availability_defaults(state)
    partial_code = has_partial_code(state)
    state["partial_code_available"] = partial_code

    if state.get("failed_phase") == "builder" and partial_code:
        state["final_status"] = FINAL_PARTIAL_SUCCESS
        state["recovery_hint"] = "You can continue editing the generated files and retry build later."
        return state

    if state.get("failed_phase") == "coder" and partial_code:
        state["final_status"] = FINAL_PARTIAL_SUCCESS
        state["recovery_hint"] = "The latest code pass failed, but editable code is available. Review and continue from the saved files."
        return state

    if state.get("failed_phase") and not partial_code:
        state["final_status"] = FINAL_FAILED
        state["recovery_hint"] = "Retry the request after the failed phase is available again."
        return state

    if state.get("degraded"):
        state["final_status"] = FINAL_DEGRADED_SUCCESS
        state["recovery_hint"] = "The request completed with fallbacks. Review the generated result before deploying."
        return state

    state["final_status"] = FINAL_SUCCESS
    return state


def finalize_state(state: dict) -> dict:
    state = compute_final_status(state)
    review = state.get("review") or {}
    build = state.get("build_result") or {}
    indexing = state.get("indexing_result") or {}
    quality_gate = state.get("quality_gate_result") or {}

    state["final_result"] = {
        "status": state.get("final_status"),
        "phase": state.get("phase"),
        "failed_phase": state.get("failed_phase"),
        "degraded": state.get("degraded", False),
        "degraded_reasons": state.get("degraded_reasons", []),
        "partial_code_available": state.get("partial_code_available", False),
        "recovery_hint": state.get("recovery_hint"),
        "code_files_count": len(state.get("code_files", [])),
        "images_count": len(state.get("images", [])),
        "review_score": review.get("score"),
        "review_passed": review.get("passed"),
        "build_success": build.get("success"),
        "indexing_success": indexing.get("success"),
        "indexing_message": indexing.get("message"),
        "quality_gate_passed": quality_gate.get("passed"),
        "quality_gate_reason": quality_gate.get("reason"),
        "syntax_check_passed": quality_gate.get("syntax_check_passed"),
    }
    state["phase"] = "completed"
    return state


def mark_degraded(state: dict, reason_code: str, failed_phase: str | None = None) -> dict:
    state = ensure_availability_defaults(state)
    state["degraded"] = True
    if reason_code not in state["degraded_reasons"]:
        state["degraded_reasons"].append(reason_code)
    if failed_phase:
        state["failed_phase"] = failed_phase
    return state


def apply_pm_fallback(state: dict, reason_code: str) -> dict:
    state = copy_state(state)
    state["prd"] = {
        "page_name": "Generated Page",
        "page_type": "landing",
        "features": ["core experience", "primary action"],
        "target_audience": "general",
    }
    state["phase"] = "prd_done"
    return mark_degraded(state, reason_code, "pm")


def apply_intent_failure(state: dict, reason_code: str, exc: Exception) -> dict:
    state = copy_state(state)
    code_gen_type = state.get("code_gen_type") or "generic"
    state["intent"] = {
        "primary_intent": INTENT_FALLBACK_MAP.get(code_gen_type, INTENT_FALLBACK_MAP["generic"]),
        "secondary_intents": [],
        "confidence": 0.55,
        "confidence_reason": f"Intent fallback used: {exc}",
        "key_entities": [],
        "slots": {"code_gen_type": code_gen_type},
        "missing_slots": [],
        "should_clarify": False,
        "clarification_questions": [],
        "retrieval_hint": code_gen_type,
    }
    state["clarification"] = None
    state["phase"] = "intent_done"
    return mark_degraded(state, reason_code, "intent")


def apply_architect_fallback(state: dict, reason_code: str) -> dict:
    state = copy_state(state)
    state["architecture"] = {
        "tech_stack": state.get("code_gen_type", "generic"),
        "component_tree": [],
        "file_list": [{"path": "src/App.vue", "purpose": "entry"}],
        "data_flow": [],
    }
    state["phase"] = "arch_done"
    return mark_degraded(state, reason_code, "architect")


def apply_builder_failure(state: dict, exc: Exception, reason_code: str) -> dict:
    state = copy_state(state)
    state["build_result"] = {"success": False, "log": str(exc)}
    return mark_degraded(state, reason_code, "builder")


def apply_coder_failure(state: dict, exc: Exception, reason_code: str) -> dict:
    state = copy_state(state)
    state["phase"] = "error"
    state["error"] = str(exc)
    state["failed_phase"] = "coder"
    if has_partial_code(state):
        return mark_degraded(state, reason_code, "coder")
    return state


def apply_reviewer_failure(state: dict, exc: Exception, reason_code: str) -> dict:
    state = copy_state(state)
    state["review"] = {
        "passed": True,
        "score": None,
        "issues": [],
        "summary": f"Reviewer unavailable: {exc}",
    }
    state["phase"] = "review_done"
    return mark_degraded(state, reason_code, "reviewer")


def apply_image_collector_failure(state: dict, reason_code: str) -> dict:
    state = copy_state(state)
    state["images"] = []
    return mark_degraded(state, reason_code, "image_collector")


async def _run_phase_runner(phase: str, state: dict, runner):
    cfg = _config()
    working_state = copy_state(state)
    if not getattr(cfg, "AGENT_RESILIENCE_ENABLED", True):
        result = runner(working_state)
        if inspect.isawaitable(result):
            return await result
        return result

    timeout_seconds = phase_timeout_seconds(phase, cfg)
    if inspect.iscoroutinefunction(runner):
        return await asyncio.wait_for(runner(working_state), timeout=timeout_seconds)

    return await asyncio.wait_for(asyncio.to_thread(runner, working_state), timeout=timeout_seconds)


async def guarded_phase_call(phase: str, state: dict, runner):
    try:
        result = await _run_phase_runner(phase, state, runner)
        result = ensure_availability_defaults(result)
        result["last_good_phase"] = phase
        return result
    except TimeoutError as exc:
        reason_code = f"{phase}_timeout"
        failure = classify_phase_failure(phase, exc, "timeout")
        if phase == "intent":
            return append_phase_failure(apply_intent_failure(state, reason_code, exc), failure)
        if phase == "pm":
            return append_phase_failure(apply_pm_fallback(state, reason_code), failure)
        if phase == "architect":
            return append_phase_failure(apply_architect_fallback(state, reason_code), failure)
        if phase == "image_collector":
            return append_phase_failure(apply_image_collector_failure(state, reason_code), failure)
        if phase == "coder":
            return append_phase_failure(apply_coder_failure(state, exc, reason_code), failure)
        if phase == "reviewer":
            return append_phase_failure(apply_reviewer_failure(state, exc, reason_code), failure)
        if phase == "builder":
            return append_phase_failure(apply_builder_failure(state, exc, reason_code), failure)
        raise
    except Exception as exc:
        reason_code = f"{phase}_exception"
        failure = classify_phase_failure(phase, exc, "exception")
        if phase == "intent":
            return append_phase_failure(apply_intent_failure(state, reason_code, exc), failure)
        if phase == "pm":
            return append_phase_failure(apply_pm_fallback(state, reason_code), failure)
        if phase == "architect":
            return append_phase_failure(apply_architect_fallback(state, reason_code), failure)
        if phase == "image_collector":
            return append_phase_failure(apply_image_collector_failure(state, reason_code), failure)
        if phase == "coder":
            return append_phase_failure(apply_coder_failure(state, exc, reason_code), failure)
        if phase == "reviewer":
            return append_phase_failure(apply_reviewer_failure(state, exc, reason_code), failure)
        if phase == "builder":
            return append_phase_failure(apply_builder_failure(state, exc, reason_code), failure)
        raise
