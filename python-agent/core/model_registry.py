"""Map business model groups to stable LiteLLM aliases."""

from config import config


def get_model_alias(group_name: str) -> str:
    """Return the configured alias, defaulting unknown groups to lightweight."""
    return config.LLM_MODEL_ALIASES.get(
        group_name,
        config.LLM_MODEL_ALIASES["lightweight"],
    )
