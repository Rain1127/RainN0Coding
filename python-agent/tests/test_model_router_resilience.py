import os
import sys
from contextlib import contextmanager

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.model_router as model_router_module
from core.model_registry import ModelCandidate
from core.model_router import ModelRouter


@contextmanager
def _noop_span(*args, **kwargs):
    yield


def _make_candidate(name: str, model: str) -> ModelCandidate:
    return ModelCandidate(
        name=name,
        model=model,
        api_key="test-key",
        base_url="http://example.com",
        timeout=1,
        circuit_breaker=None,
    )


def test_route_waits_briefly_until_active_candidates_recover(monkeypatch):
    router = ModelRouter()
    deepseek = _make_candidate("deepseek-chat", "deepseek-chat")
    glm = _make_candidate("GLM-4.7-Flash", "glm-4.7-flash")

    call_state = {"count": 0}
    sleep_calls = []

    class DummyGroup:
        candidates = [deepseek, glm]

        def get_active(self):
            call_state["count"] += 1
            if call_state["count"] < 3:
                return []
            return [glm]

    monkeypatch.setattr(model_router_module, "get_group", lambda group_name: DummyGroup())
    monkeypatch.setattr(model_router_module, "start_span", _noop_span)
    monkeypatch.setattr(model_router_module, "record_llm_call", lambda *args, **kwargs: None)
    monkeypatch.setattr(model_router_module.time, "sleep", lambda seconds: sleep_calls.append(seconds))
    monkeypatch.setattr(
        router,
        "_call_llm",
        lambda candidate, messages, parser=None, langsmith_extra=None: f"ok:{candidate.name}",
    )

    result = router.route("structured", [{"role": "user", "content": "prompt"}])

    assert result == "ok:GLM-4.7-Flash"
    assert call_state["count"] == 3
    assert sleep_calls


def test_route_probes_glm_first_when_all_candidates_are_still_open(monkeypatch):
    router = ModelRouter()
    deepseek = _make_candidate("deepseek-chat", "deepseek-chat")
    glm = _make_candidate("GLM-4.7-Flash", "glm-4.7-flash")
    seen = []

    class DummyGroup:
        candidates = [deepseek, glm]

        def get_active(self):
            return []

    monkeypatch.setattr(model_router_module, "get_group", lambda group_name: DummyGroup())
    monkeypatch.setattr(model_router_module, "start_span", _noop_span)
    monkeypatch.setattr(model_router_module, "record_llm_call", lambda *args, **kwargs: None)
    monkeypatch.setattr(model_router_module.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        router,
        "_call_llm",
        lambda candidate, messages, parser=None, langsmith_extra=None: seen.append(candidate.name)
        or f"ok:{candidate.name}",
    )

    result = router.route("structured", [{"role": "user", "content": "prompt"}])

    assert result == "ok:GLM-4.7-Flash"
    assert seen == ["GLM-4.7-Flash"]


def test_route_retries_transient_candidate_failure_once(monkeypatch):
    router = ModelRouter()
    glm = _make_candidate("GLM-4.7-Flash", "glm-4.7-flash")
    attempts = []
    sleep_calls = []

    class DummyGroup:
        candidates = [glm]

        def get_active(self):
            return [glm]

    def flaky_call(candidate, messages, parser=None, langsmith_extra=None):
        attempts.append(candidate.name)
        if len(attempts) == 1:
            raise TimeoutError("temporary provider timeout")
        return "recovered"

    monkeypatch.setattr(model_router_module, "get_group", lambda group_name: DummyGroup())
    monkeypatch.setattr(model_router_module, "start_span", _noop_span)
    monkeypatch.setattr(model_router_module, "record_llm_call", lambda *args, **kwargs: None)
    monkeypatch.setattr(model_router_module.time, "sleep", lambda seconds: sleep_calls.append(seconds))
    monkeypatch.setattr(router, "_call_llm", flaky_call)

    result = router.route(
        "reasoning",
        [{"role": "user", "content": "prompt"}],
        allow_degraded=False,
    )

    assert result == "recovered"
    assert attempts == ["GLM-4.7-Flash", "GLM-4.7-Flash"]
    assert sleep_calls == [model_router_module.TRANSIENT_RETRY_DELAY_SECONDS]
