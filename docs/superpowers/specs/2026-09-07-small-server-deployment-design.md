# Existing-server full deployment

User confirmed: existing 2-vCPU/4-GB Tencent host, up to three users, application plus monitoring, public IP access, existing data and local changes preserved.

## Architecture
Use Nginx on port 80 and the existing frontend `/api/` build. Run Java 21 and Python 3.12 as separate systemd services under a dedicated unprivileged account. Both use `/opt/rainn0coding/shared/tmp/code_output` for generated files; Java uses the shared directory as its working directory. Install Node 22 for runtime Vue builds. Keep existing MySQL, Redis and Qdrant containers, credentials and volumes.

Run version-pinned Prometheus, Grafana, Tempo and OTel Collector in a separate Docker Compose project. Bind monitoring endpoints only to loopback; access Grafana via an SSH tunnel. Use short trace retention, bounded service memory, rotated logs and a single Python worker to avoid duplicate embedding models. Tune generation concurrency using measured workload resource usage.

Alternatives considered: full application containers add image build/distribution work without a current main-branch Docker baseline; unbounded native processes provide no resource containment. Native application services plus existing/containerized infrastructure minimize changes while providing restart and memory controls.

## Release and verification
Build frontend/JAR in an isolated worktree so the original untracked static assets survive. Keep a versioned release directory and a current symlink. Store secrets outside source and preserve cloud data credentials. Back up MySQL, Redis and Qdrant before changes. Validate login, SSE generation, build, preview, retrieval, metrics, correlated traces and restart persistence before claiming completion. Resource fit for three simultaneous generations requires measurement; a healthy idle process is insufficient.

## Actual preflight
Live host: Ubuntu 22.04.5, 3655 MiB RAM, 2438 MiB available, 2047 MiB swap, 47 GB free disk. Existing data containers are healthy. Qdrant has all five project collections. SSH authentication is now working. sudo is available. UFW is inactive; cloud firewall still needs public HTTP verification.
