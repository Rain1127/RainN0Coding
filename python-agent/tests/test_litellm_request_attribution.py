import json

import openai

from memory.conversation_memory import ConversationMemory
import core.model_router as model_router_module
from rag import ragas_evaluator
from request_context import bind_request_context
from workflow import autogen_discussion


def test_conversation_summary_sends_nested_spend_metadata(monkeypatch):
    captured = {"messages": []}

    class FakeClient:
        def __init__(self, **kwargs):
            captured["client"] = kwargs

        def invoke(self, messages, config=None):
            captured["messages"].append(messages)
            return type("Response", (), {"content": "summary"})()

    monkeypatch.setattr(model_router_module, "ChatOpenAI", FakeClient)

    with bind_request_context(
        request_id="req-memory",
        trace_id="trace-memory",
        user_id="user-memory",
        app_id="app-memory",
    ):
        result = ConversationMemory()._call_llm("summarize")
        ConversationMemory()._call_llm("summarize another batch")

    assert result == "summary"
    assert captured["client"]["extra_body"]["metadata"] == {
        "user_id": "user-memory",
        "spend_logs_metadata": {
            "request_id": "req-memory",
            "trace_id": "trace-memory",
            "user_id": "user-memory",
            "app_id": "app-memory",
        },
    }
    assert captured["messages"][0][0] == captured["messages"][1][0]
    assert '"type": "object"' in captured["messages"][0][0].content
    assert captured["messages"][0][-1].content == "summarize"


def test_autogen_client_sends_spend_metadata_header(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        autogen_discussion,
        "OpenAIChatCompletionClient",
        FakeClient,
    )

    with bind_request_context(
        request_id="req-autogen",
        trace_id="trace-autogen",
        user_id="user-autogen",
        app_id="app-autogen",
    ):
        autogen_discussion._create_model_client()

    header = captured["default_headers"]["x-litellm-spend-logs-metadata"]
    assert json.loads(header)["request_id"] == "req-autogen"
    assert json.loads(header)["app_id"] == "app-autogen"


def test_ragas_client_sends_spend_metadata_header(monkeypatch):
    captured = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(
        "ragas.llms.llm_factory",
        lambda **kwargs: kwargs,
    )

    with bind_request_context(
        request_id="req-ragas",
        trace_id="",
        user_id="",
        app_id="",
    ):
        ragas_evaluator.create_ragas_judge_llm()

    header = captured["default_headers"]["x-litellm-spend-logs-metadata"]
    assert json.loads(header) == {"request_id": "req-ragas"}
