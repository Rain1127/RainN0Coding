# Kafka Code Generation Queue Implementation Plan

Approved design: `../specs/2026-09-08-kafka-code-generation-queue-design.md`; user confirmed 2026-09-08.

Goal: durable bounded generation queue on the existing cloud host, with independent execution and reconnectable progress.

Architecture: MySQL task/outbox/event storage; Spring Kafka publisher and consumer; existing Python workflow; browser task submission and SSE replay. One consumer by default. Main workspace and old deployment release remain protected.

## Work packages

- [x] Backend persistence: add `queue/GenerationTaskStore.java`, `GenerationQueueProperties.java`, SQL migration, JDBC/H2 transaction tests. Test duplicate submissions, atomic capacity, active app uniqueness, outbox redelivery, event ordering and terminal transitions. Run focused Maven tests red, implement, rerun green.
- [x] Backend execution: add queue application service, Kafka configuration/runtime, task controller. Reuse `AiCodeGeneratorFacade` for trusted execution; keep terminal done until all save/build work finishes. Persist terminal events and chat records transactionally. Test missing done, semantic failure, post-done save error and duplicate consumption. Route legacy chat through queue when enabled.
- [x] Frontend: add task API and adapt generation store/page. Contract: POST `/api/app/generation/tasks` body `{appId,message,idempotencyKey}`; GET `/api/app/generation/tasks/latest?appId=...`; GET `/api/app/generation/tasks/{taskId}`; GET `/api/app/generation/tasks/{taskId}/events?after=0`. JSON responses keep BaseResponse `{code,data,message}`. Task fields: `taskId`, `appId` strings, `status` QUEUED/RUNNING/SUCCEEDED/FAILED/INTERRUPTED, `errorMessage`, `lastEventId` string, `retryAllowed` boolean. SSE contains original generation JSON and incremental `id`; queued uses `{type:'queued',phase:'queued',message:'任务已排队'}`. Submit returns task snapshot, latest returns null if absent. On first page restoration replay from zero; reconnect within same store uses last ID. Network errors reconnect without submitting again. Tests cover close/reopen, repeated events, terminal snapshots and ownership failures; run Vitest and build.
- [x] Python execution status: track requests and synchronous phase runners by appId including runners surviving asyncio cancellation; internal authenticated read-only `/api/execution-status/{app_id}` returns `{busy:boolean}`. Queue execution and retries probe it fail closed. Unit tests verify cancelled to_thread work remains busy until actual thread exit.
- [x] Cloud artifacts: official Kafka KRaft fixed image, durable volume, loopback listeners, bounded memory/logs, migration/deploy/rollback instructions. Inspect existing cloud access and capacity read-only before mutation. No Docker Desktop.
- [x] Integration/review: run existing focused Java tests, full frontend checks, Python regressions and new failure-injection tests. Review against design then correctness/quality; fix findings.
- [ ] Release: preserve previous release, back up, install Kafka and additive schema, deploy built artifacts. Test five queued controlled jobs, browser reconnect, broker pause/restart and interrupted worker. Run one real model generation with existing smoke account. Record exact passed/failed boundaries, resource usage and rollback commands.

Run Java using JAVA_HOME `D:/Program Files/Java/jdk-23`; run Python with original workspace `.venv/Scripts/python.exe`. Never modify original environment files or print secrets. Subagents edit only assigned file groups in the shared isolated worktree and report checks. Root owns integration and release.

2026-09-16: integrated live pause/resume release 4ed388f2. Java: 152 tests passed (external-service context test excluded); frontend: 286 full-suite tests plus 6 new task lifecycle cases, production build passed; Python: 76 focused regressions passed. Kafka installed and five independent markers survived broker restart. Application activation and live queue acceptance pending.
