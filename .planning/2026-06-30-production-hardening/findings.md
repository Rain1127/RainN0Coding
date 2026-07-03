# Production Hardening Findings

## Existing Audit Context

- Root planning files contain a completed code health audit with findings around unauthenticated version CRUD, static path traversal risk, unsafe sort fields/page sizes, weak password hashing, CORS/auth risks, Python service exposure, Python tool path containment gaps, builder import failure, and subprocess shell usage.
- Worktree is dirty with many modified/deleted/untracked files. Avoid reverting or broad cleanup.

## Current Orientation

- Java chat endpoint streams SSE through `AppController.chatToGenCode` and `AppServiceImpl.chatToGenCode`.
- `AppServiceImpl.chatToGenCode` uses a Redisson lock keyed by `appId:userId` with `tryLock(0, 300s)` to reject concurrent chats for the same app/user.
- Java saves the user chat before Python generation and writes a generic AI completion message when the stream completes; there is no request idempotency key or persisted generation job state visible in this path.
- `PythonAiClient.streamCodeGen` posts directly to `/api/generate-code`; no service token, request timeout, retry policy, or request idempotency metadata is visible in the client.
- Python FastAPI allows all CORS origins and exposes `/api/generate-code` with no Java-to-Python authentication guard in the inspected file.
- Python `stream_workflow` enriches prompt with conversation memory and emits JSON events, but cancellation, timeout budgets, and payload/file-size caps are not visible in the inspected path.
- `ModelRouter` has fallback and circuit breaker support; it lacks visible concurrency semaphores, retry jitter, provider-level budgets, and typed failure classification in the inspected file.

## Production Hardening Implications

- Interface idempotency should likely live at Java gateway level with Redis/MySQL state and be propagated to Python as `requestId`/`idempotencyKey`.
- High concurrency should combine admission control, bounded queues, per-user/app locks, distributed limits, WebClient timeouts, Python semaphores, and load-shedding SSE events.
- Harness engineering should include unit, integration, fake Python SSE server, fake LLM provider, security path tests, and k6/JMeter-style smoke load tests.
- Agent guardrails should centralize path containment, command allowlists, prompt/file-size limits, generated artifact validation, secret scanning, and Java-to-Python service auth.
- HA/resilience should build on existing `ModelRouter` with request budgets, failover classification, health/readiness endpoints, dead-letter/replay semantics, and degraded responses.
