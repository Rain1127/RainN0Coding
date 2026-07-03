# Generate Code Orchestrator Design

## Goal

Lower the operational and change risk of the `generate_code` path by extracting its orchestration logic out of `python-agent/server/main.py` into a focused server-side orchestrator module, while preserving current HTTP behavior, SSE behavior, guardrail behavior, concurrency control, metrics, and request-status attribution.

## Scope

This design covers:

- extracting only the `generate_code` orchestration logic
- moving guardrail evaluation and blocked-response construction into a focused orchestration module
- moving overload detection plus semaphore acquire/release lifecycle into the orchestration module
- moving SSE status attribution and `record_request(...)` lifecycle into the orchestration module
- keeping `EventSourceResponse(...)` construction in `server/main.py`
- adding focused regression tests for the new orchestration boundary

This design does not cover:

- changing request or response schemas
- changing route paths or methods
- moving `route-codegen-type` into the same service layer
- changing the workflow engine or `stream_workflow(...)` contract
- adding timeouts, retries, circuit breakers, or cancellation policy changes in this step
- broad refactoring of other handlers

## Current Problem

`python-agent/server/main.py` still contains a dense, high-risk orchestration block inside `generate_code(...)`. That handler currently mixes:

- HTTP entry logic
- prompt guardrail evaluation
- overload detection
- semaphore lifecycle management
- workflow streaming
- SSE event status classification
- metrics increment/decrement
- final request-status persistence

That makes the hottest production path harder to reason about and harder to harden. A small change to overload behavior or status attribution currently requires editing the HTTP handler directly, which increases regression risk.

## Chosen Scope

Use the smallest useful extraction:

1. create a narrow `generate_code_orchestrator` module
2. move orchestration concerns there
3. keep request models and `EventSourceResponse(...)` in `server/main.py`
4. keep route registration and other handlers unchanged in this step

This keeps the boundary clean without over-abstracting too early.

## Design Details

### Module Boundary

Create:

- `python-agent/server/generate_code_orchestrator.py`

Responsibility:

- own the orchestration flow for `generate_code`
- evaluate guardrails and construct immediate blocked responses
- manage overload detection and semaphore lifecycle
- wrap `stream_workflow(...)` into an event generator with status attribution
- manage metric increment/decrement and final `record_request(...)`

Exports:

- a single orchestration entrypoint for `generate_code`
- small result types or a narrow result shape that lets `main.py` distinguish:
  - immediate JSON response
  - streamable event generator

This module should not own:

- FastAPI route decorators
- request model classes
- `EventSourceResponse`
- route registration

### `server/main.py` After Extraction

`python-agent/server/main.py` should remain the HTTP entry module. After this extraction it should still own:

- request models
- app assembly
- route handlers
- `EventSourceResponse(...)` construction

But the `generate_code(...)` handler should become thin:

1. receive `CodeGenRequest`
2. call the orchestrator with the request plus required dependencies
3. if the result is an immediate JSON response, return `JSONResponse(...)`
4. otherwise return `EventSourceResponse(...)` around the returned generator

That keeps HTTP concerns in `main.py` and orchestration concerns in the new module.

### Orchestrator Interface

Use a narrow entrypoint such as:

`orchestrate_generate_code(request, *, semaphore, stream_workflow, record_request, active_requests_metric)`

The exact helper names may vary, but the boundary should preserve these behaviors:

- guardrail-block path returns an immediate response payload and status code
- overload path returns an immediate response payload and status code
- success path returns an async event generator
- event generator must preserve existing SSE payload passthrough behavior

The interface should avoid importing `server.main` back into the orchestrator.

### Data Flow

#### Immediate failure path

For guardrail-blocked or overloaded requests:

1. orchestrator resolves the decision
2. orchestrator returns an immediate response description
3. `main.py` converts it to `JSONResponse(...)`

#### Stream path

For accepted requests:

1. orchestrator acquires concurrency permit
2. orchestrator increments active-request metrics
3. orchestrator yields SSE events from `stream_workflow(...)`
4. orchestrator observes event payloads and derives final status
5. orchestrator decrements metrics, records request status, and releases permit in `finally`

### Error Handling

Behavior must stay materially equivalent:

- guardrail-blocked requests still return HTTP 400 with `status="guardrail_blocked"`
- overloaded requests still return the configured overload status code with `status="overloaded"`
- workflow exceptions still result in final status `error`
- SSE event-derived statuses such as `overloaded`, `failed`, and `partial_success` still override the default `success` outcome exactly as they do now

The extraction must not introduce permit leaks, skipped metrics decrements, or missed `record_request(...)` calls.

### Testing Strategy

Keep tests focused on the new boundary.

#### Main-module tests

Preserve or add lightweight tests that prove:

- `server.main` imports the orchestration entrypoint
- the handler still exposes the same external HTTP behavior

#### Orchestrator tests

Add focused unit-style tests for:

- guardrail-block path does not call workflow
- overload path does not acquire permit or call workflow
- accepted stream path acquires and releases permit correctly
- accepted stream path decrements metrics and records final status in `finally`
- SSE `error` and non-success `done` events still map to the same persisted statuses

Prefer dependency injection over patching deep module globals where practical.

## Alternatives Considered

### Option 1: Narrow orchestrator extraction

Recommended.

Pros:

- smallest blast radius
- reduces complexity on the hottest handler path
- isolates high-risk state transitions into a testable module
- preserves current HTTP structure

Cons:

- `main.py` still owns request models and response wrapping
- only solves `generate_code` for now

### Option 2: Move `EventSourceResponse(...)` into the orchestrator

Not chosen.

Pros:

- thinner handler

Cons:

- mixes HTTP response concerns with orchestration concerns
- makes orchestrator less reusable and harder to unit test cleanly

### Option 3: Build a shared server pipeline for multiple endpoints

Not chosen.

Pros:

- stronger long-term uniformity

Cons:

- bigger blast radius
- higher risk of coupling unrelated endpoints too early

## Acceptance Criteria

- `python-agent/server/generate_code_orchestrator.py` exists and owns `generate_code` orchestration concerns
- `python-agent/server/main.py` no longer contains inline guardrail, overload, permit lifecycle, and request-status orchestration for `generate_code`
- `server/main.py` still owns request models and `EventSourceResponse(...)`
- runtime behavior of the `generate_code` endpoint remains unchanged
- focused tracing and internal-auth regression tests pass
- harness verification continues to pass

## Risks

- permit lifecycle may be broken during extraction
- final request status may drift if event classification changes subtly
- metric decrement and release logic may be skipped on exceptions
- an overly broad result abstraction may make the first extraction harder than necessary

Mitigations:

- keep the orchestrator interface narrow
- preserve the existing status-classification logic exactly, then refactor only if tests stay green
- verify release/decrement/record behavior with focused tests
- keep `EventSourceResponse(...)` in `main.py` to avoid mixing layers
