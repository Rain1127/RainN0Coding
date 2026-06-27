"""SSE 流式输出验证"""
import sys, os, json, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from workflow.sse_stream import stream_workflow

async def test():
    count = 0
    async for event_str in stream_workflow("做一个简单的导航栏", "test", "sse-test"):
        event = json.loads(event_str)
        etype = event["type"]
        if etype == "workflow_start":
            print(f"[START] {event.get('message', '')}")
        elif etype == "phase_complete":
            phase = event["phase"]
            output = event.get("output", {})
            print(f"[{phase.upper():6s}] {output}")
        elif etype == "phase_start":
            print(f"[...] {event.get('message', '')}")
        elif etype == "review_issue":
            print(f"  [ISSUE] [{event.get('severity')}] {event.get('file')}: {event.get('description', '')[:60]}")
        elif etype == "code_file":
            print(f"  [FILE] {event.get('path')} ({len(event.get('content',''))} chars)")
        elif etype == "done":
            print(f"[DONE] status={event.get('status')}")
        count += 1
    print(f"\nTotal events: {count}")

asyncio.run(test())
