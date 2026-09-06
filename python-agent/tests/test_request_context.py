import json

from request_context import (
    bind_request_context,
    build_litellm_headers,
    build_litellm_metadata,
    get_request_metadata,
)


def test_request_context_is_bound_and_reset():
    assert get_request_metadata() == {}
    with bind_request_context(
        request_id="req-1",
        trace_id="tr-1",
        user_id="u-1",
        app_id="a-1",
    ):
        assert get_request_metadata() == {
            "request_id": "req-1",
            "trace_id": "tr-1",
            "user_id": "u-1",
            "app_id": "a-1",
        }
    assert get_request_metadata() == {}


def test_request_context_omits_empty_values():
    with bind_request_context(request_id="", trace_id="tr-2", user_id="", app_id=""):
        assert get_request_metadata() == {"trace_id": "tr-2"}


def test_litellm_metadata_nests_context_for_spend_logs():
    with bind_request_context(
        request_id="req-2",
        trace_id="tr-2",
        user_id="u-2",
        app_id="a-2",
    ):
        metadata = build_litellm_metadata({"phase": "reviewer"})

    assert metadata == {
        "user_id": "u-2",
        "spend_logs_metadata": {
            "request_id": "req-2",
            "trace_id": "tr-2",
            "user_id": "u-2",
            "app_id": "a-2",
            "phase": "reviewer",
        },
    }


def test_litellm_headers_carry_context_for_clients_without_extra_body():
    with bind_request_context(
        request_id="req-3",
        trace_id="tr-3",
        user_id="u-3",
        app_id="a-3",
    ):
        headers = build_litellm_headers()

    assert json.loads(headers["x-litellm-spend-logs-metadata"]) == {
        "request_id": "req-3",
        "trace_id": "tr-3",
        "user_id": "u-3",
        "app_id": "a-3",
    }
