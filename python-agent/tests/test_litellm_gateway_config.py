import importlib


def test_gateway_defaults(monkeypatch):
    import config as config_module

    with monkeypatch.context() as scoped:
        scoped.setenv("LITELLM_BASE_URL", "http://127.0.0.1:4000/v1")
        scoped.setenv("LITELLM_API_KEY", "sk-agent-test")
        importlib.reload(config_module)

        assert config_module.config.LITELLM_BASE_URL == "http://127.0.0.1:4000/v1"
        assert config_module.config.LITELLM_API_KEY == "sk-agent-test"
        assert config_module.config.LLM_MODEL_ALIASES == {
            "reasoning": "code-reasoning",
            "structured": "code-structured",
            "lightweight": "code-lightweight",
        }

    importlib.reload(config_module)


def test_unknown_group_falls_back_to_lightweight():
    from core.model_registry import get_model_alias

    assert get_model_alias("unknown") == "code-lightweight"
