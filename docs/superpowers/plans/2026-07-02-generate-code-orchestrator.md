# Generate Code Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the `generate_code` orchestration path from `python-agent/server/main.py` into a focused orchestrator module while preserving current HTTP, SSE, guardrail, concurrency, metric, and request-status behavior.

**Architecture:** Create a narrow `server/generate_code_orchestrator.py` module that owns guardrail evaluation, overload handling, semaphore lifecycle, SSE status attribution, and final request recording. Keep request models plus `EventSourceResponse(...)` in `server/main.py`, and let the handler delegate to the orchestrator through injected dependencies.

**Tech Stack:** Python 3.12, FastAPI, pytest, asyncio, sse-starlette

---

## File Structure

- Create: `python-agent/server/generate_code_orchestrator.py`
  - Own `ImmediateResponse`, `GenerateCodeOrchestrationResult`, `_status_from_sse_event(...)`, and `orchestrate_generate_code(...)`
- Create: `python-agent/tests/test_generate_code_orchestrator.py`
  - Own focused unit-style tests for guardrail block, overload, SSE status attribution, and `finally` cleanup
- Modify: `python-agent/server/main.py`
  - Remove inline `generate_code` orchestration logic and delegate to `orchestrate_generate_code(...)`
- Modify: `python-agent/tests/test_internal_auth_and_concurrency.py`
  - Add a lightweight handler-boundary seam test for `orchestrate_generate_code`

---

### Task 1: Add Failing Orchestrator Boundary Tests

**Files:**
- Create: `python-agent/tests/test_generate_code_orchestrator.py`
- Modify: `python-agent/tests/test_internal_auth_and_concurrency.py`

- [ ] **Step 1: Add the import seam test to `python-agent/tests/test_internal_auth_and_concurrency.py`**

Add this test directly after `test_main_imports_register_routes(...)`:

```python
def test_generate_code_delegates_to_orchestrator_boundary(monkeypatch):
    sys.modules.pop("server.main", None)
    fake_orchestrator = types.ModuleType("server.generate_code_orchestrator")

    async def fake_orchestrate_generate_code(request, **kwargs):
        return types.SimpleNamespace(
            immediate_response=types.SimpleNamespace(
                body={"status": "from-fake-orchestrator", "request_id": request.request_id},
                status_code=418,
            ),
            event_generator=None,
        )

    fake_orchestrator.orchestrate_generate_code = fake_orchestrate_generate_code
    monkeypatch.setitem(sys.modules, "server.generate_code_orchestrator", fake_orchestrator)
    main = load_main(monkeypatch, token="secret", max_concurrent="1")
    asyncio.run(main.agent_semaphore.acquire())
    try:
        response = asyncio.run(main.generate_code(main.CodeGenRequest(prompt="hello", requestId="req-seam")))
    finally:
        if main.agent_semaphore.locked():
            main.agent_semaphore.release()

    assert response.status_code == 418
    assert json.loads(response.body) == {
        "status": "from-fake-orchestrator",
        "request_id": "req-seam",
    }
```

- [ ] **Step 2: Create `python-agent/tests/test_generate_code_orchestrator.py` with focused failing tests**

Create this file:

```python
import asyncio
import json
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


pytestmark = [pytest.mark.harness]


class _FakeSemaphore:
    def __init__(self, *, locked=False):
        self._locked = locked
        self.acquire_calls = 0
        self.release_calls = 0

    def locked(self):
        return self._locked

    async def acquire(self):
        self.acquire_calls += 1
        self._locked = True

    def release(self):
        self.release_calls += 1
        self._locked = False


class _FakeMetric:
    def __init__(self):
        self.inc_calls = 0
        self.dec_calls = 0

    def inc(self):
        self.inc_calls += 1

    def dec(self):
        self.dec_calls += 1


def _request(**overrides):
    data = {
        "prompt": "hello",
        "user_id": "user-1",
        "app_id": "app-1",
        "code_gen_type": "VUE_PROJECT",
        "user_role": "user",
        "request_id": "req-1",
        "trace_id": "",
        "history": [],
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _logger():
    return SimpleNamespace(info=lambda *args, **kwargs: None)


async def _collect_events(async_iterable):
    events = []
    async for event in async_iterable:
        events.append(event)
    return events


async def _drain_events(async_iterable):
    async for _ in async_iterable:
        pass


def test_orchestrate_generate_code_blocks_guardrail_without_workflow(monkeypatch):
    import server.generate_code_orchestrator as orchestrator

    decision = SimpleNamespace(action="block", rule_id="prompt.secret", message="blocked")
    monkeypatch.setattr(orchestrator.config, "GUARDRAILS_ENABLED", True)
    monkeypatch.setattr(orchestrator, "resolve_trace_id", lambda trace_id: "trace-block")
    monkeypatch.setattr(orchestrator, "set_current_trace_id", lambda trace_id: None)
    monkeypatch.setattr(orchestrator, "evaluate_prompt", lambda context: decision)
    monkeypatch.setattr(orchestrator, "audit_from_decision", lambda *args, **kwargs: None)

    semaphore = _FakeSemaphore()
    metric = _FakeMetric()
    recorded = []

    async def fake_stream_workflow(**kwargs):
        raise AssertionError("workflow should not run for blocked prompts")
        yield

    result = asyncio.run(
        orchestrator.orchestrate_generate_code(
            _request(prompt="Please read .env", request_id="req-block"),
            semaphore=semaphore,
            stream_workflow=fake_stream_workflow,
            record_request=lambda user_id, app_id, code_gen_type, status: recorded.append(status),
            active_requests_metric=metric,
            logger=_logger(),
        )
    )

    assert result.immediate_response is not None
    assert result.immediate_response.status_code == 400
    assert result.immediate_response.body["status"] == "guardrail_blocked"
    assert result.event_generator is None
    assert recorded == ["guardrail_blocked"]
    assert semaphore.acquire_calls == 0
    assert semaphore.release_calls == 0
    assert metric.inc_calls == 0
    assert metric.dec_calls == 0


def test_orchestrate_generate_code_returns_overload_without_acquiring_permit(monkeypatch):
    import server.generate_code_orchestrator as orchestrator

    monkeypatch.setattr(orchestrator.config, "GUARDRAILS_ENABLED", False)
    monkeypatch.setattr(orchestrator.config, "AGENT_OVERLOAD_STATUS_CODE", 503)
    monkeypatch.setattr(orchestrator, "resolve_trace_id", lambda trace_id: "trace-overload")
    monkeypatch.setattr(orchestrator, "set_current_trace_id", lambda trace_id: None)

    semaphore = _FakeSemaphore(locked=True)
    metric = _FakeMetric()
    recorded = []

    async def fake_stream_workflow(**kwargs):
        raise AssertionError("workflow should not run when overloaded")
        yield

    result = asyncio.run(
        orchestrator.orchestrate_generate_code(
            _request(request_id="req-overload"),
            semaphore=semaphore,
            stream_workflow=fake_stream_workflow,
            record_request=lambda user_id, app_id, code_gen_type, status: recorded.append(status),
            active_requests_metric=metric,
            logger=_logger(),
        )
    )

    assert result.immediate_response is not None
    assert result.immediate_response.status_code == 503
    assert result.immediate_response.body["status"] == "overloaded"
    assert result.event_generator is None
    assert recorded == ["overloaded"]
    assert semaphore.acquire_calls == 0
    assert semaphore.release_calls == 0
    assert metric.inc_calls == 0
    assert metric.dec_calls == 0


def test_orchestrate_generate_code_records_error_event_status_and_releases_permit(monkeypatch):
    import server.generate_code_orchestrator as orchestrator

    monkeypatch.setattr(orchestrator.config, "GUARDRAILS_ENABLED", False)
    monkeypatch.setattr(orchestrator, "resolve_trace_id", lambda trace_id: "trace-error")
    monkeypatch.setattr(orchestrator, "set_current_trace_id", lambda trace_id: None)

    semaphore = _FakeSemaphore()
    metric = _FakeMetric()
    recorded = []

    async def fake_stream_workflow(**kwargs):
        yield json.dumps({"type": "error", "status": "overloaded", "request_id": kwargs["request_id"]})
        yield json.dumps({"type": "done", "status": "failed", "request_id": kwargs["request_id"]})

    result = asyncio.run(
        orchestrator.orchestrate_generate_code(
            _request(request_id="req-error"),
            semaphore=semaphore,
            stream_workflow=fake_stream_workflow,
            record_request=lambda user_id, app_id, code_gen_type, status: recorded.append(status),
            active_requests_metric=metric,
            logger=_logger(),
        )
    )

    assert result.event_generator is not None
    events = asyncio.run(_collect_events(result.event_generator))

    assert len(events) == 2
    assert recorded == ["overloaded"]
    assert semaphore.acquire_calls == 1
    assert semaphore.release_calls == 1
    assert metric.inc_calls == 1
    assert metric.dec_calls == 1


def test_orchestrate_generate_code_records_partial_success_done_event(monkeypatch):
    import server.generate_code_orchestrator as orchestrator

    monkeypatch.setattr(orchestrator.config, "GUARDRAILS_ENABLED", False)
    monkeypatch.setattr(orchestrator, "resolve_trace_id", lambda trace_id: "trace-partial")
    monkeypatch.setattr(orchestrator, "set_current_trace_id", lambda trace_id: None)

    semaphore = _FakeSemaphore()
    metric = _FakeMetric()
    recorded = []

    async def fake_stream_workflow(**kwargs):
        assert kwargs["trace_id"] == "trace-partial"
        assert kwargs["request_id"] == "req-partial"
        yield json.dumps({"type": "done", "status": "partial_success", "request_id": kwargs["request_id"]})

    result = asyncio.run(
        orchestrator.orchestrate_generate_code(
            _request(request_id="req-partial"),
            semaphore=semaphore,
            stream_workflow=fake_stream_workflow,
            record_request=lambda user_id, app_id, code_gen_type, status: recorded.append(status),
            active_requests_metric=metric,
            logger=_logger(),
        )
    )

    assert result.event_generator is not None
    events = asyncio.run(_collect_events(result.event_generator))

    assert events == [{"data": json.dumps({"type": "done", "status": "partial_success", "request_id": "req-partial"})}]
    assert recorded == ["partial_success"]
    assert semaphore.acquire_calls == 1
    assert semaphore.release_calls == 1
    assert metric.inc_calls == 1
    assert metric.dec_calls == 1


def test_orchestrate_generate_code_records_error_and_releases_permit_when_stream_raises(monkeypatch):
    import server.generate_code_orchestrator as orchestrator

    monkeypatch.setattr(orchestrator.config, "GUARDRAILS_ENABLED", False)
    monkeypatch.setattr(orchestrator, "resolve_trace_id", lambda trace_id: "trace-exception")
    monkeypatch.setattr(orchestrator, "set_current_trace_id", lambda trace_id: None)

    semaphore = _FakeSemaphore()
    metric = _FakeMetric()
    recorded = []

    async def fake_stream_workflow(**kwargs):
        raise RuntimeError("boom")
        yield

    result = asyncio.run(
        orchestrator.orchestrate_generate_code(
            _request(request_id="req-exception"),
            semaphore=semaphore,
            stream_workflow=fake_stream_workflow,
            record_request=lambda user_id, app_id, code_gen_type, status: recorded.append(status),
            active_requests_metric=metric,
            logger=_logger(),
        )
    )

    assert result.event_generator is not None
    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(_drain_events(result.event_generator))

    assert recorded == ["error"]
    assert semaphore.acquire_calls == 1
    assert semaphore.release_calls == 1
    assert metric.inc_calls == 1
    assert metric.dec_calls == 1
```

- [ ] **Step 3: Run the seam test and the first orchestrator test to verify they fail first**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_internal_auth_and_concurrency.py::test_generate_code_delegates_to_orchestrator_boundary tests/test_generate_code_orchestrator.py::test_orchestrate_generate_code_blocks_guardrail_without_workflow -v
```

Expected:

- `test_generate_code_delegates_to_orchestrator_boundary` fails because `server.main.generate_code(...)` still owns the orchestration path
- `test_orchestrate_generate_code_blocks_guardrail_without_workflow` fails because `server.generate_code_orchestrator` does not exist yet

---

### Task 2: Implement the Orchestrator and Thin the Handler

**Files:**
- Create: `python-agent/server/generate_code_orchestrator.py`
- Modify: `python-agent/server/main.py`
- Modify: `python-agent/tests/test_internal_auth_and_concurrency.py`
- Test: `python-agent/tests/test_generate_code_orchestrator.py`
- Test: `python-agent/tests/test_internal_auth_and_concurrency.py`

- [ ] **Step 1: Create `python-agent/server/generate_code_orchestrator.py`**

Create this file:

```python
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from logging import Logger
from typing import Any

from config import config
from guardrails.audit import audit_from_decision
from guardrails.engine import evaluate_prompt
from guardrails.models import PromptContext
from tracing import resolve_trace_id, set_current_trace_id


@dataclass(slots=True)
class ImmediateResponse:
    body: dict[str, Any]
    status_code: int


@dataclass(slots=True)
class GenerateCodeOrchestrationResult:
    immediate_response: ImmediateResponse | None = None
    event_generator: AsyncIterator[dict[str, str]] | None = None


def _status_from_sse_event(event: str) -> str | None:
    try:
        payload = json.loads(event)
    except (TypeError, ValueError):
        return None

    event_type = payload.get("type")
    status = payload.get("status")
    if event_type == "error":
        return str(status or "error")
    if event_type == "done" and status and status != "success":
        return str(status)
    return None


def _guardrail_block_response(request, *, resolved_trace_id: str, prompt_decision) -> ImmediateResponse:
    return ImmediateResponse(
        body={
            "type": "error",
            "status": "guardrail_blocked",
            "rule_id": prompt_decision.rule_id,
            "message": prompt_decision.message,
            "request_id": request.request_id,
            "trace_id": resolved_trace_id,
        },
        status_code=400,
    )


def _overload_response(request, *, resolved_trace_id: str) -> ImmediateResponse:
    return ImmediateResponse(
        body={
            "type": "error",
            "status": "overloaded",
            "message": "AI Agent capacity is full. Please retry later.",
            "request_id": request.request_id,
            "trace_id": resolved_trace_id,
        },
        status_code=config.AGENT_OVERLOAD_STATUS_CODE,
    )


async def orchestrate_generate_code(
    request,
    *,
    semaphore,
    stream_workflow: Callable[..., AsyncIterator[str]],
    record_request,
    active_requests_metric,
    logger: Logger,
) -> GenerateCodeOrchestrationResult:
    resolved_trace_id = resolve_trace_id(request.trace_id)
    set_current_trace_id(resolved_trace_id)

    if config.GUARDRAILS_ENABLED:
        prompt_decision = evaluate_prompt(
            PromptContext(
                prompt=request.prompt,
                request_id=request.request_id,
                trace_id=resolved_trace_id,
                user_id=request.user_id,
                app_id=request.app_id,
                history=request.history,
            )
        )
        audit_from_decision(
            prompt_decision,
            request_id=request.request_id,
            trace_id=resolved_trace_id,
            user_id=request.user_id,
            app_id=request.app_id,
        )
        if prompt_decision.action == "block":
            record_request(request.user_id, request.app_id, request.code_gen_type, "guardrail_blocked")
            return GenerateCodeOrchestrationResult(
                immediate_response=_guardrail_block_response(
                    request,
                    resolved_trace_id=resolved_trace_id,
                    prompt_decision=prompt_decision,
                )
            )

    if semaphore.locked():
        record_request(request.user_id, request.app_id, request.code_gen_type, "overloaded")
        return GenerateCodeOrchestrationResult(
            immediate_response=_overload_response(
                request,
                resolved_trace_id=resolved_trace_id,
            )
        )

    await semaphore.acquire()
    active_requests_metric.inc()
    logger.info(
        f"Received code generation request: user={request.user_id}, app={request.app_id}, "
        f"request_id={request.request_id}, trace_id={resolved_trace_id}, prompt={request.prompt[:60]}..."
    )

    async def event_generator():
        status = "success"
        try:
            async for event in stream_workflow(
                user_request=request.prompt,
                user_id=request.user_id,
                app_id=request.app_id,
                code_gen_type=request.code_gen_type,
                user_role=request.user_role,
                trace_id=resolved_trace_id,
                request_id=request.request_id,
            ):
                event_status = _status_from_sse_event(event)
                if event_status and status == "success":
                    status = event_status
                yield {"data": event}
        except Exception:
            status = "error"
            raise
        finally:
            active_requests_metric.dec()
            record_request(request.user_id, request.app_id, request.code_gen_type, status)
            semaphore.release()

    return GenerateCodeOrchestrationResult(event_generator=event_generator())
```

- [ ] **Step 2: Update `python-agent/server/main.py` to delegate to the orchestrator**

Make these edits:

1. Remove these imports:

```python
import json
from guardrails.audit import audit_from_decision
from guardrails.engine import evaluate_prompt
from guardrails.models import PromptContext
```

2. Add this import:

```python
from server.generate_code_orchestrator import orchestrate_generate_code
```

3. Remove the inline helper:

```python
def _status_from_sse_event(event: str) -> str | None:
    ...
```

4. Replace the `generate_code(...)` body with this:

```python
async def generate_code(request: CodeGenRequest):
    """SSE code generation endpoint."""
    result = await orchestrate_generate_code(
        request,
        semaphore=agent_semaphore,
        stream_workflow=stream_workflow,
        record_request=record_request,
        active_requests_metric=ai_code_gen_active_requests,
        logger=logger,
    )

    if result.immediate_response is not None:
        return JSONResponse(
            result.immediate_response.body,
            status_code=result.immediate_response.status_code,
        )

    if result.event_generator is None:
        raise RuntimeError("generate_code orchestration returned no response path")

    return EventSourceResponse(result.event_generator)
```

- [ ] **Step 3: Run the new seam test plus the full orchestrator unit suite**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_internal_auth_and_concurrency.py::test_generate_code_delegates_to_orchestrator_boundary tests/test_generate_code_orchestrator.py -v
```

Expected: PASS.

- [ ] **Step 4: Run the existing `internal_auth_and_concurrency` suite**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_internal_auth_and_concurrency.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit the orchestrator extraction**

```bash
git add python-agent/server/generate_code_orchestrator.py python-agent/server/main.py python-agent/tests/test_generate_code_orchestrator.py python-agent/tests/test_internal_auth_and_concurrency.py
git commit -m "refactor: extract generate code orchestrator"
```

---

### Task 3: Run Focused Regression and Harness Verification

**Files:**
- Test: `python-agent/tests/test_generate_code_orchestrator.py`
- Test: `python-agent/tests/test_internal_auth_and_concurrency.py`
- Test: `python-agent/tests/test_tracing.py`

- [ ] **Step 1: Run tracing plus server-boundary verification together**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_generate_code_orchestrator.py tests/test_tracing.py tests/test_internal_auth_and_concurrency.py -v
```

Expected: PASS.

- [ ] **Step 2: Run the canonical harness verification**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest -m harness -v
```

Expected: PASS.

- [ ] **Step 3: Commit the verified regression state if the previous task commit did not already capture it**

```bash
git add python-agent/server/generate_code_orchestrator.py python-agent/server/main.py python-agent/tests/test_generate_code_orchestrator.py python-agent/tests/test_internal_auth_and_concurrency.py
git commit -m "test: verify generate code orchestrator extraction"
```

Only create this commit if verification required follow-up edits after Task 2.

---

## Plan Self-Review

- Spec coverage: the plan covers the new orchestrator module, the thin-handler main-module integration, the import seam check, focused orchestrator unit tests, focused tracing/internal-auth regression, and harness verification.
- Placeholder scan: no `TBD`, `TODO`, vague “add error handling”, or “similar to previous task” instructions remain; each code-changing step includes concrete code.
- Type consistency: the plan consistently uses `ImmediateResponse`, `GenerateCodeOrchestrationResult`, `event_generator`, and `orchestrate_generate_code(...)` across implementation and tests.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-02-generate-code-orchestrator.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
