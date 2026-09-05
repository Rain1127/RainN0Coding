from request_context import bind_request_context, get_request_metadata


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
