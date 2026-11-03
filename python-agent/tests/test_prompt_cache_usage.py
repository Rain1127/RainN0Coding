from types import SimpleNamespace

import request_context
from request_context import capture_llm_usage, record_llm_response


def normalize_llm_usage(*args):
    func = getattr(request_context, "normalize_llm_usage", None)
    assert callable(func)
    return func(*args)


def _response(usage=None, metadata=None):
    return SimpleNamespace(usage_metadata=usage, response_metadata=metadata or {})


def test_deepseek_hit_and_miss_do_not_create_tokens():
    response = _response(metadata={
        "model_name": "deepseek-v4-pro",
        "token_usage": {
            "prompt_tokens": 100, "completion_tokens": 10,
            "prompt_cache_hit_tokens": 70, "prompt_cache_miss_tokens": 30,
        },
    })
    usage = normalize_llm_usage(response, "code-reasoning")
    assert usage["request_model"] == "code-reasoning"
    assert usage["actual_model"] == "deepseek"
    assert usage["cache_hit_tokens"] == 70
    assert usage["cache_miss_tokens"] == 30
    assert usage["cache_creation_tokens"] == 0


def test_anthropic_style_and_langchain_details_map_separately():
    response = _response(
        usage={"input_tokens": 100, "output_tokens": 20,
               "input_token_details": {"cache_read": 60, "cache_creation": 25}},
        metadata={"model_name": "claude-sonnet-4"},
    )
    usage = normalize_llm_usage(response, "code-structured")
    assert usage["actual_model"] == "claude"
    assert usage["cache_hit_tokens"] == 60
    assert usage["cache_creation_tokens"] == 25
    assert usage["cache_miss_tokens"] == 0


def test_litellm_token_usage_and_fallback_model_are_not_attributed_to_alias():
    response = _response(metadata={
        "model_name": "glm-4.5",
        "token_usage": {"prompt_tokens": 80, "completion_tokens": 5,
                        "cache_read_input_tokens": 10,
                        "cache_creation_input_tokens": 20},
    })
    with capture_llm_usage() as captured:
        record_llm_response(response, "code-reasoning")
    assert captured[0]["model"] == "code-reasoning"
    assert captured[0]["actual_model"] == "glm"
    assert captured[0]["cache_hit_tokens"] == 10
    assert captured[0]["cache_creation_tokens"] == 20


def test_requested_alias_without_actual_model_is_unknown():
    usage = normalize_llm_usage(
        _response(usage={"input_tokens": 10, "output_tokens": 2},
                  metadata={"model_name": "code-reasoning"}),
        "code-reasoning",
    )
    assert usage["actual_model"] == "unknown"


def test_empty_langchain_usage_uses_litellm_token_usage():
    usage = normalize_llm_usage(
        _response(usage={}, metadata={
            "token_usage": {"prompt_tokens": 40, "completion_tokens": 3,
                            "prompt_cache_hit_tokens": 15},
        }),
        "code-structured",
    )
    assert usage["input_tokens"] == 40
    assert usage["cache_hit_tokens"] == 15


def test_actual_model_field_wins_when_model_name_is_request_alias():
    usage = normalize_llm_usage(
        _response(usage={"input_tokens": 20, "output_tokens": 2},
                  metadata={"model_name": "code-reasoning", "model": "glm-4.5"}),
        "code-reasoning",
    )
    assert usage["actual_model"] == "glm"


def test_litellm_fallback_alias_is_not_counted_as_primary():
    usage = normalize_llm_usage(
        _response(usage={"input_tokens": 20, "output_tokens": 2},
                  metadata={"model_name": "code-reasoning-glm"}),
        "code-reasoning",
    )
    assert usage["actual_model"] == "glm"


def test_partial_langchain_usage_uses_complete_gateway_usage():
    usage = normalize_llm_usage(
        _response(usage={"input_tokens": 1}, metadata={
            "token_usage": {"prompt_tokens": 40, "completion_tokens": 3},
        }),
        "code-structured",
    )
    assert usage["input_tokens"] == 40
    assert usage["output_tokens"] == 3
