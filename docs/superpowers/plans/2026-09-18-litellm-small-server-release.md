# LiteLLM Small-Server Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge the LiteLLM gateway into current `main` and deploy it on the existing Tencent Cloud mixed systemd/Docker topology without replacing current data, Kafka, checkpoints, or application services.

**Architecture:** Keep Java and Python as systemd services. Add private PostgreSQL and LiteLLM containers on the existing `rainn0coding-cloud_default` network, bind LiteLLM only to `127.0.0.1:4000`, provision a restricted Virtual Key, and switch only the Python release/environment after the gateway passes health and model checks.

**Tech Stack:** Git, Python 3.12, pytest, LiteLLM Proxy 1.98.0, PostgreSQL 17, Redis 7, Docker Compose, systemd, Spring Boot, Vue/Vitest, Kafka, Prometheus.

---

### Task 1: Integrate current main with the LiteLLM branch

**Files:**
- Modify: `python-agent/config.py`
- Modify: `python-agent/server/generate_code_orchestrator.py`
- Verify: `python-agent/tests/test_generate_code_orchestrator.py`
- Verify: `python-agent/tests/test_generation_pause.py`
- Verify: `python-agent/tests/test_no_direct_provider_access.py`

- [x] **Step 1: Create a recovery ref for the original feature head**

Run: `git branch codex/litellm-gateway-backup-20260918 720cf60a`

Expected: the backup ref resolves to the original LiteLLM head.

- [x] **Step 2: Merge current main into the isolated LiteLLM worktree**

Run: `git merge --no-ff main -m "merge: integrate current main into LiteLLM gateway"`

Expected: only `python-agent/config.py` and `python-agent/server/generate_code_orchestrator.py` require semantic conflict resolution.

- [x] **Step 3: Preserve both gateway and pause/resume behavior**

Keep `CHECKPOINT_DB_PATH` plus the `LITELLM_*` and `LLM_*_MODEL` settings. Do not restore provider credentials to Python runtime configuration. Wrap the full workflow stream in `bind_request_context(...)` and pass `resume=True` to `stream_workflow` when the request is a resume.

- [x] **Step 4: Run focused merge-seam tests**

Run the gateway, request-context, pause/resume, concurrency, Builder and no-direct-provider test files with `PYTHON_DOTENV_DISABLED=1` and a writable `--basetemp`.

Expected: `101 passed`.

### Task 2: Add deployment contracts for the current mixed topology

**Files:**
- Create: `deploy/small-server/litellm/test_release_contract.py`
- Create: `deploy/small-server/litellm/runtime.env.example`
- Create: `deploy/small-server/litellm/compose.yml`
- Create: `deploy/small-server/litellm/prepare-runtime.py`
- Create: `deploy/small-server/litellm/start.sh`
- Create: `deploy/small-server/litellm/verify.py`
- Create: `deploy/small-server/litellm/rollback.sh`
- Modify: `deploy/small-server/monitoring/prometheus.yml`
- Modify: `deploy/small-server/monitoring/compose.yml`

- [ ] **Step 1: Write failing deployment-contract tests**

The tests must assert:

```python
assert "rainn0coding-cloud_default" in compose
assert "127.0.0.1:4000:4000" in compose
assert "rainn0coding_litellm_postgres_data" in compose
assert "mem_limit: 256m" in compose
assert "mem_limit: 512m" in compose
assert "docker volume rm" not in rollback
assert "docker system prune" not in rollback
assert "127.0.0.1:4000" in prometheus
assert all(value == "" for key, value in env.items() if key.endswith(("_KEY", "_PASSWORD")))
```

- [ ] **Step 2: Run the contract test and confirm RED**

Run: `python -m pytest deploy/small-server/litellm/test_release_contract.py -q`

Expected: FAIL because the deployment files do not exist yet.

- [ ] **Step 3: Implement the Compose boundary**

Use the pinned PostgreSQL and LiteLLM images already recorded in `deploy/cloud/versions.env`. PostgreSQL has no published port and uses the named persistent volume. LiteLLM joins the existing external network, mounts `infrastructure/litellm/config.yaml` read-only, publishes only `127.0.0.1:4000`, uses restart policies and the approved memory limits.

- [ ] **Step 4: Implement restricted runtime preparation**

`prepare-runtime.py` must run as root, read existing `/etc/rainn0coding/python.env` without printing values, require both provider keys, generate missing master/salt/database secrets with `secrets.token_urlsafe`, write `/etc/rainn0coding/litellm.env` mode `0600`, and create a timestamped `python.env` backup. It must translate the existing Zhipu variable names to the LiteLLM names and write fixed business-model defaults.

- [ ] **Step 5: Implement start, verify and rollback scripts**

`start.sh` validates the external network and configuration before creating containers. `verify.py` checks liveness, authorized models, loopback-only port binding, container health and metrics without printing credentials. `rollback.sh` stops the two new containers but never deletes volumes, databases, existing services or backups.

- [ ] **Step 6: Add authenticated Prometheus scraping**

Mount a root-created LiteLLM metrics-token file read-only into Prometheus and add a `litellm` job targeting `127.0.0.1:4000/metrics` with `credentials_file`. Do not place the token in YAML.

- [ ] **Step 7: Run contracts and shell syntax checks**

Run:

```powershell
& 'D:\yu-ai-code-mother\python-agent\.venv\Scripts\python.exe' -m pytest deploy/small-server/litellm/test_release_contract.py deploy/cloud/tests/test_cloud_contract.py -q
bash -n deploy/small-server/litellm/start.sh deploy/small-server/litellm/rollback.sh
```

Expected: all tests pass and `bash -n` exits 0.

### Task 3: Complete code review and local verification

**Files:**
- Review: all files in `git diff main...HEAD`
- Verify: `python-agent/tests/`
- Verify: `RainN0Coding-frontend/`
- Verify: `src/test/java/`

- [ ] **Step 1: Scan secrets and provider bypasses**

Run provider-boundary tests and search the production diff for credential-shaped values. Accept only empty examples and test-only `sk-contract` values.

- [ ] **Step 2: Run Python verification**

Run the focused 101-test merge suite, the 21 LiteLLM/config/cloud contracts, then the full Python suite with an explicit writable temporary directory. Record native ONNX diagnostics separately from pytest exit status.

- [ ] **Step 3: Run frontend verification without retaining generated artifacts**

Run `npm test`, `npm run typecheck`, and `npm run build`. Record counts, then restore only build-generated `src/main/resources/static` changes that were absent before the build.

- [ ] **Step 4: Run Java verification**

Run Maven tests and package with `JAVA_HOME=D:\Program Files\Java\jdk-23`. Do not call Java green if any test is skipped due to an unavailable required service unless the test contract explicitly uses controlled substitutes.

- [ ] **Step 5: Review correctness, security, architecture and performance**

Block merge for provider-key leakage, direct-provider fallback, public database/gateway ports, destructive rollback, loss of pause/resume arguments, duplicate retry layers or unbounded resource settings.

### Task 4: Commit and update main safely

**Files:**
- Commit: all reviewed integration and deployment files

- [ ] **Step 1: Resolve and stage the merge**

Run `git diff --check`, confirm no conflict markers, then stage the two resolved files, approved design/plan and deployment assets.

- [ ] **Step 2: Create the merge commit**

Commit with the existing merge message and include verification details in the commit body.

- [ ] **Step 3: Verify the committed tree**

Run `git status --short`, `git log -1 --show-signature --stat`, and the focused gateway/pause suite against the committed tree.

- [ ] **Step 4: Push feature and main**

Push `codex/litellm-gateway`, fast-forward/merge the tested commit into local `main` without touching the existing unrelated `pyproject.toml` and untracked files, rerun focused verification from the merged commit, then push `main` to `origin`.

Expected: local `main`, `origin/main`, and the deployment commit are identical.

### Task 5: Prepare the cloud release and gateway

**Files:**
- Upload: reviewed release archive and `deploy/small-server/litellm/`
- Server: `/opt/rainn0coding/releases/<release>`
- Server: `/etc/rainn0coding/litellm.env`
- Server: `/etc/rainn0coding/python.env`

- [ ] **Step 1: Capture pre-deploy evidence**

Record current release, service/container health, Kafka lag/active tasks, memory, swap and disk. Create timestamped backups of MySQL, `/etc/rainn0coding/python.env`, checkpoint database, release manifest and shared code output metadata.

- [ ] **Step 2: Build and hash immutable release artifacts**

Package Python from the tested commit, produce SHA-256 locally and verify the uploaded hash on the server. Create a new release directory; never overwrite `/opt/rainn0coding/releases/20260917-main-bfd24e5b`.

- [ ] **Step 3: Prepare and start PostgreSQL/LiteLLM**

Run `prepare-runtime.py`, pull pinned images, start PostgreSQL then LiteLLM, and run `verify.py`. Confirm 5432 is not published and 4000 is loopback-only.

- [ ] **Step 4: Provision the restricted Python key**

Call `/key/generate` with the master key from a root-only process, allow exactly the three business aliases, store the result in the candidate Python environment and metrics credential file, and never print the returned key.

### Task 6: Switch Python traffic and accept the deployment

**Files:**
- Server: `/opt/rainn0coding/current`
- Server: `/etc/rainn0coding/python.env`
- Evidence: `/opt/rainn0coding/shared/verification/litellm-<release>.json`

- [ ] **Step 1: Drain generation work**

Set the queue maintenance lock, reject new submissions, wait for `RUNNING` and `PAUSING` counts to reach zero, and preserve `QUEUED`/`PAUSED` records.

- [ ] **Step 2: Atomically switch Python**

Update the candidate Python environment to include only `LITELLM_BASE_URL`, `LITELLM_HEALTH_URL`, `LITELLM_API_KEY` and business aliases for model access. Remove provider keys from Python only after the gateway check passes. Atomically switch the release symlink and restart only `rainn0coding-python`.

- [ ] **Step 3: Run health and authorization checks**

Verify systemd status, `/api/health`, LiteLLM liveness, three aliases, rejection of unauthorized/missing keys, Prometheus target and no public 4000/5432 listeners.

- [ ] **Step 4: Run a real end-to-end generation**

Submit one controlled authenticated task through Java, reconnect SSE, wait for terminal success, verify generated files/build/chat history/Kafka state, and correlate the request in LiteLLM SpendLogs/metrics without storing Prompt or generated code in evidence.

- [ ] **Step 5: Verify restart persistence and resources**

Restart LiteLLM and Python one at a time, rerun health and restricted model checks, verify PostgreSQL records persist, and capture memory/swap/OOM/restart counters.

- [ ] **Step 6: Release the queue and write acceptance evidence**

Clear the maintenance lock only after all checks pass. Write commit, release path, hashes, image digests, test counts, request/task IDs, non-secret health results, resource snapshot and limitations to the verification JSON/Markdown record.

### Task 7: Execute rollback on any failed gate

**Files:**
- Restore: prior `current` symlink and Python environment backup

- [ ] **Step 1: Stop new work and restore the prior Python release**

Keep the queue locked, atomically restore the old symlink/environment and restart Python.

- [ ] **Step 2: Verify the prior production path**

Confirm Python/Java health, existing preview, Kafka state and one bounded status/API check before unlocking the queue.

- [ ] **Step 3: Preserve evidence and data**

Do not delete PostgreSQL/LiteLLM volumes, checkpoints, Kafka data, MySQL data or new release files. Record the failed gate and recovery result without secrets.
