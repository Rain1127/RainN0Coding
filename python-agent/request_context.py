from contextlib import contextmanager
from contextvars import ContextVar
from collections.abc import Iterator
import json
import math


_request_metadata: ContextVar[dict[str, str]] = ContextVar(
    "request_metadata",
    default={},
)

_llm_usage: ContextVar[list[dict[str, object]] | None] = ContextVar(
    "llm_usage",
    default=None,
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


@contextmanager
def capture_llm_usage() -> Iterator[list[dict[str, object]]]:
    """Capture provider-reported LLM usage in the current execution context."""
    captured: list[dict[str, object]] = []
    token = _llm_usage.set(captured)
    try:
        yield captured
    finally:
        _llm_usage.reset(token)


def _token_count(usage: dict[str, object], primary: str, fallback: str) -> int | None:
    value = usage.get(primary, usage.get(fallback, 0))
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def record_llm_response(response: object, model: str) -> None:
    """Record provider usage without allowing telemetry to affect the model call."""
    captured = _llm_usage.get()
    if captured is None:
        return

    try:
        response_metadata = getattr(response, "response_metadata", {}) or {}
        if not isinstance(response_metadata, dict):
            response_metadata = {}
        usage = getattr(response, "usage_metadata", None)
        if not isinstance(usage, dict):
            fallback_usage = response_metadata.get("token_usage", {}) or {}
            usage = fallback_usage if isinstance(fallback_usage, dict) else {}

        input_tokens = _token_count(usage, "input_tokens", "prompt_tokens")
        output_tokens = _token_count(usage, "output_tokens", "completion_tokens")
        if input_tokens is None or output_tokens is None:
            return
        expected_total = input_tokens + output_tokens
        total_value = usage.get("total_tokens", expected_total)
        if (
            isinstance(total_value, bool)
            or not isinstance(total_value, int)
            or total_value < expected_total
        ):
            return

        raw_cost = response_metadata.get("response_cost")
        cost = None
        if (
            isinstance(raw_cost, (int, float))
            and not isinstance(raw_cost, bool)
            and raw_cost >= 0
        ):
            try:
                normalized_cost = float(raw_cost)
            except (OverflowError, TypeError, ValueError):
                pass
            else:
                if math.isfinite(normalized_cost):
                    cost = normalized_cost
    except Exception:
        return
    captured.append(
        {
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_value,
            "cost_usd": cost,
        }
    )
