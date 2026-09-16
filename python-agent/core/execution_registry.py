"""Process-local execution occupancy, including workers surviving SSE cancellation.

Deploy one Python worker: a probe of another process cannot see this registry.
Process exit removes its threads, but this registry does not establish termination
of detached subprocesses or remote model requests. Service shutdown must reap its
process group before a replacement process can safely report the app idle.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import copy_context
from threading import Lock


class ExecutionRegistry:
    def __init__(self):
        self._lock = Lock()
        self._counts: dict[str, int] = {}

    def acquire(self, app_id: str):
        """Reserve occupancy before dispatch; return an idempotent release."""
        key = str(app_id)
        with self._lock:
            self._counts[key] = self._counts.get(key, 0) + 1
        released = False

        def release():
            nonlocal released
            with self._lock:
                if released:
                    return
                released = True
                remaining = self._counts[key] - 1
                if remaining:
                    self._counts[key] = remaining
                else:
                    del self._counts[key]

        return release

    @contextmanager
    def track(self, app_id: str):
        release = self.acquire(app_id)
        try:
            yield
        finally:
            release()

    def is_busy(self, app_id: str) -> bool:
        with self._lock:
            return self._counts.get(str(app_id), 0) > 0

    async def run_sync(self, app_id: str, runner, state):
        """Cancellation stops waiting, never releases a queued/running worker."""
        release = self.acquire(app_id)
        context = copy_context()

        def worker():
            try:
                return context.run(runner, state)
            finally:
                release()

        try:
            # Submit immediately. Shield prevents cancellation of queued executor
            # work, so every accepted submission eventually runs its finally.
            future = asyncio.get_running_loop().run_in_executor(None, worker)
        except BaseException:
            release()
            raise

        # A disconnected caller will not retrieve a late worker exception.
        future.add_done_callback(lambda done: None if done.cancelled() else done.exception())
        return await asyncio.shield(future)


execution_registry = ExecutionRegistry()
