from contextlib import contextmanager
from contextvars import ContextVar
from collections.abc import Iterator
import json


_request_metadata: ContextVar[dict[str, str]] = ContextVar(
    "request_metadata",
    default={},
)


def get_request_metadata() -> dict[str, str]:
    """Return a copy of metadata bound to the current request context."""
    return dict(_request_metadata.get())


def build_litellm_metadata(
    extra_metadata: dict[str, str] | None = None,
) -> dict[str, object]:
    """Build the metadata shape LiteLLM persists in SpendLogs."""
    metadata = get_request_metadata()
    metadata.update(extra_metadata or {})
    payload: dict[str, object] = {"spend_logs_metadata": metadata}
    if user_id := metadata.get("user_id"):
        payload["user_id"] = user_id
    return payload


def build_litellm_headers(
    extra_metadata: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build attribution headers for clients that cannot send extra_body."""
    metadata = get_request_metadata()
    metadata.update(extra_metadata or {})
    if not metadata:
        return {}
    return {
        "x-litellm-spend-logs-metadata": json.dumps(
            metadata,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    }


@contextmanager
def bind_request_context(
    *,
    request_id: str,
    trace_id: str,
    user_id: str,
    app_id: str,
) -> Iterator[None]:
    """Bind non-empty request metadata and reset it when the request finishes."""
    metadata = {
        key: value
        for key, value in {
            "request_id": request_id,
            "trace_id": trace_id,
            "user_id": user_id,
            "app_id": app_id,
        }.items()
        if value
    }
    token = _request_metadata.set(metadata)
    try:
        yield
    finally:
        _request_metadata.reset(token)
