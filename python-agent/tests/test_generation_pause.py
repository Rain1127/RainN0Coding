"""Real LangGraph/checkpoint tests; no LLM, Redis or application database."""
import asyncio
import importlib.util
from pathlib import Path
import sys
import subprocess

import pytest
from langgraph.graph import StateGraph, END
from typing import TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_persistent_run_control_exists():
    assert importlib.util.find_spec("workflow.run_control") is not None


class State(TypedDict, total=False):
    step: int


def graph(session, calls):
    wf = StateGraph(State)

    def first(state):
        calls.append("first")
        session.store.pause("r1", "u", "a")
        return {"step": 1}

    def second(state):
        calls.append("second")
        return {"step": 2}

    wf.add_node("first", first)
    wf.add_node("gate", session.pause_gate)
    wf.add_node("second", second)
    wf.set_entry_point("first")
    wf.add_edge("first", "gate")
    wf.add_edge("gate", "second")
    wf.add_edge("second", END)
    return wf


def test_pause_reopen_resume_preserves_completed_node(tmp_path):
    from workflow.run_control import RunStore, RunSession, RunControlError
    path = tmp_path / "checkpoint.db"
    calls = []

    async def start():
        store = RunStore(path)
        async with RunSession(store, "r1", "u", "a", payload={"prompt": "original"}) as session:
            states = [s async for s in session.states(graph(session, calls), {"step": 0})]
        assert states[-1]["__paused__"] is True
        assert store.get("r1", "u", "a")["status"] == "paused"
        assert calls == ["first"]
        with pytest.raises(RunControlError):
            store.pause("r1", "someone_else", "a")

    async def resume():
        store = RunStore(path)
        async with RunSession(store, "r1", "u", "a", resume=True) as session:
            assert session.payload["prompt"] == "original"
            states = [s async for s in session.states(graph(session, calls), None)]
        assert states[-1] == {"step": 2}
        assert calls == ["first", "second"]
        assert store.get("r1", "u", "a")["status"] == "completed"
        with pytest.raises(RunControlError):
            async with RunSession(store, "r1", "u", "a", resume=True):
                pass

    asyncio.run(start())
    asyncio.run(resume())


def test_duplicate_execution_and_new_run_while_paused_rejected(tmp_path):
    from workflow.run_control import RunStore, RunSession, RunControlError

    async def run():
        store = RunStore(tmp_path / "checkpoint.db")
        async with RunSession(store, "r1", "u", "a") as session:
            with pytest.raises(RunControlError):
                async with RunSession(store, "r1", "u", "a", resume=True):
                    pass
            assert store.pause("r1", "u", "a")["status"] == "pausing"
            assert store.pause("r1", "u", "a")["status"] == "pausing"
            _ = [s async for s in session.states(graph(session, []), {})]
        with pytest.raises(RunControlError):
            async with RunSession(store, "r2", "u", "a"):
                pass

    asyncio.run(run())


def test_timed_out_worker_retains_app_lock_until_it_finishes(tmp_path, monkeypatch):
    import threading
    from workflow.run_control import RunStore, RunSession, RunControlError
    from workflow import resilience
    monkeypatch.setattr(resilience, "phase_timeout_seconds", lambda *args: 0.02)
    release = threading.Event()
    timed_out = asyncio.Event()

    async def run():
        store = RunStore(tmp_path / "timeout.db")

        async def execute():
            async with RunSession(store, "r", "u", "a"):
                with pytest.raises(TimeoutError):
                    await resilience._run_phase_runner("coder", {}, lambda state: release.wait(5))
                timed_out.set()

        task = asyncio.create_task(execute())
        try:
            await asyncio.wait_for(timed_out.wait(), timeout=3)
            with pytest.raises(RunControlError):
                with store.execution_lock("a"):
                    pass
            assert not task.done()
        finally:
            release.set()
            await task

    asyncio.run(run())


def test_checkpoint_survives_a_new_python_process(tmp_path):
    script = '''
import asyncio, sys
from typing import TypedDict
from pathlib import Path
from langgraph.graph import StateGraph, END
from workflow.run_control import RunStore, RunSession
class State(TypedDict, total=False):
    count: int
async def run():
    store = RunStore(sys.argv[1])
    calls = Path(sys.argv[1] + '.calls')
    async with RunSession(store, 'r1', 'u', 'a', resume=sys.argv[2]=='resume') as session:
        def first(state):
            with calls.open('a') as f: f.write('first\\n')
            store.pause('r1', 'u', 'a')
            return {'count': 1}
        def second(state):
            with calls.open('a') as f: f.write('second\\n')
            return {'count': 2}
        graph = StateGraph(State)
        graph.add_node('first', first)
        graph.add_node('gate', session.pause_gate)
        graph.add_node('second', second)
        graph.set_entry_point('first')
        graph.add_edge('first', 'gate')
        graph.add_edge('gate', 'second')
        graph.add_edge('second', END)
        states = [state async for state in session.states(graph, {'count': 0})]
    assert store.get('r1','u','a')['status'] == ('completed' if sys.argv[2]=='resume' else 'paused')
asyncio.run(run())
'''
    import os
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
    path = str(tmp_path / "cross_process.db")
    for mode in ("start", "resume"):
        result = subprocess.run([sys.executable, "-c", script, path, mode], env=env,
                                capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
    assert Path(path + ".calls").read_text().splitlines() == ["first", "second"]


def test_disconnect_keeps_execution_lock_until_sync_node_checkpoints(tmp_path):
    import threading
    from server.generation_stream_transport import detached_stream, _producers
    from workflow.run_control import RunStore, RunSession, RunControlError
    started, release = threading.Event(), threading.Event()

    async def run():
        store = RunStore(tmp_path / "disconnect.db")

        async def source():
            async with RunSession(store, "r", "u", "a") as session:
                yield "started"
                graph = StateGraph(State)

                async def worker(state):
                    def blocking():
                        started.set()
                        assert release.wait(10)
                        return {"step": 1}
                    return await asyncio.to_thread(blocking)

                graph.add_node("worker", worker)
                graph.add_node("gate", session.pause_gate)
                graph.set_entry_point("worker")
                graph.add_edge("worker", "gate")
                graph.add_edge("gate", END)
                async for state in session.states(graph, {}):
                    yield state

        def pause():
            store.pause("r", "u", "a")
            return True

        stream = detached_stream(source(), pause)
        assert await anext(stream) == "started"
        try:
            assert await asyncio.to_thread(started.wait, 5)
            await stream.aclose()
            with pytest.raises(RunControlError):
                with store.execution_lock("a"):
                    pass
            assert store.get("r", "u", "a")["status"] == "pausing"
        finally:
            release.set()
            await asyncio.wait_for(asyncio.gather(*list(_producers)), timeout=10)
        assert store.get("r", "u", "a")["status"] == "paused"
        with store.execution_lock("a"):
            pass

    asyncio.run(run())
