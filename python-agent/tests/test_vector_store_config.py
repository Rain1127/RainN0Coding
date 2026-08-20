import importlib
import sys

import pytest


@pytest.fixture(autouse=True)
def _remove_reloaded_config_after_test():
    yield
    sys.modules.pop("config", None)


def _reload_config(monkeypatch, **env):
    import dotenv

    monkeypatch.setattr(
        dotenv,
        "load_dotenv",
        lambda *args, **kwargs: False,
    )
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    sys.modules.pop("config", None)
    return importlib.import_module("config").config


def test_vector_store_defaults_to_milvus(monkeypatch):
    monkeypatch.delenv("VECTOR_DB_PROVIDER", raising=False)

    config = _reload_config(monkeypatch)

    assert config.VECTOR_DB_PROVIDER == "milvus"


def test_qdrant_settings_are_read_from_environment(monkeypatch):
    config = _reload_config(
        monkeypatch,
        VECTOR_DB_PROVIDER="qdrant",
        QDRANT_URL="http://localhost:6333",
        QDRANT_API_KEY="local-key",
        QDRANT_TIMEOUT_SECONDS="7",
    )

    assert config.VECTOR_DB_PROVIDER == "qdrant"
    assert config.QDRANT_URL == "http://localhost:6333"
    assert config.QDRANT_API_KEY == "local-key"
    assert config.QDRANT_TIMEOUT_SECONDS == 7.0
