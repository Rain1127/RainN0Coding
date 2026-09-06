import importlib
import sys

import pytest
import redis

from memory import conversation_memory as memory_module
from rag import rag_cache as cache_module


@pytest.fixture(autouse=True)
def _remove_reloaded_config_after_test():
    yield
    sys.modules.pop("config", None)


def test_redis_password_is_loaded_from_environment(monkeypatch):
    monkeypatch.setenv("REDIS_PASSWORD", "redis-secret")
    monkeypatch.setenv("CODE_OUTPUT_DIR", "/data/code-output")
    sys.modules.pop("config", None)

    current_config = importlib.import_module("config").config

    assert current_config.REDIS_PASSWORD == "redis-secret"
    assert current_config.CODE_OUTPUT_DIR == "/data/code-output"


@pytest.mark.parametrize(
    "module, factory",
    [
        (memory_module, memory_module.ConversationMemory),
        (cache_module, cache_module.RagCache),
    ],
)
def test_redis_clients_use_configured_password(monkeypatch, module, factory):
    captured = {}

    class FakeRedis:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def ping(self):
            return True

    monkeypatch.setattr(redis, "Redis", FakeRedis)
    monkeypatch.setattr(module.config, "REDIS_PASSWORD", "redis-secret", raising=False)

    client = factory()._get_redis()

    assert client is not None
    assert captured["password"] == "redis-secret"
