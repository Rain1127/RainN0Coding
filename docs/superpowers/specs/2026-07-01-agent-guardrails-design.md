# Agent Guardrails Design

## Goal

Build the second production-hardening slice for the Python agent runtime: end-to-end agent safety guardrails with graded enforcement.

This slice covers both:

- request entry guardrails for `/api/generate-code`
- coder toolchain guardrails for `create_file`, `read_file`, `modify_file`, `delete_file`, and `list_files`

The enforcement model is:

- high risk: block
- medium risk: warn and continue
- low risk: audit only

## Scope

This design includes:

- a centralized Python guardrail engine
- prompt and context checks before workflow execution
- tool-action checks before filesystem tools run
- output checks before dangerous SSE payloads are forwarded
- structured guardrail audit logs
- focused Python tests for prompt, tool, and output guardrails

This design does not include:

- OS-level sandboxing
- Java-side duplicate policy evaluation
- database-backed audit storage
- ML-based safety classification
- full secret scanning of generated project contents

## Current System Context

The current Python agent runtime already has a few isolated safeguards:

- `tools/path_guard.py` prevents project-root escape
- `tools/guard.py` enforces simple role-based tool permissions
- `server/main.py` has internal-token auth and local concurrency admission

What is missing is a unified safety decision layer:

- no shared policy model for `allow / warn / block`
- no entry-point risk checks on prompt or history
- no structured reason codes for blocked tool actions
- no output-layer check to stop risky `code_file` events from being forwarded
- no consistent audit trail for why a request or tool action was allowed, warned, or blocked

## Design Approach

Use a centralized guardrail engine inside the Python agent runtime.

Instead of scattering one-off checks across the server, workflow, and tools, this slice introduces a single guardrail module that evaluates risk and returns a structured decision object. Entry guards, tool guards, and output guards will all use the same decision model so behavior is consistent and auditable.

This gives us:

- a single place to evolve policy
- deterministic tests
- consistent error semantics
- low-friction future integration with metrics and monitoring

## Architecture

Create a new Python module group:

- `python-agent/guardrails/policy.py`
- `python-agent/guardrails/models.py`
- `python-agent/guardrails/audit.py`
- `python-agent/guardrails/prompt_guard.py`
- `python-agent/guardrails/tool_guard.py`
- `python-agent/guardrails/output_guard.py`
- `python-agent/guardrails/engine.py`

Responsibilities:

- `models.py`
  Defines shared request, tool-action, output-event, and decision models.
- `policy.py`
  Defines severity levels, action levels, thresholds, protected file patterns, and allowed extension sets.
- `audit.py`
  Emits structured audit logs for all warn and block decisions, and optionally low-risk allows when configured.
- `prompt_guard.py`
  Evaluates user prompt, request metadata, and optional conversation context.
- `tool_guard.py`
  Evaluates file tool calls before they touch the filesystem.
- `output_guard.py`
  Evaluates generated SSE event payloads before forwarding risky content.
- `engine.py`
  Exposes a unified API for guardrail evaluation and returns normalized decisions.

## Decision Model

Use one shared decision object across all guardrails:

```python
GuardrailDecision(
    action="allow" | "warn" | "block",
    severity="low" | "medium" | "high",
    rule_id="...",
    message="...",
    details={...},
)
```

Behavior by action:

- `allow`
  Continue silently unless low-risk auditing is enabled.
- `warn`
  Continue execution, emit an audit log, and attach a structured warning to the local request context.
- `block`
  Stop execution and return a safe structured rejection.

## Prompt Guardrails

Prompt guardrails run in `server/main.py` before `stream_workflow(...)` starts.

Inputs:

- `prompt`
- `request_id`
- `trace_id`
- `user_id`
- `app_id`
- optional `history`

High-risk prompt examples:

- explicit request to access secrets, credentials, SSH keys, or environment files
- instructions to write outside the project root
- instructions to destroy or wipe project files
- instructions to generate system-destructive shell commands as project output

Medium-risk prompt examples:

- requests to overwrite key entry files
- requests to create executable automation scripts
- prompts with excessive size or suspicious repetition patterns

Low-risk prompt examples:

- unusually large but still acceptable prompt length
- repeated path exploration intent

High-risk result:

- return an immediate structured error response from `/api/generate-code`
- do not start the workflow

Medium-risk result:

- continue
- emit an audit log
- optionally add an early warning SSE event for observability

Low-risk result:

- continue
- audit only

## Tool Guardrails

Tool guardrails sit in front of the coder file tools:

- `create_file`
- `read_file`
- `modify_file`
- `delete_file`
- `list_files`

Each tool constructs a normalized `ToolAction` and asks the centralized engine for a decision before continuing.

Checks:

- path must stay under project root
- sensitive file names are protected:
  `.env`, `.env.*`, credential files, SSH material, certificate keys, OS/user shell config
- protected project files are guarded:
  `package.json`, `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `pyproject.toml`, `pom.xml`, `vite.config.*`, primary entrypoints
- allowed extension policy for create/modify
- max single-write size
- max replacement size for `modify_file`
- max directory traversal depth for `list_files`
- delete operations treated as higher risk than read/write

Action examples:

- high
  project-root escape, sensitive file access, deleting protected files
- medium
  modifying protected entry files, creating scripts such as `.sh`, `.bat`, `.ps1`, or large single-file rewrites
- low
  repeated wide directory listing or high-frequency reads

The existing role-based policy remains in place. Guardrails are additive, not a replacement.

## Output Guardrails

Output guardrails run on SSE payloads before forwarding them to the Java gateway path.

Primary target:

- `code_file` events

Checks:

- generated file path must not target sensitive or protected file patterns outside current policy
- generated file content size must stay under a configured ceiling
- suspicious command content patterns can be flagged when a generated file is clearly a destructive script

Behavior:

- high-risk output event: convert to structured error and stop forwarding the risky payload
- medium-risk output event: forward but audit
- low-risk output event: audit only

This layer complements, but does not replace, existing path containment checks in Java and Python.

## Error Semantics

Introduce stable rule-based responses instead of generic denials.

Examples:

- `prompt.secret_access_blocked`
- `prompt.path_escape_blocked`
- `tool.delete_protected_file_blocked`
- `tool.modify_entrypoint_warn`
- `output.oversize_code_file_blocked`

Blocked entry requests should return JSON or SSE-safe structured payloads including:

- `type: "error"`
- `status: "guardrail_blocked"`
- `rule_id`
- `message`
- `request_id`
- `trace_id`

Tool blocks should return a safe tool error string that the agent can observe, while audit logs keep the structured fields.

## Audit and Observability

All `warn` and `block` decisions emit structured logs through one helper.

Each audit record should include:

- `rule_id`
- `action`
- `severity`
- `request_id`
- `trace_id`
- `user_id`
- `app_id`
- `tool_name` when relevant
- `path` when relevant

Phase 1 audit storage is log-only. No DB schema changes are required.

## Configuration

Add Python config values for the guardrail engine:

- `GUARDRAILS_ENABLED`
- `GUARDRAILS_AUDIT_LOW_RISK`
- `GUARDRAILS_MAX_PROMPT_CHARS`
- `GUARDRAILS_MAX_FILE_WRITE_BYTES`
- `GUARDRAILS_MAX_MODIFY_REPLACEMENT_BYTES`
- `GUARDRAILS_MAX_LIST_FILES_DEPTH`

Defaults should be conservative but not so small that normal generation breaks.

## Integration Points

Server integration:

- `python-agent/server/main.py`
  Run prompt guard before workflow start.

Workflow integration:

- `python-agent/workflow/sse_stream.py`
  Run output guard before forwarding `code_file` and other risky events.

Tool integration:

- `python-agent/tools/create_file.py`
- `python-agent/tools/read_file.py`
- `python-agent/tools/modify_file.py`
- `python-agent/tools/delete_file.py`
- `python-agent/tools/list_files.py`

These tools should call the centralized engine rather than baking policy into each file.

## Testing Strategy

Add focused tests for:

- prompt high-risk block
- prompt medium-risk warn
- create outside root blocked
- delete protected file blocked
- modify protected entrypoint warned
- output oversize `code_file` blocked
- output protected-path `code_file` blocked
- audit emission on warn/block

Test layers:

- `python-agent/tests/test_guardrails_prompt.py`
- `python-agent/tests/test_guardrails_tools.py`
- `python-agent/tests/test_guardrails_output.py`
- extend `python-agent/tests/test_internal_auth_and_concurrency.py` only if endpoint wiring changes need a server-level regression

The tests should avoid real LLM calls and use direct function tests or patched workflow/tool entrypoints.

## Rollout Plan

1. Add guardrail config and shared models.
2. Add centralized engine and audit logger.
3. Wire prompt guard into `/api/generate-code`.
4. Wire tool guard into coder file tools.
5. Wire output guard into SSE event forwarding.
6. Add focused tests and update harness documentation if needed.

## Acceptance Criteria

- High-risk prompts are rejected before workflow execution.
- High-risk tool actions are blocked before filesystem access.
- Medium-risk tool and prompt actions are allowed but audited.
- High-risk generated `code_file` events are not forwarded.
- Guardrail logs include `request_id` and `trace_id`.
- Focused Python guardrail tests pass without real model calls.

## Risks

- Overly strict defaults may block legitimate generation flows.
- Warn-only rules can create noisy logs if thresholds are too low.
- Output guardrails may need tuning to avoid blocking legitimate large files for some stacks.
- This slice improves application-level safety, but it is not a substitute for true execution sandboxing.
