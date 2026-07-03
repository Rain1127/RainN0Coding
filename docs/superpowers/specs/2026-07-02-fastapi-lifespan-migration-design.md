# FastAPI Lifespan Migration Design

## Goal

Eliminate FastAPI `on_event` deprecation warnings in the Python agent test and harness runs by migrating the server startup and shutdown hooks in `python-agent/server/main.py` to a `lifespan` handler, without changing request behavior, tracing setup, or runtime resource ownership.

## Scope

This design covers:

- Python server lifecycle wiring in `python-agent/server/main.py`
- startup initialization currently performed in the `startup` event
- shutdown cleanup currently performed in the `shutdown` event
- a focused regression test in `python-agent/tests/test_internal_auth_and_concurrency.py`

This design does not cover:

- refactoring the server into an app factory
- changing tracing, monitoring, or auth behavior
- changing background cleanup behavior beyond moving it under lifespan
- changing Milvus, SQLite, or feedback tracker implementations

## Current Problem

`python-agent/server/main.py` still uses:

- `@app.on_event("startup")`
- `@app.on_event("shutdown")`

These hooks are deprecated in current FastAPI, and the existing focused verification runs emit repeated deprecation warnings during `TestClient`-based tests. The warnings are noisy, reduce confidence in regression output, and mask the signal from real failures.

## Chosen Approach

Use a single FastAPI `lifespan` async context manager and move the existing startup and shutdown logic into it with minimal structural change.

Why this approach:

- it matches current FastAPI guidance
- it keeps behavior localized to `server/main.py`
- it avoids broad app-construction refactors
- it preserves the current module import and test loading pattern used by `test_internal_auth_and_concurrency.py`

## Design Details

### Server Lifecycle

`python-agent/server/main.py` should:

- define an async lifespan context manager near the current startup/shutdown logic
- perform the current startup work before `yield`
- perform the current shutdown work in the `finally` block after `yield`
- construct `app = FastAPI(..., lifespan=lifespan)`

The existing responsibilities stay the same:

- initialize SQLite store
- ensure the code store directory exists
- initialize feedback tracker
- start the periodic quality cleanup task
- stop the cleanup task on shutdown
- close Milvus, SQLite, and feedback tracker resources on shutdown

### Behavior Preservation

The migration must preserve these behaviors:

- cleanup task is still created once during app startup
- cleanup task is cancelled on shutdown and awaited safely
- resource-close failures remain non-fatal
- logging messages remain materially equivalent
- route registration, middleware order, tracing setup, monitoring setup, and auth behavior stay unchanged

### Testing

Add a focused lifecycle regression test in `python-agent/tests/test_internal_auth_and_concurrency.py` that:

- loads `server.main` through the existing `load_main(...)` helper
- creates a `TestClient(main.app)` context
- exercises one lightweight request such as `GET /api/health`
- asserts no captured warning message contains the FastAPI `on_event is deprecated` text

This test should stay deterministic by reusing the existing fake store approach already used by the health-path tests.

## Alternatives Considered

### Option 1: Minimal lifespan migration

Recommended.

Pros:

- smallest safe change
- preserves existing import/test surface
- directly removes the deprecation source

Cons:

- keeps `server/main.py` as a large module

### Option 2: App factory refactor

Not recommended for this step.

Pros:

- cleaner long-term composition
- lifecycle wiring becomes easier to test in isolation

Cons:

- larger blast radius
- likely requires test harness rewiring
- mixes warning cleanup with broader server architecture change

## Acceptance Criteria

- `python-agent/server/main.py` no longer uses `@app.on_event("startup")` or `@app.on_event("shutdown")`
- server startup and shutdown behavior remains functionally equivalent
- the focused internal auth / concurrency test suite passes
- the harness suite passes
- the previous FastAPI `on_event` deprecation warnings are no longer emitted in the targeted verification runs

## Risks

- if lifecycle logic is moved carelessly, background cleanup may not start or stop correctly
- if the test relies on global module state, warning assertions could become flaky

Mitigations:

- keep the migration structural and shallow
- keep the test focused on the existing `TestClient` lifecycle path
- verify both the focused suite and the harness suite after the change
