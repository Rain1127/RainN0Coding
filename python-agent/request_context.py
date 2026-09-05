from contextlib import contextmanager
from contextvars import ContextVar
from collections.abc import Iterator


_request_metadata: ContextVar[dict[str, str]] = ContextVar(
    "request_metadata",
    default={},
)


def get_request_metadata() -> dict[str, str]:
    """Return a copy of metadata bound to the current request context."""
    return dict(_request_metadata.get())


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
