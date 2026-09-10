"""Keep execution ownership when an SSE client disconnects during a sync node."""
import asyncio
from contextlib import aclosing

_producers: set[asyncio.Task] = set()


async def detached_stream(source, request_pause):
    queue = asyncio.Queue(maxsize=64)
    disconnected = False
    pause_recorded = False
    exhausted = False

    def pause_if_disconnected():
        nonlocal pause_recorded
        if disconnected and not pause_recorded:
            pause_recorded = request_pause()

    async def deliver(kind, value=None):
        pause_if_disconnected()
        if not disconnected:
            await queue.put((kind, value))

    async def produce():
        try:
            async with aclosing(source):
                async for event in source:
                    await deliver("event", event)
        except Exception as exc:
            await deliver("error", exc)
        finally:
            await deliver("end")

    task = asyncio.create_task(produce(), name="generation-producer")
    _producers.add(task)
    task.add_done_callback(_producers.discard)
    try:
        while True:
            kind, value = await queue.get()
            if kind == "end":
                exhausted = True
                break
            if kind == "error":
                raise value
            yield value
    finally:
        if not exhausted:
            # Do not cancel to_thread/model/build execution. Producer owns its
            # semaphore and app lock until the next checkpoint gate has paused.
            disconnected = True
            pause_if_disconnected()
            while not queue.empty():
                queue.get_nowait()
