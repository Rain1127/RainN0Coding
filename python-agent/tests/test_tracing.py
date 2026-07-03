import os
import sys
import types
from contextlib import contextmanager

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from opentelemetry import trace
from opentelemetry.trace import (
    NonRecordingSpan,
    SpanContext,
    TraceFlags,
    TraceState,
)

import tracing
from tracing import _otlp_exporter_enabled, resolve_trace_id


class _DummyApp:
    def __init__(self):
        self.middlewares = []

    def middleware(self, kind):
        def decorator(func):
            self.middlewares.append((kind, func))
            return func

        return decorator


class _DummySpan:
    def set_attribute(self, *args, **kwargs):
        return None

    def record_exception(self, *args, **kwargs):
        return None

    def set_status(self, *args, **kwargs):
        return None


class _DummyTracer:
    @contextmanager
    def start_as_current_span(self, *args, **kwargs):
        yield _DummySpan()


class _FakeResource:
    @staticmethod
    def create(attributes):
        return {"attributes": attributes}


class _FakeTracerProvider:
    def __init__(self, resource):
        self.resource = resource
        self.span_processors = []

    def add_span_processor(self, processor):
        self.span_processors.append(processor)


class _FakeBatchSpanProcessor:
    def __init__(self, exporter):
        self.exporter = exporter


class _FakeOTLPSpanExporter:
    def __init__(self, endpoint):
        self.endpoint = endpoint


def _install_fake_otel(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "opentelemetry.sdk.resources",
        types.SimpleNamespace(Resource=_FakeResource),
    )
    monkeypatch.setitem(
        sys.modules,
        "opentelemetry.sdk.trace",
        types.SimpleNamespace(TracerProvider=_FakeTracerProvider),
    )
    monkeypatch.setitem(
        sys.modules,
        "opentelemetry.sdk.trace.export",
        types.SimpleNamespace(BatchSpanProcessor=_FakeBatchSpanProcessor),
    )
    monkeypatch.setitem(
        sys.modules,
        "opentelemetry.exporter.otlp.proto.http.trace_exporter",
        types.SimpleNamespace(OTLPSpanExporter=_FakeOTLPSpanExporter),
    )


def test_resolve_trace_id_prefers_current_span():
    span_context = SpanContext(
        trace_id=0x1234567890ABCDEF1234567890ABCDEF,
        span_id=0x1234567890ABCDEF,
        is_remote=False,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
        trace_state=TraceState(),
    )
    span = NonRecordingSpan(span_context)

    with trace.use_span(span, end_on_exit=False):
        assert resolve_trace_id("body-trace-id") == "1234567890abcdef1234567890abcdef"


def test_resolve_trace_id_falls_back_to_request_body():
    assert resolve_trace_id("body-trace-id") == "body-trace-id"


def test_otlp_exporter_enabled_is_false_for_test_env_when_unset(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("OTEL_EXPORTER_ENABLED", raising=False)

    assert _otlp_exporter_enabled() is False


def test_otlp_exporter_enabled_is_false_for_environment_test_fallback_when_app_env_unset(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.delenv("OTEL_EXPORTER_ENABLED", raising=False)

    assert _otlp_exporter_enabled() is False


def test_otlp_exporter_enabled_is_true_for_dev_env_when_unset(monkeypatch):
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.delenv("OTEL_EXPORTER_ENABLED", raising=False)

    assert _otlp_exporter_enabled() is True


def test_otlp_exporter_enabled_respects_true_override_in_test_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("OTEL_EXPORTER_ENABLED", "true")

    assert _otlp_exporter_enabled() is True


def test_otlp_exporter_enabled_respects_false_override_in_dev_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("OTEL_EXPORTER_ENABLED", "false")

    assert _otlp_exporter_enabled() is False


def test_setup_tracing_skips_otlp_exporter_in_test_env_by_default(monkeypatch):
    app = _DummyApp()
    providers = []
    _install_fake_otel(monkeypatch)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("OTEL_EXPORTER_ENABLED", raising=False)
    monkeypatch.setattr(tracing, "_tracing_ready", False)
    monkeypatch.setattr(tracing.trace, "set_tracer_provider", providers.append)
    monkeypatch.setattr(tracing.trace, "get_tracer", lambda name: _DummyTracer())

    tracing.setup_tracing(app)

    assert len(providers) == 1
    assert providers[0].span_processors == []
    assert app.middlewares and len(app.middlewares) == 1
    assert app.middlewares[0][0] == "http"
    assert tracing._tracing_ready is True


def test_setup_tracing_installs_otlp_exporter_when_enabled_in_test_env(monkeypatch):
    app = _DummyApp()
    providers = []
    endpoint = "http://collector.example/v1/traces"
    _install_fake_otel(monkeypatch)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("OTEL_EXPORTER_ENABLED", "true")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", endpoint)
    monkeypatch.setattr(tracing, "_tracing_ready", False)
    monkeypatch.setattr(tracing.trace, "set_tracer_provider", providers.append)
    monkeypatch.setattr(tracing.trace, "get_tracer", lambda name: _DummyTracer())

    tracing.setup_tracing(app)

    assert len(providers) == 1
    assert len(providers[0].span_processors) == 1
    assert providers[0].span_processors[0].exporter.endpoint == endpoint
    assert app.middlewares and len(app.middlewares) == 1
    assert tracing._tracing_ready is True
