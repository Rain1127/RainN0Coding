# Agent Availability & Resilience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add graded degradation, partial-success returns, and deterministic high-availability harness coverage to the Python agent workflow, with only lightweight Java compatibility updates.

**Architecture:** Keep the existing LangGraph topology, but add a workflow-local resilience layer around phase execution and terminal finalization. Introduce availability state fields, a reusable failure-policy module, additive SSE warning/done semantics, and deterministic mocked workflow tests that prove degraded and partial-success behavior without real LLM calls.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, pytest, existing deterministic harness markers, Java Spring Boot SSE proxy compatibility.

---

## File Structure

- Create `python-agent/workflow/resilience.py`
  - Centralize failure classification, fallback helpers, final-status computation, and partial-code viability checks.
- Modify `python-agent/state/code_gen_state.py`
  - Add new availability-oriented TypedDict fields used across workflow, SSE, and tests.
- Modify `python-agent/config.py`
  - Add phase timeout and resilience toggle settings for the Python runtime.
- Modify `python-agent/workflow/code_gen_workflow.py`
  - Wrap phase execution through guarded helpers and ensure the terminal node uses the new finalizer output.
- Modify `python-agent/workflow/sse_stream.py`
  - Emit `warning` events and enhanced terminal `done` payloads.
- Modify `python-agent/server/main.py`
  - Treat `degraded_success` and `partial_success` as terminal semantic outcomes instead of generic errors.
- Create `python-agent/tests/test_workflow_resilience.py`
  - Deterministic unit and integration-style mocked workflow tests for availability semantics.
- Modify `python-agent/tests/conftest.py`
  - Register the new deterministic resilience suite in the marker-aware collection allowlist.
- Modify `python-agent/tests/test_internal_auth_and_concurrency.py`
  - Add server-level regression coverage for new terminal statuses.
- Modify `docs/production-hardening-harness.md`
  - Document new high-availability harness commands and expected degraded/partial-success semantics.
- Modify `.planning/2026-06-30-production-hardening/progress.md`
  - Record route 4 completion evidence and exact verification commands.
- Modify `src/main/java/com/yupi/yuaicodemother/controller/AppController.java`
  - Treat `degraded_success` and `partial_success` as non-system-error semantic terminal states.
- Modify `src/main/java/com/yupi/yuaicodemother/service/impl/AppServiceImpl.java`
  - Preserve meaningful chat-history summary text for `degraded_success` and `partial_success`.

---

### Task 1: Add Availability State and Resilience Config

**Files:**
- Create: `python-agent/workflow/resilience.py`
- Modify: `python-agent/state/code_gen_state.py`
- Modify: `python-agent/config.py`
- Test: `python-agent/tests/test_workflow_resilience.py`

- [ ] **Step 1: Write the failing state/config unit tests**

Create `python-agent/tests/test_workflow_resilience.py` with these starter tests:

```python
import importlib
import sys

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
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_workflow_resilience.py::test_codegen_state_supports_availability_fields tests/test_workflow_resilience.py::test_resilience_config_defaults -v
```

Expected: FAIL because the new state keys and config attributes do not exist yet.

- [ ] **Step 3: Add the availability fields to `CodeGenState`**

Update `python-agent/state/code_gen_state.py` by extending the TypedDict with:

```python
    degraded: bool
    degraded_reasons: list[str]
    failed_phase: str | None
    last_good_phase: str | None
    partial_code_available: bool
    final_status: str | None
    recovery_hint: str | None
    phase_failures: list[dict]
```

Also keep the existing fields intact so the rest of the workflow continues to type-check.

- [ ] **Step 4: Add resilience config defaults**

Update `python-agent/config.py` inside `class Config` with:

```python
    AGENT_RESILIENCE_ENABLED: bool = os.getenv("AGENT_RESILIENCE_ENABLED", "true").lower() == "true"
    AGENT_PHASE_TIMEOUT_SHORT_SECONDS: int = int(os.getenv("AGENT_PHASE_TIMEOUT_SHORT_SECONDS", "30"))
    AGENT_PHASE_TIMEOUT_MEDIUM_SECONDS: int = int(os.getenv("AGENT_PHASE_TIMEOUT_MEDIUM_SECONDS", "90"))
    AGENT_PHASE_TIMEOUT_LONG_SECONDS: int = int(os.getenv("AGENT_PHASE_TIMEOUT_LONG_SECONDS", "240"))
```

- [ ] **Step 5: Create the resilience helper module skeleton**

Create `python-agent/workflow/resilience.py` with this initial structure:

```python
from __future__ import annotations

from copy import deepcopy


FINAL_SUCCESS = "success"
FINAL_DEGRADED_SUCCESS = "degraded_success"
FINAL_PARTIAL_SUCCESS = "partial_success"
FINAL_FAILED = "failed"


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
```

- [ ] **Step 6: Re-run the new state/config tests**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_workflow_resilience.py::test_codegen_state_supports_availability_fields tests/test_workflow_resilience.py::test_resilience_config_defaults -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add python-agent/state/code_gen_state.py python-agent/config.py python-agent/workflow/resilience.py python-agent/tests/test_workflow_resilience.py
git commit -m "feat: add workflow resilience state and config"
```

---

### Task 2: Add Failure Classification and Final Status Helpers

**Files:**
- Modify: `python-agent/workflow/resilience.py`
- Test: `python-agent/tests/test_workflow_resilience.py`

- [ ] **Step 1: Write failing unit tests for failure policy and final-status rules**

Append these tests to `python-agent/tests/test_workflow_resilience.py`:

```python
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
```

- [ ] **Step 2: Run the new unit tests to verify they fail**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_workflow_resilience.py::test_classify_phase_failure_marks_reviewer_as_degradable tests/test_workflow_resilience.py::test_classify_phase_failure_marks_coder_as_hard_fail tests/test_workflow_resilience.py::test_compute_final_status_prefers_partial_success_when_code_exists -v
```

Expected: FAIL because the resilience helpers do not exist yet.

- [ ] **Step 3: Implement failure-classification helpers**

Extend `python-agent/workflow/resilience.py` with:

```python
DEGRADABLE_PHASES = {"intent", "pm", "image_collector", "reviewer", "memory", "rag"}
PARTIAL_SAFE_PHASES = {"reviewer", "builder", "coder"}


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
```

- [ ] **Step 4: Implement partial-code viability and final-status helpers**

Continue `python-agent/workflow/resilience.py` with:

```python
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
```

- [ ] **Step 5: Re-run the new resilience unit tests**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_workflow_resilience.py::test_classify_phase_failure_marks_reviewer_as_degradable tests/test_workflow_resilience.py::test_classify_phase_failure_marks_coder_as_hard_fail tests/test_workflow_resilience.py::test_compute_final_status_prefers_partial_success_when_code_exists -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add python-agent/workflow/resilience.py python-agent/tests/test_workflow_resilience.py
git commit -m "feat: add workflow failure policy helpers"
```

---

### Task 3: Wire Guarded Finalization Into the Workflow

**Files:**
- Modify: `python-agent/workflow/code_gen_workflow.py`
- Modify: `python-agent/workflow/resilience.py`
- Test: `python-agent/tests/test_workflow_resilience.py`

- [ ] **Step 1: Write failing workflow-finalizer tests**

Append these tests to `python-agent/tests/test_workflow_resilience.py`:

```python
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
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_workflow_resilience.py::test_finalize_state_returns_partial_success_for_failed_builder tests/test_workflow_resilience.py::test_finalize_state_returns_failed_when_no_code_exists -v
```

Expected: FAIL because `finalize_state` does not exist yet.

- [ ] **Step 3: Implement the workflow finalizer helper**

Extend `python-agent/workflow/resilience.py` with:

```python
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
```

- [ ] **Step 4: Switch `end_node` to the shared finalizer**

Update `python-agent/workflow/code_gen_workflow.py` imports and `end_node`:

```python
from workflow.resilience import ensure_availability_defaults, finalize_state
```

```python
def end_node(state: CodeGenState) -> CodeGenState:
    state = ensure_availability_defaults(state)
    return finalize_state(state)
```

Also update `_build_initial_state(...)` so it includes:

```python
        "degraded": False,
        "degraded_reasons": [],
        "failed_phase": None,
        "last_good_phase": None,
        "partial_code_available": False,
        "final_status": None,
        "recovery_hint": None,
        "phase_failures": [],
```

- [ ] **Step 5: Re-run the finalizer tests**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_workflow_resilience.py::test_finalize_state_returns_partial_success_for_failed_builder tests/test_workflow_resilience.py::test_finalize_state_returns_failed_when_no_code_exists -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add python-agent/workflow/resilience.py python-agent/workflow/code_gen_workflow.py python-agent/tests/test_workflow_resilience.py
git commit -m "feat: add workflow finalizer for degraded outcomes"
```

---

### Task 4: Emit Warning Events and Enhanced Terminal Done Status

**Files:**
- Modify: `python-agent/workflow/sse_stream.py`
- Modify: `python-agent/server/main.py`
- Modify: `python-agent/tests/test_internal_auth_and_concurrency.py`
- Test: `python-agent/tests/test_workflow_resilience.py`
- Test: `python-agent/tests/test_internal_auth_and_concurrency.py`

- [ ] **Step 1: Write the failing SSE warning and done-event tests**

Append these tests to `python-agent/tests/test_workflow_resilience.py`:

```python
import asyncio
import json


def test_stream_workflow_emits_warning_for_degraded_result(monkeypatch, fake_conversation_memory, collect_json_events):
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
    from server.main import _status_from_sse_event

    event = json.dumps({"type": "done", "status": "partial_success"})
    assert _status_from_sse_event(event) == "partial_success"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_workflow_resilience.py::test_stream_workflow_emits_warning_for_degraded_result tests/test_workflow_resilience.py::test_status_from_sse_event_accepts_partial_success -v
```

Expected: FAIL because no warning event is emitted and the server does not yet treat the new status as a first-class terminal result.

- [ ] **Step 3: Emit warning events and enhanced done payloads**

Update `python-agent/workflow/sse_stream.py` in the `phase == "completed" or phase == "error"` block to:

```python
                    final = state.get("final_result") or {}
                    final_status = final.get("status") or "success"

                    if final.get("degraded"):
                        for reason in final.get("degraded_reasons", []):
                            yield _event(
                                "warning",
                                status="degraded",
                                phase=final.get("failed_phase") or state.get("phase"),
                                reason=reason,
                                message=final.get("recovery_hint") or "Workflow completed with a degraded path.",
                            )

                    yield _event(
                        "done",
                        status=final_status,
                        failed_phase=final.get("failed_phase"),
                        degraded=final.get("degraded", False),
                        degraded_reasons=final.get("degraded_reasons", []),
                        partial_code_available=final.get("partial_code_available", False),
                        recovery_hint=final.get("recovery_hint"),
                        result=final,
                    )
```

- [ ] **Step 4: Keep Python server status tracking compatible**

Update `python-agent/server/main.py` so `_status_from_sse_event(...)` still returns:

```python
    if event_type == "done" and status and status != "success":
        return str(status)
```

and add a focused regression test to `python-agent/tests/test_internal_auth_and_concurrency.py`:

```python
def test_generate_code_records_partial_success_done_event(monkeypatch):
    main = load_main(monkeypatch, token="secret")
    recorded = []

    async def fake_stream_workflow(**kwargs):
        yield json.dumps({"type": "done", "status": "partial_success", "request_id": kwargs["request_id"]})

    def fake_record_request(user_id, app_id, code_gen_type, status):
        recorded.append(status)

    client = TestClient(main.app)
    with (
        patch.object(main, "stream_workflow", fake_stream_workflow),
        patch.object(main, "record_request", fake_record_request),
    ):
        response = client.post(
            "/api/generate-code",
            headers={"X-Internal-Token": "secret"},
            json={"prompt": "hello", "requestId": "req-partial"},
        )

    assert response.status_code == 200
    assert recorded == ["partial_success"]
```

- [ ] **Step 5: Re-run the focused SSE and server tests**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_workflow_resilience.py::test_stream_workflow_emits_warning_for_degraded_result tests/test_workflow_resilience.py::test_status_from_sse_event_accepts_partial_success tests/test_internal_auth_and_concurrency.py::test_generate_code_records_partial_success_done_event -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add python-agent/workflow/sse_stream.py python-agent/server/main.py python-agent/tests/test_workflow_resilience.py python-agent/tests/test_internal_auth_and_concurrency.py
git commit -m "feat: emit degraded workflow warning and terminal statuses"
```

---

### Task 5: Add Guarded Fallback Behavior for PM, Architect, Reviewer, and Builder Paths

**Files:**
- Modify: `python-agent/workflow/resilience.py`
- Modify: `python-agent/workflow/code_gen_workflow.py`
- Test: `python-agent/tests/test_workflow_resilience.py`

- [ ] **Step 1: Write failing fallback-behavior tests**

Append these tests to `python-agent/tests/test_workflow_resilience.py`:

```python
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
```

- [ ] **Step 2: Run the fallback tests to verify they fail**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_workflow_resilience.py::test_apply_pm_fallback_creates_minimal_prd tests/test_workflow_resilience.py::test_apply_architect_fallback_creates_minimal_file_list tests/test_workflow_resilience.py::test_apply_builder_failure_marks_partial_success -v
```

Expected: FAIL because the fallback helpers do not exist yet.

- [ ] **Step 3: Implement fallback helpers in `workflow/resilience.py`**

Add:

```python
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
```

- [ ] **Step 4: Add a minimal guarded phase wrapper for workflow-local fallback**

Extend `python-agent/workflow/resilience.py` with:

```python
async def guarded_phase_call(phase: str, state: dict, runner):
    try:
        result = runner(state)
        if hasattr(result, "__await__"):
            result = await result
        result = ensure_availability_defaults(result)
        result["last_good_phase"] = phase
        return result
    except TimeoutError as exc:
        reason_code = f"{phase}_timeout"
        if phase == "pm":
            return apply_pm_fallback(state, reason_code)
        if phase == "architect":
            return apply_architect_fallback(state, reason_code)
        if phase == "builder":
            return apply_builder_failure(state, exc, reason_code)
        raise
    except Exception as exc:
        reason_code = f"{phase}_exception"
        if phase == "pm":
            return apply_pm_fallback(state, reason_code)
        if phase == "architect":
            return apply_architect_fallback(state, reason_code)
        if phase == "builder":
            return apply_builder_failure(state, exc, reason_code)
        raise
```

- [ ] **Step 5: Wrap PM, Architect, forked code/image, and Builder calls**

Update `python-agent/workflow/code_gen_workflow.py` imports:

```python
from workflow.resilience import (
    ensure_availability_defaults,
    finalize_state,
    guarded_phase_call,
)
```

Then change the local nodes:

```python
async def fork_coder_and_images(state: CodeGenState) -> CodeGenState:
    state = await guarded_phase_call("image_collector", state, image_collector_agent)
    state = await guarded_phase_call("coder", state, coder_agent)
    return state
```

and register it as the node implementation. Also add thin async wrappers:

```python
async def pm_agent_node(state: CodeGenState) -> CodeGenState:
    return await guarded_phase_call("pm", state, pm_agent)


async def architect_agent_node(state: CodeGenState) -> CodeGenState:
    return await guarded_phase_call("architect", state, architect_agent)


async def builder_agent_node(state: CodeGenState) -> CodeGenState:
    return await guarded_phase_call("builder", state, builder_agent)
```

Wire those node functions into the graph instead of the raw agents.

- [ ] **Step 6: Re-run the fallback tests**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_workflow_resilience.py::test_apply_pm_fallback_creates_minimal_prd tests/test_workflow_resilience.py::test_apply_architect_fallback_creates_minimal_file_list tests/test_workflow_resilience.py::test_apply_builder_failure_marks_partial_success -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add python-agent/workflow/resilience.py python-agent/workflow/code_gen_workflow.py python-agent/tests/test_workflow_resilience.py
git commit -m "feat: add guarded fallback paths for workflow phases"
```

---

### Task 6: Add Deterministic Degraded and Partial-Success Harness Coverage

**Files:**
- Modify: `python-agent/tests/test_workflow_resilience.py`
- Modify: `python-agent/tests/conftest.py`
- Test: `python-agent/tests/test_workflow_resilience.py`

- [ ] **Step 1: Write the end-to-end mocked harness tests**

Append these tests to `python-agent/tests/test_workflow_resilience.py`:

```python
def test_stream_workflow_returns_partial_success_when_builder_fails(monkeypatch, fake_conversation_memory, collect_json_events):
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


def test_stream_workflow_returns_failed_when_coder_never_produces_code(monkeypatch, fake_conversation_memory, collect_json_events):
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
```

- [ ] **Step 2: Add the new resilience file to the deterministic collection allowlist**

Update `python-agent/tests/conftest.py`:

```python
MARKER_FILE_ALLOWLIST = {
    "unit": {"test_guardrails_prompt.py", "test_workflow_resilience.py"},
    "integration": {
        "test_guardrails_tools.py",
        "test_guardrails_output.py",
        "test_internal_auth_and_concurrency.py",
        "test_tools.py",
        "test_workflow_resilience.py",
    },
    "harness": {
        "test_guardrails_tools.py",
        "test_guardrails_output.py",
        "test_internal_auth_and_concurrency.py",
        "test_tools.py",
        "test_workflow_imports_unittest.py",
        "test_workflow_resilience.py",
    },
}
```

- [ ] **Step 3: Run the resilience file directly**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_workflow_resilience.py -v
```

Expected: PASS.

- [ ] **Step 4: Run the marker-selected harness suite**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest -m harness -v
```

Expected: PASS and include the new workflow resilience tests.

- [ ] **Step 5: Commit**

```bash
git add python-agent/tests/test_workflow_resilience.py python-agent/tests/conftest.py
git commit -m "test: cover workflow degraded and partial-success paths"
```

---

### Task 7: Add Lightweight Java Compatibility for New Terminal Statuses

**Files:**
- Modify: `src/main/java/com/yupi/yuaicodemother/controller/AppController.java`
- Modify: `src/main/java/com/yupi/yuaicodemother/service/impl/AppServiceImpl.java`
- Test: existing focused Java SSE/controller tests covering semantic failure parsing

- [ ] **Step 1: Write the compatibility behavior change in code first**

Update `AppController.semanticFailureMessage(...)` and `errorCodeForStatus(...)` so `degraded_success` and `partial_success` are not treated as generic system failures:

```java
    private int errorCodeForStatus(String status) {
        if ("overloaded".equals(status)) {
            return ErrorCode.AI_GENERATION_OVERLOADED.getCode();
        }
        if ("partial_success".equals(status) || "degraded_success".equals(status)) {
            return ErrorCode.SUCCESS.getCode();
        }
        return ErrorCode.SYSTEM_ERROR.getCode();
    }

    private String semanticFailureMessage(JSONObject payload, String status) {
        if ("partial_success".equals(status) || "degraded_success".equals(status)) {
            return null;
        }
        String message = payload.getStr("message");
        if (StrUtil.isNotBlank(message)) {
            return message;
        }
        return StrUtil.isNotBlank(status) ? status : ErrorCode.SYSTEM_ERROR.getMessage();
    }
```

Also update `detectSemanticFailure(...)` to skip creating `SseFailure` for those two statuses.

- [ ] **Step 2: Preserve meaningful chat-history summary text**

Update `AppServiceImpl.semanticFailureMessage(...)` to:

```java
        if ("done".equals(type) && StrUtil.isNotBlank(status)) {
            if ("partial_success".equals(status) || "degraded_success".equals(status)) {
                return null;
            }
            if (!"success".equals(status)) {
                return status;
            }
        }
```

This keeps the AI history entry on degraded or partial-success runs as completion rather than failure.

- [ ] **Step 3: Run focused Java tests**

Run:

```powershell
$env:JAVA_HOME='D:/Program Files/Java/jdk-23'
mvn test '-Dtest=AppControllerProductionBaselineTest,AppControllerTest,AppServiceImplProductionBaselineTest,AiCodeGeneratorFacadeTest'
```

Expected: PASS with no regression in overload and semantic SSE handling.

- [ ] **Step 4: Commit**

```bash
git add src/main/java/com/yupi/yuaicodemother/controller/AppController.java src/main/java/com/yupi/yuaicodemother/service/impl/AppServiceImpl.java
git commit -m "fix: treat degraded workflow statuses as non-fatal"
```

---

### Task 8: Update Hardening Docs and Record Verification Evidence

**Files:**
- Modify: `docs/production-hardening-harness.md`
- Modify: `.planning/2026-06-30-production-hardening/progress.md`
- Test: `python-agent/tests/test_workflow_resilience.py`
- Test: marker-selected Python harness suite

- [ ] **Step 1: Document the new availability semantics**

Add a new section to `docs/production-hardening-harness.md`:

```markdown
## Python Agent Availability Harness

- `degraded_success`: workflow completed with fallback or soft-fail paths
- `partial_success`: editable code was returned, but a late stage such as reviewer or builder failed
- `failed`: no safe editable code artifact could be returned

### Focused Resilience File

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_workflow_resilience.py -v
```

### Canonical Harness Command

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest -m harness -v
```

Expected result: deterministic mocked workflow resilience tests pass without real LLM providers.
```

- [ ] **Step 2: Record route 4 implementation evidence**

Append these bullets to `.planning/2026-06-30-production-hardening/progress.md`:

```markdown
- Route 4 design approved: workflow-internal graded degradation with `degraded_success` and `partial_success` terminal semantics.
- Route 4 implementation completed: resilience state fields, failure policy helpers, workflow finalizer, SSE warning/done enhancements, and deterministic mocked workflow resilience tests.
- Verification: `pytest tests/test_workflow_resilience.py -v` passed, and `pytest -m harness -v` passed with workflow resilience coverage included.
```

Replace the verification line with exact observed outcomes from fresh runs.

- [ ] **Step 3: Run fresh final Python verification**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_workflow_resilience.py tests/test_guardrails_prompt.py tests/test_guardrails_tools.py tests/test_guardrails_output.py tests/test_internal_auth_and_concurrency.py tests/test_workflow_imports_unittest.py tests/test_tools.py -v
```

Expected: PASS.

- [ ] **Step 4: Run fresh marker-based verification**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest -m harness -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/production-hardening-harness.md .planning/2026-06-30-production-hardening/progress.md
git commit -m "docs: record agent availability harness evidence"
```

---

## Plan Self-Review

- Spec coverage: state model, failure policy, guarded workflow execution, SSE warning/done semantics, partial-result rules, deterministic tests, docs, and Java compatibility each map to dedicated tasks.
- Placeholder scan: no `TODO`, `TBD`, or “handle appropriately” steps remain; each task lists concrete files, tests, commands, and code snippets.
- Type consistency: the plan consistently uses `degraded_success`, `partial_success`, `failed_phase`, `degraded_reasons`, `partial_code_available`, and `recovery_hint` across workflow state, SSE payloads, tests, and Java compatibility handling.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-01-agent-availability-resilience.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
