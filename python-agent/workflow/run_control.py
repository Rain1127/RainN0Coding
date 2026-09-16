"""Durable run ownership and cooperative LangGraph pause/resume on one host.

The OS lock spans streaming, checkpoint writes and completion. It is released by
the kernel on process death; unlike a TTL it cannot expire during a slow LLM call.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command, interrupt

current_run: ContextVar["RunSession | None"] = ContextVar("current_generation_run", default=None)


async def run_owned_worker(runner, state):
    from core.execution_registry import execution_registry
    session = current_run.get()
    if session is None:
        return await execution_registry.run_sync(state.get("app_id", ""), runner, state)
    worker = asyncio.create_task(execution_registry.run_sync(state.get("app_id", ""), runner, state))
    session.workers.add(worker)
    # wait_for may time out the caller; the underlying OS thread still owns its
    # effects. Gates/cleanup must await it before allowing subsequent execution.
    return await asyncio.shield(worker)


class RunControlError(Exception):
    def __init__(self, message, status_code=409):
        super().__init__(message)
        self.status_code = status_code


class RunStore:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS generation_runs (
                run_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, app_id TEXT NOT NULL,
                status TEXT NOT NULL, pause_requested INTEGER NOT NULL DEFAULT 0,
                payload TEXT NOT NULL, updated_at REAL NOT NULL)""")
            db.execute("CREATE TABLE IF NOT EXISTS generation_effects "
                       "(run_id TEXT NOT NULL, effect TEXT NOT NULL, PRIMARY KEY(run_id,effect))")

    def claim_effect(self, run_id, effect):
        """At-most-once best-effort ancillary effects (conversation summaries)."""
        with self.connection() as db:
            return db.execute("INSERT OR IGNORE INTO generation_effects VALUES (?,?)",
                              (run_id, effect)).rowcount == 1

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, run_id, user_id, app_id):
        with self.connection() as db:
            row = db.execute("SELECT * FROM generation_runs WHERE run_id=? AND user_id=? AND app_id=?",
                             (run_id, user_id, app_id)).fetchone()
        if row is None:
            raise RunControlError("Generation task not found", 404)
        return dict(row)

    def create(self, run_id, user_id, app_id, payload):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            pending = db.execute("SELECT run_id FROM generation_runs WHERE app_id=? AND status NOT IN ('completed','failed')",
                                 (app_id,)).fetchone()
            if pending:
                raise RunControlError("Resume the existing unfinished generation first")
            try:
                db.execute("INSERT INTO generation_runs VALUES (?,?,?,?,?,?,?)",
                           (run_id, user_id, app_id, "running", 0, json.dumps(payload), time.time()))
            except sqlite3.IntegrityError as exc:
                raise RunControlError("Generation task already exists") from exc

    def update_status(self, run_id, status):
        with self.connection() as db:
            db.execute("UPDATE generation_runs SET status=?, updated_at=? WHERE run_id=?",
                       (status, time.time(), run_id))

    def pause(self, run_id, user_id, app_id):
        self.get(run_id, user_id, app_id)
        with self.connection() as db:
            db.execute("UPDATE generation_runs SET pause_requested=1,status='pausing',updated_at=? "
                       "WHERE run_id=? AND status IN ('running','pausing')", (time.time(), run_id))
        return self.public_status(run_id, user_id, app_id)

    def public_status(self, run_id, user_id, app_id):
        row = self.get(run_id, user_id, app_id)
        status = row["status"]
        if status in ("running", "pausing"):
            try:
                with self.execution_lock(app_id):
                    status = "interrupted"
            except RunControlError:
                pass
        return {"run_id": run_id, "status": status}

    @contextmanager
    def execution_lock(self, app_id):
        lock_dir = self.path.parent / (self.path.name + ".locks")
        lock_dir.mkdir(exist_ok=True)
        name = hashlib.sha256(app_id.encode()).hexdigest()
        handle = open(lock_dir / name, "a+b")
        acquired = False
        try:
            if os.name == "nt":
                import msvcrt
                handle.seek(0, 2)
                if handle.tell() == 0:
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError as exc:
                    raise RunControlError("Generation is already executing") from exc
            else:
                import fcntl
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise RunControlError("Generation is already executing") from exc
            acquired = True
            yield
        finally:
            if acquired:
                if os.name == "nt":
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle, fcntl.LOCK_UN)
            handle.close()


class RunSession:
    def __init__(self, store, run_id, user_id, app_id, *, resume=False, payload=None):
        self.store, self.run_id = store, run_id
        self.user_id, self.app_id = user_id, app_id
        self.resume, self.payload = resume, payload or {}
        self.finished = False
        self.workers = set()
        self.config = {"configurable": {"thread_id": json.dumps([user_id, app_id, run_id])},
                       "recursion_limit": 150}

    async def __aenter__(self):
        self.lock = self.store.execution_lock(self.app_id)
        self.lock.__enter__()
        try:
            if self.resume:
                row = self.store.get(self.run_id, self.user_id, self.app_id)
                if row["status"] in ("completed", "failed"):
                    raise RunControlError("Generation has already ended")
                self.payload = json.loads(row["payload"])
            else:
                self.store.create(self.run_id, self.user_id, self.app_id, self.payload)
            self.saver_context = AsyncSqliteSaver.from_conn_string(str(self.store.path))
            self.saver = await self.saver_context.__aenter__()
            await self.saver.setup()
        except BaseException:
            if hasattr(self, "saver"):
                await self.saver_context.__aexit__(None, None, None)
            self.lock.__exit__(None, None, None)
            raise
        self.context_token = current_run.set(self)
        return self

    async def __aexit__(self, *exc):
        try:
            await self.wait_workers()
            if not self.finished:
                self.store.update_status(self.run_id, "interrupted")
            await self.saver_context.__aexit__(*exc)
        finally:
            current_run.reset(self.context_token)
            self.lock.__exit__(*exc)

    async def wait_workers(self):
        if self.workers:
            await asyncio.gather(*self.workers, return_exceptions=True)
            self.workers.clear()

    async def pause_gate(self, state):
        await self.wait_workers()
        row = self.store.get(self.run_id, self.user_id, self.app_id)
        if row["pause_requested"]:
            # Keep the flag set until interrupt returns: on resume this node must
            # execute the same interrupt call to consume Command(resume=...).
            interrupt({"run_id": self.run_id, "reason": "user_pause"})
            with self.store.connection() as db:
                db.execute("UPDATE generation_runs SET pause_requested=0 WHERE run_id=?", (self.run_id,))
        return {"user_role": self.user_role} if hasattr(self, "user_role") else {}

    async def states(self, workflow, initial):
        graph = workflow.compile(checkpointer=self.saver)
        graph_input = initial
        if self.resume:
            checkpoint = await graph.aget_state(self.config)
            if not checkpoint.values:
                # The process may die after task creation but before graph input.
                if initial is None:
                    raise RunControlError("No checkpoint is available to resume")
            elif not checkpoint.next:
                self.store.update_status(self.run_id, "completed")
                self.finished = True
                # Re-deliver terminal output after a lost final SSE connection.
                yield checkpoint.values
                return
            else:
                graph_input = Command(resume=True) if checkpoint.interrupts else None
        self.store.update_status(self.run_id, "running")
        previous = None
        async for state in graph.astream(graph_input, self.config, stream_mode="values", durability="sync"):
            if state != previous:
                previous = state
                yield state
        await self.wait_workers()
        snapshot = await graph.aget_state(self.config)
        status = "paused" if snapshot.next else "completed"
        if status == "completed":
            final_status = (snapshot.values.get("final_result") or {}).get("status")
            if snapshot.values.get("error") or snapshot.values.get("phase") == "clarify" or (
                final_status and final_status not in ("success", "partial_success", "degraded_success")
            ):
                status = "failed"
        self.store.update_status(self.run_id, status)
        self.finished = True
        if status == "paused":
            yield {"__paused__": True}


def default_run_store():
    from config import config
    return RunStore(config.CHECKPOINT_DB_PATH)
