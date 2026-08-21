# RainN0Coding Cloud Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有腾讯云2核4G服务器上部署仅通过SSH隧道访问的Prometheus、Tempo、OpenTelemetry Collector和Grafana，并验证本地Java/Python的指标与完整Trace。

**Architecture:** Prometheus在云端使用host network抓取SSH反向转发出来的Java/Python指标端口；Java/Python通过SSH正向转发把OTLP HTTP Trace发送给云端Collector；Collector写入单机Tempo，Grafana统一查询Prometheus和Tempo。监控Compose与现有MySQL/Redis/Qdrant Compose隔离，所有宿主机端口只绑定`127.0.0.1`。

**Tech Stack:** Docker Compose、Prometheus 3.12.0、Tempo 2.10.7、OpenTelemetry Collector Contrib 0.157.0、Grafana 13.1.0、PowerShell OpenSSH、Python unittest + PyYAML。

---

## File map

- `deploy/cloud-monitoring/compose.monitoring.yml`: 四个云端监控服务、资源上限、网络与Volume。
- `deploy/cloud-monitoring/.env.example`: 非秘密的Grafana环境变量模板。
- `deploy/cloud-monitoring/prometheus/prometheus.yml`: Prometheus保留策略以外的抓取配置。
- `deploy/cloud-monitoring/tempo/tempo.yaml`: Tempo单机、本地存储、24小时保留配置。
- `deploy/cloud-monitoring/otel/collector.yaml`: OTLP接收、内存保护、批处理和Tempo导出。
- `deploy/cloud-monitoring/grafana/provisioning/datasources/datasources.yaml`: Prometheus、Tempo数据源。
- `deploy/cloud-monitoring/grafana/provisioning/dashboards/dashboards.yaml`: Dashboard文件加载配置。
- `deploy/cloud-monitoring/grafana/dashboards/rainn0coding-overview.json`: Java/Python存活和请求速率概览。
- `deploy/cloud-monitoring/start-monitoring-tunnel.ps1`: 数据层、Grafana、OTLP正向转发与指标反向转发。
- `deploy/cloud-monitoring/tests/test_monitoring_bundle.py`: 部署包静态契约测试。
- `deploy/cloud-monitoring/README.md`: 上传、启动、验收、停止和回滚操作手册。

### Task 1: Add failing deployment-contract tests

**Files:**
- Create: `deploy/cloud-monitoring/tests/test_monitoring_bundle.py`

- [ ] **Step 1: Write the deployment contract test**

```python
from pathlib import Path
import re
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


class MonitoringBundleContractTest(unittest.TestCase):
    def load_yaml(self, relative_path: str):
        return yaml.safe_load((ROOT / relative_path).read_text(encoding="utf-8"))

    def test_compose_uses_pinned_images_and_expected_services(self):
        compose = self.load_yaml("compose.monitoring.yml")
        services = compose["services"]
        self.assertEqual(
            set(services),
            {"prometheus", "tempo", "otel-collector", "grafana"},
        )
        self.assertEqual(services["prometheus"]["image"], "prom/prometheus:v3.12.0")
        self.assertEqual(services["tempo"]["image"], "grafana/tempo:2.10.7")
        self.assertEqual(
            services["otel-collector"]["image"],
            "otel/opentelemetry-collector-contrib:0.157.0",
        )
        self.assertEqual(services["grafana"]["image"], "grafana/grafana:13.1.0")
        self.assertNotIn(":latest", (ROOT / "compose.monitoring.yml").read_text(encoding="utf-8"))

    def test_host_ports_are_loopback_only(self):
        compose = self.load_yaml("compose.monitoring.yml")
        services = compose["services"]
        self.assertEqual(services["grafana"]["ports"], ["127.0.0.1:3000:3000"])
        self.assertEqual(
            services["otel-collector"]["ports"],
            ["127.0.0.1:4317:4317", "127.0.0.1:4318:4318"],
        )
        self.assertEqual(services["prometheus"]["network_mode"], "host")
        self.assertIn("--web.listen-address=127.0.0.1:9090", services["prometheus"]["command"])

    def test_resource_and_persistence_limits_are_present(self):
        compose = self.load_yaml("compose.monitoring.yml")
        services = compose["services"]
        self.assertEqual(services["grafana"]["mem_limit"], "512m")
        self.assertEqual(services["prometheus"]["mem_limit"], "384m")
        self.assertEqual(services["tempo"]["mem_limit"], "384m")
        self.assertEqual(services["otel-collector"]["mem_limit"], "192m")
        self.assertEqual(
            set(compose["volumes"]),
            {"grafana_data", "prometheus_data", "tempo_data"},
        )
        self.assertIn("--storage.tsdb.retention.time=3d", services["prometheus"]["command"])
        self.assertIn("--storage.tsdb.retention.size=512MB", services["prometheus"]["command"])

    def test_prometheus_targets_reverse_tunnel_ports(self):
        config = self.load_yaml("prometheus/prometheus.yml")
        jobs = {job["job_name"]: job for job in config["scrape_configs"]}
        self.assertEqual(
            jobs["RainN0Coding-java"]["static_configs"][0]["targets"],
            ["127.0.0.1:18123"],
        )
        self.assertEqual(jobs["RainN0Coding-java"]["metrics_path"], "/api/actuator/prometheus")
        self.assertEqual(
            jobs["RainN0Coding-python"]["static_configs"][0]["targets"],
            ["127.0.0.1:18000"],
        )
        self.assertEqual(jobs["RainN0Coding-python"]["metrics_path"], "/metrics")

    def test_tempo_retains_traces_for_24_hours(self):
        tempo = self.load_yaml("tempo/tempo.yaml")
        self.assertFalse(tempo["auth_enabled"])
        self.assertEqual(tempo["storage"]["trace"]["backend"], "local")
        self.assertEqual(tempo["compactor"]["compaction"]["block_retention"], "24h")

    def test_collector_exports_otlp_to_tempo(self):
        collector = self.load_yaml("otel/collector.yaml")
        traces = collector["service"]["pipelines"]["traces"]
        self.assertEqual(traces["receivers"], ["otlp"])
        self.assertEqual(traces["processors"], ["memory_limiter", "batch"])
        self.assertEqual(traces["exporters"], ["otlp/tempo"])
        self.assertEqual(collector["exporters"]["otlp/tempo"]["endpoint"], "tempo:4317")

    def test_tunnel_script_contains_all_forwards(self):
        script = (ROOT / "start-monitoring-tunnel.ps1").read_text(encoding="utf-8")
        expected = {
            "13306:127.0.0.1:3306",
            "16379:127.0.0.1:6379",
            "16333:127.0.0.1:6333",
            "13000:127.0.0.1:3000",
            "14318:127.0.0.1:4318",
            "19090:127.0.0.1:9090",
            "18123:127.0.0.1:8123",
            "18000:127.0.0.1:8000",
        }
        for forward in expected:
            self.assertIn(forward, script)
        self.assertRegex(script, re.compile(r"ExitOnForwardFailure=yes"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and confirm the RED state**

Run from `D:\yu-ai-code-mother`:

```powershell
& 'D:\yu-ai-code-mother\python-agent\.venv\Scripts\python.exe' `
  'D:\yu-ai-code-mother\deploy\cloud-monitoring\tests\test_monitoring_bundle.py' `
  -v
```

Expected: tests fail with `FileNotFoundError` for `compose.monitoring.yml` and the other not-yet-created deployment files. The test file itself must collect successfully.

- [ ] **Step 3: Commit only the RED test**

```powershell
git add -- deploy/cloud-monitoring/tests/test_monitoring_bundle.py
git commit -m "test: define cloud monitoring bundle contract"
```

### Task 2: Implement the Compose, Prometheus, Tempo, and Collector bundle

**Files:**
- Create: `deploy/cloud-monitoring/compose.monitoring.yml`
- Create: `deploy/cloud-monitoring/.env.example`
- Create: `deploy/cloud-monitoring/prometheus/prometheus.yml`
- Create: `deploy/cloud-monitoring/tempo/tempo.yaml`
- Create: `deploy/cloud-monitoring/otel/collector.yaml`

- [ ] **Step 1: Create `compose.monitoring.yml`**

```yaml
name: rainn0coding-monitoring

services:
  prometheus:
    image: prom/prometheus:v3.12.0
    container_name: rainn0coding-prometheus
    network_mode: host
    command:
      - --config.file=/etc/prometheus/prometheus.yml
      - --storage.tsdb.path=/prometheus
      - --storage.tsdb.retention.time=3d
      - --storage.tsdb.retention.size=512MB
      - --web.listen-address=127.0.0.1:9090
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus_data:/prometheus
    mem_limit: 384m
    restart: unless-stopped

  tempo:
    image: grafana/tempo:2.10.7
    container_name: rainn0coding-tempo
    command:
      - -config.file=/etc/tempo/tempo.yaml
    volumes:
      - ./tempo/tempo.yaml:/etc/tempo/tempo.yaml:ro
      - tempo_data:/var/tempo
    expose:
      - "3200"
      - "4317"
    mem_limit: 384m
    restart: unless-stopped
    networks:
      - monitoring

  otel-collector:
    image: otel/opentelemetry-collector-contrib:0.157.0
    container_name: rainn0coding-otel-collector
    command:
      - --config=/etc/otelcol-contrib/collector.yaml
    ports:
      - "127.0.0.1:4317:4317"
      - "127.0.0.1:4318:4318"
    volumes:
      - ./otel/collector.yaml:/etc/otelcol-contrib/collector.yaml:ro
    depends_on:
      - tempo
    mem_limit: 192m
    restart: unless-stopped
    networks:
      - monitoring

  grafana:
    image: grafana/grafana:13.1.0
    container_name: rainn0coding-grafana
    ports:
      - "127.0.0.1:3000:3000"
    environment:
      GF_SECURITY_ADMIN_USER: admin
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD:?GRAFANA_ADMIN_PASSWORD is required}
      GF_USERS_ALLOW_SIGN_UP: "false"
      GF_AUTH_ANONYMOUS_ENABLED: "false"
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning:ro
      - ./grafana/dashboards:/var/lib/grafana/dashboards:ro
    depends_on:
      - tempo
    extra_hosts:
      - "host.docker.internal:host-gateway"
    mem_limit: 512m
    restart: unless-stopped
    networks:
      - monitoring

networks:
  monitoring:

volumes:
  grafana_data:
  prometheus_data:
  tempo_data:
```

- [ ] **Step 2: Create `.env.example`**

```dotenv
GRAFANA_ADMIN_PASSWORD=replace-with-a-random-secret
```

- [ ] **Step 3: Create the Prometheus scrape config**

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: prometheus
    static_configs:
      - targets: ["127.0.0.1:9090"]

  - job_name: RainN0Coding-java
    metrics_path: /api/actuator/prometheus
    scrape_interval: 10s
    scrape_timeout: 5s
    static_configs:
      - targets: ["127.0.0.1:18123"]

  - job_name: RainN0Coding-python
    metrics_path: /metrics
    scrape_interval: 10s
    scrape_timeout: 5s
    static_configs:
      - targets: ["127.0.0.1:18000"]
```

- [ ] **Step 4: Create the Tempo config**

```yaml
auth_enabled: false

server:
  http_listen_port: 3200
  grpc_listen_port: 9095

distributor:
  receivers:
    otlp:
      protocols:
        grpc:
          endpoint: 0.0.0.0:4317
        http:
          endpoint: 0.0.0.0:4318

ingester:
  max_block_duration: 5m

compactor:
  compaction:
    block_retention: 24h

storage:
  trace:
    backend: local
    wal:
      path: /var/tempo/wal
    local:
      path: /var/tempo/traces

usage_report:
  reporting_enabled: false
```

- [ ] **Step 5: Create the Collector config**

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 128
    spike_limit_mib: 32
  batch:
    timeout: 1s
    send_batch_size: 256

exporters:
  otlp/tempo:
    endpoint: tempo:4317
    tls:
      insecure: true

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlp/tempo]
```

- [ ] **Step 6: Run the contract tests and inspect remaining failures**

```powershell
& 'D:\yu-ai-code-mother\python-agent\.venv\Scripts\python.exe' `
  'D:\yu-ai-code-mother\deploy\cloud-monitoring\tests\test_monitoring_bundle.py' `
  -v
```

Expected: Compose, Prometheus, Tempo, and Collector tests pass; only missing Grafana and tunnel files remain failing.

- [ ] **Step 7: Validate Compose rendering with a non-secret test value**

```powershell
$env:GRAFANA_ADMIN_PASSWORD='validation-only-not-for-deployment'
docker compose `
  -f deploy/cloud-monitoring/compose.monitoring.yml `
  config --quiet
Remove-Item Env:GRAFANA_ADMIN_PASSWORD
```

Expected: exit code `0` with no schema error.

- [ ] **Step 8: Commit the core monitoring services**

```powershell
git add -- `
  deploy/cloud-monitoring/compose.monitoring.yml `
  deploy/cloud-monitoring/.env.example `
  deploy/cloud-monitoring/prometheus/prometheus.yml `
  deploy/cloud-monitoring/tempo/tempo.yaml `
  deploy/cloud-monitoring/otel/collector.yaml
git commit -m "feat: add cloud monitoring services"
```

### Task 3: Provision Grafana data sources and dashboard

**Files:**
- Create: `deploy/cloud-monitoring/grafana/provisioning/datasources/datasources.yaml`
- Create: `deploy/cloud-monitoring/grafana/provisioning/dashboards/dashboards.yaml`
- Create: `deploy/cloud-monitoring/grafana/dashboards/rainn0coding-overview.json`

- [ ] **Step 1: Create the data-source provisioning file**

```yaml
apiVersion: 1

deleteDatasources:
  - name: Prometheus
    orgId: 1
  - name: Tempo
    orgId: 1

datasources:
  - name: Prometheus
    uid: prometheus
    type: prometheus
    access: proxy
    url: http://host.docker.internal:9090
    isDefault: true
    editable: false
    jsonData:
      timeInterval: 15s

  - name: Tempo
    uid: tempo
    type: tempo
    access: proxy
    url: http://tempo:3200
    editable: false
    jsonData:
      httpMethod: GET
      tracesToMetrics:
        datasourceUid: prometheus
        tags:
          - key: service.name
            value: service
```

- [ ] **Step 2: Create the dashboard provisioning file**

```yaml
apiVersion: 1

providers:
  - name: RainN0Coding
    orgId: 1
    folder: RainN0Coding
    type: file
    disableDeletion: true
    allowUiUpdates: false
    updateIntervalSeconds: 30
    options:
      path: /var/lib/grafana/dashboards
```

- [ ] **Step 3: Create the minimal overview dashboard**

```json
{
  "annotations": {"list": []},
  "editable": false,
  "fiscalYearStartMonth": 0,
  "graphTooltip": 1,
  "id": null,
  "links": [],
  "panels": [
    {
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "fieldConfig": {"defaults": {"mappings": [], "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": null}, {"color": "green", "value": 1}]}}, "overrides": []},
      "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
      "id": 1,
      "options": {"colorMode": "background", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": false}, "textMode": "auto", "wideLayout": true},
      "targets": [{"expr": "up{job=~\"RainN0Coding-.+\"}", "legendFormat": "{{job}}", "refId": "A"}],
      "title": "Java / Python Targets",
      "type": "stat"
    },
    {
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "fieldConfig": {"defaults": {"unit": "reqps"}, "overrides": []},
      "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0},
      "id": 2,
      "options": {"legend": {"calcs": [], "displayMode": "list", "placement": "bottom", "showLegend": true}, "tooltip": {"mode": "single", "sort": "none"}},
      "targets": [
        {"expr": "sum(rate(http_server_requests_seconds_count[5m]))", "legendFormat": "Java", "refId": "A"},
        {"expr": "sum(rate(http_requests_total[5m]))", "legendFormat": "Python", "refId": "B"}
      ],
      "title": "Request Rate",
      "type": "timeseries"
    },
    {
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "fieldConfig": {"defaults": {"unit": "bytes"}, "overrides": []},
      "gridPos": {"h": 8, "w": 12, "x": 0, "y": 8},
      "id": 3,
      "options": {"legend": {"calcs": [], "displayMode": "list", "placement": "bottom", "showLegend": true}, "tooltip": {"mode": "single", "sort": "none"}},
      "targets": [{"expr": "sum(jvm_memory_used_bytes)", "legendFormat": "JVM used", "refId": "A"}],
      "title": "JVM Memory",
      "type": "timeseries"
    },
    {
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "fieldConfig": {"defaults": {"unit": "s"}, "overrides": []},
      "gridPos": {"h": 8, "w": 12, "x": 12, "y": 8},
      "id": 4,
      "options": {"legend": {"calcs": [], "displayMode": "list", "placement": "bottom", "showLegend": true}, "tooltip": {"mode": "single", "sort": "none"}},
      "targets": [{"expr": "histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket[5m])))", "legendFormat": "Python p95", "refId": "A"}],
      "title": "Python HTTP p95",
      "type": "timeseries"
    }
  ],
  "refresh": "15s",
  "schemaVersion": 42,
  "tags": ["RainN0Coding", "demo"],
  "templating": {"list": []},
  "time": {"from": "now-1h", "to": "now"},
  "timezone": "browser",
  "title": "RainN0Coding Overview",
  "uid": "rainn0coding-overview",
  "version": 1
}
```

- [ ] **Step 4: Validate YAML and JSON syntax**

```powershell
& 'D:\yu-ai-code-mother\python-agent\.venv\Scripts\python.exe' -c `
  "import json, pathlib, yaml; root=pathlib.Path('deploy/cloud-monitoring'); yaml.safe_load((root/'grafana/provisioning/datasources/datasources.yaml').read_text(encoding='utf-8')); yaml.safe_load((root/'grafana/provisioning/dashboards/dashboards.yaml').read_text(encoding='utf-8')); json.loads((root/'grafana/dashboards/rainn0coding-overview.json').read_text(encoding='utf-8')); print('GRAFANA_CONFIG_OK')"
```

Expected: `GRAFANA_CONFIG_OK`.

- [ ] **Step 5: Commit Grafana provisioning**

```powershell
git add -- deploy/cloud-monitoring/grafana
git commit -m "feat: provision cloud monitoring dashboards"
```

### Task 4: Add the unified SSH tunnel script

**Files:**
- Create: `deploy/cloud-monitoring/start-monitoring-tunnel.ps1`

- [ ] **Step 1: Create the tunnel script**

```powershell
[CmdletBinding()]
param(
    [string]$Server = '124.223.164.223',
    [string]$User = 'ubuntu'
)

$sshArguments = @(
    '-N',
    '-T',
    '-o', 'ExitOnForwardFailure=yes',
    '-o', 'ServerAliveInterval=30',
    '-o', 'ServerAliveCountMax=3',
    '-L', '13306:127.0.0.1:3306',
    '-L', '16379:127.0.0.1:6379',
    '-L', '16333:127.0.0.1:6333',
    '-L', '13000:127.0.0.1:3000',
    '-L', '14318:127.0.0.1:4318',
    '-L', '19090:127.0.0.1:9090',
    '-R', '18123:127.0.0.1:8123',
    '-R', '18000:127.0.0.1:8000',
    "$User@$Server"
)

Write-Host 'Starting RainN0Coding data and monitoring tunnel.'
Write-Host 'Keep this window open during the demo.'
Write-Host 'Grafana: http://127.0.0.1:13000'
Write-Host 'Prometheus diagnostics: http://127.0.0.1:19090'

& ssh @sshArguments
exit $LASTEXITCODE
```

- [ ] **Step 2: Parse the PowerShell script without opening a connection**

```powershell
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile(
  'D:\yu-ai-code-mother\deploy\cloud-monitoring\start-monitoring-tunnel.ps1',
  [ref]$null,
  [ref]$errors
) | Out-Null
if ($errors.Count -gt 0) { $errors | Format-List; exit 1 }
'TUNNEL_SCRIPT_OK'
```

Expected: `TUNNEL_SCRIPT_OK`.

- [ ] **Step 3: Run the full bundle contract test**

```powershell
& 'D:\yu-ai-code-mother\python-agent\.venv\Scripts\python.exe' `
  'D:\yu-ai-code-mother\deploy\cloud-monitoring\tests\test_monitoring_bundle.py' `
  -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit the tunnel script**

```powershell
git add -- deploy/cloud-monitoring/start-monitoring-tunnel.ps1
git commit -m "feat: add secure monitoring tunnel"
```

### Task 5: Write the operator runbook

**Files:**
- Create: `deploy/cloud-monitoring/README.md`

- [ ] **Step 1: Write the runbook with the following complete content**

```markdown
# RainN0Coding cloud monitoring

This bundle deploys Prometheus, Tempo, OpenTelemetry Collector, and Grafana on the existing Tencent Cloud server. It never opens monitoring ports to the public Internet.

## Local prerequisites

- Java listens on `127.0.0.1:8123` and exposes `/api/actuator/prometheus`.
- Python listens on `127.0.0.1:8000` and exposes `/metrics`.
- Windows OpenSSH can log in to `ubuntu@124.223.164.223`.

## Upload

From PowerShell in `D:\yu-ai-code-mother`:

```powershell
$bundle = Join-Path $env:TEMP 'rainn0coding-cloud-monitoring.tar.gz'
tar.exe -czf $bundle -C .\deploy\cloud-monitoring .
scp.exe $bundle ubuntu@124.223.164.223:/home/ubuntu/rainn0coding-cloud-monitoring.tar.gz
```

In the Tencent Cloud terminal:

```bash
mkdir -p /home/ubuntu/rainn0coding-cloud/monitoring
tar -xzf /home/ubuntu/rainn0coding-cloud-monitoring.tar.gz \
  -C /home/ubuntu/rainn0coding-cloud/monitoring
cd /home/ubuntu/rainn0coding-cloud/monitoring
```

## Secret initialization

```bash
umask 077
if [ ! -f .env ]; then
  GRAFANA_ADMIN_SECRET="$(openssl rand -hex 24)"
  printf 'GRAFANA_ADMIN_PASSWORD=%s\n' "$GRAFANA_ADMIN_SECRET" > .env
  unset GRAFANA_ADMIN_SECRET
fi
chmod 600 .env
test "$(stat -c '%a' .env)" = '600'
```

Do not print or commit `.env`. Read it only when entering the Grafana password.

## Start cloud monitoring

```bash
docker compose -f compose.monitoring.yml config --quiet
docker compose -f compose.monitoring.yml pull
docker compose -f compose.monitoring.yml up -d
docker compose -f compose.monitoring.yml ps
```

## Start the Windows tunnel

Run in a dedicated PowerShell window and keep it open:

```powershell
& 'D:\yu-ai-code-mother\deploy\cloud-monitoring\start-monitoring-tunnel.ps1'
```

## Configure local applications

Add this environment variable to the IDEA Spring Boot configuration:

```text
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:14318/v1/traces
```

Add these environment variables to the PyCharm Python Agent configuration:

```text
OTEL_EXPORTER_ENABLED=true
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:14318/v1/traces
```

Restart both applications after changing environment variables.

## Verify

```powershell
curl.exe -fsS http://127.0.0.1:13000/api/health
curl.exe -fsS http://127.0.0.1:19090/-/ready
curl.exe -fsS http://127.0.0.1:8123/api/actuator/prometheus
curl.exe -fsS http://127.0.0.1:8000/metrics
```

Open Grafana at `http://127.0.0.1:13000`. Sign in as `admin` with the secret stored in the cloud `.env` file. Open the `RainN0Coding Overview` dashboard. In Explore, select Tempo and query:

```traceql
{ resource.service.name = "RainN0Coding-backend" }
```

and:

```traceql
{ resource.service.name = "python-agent" }
```

## Stop and resume

Stop monitoring without deleting data:

```bash
cd /home/ubuntu/rainn0coding-cloud/monitoring
docker compose -f compose.monitoring.yml stop
```

Resume:

```bash
docker compose -f compose.monitoring.yml start
```

Never run `docker compose down -v` because it deletes monitoring history.

## Roll back monitoring only

```bash
cd /home/ubuntu/rainn0coding-cloud/monitoring
docker compose -f compose.monitoring.yml down
```

This removes only monitoring containers and their network. It preserves named volumes and does not touch the data-service Compose project.
```

- [ ] **Step 2: Check the runbook for forbidden public-port instructions and destructive volume deletion**

```powershell
rg -n '0\.0\.0\.0:(3000|9090|3200|4317|4318)|down -v|ufw allow|安全组.*(3000|9090|3200|4317|4318)' `
  deploy/cloud-monitoring
```

Expected: only the warning `Never run docker compose down -v` may match; no instruction binds or opens a public monitoring port.

- [ ] **Step 3: Commit the runbook**

```powershell
git add -- deploy/cloud-monitoring/README.md
git commit -m "docs: add cloud monitoring runbook"
```

### Task 6: Run local quality gates and package the deployment bundle

**Files:**
- Verify: `deploy/cloud-monitoring/**`

- [ ] **Step 1: Run the bundle contract tests**

```powershell
& 'D:\yu-ai-code-mother\python-agent\.venv\Scripts\python.exe' `
  'D:\yu-ai-code-mother\deploy\cloud-monitoring\tests\test_monitoring_bundle.py' `
  -v
```

Expected: all tests pass.

- [ ] **Step 2: Render Compose and list exact images**

```powershell
$env:GRAFANA_ADMIN_PASSWORD='validation-only-not-for-deployment'
docker compose -f deploy/cloud-monitoring/compose.monitoring.yml config --quiet
docker compose -f deploy/cloud-monitoring/compose.monitoring.yml config --images
Remove-Item Env:GRAFANA_ADMIN_PASSWORD
```

Expected image list:

```text
grafana/grafana:13.1.0
grafana/tempo:2.10.7
otel/opentelemetry-collector-contrib:0.157.0
prom/prometheus:v3.12.0
```

- [ ] **Step 3: Run whitespace and secret scans**

```powershell
git diff --check
rg -n 'GRAFANA_ADMIN_PASSWORD=(admin|replace-with-a-random-secret)$|:latest|124\.223\.164\.223:(3000|9090|3200|4317|4318)' `
  deploy/cloud-monitoring `
  -g '!**/.env.example'
```

Expected: no matches and `git diff --check` exits zero.

- [ ] **Step 4: Confirm unrelated working-tree changes remain untouched**

```powershell
git status --short
git log --oneline -6
```

Expected: monitoring commits are present; the user's pre-existing unrelated changes remain exactly as they were.

### Task 7: Upload and start the monitoring stack on Tencent Cloud

**Files:**
- Deploy: `deploy/cloud-monitoring/**` to `/home/ubuntu/rainn0coding-cloud/monitoring/`

- [ ] **Step 1: Package and upload from local PowerShell**

```powershell
$bundle = Join-Path $env:TEMP 'rainn0coding-cloud-monitoring.tar.gz'
tar.exe -czf $bundle -C .\deploy\cloud-monitoring .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
scp.exe $bundle ubuntu@124.223.164.223:/home/ubuntu/rainn0coding-cloud-monitoring.tar.gz
```

Expected: `scp` exits zero. The archive contains no `.env` file because only `.env.example` exists locally.

- [ ] **Step 2: Extract and initialize the cloud secret in the Tencent terminal**

```bash
mkdir -p /home/ubuntu/rainn0coding-cloud/monitoring
tar -xzf /home/ubuntu/rainn0coding-cloud-monitoring.tar.gz \
  -C /home/ubuntu/rainn0coding-cloud/monitoring
cd /home/ubuntu/rainn0coding-cloud/monitoring

umask 077
if [ ! -f .env ]; then
  GRAFANA_ADMIN_SECRET="$(openssl rand -hex 24)"
  printf 'GRAFANA_ADMIN_PASSWORD=%s\n' "$GRAFANA_ADMIN_SECRET" > .env
  unset GRAFANA_ADMIN_SECRET
fi
chmod 600 .env
test "$(stat -c '%a' .env)" = '600' && echo SECRET_FILE_OK
```

Expected: `SECRET_FILE_OK`. Do not print `.env`.

- [ ] **Step 3: Validate and pull fixed images**

```bash
docker compose -f compose.monitoring.yml config --quiet
docker compose -f compose.monitoring.yml config --images
docker compose -f compose.monitoring.yml pull
```

Expected: exactly the four pinned images are listed and pulled successfully.

- [ ] **Step 4: Start the monitoring containers**

```bash
docker compose -f compose.monitoring.yml up -d
docker compose -f compose.monitoring.yml ps
```

Expected: `rainn0coding-prometheus`, `rainn0coding-tempo`, `rainn0coding-otel-collector`, and `rainn0coding-grafana` remain `Up` without restart loops.

- [ ] **Step 5: Verify cloud-local readiness and loopback bindings**

```bash
curl -fsS http://127.0.0.1:9090/-/ready
curl -fsS http://127.0.0.1:3000/api/health
docker compose -f compose.monitoring.yml logs --tail=100 tempo otel-collector
ss -lnt | grep -E '127\.0\.0\.1:(3000|9090|4317|4318)'
```

Expected:

- Prometheus reports ready.
- Grafana JSON contains `"database":"ok"`.
- Tempo/Collector logs contain no config parse error or repeated export failure.
- All published monitoring sockets shown by `ss` use `127.0.0.1`; no monitoring service is bound to `0.0.0.0` on the host.

- [ ] **Step 6: Verify original data services are still healthy**

```bash
cd /home/ubuntu/rainn0coding-cloud
docker compose ps
curl -fsS http://127.0.0.1:6333/healthz
docker exec rainn0coding-redis redis-cli ping
```

Expected: MySQL, Redis, Qdrant remain healthy; Qdrant says `healthz check passed`; Redis says `PONG`.

### Task 8: Establish tunnels and configure local Java/Python

**Files:**
- Runtime configuration only: IDEA `RainN0CodingApplication`
- Runtime configuration only: PyCharm `Python Agent Cloud`

- [ ] **Step 1: Stop the old SSH tunnel process**

Close only the PowerShell window running the old `ssh -N` tunnel. Do not stop Java, Python, Docker, or cloud data containers yet.

- [ ] **Step 2: Start the unified tunnel**

```powershell
& 'D:\yu-ai-code-mother\deploy\cloud-monitoring\start-monitoring-tunnel.ps1'
```

Expected: password authentication succeeds, the window stays open without `remote port forwarding failed` or `Address already in use`.

- [ ] **Step 3: Verify all local forward ports from a second PowerShell window**

```powershell
@(13306, 16379, 16333, 13000, 14318, 19090) | ForEach-Object {
  "$_=" + (Test-NetConnection 127.0.0.1 -Port $_ -InformationLevel Quiet)
}
```

Expected: every line ends in `True`.

- [ ] **Step 4: Add the Java OTLP environment variable in IDEA**

In `Run/Debug Configurations -> Spring Boot -> RainN0CodingApplication -> Environment variables`, preserve all existing MySQL and Redis variables and add:

```text
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:14318/v1/traces
```

Stop and restart the Java application. Expected startup markers:

```text
Started RainN0CodingApplication
Tomcat started on port 8123
```

- [ ] **Step 5: Add the Python OTLP variables in PyCharm**

In `Run/Debug Configurations -> Python -> Python Agent Cloud -> Environment variables`, preserve Qdrant and Redis variables and add:

```text
OTEL_EXPORTER_ENABLED=true
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:14318/v1/traces
```

Stop and restart Python. Expected startup marker:

```text
Application startup complete.
```

- [ ] **Step 6: Verify local metrics endpoints and Prometheus Targets**

```powershell
curl.exe -fsS http://127.0.0.1:8123/api/actuator/prometheus > $null
curl.exe -fsS http://127.0.0.1:8000/metrics > $null
$targets = Invoke-RestMethod http://127.0.0.1:19090/api/v1/targets
$targets.data.activeTargets | Select-Object scrapePool,health,lastError
```

Expected: `RainN0Coding-java` and `RainN0Coding-python` both have `health` equal to `up` and empty `lastError`.

### Task 9: Complete end-to-end metrics, Trace, persistence, and resource acceptance

**Files:**
- Runtime verification only

- [ ] **Step 1: Verify Grafana provisioning**

Open `http://127.0.0.1:13000`, sign in as `admin` using the secret stored in cloud `.env`, then verify:

- Connections -> Data sources shows Prometheus and Tempo without connection errors.
- Dashboards -> RainN0Coding -> RainN0Coding Overview exists.
- Java / Python Targets shows both targets as `1`.

- [ ] **Step 2: Trigger one real code-generation request**

Use the application UI and submit:

```text
创建一个简单的待办事项管理页面，支持新增、完成和删除任务。
```

Wait until Reviewer and Builder finish. Record the `trace` value shown in Java or Python logs; do not record API keys or passwords.

- [ ] **Step 3: Verify the cross-service Trace in Grafana Explore**

Select Tempo and execute:

```traceql
{ resource.service.name = "RainN0Coding-backend" }
```

Then execute:

```traceql
{ resource.service.name = "python-agent" }
```

Expected: the same trace ID contains Java entry/WebClient spans and Python server, `workflow.stream`, Agent, and LLM spans. The trace ID matches the application logs for the test request.

- [ ] **Step 4: Capture pre-restart persistence evidence**

In the Tencent terminal:

```bash
cd /home/ubuntu/rainn0coding-cloud/monitoring
docker volume ls --format '{{.Name}}' | grep '^rainn0coding-monitoring_'
curl -fsS 'http://127.0.0.1:9090/api/v1/query?query=up' > /tmp/prometheus-up-before.json
```

Expected: `grafana_data`, `prometheus_data`, and `tempo_data` volumes exist; the Prometheus query succeeds.

- [ ] **Step 5: Recreate monitoring containers without deleting volumes**

```bash
docker compose -f compose.monitoring.yml down
docker volume ls --format '{{.Name}}' | grep '^rainn0coding-monitoring_'
docker compose -f compose.monitoring.yml up -d
```

Expected: all three named volumes still exist and all four containers return to `Up`.

- [ ] **Step 6: Verify persistence and data-service isolation after recreation**

```bash
curl -fsS http://127.0.0.1:9090/-/ready
curl -fsS http://127.0.0.1:3000/api/health
cd /home/ubuntu/rainn0coding-cloud
docker compose ps
```

Open Grafana again and verify the account, data sources, dashboard, earlier Prometheus samples, and the recent Tempo trace still exist. Expected: MySQL, Redis, and Qdrant were not recreated and remain healthy.

- [ ] **Step 7: Verify resource and security acceptance**

```bash
free -h
swapon --show
df -h /
docker inspect \
  -f '{{.Name}} OOMKilled={{.State.OOMKilled}} RestartCount={{.RestartCount}} Status={{.State.Status}}' \
  rainn0coding-prometheus rainn0coding-tempo rainn0coding-otel-collector rainn0coding-grafana
docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}'
ss -lnt | grep -E ':(3000|9090|3200|4317|4318)'
```

Expected:

- available memory is at least 512 MB;
- all `OOMKilled=false`, restart counts are zero after the controlled recreation, and statuses are running;
- Swap usage is not continuously increasing during a five-minute idle observation;
- disk usage remains below 70%;
- no monitoring port is bound to a public host address.

- [ ] **Step 8: Record the final operational handoff**

Final handoff must include:

```text
Cloud start:  cd ~/rainn0coding-cloud/monitoring && docker compose -f compose.monitoring.yml start
Tunnel start: D:\yu-ai-code-mother\deploy\cloud-monitoring\start-monitoring-tunnel.ps1
Grafana:      http://127.0.0.1:13000
Prometheus:   http://127.0.0.1:19090
Cloud stop:   docker compose -f compose.monitoring.yml stop
```

Do not include the Grafana password in the handoff.
