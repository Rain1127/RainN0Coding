# Generation Pause / Resume Implementation Plan

> Execute in this session using subagent-driven-development, with separate frontend, Java gateway and Python implementation responsibilities. User confirmed node-boundary pause and LangGraph checkpoints on 2026-09-09.

**Goal:** A user pauses generation from the UI, waits for the current node to finish, then resumes the same run without replaying completed business nodes.

**Architecture:** Durable SQLite checkpoints plus persisted run controls. An independent gate before each business node checks pause intent and uses LangGraph interrupt; resume uses Command(resume=True) and the original run identity. User/app ownership is validated by Java and Python. Each app has one unfinished generation; execution uses an exclusive local filesystem lock released on process death. SQLite and output files must remain on durable local storage; this version targets a single host, not distributed replicas.

**Tech Stack:** Vue/Pinia, Spring Boot/WebClient, FastAPI, LangGraph AsyncSqliteSaver.

## Interface contract

- Existing GET `/app/chat/gen/code`: frontend supplies UUID Idempotency-Key; that request ID is the stable run ID.
- POST `/app/chat/gen/pause`: JSON `{appId, runId}`, returns normal BaseResponse containing `{run_id, status}`. Pause acknowledgement means pausing; only SSE `done/status=paused` confirms a checkpointed pause.
- GET `/app/chat/gen/resume?appId=...&runId=...`: SSE in the existing `{d: ...}` gateway envelope; no new user message and no new run ID.
- Python POST `/api/generation/pause`: `{userId, appId, runId}` returns `{run_id,status}`.
- Python POST `/api/generate-code`: retain existing fields; add `resume: bool=false`. requestId is run ID; resume=true loads the saved input, so prompt may be empty.
- SSE events always carry request_id; paused emits `type=paused` then `type=done,status=paused`; resume emits workflow_resumed and completes through the original event pipeline. A pause is not success or failure.

## Tasks and validation

- [x] Python: test a real small LangGraph with SQLite pause at a gate, close/reopen saver, resume in a fresh process, verify completed business node ran once. Test ownership, duplicate execution, missing run, completed run and repeated pause/resume.
- [x] Python: implement `workflow/run_control.py` (SQLite run metadata, process lock, pause gate, managed execution), wire workflow, SSE and HTTP control with no memory-only fallback. Add dependency and environment documentation.
- [x] Java: test pause/resume ownership and forwarding, paused completion handling and no duplicate user history. Wire client/facade/service/controller while keeping existing generation routes compatible.
- [x] Frontend: test pausing/paused/resume transitions, retained files and original run ID, duplicate clicks and error recovery. Wire buttons and progress states; run vitest and production build.
- [x] Integration: run focused Python, Java and frontend regressions; review diff for checkpoint safety, interrupt propagation, task isolation and unrelated changes. Document commands, evidence and unverified live dependencies.

## Completion criteria

Paused task has a durable checkpoint and starts no following business node. Resume reuses the saved input and progresses from its gate. Double clicks cannot execute a run twice. Unauthorized controls are rejected. Pausing is visible in the UI and is never marked as successful completion. Closing/reopening the checkpoint store (including a fresh Python process) preserves a paused task.
