import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import llm_factory
from request_context import bind_request_context


def test_compatibility_llm_uses_gateway_reasoning_alias(monkeypatch):
    captured = {}

    class FakeLlm:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(llm_factory, "ChatOpenAI", FakeLlm)

    with bind_request_context(
        request_id="req-compat",
        trace_id="trace-compat",
        user_id="user-compat",
        app_id="app-compat",
    ):
        llm_factory.create_llm(temperature=0.2)

    assert captured["model"] == "code-reasoning"
    assert captured["base_url"].endswith(":4000/v1")
    assert captured["max_retries"] == 0
    assert captured["extra_body"]["metadata"]["spend_logs_metadata"]["request_id"] == "req-compat"


def test_reasoning_llm_uses_gateway_without_sdk_retries(monkeypatch):
    captured = {}

    class FakeLlm:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(llm_factory, "ChatOpenAI", FakeLlm)

    with bind_request_context(
        request_id="req-reasoning",
        trace_id="",
        user_id="",
        app_id="",
    ):
        llm_factory.create_reasoning_llm()

    assert captured["model"] == "code-reasoning"
    assert captured["base_url"].endswith(":4000/v1")
    assert captured["max_retries"] == 0
    assert captured["extra_body"]["metadata"]["spend_logs_metadata"] == {
        "request_id": "req-reasoning"
    }


def test_tool_enabled_llm_routes_each_invoke_through_model_fallback(monkeypatch):
    route_calls = []

    class FakeDirectLlm:
        def __init__(self, **kwargs):
            pass

        def bind_tools(self, tools):
            return self

        def invoke(self, messages, config=None):
            return "primary-direct"

    class FakeFallbackClient:
        def bind_tools(self, tools):
            assert tools == ["create_file"]
            return self

        def invoke(self, messages, config=None):
            assert messages == ["generate"]
            assert config == {"run_name": "coder"}
            return "fallback-tool-response"

    def fake_route(**kwargs):
        route_calls.append(kwargs)
        return kwargs["parser"](
            kwargs["messages"],
            _client=FakeFallbackClient(),
            _config=kwargs["langsmith_extra"],
        )

    monkeypatch.setattr(llm_factory, "ChatOpenAI", FakeDirectLlm)
    monkeypatch.setattr(llm_factory.model_router, "route", fake_route)

    llm = llm_factory.create_tool_enabled_llm(["create_file"], group="reasoning")
    result = llm.invoke(["generate"], config={"run_name": "coder"})

    assert result == "fallback-tool-response"
    assert len(route_calls) == 1
    assert route_calls[0]["group_name"] == "reasoning"
    assert route_calls[0]["allow_degraded"] is False

