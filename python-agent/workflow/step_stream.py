"""Poll durable step events while LangGraph is waiting for a sync Coder node."""
import asyncio


async def states_with_steps(source, session):
    iterator = source.__aiter__()
    pending = None
    cursor = 0
    try:
        pending = asyncio.create_task(anext(iterator))
        while True:
            page = await asyncio.to_thread(session.store.public_events, session.run_id, session.user_id, session.app_id, cursor, 100)
            if page['events']:
                cursor = page['step_cursor']
                yield {'__harness_events__': page['events']}
            if page['has_more']:
                continue
            done, _ = await asyncio.wait({pending}, timeout=0.25)
            if not done:
                continue
            try:
                state = pending.result()
            except StopAsyncIteration:
                break
            while True:
                page = await asyncio.to_thread(session.store.public_events, session.run_id, session.user_id, session.app_id, cursor, 100)
                if page['events']:
                    cursor = page['step_cursor']
                    yield {'__harness_events__': page['events']}
                if not page['has_more']:
                    break
            yield state
            pending = asyncio.create_task(anext(iterator))
    finally:
        if pending and not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        await iterator.aclose()
