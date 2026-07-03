# Test OTLP Exporter Noise Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Disable OTLP exporter registration by default in Python test environment so pytest runs stay quiet, while preserving current tracing defaults for non-test environments.

**Architecture:** Keep `python-agent/tracing.py` as the single place that decides whether OTLP export is enabled. Add a tiny environment-resolution helper, gate exporter registration inside `setup_tracing`, and cover both the decision logic and setup side effects with deterministic monkeypatched tests in `python-agent/tests/test_tracing.py`.

**Tech Stack:** Python 3.12, FastAPI middleware wiring, OpenTelemetry SDK, pytest, monkeypatch

---

## File Structure

- Modify `python-agent/tracing.py`
  - Add a narrow helper that resolves `OTEL_EXPORTER_ENABLED` against `APP_ENV`.
  - Keep tracer provider and middleware setup intact.
  - Register `BatchSpanProcessor(OTLPSpanExporter(...))` only when OTLP export is enabled.
- Modify `python-agent/tests/test_tracing.py`
  - Add pure decision tests for the new helper.
  - Add deterministic setup tests proving middleware still registers and exporter registration is skipped in `APP_ENV=test` unless explicitly enabled.
- No docs change
  - The behavior is intentionally local and self-documenting through focused regression tests.

---

### Task 1: Add the Failing Environment-Decision Tests

**Files:**
- Modify: `python-agent/tests/test_tracing.py`
- Test: `python-agent/tests/test_tracing.py`

- [ ] **Step 1: Append failing tests for the new exporter-enable decision helper**

Add these tests to `python-agent/tests/test_tracing.py` below the existing `resolve_trace_id` coverage:

```python
import tracing


def test_otlp_exporter_enabled_defaults_off_in_test_env(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_ENABLED", raising=False)
    monkeypatch.setenv("APP_ENV", "test")

    assert tracing._otlp_exporter_enabled() is False


def test_otlp_exporter_enabled_defaults_on_outside_test(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_ENABLED", raising=False)
    monkeypatch.setenv("APP_ENV", "dev")

    assert tracing._otlp_exporter_enabled() is True


def test_otlp_exporter_enabled_true_override_wins_in_test_env(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "test")

    assert tracing._otlp_exporter_enabled() is True


def test_otlp_exporter_enabled_false_override_wins_outside_test(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_ENABLED", "false")
    monkeypatch.setenv("APP_ENV", "dev")

    assert tracing._otlp_exporter_enabled() is False
```

- [ ] **Step 2: Run the new helper tests to verify they fail first**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_tracing.py -k otlp_exporter_enabled -v
```

Expected: FAIL because `_otlp_exporter_enabled` does not exist yet.

- [ ] **Step 3: Add the minimal helper in `python-agent/tracing.py`**

Insert this helper above `setup_tracing`:

```python
def _otlp_exporter_enabled() -> bool:
    explicit = os.getenv("OTEL_EXPORTER_ENABLED")
    if explicit is not None:
        return explicit.strip().lower() == "true"

    return os.getenv("APP_ENV", "").strip().lower() != "test"
```

Do not add broader config plumbing or extra abstraction in this task.

- [ ] **Step 4: Re-run the helper tests**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_tracing.py -k otlp_exporter_enabled -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add python-agent/tracing.py python-agent/tests/test_tracing.py
git commit -m "test: cover tracing exporter env decision"
```

---

### Task 2: Prove `setup_tracing` Skips Exporter Registration in Tests

**Files:**
- Modify: `python-agent/tests/test_tracing.py`
- Modify: `python-agent/tracing.py`
- Test: `python-agent/tests/test_tracing.py`

- [ ] **Step 1: Append failing setup-behavior tests that monkeypatch OpenTelemetry classes**

Add these helpers and tests to `python-agent/tests/test_tracing.py`:

```python
class DummyApp:
    def __init__(self):
        self.http_middlewares = []

    def middleware(self, kind):
        assert kind == "http"

        def decorator(func):
            self.http_middlewares.append(func)
            return func

        return decorator


class DummyTracer:
    pass


def test_setup_tracing_skips_otlp_exporter_in_test_env(monkeypatch):
    import opentelemetry.sdk.resources as sdk_resources
    import opentelemetry.sdk.trace as sdk_trace
    import opentelemetry.sdk.trace.export as sdk_trace_export
    import opentelemetry.exporter.otlp.proto.http.trace_exporter as trace_exporter_module

    app = DummyApp()
    captured = {}

    class FakeProvider:
        def __init__(self, resource):
            self.resource = resource
            self.processors = []

        def add_span_processor(self, processor):
            self.processors.append(processor)

    class FakeBatchSpanProcessor:
        def __init__(self, exporter):
            self.exporter = exporter

    class FakeExporter:
        def __init__(self, endpoint):
            self.endpoint = endpoint

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("OTEL_EXPORTER_ENABLED", raising=False)
    monkeypatch.setattr(tracing, "_tracing_ready", False)
    monkeypatch.setattr(sdk_resources.Resource, "create", staticmethod(lambda attrs: attrs))
    monkeypatch.setattr(sdk_trace, "TracerProvider", FakeProvider)
    monkeypatch.setattr(sdk_trace_export, "BatchSpanProcessor", FakeBatchSpanProcessor)
    monkeypatch.setattr(trace_exporter_module, "OTLPSpanExporter", FakeExporter)
    monkeypatch.setattr(tracing.trace, "set_tracer_provider", lambda provider: captured.setdefault("provider", provider))
    monkeypatch.setattr(tracing.trace, "get_tracer", lambda name: DummyTracer())

    tracing.setup_tracing(app, service_name="python-agent-test")

    assert captured["provider"].processors == []
    assert len(app.http_middlewares) == 1
    assert tracing._tracing_ready is True


def test_setup_tracing_adds_otlp_exporter_when_explicitly_enabled(monkeypatch):
    import opentelemetry.sdk.resources as sdk_resources
    import opentelemetry.sdk.trace as sdk_trace
    import opentelemetry.sdk.trace.export as sdk_trace_export
    import opentelemetry.exporter.otlp.proto.http.trace_exporter as trace_exporter_module

    app = DummyApp()
    captured = {}

    class FakeProvider:
        def __init__(self, resource):
            self.resource = resource
            self.processors = []

        def add_span_processor(self, processor):
            self.processors.append(processor)

    class FakeBatchSpanProcessor:
        def __init__(self, exporter):
            self.exporter = exporter

    class FakeExporter:
        def __init__(self, endpoint):
            self.endpoint = endpoint

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("OTEL_EXPORTER_ENABLED", "true")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://collector.test/v1/traces")
    monkeypatch.setattr(tracing, "_tracing_ready", False)
    monkeypatch.setattr(sdk_resources.Resource, "create", staticmethod(lambda attrs: attrs))
    monkeypatch.setattr(sdk_trace, "TracerProvider", FakeProvider)
    monkeypatch.setattr(sdk_trace_export, "BatchSpanProcessor", FakeBatchSpanProcessor)
    monkeypatch.setattr(trace_exporter_module, "OTLPSpanExporter", FakeExporter)
    monkeypatch.setattr(tracing.trace, "set_tracer_provider", lambda provider: captured.setdefault("provider", provider))
    monkeypatch.setattr(tracing.trace, "get_tracer", lambda name: DummyTracer())

    tracing.setup_tracing(app, service_name="python-agent-test")

    assert len(captured["provider"].processors) == 1
    assert captured["provider"].processors[0].exporter.endpoint == "http://collector.test/v1/traces"
    assert len(app.http_middlewares) == 1
```

- [ ] **Step 2: Run the setup tests to verify they fail before the implementation change**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_tracing.py -k setup_tracing -v
```

Expected: FAIL because `setup_tracing` always adds a span processor today.

- [ ] **Step 3: Gate exporter registration in `python-agent/tracing.py` without changing middleware behavior**

Update `setup_tracing` to this shape:

```python
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
            "service.namespace": "yu-ai-code-mother",
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
```

Important: keep the `_tracing_ready` assignment after middleware registration and do not change trace-id resolution behavior.

- [ ] **Step 4: Re-run the full tracing suite**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_tracing.py -v
```

Expected: PASS, including both `resolve_trace_id` and OTLP exporter gating coverage.

- [ ] **Step 5: Commit**

```bash
git add python-agent/tracing.py python-agent/tests/test_tracing.py
git commit -m "fix: disable otlp exporter by default in tests"
```

---

### Task 3: Run Focused Regression Verification

**Files:**
- Modify: `python-agent/tracing.py`
- Modify: `python-agent/tests/test_tracing.py`
- Test: `python-agent/tests/test_tracing.py`
- Test: `python-agent/tests/test_internal_auth_and_concurrency.py`

- [ ] **Step 1: Re-run the tracing and FastAPI boundary suites together**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_tracing.py tests/test_internal_auth_and_concurrency.py -v
```

Expected: PASS. This confirms the focused tracing regression and the API boundary suite still initialize cleanly with the new default.

- [ ] **Step 2: Re-run the canonical harness command and confirm the collector-noise regression is gone**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest -m harness -v
```

Expected: PASS with no OTLP connection-failure noise emitted against `http://localhost:4318/v1/traces` when `APP_ENV=test`.

- [ ] **Step 3: Commit the final verified state if the previous commits were squashed away during execution**

```bash
git add python-agent/tracing.py python-agent/tests/test_tracing.py
git commit -m "test: verify tracing exporter noise regression"
```

Only do this commit if execution mode or local workflow left the branch without the earlier commits.

---

## Plan Self-Review

- Spec coverage: the plan covers the environment rule, default test disable behavior, explicit true override, preserved non-test default behavior, middleware initialization, and deterministic regression verification.
- Placeholder scan: every code-changing step includes concrete code, exact file paths, commands, and expected outcomes; no `TODO`, `TBD`, or vague validation language remains.
- Type consistency: the plan consistently uses `_otlp_exporter_enabled`, `setup_tracing`, `OTEL_EXPORTER_ENABLED`, and `APP_ENV` across tests and implementation.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-02-test-otel-exporter-noise.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
