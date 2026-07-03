# Test OTLP Exporter Noise Design

## Goal

Eliminate OpenTelemetry OTLP exporter connection-noise during Python test runs without changing the default tracing behavior for development or production environments.

## Scope

This design covers:

- Python-side tracing setup in `python-agent/tracing.py`
- test-environment exporter disable semantics
- a deterministic tracing regression test

This design does not cover:

- changing Java tracing behavior
- changing default OTLP behavior for development or production
- redesigning tracing middleware or span attributes

## Current Problem

`python-agent/tracing.py` always installs an `OTLPSpanExporter` pointing at `http://localhost:4318/v1/traces` unless the caller completely bypasses `setup_tracing`.

Most deterministic tests already monkeypatch tracing setup, but not every path avoids exporter initialization. As a result, test runs can finish successfully while background exporter threads still emit noisy connection-failure logs against `localhost:4318`.

This noise pollutes regression output and makes it harder to distinguish real failures from environment chatter.

## Design Approach

Use a narrow exporter-enable gate.

The tracing module should keep its current middleware and tracer setup, but exporter registration should become conditional:

- `OTEL_EXPORTER_ENABLED=false` disables OTLP exporter registration
- test environment should default to exporter disabled
- development, local, and production should keep the current default behavior unless the explicit flag disables it

This preserves current runtime semantics while giving tests and CI a clean, deterministic no-export mode.

## Configuration Rules

Add one Python config-level environment rule:

- `OTEL_EXPORTER_ENABLED`

Behavior:

- if explicitly set to `false`, do not register `OTLPSpanExporter`
- if explicitly set to `true`, register exporter normally
- if unset and `APP_ENV=test`, treat it as disabled
- if unset in other environments, treat it as enabled

This rule should live close to tracing setup logic so it remains easy to reason about and easy to override in targeted tests.

## Implementation Shape

### Tracing Module

`python-agent/tracing.py` should:

- compute whether OTLP export is enabled before creating `OTLPSpanExporter`
- still initialize tracer provider and request middleware cleanly when exporter is disabled
- avoid starting background export work when disabled

The middleware behavior, trace-id resolution, and span helper APIs should remain unchanged.

### Tests

`python-agent/tests/test_tracing.py` should gain a deterministic regression check proving:

- when `APP_ENV=test` and no explicit override is set, tracing setup does not install OTLP exporter
- explicit `OTEL_EXPORTER_ENABLED=true` still allows exporter setup

Where possible, the test should inspect tracing setup behavior via monkeypatching rather than attempting real network calls.

## Acceptance Criteria

- Python test runs no longer emit OTLP connection-failure noise by default in `APP_ENV=test`
- development and production tracing behavior remains unchanged unless explicitly disabled
- tracing middleware still initializes successfully when exporter is disabled
- deterministic tracing regression tests pass without depending on a live collector

## Risks

- if the disable gate is implemented too broadly, local observability could silently disappear outside tests
- if tests rely on global tracer provider state, regression coverage could become order-sensitive

Mitigation:

- keep the environment rule narrow and explicit
- test the enable/disable decision directly with monkeypatching
