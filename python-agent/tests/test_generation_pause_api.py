import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_production_stream_pause_resume_replays_files(monkeypatch, tmp_path, fake_conversation_memory):
    from langgraph.graph import StateGraph, END
    from state.code_gen_state import CodeGenState
    from workflow import code_gen_workflow, sse_stream
    from workflow.run_control import RunStore
    import config

    monkeypatch.setattr(config.config, "CHECKPOINT_DB_PATH", str(tmp_path / "checkpoints.db"))
    monkeypatch.setattr(sse_stream, "conversation_memory", fake_conversation_memory)
    calls = []

    def factory(session):
        graph = StateGraph(CodeGenState)

        def code(state):
            calls.append("code")
            session.store.pause("api-run", "u", "a")
            return {"phase": "code_done", "code_files": [{"path": "index.html", "content": "hello"}]}

        def review(state):
            calls.append("review")
            return {"phase": "completed", "final_result": {"status": "success"}}

        graph.add_node("code", code)
        graph.add_node("gate", session.pause_gate)
        graph.add_node("review", review)
        graph.set_entry_point("code")
        graph.add_edge("code", "gate")
        graph.add_edge("gate", "review")
        graph.add_edge("review", END)
        return graph

    monkeypatch.setattr(code_gen_workflow, "create_code_gen_workflow", factory)

    async def run():
        first = [json.loads(e) async for e in sse_stream.stream_persistent_workflow(
            "original", "u", "a", request_id="api-run")]
        assert first[-1]["status"] == "paused", first
        assert not any(e.get("status") == "success" for e in first)
        assert calls == ["code"]
        second = [json.loads(e) async for e in sse_stream.stream_persistent_workflow(
            "", "u", "a", request_id="api-run", resume=True)]
        assert second[-1]["status"] == "success", second
        assert any(e["type"] == "code_file" and e["content"] == "hello" for e in second)
        assert calls == ["code", "review"]
        assert RunStore(config.config.CHECKPOINT_DB_PATH).get("api-run", "u", "a")["status"] == "completed"

    asyncio.run(run())


def test_resume_http_forwards_original_identity(monkeypatch):
    from fastapi.testclient import TestClient
    from server import main
    captured = []

    async def fake_stream(**kwargs):
        captured.append(kwargs)
        yield json.dumps({"type": "done", "status": "paused"})

    monkeypatch.setattr(main._config(), "INTERNAL_API_TOKEN", "test-token")
    monkeypatch.setattr(main, "stream_workflow", fake_stream)
    client = TestClient(main.app)
    response = client.post("/api/generate-code", headers={"X-Internal-Token": "test-token"},
                           json={"userId": "u", "appId": "a", "prompt": "", "requestId": "r", "resume": True})
    assert response.status_code == 200
    assert captured[0]["resume"] is True
    assert captured[0]["request_id"] == "r"


def test_control_http_auth_and_owner(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from server import main
    from workflow.run_control import RunStore
    monkeypatch.setattr(main._config(), "INTERNAL_API_TOKEN", "test-token")
    monkeypatch.setattr(main._config(), "CHECKPOINT_DB_PATH", str(tmp_path / "cp.db"))
    store = RunStore(main._config().CHECKPOINT_DB_PATH)
    store.create("r", "u", "a", {})
    store.update_status("r", "paused")
    client = TestClient(main.app)
    body = {"runId": "r", "userId": "u", "appId": "a"}
    assert client.post("/api/generation/pause", json=body).status_code == 401
    headers = {"X-Internal-Token": "test-token"}
    assert client.post("/api/generation/status", json={**body, "userId": "other"}, headers=headers).status_code == 404
    assert client.post("/api/generation/pause", json=body, headers=headers).json()["status"] == "paused"


def test_output_rejection_does_not_leave_unresumable_pending_run(monkeypatch, tmp_path, fake_conversation_memory):
    from types import SimpleNamespace
    from langgraph.graph import StateGraph, END
    from state.code_gen_state import CodeGenState
    from workflow import code_gen_workflow, sse_stream
    from workflow.run_control import RunStore
    import config
    monkeypatch.setattr(config.config, "CHECKPOINT_DB_PATH", str(tmp_path / "cp.db"))
    monkeypatch.setattr(sse_stream, "conversation_memory", fake_conversation_memory)
    monkeypatch.setattr(sse_stream, "evaluate_output_event", lambda _: SimpleNamespace(action="block", rule_id="test", message="blocked"))
    monkeypatch.setattr(sse_stream, "audit_from_decision", lambda *args, **kwargs: None)

    def factory(session):
        graph = StateGraph(CodeGenState)
        graph.add_node("code", lambda state: {"phase": "code_done", "code_files": [{"path": "a.html", "content": "rejected"}]})
        graph.set_entry_point("code")
        graph.add_edge("code", END)
        return graph

    monkeypatch.setattr(code_gen_workflow, "create_code_gen_workflow", factory)

    async def run():
        events = [json.loads(e) async for e in sse_stream.stream_persistent_workflow("hi", "u", "a", request_id="blocked")]
        assert events[-1]["status"] == "guardrail_blocked"
        store = RunStore(config.config.CHECKPOINT_DB_PATH)
        assert store.get("blocked", "u", "a")["status"] == "failed"
        store.create("next-run", "u", "a", {})

    asyncio.run(run())
