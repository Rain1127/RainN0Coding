# Agent Availability & Resilience Design

## Goal

Build the fourth production-hardening slice for the Python agent runtime: high availability and risk resistance after the existing prompt/tool/output guardrails are in place.

This slice prioritizes uninterrupted, explainable responses over strict all-or-nothing execution. When some agent phases or model calls fail, the system should degrade gracefully and return the best editable code artifact available, together with explicit risk and recovery signals.

## Scope

This design covers:

- Python-side agent execution availability for the LangGraph workflow.
- Failure classification for model and agent runtime errors.
- Graceful degradation and fallback behavior per workflow phase.
- Partial-result return semantics when code already exists but late phases fail.
- SSE contract enhancements for degraded and partial-success outcomes.
- Deterministic harness coverage for degraded-success and partial-success flows.

This design deliberately does not cover:

- Java-to-Python transport reliability changes already addressed in the production baseline.
- Redis, Milvus, or external infrastructure outage recovery as first-class targets in this slice.
- Client disconnect recovery, resumable SSE replay, or async job queues.
- Disk-full handling, OS-level process supervision, or container orchestration.
- Frontend redesign of degraded-result UX beyond consuming richer SSE semantics.

## Current System Context

The Python workflow today is:

`intent_agent -> pm_agent -> architect_agent -> image_collector_agent + coder_agent -> reviewer_agent -> builder_agent`

The repository already contains some resilience-oriented building blocks:

- `core/model_router.py` with candidate fallback and per-model circuit breakers.
- `agents/intent_agent.py` with a rule-based fallback path.
- `memory/conversation_memory.py` with in-memory fallback when Redis is unavailable.
- `server/main.py` with internal auth, local concurrency protection, and structured overload handling.
- `workflow/sse_stream.py` with structured SSE progress emission.

The missing availability layer is inside the workflow itself:

- Most phases still fail the run too bluntly when they time out or raise.
- There is no unified failure policy describing which phases are hard-stop versus degradable.
- There is no stable final status model for `degraded_success` or `partial_success`.
- There is no canonical partial-result assembly path when reviewer or builder fails after code generation.
- Harness coverage exists for guardrails and baseline concurrency, but not for workflow degradation semantics.

## Design Approach

Use workflow-internal graded degradation with a unified finalizer.

Instead of wrapping the whole system in a second orchestration layer, this slice strengthens the existing workflow with:

1. a phase-level failure policy,
2. a guarded execution wrapper,
3. partial-result assembly rules,
4. an enhanced SSE finalization contract.

This approach keeps the implementation aligned with the current LangGraph architecture, minimizes duplicate state machines, and directly addresses the main production risk: local agent or model failure causing the entire code-generation run to collapse unnecessarily.

## Availability Strategy

This slice chooses:

- **Availability priority:** prefer uninterrupted completion over strict all-or-nothing correctness.
- **Return priority:** prefer returning editable partial code over returning only failure metadata.
- **Failure domain priority:** first cover model and agent runtime failure inside `python-agent`.

That means the system should:

- keep running when non-core phases fail,
- continue after soft failures using bounded fallback behavior,
- return partial code if the system already has a usable `code_files` set,
- fail only when no safe code artifact exists or a core phase cannot produce required structure.

## Failure Classification Model

Each phase failure is classified along these axes:

- `phase`: which workflow phase failed
- `reason_code`: stable machine-readable code such as `reviewer_timeout` or `pm_exception`
- `error_type`: `timeout`, `exception`, `fallback_exhausted`, or `validation_failure`
- `retryable`: whether the phase can be retried inside the workflow
- `degradable`: whether the workflow may continue
- `partial_code_safe`: whether current code artifacts may still be returned

This classification becomes the shared language across workflow state, SSE, audit logs, and tests.

## Phase Availability Matrix

### Hard-Fail Phases

- `coder_agent`
- `architect_agent` when it cannot produce even a minimum viable file plan

These phases form the minimum code-generation backbone. If they fail before any usable code exists, the workflow ends with `failed`.

### Soft-Fail Continue Phases

- `intent_agent`
- `pm_agent`
- `image_collector_agent`
- `reviewer_agent`
- memory context loading
- RAG retrieval steps

These phases may degrade without stopping the run. Their failures should emit warnings, update degraded state, and continue with fallback data or reduced context.

### Soft-Fail Partial-Success Phase

- `builder_agent`

If code generation succeeded but validation, install, or build checks fail, the run should complete as `partial_success` rather than `failed`.

## Phase Fallback Rules

### Intent

If the intent LLM path fails or times out:

- use the existing rule-based intent fallback,
- set `degraded=true`,
- append `intent_fallback_used` or a more specific reason such as `intent_timeout`,
- continue normally.

### PM

If `pm_agent` fails:

- synthesize a minimal PRD skeleton from the raw user request and `code_gen_type`,
- include only essential structure needed by downstream phases,
- mark the run degraded.

### Architect

If `architect_agent` fails:

- try to synthesize a minimum file-plan skeleton from the available PRD or request context,
- if a minimum viable architecture can be assembled, continue as degraded,
- if not, hard-fail the run.

### Coder

If `coder_agent` fails:

- if there are no usable `code_files`, end as `failed`,
- if there is already a usable prior code snapshot in state, end as `partial_success`,
- do not claim full success if the final code step never completed.

### Reviewer

If `reviewer_agent` fails:

- do not discard already generated code,
- emit a degraded warning,
- skip review gating,
- continue to the finalizer or builder according to available code artifacts.

### Builder

If `builder_agent` fails:

- preserve generated `code_files`,
- attach build or syntax failure summary,
- finalize as `partial_success`,
- include a recovery hint telling the user to continue editing or retry build later.

### Image Collector

If `image_collector_agent` fails:

- ignore image enrichment,
- continue with code generation,
- mark degraded only if the image result was expected to influence output.

### Memory and RAG

If memory or retrieval fails:

- continue in no-memory or no-RAG mode,
- mark degraded,
- do not block core generation.

## Workflow State Extensions

Extend `CodeGenState` with availability-oriented fields:

- `degraded: bool`
- `degraded_reasons: list[str]`
- `failed_phase: str | None`
- `last_good_phase: str | None`
- `partial_code_available: bool`
- `final_status: Literal["success", "degraded_success", "partial_success", "failed"] | None`
- `recovery_hint: str | None`
- `phase_failures: list[dict]`

### Field Semantics

- `degraded` means at least one phase continued after a soft failure.
- `degraded_reasons` is the ordered list of machine-readable degradation codes.
- `failed_phase` is the phase that caused terminal failure or partial-success finalization.
- `last_good_phase` helps audit and user-facing explanation.
- `partial_code_available` means the run has a code artifact safe to return.
- `final_status` is set once in the finalizer and becomes the canonical terminal outcome.
- `recovery_hint` is short user-facing guidance such as retrying review/build later.
- `phase_failures` stores structured failure records for traceability and tests.

## Guarded Phase Execution

Introduce a unified phase execution wrapper in the workflow layer, conceptually:

- resolve the phase policy,
- run the phase under a timeout,
- catch exceptions,
- classify the failure,
- either apply fallback or stop,
- update degraded/failure state consistently.

The wrapper should be responsible for:

- timeout enforcement,
- exception normalization,
- degraded state updates,
- fallback invocation,
- structured logging and metrics,
- preserving prior `code_files` when safe.

This logic should live near workflow orchestration rather than being reimplemented inside every agent.

## Timeout Policy

Use phase-class time budgets rather than a single global timeout:

- short timeout group: `intent`, `pm`, `reviewer`
- medium timeout group: `architect`
- long timeout group: `coder`, `builder`

Exact values should be implementation-configurable, but the policy intent is:

- early classification phases should fail fast,
- code-generation phases get the longest budget,
- late verification phases should not block result return indefinitely.

Each timeout maps to a stable reason code such as:

- `intent_timeout`
- `pm_timeout`
- `architect_timeout`
- `coder_timeout`
- `reviewer_timeout`
- `builder_timeout`

## Partial Result Assembly

A run may return partial code when:

- `code_files` exists,
- the file set passes a minimum viability threshold,
- no output guardrail blocks the generated files,
- the failure happened after or during a stage where partial code is still meaningful.

The minimum viability threshold should be conservative and implementation-local, for example:

- at least one primary entry file for the selected stack, or
- at least one non-empty code artifact plus a recognized code generation type.

This threshold should not attempt to prove correctness; it only decides whether the result is worth returning.

## Final Status Rules

The finalizer should produce exactly one of four terminal statuses:

### `success`

Use when:

- core phases completed,
- no degraded path was used,
- no terminal partial-result condition occurred.

### `degraded_success`

Use when:

- the run completed with usable code,
- one or more soft-fail or fallback paths were used,
- the overall code-generation backbone still completed.

Typical causes:

- memory unavailable
- RAG unavailable
- intent fallback used
- reviewer skipped due to timeout but code path still completed safely

### `partial_success`

Use when:

- the run has returnable code,
- but a late or partially core phase failed,
- and the result should be treated as editable but risky.

Typical causes:

- builder failed
- reviewer failed after code generation
- coder produced a usable prior snapshot but final code pass failed

### `failed`

Use when:

- no safe code artifact exists, or
- a hard-fail phase failed before a returnable result could be assembled.

## SSE Contract Enhancements

Keep the current event types and add workflow-availability semantics without breaking compatibility.

### Warning Event

Add a `warning` event for degradations:

```json
{
  "type": "warning",
  "status": "degraded",
  "phase": "review",
  "reason": "reviewer_timeout",
  "message": "Code review timed out. Returning the best generated code so far.",
  "request_id": "...",
  "trace_id": "..."
}
```

This is the canonical event for soft-fail and fallback notification.

### Enhanced Done Event

Enhance the final `done` event with terminal availability fields:

```json
{
  "type": "done",
  "status": "partial_success",
  "failed_phase": "builder",
  "degraded": true,
  "degraded_reasons": ["reviewer_timeout", "builder_compile_failed"],
  "partial_code_available": true,
  "recovery_hint": "You can continue editing the generated files and retry build later.",
  "request_id": "...",
  "trace_id": "..."
}
```

### Compatibility Rule

Existing consumers that only understand `done.status` should continue working. New fields are additive and optional from the Java proxy perspective, though the implementation plan should add Java-side compatibility for the new status values.

## Java Compatibility Boundary

This slice remains Python-first.

Java should only need light compatibility changes:

- tolerate `done.status` values `degraded_success` and `partial_success`,
- pass through `warning` SSE events,
- avoid treating these new terminal statuses as generic failure.

This design does not require a Java-side protocol redesign.

## Metrics, Audit, and Observability

Add metrics and logs for:

- degraded run count by phase and reason code,
- partial-success count by phase,
- hard-failure count by phase,
- fallback usage count by phase,
- terminal status distribution across `success / degraded_success / partial_success / failed`.

Guardrail audit logging remains separate, but degraded-execution records should be easy to correlate by `request_id` and `trace_id`.

## Harness Engineering

### Unit Coverage

Add deterministic tests for:

- failure policy classification,
- final status computation,
- fallback selection,
- partial-code viability decisions.

### Integration Coverage

Add workflow-level tests with mocked phase behavior:

- reviewer timeout still returns code and `partial_success` or `degraded_success`,
- builder failure still returns code and `partial_success`,
- intent fallback produces `degraded_success`,
- coder complete failure produces `failed`,
- architect fallback succeeds with a minimal file plan,
- coder prior snapshot path yields `partial_success` if final code generation later fails.

### Harness Coverage

Extend the deterministic Python harness suites to verify:

- `warning` event emission,
- enhanced `done` event fields,
- `degraded_reasons`,
- `failed_phase`,
- `recovery_hint`,
- stable marker-selected execution under `pytest -m harness -v`.

All new tests must run without real LLM providers.

## Configuration

Add Python configuration for phase time budgets and availability toggles. The implementation plan should define concrete config names, but the design requires:

- per-phase or per-phase-group timeout settings,
- a master enable flag for graded degradation,
- optional toggles for phase-level fallback behavior when phased rollout control is required.

This should default to enabled in development and test once covered by harness tests, because the entire point of this slice is to exercise the degraded paths intentionally.

## Rollout Plan

1. Add workflow state fields and final-status computation helpers.
2. Add failure classification and guarded phase execution.
3. Wire fallback behavior into soft-fail phases.
4. Enhance SSE `warning` and terminal `done` events.
5. Add Python harness tests for degraded and partial-success flows.
6. Add lightweight Java compatibility handling for new terminal statuses.
7. Update hardening docs with high-availability semantics and canonical tests.

## Acceptance Criteria

- Non-core phase failure does not terminate the workflow when safe fallback exists.
- If usable `code_files` already exist, the workflow returns `degraded_success` or `partial_success` whenever possible.
- Reviewer and builder failure do not suppress editable code output.
- Coder failure with no usable code returns `failed`.
- Final SSE `done` always includes stable terminal availability semantics.
- Deterministic tests cover degraded-success and partial-success flows without real model calls.

## Risks

- Returning partial code increases the chance that users act on incomplete output; mitigation is explicit `warning`, `done.status`, and `recovery_hint`.
- Overly permissive degradation could hide real quality regressions; mitigation is keeping hard-fail boundaries strict around architecture and code generation backbone.
- If fallback synthesis for PM or architecture is too aggressive, downstream code quality may drift; mitigation is keeping fallback outputs minimal and testable.
- Existing legacy tests in the Python suite can still be noisy outside the deterministic harness lanes; implementation should extend the marker-based harness carefully instead of broadening global collection again.
