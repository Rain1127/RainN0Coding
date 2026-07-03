# Production Baseline Design

## Goal

Build the first production-hardening slice for the AI code generation platform without changing the user-facing SSE workflow. This slice focuses on interface idempotency, high-concurrency admission control, Java-to-Python service authentication, timeout/retry behavior, and a repeatable harness test baseline.

## Scope

This design covers:

- Java gateway idempotency for app creation, app deployment, and AI code-generation SSE startup.
- Java-side concurrency admission for expensive AI generation work.
- Python-side service authentication and local concurrency protection.
- Java WebClient reliability settings for the Python Agent.
- Harness tests that can prove the new behavior without calling real LLM providers.

This design deliberately does not cover:

- Replacing the current SSE flow with a full async job queue.
- Introducing Kafka, RabbitMQ, or a distributed workflow engine.
- Full Agent tool sandboxing, command allowlists, secret scanning, or generated-code policy gates.
- Full model-provider high availability beyond the existing Python model router.
- Frontend UX redesign.

## Current System Context

The current request path is:

`Frontend -> Java /api/app/chat/gen/code -> AppServiceImpl -> AiCodeGeneratorFacade -> PythonAiClient -> Python FastAPI /api/generate-code -> LangGraph workflow -> SSE stream back`

The repository already has some production-oriented building blocks:

- Redisson-backed rate limiting through `@RateLimit`.
- A per-user/per-app Redisson lock in `AppServiceImpl.chatToGenCode`.
- Python model fallback and circuit-breaker logic in `core/model_router.py`.
- Prometheus and trace plumbing in both Java and Python.

The missing baseline pieces are:

- No request idempotency contract.
- No Java-to-Python shared-secret authentication.
- No bounded AI-generation admission control across all app/user pairs.
- No explicit WebClient timeout/retry/error mapping for the Python Agent path.
- No Python-side semaphore to prevent local Agent overload.
- No fake-provider harness that can test SSE, idempotency, timeout, and overload behavior deterministically.

## Design Approach

Use a gateway-first production baseline.

Java remains the primary external API boundary. It owns HTTP authentication, user identity, idempotency keys, request admission, and stable error semantics. Python remains the Agent execution engine and adds only the controls it needs to reject unauthorized internal traffic and avoid local overload.

This keeps the first production slice small enough to test while still improving real operational safety.

## Idempotency Contract

Clients may send `Idempotency-Key` for selected mutating or expensive endpoints:

- `POST /api/app/add`
- `POST /api/app/deploy`
- `GET /api/app/chat/gen/code`

The key is scoped by:

- login user id
- endpoint operation name
- normalized request fingerprint
- raw idempotency key

The request fingerprint prevents accidental key reuse across different payloads. If the same key is reused with a different app id, prompt, or request body, Java returns a parameter error instead of reusing the prior result.

### State Model

Redis stores a compact idempotency record:

```json
{
  "status": "PROCESSING|SUCCESS|FAILED",
  "fingerprint": "sha256",
  "httpStatus": 200,
  "resultJson": "{}",
  "errorCode": 0,
  "errorMessage": "",
  "createdAt": "2026-06-30T00:00:00Z",
  "updatedAt": "2026-06-30T00:00:00Z"
}
```

Suggested TTLs:

- `PROCESSING`: 10 minutes for normal REST calls, 30 minutes for AI generation.
- `SUCCESS`: 24 hours.
- `FAILED`: 5 minutes.

### Endpoint Behavior

For `POST /app/add` and `POST /app/deploy`:

- First request stores `PROCESSING`, executes the service method, then stores `SUCCESS` with the response payload.
- Duplicate with the same key and fingerprint returns the cached success response.
- Duplicate while processing returns `TOO_MANY_REQUEST` or a dedicated `REQUEST_IN_PROGRESS` error if that code exists when implemented.
- Duplicate after failure returns the previous error for the short failure TTL.

For `GET /app/chat/gen/code`:

- The idempotency key prevents starting a second generation for the same user/app/message.
- Because replaying a completed SSE stream from Redis would require storing potentially large code chunks, phase 1 does not replay the whole stream.
- A duplicate in `PROCESSING` state returns a structured SSE `error` event and `done` event with `status="duplicate_in_progress"`.
- A duplicate in `SUCCESS` state returns a short structured SSE event telling the client the generation already completed, then `done`.
- The original stream still runs normally.

## High-Concurrency Admission Control

Keep the existing per-user/per-app chat lock and add a global AI-generation permit.

Java uses Redisson `RSemaphore` or `RPermitExpirableSemaphore` with a configurable permit count:

- property: `ai.codegen.max-concurrent-requests`
- default: `8`
- Redis key: `ai:codegen:permits`
- wait time: `0` seconds in phase 1, so overload fails fast instead of queueing unbounded requests.
- lease time: slightly above expected generation budget, for example `30m`.

Behavior:

- If no permit is available, Java returns an SSE `error` event and `done` event with `status="overloaded"`.
- The permit is released in `doFinally`, covering completion, cancellation, and errors.
- Existing `ai:chat:lock:{appId}:{userId}` continues to reject concurrent generation for the same app/user.

Python also adds a local `asyncio.Semaphore`:

- setting: `AGENT_MAX_CONCURRENT_REQUESTS`
- default: `4`
- If the semaphore cannot be acquired immediately, return HTTP 429 or an SSE error before starting the LangGraph workflow.

Java and Python limits are intentionally separate. Java protects the platform entry point; Python protects the Agent process when called directly or when multiple Java instances exist.

## Java-to-Python Service Authentication

Add an internal shared token:

Java config:

```yaml
python:
  ai:
    base-url: http://localhost:8000
    internal-token: ${PYTHON_AI_INTERNAL_TOKEN:}
```

Python config:

```env
INTERNAL_API_TOKEN=...
```

Java sends:

- `X-Internal-Token`
- `X-Request-Id`
- `X-Idempotency-Key` when available
- existing trace id in body remains for compatibility

Python middleware rejects protected `/api/*` endpoints except health/readiness when the token is configured and the header does not match.

Development behavior:

- If the token is blank in both services, local development can still run.
- Production deployment must set the token. The deployment runbook should document this requirement.

## WebClient Reliability

`PythonAiClient` should use a dedicated WebClient with:

- connection timeout
- response timeout
- read/write timeout
- bounded in-memory buffer
- trace/request headers
- error mapping for 401, 429, 5xx, and network timeouts

Recommended properties:

```yaml
python:
  ai:
    connect-timeout-ms: 3000
    response-timeout-seconds: 1800
    route-timeout-seconds: 30
```

Retry policy:

- `routeCodeGenType` may retry once on connection timeout or 5xx, then fall back to `VUE_PROJECT`.
- streaming generation should not blindly retry after the Python workflow starts, because that can create duplicate side effects. It should rely on idempotency and admission control instead.

## Request Identifiers

Java generates or resolves:

- `traceId`: existing tracing flow.
- `requestId`: a stable UUID per incoming API request, or the idempotency record id when provided.
- `idempotencyKey`: optional client key.

Python includes `request_id` and `trace_id` in emitted events where practical. This makes harness assertions and production log correlation easier.

## Harness Engineering

### Java Harness

Add tests that avoid real Python and real LLM calls:

- `PythonAiClientTest`: use a mock HTTP server or custom ExchangeFunction to verify headers, timeout mapping, 401/429 handling, and SSE body parsing.
- `IdempotencyServiceTest`: verify first execution, duplicate success replay, fingerprint mismatch, processing rejection, and failure TTL behavior.
- `AppControllerProductionBaselineTest`: verify idempotency header plumbing and duplicate SSE rejection using mocked services.
- `AiGenerationConcurrencyTest`: verify permit acquisition and release on complete/error/cancel.

Where Redis is required, prefer a fake abstraction for unit tests and keep Redisson integration tests profile-gated.

### Python Harness

Add FastAPI tests with `pytest` and `httpx`/TestClient:

- request without internal token is rejected when token is configured.
- request with valid token succeeds.
- health endpoint remains accessible.
- local semaphore overload returns structured rejection.
- generated SSE events include request id and trace id.

Mock `stream_workflow` so tests do not call real LLMs.

### Smoke Load Harness

Add a minimal script or documented command for concurrent local smoke testing:

- 1 request succeeds.
- duplicate idempotency key does not start a second workflow.
- concurrent requests above the configured permit limit fail fast with overload.

This can be a Java test first; k6/JMeter can come later.

## Error Semantics

Use structured, user-safe error messages:

- `duplicate_in_progress`: same idempotency key is already running.
- `duplicate_completed`: same idempotency key already completed.
- `overloaded`: platform is at generation capacity.
- `python_unauthorized`: Java/Python token mismatch.
- `python_timeout`: Python Agent did not respond within the configured budget.
- `python_unavailable`: connection refused, DNS failure, or 5xx after allowed fallback.

For SSE, emit:

```json
{"type":"error","status":"overloaded","message":"AI generation capacity is full. Please retry later.","request_id":"...","trace_id":"..."}
```

Then emit:

```json
{"type":"done","status":"overloaded","request_id":"...","trace_id":"..."}
```

## Configuration

Java:

- `python.ai.internal-token`
- `python.ai.connect-timeout-ms`
- `python.ai.response-timeout-seconds`
- `python.ai.route-timeout-seconds`
- `ai.codegen.max-concurrent-requests`
- `ai.codegen.permit-lease-minutes`
- `idempotency.enabled`
- `idempotency.success-ttl-hours`
- `idempotency.processing-ttl-minutes`
- `idempotency.failure-ttl-minutes`

Python:

- `INTERNAL_API_TOKEN`
- `AGENT_MAX_CONCURRENT_REQUESTS`
- `AGENT_OVERLOAD_STATUS_CODE`

## Rollout Plan

1. Add Java idempotency and concurrency abstractions with unit tests.
2. Wire Java app endpoints through those abstractions.
3. Harden `PythonAiClient` headers, timeouts, and error mapping.
4. Add Python internal-token middleware and local semaphore.
5. Add harness tests for Java and Python.
6. Update deployment documentation with required token and concurrency settings.

## Acceptance Criteria

- Repeating `POST /app/add` with the same `Idempotency-Key` and same body returns one logical app creation result.
- Reusing the same idempotency key with a different body is rejected.
- Repeating a running code-generation SSE request with the same idempotency key does not start a second Python workflow.
- When the Java AI permit limit is reached, additional generation requests fail fast with a structured SSE overload response.
- Java sends `X-Internal-Token` to Python when configured.
- Python rejects protected API requests with an invalid internal token.
- Route-codegen fallback still returns the default generation type when Python routing fails.
- Harness tests pass without calling real LLM providers.

## Risks

- SSE completion replay is intentionally shallow in phase 1. Users get a completed notice, not a replayed full stream.
- Redis outages can affect idempotency and concurrency. Implementation should fail closed for expensive generation and may fail open only for low-risk app creation if explicitly chosen in the implementation plan.
- Existing dirty worktree changes may overlap with touched files. Implementation must inspect each file before editing and avoid reverting user-owned changes.
