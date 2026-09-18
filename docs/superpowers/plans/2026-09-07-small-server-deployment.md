# Small Server Deployment Implementation Plan

**Goal:** Run the complete current application and monitoring on the existing server while preserving data.
**Architecture:** Nginx + systemd Java/Python; existing Docker databases; separate loopback-only monitoring Compose project.
**Tech Stack:** Java 21, Python 3.12, Node 22, Nginx, Docker Compose, Qdrant, Prometheus, Grafana, Tempo, OpenTelemetry.

## Execution checklist
- [x] Verify authenticated SSH, live resource availability and existing data containers.
- [x] Create isolated worktree from current main.
- [ ] Add a failing regression test for `CODE_OUTPUT_DIR` environment configuration; implement the one-line configuration change and run the test.
- [ ] Create `deploy/small-server/` with preflight/backup/provision scripts, systemd units, monitoring configuration, environment examples and runbook.
- [ ] Back up existing MySQL database, Redis snapshot and Qdrant snapshots with restricted access; verify outputs before installation.
- [ ] Install Java 21, Node 22, Python 3.12 and Nginx from official distribution channels; resolve exact runtime Python dependencies and persist their lock.
- [ ] Build frontend and JAR in the worktree; run focused application tests and check release contents exclude secrets/local caches.
- [ ] Transfer versioned release and secrets separately, activate application and monitoring services, then validate local health endpoints.
- [ ] Verify public access and real login/generation/build/preview/retrieval. Confirm Java/Python trace correlation in Tempo and metric targets in Prometheus.
- [ ] Measure live memory during workload and after restart, verify persistence, and document access, backup, rollback and measured limitations.

## Verification commands
`python-agent/.venv/Scripts/python.exe -m pytest tests/test_cloud_output_config.py` (from the Python directory, using the original existing venv executable).

`npm ci` then `npm run build` in the isolated frontend directory; JDK 23 `mvn package` with relevant unit/contract suites.

`bash -n deploy/small-server/*.sh`, `docker compose config --quiet`, `nginx -t`, `systemd-analyze verify` and actual health probes on the remote host.

No database recreation, schema deletion, credential rotation or unrelated feature-branch merge is part of this plan.
