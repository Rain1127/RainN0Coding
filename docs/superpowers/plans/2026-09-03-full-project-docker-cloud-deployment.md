# Full Project Docker Cloud Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the verified Vue, Spring Boot, FastAPI, LiteLLM, data, vector-search, and observability stack to one Linux cloud host using isolated Docker containers without Docker Compose.

**Architecture:** Build immutable application images and run every service on a private `rain-network`. Expose only the Nginx frontend on 80/443; use idempotent shell scripts, named volumes, health probes, and an environment file to start dependencies before consumers.

**Tech Stack:** Docker Engine, Nginx, Vue/Vite, Java 21 runtime with JDK 23 build stage, Python 3.12, LiteLLM 1.98.0, MySQL, PostgreSQL, Redis, Qdrant, Prometheus, Grafana, OpenTelemetry Collector, Tempo, Bash.

**Approved design:** `docs/superpowers/specs/2026-09-03-litellm-gateway-design.md`

---

## File map

### Create

- `deploy/docker/frontend.Dockerfile` — Vite build and Nginx runtime.
- `deploy/docker/frontend.nginx.conf` — SPA serving, `/api` proxy, and SSE-safe buffering settings.
- `deploy/docker/java.Dockerfile` — JDK 23 build and Java 21 runtime.
- `deploy/docker/python-agent.Dockerfile` — frozen uv environment and FastAPI runtime.
- `.dockerignore` — excludes secrets, caches, generated output, and local environments from the repository-root build context.
- `RainN0Coding-frontend/build-target.ts` — pure standalone/Spring-static output selection helper.
- `RainN0Coding-frontend/build-target.test.ts` — protects both frontend build modes.
- `deploy/cloud/versions.env` — exact external image versions, including LiteLLM 1.98.0.
- `deploy/cloud/runtime.env.example` — non-secret runtime contract.
- `deploy/cloud/create-network-and-volumes.sh` — idempotent Docker prerequisites.
- `deploy/cloud/start-data-services.sh` — MySQL, PostgreSQL, Redis, and Qdrant containers.
- `deploy/cloud/start-observability.sh` — Prometheus, Grafana, Tempo, and OTel containers.
- `deploy/cloud/start-app-services.sh` — LiteLLM, FastAPI, Java, and frontend containers.
- `deploy/cloud/health-check.sh` — internal and public service verification.
- `deploy/cloud/rollback.sh` — restores the previous immutable application image set.
- `deploy/cloud/prometheus.yml` — container-DNS scrape targets.
- `deploy/cloud/otel-collector-config.yml` — Tempo trace export.
- `deploy/cloud/tempo.yml` — version-compatible single-host storage.
- `deploy/cloud/README.md` — build, release, backup, restore, rollback, and firewall runbook.

### Modify

- `RainN0Coding-frontend/vite.config.ts` — support standalone `/` builds without changing the current Spring-static build default.
- `python-agent/config.py` — make output and internal service paths environment-configurable.
- `src/main/resources/application.yml` — keep all container endpoints environment-driven.
- `grafana/datasources/prometheus.yml` — support a container Prometheus URL through provisioning.

## Task 1: Build immutable application images

**Files:**
- Create: `deploy/docker/frontend.Dockerfile`
- Create: `deploy/docker/frontend.nginx.conf`
- Create: `deploy/docker/java.Dockerfile`
- Create: `deploy/docker/python-agent.Dockerfile`
- Create: `.dockerignore`
- Create: `RainN0Coding-frontend/build-target.ts`
- Create: `RainN0Coding-frontend/build-target.test.ts`
- Modify: `RainN0Coding-frontend/vite.config.ts`

- [ ] **Step 1: Add a failing frontend base-path test**

Extract both production path decisions into a pure helper and test:

```typescript
export const resolveBuildTarget = (target: string | undefined) => ({
  base: target === 'standalone' ? '/' : '/api/',
  outDir: target === 'standalone' ? 'dist' : '../src/main/resources/static',
})
```

Vitest must assert both fields for `standalone` and `undefined`. Import the helper in `vite.config.ts`; keep the current Spring-static behavior as the default and pass `emptyOutDir: true` for both explicit output directories.

- [ ] **Step 2: Implement the frontend container**

```dockerfile
# deploy/docker/frontend.Dockerfile
FROM node:22.18.0-alpine AS build
WORKDIR /app
COPY RainN0Coding-frontend/package*.json ./
RUN npm ci
COPY RainN0Coding-frontend/ ./
ENV VITE_BUILD_TARGET=standalone
RUN npm run build

FROM nginx:1.28.0-alpine
COPY deploy/docker/frontend.nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
HEALTHCHECK CMD wget -qO- http://127.0.0.1/healthz || exit 1
```

The Nginx config serves `index.html`, proxies `/api/` to `http://java-api:8123`, disables proxy buffering for SSE, and exposes `/healthz` without proxying.

- [ ] **Step 3: Implement the Java image**

```dockerfile
FROM maven:3.9.11-eclipse-temurin-23 AS build
WORKDIR /src
COPY pom.xml ./
RUN mvn -B -DskipTests dependency:go-offline
COPY src ./src
RUN mvn -B -DskipTests package

FROM eclipse-temurin:21-jre
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 app
WORKDIR /app
COPY --from=build /src/target/RainN0Coding-0.0.1-SNAPSHOT.jar app.jar
USER 10001
EXPOSE 8123
HEALTHCHECK CMD curl -fsS http://127.0.0.1:8123/api/actuator/health || exit 1
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

- [ ] **Step 4: Implement the Python Agent image**

```dockerfile
FROM python:3.12.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 curl && rm -rf /var/lib/apt/lists/*
RUN useradd --system --uid 10001 app
WORKDIR /app
COPY python-agent/pyproject.toml python-agent/uv.lock ./
RUN pip install --no-cache-dir uv==0.8.15 && uv sync --frozen --no-dev
COPY python-agent/ ./
RUN chown -R app:app /app
USER 10001
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH=/app
EXPOSE 8000
HEALTHCHECK CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 5: Exclude local and secret material**

The repository-root `.dockerignore` must include `.git`, `.env`, `*.local.yml`, `.venv`, `node_modules`, build outputs, generated apps, logs, caches, `.worktrees`, and `secrets`. Keep `python-agent/uv.lock`, frontend lockfiles, source files, and deployment configuration included.

- [ ] **Step 6: Build and smoke-test images locally**

```bash
docker build -f deploy/docker/frontend.Dockerfile -t rain/frontend:test .
docker build -f deploy/docker/java.Dockerfile -t rain/java-api:test .
docker build -f deploy/docker/python-agent.Dockerfile -t rain/python-agent:test .
docker image inspect rain/frontend:test rain/java-api:test rain/python-agent:test >/dev/null
```

Expected: all builds and inspections exit 0.

- [ ] **Step 7: Commit**

```bash
git add .dockerignore deploy/docker/frontend.Dockerfile deploy/docker/frontend.nginx.conf deploy/docker/java.Dockerfile deploy/docker/python-agent.Dockerfile RainN0Coding-frontend/build-target.ts RainN0Coding-frontend/build-target.test.ts RainN0Coding-frontend/vite.config.ts
git commit -m "feat: containerize application services"
```

## Task 2: Define pinned runtime versions and environment contracts

**Files:**
- Create: `deploy/cloud/versions.env`
- Create: `deploy/cloud/runtime.env.example`

- [ ] **Step 1: Pin the external images**

```dotenv
MYSQL_IMAGE=mysql:8.4.6
POSTGRES_IMAGE=postgres:17.6-alpine
REDIS_IMAGE=redis:7.4.5-alpine
QDRANT_IMAGE=qdrant/qdrant:v1.15.4
LITELLM_IMAGE=ghcr.io/berriai/litellm:v1.98.0@sha256:d70b5e0686ecfa186b0f779d4681cf2ff17bbe9c9d7b7301d2e59fce246b668d
PROMETHEUS_IMAGE=prom/prometheus:v3.5.0
GRAFANA_IMAGE=grafana/grafana:11.6.0
OTEL_IMAGE=otel/opentelemetry-collector-contrib:0.132.0
TEMPO_IMAGE=grafana/tempo:2.8.2
```

Verify every declared tag before writing runtime scripts:

```bash
set -a
. deploy/cloud/versions.env
set +a
for image in "$MYSQL_IMAGE" "$POSTGRES_IMAGE" "$REDIS_IMAGE" "$QDRANT_IMAGE" "$LITELLM_IMAGE" "$PROMETHEUS_IMAGE" "$GRAFANA_IMAGE" "$OTEL_IMAGE" "$TEMPO_IMAGE"; do
  docker pull "$image"
  docker image inspect --format '{{index .RepoDigests 0}}' "$image"
done
```

Expected: every pull and inspect exits 0. A missing tag blocks this task and must be replaced by a separately verified explicit version in this plan; never substitute `latest` during execution.

- [ ] **Step 2: Define runtime variables without values**

`runtime.env.example` lists container names, database names/users, internal URLs, application origins, JVM memory, Python concurrency, LiteLLM key aliases, OTLP endpoint, and data directories. Secret values are empty. Include:

```dotenv
APP_RELEASE=initial
PUBLIC_ORIGIN=https://example.invalid
MYSQL_DATABASE=rainn0coding
MYSQL_USER=rain
MYSQL_PASSWORD=
MYSQL_ROOT_PASSWORD=
POSTGRES_DB=litellm_gateway
POSTGRES_USER=litellm
POSTGRES_PASSWORD=
REDIS_PASSWORD=
LITELLM_MASTER_KEY=
LITELLM_API_KEY=
DEEPSEEK_API_KEY=
ZHIPUAI_API_KEY=
PYTHON_AI_INTERNAL_TOKEN=
```

- [ ] **Step 3: Add a secret-boundary test**

Use `git grep` and assert tracked deployment files contain no non-empty value for variables ending in `_KEY`, `_TOKEN`, or `_PASSWORD`.

- [ ] **Step 4: Commit**

```bash
git add deploy/cloud/versions.env deploy/cloud/runtime.env.example
git commit -m "chore: pin cloud runtime images"
```

## Task 3: Start persistent data services without Compose

**Files:**
- Create: `deploy/cloud/create-network-and-volumes.sh`
- Create: `deploy/cloud/start-data-services.sh`

- [ ] **Step 1: Create idempotent prerequisites**

```bash
#!/usr/bin/env bash
set -Eeuo pipefail
docker network inspect rain-network >/dev/null 2>&1 || docker network create rain-network
for volume in rain-mysql rain-postgres rain-redis rain-qdrant rain-code-output rain-prometheus rain-grafana rain-tempo; do
  docker volume inspect "$volume" >/dev/null 2>&1 || docker volume create "$volume" >/dev/null
done
```

- [ ] **Step 2: Add a reusable replace-container function**

```bash
replace_container() {
  local name="$1"
  if docker container inspect "$name" >/dev/null 2>&1; then
    docker rm -f "$name" >/dev/null
  fi
}
```

Use only explicit container names; never remove containers by broad filter or glob.

- [ ] **Step 3: Start MySQL, PostgreSQL, Redis, and Qdrant**

Use explicit names, named volumes, health commands, and no published host ports:

```bash
replace_container mysql
docker run -d --name mysql --network rain-network --restart unless-stopped \
  --env MYSQL_DATABASE --env MYSQL_USER --env MYSQL_PASSWORD --env MYSQL_ROOT_PASSWORD \
  --volume rain-mysql:/var/lib/mysql \
  --health-cmd='mysqladmin ping -h 127.0.0.1 -uroot -p"$MYSQL_ROOT_PASSWORD" --silent' \
  --health-interval=10s --health-timeout=5s --health-retries=12 \
  "$MYSQL_IMAGE"

replace_container postgres
docker run -d --name postgres --network rain-network --restart unless-stopped \
  --env POSTGRES_DB --env POSTGRES_USER --env POSTGRES_PASSWORD \
  --volume rain-postgres:/var/lib/postgresql/data \
  --health-cmd='pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  --health-interval=10s --health-timeout=5s --health-retries=12 \
  "$POSTGRES_IMAGE"

replace_container redis
docker run -d --name redis --network rain-network --restart unless-stopped \
  --volume rain-redis:/data \
  --health-cmd='redis-cli -a "$REDIS_PASSWORD" ping | grep -q PONG' \
  --health-interval=10s --health-timeout=5s --health-retries=12 \
  "$REDIS_IMAGE" redis-server --appendonly yes --requirepass "$REDIS_PASSWORD"

replace_container qdrant
docker run -d --name qdrant --network rain-network --restart unless-stopped \
  --volume rain-qdrant:/qdrant/storage \
  --health-cmd="bash -c ':> /dev/tcp/127.0.0.1/6333'" \
  --health-interval=10s --health-timeout=5s --health-retries=12 \
  "$QDRANT_IMAGE"
```

At script startup, source `versions.env` and the operator-owned `runtime.env`, then fail with `${VARIABLE:?message}` checks before replacing any container.

- [ ] **Step 4: Wait for health, not elapsed time**

```bash
wait_healthy() {
  local name="$1"
  for _ in $(seq 1 60); do
    status=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$name")
    [[ "$status" == healthy ]] && return 0
    [[ "$status" == exited || "$status" == dead ]] && return 1
    sleep 2
  done
  return 1
}
```

- [ ] **Step 5: Run shell checks and an idempotency rehearsal**

```bash
bash -n deploy/cloud/create-network-and-volumes.sh deploy/cloud/start-data-services.sh
shellcheck deploy/cloud/create-network-and-volumes.sh deploy/cloud/start-data-services.sh
./deploy/cloud/create-network-and-volumes.sh
./deploy/cloud/create-network-and-volumes.sh
```

Expected: both runs exit 0 and keep the same volumes.

- [ ] **Step 6: Commit**

```bash
git add deploy/cloud/create-network-and-volumes.sh deploy/cloud/start-data-services.sh
git commit -m "feat: add Docker data service bootstrap"
```

## Task 4: Start LiteLLM and application containers

**Files:**
- Create: `deploy/cloud/start-app-services.sh`
- Modify: `python-agent/config.py`
- Modify: `src/main/resources/application.yml`

- [ ] **Step 1: Make generated paths environment-configurable**

Add tests then replace the fixed Python output path with:

```python
CODE_OUTPUT_DIR: str = os.getenv("CODE_OUTPUT_DIR", "/tmp/ai-code-project")
```

Keep Java endpoints expressed through existing `PYTHON_AI_BASE_URL`, MySQL, Redis, CORS, and OTLP variables.

- [ ] **Step 2: Start LiteLLM with no public port**

Mount the configuration read-only, inject only the gateway's required secrets, and publish no host port:

```bash
replace_container litellm
docker run -d --name litellm --network rain-network --restart unless-stopped \
  --env LITELLM_MASTER_KEY --env DEEPSEEK_API_KEY --env ZHIPUAI_API_KEY \
  --env REDIS_PASSWORD --env REDIS_HOST=redis --env REDIS_PORT=6379 \
  --env DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}" \
  --volume "$PWD/infrastructure/litellm/config.yaml:/app/config.yaml:ro" \
  --health-cmd='python -c "import urllib.request; urllib.request.urlopen(\"http://127.0.0.1:4000/health/liveliness\", timeout=3)"' \
  --health-interval=10s --health-timeout=5s --health-retries=18 \
  "$LITELLM_IMAGE" --config /app/config.yaml --port 4000
wait_healthy litellm
```

- [ ] **Step 3: Start Python after LiteLLM is healthy**

Set:

```dotenv
LITELLM_BASE_URL=http://litellm:4000/v1
LITELLM_HEALTH_URL=http://litellm:4000/health/liveliness
REDIS_HOST=redis
QDRANT_URL=http://qdrant:6333
VECTOR_DB_PROVIDER=qdrant
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://otel-collector:4318/v1/traces
CODE_OUTPUT_DIR=/data/code-output
```

Mount `rain-code-output:/data/code-output` and pass the agent key separately from the gateway master key:

```bash
replace_container python-agent
docker run -d --name python-agent --network rain-network --restart unless-stopped \
  --env LITELLM_API_KEY --env INTERNAL_API_TOKEN="$PYTHON_AI_INTERNAL_TOKEN" \
  --env LITELLM_BASE_URL=http://litellm:4000/v1 \
  --env LITELLM_HEALTH_URL=http://litellm:4000/health/liveliness \
  --env REDIS_HOST=redis --env REDIS_PORT=6379 --env REDIS_PASSWORD \
  --env QDRANT_URL=http://qdrant:6333 --env VECTOR_DB_PROVIDER=qdrant \
  --env OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://otel-collector:4318/v1/traces \
  --env CODE_OUTPUT_DIR=/data/code-output \
  --volume rain-code-output:/data/code-output \
  "rain/python-agent:${APP_RELEASE}"
wait_healthy python-agent
```

- [ ] **Step 4: Start Java and frontend in dependency order**

Java uses the private MySQL, Redis, and Python DNS names. Frontend is the only public application container:

```bash
replace_container java-api
docker run -d --name java-api --network rain-network --restart unless-stopped \
  --env MYSQL_URL="jdbc:mysql://mysql:3306/${MYSQL_DATABASE}" \
  --env MYSQL_USERNAME="$MYSQL_USER" --env MYSQL_PASSWORD \
  --env REDIS_HOST=redis --env REDIS_PORT=6379 --env REDIS_PASSWORD \
  --env PYTHON_AI_BASE_URL=http://python-agent:8000 --env PYTHON_AI_INTERNAL_TOKEN \
  --env APP_CORS_ALLOWED_ORIGIN_PATTERNS="$PUBLIC_ORIGIN" \
  --env OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://otel-collector:4318/v1/traces \
  "rain/java-api:${APP_RELEASE}"
wait_healthy java-api

replace_container frontend
docker run -d --name frontend --network rain-network --restart unless-stopped \
  --publish 80:80 \
  "rain/frontend:${APP_RELEASE}"
wait_healthy frontend
```

The runbook defines HTTPS as a separate, explicit certificate step: mount operator-provided certificate/key files into Nginx, enable the reviewed 443 server block, then add `--publish 443:443`. Never commit certificate private keys or silently serve a self-signed production endpoint.

- [ ] **Step 5: Parse-check and dry-run commands**

```bash
bash -n deploy/cloud/start-app-services.sh
shellcheck deploy/cloud/start-app-services.sh
```

Expected: exit 0 with no shellcheck errors.

- [ ] **Step 6: Commit**

```bash
git add deploy/cloud/start-app-services.sh python-agent/config.py src/main/resources/application.yml
git commit -m "feat: run application stack on private Docker network"
```

## Task 5: Start observability containers with compatible configs

**Files:**
- Create: `deploy/cloud/start-observability.sh`
- Create: `deploy/cloud/prometheus.yml`
- Create: `deploy/cloud/otel-collector-config.yml`
- Create: `deploy/cloud/tempo.yml`
- Modify: `grafana/datasources/prometheus.yml`

- [ ] **Step 1: Add container-DNS scrape targets**

Prometheus targets are `java-api:8123`, `python-agent:8000`, and `litellm:4000`. Mount the LiteLLM metrics credential as a read-only secret file. Do not publish Prometheus or Tempo ports.

- [ ] **Step 2: Add Tempo-compatible OTLP flow**

OTel Collector receives OTLP gRPC/HTTP on the private network, batches traces, and exports to `tempo:4317` with insecure transport. Tempo uses a local named volume and a configuration validated by `tempo -config.file=...` for the pinned version.

- [ ] **Step 3: Start observability after application health**

Grafana mounts existing dashboard provisioning and cloud datasource files. Do not use the default `admin/admin`; require `GF_SECURITY_ADMIN_PASSWORD` from the runtime environment. Publish Grafana only on `127.0.0.1:3001:3000` for SSH-tunnel access.

- [ ] **Step 4: Validate configuration and targets**

```bash
docker run --rm -v "$PWD/deploy/cloud/prometheus.yml:/etc/prometheus/prometheus.yml:ro" "$PROMETHEUS_IMAGE" promtool check config /etc/prometheus/prometheus.yml
bash -n deploy/cloud/start-observability.sh
shellcheck deploy/cloud/start-observability.sh
```

Expected: Prometheus reports `SUCCESS`; shell checks exit 0.

- [ ] **Step 5: Commit**

```bash
git add deploy/cloud/start-observability.sh deploy/cloud/prometheus.yml deploy/cloud/otel-collector-config.yml deploy/cloud/tempo.yml grafana/datasources/prometheus.yml
git commit -m "feat: deploy private observability stack"
```

## Task 6: Add health, backup, and rollback operations

**Files:**
- Create: `deploy/cloud/health-check.sh`
- Create: `deploy/cloud/rollback.sh`
- Create: `deploy/cloud/README.md`

- [ ] **Step 1: Verify every internal boundary from a disposable curl container**

`health-check.sh` checks container health plus HTTP endpoints from `curlimages/curl` attached to `rain-network`: LiteLLM liveness, FastAPI health, Java Actuator, frontend health, Prometheus targets, Tempo readiness, and Grafana health. It also confirms host-published ports are limited to the explicit allowlist.

- [ ] **Step 2: Add database backup and restore rehearsal commands**

The runbook uses `mysqldump` and `pg_dump` executed inside their containers, writes timestamped files beneath `/opt/rainn0coding/backups`, checks nonzero size, and restores each backup into a temporary verification database before retention cleanup.

- [ ] **Step 3: Add immutable application rollback**

`rollback.sh` accepts an explicit release identifier, verifies `rain/frontend:$release`, `rain/java-api:$release`, and `rain/python-agent:$release` exist before stopping anything, then replaces only the three application containers and runs `health-check.sh`. Data containers and volumes are never removed.

- [ ] **Step 4: Test scripts against a disposable release**

```bash
bash -n deploy/cloud/health-check.sh deploy/cloud/rollback.sh
shellcheck deploy/cloud/health-check.sh deploy/cloud/rollback.sh
./deploy/cloud/health-check.sh
```

Expected: all service checks print `[PASS]`. Force a bad application release, run rollback to the previous release, and verify health returns to green.

- [ ] **Step 5: Commit**

```bash
git add deploy/cloud/health-check.sh deploy/cloud/rollback.sh deploy/cloud/README.md
git commit -m "docs: add cloud operations and rollback runbook"
```

## Task 7: Complete cloud acceptance

**Files:**
- Modify: `deploy/cloud/README.md`

- [ ] **Step 1: Run pre-deployment repository checks**

Run the complete Python suite, `mvn test`, frontend tests/build, `git diff --check`, Docker builds, shellcheck, and secret scans. Every command must exit 0 before uploading images.

- [ ] **Step 2: Deploy in dependency order**

```bash
./deploy/cloud/create-network-and-volumes.sh
./deploy/cloud/start-data-services.sh
./deploy/cloud/start-app-services.sh
./deploy/cloud/start-observability.sh
./deploy/cloud/health-check.sh
```

Expected: each script exits 0; repeated execution preserves data volumes and current secrets.

- [ ] **Step 3: Run public and internal security checks**

From outside the server, only 22, 80, and 443 may be reachable. LiteLLM 4000, FastAPI 8000, Java 8123, MySQL 3306, PostgreSQL 5432, Redis 6379, Qdrant 6333, Prometheus 9090, Tempo 3200, and OTel 4317/4318 must be unreachable publicly.

- [ ] **Step 4: Run end-to-end and failure drills**

Run `scripts/api_smoke_test.py` against the public origin, force the fake/non-production primary model to return 500, confirm LiteLLM records a successful fallback, exhaust a low-budget test key, restart the host, and repeat health checks. Do not inject failures into live user traffic.

- [ ] **Step 5: Run backup restore and application rollback drills**

Verify MySQL and PostgreSQL backups restore into temporary databases. Deploy a known bad application image, execute `rollback.sh <previous-release>`, and confirm SSE generation succeeds afterward.

- [ ] **Step 6: Record evidence and commit**

Record timestamps, image digests, commands, exit codes, and non-sensitive success markers in the runbook. Do not paste keys, passwords, prompts, or generated user code.

```bash
git add deploy/cloud/README.md
git commit -m "docs: record cloud deployment acceptance"
```

## Completion gate

Deployment is complete only when all containers are healthy, a full user generation succeeds, LiteLLM spend/fallback records persist across restart, dashboards show live data, data restore and app rollback drills pass, and external scanning confirms that only the approved public ports are reachable.
