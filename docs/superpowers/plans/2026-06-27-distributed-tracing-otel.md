# Distributed Tracing via OpenTelemetry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add standard OpenTelemetry distributed tracing across the Spring Boot gateway and FastAPI agent while keeping existing Prometheus/Grafana metrics and business `traceId` compatibility.

**Architecture:** Spring Boot will keep acting as the gateway but will use Spring Boot's OpenTelemetry tracing support plus the auto-configured `WebClient.Builder` so outbound calls to Python automatically carry W3C trace context headers. FastAPI will initialize OpenTelemetry SDK + FastAPI instrumentation so incoming trace headers become server spans, and key workflow stages will be recorded as child spans. The existing business `traceId` stays in the payload and logs, but it will be derived from the active trace when available so operators can correlate logs, spans, and SSE events using one identifier.

**Tech Stack:** Spring Boot 3.5 tracing auto-configuration, Micrometer tracing bridge over OpenTelemetry, OTLP exporter, OpenTelemetry Python SDK, FastAPI instrumentation, OTel Collector, Grafana Tempo, existing Prometheus + Grafana.

---

### Task 1: Add Java tracing dependencies and config

**Files:**
- Modify: `pom.xml`
- Modify: `src/main/resources/application.yml`
- Create: `src/main/resources/logback-spring.xml`

- [ ] **Step 1: Write the failing test**

Create a Java test that expects the active trace ID resolver to fall back to a UUID-shaped value when there is no current span.

```java
@Test
void fallsBackToUuidWhenNoCurrentSpanExists() {
    String traceId = traceIdResolver.resolveCurrentTraceId();
    assertThat(traceId).matches("[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}");
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `JAVA_HOME="D:/Program Files/Java/jdk-23" mvn -Dtest=TraceIdResolverTest test`
Expected: FAIL because the resolver class does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Add the OTel tracing starter and OTLP exporter to `pom.xml`, configure `management.tracing.sampling.probability=1.0`, `management.tracing.propagation.type=w3c`, and `management.opentelemetry.tracing.export.otlp.endpoint=http://localhost:4318/v1/traces`. Add a `logback-spring.xml` pattern that prints `traceId` and `spanId`.

- [ ] **Step 4: Run test to verify it passes**

Run: `JAVA_HOME="D:/Program Files/Java/jdk-23" mvn -Dtest=TraceIdResolverTest test`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pom.xml src/main/resources/application.yml src/main/resources/logback-spring.xml src/test/java/com/yupi/yuaicodemother/monitor/TraceIdResolverTest.java src/main/java/com/yupi/yuaicodemother/monitor/TraceIdResolver.java
git commit -m "feat: add otel tracing foundation"
```

### Task 2: Make Java outbound calls trace-aware

**Files:**
- Modify: `src/main/java/com/yupi/yuaicodemother/core/python/PythonAiClient.java`
- Modify: `src/main/java/com/yupi/yuaicodemother/core/AiCodeGeneratorFacade.java`
- Modify: `src/main/java/com/yupi/yuaicodemother/service/impl/AppServiceImpl.java`
- Create: `src/main/java/com/yupi/yuaicodemother/monitor/TraceIdResolver.java`
- Create: `src/test/java/com/yupi/yuaicodemother/core/python/PythonAiClientTest.java`
- Create: `src/test/java/com/yupi/yuaicodemother/monitor/TraceIdResolverTest.java`

- [ ] **Step 1: Write the failing test**

Create a Java unit test that verifies `PythonAiClient` uses the injected `WebClient.Builder` instead of constructing its own builder, and that `streamCodeGen(...)` still serializes `traceId` into the request body.

```java
@Test
void streamCodeGenUsesInjectedBuilderAndIncludesTraceId() {
    // mock builder + request chain
    // assert body contains traceId and baseUrl is configured through injected builder
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `JAVA_HOME="D:/Program Files/Java/jdk-23" mvn -Dtest=PythonAiClientTest test`
Expected: FAIL because the client still instantiates its own builder.

- [ ] **Step 3: Write minimal implementation**

Inject `WebClient.Builder` into `PythonAiClient`, derive the current trace ID from Micrometer tracing when available, and keep the business `traceId` in the JSON body. Update `AppServiceImpl` to use the trace resolver instead of raw UUID generation so the business trace ID aligns with the active trace when one exists.

- [ ] **Step 4: Run test to verify it passes**

Run: `JAVA_HOME="D:/Program Files/Java/jdk-23" mvn -Dtest=PythonAiClientTest,TraceIdResolverTest test`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/main/java/com/yupi/yuaicodemother/core/python/PythonAiClient.java src/main/java/com/yupi/yuaicodemother/core/AiCodeGeneratorFacade.java src/main/java/com/yupi/yuaicodemother/service/impl/AppServiceImpl.java src/main/java/com/yupi/yuaicodemother/monitor/TraceIdResolver.java src/test/java/com/yupi/yuaicodemother/core/python/PythonAiClientTest.java src/test/java/com/yupi/yuaicodemother/monitor/TraceIdResolverTest.java
git commit -m "feat: propagate trace context through java gateway"
```

### Task 3: Add Python OpenTelemetry tracing

**Files:**
- Modify: `python-agent/pyproject.toml`
- Modify: `python-agent/server/main.py`
- Modify: `python-agent/monitoring.py`
- Modify: `python-agent/workflow/sse_stream.py`
- Modify: `python-agent/core/model_router.py`
- Create: `python-agent/tracing.py`
- Create: `python-agent/tests/test_tracing.py`

- [ ] **Step 1: Write the failing test**

Create a Python unit test that expects the new trace helper to prefer the current OpenTelemetry span trace ID and otherwise fall back to the request body trace ID.

```python
def test_resolve_trace_id_prefers_current_span():
    # current span context with trace id
    # assert helper returns the span trace id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd python-agent && PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_tracing.py -v`
Expected: FAIL because the helper module does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Add OpenTelemetry SDK/exporter/instrumentation dependencies, initialize FastAPI instrumentation in `server/main.py`, create a helper to resolve the active trace ID for logs and SSE events, and add spans around the workflow and model-router hot paths.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd python-agent && PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_tracing.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add python-agent/pyproject.toml python-agent/server/main.py python-agent/monitoring.py python-agent/workflow/sse_stream.py python-agent/core/model_router.py python-agent/tracing.py python-agent/tests/test_tracing.py
git commit -m "feat: add python otel tracing"
```

### Task 4: Add local observability stack for traces

**Files:**
- Modify: `docker-compose.monitoring.yml`
- Create: `otel-collector-config.yml`
- Create: `tempo.yaml`
- Modify: `guide/grafana-prometheus-guide.md`
- Modify: `guide/start-monitoring.bat`

- [ ] **Step 1: Write the failing test**

Add a lightweight config validation check or startup smoke test that verifies the new tracing stack files exist and the collector exposes OTLP HTTP on `4318`.

```bash
curl http://localhost:4318/v1/traces
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -f docker-compose.monitoring.yml config`
Expected: FAIL until the collector and Tempo services are added.

- [ ] **Step 3: Write minimal implementation**

Add OpenTelemetry Collector and Tempo services to the monitoring compose file, wire Grafana to Tempo, and document how to run the full stack locally.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -f docker-compose.monitoring.yml config`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add docker-compose.monitoring.yml otel-collector-config.yml tempo.yaml guide/grafana-prometheus-guide.md guide/start-monitoring.bat
git commit -m "feat: add local tracing stack"
```
