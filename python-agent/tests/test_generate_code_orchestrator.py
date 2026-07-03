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
