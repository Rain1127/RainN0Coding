# Server Assembly Boundaries Design

## Goal

Reduce the structural complexity of `python-agent/server/main.py` by extracting only app-assembly concerns into focused modules, while preserving all current request behavior, route behavior, tracing behavior, middleware behavior, and lifecycle behavior.

## Scope

This design covers:

- minimal server-side boundary extraction around FastAPI app assembly
- lifecycle wiring extraction
- middleware registration extraction
- lightweight route registration extraction
- focused regression verification for existing server behavior

This design does not cover:

- moving `generate_code` business logic out of `main.py`
- changing request or response schemas
- changing tracing, auth, concurrency, or guardrail behavior
- introducing an app factory
- broad refactoring of `server/main.py` beyond assembly concerns

## Current Problem

`python-agent/server/main.py` currently mixes several responsibilities:

- FastAPI app construction
- lifespan resource management
- middleware definitions
- route registration
- request models
- heavy endpoint logic
- logging and tracing helpers

Even after the recent lifecycle migration, the file remains hard to scan because assembly concerns and request-handling concerns live together. That raises change risk: a small wiring change forces readers to re-parse large unrelated sections.

## Chosen Scope

Use the narrowest useful extraction:

1. move lifespan wiring into `server/lifespan.py`
2. move middleware registration into `server/middleware.py`
3. move lightweight route registration into `server/routes.py`
4. keep endpoint handler implementations, request models, and helper logic in `server/main.py`

This keeps the change small enough to verify safely while making the top-level assembly path much easier to read.

## Design Details

### Module Boundaries

#### `python-agent/server/lifespan.py`

Responsibility:

- own the FastAPI lifespan context manager
- own the cleanup task handle used by lifespan startup/shutdown

Exports:

- `lifespan`
- an accessor or module-level state shape needed only if existing tests must confirm cleanup-task reset

Behavior:

- preserve the exact startup and shutdown responsibilities currently implemented
- keep best-effort cleanup semantics
- keep logging materially equivalent

#### `python-agent/server/middleware.py`

Responsibility:

- define server middleware functions
- provide a single registration function that attaches them to the app in the intended order

Exports:

- `register_middleware(app: FastAPI) -> None`

Behavior:

- preserve the current middleware order
- preserve auth bypass rules, logging behavior, and CORS setup behavior
- avoid moving business logic out of the existing middleware bodies except as needed for extraction

#### `python-agent/server/routes.py`

Responsibility:

- register lightweight routes onto the app

Exports:

- `register_routes(app: FastAPI, *, generate_code_handler, route_code_gen_type_handler, health_handler) -> None`

Behavior:

- attach the existing route paths and methods
- keep handler implementations outside this module for now
- keep this module focused on route-to-handler wiring, not endpoint logic

### `python-agent/server/main.py`

After the extraction, `main.py` should remain the runtime entry module, but it should narrow to:

- imports
- logging/tracing formatter setup
- request/response models
- endpoint handler implementations
- app construction
- assembly calls:
  - `FastAPI(..., lifespan=lifespan)`
  - `setup_tracing(app)`
  - `setup_monitoring(app)`
  - `register_middleware(app)`
  - `register_routes(...)`
- `__main__` startup block

The heavy handler logic stays put for this step.

## Alternatives Considered

### Option 1: Minimal assembly extraction

Recommended.

Pros:

- smallest blast radius
- makes the top-level app wiring readable
- leaves risky endpoint logic untouched
- keeps existing tests close to current behavior

Cons:

- `main.py` still remains a substantial file
- route handlers are not yet isolated

### Option 2: Extract lightweight handlers too

Not chosen for this step.

Pros:

- slightly cleaner module ownership
- smaller `main.py`

Cons:

- begins mixing wiring cleanup with endpoint relocation
- raises chance of import-cycle or test rewiring issues

### Option 3: Full app-factory refactor

Not chosen.

Pros:

- strongest long-term architecture

Cons:

- much larger blast radius
- would likely force broad test changes
- unnecessary for the current readability goal

## Testing Strategy

Keep testing focused on regression safety, not architecture ceremony.

Required verification:

- existing server-focused tests continue to pass
- targeted tracing plus internal-auth suite continues to pass
- harness suite continues to pass

Add only minimal new tests if the extraction needs a direct assertion about module wiring behavior. Prefer preserving existing tests over inventing new structural-only tests.

## Acceptance Criteria

- `python-agent/server/lifespan.py`, `python-agent/server/middleware.py`, and `python-agent/server/routes.py` exist with focused responsibilities
- `python-agent/server/main.py` no longer contains inline lifespan definition or inline middleware registration bodies
- route registration is extracted, while existing handler implementations remain behaviorally unchanged
- no endpoint path, method, or response behavior changes
- focused server verification passes
- harness verification passes

## Risks

- imports may become tangled if extracted modules reach back into `main.py` carelessly
- middleware registration order could drift during extraction
- route registration helpers may accidentally change handler binding or metadata

Mitigations:

- keep extracted modules one-way and narrow
- pass handlers into `register_routes(...)` explicitly instead of importing them back from `main.py`
- preserve middleware registration order exactly
- verify with existing suites rather than trusting structural edits
