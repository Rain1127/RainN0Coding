import os
import sys
from contextlib import contextmanager

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.model_router as model_router_module
from core.model_router import ModelRouter
from request_context import bind_request_context


@contextmanager
def _noop_span(*args, **kwargs):
    yield


def _install_fake_client(monkeypatch, *, content="ok", error=None):
    captured = {"clients": [], "invocations": []}

    class FakeClient:
        def __init__(self, **kwargs):
            captured["clients"].append(kwargs)

        def invoke(self, messages, config=None):
            captured["invocations"].append({"messages": messages, "config": config})
            if error is not None:
                raise error
            return type("Response", (), {"content": content})()

    monkeypatch.setattr(model_router_module, "ChatOpenAI", FakeClient)
    monkeypatch.setattr(model_router_module, "start_span", _noop_span)
    monkeypatch.setattr(model_router_module, "record_llm_call", lambda *args, **kwargs: None)
    return captured


def test_route_calls_gateway_once_with_alias_and_zero_sdk_retries(monkeypatch):
    captured = _install_fake_client(monkeypatch)

    result = ModelRouter().route("structured", ["prompt"], allow_degraded=False)

    assert result == "ok"
    assert len(captured["clients"]) == 1
    assert len(captured["invocations"]) == 1
    assert captured["clients"][0]["model"] == "code-structured"
    assert captured["clients"][0]["max_retries"] == 0
    assert captured["clients"][0]["base_url"].endswith(":4000/v1")


def test_route_puts_request_context_in_litellm_metadata(monkeypatch):
    captured = _install_fake_client(monkeypatch)

    with bind_request_context(
        request_id="req-1",
        trace_id="tr-1",
        user_id="u-1",
        app_id="a-1",
    ):
        ModelRouter().route(
            "reasoning",
            ["prompt"],
            allow_degraded=False,
            langsmith_extra={"metadata": {"phase": "coder"}},
        )

    assert captured["clients"][0]["extra_body"]["metadata"] == {
        "request_id": "req-1",
        "trace_id": "tr-1",
        "user_id": "u-1",
        "app_id": "a-1",
        "phase": "coder",
    }


def test_route_returns_none_only_when_degraded_mode_is_allowed(monkeypatch):
    captured = _install_fake_client(monkeypatch, error=TimeoutError("gateway timeout"))

    result = ModelRouter().route("lightweight", ["prompt"], allow_degraded=True)

    assert result is None
    assert len(captured["clients"]) == 1
    assert len(captured["invocations"]) == 1


def test_route_raises_gateway_error_when_degraded_mode_is_forbidden(monkeypatch):
    _install_fake_client(monkeypatch, error=TimeoutError("gateway timeout"))

    with pytest.raises(RuntimeError, match="LiteLLM gateway call failed"):
        ModelRouter().route("reasoning", ["prompt"], allow_degraded=False)
