import importlib
import sys
import asyncio
import json

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.harness]


def test_codegen_state_supports_availability_fields():
    from state.code_gen_state import CodeGenState

    state: CodeGenState = {
        "phase": "init",
        "degraded": False,
        "degraded_reasons": [],
        "failed_phase": None,
        "last_good_phase": None,
        "partial_code_available": False,
        "final_status": None,
        "recovery_hint": None,
        "phase_failures": [],
    }

    assert state["degraded"] is False
    assert state["degraded_reasons"] == []
    assert state["partial_code_available"] is False


def test_resilience_config_defaults(monkeypatch):
    for key in [
        "AGENT_RESILIENCE_ENABLED",
        "AGENT_PHASE_TIMEOUT_SHORT_SECONDS",
        "AGENT_PHASE_TIMEOUT_MEDIUM_SECONDS",
        "AGENT_PHASE_TIMEOUT_LONG_SECONDS",
    ]:
        monkeypatch.delenv(key, raising=False)

    sys.modules.pop("config", None)
    config_module = importlib.import_module("config")
    cfg = config_module.config

    assert cfg.AGENT_RESILIENCE_ENABLED is True
    assert cfg.AGENT_PHASE_TIMEOUT_SHORT_SECONDS == 30
    assert cfg.AGENT_PHASE_TIMEOUT_MEDIUM_SECONDS == 90
    assert cfg.AGENT_PHASE_TIMEOUT_LONG_SECONDS == 240


def test_classify_phase_failure_marks_reviewer_as_degradable():
    from workflow.resilience import classify_phase_failure

    failure = classify_phase_failure("reviewer", RuntimeError("boom"), error_type="exception")

    assert failure["phase"] == "reviewer"
    assert failure["reason_code"] == "reviewer_exception"
    assert failure["degradable"] is True
    assert failure["partial_code_safe"] is True


def test_classify_phase_failure_marks_coder_as_hard_fail():
    from workflow.resilience import classify_phase_failure

    failure = classify_phase_failure("coder", TimeoutError("late"), error_type="timeout")

    assert failure["phase"] == "coder"
    assert failure["reason_code"] == "coder_timeout"
    assert failure["degradable"] is False


def test_compute_final_status_prefers_partial_success_when_code_exists():
    from workflow.resilience import compute_final_status

    state = {
        "phase": "build_done",
        "degraded": True,
        "degraded_reasons": ["builder_exception"],
        "failed_phase": "builder",
        "code_gen_type": "vue_project",
        "code_files": [{"path": "src/App.vue", "content": "<template />"}],
        "build_result": {"success": False, "log": "npm build failed"},
    }

    final = compute_final_status(state)

    assert final["final_status"] == "partial_success"
    assert final["partial_code_available"] is True
    assert final["recovery_hint"]


def test_compute_final_status_returns_partial_success_for_failed_coder_with_existing_code():
    from workflow.resilience import compute_final_status

    state = {
        "phase": "error",
        "degraded": True,
        "degraded_reasons": ["coder_exception"],
        "failed_phase": "coder",
        "code_gen_type": "vue_project",
        "code_files": [{"path": "src/App.vue", "content": "<template />"}],
    }

    final = compute_final_status(state)

    assert final["final_status"] == "partial_success"
    assert final["partial_code_available"] is True
    assert final["recovery_hint"]


def test_finalize_state_returns_partial_success_for_failed_builder():
    from workflow.resilience import finalize_state

    state = {
        "phase": "build_done",
        "degraded": True,
        "degraded_reasons": ["builder_exception"],
        "failed_phase": "builder",
        "code_gen_type": "vue_project",
        "code_files": [{"path": "src/App.vue", "content": "<template />"}],
        "review": {"passed": True, "score": 88},
        "build_result": {"success": False, "log": "npm build failed"},
        "images": [],
    }

    final = finalize_state(state)

    assert final["phase"] == "completed"
    assert final["final_result"]["status"] == "partial_success"
    assert final["final_result"]["partial_code_available"] is True


def test_finalize_state_returns_failed_when_no_code_exists():
    from workflow.resilience import finalize_state

    state = {
        "phase": "error",
        "failed_phase": "coder",
        "degraded": False,
        "code_gen_type": "vue_project",
        "code_files": [],
        "images": [],
    }

    final = finalize_state(state)

    assert final["final_result"]["status"] == "failed"
    assert final["final_result"]["code_files_count"] == 0


def test_stream_workflow_emits_warning_for_degraded_result(
    monkeypatch, fake_conversation_memory, collect_json_events
):
    import workflow.sse_stream as sse_stream

    async def fake_run_workflow_async(*args, **kwargs):
        yield {
            "phase": "completed",
            "degraded": True,
            "degraded_reasons": ["reviewer_timeout"],
            "failed_phase": "reviewer",
            "partial_code_available": True,
            "final_result": {
                "status": "degraded_success",
                "failed_phase": "reviewer",
                "degraded": True,
                "degraded_reasons": ["reviewer_timeout"],
                "partial_code_available": True,
                "recovery_hint": "Review the generated result before deploying.",
            },
            "review": {"passed": True, "score": 85},
            "code_files": [{"path": "src/App.vue", "content": "<template />"}],
            "intent": {"primary_intent": "code"},
            "retry_count": 0,
        }

    monkeypatch.setattr(sse_stream, "conversation_memory", fake_conversation_memory)
    monkeypatch.setattr(sse_stream, "run_workflow_async", fake_run_workflow_async)

    events = asyncio.run(collect_json_events(sse_stream.stream_workflow("hello", request_id="req-degraded")))

    assert any(event["type"] == "warning" and event["reason"] == "reviewer_timeout" for event in events)
    assert events[-1]["type"] == "done"
    assert events[-1]["status"] == "degraded_success"


def test_status_from_sse_event_accepts_partial_success():
    from server.generate_code_orchestrator import _status_from_sse_event

    event = json.dumps({"type": "done", "status": "partial_success"})
    assert _status_from_sse_event(event) == "partial_success"


def test_apply_pm_fallback_creates_minimal_prd():
    from workflow.resilience import apply_pm_fallback

    state = {"user_request": "build a blog home page", "code_gen_type": "vue_project"}
    result = apply_pm_fallback(state, "pm_timeout")

    assert result["prd"]["page_name"] == "Generated Page"
    assert result["prd"]["features"]
    assert result["degraded"] is True
    assert "pm_timeout" in result["degraded_reasons"]


def test_apply_architect_fallback_creates_minimal_file_list():
    from workflow.resilience import apply_architect_fallback

    state = {"code_gen_type": "vue_project", "prd": {"page_name": "Landing", "features": ["hero"]}}
    result = apply_architect_fallback(state, "architect_exception")

    assert result["architecture"]["file_list"]
    assert result["phase"] == "arch_done"


def test_apply_builder_failure_marks_partial_success():
    from workflow.resilience import apply_builder_failure

    state = {"code_gen_type": "vue_project", "code_files": [{"path": "src/App.vue", "content": "<template />"}]}
    result = apply_builder_failure(state, RuntimeError("npm build failed"), "builder_exception")

    assert result["failed_phase"] == "builder"
    assert result["degraded"] is True
    assert result["build_result"]["success"] is False


def test_guarded_phase_call_degrades_reviewer_timeout_with_existing_code():
    from workflow.resilience import guarded_phase_call

    async def failing_reviewer(_state):
        raise TimeoutError("review late")

    state = {
        "phase": "code_done",
        "code_gen_type": "vue_project",
        "code_files": [{"path": "src/App.vue", "content": "<template />"}],
        "degraded": False,
        "degraded_reasons": [],
        "phase_failures": [],
    }

    result = asyncio.run(guarded_phase_call("reviewer", state, failing_reviewer))

    assert result["phase"] == "review_done"
    assert result["degraded"] is True
    assert result["failed_phase"] == "reviewer"
    assert "reviewer_timeout" in result["degraded_reasons"]
    assert result["review"]["passed"] is True


def test_guarded_phase_call_records_structured_phase_failure_for_pm_fallback():
    from workflow.resilience import guarded_phase_call

    def failing_pm(_state):
        raise RuntimeError("pm blew up")

    state = {
        "user_request": "build a dashboard",
        "code_gen_type": "vue_project",
        "degraded": False,
        "degraded_reasons": [],
        "phase_failures": [],
    }

    result = asyncio.run(guarded_phase_call("pm", state, failing_pm))

    assert result["phase"] == "prd_done"
    assert result["phase_failures"] == [
        {
            "phase": "pm",
            "reason_code": "pm_exception",
            "error_type": "exception",
            "retryable": False,
            "degradable": True,
            "partial_code_safe": False,
            "message": "pm blew up",
        }
    ]


def test_phase_timeout_budget_mapping():
    from workflow.resilience import phase_timeout_seconds

    class _Cfg:
        AGENT_PHASE_TIMEOUT_SHORT_SECONDS = 11
        AGENT_PHASE_TIMEOUT_MEDIUM_SECONDS = 22
        AGENT_PHASE_TIMEOUT_LONG_SECONDS = 33

    assert phase_timeout_seconds("pm", _Cfg()) == 22
    assert phase_timeout_seconds("reviewer", _Cfg()) == 22
    assert phase_timeout_seconds("architect", _Cfg()) == 22
    assert phase_timeout_seconds("coder", _Cfg()) == 33


def test_guarded_phase_call_enforces_timeout_budget_for_sync_runner(monkeypatch):
    import time
    import workflow.resilience as resilience

    monkeypatch.setattr(
        resilience,
        "_config",
        lambda: type(
            "_Cfg",
            (),
            {
                "AGENT_RESILIENCE_ENABLED": True,
                "AGENT_PHASE_TIMEOUT_SHORT_SECONDS": 0.01,
                "AGENT_PHASE_TIMEOUT_MEDIUM_SECONDS": 0.02,
                "AGENT_PHASE_TIMEOUT_LONG_SECONDS": 0.03,
            },
        )(),
    )

    def slow_pm(_state):
        time.sleep(0.05)
        return {"phase": "prd_done", "prd": {"page_name": "too late"}}

    state = {
        "user_request": "build a dashboard",
        "code_gen_type": "vue_project",
        "degraded": False,
        "degraded_reasons": [],
        "phase_failures": [],
    }

    result = asyncio.run(resilience.guarded_phase_call("pm", state, slow_pm))

    assert result["phase"] == "prd_done"
    assert result["prd"]["page_name"] == "Generated Page"
    assert "pm_timeout" in result["degraded_reasons"]
    assert result["phase_failures"][0]["reason_code"] == "pm_timeout"


def test_guarded_phase_call_degrades_image_collector_failure_without_blocking_code_path():
    from workflow.resilience import guarded_phase_call

    def failing_image_collector(_state):
        raise RuntimeError("image source unavailable")

    state = {
        "phase": "arch_done",
        "code_gen_type": "vue_project",
        "images": [{"url": "stale"}],
        "degraded": False,
        "degraded_reasons": [],
        "phase_failures": [],
    }

    result = asyncio.run(guarded_phase_call("image_collector", state, failing_image_collector))

    assert result["images"] == []
    assert result["degraded"] is True
    assert result["failed_phase"] == "image_collector"
    assert "image_collector_exception" in result["degraded_reasons"]
    assert result["phase_failures"][0]["reason_code"] == "image_collector_exception"


def test_guarded_phase_call_preserves_existing_code_when_coder_fails():
    from workflow.resilience import guarded_phase_call

    def failing_coder(_state):
        raise RuntimeError("coder blew up")

    state = {
        "phase": "arch_done",
        "code_gen_type": "vue_project",
        "code_files": [{"path": "src/App.vue", "content": "<template />"}],
        "degraded": False,
        "degraded_reasons": [],
        "phase_failures": [],
    }

    result = asyncio.run(guarded_phase_call("coder", state, failing_coder))

    assert result["phase"] == "error"
    assert result["failed_phase"] == "coder"
    assert result["degraded"] is True
    assert result["code_files"] == [{"path": "src/App.vue", "content": "<template />"}]
    assert "coder_exception" in result["degraded_reasons"]
    assert result["phase_failures"][0]["reason_code"] == "coder_exception"


def test_guarded_phase_call_marks_failed_when_coder_has_no_code():
    from workflow.resilience import guarded_phase_call

    def failing_coder(_state):
        raise RuntimeError("coder blew up")

    state = {
        "phase": "arch_done",
        "code_gen_type": "vue_project",
        "code_files": [],
        "degraded": False,
        "degraded_reasons": [],
        "phase_failures": [],
    }

    result = asyncio.run(guarded_phase_call("coder", state, failing_coder))

    assert result["phase"] == "error"
    assert result["failed_phase"] == "coder"
    assert result["degraded"] is False
    assert result["phase_failures"][0]["reason_code"] == "coder_exception"


def test_guarded_phase_call_degrades_intent_failure_with_rule_based_fallback():
    from workflow.resilience import guarded_phase_call

    def failing_intent(_state):
        raise RuntimeError("intent llm unavailable")

    state = {
        "phase": "mode_detected",
        "user_request": "build a landing page",
        "code_gen_type": "vue_project",
        "degraded": False,
        "degraded_reasons": [],
        "phase_failures": [],
    }

    result = asyncio.run(guarded_phase_call("intent", state, failing_intent))

    assert result["phase"] == "intent_done"
    assert result["degraded"] is True
    assert result["failed_phase"] == "intent"
    assert result["intent"]["slots"]["code_gen_type"] == "vue_project"
    assert "intent_exception" in result["degraded_reasons"]
    assert result["phase_failures"][0]["reason_code"] == "intent_exception"


def test_stream_workflow_returns_partial_success_when_builder_fails(
    monkeypatch, fake_conversation_memory, collect_json_events
):
    import workflow.sse_stream as sse_stream

    async def fake_run_workflow_async(*args, **kwargs):
        yield {
            "phase": "completed",
            "degraded": True,
            "degraded_reasons": ["builder_exception"],
            "failed_phase": "builder",
            "partial_code_available": True,
            "final_result": {
                "status": "partial_success",
                "failed_phase": "builder",
                "degraded": True,
                "degraded_reasons": ["builder_exception"],
                "partial_code_available": True,
                "recovery_hint": "You can continue editing the generated files and retry build later.",
            },
            "review": {"passed": True, "score": 90},
            "code_files": [{"path": "src/App.vue", "content": "<template />"}],
            "intent": {"primary_intent": "code"},
            "retry_count": 0,
        }

    monkeypatch.setattr(sse_stream, "conversation_memory", fake_conversation_memory)
    monkeypatch.setattr(sse_stream, "run_workflow_async", fake_run_workflow_async)

    events = asyncio.run(collect_json_events(sse_stream.stream_workflow("hello", request_id="req-partial")))

    assert events[-1]["status"] == "partial_success"
    assert events[-1]["partial_code_available"] is True
    assert events[-1]["failed_phase"] == "builder"


def test_stream_workflow_returns_failed_when_coder_never_produces_code(
    monkeypatch, fake_conversation_memory, collect_json_events
):
    import workflow.sse_stream as sse_stream

    async def fake_run_workflow_async(*args, **kwargs):
        yield {
            "phase": "completed",
            "degraded": False,
            "degraded_reasons": [],
            "failed_phase": "coder",
            "partial_code_available": False,
            "final_result": {
                "status": "failed",
                "failed_phase": "coder",
                "degraded": False,
                "degraded_reasons": [],
                "partial_code_available": False,
                "recovery_hint": "Retry the request after the failed phase is available again.",
            },
            "review": {},
            "code_files": [],
            "intent": {"primary_intent": "code"},
            "retry_count": 0,
        }

    monkeypatch.setattr(sse_stream, "conversation_memory", fake_conversation_memory)
    monkeypatch.setattr(sse_stream, "run_workflow_async", fake_run_workflow_async)

    events = asyncio.run(collect_json_events(sse_stream.stream_workflow("hello", request_id="req-failed")))

    assert events[-1]["status"] == "failed"
    assert events[-1]["partial_code_available"] is False
