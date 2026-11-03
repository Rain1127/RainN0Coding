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


def _safe_cache_tokens(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _actual_model_label(value: object, requested: str) -> str:
    if not isinstance(value, str) or not value or value == requested:
        return "unknown"
    name = value.lower()
    if name in {"code-reasoning-glm", "code-structured-glm", "code-lightweight-glm"}:
        return "glm"
    if name == "code-reasoning-chat":
        return "deepseek"
    for prefix, label in (("deepseek", "deepseek"), ("glm", "glm"),
                          ("zhipu", "glm"), ("claude", "claude"),
                          ("anthropic", "claude"), ("gpt", "openai")):
        if name.startswith(prefix) or f"/{prefix}" in name:
            return label
    return "unknown"


def normalize_llm_usage(response: object, requested_model: str) -> dict[str, object] | None:
    """Normalize provider cache fields while preserving their distinct meanings."""
    try:
        response_metadata = getattr(response, "response_metadata", {}) or {}
        if not isinstance(response_metadata, dict):
            response_metadata = {}
        reported_usage = getattr(response, "usage_metadata", None)
        token_usage = response_metadata.get("token_usage", {}) or {}
        if not isinstance(token_usage, dict):
            token_usage = {}
        has_counts = (isinstance(reported_usage, dict)
                      and any(key in reported_usage for key in ("input_tokens", "prompt_tokens"))
                      and any(key in reported_usage for key in ("output_tokens", "completion_tokens")))
        usage = reported_usage if has_counts else token_usage

        input_tokens = _token_count(usage, "input_tokens", "prompt_tokens")
        output_tokens = _token_count(usage, "output_tokens", "completion_tokens")
        if input_tokens is None or output_tokens is None:
            return None
        expected_total = input_tokens + output_tokens
        total_value = usage.get("total_tokens", expected_total)
        if (
            isinstance(total_value, bool)
            or not isinstance(total_value, int)
            or total_value < expected_total
        ):
            return None

        cache_sources = [source for source in (usage, token_usage,
                         usage.get("input_token_details"),
                         token_usage.get("prompt_tokens_details"),
                         response_metadata.get("usage")) if isinstance(source, dict)]
        def cache_value(*names: str) -> int:
            for source in cache_sources:
                for name in names:
                    if name in source:
                        return _safe_cache_tokens(source[name])
            return 0

        hit = cache_value("prompt_cache_hit_tokens", "cache_read_input_tokens",
                          "cache_read", "cached_tokens")
        miss = cache_value("prompt_cache_miss_tokens")
        creation = cache_value("cache_creation_input_tokens", "cache_creation")
        actual_model = "unknown"
        for candidate in (response_metadata.get("model"),
                          response_metadata.get("model_name"),
                          response_metadata.get("litellm_model")):
            actual_model = _actual_model_label(candidate, requested_model)
            if actual_model != "unknown":
                break

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
        return None
    return {
        "model": requested_model,
        "request_model": requested_model,
        "actual_model": actual_model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_value,
        "cache_hit_tokens": hit,
        "cache_miss_tokens": miss,
        "cache_creation_tokens": creation,
        "cost_usd": cost,
    }


def record_llm_response(response: object, model: str) -> None:
    """Record usage without allowing telemetry to affect the model call."""
    if (getattr(response, 'response_metadata', {}) or {}).get('harness_replayed'):
        return
    usage = normalize_llm_usage(response, model)
    from workflow.budget import active_budget
    budget = active_budget.get()
    if budget and budget.pending:
        budget.observe(usage)
    from workflow.run_journal import active_journal
    journal = active_journal.get()
    if journal:
        journal.capture_response(response, usage)
    if usage is None:
        return
    captured = _llm_usage.get()
    if captured is not None:
        item = {key: usage[key] for key in (
            "model", "input_tokens", "output_tokens", "total_tokens", "cost_usd")}
        if usage["actual_model"] != "unknown":
            item["actual_model"] = usage["actual_model"]
        for key in ("cache_hit_tokens", "cache_miss_tokens", "cache_creation_tokens"):
            if usage[key]:
                item[key] = usage[key]
        captured.append(item)
    try:
        from monitoring import record_prompt_cache_tokens
        record_prompt_cache_tokens(usage)
    except Exception:
        pass
