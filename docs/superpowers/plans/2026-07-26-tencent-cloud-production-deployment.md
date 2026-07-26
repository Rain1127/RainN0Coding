# Tencent Cloud Production Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy RainN0Coding to a one-month Tencent Cloud Lighthouse instance in Hong Kong with trusted IP HTTPS, reproducible releases, secure secrets, backups, rollback, and complete business-chain verification.

**Architecture:** Build the Vue assets into the Spring Boot JAR, run Spring Boot and FastAPI as hardened systemd services, and run Milvus/MinIO/etcd with Docker Compose on one 4C16G host. Nginx is the only public application entry point; MySQL, Redis, FastAPI, and Milvus remain loopback-only. The implementation first produces a clean, tested release commit from the user-approved working changes, then provisions and verifies the server.

**Tech Stack:** Vue 3/Vite, Java 21 runtime with JDK 23 local build, Spring Boot 3.5.9, Python 3.12 managed by uv, FastAPI/Uvicorn, MySQL 8, Redis, Milvus Standalone, Docker Compose, Nginx, systemd, Certbot 5.4+, PowerShell, Bash.

---

## File Map

**Modify**

- `pyproject.toml` and root `uv.lock` — preserve the user-approved pending dependency metadata.
- `src/main/java/com/rain/rainn0coding/config/DataInitializer.java` — remove fixed administrator credentials.
- `src/main/resources/application.yml` — expose secure administrator bootstrap variables.
- `src/test/java/com/rain/rainn0coding/config/DataInitializerTest.java` — verify disabled, secure, and database-unavailable bootstrap paths.
- `milvus/docker-compose.yml` — bind Milvus to loopback and inject MinIO credentials/data paths.
- `scripts/api_smoke_test.py` — require administrator credentials from the caller.
- `.gitignore` — exclude `.pnpm-store/` and deployment release archives.
- `docs/tencent-cloud-deployment-runbook.md` — align the existing runbook with automated production assets and IP certificates.

**Create**

- `src/main/resources/application-prod.yml` — production-only cookie, API-doc, actuator, and logging settings.
- `src/test/java/com/rain/rainn0coding/config/ProductionProfileTest.java` — contract test for the production profile.
- `scripts/tests/test_production_deployment_assets.py` — standard-library contract tests for deployment files.
- `deploy/production/java.env.example` — Java EnvironmentFile schema with no secrets.
- `deploy/production/python.env.example` — Python EnvironmentFile schema with no secrets.
- `deploy/production/milvus.env.example` — Milvus EnvironmentFile schema with no secrets.
- `deploy/production/systemd/yuai-java.service` — Java service definition.
- `deploy/production/systemd/yuai-python.service` — Python service definition.
- `deploy/production/systemd/yuai-mysql-backup.service` and `.timer` — daily database backup.
- `deploy/production/systemd/yuai-cert-renew.service` and `.timer` — short-lived IP certificate renewal.
- `deploy/production/nginx/rainn0coding-bootstrap.conf` — HTTP-only ACME bootstrap.
- `deploy/production/nginx/rainn0coding-https.conf.template` — IP HTTPS reverse proxy and SSE settings.
- `scripts/deploy/package-release.ps1` — reproducible Windows release packaging.
- `scripts/deploy/provision-ubuntu.sh` — host package, user, directory, firewall, and swap setup.
- `scripts/deploy/install-release.sh` — atomic release install and service registration.
- `scripts/deploy/backup-mysql.sh` — daily backup implementation.
- `scripts/deploy/verify-production.sh` — service, disk, certificate, and port verification.

## Task 1: Create an Isolated, Reproducible Release Baseline

**Files:**

- Modify: `pyproject.toml`
- Create: `uv.lock`
- Rebuild: `src/main/resources/static/**`
- Modify: `.gitignore`

- [ ] **Step 1: Create an isolated worktree**

Invoke `superpowers:using-git-worktrees` before changing product files. Create branch `codex/tencent-cloud-deployment` from commit `5e729ff1`.

Expected: the deployment branch is in a separate worktree and the original dirty workspace remains unchanged.

- [ ] **Step 2: Reapply the approved root dependency metadata**

Apply this exact dependency block to root `pyproject.toml`:

```toml
[project]
name = "RainN0Coding"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "langchain-openai>=1.3.3",
    "pymilvus>=3.0.0",
]
```

- [ ] **Step 3: Regenerate the root lockfile**

Run:

```powershell
uv lock
```

Expected: `uv.lock` is generated without dependency-resolution errors.

- [ ] **Step 4: Reproduce the frontend production assets**

Run:

```powershell
Set-Location RainN0Coding-frontend
npm ci
npm test
npm run build
Set-Location ..
```

Expected: Vitest passes and Vite writes the production bundle into `src/main/resources/static`. Only assets produced by this command are eligible for the release commit.

- [ ] **Step 5: Add local artifact exclusions**

Append:

```gitignore
.pnpm-store/
release/
*.release.tar.gz
```

- [ ] **Step 6: Verify the baseline diff**

Run:

```powershell
git status --short
git diff --check
git diff -- pyproject.toml .gitignore
```

Expected: no `.env`, `application-local.yml`, `.pnpm-store`, IDE file, database, or unrelated historical plan is present.

- [ ] **Step 7: Commit the reproducible baseline**

```powershell
git add pyproject.toml uv.lock .gitignore src/main/resources/static
git commit -m "build: capture deployment release baseline"
```

Expected: one commit containing only dependency metadata, exclusions, and reproducible frontend output.

## Task 2: Remove Fixed Administrator Credentials

**Files:**

- Modify: `src/main/java/com/rain/rainn0coding/config/DataInitializer.java`
- Modify: `src/main/resources/application.yml`
- Modify: `src/test/java/com/rain/rainn0coding/config/DataInitializerTest.java`

- [ ] **Step 1: Write failing bootstrap tests**

Add these cases to `DataInitializerTest`:

```java
@Test
void initAdminUserSkipsWhenBootstrapCredentialsAreMissing() {
    DataInitializer initializer = new DataInitializer();
    UserService userService = mock(UserService.class);
    ReflectionTestUtils.setField(initializer, "userService", userService);
    ReflectionTestUtils.setField(initializer, "adminAccount", "");
    ReflectionTestUtils.setField(initializer, "adminPassword", "");

    initializer.initAdminUser();

    verifyNoInteractions(userService);
}

@Test
void initAdminUserHashesConfiguredPasswordWithoutPersistingPlaintext() {
    DataInitializer initializer = new DataInitializer();
    UserService userService = mock(UserService.class);
    ReflectionTestUtils.setField(initializer, "userService", userService);
    ReflectionTestUtils.setField(initializer, "adminAccount", "production_admin");
    ReflectionTestUtils.setField(initializer, "adminPassword", "A-strong-admin-password-2026");
    when(userService.getOne(any(QueryWrapper.class))).thenReturn(null);
    when(userService.getEncryptPassword("A-strong-admin-password-2026"))
            .thenReturn("$2a$10$example-hash");

    initializer.initAdminUser();

    ArgumentCaptor<User> captor = ArgumentCaptor.forClass(User.class);
    verify(userService).save(captor.capture());
    assertThat(captor.getValue().getUserAccount()).isEqualTo("production_admin");
    assertThat(captor.getValue().getUserPassword()).isEqualTo("$2a$10$example-hash");
    assertThat(captor.getValue().getUserPassword())
            .doesNotContain("A-strong-admin-password-2026");
}

@Test
void initAdminUserRejectsShortBootstrapPassword() {
    DataInitializer initializer = new DataInitializer();
    ReflectionTestUtils.setField(initializer, "userService", mock(UserService.class));
    ReflectionTestUtils.setField(initializer, "adminAccount", "production_admin");
    ReflectionTestUtils.setField(initializer, "adminPassword", "too-short");

    assertThatThrownBy(initializer::initAdminUser)
            .isInstanceOf(IllegalStateException.class)
            .hasMessageContaining("at least 16 characters");
}
```

Add imports:

```java
import org.mockito.ArgumentCaptor;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.verifyNoInteractions;
```

Update the existing database-unavailable test to set a valid account/password before invoking the initializer.

- [ ] **Step 2: Run the tests and confirm failure**

Run:

```powershell
$env:JAVA_HOME='D:/Program Files/Java/jdk-23'
./mvnw.cmd -Dtest=DataInitializerTest test
```

Expected: compilation or assertion failure because configurable bootstrap fields do not exist.

- [ ] **Step 3: Implement secure bootstrap behavior**

Replace the fixed credential block in `DataInitializer` with:

```java
@Value("${app.admin-bootstrap.account:}")
private String adminAccount;

@Value("${app.admin-bootstrap.password:}")
private String adminPassword;

@PostConstruct
public void initAdminUser() {
    if (StrUtil.hasBlank(adminAccount, adminPassword)) {
        log.info("Administrator bootstrap is disabled");
        return;
    }
    if (adminPassword.length() < 16) {
        throw new IllegalStateException(
                "Administrator bootstrap password must be at least 16 characters"
        );
    }
    try {
        QueryWrapper queryWrapper = QueryWrapper.create()
                .eq("userAccount", adminAccount);
        User existing = userService.getOne(queryWrapper);
        if (existing != null) {
            log.info("Administrator account already exists: {}", adminAccount);
            return;
        }

        User admin = new User();
        admin.setUserAccount(adminAccount);
        admin.setUserPassword(userService.getEncryptPassword(adminPassword));
        admin.setUserName("管理员");
        admin.setUserRole("admin");
        admin.setUserProfile("系统管理员");
        if (!userService.save(admin)) {
            throw new IllegalStateException("Failed to create administrator account");
        }
        log.info("Created administrator account: {}", adminAccount);
    } catch (DataAccessException e) {
        log.warn("Skip administrator bootstrap because database is unavailable: {}",
                e.getMessage());
    }
}
```

Add imports:

```java
import cn.hutool.core.util.StrUtil;
import org.springframework.beans.factory.annotation.Value;
```

Add to `application.yml` under `app`:

```yaml
  admin-bootstrap:
    account: ${BOOTSTRAP_ADMIN_ACCOUNT:}
    password: ${BOOTSTRAP_ADMIN_PASSWORD:}
```

- [ ] **Step 4: Run focused and password tests**

Run:

```powershell
./mvnw.cmd -Dtest=DataInitializerTest,UserServiceImplTest test
```

Expected: all tests pass; newly stored passwords begin with a BCrypt prefix.

- [ ] **Step 5: Scan for disclosed defaults**

Run:

```powershell
rg -n "admin123|rainadmin123|4019b808b8a10fae1eeb8d0eec9a4c93" src scripts
```

Expected: no production source or smoke script contains a working default administrator credential.

- [ ] **Step 6: Commit**

```powershell
git add src/main/java/com/rain/rainn0coding/config/DataInitializer.java `
        src/main/resources/application.yml `
        src/test/java/com/rain/rainn0coding/config/DataInitializerTest.java
git commit -m "fix: secure production administrator bootstrap"
```

## Task 3: Add a Locked-Down Spring Production Profile

**Files:**

- Create: `src/main/resources/application-prod.yml`
- Create: `src/test/java/com/rain/rainn0coding/config/ProductionProfileTest.java`

- [ ] **Step 1: Write the failing profile contract test**

Create:

```java
package com.rain.rainn0coding.config;

import org.junit.jupiter.api.Test;
import org.springframework.boot.env.YamlPropertySourceLoader;
import org.springframework.core.env.PropertySource;
import org.springframework.core.io.ClassPathResource;

import java.io.IOException;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class ProductionProfileTest {

    @Test
    void productionProfileLocksDownPublicRuntimeSettings() throws IOException {
        List<PropertySource<?>> sources = new YamlPropertySourceLoader().load(
                "prod", new ClassPathResource("application-prod.yml")
        );
        PropertySource<?> properties = sources.getFirst();

        assertThat(properties.getProperty("server.servlet.session.cookie.secure"))
                .isEqualTo(true);
        assertThat(properties.getProperty("server.servlet.session.cookie.http-only"))
                .isEqualTo(true);
        assertThat(properties.getProperty("management.endpoints.web.exposure.include"))
                .isEqualTo("health,info");
        assertThat(properties.getProperty("management.endpoint.health.show-details"))
                .isEqualTo("never");
        assertThat(properties.getProperty("springdoc.api-docs.enabled")).isEqualTo(false);
        assertThat(properties.getProperty("knife4j.enable")).isEqualTo(false);
        assertThat(properties.getProperty("sa-token.is-log")).isEqualTo(false);
    }
}
```

- [ ] **Step 2: Run and verify failure**

```powershell
./mvnw.cmd -Dtest=ProductionProfileTest test
```

Expected: FAIL because `application-prod.yml` does not exist.

- [ ] **Step 3: Create the production profile**

Create `application-prod.yml`:

```yaml
server:
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax

springdoc:
  api-docs:
    enabled: false

knife4j:
  enable: false

sa-token:
  is-log: false

management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: never

otel:
  sdk:
    disabled: true
```

- [ ] **Step 4: Run the profile tests**

```powershell
./mvnw.cmd -Dtest=ProductionProfileTest,ProductionBaselinePropertiesTest test
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/main/resources/application-prod.yml `
        src/test/java/com/rain/rainn0coding/config/ProductionProfileTest.java
git commit -m "feat: add hardened production profile"
```

## Task 4: Make Milvus Compose Safe for a Single Public Host

**Files:**

- Modify: `milvus/docker-compose.yml`
- Create: `deploy/production/milvus.env.example`
- Create: `scripts/tests/test_production_deployment_assets.py`

- [ ] **Step 1: Write failing deployment-asset checks**

Create the first version of `scripts/tests/test_production_deployment_assets.py`:

```python
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class ProductionDeploymentAssetTest(unittest.TestCase):
    def test_milvus_is_loopback_only_and_has_no_default_credentials(self):
        compose = (ROOT / "milvus/docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("127.0.0.1:${MILVUS_PORT:-19530}:19530", compose)
        self.assertIn("127.0.0.1:${MILVUS_HEALTH_PORT:-9091}:9091", compose)
        self.assertNotIn("minioadmin", compose)
        self.assertIn("${MINIO_ROOT_USER:?", compose)
        self.assertIn("${MINIO_ROOT_PASSWORD:?", compose)

    def test_production_milvus_environment_schema_exists(self):
        env_text = (ROOT / "deploy/production/milvus.env.example").read_text(
            encoding="utf-8"
        )
        for key in (
            "MINIO_ROOT_USER=",
            "MINIO_ROOT_PASSWORD=",
            "ETCD_DATA_DIR=",
            "MINIO_DATA_DIR=",
            "MILVUS_DATA_DIR=",
        ):
            self.assertIn(key, env_text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run and confirm failure**

```powershell
python -m unittest scripts.tests.test_production_deployment_assets -v
```

Expected: FAIL on public port bindings, default credentials, and missing environment schema.

- [ ] **Step 3: Harden the Compose file**

Use these exact environment and volume declarations:

```yaml
  etcd:
    volumes:
      - ${ETCD_DATA_DIR:-etcd_data}:/etcd

  minio:
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER:?MINIO_ROOT_USER is required}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD:?MINIO_ROOT_PASSWORD is required}
    volumes:
      - ${MINIO_DATA_DIR:-minio_data}:/minio_data

  milvus-standalone:
    environment:
      ETCD_ENDPOINTS: etcd:2379
      MINIO_ADDRESS: minio:9000
      MINIO_ACCESS_KEY_ID: ${MINIO_ROOT_USER:?MINIO_ROOT_USER is required}
      MINIO_SECRET_ACCESS_KEY: ${MINIO_ROOT_PASSWORD:?MINIO_ROOT_PASSWORD is required}
    volumes:
      - ${MILVUS_DATA_DIR:-milvus_data}:/var/lib/milvus
    ports:
      - "127.0.0.1:${MILVUS_PORT:-19530}:19530"
      - "127.0.0.1:${MILVUS_HEALTH_PORT:-9091}:9091"
```

Keep the existing health checks and dependency ordering.

- [ ] **Step 4: Create the non-secret environment schema**

Create `deploy/production/milvus.env.example`:

```dotenv
MINIO_ROOT_USER=
MINIO_ROOT_PASSWORD=
ETCD_DATA_DIR=/opt/RainN0Coding/data/milvus/etcd
MINIO_DATA_DIR=/opt/RainN0Coding/data/milvus/minio
MILVUS_DATA_DIR=/opt/RainN0Coding/data/milvus/standalone
MILVUS_PORT=19530
MILVUS_HEALTH_PORT=9091
```

- [ ] **Step 5: Validate Compose and tests**

Use temporary non-production values only for validation:

```powershell
$env:MINIO_ROOT_USER='compose-validation-user'
$env:MINIO_ROOT_PASSWORD='compose-validation-password-2026'
docker compose -f milvus/docker-compose.yml config --quiet
python -m unittest scripts.tests.test_production_deployment_assets -v
```

Expected: Compose config succeeds and all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add milvus/docker-compose.yml deploy/production/milvus.env.example `
        scripts/tests/test_production_deployment_assets.py
git commit -m "fix: isolate production Milvus services"
```

## Task 5: Add Production Environment, systemd, and Nginx Templates

**Files:**

- Create: `deploy/production/java.env.example`
- Create: `deploy/production/python.env.example`
- Create: `deploy/production/systemd/yuai-java.service`
- Create: `deploy/production/systemd/yuai-python.service`
- Create: `deploy/production/systemd/yuai-mysql-backup.service`
- Create: `deploy/production/systemd/yuai-mysql-backup.timer`
- Create: `deploy/production/systemd/yuai-cert-renew.service`
- Create: `deploy/production/systemd/yuai-cert-renew.timer`
- Create: `deploy/production/nginx/rainn0coding-bootstrap.conf`
- Create: `deploy/production/nginx/rainn0coding-https.conf.template`
- Modify: `scripts/tests/test_production_deployment_assets.py`

- [ ] **Step 1: Extend the contract tests before creating templates**

Add:

```python
    def test_systemd_units_use_protected_environment_files(self):
        java = (ROOT / "deploy/production/systemd/yuai-java.service").read_text(
            encoding="utf-8"
        )
        python = (ROOT / "deploy/production/systemd/yuai-python.service").read_text(
            encoding="utf-8"
        )
        for unit in (java, python):
            self.assertIn("User=yuai", unit)
            self.assertIn("NoNewPrivileges=true", unit)
            self.assertIn("Restart=on-failure", unit)
        self.assertIn("EnvironmentFile=/opt/RainN0Coding/config/java.env", java)
        self.assertIn("EnvironmentFile=/opt/RainN0Coding/config/python.env", python)
        self.assertIn("-Xmx2g", java)
        self.assertIn("--workers 1", python)

    def test_nginx_template_preserves_sse_and_blocks_actuator(self):
        nginx = (
            ROOT / "deploy/production/nginx/rainn0coding-https.conf.template"
        ).read_text(encoding="utf-8")
        self.assertIn("proxy_buffering off;", nginx)
        self.assertIn("proxy_read_timeout 1800s;", nginx)
        self.assertIn("location ^~ /api/actuator", nginx)
        self.assertIn("deny all;", nginx)
        self.assertIn("/etc/letsencrypt/live/${PUBLIC_IP}/fullchain.pem", nginx)
```

Run the test and expect missing-file failures.

- [ ] **Step 2: Create Java environment schema**

Create `deploy/production/java.env.example`:

```dotenv
SPRING_PROFILES_ACTIVE=prod
MYSQL_URL="jdbc:mysql://127.0.0.1:3306/rainn0coding?useUnicode=true&characterEncoding=utf8&serverTimezone=Asia/Shanghai"
MYSQL_USERNAME=rainn0coding
MYSQL_PASSWORD=
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_DATABASE=0
REDIS_PASSWORD=
PYTHON_AI_BASE_URL=http://127.0.0.1:8000
PYTHON_AI_INTERNAL_TOKEN=
AI_CODEGEN_MAX_CONCURRENT_REQUESTS=1
AI_CODEGEN_PERMIT_LEASE_MINUTES=30
APP_DEPLOY_HOST=
APP_CORS_ALLOWED_ORIGIN_PATTERNS=
BOOTSTRAP_ADMIN_ACCOUNT=
BOOTSTRAP_ADMIN_PASSWORD=
COS_SECRET_ID=
COS_SECRET_KEY=
PEXELS_API_KEY=
OTEL_SDK_DISABLED=true
```

- [ ] **Step 3: Create Python environment schema**

Create `deploy/production/python.env.example`:

```dotenv
APP_ENV=production
SERVER_PORT=8000
INTERNAL_API_TOKEN=
INTERNAL_API_ALLOW_MISSING_TOKEN=false
AGENT_MAX_CONCURRENT_REQUESTS=1
AGENT_OVERLOAD_STATUS_CODE=503
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-v4-pro
CHAT_MODEL=deepseek-chat
REASONING_MODEL=deepseek-v4-pro
ZHIPU_API_KEY=
ZHIPU_BASE_URL=https://open.bigmodel.cn/api/paas/v4
ZHIPU_FLASH_MODEL=glm-4.7-flash
MILVUS_MODE=standalone
MILVUS_HOST=127.0.0.1
MILVUS_PORT=19530
LOCAL_EMBEDDING_ENABLED=true
EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
SQLITE_DB_PATH=/opt/RainN0Coding/data/python/rag_data/exact_search.db
CODE_STORE_DIR=/opt/RainN0Coding/data/python/verified_code
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
LANGSMITH_TRACING=false
```

- [ ] **Step 4: Create hardened application services**

Create `yuai-java.service`:

```ini
[Unit]
Description=RainN0Coding Spring Boot gateway
After=network-online.target mysql.service redis-server.service yuai-python.service
Wants=network-online.target

[Service]
Type=simple
User=yuai
Group=yuai
WorkingDirectory=/opt/RainN0Coding/current
EnvironmentFile=/opt/RainN0Coding/config/java.env
ExecStart=/usr/bin/java -Xms512m -Xmx2g -jar /opt/RainN0Coding/current/app.jar
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/opt/RainN0Coding/data /opt/RainN0Coding/tmp /opt/RainN0Coding/logs
StandardOutput=append:/opt/RainN0Coding/logs/java/stdout.log
StandardError=append:/opt/RainN0Coding/logs/java/stderr.log

[Install]
WantedBy=multi-user.target
```

Create `yuai-python.service`:

```ini
[Unit]
Description=RainN0Coding FastAPI agent
After=network-online.target redis-server.service docker.service
Requires=docker.service

[Service]
Type=simple
User=yuai
Group=yuai
WorkingDirectory=/opt/RainN0Coding/current/python-agent
EnvironmentFile=/opt/RainN0Coding/config/python.env
Environment=PYTHONPATH=/opt/RainN0Coding/current/python-agent
ExecStart=/opt/RainN0Coding/current/python-agent/.venv/bin/python -m uvicorn server.main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/RainN0Coding/data /opt/RainN0Coding/tmp /opt/RainN0Coding/logs
StandardOutput=append:/opt/RainN0Coding/logs/python/stdout.log
StandardError=append:/opt/RainN0Coding/logs/python/stderr.log

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 5: Create backup and certificate timers**

Create the backup service/timer:

```ini
[Unit]
Description=RainN0Coding MySQL backup

[Service]
Type=oneshot
User=yuai
Group=yuai
EnvironmentFile=/opt/RainN0Coding/config/java.env
ExecStart=/opt/RainN0Coding/current/scripts/deploy/backup-mysql.sh
```

```ini
[Unit]
Description=Run RainN0Coding MySQL backup daily

[Timer]
OnCalendar=*-*-* 03:30:00
Persistent=true
RandomizedDelaySec=15m

[Install]
WantedBy=timers.target
```

Create the certificate service/timer:

```ini
[Unit]
Description=Renew RainN0Coding short-lived IP certificate
After=network-online.target nginx.service

[Service]
Type=oneshot
ExecStart=/snap/bin/certbot renew --quiet --deploy-hook "systemctl reload nginx"
```

```ini
[Unit]
Description=Check RainN0Coding IP certificate every six hours

[Timer]
OnCalendar=*-*-* 00/6:15:00
Persistent=true
RandomizedDelaySec=15m

[Install]
WantedBy=timers.target
```

- [ ] **Step 6: Create Nginx bootstrap and HTTPS templates**

Create `rainn0coding-bootstrap.conf`:

```nginx
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        default_type text/plain;
    }

    location / {
        return 503;
    }
}
```

Create `rainn0coding-https.conf.template`:

```nginx
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        default_type text/plain;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2 default_server;
    listen [::]:443 ssl http2 default_server;
    server_name _;

    ssl_certificate /etc/letsencrypt/live/${PUBLIC_IP}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${PUBLIC_IP}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    client_max_body_size 50m;

    location = / {
        return 302 /api/;
    }

    location ^~ /api/actuator {
        deny all;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8123;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 1800s;
        proxy_send_timeout 1800s;
    }
}
```

- [ ] **Step 7: Run contract tests**

```powershell
python -m unittest scripts.tests.test_production_deployment_assets -v
```

Expected: all deployment-template tests pass.

- [ ] **Step 8: Commit**

```powershell
git add deploy/production scripts/tests/test_production_deployment_assets.py
git commit -m "feat: add production service templates"
```

## Task 6: Add Provisioning, Release, Backup, and Verification Scripts

**Files:**

- Create: `scripts/deploy/package-release.ps1`
- Create: `scripts/deploy/provision-ubuntu.sh`
- Create: `scripts/deploy/install-release.sh`
- Create: `scripts/deploy/backup-mysql.sh`
- Create: `scripts/deploy/verify-production.sh`
- Modify: `scripts/tests/test_production_deployment_assets.py`

- [ ] **Step 1: Add failing script-presence and safety tests**

Add:

```python
    def test_shell_scripts_are_strict_and_do_not_embed_secrets(self):
        for relative in (
            "scripts/deploy/provision-ubuntu.sh",
            "scripts/deploy/install-release.sh",
            "scripts/deploy/backup-mysql.sh",
            "scripts/deploy/verify-production.sh",
        ):
            content = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("set -euo pipefail", content)
            self.assertNotIn("admin123", content)
            self.assertNotIn("minioadmin", content)

    def test_release_packager_excludes_local_secrets(self):
        content = (ROOT / "scripts/deploy/package-release.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("application-local.yml", content)
        self.assertIn("python-agent/.env", content)
        self.assertIn(".pnpm-store", content)
```

Run and expect missing-file failures.

- [ ] **Step 2: Create the release packager**

Create `package-release.ps1`:

```powershell
param(
    [string]$OutputDirectory = "release"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
$output = Join-Path $root $OutputDirectory
$stage = Join-Path $output "stage"
$archive = Join-Path $output "rainn0coding.release.tar.gz"

if (Test-Path -LiteralPath $stage) {
    Remove-Item -LiteralPath $stage -Recurse -Force
}
New-Item -ItemType Directory -Path $stage -Force | Out-Null

$jar = Get-ChildItem -LiteralPath (Join-Path $root "target") `
    -Filter "RainN0Coding-*.jar" |
    Where-Object { $_.Name -notlike "*.original" } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if (-not $jar) { throw "Spring Boot jar was not found" }

Copy-Item -LiteralPath $jar.FullName -Destination (Join-Path $stage "app.jar")
Copy-Item -LiteralPath (Join-Path $root "python-agent") `
    -Destination (Join-Path $stage "python-agent") -Recurse
Copy-Item -LiteralPath (Join-Path $root "milvus") `
    -Destination (Join-Path $stage "milvus") -Recurse
Copy-Item -LiteralPath (Join-Path $root "deploy") `
    -Destination (Join-Path $stage "deploy") -Recurse
Copy-Item -LiteralPath (Join-Path $root "scripts") `
    -Destination (Join-Path $stage "scripts") -Recurse
Copy-Item -LiteralPath (Join-Path $root "sql") `
    -Destination (Join-Path $stage "sql") -Recurse

$forbidden = @(
    "application-local.yml",
    "python-agent/.env",
    ".pnpm-store",
    "node_modules",
    ".venv",
    "__pycache__"
)
Get-ChildItem -LiteralPath $stage -Recurse -Force |
    Where-Object { $forbidden -contains $_.Name } |
    Remove-Item -Recurse -Force

if (Test-Path -LiteralPath $archive) {
    Remove-Item -LiteralPath $archive -Force
}
tar -czf $archive -C $stage .
Get-FileHash -Algorithm SHA256 -LiteralPath $archive |
    Format-List Path, Hash
```

- [ ] **Step 3: Create host provisioning script**

Create `provision-ubuntu.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root" >&2
  exit 1
fi

apt-get update
apt-get install -y \
  ca-certificates curl git nginx mysql-server redis-server \
  docker.io docker-compose-plugin openjdk-21-jre-headless \
  chromium-browser fonts-noto-cjk fonts-wqy-zenhei \
  openssl ufw snapd

id yuai >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin yuai
usermod -aG docker yuai

install -d -o yuai -g yuai \
  /opt/RainN0Coding/releases \
  /opt/RainN0Coding/config \
  /opt/RainN0Coding/data/mysql \
  /opt/RainN0Coding/data/redis \
  /opt/RainN0Coding/data/milvus/etcd \
  /opt/RainN0Coding/data/milvus/minio \
  /opt/RainN0Coding/data/milvus/standalone \
  /opt/RainN0Coding/data/python/rag_data \
  /opt/RainN0Coding/data/python/verified_code \
  /opt/RainN0Coding/data/backups/mysql \
  /opt/RainN0Coding/tmp/code_output \
  /opt/RainN0Coding/tmp/code_deploy \
  /opt/RainN0Coding/logs/java \
  /opt/RainN0Coding/logs/python \
  /var/www/certbot

if ! swapon --show=NAME --noheadings | grep -qx /swapfile; then
  fallocate -l 4G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

systemctl enable --now docker mysql redis-server nginx

snap install core
snap refresh core
snap install --classic certbot
ln -sf /snap/bin/certbot /usr/local/bin/certbot

if ! command -v node >/dev/null 2>&1; then
  snap install node --classic --channel=22/stable
fi

if [[ ! -x /home/yuai/.local/bin/uv ]]; then
  sudo -u yuai env HOME=/home/yuai sh -c \
    'curl -LsSf https://astral.sh/uv/0.11.32/install.sh | sh'
fi
sudo -u yuai env HOME=/home/yuai /home/yuai/.local/bin/uv python install 3.12

ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "Provisioning complete"
```

- [ ] **Step 4: Create atomic release installer**

Create `install-release.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

archive="${1:?release archive path is required}"
release_id="${2:?release id is required}"
root=/opt/RainN0Coding
release_dir="${root}/releases/${release_id}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root" >&2
  exit 1
fi
if [[ -e "${release_dir}" ]]; then
  echo "Release already exists: ${release_dir}" >&2
  exit 1
fi

install -d -o yuai -g yuai "${release_dir}"
tar -xzf "${archive}" -C "${release_dir}"
chown -R yuai:yuai "${release_dir}"

sudo -u yuai env HOME=/home/yuai \
  /home/yuai/.local/bin/uv sync \
  --project "${release_dir}/python-agent" \
  --frozen --python 3.12

ln -sfn "${release_dir}" "${root}/current.next"
mv -Tf "${root}/current.next" "${root}/current"

install -m 0644 "${release_dir}/deploy/production/systemd/"*.service /etc/systemd/system/
install -m 0644 "${release_dir}/deploy/production/systemd/"*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable yuai-python yuai-java yuai-mysql-backup.timer yuai-cert-renew.timer
```

- [ ] **Step 5: Create MySQL backup script**

Create `backup-mysql.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

backup_dir=/opt/RainN0Coding/data/backups/mysql
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="${backup_dir}/rainn0coding-${timestamp}.sql.gz"

install -d -m 0700 "${backup_dir}"
export MYSQL_PWD="${MYSQL_PASSWORD:?MYSQL_PASSWORD is required}"
mysqldump \
  --host=127.0.0.1 \
  --user="${MYSQL_USERNAME:?MYSQL_USERNAME is required}" \
  --single-transaction \
  --routines --triggers \
  rainn0coding | gzip -9 > "${target}"
chmod 600 "${target}"
find "${backup_dir}" -type f -name 'rainn0coding-*.sql.gz' -mtime +7 -delete
gzip -t "${target}"
echo "${target}"
```

- [ ] **Step 6: Create production verification script**

Create `verify-production.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

public_ip="${1:?public IP is required}"

for service in mysql redis-server docker yuai-python yuai-java nginx; do
  systemctl is-active --quiet "${service}" || {
    echo "inactive service: ${service}" >&2
    exit 1
  }
done

curl --fail --silent http://127.0.0.1:8000/api/health >/dev/null
curl --fail --silent http://127.0.0.1:8123/api/actuator/health >/dev/null
curl --fail --silent "https://${public_ip}/api/" >/dev/null

echo | openssl s_client -connect "${public_ip}:443" -servername "${public_ip}" 2>/dev/null |
  openssl x509 -noout -checkend 86400

disk_use="$(df --output=pcent /opt | tail -1 | tr -dc '0-9')"
if (( disk_use >= 80 )); then
  echo "disk usage is ${disk_use}%" >&2
  exit 1
fi

docker compose \
  --env-file /opt/RainN0Coding/config/milvus.env \
  -f /opt/RainN0Coding/current/milvus/docker-compose.yml ps

echo "PRODUCTION BASELINE CHECKS PASSED"
```

- [ ] **Step 7: Validate script syntax and contract tests**

Run:

```powershell
python -m unittest scripts.tests.test_production_deployment_assets -v
bash -n scripts/deploy/provision-ubuntu.sh
bash -n scripts/deploy/install-release.sh
bash -n scripts/deploy/backup-mysql.sh
bash -n scripts/deploy/verify-production.sh
```

Expected: all tests and Bash syntax checks pass.

- [ ] **Step 8: Commit**

```powershell
git add scripts/deploy scripts/tests/test_production_deployment_assets.py
git commit -m "feat: automate production release operations"
```

## Task 7: Make the Smoke Test Compatible with Secure Bootstrap

**Files:**

- Modify: `scripts/api_smoke_test.py`
- Create: `scripts/tests/test_api_smoke_test.py`

- [ ] **Step 1: Write the failing environment test**

Create:

```python
import os
import unittest
from unittest.mock import patch

from scripts.api_smoke_test import required_env


class ApiSmokeTestConfigurationTest(unittest.TestCase):
    def test_required_env_rejects_missing_value(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "SMOKE_ADMIN_PASSWORD"):
                required_env("SMOKE_ADMIN_PASSWORD")
```

- [ ] **Step 2: Run and confirm failure**

```powershell
python -m unittest scripts.tests.test_api_smoke_test -v
```

Expected: import failure because `required_env` is not defined.

- [ ] **Step 3: Require explicit smoke credentials**

Add:

```python
def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value
```

Replace:

```python
admin_account = os.getenv("SMOKE_ADMIN_ACCOUNT", "admin")
admin_password = os.getenv("SMOKE_ADMIN_PASSWORD", "admin123")
```

with:

```python
admin_account = required_env("SMOKE_ADMIN_ACCOUNT")
admin_password = required_env("SMOKE_ADMIN_PASSWORD")
```

Add:

```python
parser.add_argument(
    "--python-token",
    default=os.getenv("SMOKE_PYTHON_INTERNAL_TOKEN", ""),
)
```

After `args = parser.parse_args()`, require a configured token:

```python
python_token = args.python_token.strip() or required_env(
    "SMOKE_PYTHON_INTERNAL_TOKEN"
)
```

Pass it to the protected Python routing request:

```python
routed = python_api.post(
    "/api/route-codegen-type",
    json={"prompt": "创建一个 Vue 登录页面"},
    headers={"X-Internal-Token": python_token},
    timeout=120.0,
)
```

- [ ] **Step 4: Run unit tests and scan defaults**

```powershell
python -m unittest scripts.tests.test_api_smoke_test -v
rg -n "admin123|rainadmin123" scripts src
```

Expected: tests pass and no working default password remains.

- [ ] **Step 5: Commit**

```powershell
git add scripts/api_smoke_test.py scripts/tests/test_api_smoke_test.py
git commit -m "test: require explicit production smoke credentials"
```

## Task 8: Run the Complete Local Release Gate

**Files:**

- Build output: `src/main/resources/static/**`
- Build output: `target/RainN0Coding-0.0.1-SNAPSHOT.jar`
- Build output: `release/rainn0coding.release.tar.gz`

- [ ] **Step 1: Run frontend verification**

```powershell
Set-Location RainN0Coding-frontend
npm ci
npm test
npm run typecheck
npm run build
Set-Location ..
```

Expected: tests, type checking, and production build all pass.

- [ ] **Step 2: Run Python locked-environment verification**

```powershell
Set-Location python-agent
uv sync --frozen --python 3.12
$env:PYTHONPATH=(Get-Location).Path
uv run --frozen python -c "from workflow.code_gen_workflow import create_code_gen_workflow; print('workflow import ok')"
uv run --frozen pytest tests -q
Set-Location ..
```

Expected: workflow import prints `workflow import ok` and pytest exits successfully.

- [ ] **Step 3: Run Java verification with JDK 23**

```powershell
$env:JAVA_HOME='D:/Program Files/Java/jdk-23'
./mvnw.cmd test
./mvnw.cmd clean package -DskipTests
```

Expected: Maven reports `BUILD SUCCESS` for tests and package. If infrastructure-dependent tests fail, use `superpowers:systematic-debugging`, start the required local MySQL/Redis services, and rerun; do not waive failures silently.

- [ ] **Step 4: Package and inspect the release**

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File scripts/deploy/package-release.ps1
tar -tzf release/rainn0coding.release.tar.gz |
  Select-String -Pattern '\.env$|application-local\.yml|node_modules|\.venv|\.pnpm-store'
```

Expected: the archive hash is printed and the forbidden-file scan returns no matches.

- [ ] **Step 5: Review and commit regenerated assets**

```powershell
git diff --check
git status --short
git add src/main/resources/static
git commit -m "build: refresh verified production assets"
```

Skip this commit only if `git status --short -- src/main/resources/static` is empty.

- [ ] **Step 6: Run the multi-axis code review**

Invoke `code-review-and-quality`. Review only the deployment branch diff, address verified in-scope findings, rerun affected tests, and commit fixes separately.

## Task 9: Purchase the Lighthouse Instance with a User Payment Gate

**External state:** Tencent Cloud console.

- [ ] **Step 1: Open the signed-in Tencent Cloud purchase page**

Use `chrome:control-chrome` because this step depends on the user's authenticated browser session.

- [ ] **Step 2: Select the approved configuration**

Choose:

```text
Product: Lighthouse
Region: China Hong Kong
Image: Ubuntu Server 22.04 LTS 64-bit
CPU/RAM: 4 vCPU / 16 GB
System disk: at least 100 GB SSD
Billing period: 1 month
Auto-renewal: off for the trial
```

- [ ] **Step 3: Stop at checkout**

Report the exact displayed price, bandwidth, monthly traffic quota, disk size, and renewal price. Do not submit payment until the user explicitly confirms the displayed purchase.

- [ ] **Step 4: Let the user complete payment**

After the user confirms, allow the user to complete any password, MFA, identity, or payment step that the browser requires.

- [ ] **Step 5: Record non-secret server facts**

Record:

```text
Instance ID
Public IPv4
Private IPv4
Region/zone
Image
Purchased CPU/RAM/disk
Expiration date
```

Do not record account cookies, payment details, private keys, or console tokens.

## Task 10: Provision the Server and Create Production Secrets

**Server paths:**

- `/opt/RainN0Coding/config/java.env`
- `/opt/RainN0Coding/config/python.env`
- `/opt/RainN0Coding/config/milvus.env`

- [ ] **Step 1: Configure SSH key access**

Generate a dedicated key locally if none exists:

```powershell
ssh-keygen -t ed25519 -a 64 -f "$HOME/.ssh/yuai_lighthouse" -C "yuai-lighthouse"
```

Install only the public key through the Tencent Cloud console. Verify key login before disabling password authentication.

Capture the purchased address once for all local commands:

```powershell
$publicIp = Read-Host 'Lighthouse public IPv4'
```

- [ ] **Step 2: Upload and run provisioning**

```powershell
scp -i "$HOME/.ssh/yuai_lighthouse" `
  scripts/deploy/provision-ubuntu.sh "root@${publicIp}:/root/"
ssh -i "$HOME/.ssh/yuai_lighthouse" "root@${publicIp}" `
  "bash /root/provision-ubuntu.sh"
```

Expected: Java 21, Docker, MySQL, Redis, Nginx, Certbot, Node 22, uv, Python 3.12, 4 GB swap, directories, and UFW are ready.

- [ ] **Step 3: Generate service secrets locally without printing them**

Generate separate values:

```powershell
$mysqlPassword = -join ((48..57)+(65..90)+(97..122) | Get-Random -Count 32 | ForEach-Object {[char]$_})
$redisPassword = -join ((48..57)+(65..90)+(97..122) | Get-Random -Count 32 | ForEach-Object {[char]$_})
$internalToken = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).ToLower()
$minioUser = "yuai" + (Get-Random -Minimum 100000 -Maximum 999999)
$minioPassword = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).ToLower()
$adminPassword = [Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(24))
```

Obtain new DeepSeek, Zhipu, COS, and Pexels keys from their provider consoles. Do not reuse values found in local `.env` or `application-local.yml`.

- [ ] **Step 4: Create production EnvironmentFiles locally in a temporary protected directory**

Copy the three `.example` files outside the repository, fill every required field, set:

```powershell
$appDeployHost = "https://$publicIp/api/static"
$corsOrigin = "https://$publicIp"
$bootstrapAdminAccount = "production_admin"
```

Write those values to `APP_DEPLOY_HOST`, `APP_CORS_ALLOWED_ORIGIN_PATTERNS`,
and `BOOTSTRAP_ADMIN_ACCOUNT`. Use the same generated internal token for
`PYTHON_AI_INTERNAL_TOKEN` and `INTERNAL_API_TOKEN`.

- [ ] **Step 5: Upload and protect EnvironmentFiles**

```powershell
scp -i "$HOME/.ssh/yuai_lighthouse" java.env python.env milvus.env `
  "root@${publicIp}:/opt/RainN0Coding/config/"
ssh -i "$HOME/.ssh/yuai_lighthouse" "root@${publicIp}" `
  "printf '%s\n' '$publicIp' > /opt/RainN0Coding/config/public-ip && chown root:yuai /opt/RainN0Coding/config/*.env /opt/RainN0Coding/config/public-ip && chmod 640 /opt/RainN0Coding/config/*.env /opt/RainN0Coding/config/public-ip"
```

Expected: the `yuai` services can read the files, but they are not world-readable.

- [ ] **Step 6: Initialize MySQL and Redis securely**

Run on the server with values sourced from the protected EnvironmentFile:

```bash
set -a
source /opt/RainN0Coding/config/java.env
set +a
mysql -uroot <<SQL
CREATE DATABASE IF NOT EXISTS rainn0coding
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'rainn0coding'@'127.0.0.1'
  IDENTIFIED BY '${MYSQL_PASSWORD}';
ALTER USER 'rainn0coding'@'127.0.0.1'
  IDENTIFIED BY '${MYSQL_PASSWORD}';
GRANT ALL PRIVILEGES ON rainn0coding.* TO 'rainn0coding'@'127.0.0.1';
FLUSH PRIVILEGES;
SQL
sed -i "s/^# requirepass .*/requirepass ${REDIS_PASSWORD}/" /etc/redis/redis.conf
systemctl restart redis-server
```

Expected: application user can connect to MySQL and `redis-cli -a "$REDIS_PASSWORD" ping` returns `PONG`.

## Task 11: Install the Release, Data Stores, and Services

- [ ] **Step 1: Upload the verified archive and checksum**

```powershell
scp -i "$HOME/.ssh/yuai_lighthouse" `
  release/rainn0coding.release.tar.gz "root@${publicIp}:/opt/RainN0Coding/"
```

Compare the server SHA-256 with the local package output before extraction.

- [ ] **Step 2: Install the immutable release**

```bash
rm -rf /root/yuai-release-tools
mkdir -p /root/yuai-release-tools
tar -xzf /opt/RainN0Coding/rainn0coding.release.tar.gz \
  -C /root/yuai-release-tools \
  ./scripts/deploy/install-release.sh
bash /root/yuai-release-tools/scripts/deploy/install-release.sh \
  /opt/RainN0Coding/rainn0coding.release.tar.gz \
  "$(date -u +%Y%m%dT%H%M%SZ)"
```

- [ ] **Step 3: Initialize the database schema**

```bash
set -a
source /opt/RainN0Coding/config/java.env
set +a
export MYSQL_PWD="${MYSQL_PASSWORD}"
mysql -h127.0.0.1 -u"${MYSQL_USERNAME}" rainn0coding \
  < /opt/RainN0Coding/current/sql/create_table.sql
```

Expected: `user`, `app`, `chat_history`, `app_version`, and `intent_config` exist.

- [ ] **Step 4: Start Milvus with protected credentials**

```bash
docker compose \
  --env-file /opt/RainN0Coding/config/milvus.env \
  -f /opt/RainN0Coding/current/milvus/docker-compose.yml up -d
docker compose \
  --env-file /opt/RainN0Coding/config/milvus.env \
  -f /opt/RainN0Coding/current/milvus/docker-compose.yml ps
```

Expected: etcd, MinIO, and Milvus become healthy; ports 19530 and 9091 listen only on `127.0.0.1`.

- [ ] **Step 5: Seed retrieval data**

```bash
sudo -u yuai env \
  PYTHONPATH=/opt/RainN0Coding/current/python-agent \
  bash -c 'set -a; source /opt/RainN0Coding/config/python.env; set +a; \
  /opt/RainN0Coding/current/python-agent/.venv/bin/python \
  /opt/RainN0Coding/current/python-agent/rag/seed_milvus.py'
```

Expected: seed command exits successfully and Python health reports Milvus/SQLite connected.

- [ ] **Step 6: Start application services**

```bash
systemctl start yuai-python
curl --fail http://127.0.0.1:8000/api/health
systemctl start yuai-java
curl --fail http://127.0.0.1:8123/api/actuator/health
systemctl enable --now yuai-mysql-backup.timer yuai-cert-renew.timer
```

Expected: both health checks pass before Nginx exposes the application.

## Task 12: Issue Trusted IP HTTPS and Verify the Public Boundary

- [ ] **Step 1: Enable ACME bootstrap Nginx config**

```bash
install -m 0644 \
  /opt/RainN0Coding/current/deploy/production/nginx/rainn0coding-bootstrap.conf \
  /etc/nginx/sites-available/rainn0coding
ln -sfn /etc/nginx/sites-available/rainn0coding \
  /etc/nginx/sites-enabled/rainn0coding
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx
```

- [ ] **Step 2: Request the short-lived IP certificate**

```bash
read -r -p "Public IPv4: " PUBLIC_IP
read -r -p "Certificate contact email: " CERTBOT_EMAIL
certbot certonly \
  --preferred-profile shortlived \
  --webroot \
  --webroot-path /var/www/certbot \
  --ip-address "${PUBLIC_IP}" \
  --agree-tos \
  --email "${CERTBOT_EMAIL}" \
  --non-interactive
```

Expected: certificate files exist under `/etc/letsencrypt/live/${PUBLIC_IP}/`.

- [ ] **Step 3: Render and enable HTTPS config**

```bash
envsubst '${PUBLIC_IP}' \
  < /opt/RainN0Coding/current/deploy/production/nginx/rainn0coding-https.conf.template \
  > /etc/nginx/sites-available/rainn0coding
nginx -t
systemctl reload nginx
```

Expected: `https://${PUBLIC_IP}/api/` opens with a publicly trusted certificate and HTTP redirects to HTTPS.

- [ ] **Step 4: Test renewal automation**

```bash
certbot renew --dry-run
systemctl start yuai-cert-renew.service
systemctl status yuai-cert-renew.timer --no-pager
```

Expected: dry-run succeeds, Nginx reload hook succeeds, and the six-hour timer is active.

- [ ] **Step 5: Verify network exposure**

From the local machine:

```powershell
Test-NetConnection $publicIp -Port 22
Test-NetConnection $publicIp -Port 80
Test-NetConnection $publicIp -Port 443
Test-NetConnection $publicIp -Port 8123
Test-NetConnection $publicIp -Port 8000
Test-NetConnection $publicIp -Port 3306
Test-NetConnection $publicIp -Port 6379
Test-NetConnection $publicIp -Port 19530
```

Expected: 22, 80, and 443 succeed; all internal ports fail.

## Task 13: Execute Business, Restart, Backup, and Rollback Acceptance

- [ ] **Step 1: Run the server baseline verifier**

```bash
public_ip="$(cat /opt/RainN0Coding/config/public-ip)"
/opt/RainN0Coding/current/scripts/deploy/verify-production.sh "${public_ip}"
```

Expected: `PRODUCTION BASELINE CHECKS PASSED`.

- [ ] **Step 2: Run fast API smoke tests**

From the local machine, provide the generated administrator credentials through environment variables:

```powershell
$env:SMOKE_ADMIN_ACCOUNT='production_admin'
$env:SMOKE_ADMIN_PASSWORD=$adminPassword
$tunnel = Start-Process -FilePath ssh -WindowStyle Hidden -PassThru `
  -ArgumentList @(
    '-N', '-L', '18000:127.0.0.1:8000',
    '-i', "$HOME/.ssh/yuai_lighthouse", "root@$publicIp"
  )
try {
  python scripts/api_smoke_test.py `
    --java-base "https://$publicIp/api" `
    --python-base http://127.0.0.1:18000 `
    --python-token $internalToken `
    --skip-generation
} finally {
  Stop-Process -Id $tunnel.Id
}
```

Expected: CRUD, authentication, authorization, version, and configuration checks pass.

- [ ] **Step 3: Run one complete generation**

Run:

```powershell
$tunnel = Start-Process -FilePath ssh -WindowStyle Hidden -PassThru `
  -ArgumentList @(
    '-N', '-L', '18000:127.0.0.1:8000',
    '-i', "$HOME/.ssh/yuai_lighthouse", "root@$publicIp"
  )
try {
  python scripts/api_smoke_test.py `
    --java-base "https://$publicIp/api" `
    --python-base http://127.0.0.1:18000 `
    --python-token $internalToken
} finally {
  Stop-Process -Id $tunnel.Id
}
```

Expected: SSE produces a successful terminal event, generated files build, download works, deploy returns an HTTPS URL, and the deployed page returns `text/html`.

- [ ] **Step 4: Verify daily backup and restore**

```bash
systemctl start yuai-mysql-backup.service
latest_backup="$(ls -1t /opt/RainN0Coding/data/backups/mysql/*.sql.gz | head -1)"
gzip -t "${latest_backup}"
mysql -uroot -e 'DROP DATABASE IF EXISTS rainn0coding_restore_test;
CREATE DATABASE rainn0coding_restore_test CHARACTER SET utf8mb4;'
gunzip -c "${latest_backup}" |
  mysql -uroot rainn0coding_restore_test
mysql -uroot -Nse \
  "SELECT COUNT(*) FROM information_schema.tables
   WHERE table_schema='rainn0coding_restore_test';"
mysql -uroot -e 'DROP DATABASE rainn0coding_restore_test;'
```

Expected: restore-test table count is at least 5.

- [ ] **Step 5: Verify reboot recovery**

Create a Lighthouse snapshot, then:

```bash
reboot
```

After SSH returns:

```bash
public_ip="$(cat /opt/RainN0Coding/config/public-ip)"
/opt/RainN0Coding/current/scripts/deploy/verify-production.sh "${public_ip}"
```

Expected: all services, data, HTTPS, and timers recover automatically.

- [ ] **Step 6: Exercise application rollback**

Run:

```bash
previous_release="$(readlink -f /opt/RainN0Coding/current)"
rollback_test_id="rollback-test-$(date -u +%Y%m%dT%H%M%SZ)"
bash /root/yuai-release-tools/scripts/deploy/install-release.sh \
  /opt/RainN0Coding/rainn0coding.release.tar.gz \
  "${rollback_test_id}"
ln -sfn "${previous_release}" /opt/RainN0Coding/current.next
mv -Tf /opt/RainN0Coding/current.next /opt/RainN0Coding/current
systemctl restart yuai-python yuai-java
public_ip="$(cat /opt/RainN0Coding/config/public-ip)"
/opt/RainN0Coding/current/scripts/deploy/verify-production.sh "${public_ip}"
```

Expected: atomic symlink rollback restores a healthy release without data loss.

- [ ] **Step 7: Record acceptance evidence**

Capture:

```text
Public HTTPS URL
Release commit SHA
Release archive SHA-256
Service status summary
Certificate issuer and expiry
External port results
Smoke-test final line
Backup filename and restore table count
Post-reboot verification result
Rollback verification result
```

Never include passwords, API keys, private keys, cookies, or EnvironmentFile contents.

## Task 14: Update the Runbook and Final Handoff

**Files:**

- Modify: `docs/tencent-cloud-deployment-runbook.md`

- [ ] **Step 1: Correct stale blocker descriptions**

Update the runbook to state that deploy-host configuration, deploy-root alignment, `app_version` schema, BCrypt, administrator-only AppVersion endpoints, and path containment are implemented. Keep the secure bootstrap and key rotation requirements.

- [ ] **Step 2: Document the automated assets**

Add exact references to:

```text
deploy/production/
scripts/deploy/package-release.ps1
scripts/deploy/provision-ubuntu.sh
scripts/deploy/install-release.sh
scripts/deploy/backup-mysql.sh
scripts/deploy/verify-production.sh
```

Document Certbot 5.4+ `shortlived` IP certificate issuance and the six-hour renewal timer.

- [ ] **Step 3: Run final documentation and repository checks**

```powershell
rg -n "admin123|rainadmin123|minioadmin" docs deploy scripts src
git diff --check
git status --short
```

Expected: no real default credentials and no whitespace errors.

- [ ] **Step 4: Verify before completion**

Invoke `superpowers:verification-before-completion`. Re-run the local release gate and the production acceptance commands whose evidence will be reported.

- [ ] **Step 5: Commit the final runbook**

```powershell
git add docs/tencent-cloud-deployment-runbook.md
git commit -m "docs: finalize production operations runbook"
```

- [ ] **Step 6: Present completion evidence**

Report the live HTTPS URL, release SHA, test results, backup/restore evidence, reboot recovery, rollback result, monitoring exclusion, and the exact follow-up needed before the one-month server expires.
