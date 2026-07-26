import asyncio
import json

from workflow import sse_stream


def test_initial_progress_events_preserve_chinese_text(monkeypatch):
    monkeypatch.setattr(
        sse_stream.conversation_memory,
        "get_context",
        lambda _thread_id: {"summary": "", "recent_messages": []},
    )

    async def fake_run_workflow_async(*_args, **_kwargs):
        yield {"phase": "mode_detected", "mode": "new", "retry_count": 0}

    monkeypatch.setattr(sse_stream, "run_workflow_async", fake_run_workflow_async)

    async def collect_events():
        return [
            json.loads(event)
            async for event in sse_stream.stream_workflow(
                "创建一个运营数据看板",
                user_id="test-user",
                app_id="test-app",
            )
        ]

    events = asyncio.run(collect_events())

    assert [event["message"] for event in events] == [
        "开始处理需求: 创建一个运营数据看板",
        "正在理解你的需求...",
        "正在启动全新代码生成...",
    ]
