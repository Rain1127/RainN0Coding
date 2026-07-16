import asyncio
import os
import sys
from contextlib import contextmanager

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


pytestmark = [pytest.mark.integration, pytest.mark.harness]


def test_output_guard_blocks_protected_path_code_file():
    from guardrails.engine import evaluate_output_event
    from guardrails.models import OutputEvent

    decision = evaluate_output_event(
        OutputEvent(event_type="code_file", path=".env", content="SECRET=1", request_id="req-1", trace_id="trace-1")
    )

    assert decision.action == "block"
    assert decision.rule_id == "output.protected_path_blocked"


@pytest.mark.parametrize("path", ["src/js/main.js", "src/main.ts", "src/App.vue"])
def test_output_guard_allows_generated_project_entrypoints(path):
    from guardrails.engine import evaluate_output_event
    from guardrails.models import OutputEvent

    decision = evaluate_output_event(
        OutputEvent(
            event_type="code_file",
            path=path,
            content="export default {}",
            request_id="req-entry",
            trace_id="trace-entry",
        )
    )

    assert decision.action == "allow"
    assert decision.rule_id == "output.ok"


def test_output_guard_blocks_oversize_code_file():
    from guardrails.engine import evaluate_output_event
    from guardrails.models import OutputEvent

    decision = evaluate_output_event(
        OutputEvent(
            event_type="code_file",
            path="src/pages/dashboard.ts",
            content="A" * 250000,
            request_id="req-2",
            trace_id="trace-2",
        )
    )

    assert decision.action == "block"
    assert decision.rule_id == "output.oversize_code_file_blocked"


def test_stream_workflow_emits_guardrail_blocked_for_protected_output(
    monkeypatch, fake_conversation_memory, collect_json_events
):
    import workflow.sse_stream as sse_stream

    @contextmanager
    def fake_start_span(*args, **kwargs):
        yield

    async def fake_run_workflow_async(*args, **kwargs):
        yield {
            "phase": "code_done",
            "code_files": [{"path": ".env", "content": "SECRET=1"}],
            "retry_count": 0,
        }

    monkeypatch.setattr(sse_stream, "start_span", fake_start_span)
    monkeypatch.setattr(sse_stream, "conversation_memory", fake_conversation_memory)
    monkeypatch.setattr(sse_stream, "run_workflow_async", fake_run_workflow_async)

    events = asyncio.run(
        collect_json_events(
            sse_stream.stream_workflow("hello", request_id="req-out", trace_id="trace-out")
        )
    )

    assert any(
        event["type"] == "error"
        and event["status"] == "guardrail_blocked"
        and event["rule_id"] == "output.protected_path_blocked"
        for event in events
    )
    assert events[-1]["type"] == "done"
    assert events[-1]["status"] == "guardrail_blocked"
