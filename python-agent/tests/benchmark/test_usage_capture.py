from __future__ import annotations

import asyncio

import pytest
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

import core.model_router as model_router_module
import llm_factory
from core.model_router import ModelRouter
from request_context import capture_llm_usage, record_llm_response


pytestmark = pytest.mark.benchmark

class FakeResponse:
    def __init__(self, *, usage_metadata=None, response_metadata=None, content="ok"):
        self.usage_metadata = usage_metadata
        self.response_metadata = response_metadata or {}
        self.content = content


class ParsedAnswer(BaseModel):
    value: str


def test_capture_llm_usage_keeps_actual_tokens_and_spend():
    response = FakeResponse(
        usage_metadata={"input_tokens": 12, "output_tokens": 5, "total_tokens": 17},
        response_metadata={"model_name": "ignored", "response_cost": 0.004},
    )

    with capture_llm_usage() as captured:
        record_llm_response(response, "code-structured")

    assert captured == [
        {
            "model": "code-structured",
            "input_tokens": 12,
            "output_tokens": 5,
            "total_tokens": 17,
            "cost_usd": 0.004,
        }
    ]


def test_usage_metadata_wins_and_token_usage_is_the_fallback():
    preferred = FakeResponse(
        usage_metadata={"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
        response_metadata={
            "token_usage": {"prompt_tokens": 90, "completion_tokens": 10, "total_tokens": 100}
        },
    )
    fallback = FakeResponse(
        usage_metadata=None,
        response_metadata={
            "token_usage": {"prompt_tokens": 7, "completion_tokens": 4, "total_tokens": 11}
        },
    )

    with capture_llm_usage() as captured:
        record_llm_response(preferred, "preferred")
        record_llm_response(fallback, "fallback")

    assert [(item["input_tokens"], item["output_tokens"], item["total_tokens"]) for item in captured] == [
        (2, 3, 5),
        (7, 4, 11),
    ]


@pytest.mark.parametrize(
    "usage",
    [
        {"input_tokens": True, "output_tokens": 0, "total_tokens": 1},
        {"input_tokens": -1, "output_tokens": 0, "total_tokens": 0},
        {"input_tokens": 1.5, "output_tokens": 0, "total_tokens": 1},
        {"input_tokens": 2, "output_tokens": 3, "total_tokens": 4},
    ],
)
def test_capture_rejects_malformed_or_inconsistent_token_counts(usage):
    with capture_llm_usage() as captured:
        record_llm_response(FakeResponse(usage_metadata=usage), "model")
    assert captured == []


@pytest.mark.parametrize("cost", [None, True, -0.1, float("nan"), float("inf"), "0.1", 10**1000])
def test_capture_does_not_invent_or_accept_invalid_cost(cost):
    response = FakeResponse(
        usage_metadata={"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
        response_metadata={"response_cost": cost},
    )
    with capture_llm_usage() as captured:
        record_llm_response(response, "model")
    assert captured[0]["cost_usd"] is None


def test_inactive_capture_is_a_noop_even_for_malformed_provider_metadata():
    record_llm_response(
        FakeResponse(usage_metadata={"input_tokens": True, "output_tokens": -1}),
        "model",
    )


def test_nested_capture_restores_the_outer_capture():
    response = FakeResponse(usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})
    with capture_llm_usage() as outer:
        record_llm_response(response, "outer-before")
        with capture_llm_usage() as inner:
            record_llm_response(response, "inner")
        record_llm_response(response, "outer-after")

    assert [item["model"] for item in outer] == ["outer-before", "outer-after"]
    assert [item["model"] for item in inner] == ["inner"]


def test_concurrent_captures_do_not_cross_contaminate():
    async def worker(model: str):
        with capture_llm_usage() as captured:
            await asyncio.sleep(0)
            record_llm_response(
                FakeResponse(usage_metadata={"input_tokens": 1, "output_tokens": 0, "total_tokens": 1}),
                model,
            )
            await asyncio.sleep(0)
            return captured

    async def run_workers():
        return await asyncio.gather(worker("first"), worker("second"))

    first, second = asyncio.run(run_workers())
    assert [item["model"] for item in first] == ["first"]
    assert [item["model"] for item in second] == ["second"]


def test_model_router_records_plain_response_once(monkeypatch):
    response = FakeResponse(
        usage_metadata={"input_tokens": 4, "output_tokens": 2, "total_tokens": 6},
        content="plain",
    )

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def invoke(self, messages, config=None):
            return response

    monkeypatch.setattr(model_router_module, "ChatOpenAI", FakeClient)
    monkeypatch.setattr(model_router_module, "record_llm_call", lambda *args, **kwargs: None)

    with capture_llm_usage() as captured:
        assert ModelRouter().route("lightweight", ["prompt"], allow_degraded=False) == "plain"

    assert len(captured) == 1


def test_bad_provider_usage_never_changes_a_successful_model_result(monkeypatch):
    response = FakeResponse(
        usage_metadata={"input_tokens": "broken", "output_tokens": 2, "total_tokens": 2},
        content="business-result",
    )

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def invoke(self, messages, config=None):
            return response

    monkeypatch.setattr(model_router_module, "ChatOpenAI", FakeClient)
    monkeypatch.setattr(model_router_module, "record_llm_call", lambda *args, **kwargs: None)

    with capture_llm_usage() as captured:
        result = ModelRouter().route("lightweight", ["prompt"], allow_degraded=False)

    assert result == "business-result"
    assert captured == []


def test_structured_response_is_recorded_exactly_once(monkeypatch):
    response = FakeResponse(
        usage_metadata={"input_tokens": 6, "output_tokens": 3, "total_tokens": 9},
        content='{"value":"ok"}',
    )

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def invoke(self, messages, config=None):
            return response

    monkeypatch.setattr(model_router_module, "ChatOpenAI", FakeClient)
    monkeypatch.setattr(model_router_module, "record_llm_call", lambda *args, **kwargs: None)
    parser = lambda messages, **kwargs: llm_factory._call_with_parser(
        messages,
        ParsedAnswer,
        "return value",
        "structured",
        **kwargs,
    )

    with capture_llm_usage() as captured:
        result = ModelRouter().route(
            "structured",
            [HumanMessage(content="prompt")],
            parser=parser,
            allow_degraded=False,
        )

    assert result == ParsedAnswer(value="ok")
    assert len(captured) == 1
    assert captured[0]["model"] == "code-structured"


def test_tool_response_is_recorded_once_by_router(monkeypatch):
    response = FakeResponse(
        usage_metadata={"input_tokens": 8, "output_tokens": 1, "total_tokens": 9},
        content="",
    )

    class BoundClient:
        def invoke(self, messages, config=None):
            return response

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def bind_tools(self, tools):
            return BoundClient()

    monkeypatch.setattr(model_router_module, "ChatOpenAI", FakeClient)
    monkeypatch.setattr(model_router_module, "record_llm_call", lambda *args, **kwargs: None)
    llm = llm_factory.create_tool_enabled_llm(["tool"])

    with capture_llm_usage() as captured:
        assert llm.invoke(["prompt"]) is response

    assert len(captured) == 1
