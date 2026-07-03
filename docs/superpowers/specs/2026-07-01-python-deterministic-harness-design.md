# Python Deterministic Harness Design

## Goal

Build the third production-hardening slice for the Python agent runtime: a deterministic, pytest-centered harness layer that makes local and CI verification predictable, fast to select, and easy to extend without changing the business runtime.

This slice focuses on test organization, shared fixtures, and repeatable execution commands for the Python agent only. It does not introduce a new test runner, a replay platform, or cross-service Java/Python orchestration.

## Scope

In scope:
- standard pytest markers for `unit`, `integration`, and `harness`
- shared `conftest.py` helpers for repeated setup patterns already emerging in the test suite
- deterministic test selection commands for local and CI use
- light cleanup of existing focused tests so they align with the new harness contract
- harness documentation updates

Out of scope:
- real-provider E2E tests
- a custom runner or orchestration framework
- Java-side harness unification
- large-scale test rewrites unrelated to deterministic execution
- flaky network-facing integration with external systems

## Context

The Python side now has several production-hardening focused suites:
- prompt, tool, and output guardrail tests
- FastAPI auth/concurrency tests
- workflow import smoke tests
- file-tool regression tests

These tests are useful, but they are still arranged mostly as individual files rather than as a coherent harness surface. That creates three problems:

1. it is not obvious which tests are pure unit tests versus integration-oriented runtime checks
2. setup logic like module reloads, temporary tool context, and fake memory is beginning to repeat
3. CI and local contributors do not yet have one stable mental model for "what should I run for fast confidence?"

## Approaches Considered

### Option 1: Light Pytest Organization Layer

Add markers, a minimal `conftest.py`, and clear commands while keeping the current files mostly intact.

Pros:
- smallest change surface
- low risk to working suites
- fastest path to repeatable CI usage

Cons:
- fixture reuse will improve, but not all duplication disappears immediately

### Option 2: Fixture-First Refactor

In addition to markers, aggressively extract shared fake workflow, fake memory, fake config, and guardrail helpers into a broader test support layer.

Pros:
- cleaner long-term test authoring
- less duplication across future tests

Cons:
- larger refactor while the harness contract is still settling
- higher risk of destabilizing already-green suites

### Option 3: Full Harness Framework

Introduce a custom execution layer or strongly opinionated harness package on top of pytest.

Pros:
- maximum future extensibility

Cons:
- overbuilt for the current project state
- unnecessary divergence from existing pytest usage

## Recommendation

Use Option 1 now.

The right move for this repo is to stabilize the harness contract first, not to build an internal testing platform. A thin pytest organization layer gives immediate production value with limited risk, and it keeps the door open for a later fixture-heavy pass if the test surface keeps growing.

## Target Design

### 1. Test Taxonomy

The deterministic Python harness will use exactly three marker layers:

- `unit`
  - pure rule evaluation
  - config parsing
  - isolated helper behavior
  - no FastAPI app startup
  - no workflow streaming loop

- `integration`
  - FastAPI `TestClient`
  - SSE stream wrapper behavior
  - file tool wiring
  - module-to-module runtime wiring
  - fake dependencies are allowed, but the test still exercises real boundaries between modules

- `harness`
  - focused production-hardening verification entrypoints
  - multi-file confidence suites used in docs and CI
  - smoke-level deterministic checks that define "release confidence" for the Python agent slice

The rule of thumb:
- if the test asserts one module's internal logic, it is `unit`
- if it crosses real runtime boundaries inside Python, it is `integration`
- if it is part of the standard production-hardening verification command, it is `harness`

Some tests may intentionally carry both `integration` and `harness`. That is acceptable when the file both exercises runtime wiring and belongs to the focused release-confidence set.

### 2. Shared Fixture Layer

Create a lightweight [`python-agent/tests/conftest.py`](D:/RainN0Coding/python-agent/tests/conftest.py) with only the shared setup patterns already proven useful.

Expected helpers:
- guardrail module reload helper
- temporary project/tool context helper
- fake conversation memory helper
- optional common JSON event collector helper for SSE-oriented tests

This file should stay intentionally small. It is not a dumping ground for every fake object in the project. Only move helpers that are either already duplicated or clearly central to deterministic harness behavior.

### 3. Pytest Configuration

Register the markers in [`python-agent/pyproject.toml`](D:/RainN0Coding/python-agent/pyproject.toml) under pytest configuration so marker use is explicit and warning-free.

At minimum, the configuration should:
- declare `unit`, `integration`, and `harness`
- support readable `-m` selection in local and CI commands

No new plugins are required for this slice.

### 4. Existing Test File Mapping

Initial mapping should be conservative and based on actual behavior:

- [`python-agent/tests/test_guardrails_prompt.py`](D:/RainN0Coding/python-agent/tests/test_guardrails_prompt.py)
  - primarily `unit`
  - some tests may also be `integration` if they intentionally verify engine routing rather than pure prompt classification

- [`python-agent/tests/test_guardrails_tools.py`](D:/RainN0Coding/python-agent/tests/test_guardrails_tools.py)
  - `integration`
  - `harness`

- [`python-agent/tests/test_guardrails_output.py`](D:/RainN0Coding/python-agent/tests/test_guardrails_output.py)
  - `integration`
  - `harness`

- [`python-agent/tests/test_internal_auth_and_concurrency.py`](D:/RainN0Coding/python-agent/tests/test_internal_auth_and_concurrency.py)
  - `integration`
  - `harness`

- [`python-agent/tests/test_tools.py`](D:/RainN0Coding/python-agent/tests/test_tools.py)
  - `integration`
  - optionally `harness` if it remains part of the standard focused production suite

- [`python-agent/tests/test_workflow_imports_unittest.py`](D:/RainN0Coding/python-agent/tests/test_workflow_imports_unittest.py)
  - `harness`
  - not necessarily `integration`, because it is mostly a wiring smoke test rather than runtime boundary behavior

This mapping should be explicit in code through decorators rather than implied by filename.

### 5. Deterministic Execution Contract

The harness must support three stable command shapes:

1. fast unit confidence
```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest -m unit -v
```

2. runtime wiring confidence
```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest -m integration -v
```

3. focused production harness
```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest -m harness -v
```

The third command becomes the canonical Python deterministic harness command for this production-hardening slice.

### 6. CI Intent

This slice does not need a new CI system integration file yet, but it should leave the repo ready for one. The outcome should make it trivial for CI to choose:

- `unit` on fast paths
- `integration` on broader validation
- `harness` on release-quality focused validation

That means the marker contract and commands must be stable, documented, and not dependent on hidden local state.

### 7. Error Handling and Stability Rules

The harness should bias toward deterministic fakes over real external dependencies.

Rules:
- prefer fake workflow generators over real model calls
- prefer fake memory/context over real backing services
- prefer temp directories over fixed filesystem state
- avoid order-dependent tests
- avoid assertions that depend on wall-clock timing except where timing is the subject under test
- do not make the harness require Redis, Milvus, or external LLM providers for the focused production command

### 8. Documentation

Update [`docs/production-hardening-harness.md`](D:/RainN0Coding/docs/production-hardening-harness.md) so the Python section clearly explains:
- what each marker means
- which command is the canonical focused harness command
- which focused files are currently included
- what result is expected

The doc should stay operator-oriented and command-first.

## File Plan

Expected files to modify or create:

- modify [`python-agent/pyproject.toml`](D:/RainN0Coding/python-agent/pyproject.toml)
  - add pytest marker registration

- create [`python-agent/tests/conftest.py`](D:/RainN0Coding/python-agent/tests/conftest.py)
  - minimal shared deterministic helpers

- modify selected files under [`python-agent/tests/`](D:/RainN0Coding/python-agent/tests)
  - add markers
  - remove small duplicated setup where clearly replaced by `conftest.py`

- modify [`docs/production-hardening-harness.md`](D:/RainN0Coding/docs/production-hardening-harness.md)
  - document unit/integration/harness execution model

- modify [`.planning/2026-06-30-production-hardening/progress.md`](D:/RainN0Coding/.planning/2026-06-30-production-hardening/progress.md)
  - record area 3 implementation and verification evidence

## Testing Strategy

Implementation should be driven by deterministic verification:

1. add pytest marker configuration
2. mark current focused files
3. add minimal shared fixtures
4. run direct file suites to ensure no regression
5. run marker-selected suites:
   - `pytest -m unit -v`
   - `pytest -m integration -v`
   - `pytest -m harness -v`

Success means:
- marker selection works without unknown-marker warnings
- current focused suites remain green
- deterministic harness command becomes simpler and clearer than the current file-list-only approach

## Risks and Mitigations

Risk: over-classifying too early and mislabeling tests  
Mitigation: use conservative markers and only tag files whose behavior is already understood

Risk: `conftest.py` becomes a vague shared utility bucket  
Mitigation: only extract helpers already duplicated or central to deterministic harness setup

Risk: existing green tests break from fixture refactors  
Mitigation: keep fixture extraction shallow and rerun both file-based and marker-based commands

Risk: documentation drifts from actual command behavior  
Mitigation: verify the documented commands exactly as written before closing the task

## Acceptance Criteria

This slice is complete when:
- pytest markers `unit`, `integration`, and `harness` are registered
- focused Python production-hardening tests are explicitly categorized
- minimal shared deterministic fixtures exist in `conftest.py`
- marker-based commands run successfully
- harness documentation reflects the new execution model
- progress tracking records actual verification results
