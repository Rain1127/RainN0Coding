"""
OpenTelemetry tracing helpers for the Python agent.

This module keeps the tracing setup small and explicit:
- initialize an OTLP exporter once
- extract incoming W3C context from FastAPI requests
- keep a request-local trace id for logs and SSE payloads
- provide a tiny span helper for workflow and model call nesting
"""
from contextlib import contextmanager
from contextvars import ContextVar
import os

from opentelemetry import trace
from opentelemetry.propagate import extract
from opentelemetry.trace import SpanKind, Status, StatusCode

_trace_id_context: ContextVar[str] = ContextVar("trace_id", default="-")
_tracing_ready = False


def _otlp_exporter_enabled() -> bool:
    explicit = os.getenv("OTEL_EXPORTER_ENABLED")
    if explicit is not None:
        return explicit.strip().lower() == "true"
    app_env = os.getenv("APP_ENV", os.getenv("ENVIRONMENT", ""))
    return app_env.strip().lower() != "test"


def _format_trace_id(trace_id: int) -> str:
    if not trace_id:
        return "-"
    return f"{trace_id:032x}"


def _format_span_id(span_id: int) -> str:
    if not span_id:
        return "-"
    return f"{span_id:016x}"


def get_current_trace_id(default: str = "-") -> str:
    return _trace_id_context.get(default)


def set_current_trace_id(trace_id: str) -> None:
    _trace_id_context.set(trace_id or "-")


def current_trace_context(default_trace_id: str = "-", default_span_id: str = "-") -> tuple[str, str]:
    span = trace.get_current_span()
    span_context = span.get_span_context() if span is not None else None
    if span_context is not None and span_context.is_valid:
        return _format_trace_id(span_context.trace_id), _format_span_id(span_context.span_id)
    return get_current_trace_id(default_trace_id), default_span_id


def resolve_trace_id(request_trace_id: str = "") -> str:
    trace_id, _ = current_trace_context(request_trace_id or "-")
    if trace_id != "-":
        return trace_id
    return request_trace_id or "-"


def setup_tracing(app, service_name: str = "python-agent") -> None:
    """Initialize OTLP export and attach a request middleware that opens server spans."""
    global _tracing_ready
    if _tracing_ready:
        return

    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": "RainN0Coding",
        }
    )
    provider = TracerProvider(resource=resource)
    if _otlp_exporter_enabled():
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        endpoint = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://localhost:4318/v1/traces")
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)

    tracer = trace.get_tracer("python-agent.server")

    @app.middleware("http")
    async def tracing_middleware(request, call_next):
        parent_context = extract(dict(request.headers))
        span_name = f"{request.method} {request.url.path}"
        with tracer.start_as_current_span(span_name, context=parent_context, kind=SpanKind.SERVER) as span:
            resolved_trace_id = resolve_trace_id()
            token = _trace_id_context.set(resolved_trace_id)
            span.set_attribute("http.method", request.method)
            span.set_attribute("http.route", request.url.path)
            span.set_attribute("app.component", "python-agent")
            try:
                response = await call_next(request)
                span.set_attribute("http.status_code", response.status_code)
                return response
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise
            finally:
                _trace_id_context.reset(token)

    _tracing_ready = True


@contextmanager
def start_span(name: str, attributes: dict | None = None, kind: SpanKind = SpanKind.INTERNAL):
    tracer = trace.get_tracer("python-agent.workflow")
    with tracer.start_as_current_span(name, kind=kind) as span:
        if attributes:
            for key, value in attributes.items():
                if value is not None:
                    span.set_attribute(key, value)
        yield span
