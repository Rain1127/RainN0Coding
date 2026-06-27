# Grafana + Prometheus 极速使用指南

> 适用项目：yu-ai-code-mother  
> 更新日期：2026-06-23

---

## 1. 架构一图流

```
┌─────────────────────────────────────────────────────────┐
│                     Grafana :3000                        │
│                  (Docker 容器运行)                         │
│               admin / admin 登录                           │
│         大盘: AI Workflow Monitoring                       │
└──────────────────────┬──────────────────────────────────┘
                       │ 查询
                       ▼
┌─────────────────────────────────────────────────────────┐
│                   Prometheus :9090                        │
│               (Windows 宿主机直接运行)                      │
│         prometheus.yml 在项目根目录                        │
│         抓取间隔: 10s / 保留 15 天                         │
└──────┬──────────────────────────┬───────────────────────┘
       │ 抓取 /metrics             │ 抓取 /api/actuator/prometheus
       ▼                           ▼
┌──────────────┐          ┌──────────────────┐
│ Python :8000 │          │  Java Spring :8123│
│ 8 自定义指标   │          │ 4 Micrometer 指标 │
│ + HTTP 自动   │          │ + JVM 自动指标     │
└──────────────┘          └──────────────────┘
```

---

## 2. 一键启动

### 启动顺序

```bash
# 1. Python FastAPI（先启动，Prometheus 需要抓它）
cd python-agent
PYTHONPATH=. .venv/Scripts/python.exe server/main.py
# → http://localhost:8000
# → http://localhost:8000/metrics （Prometheus 指标）
# → http://localhost:8000/api/health （健康检查）

# 2. Java Spring Boot（IDEA 或 mvn）
# → http://localhost:8123/api/actuator/prometheus

# 3. Prometheus（在项目根目录）
prometheus --config.file=prometheus.yml
# → http://localhost:9090
# → http://localhost:9090/targets （查看抓取状态）

# 4. Grafana（Docker）
docker compose -f docker-compose.monitoring.yml up -d
# → http://localhost:3000
#   用户名: admin  密码: admin123
```

### 停止

```bash
docker compose -f docker-compose.monitoring.yml down   # 停 Grafana
# Ctrl+C                                                # 停 Python / Prometheus
```

---

## 3. 大盘速览

### 大盘 1: AI Workflow Monitoring（Python 工作流）

访问 `http://localhost:3000` → Dashboards → **AI Workflow Monitoring**

| 区域 | 面板 | 看什么 |
|------|------|--------|
| **概览** | 请求吞吐、状态分布 Pie、活跃请求数、今日总量 | 整体流量和健康度 |
| **阶段性能** | P50/P95 耗时曲线、各阶段平均耗时 Bar | 哪个 Agent 最慢？ |
| **LLM 调用** | 每阶段调用次数、成功率、按模型分布 | 哪个阶段消耗最多 API？ |
| **重试分析** | 重试次数分布、平均重试、产出文件数 | 代码质量趋势 |
| **RAG 缓存** | 命中率、命中/未命中趋势 | 检索是否有效？ |
| **熔断器** | 各模型状态 Timeline | 模型是否被熔断？ |

### 大盘 2: AI Model Monitoring（Java 侧 LLM 指标）

访问 `http://localhost:3000` → Dashboards → **AI Model Monitoring**

| 区域 | 面板 | 看什么 |
|------|------|--------|
| 概览 | 成功请求数、Token 总量、平均响应时间 | LLM 调用总览 |
| Token 分析 | 累计趋势、类型分布 | 成本估算 |
| 模型分析 | 请求趋势、平均响应时间 | 模型性能对比 |
| 排行榜 | Top 应用、Top 用户 | 使用量排名 |
| 错误分析 | 错误率趋势、错误类型分布 | 排查故障 |

---

## 4. Python 侧完整指标清单

### 业务指标（`monitoring.py` 定义）

| 指标名 | 类型 | 标签 | 含义 |
|--------|------|------|------|
| `ai_code_gen_requests_total` | Counter | user_id, app_id, code_gen_type, status | 请求总数 |
| `ai_code_gen_active_requests` | Gauge | — | 正在执行的请求 |
| `ai_code_gen_phase_duration_seconds` | Histogram | phase, code_gen_type | 阶段耗时 |
| `ai_code_gen_llm_calls_total` | Counter | model_name, phase, status | LLM 调用次数 |
| `ai_code_gen_retries` | Histogram | code_gen_type | 重试次数 |
| `ai_code_gen_files_generated` | Histogram | code_gen_type | 产出文件数 |
| `ai_rag_cache_hit_total` | Counter | status (hit/miss) | 缓存命中 |
| `ai_circuit_breaker_state` | Gauge | model_name | 熔断器 (0=关/1=开/2=半开) |

### HTTP 指标（`prometheus_fastapi_instrumentator` 自动提供）

| 指标名 | 含义 |
|--------|------|
| `http_requests_total` | HTTP 请求总数 |
| `http_request_duration_seconds` | 请求耗时 |
| `http_request_size_bytes` | 请求体大小 |

### phase 标签可选值

```
intent → pm → architect → coder → reviewer → builder
mode_detect, clarify, fork_coder_and_images
```

---

## 5. 常用 PromQL 查询

直接在 Grafana Explore 或 Prometheus Web UI (`:9090`) 中执行：

```promql
# 过去 5 分钟每秒请求数
rate(ai_code_gen_requests_total[5m])

# 成功率
sum(ai_code_gen_requests_total{status="success"}) / sum(ai_code_gen_requests_total)

# Coder 阶段 P95 耗时
histogram_quantile(0.95, sum(rate(ai_code_gen_phase_duration_seconds_bucket{phase="coder"}[5m])) by (le))

# LLM 调用成功率
sum(ai_code_gen_llm_calls_total{status="success"}) / sum(ai_code_gen_llm_calls_total)

# RAG 缓存命中率
sum(ai_rag_cache_hit_total{status="hit"}) / sum(ai_rag_cache_hit_total)

# 哪个模型被熔断了？
ai_circuit_breaker_state > 0

# 过去 1 小时请求 Top 用户
topk(5, sum(increase(ai_code_gen_requests_total[1h])) by (user_id))

# Java 侧：Token 消耗速率
rate(ai_model_tokens_total[5m])
```

---

## 6. 触发一次请求收集数据

Grafana 大盘初始为空是正常的——还没请求过。触发一次生成即可看到数据：

```bash
curl -X POST http://localhost:8000/api/generate-code \
  -H "Content-Type: application/json" \
  -d '{"userId":"test","appId":"demo","prompt":"做一个登录页面"}'
```

然后刷新 Grafana 大盘（右上角刷新按钮或等 10s 自动刷新）。

---

## 7. 配置热更新

### Prometheus 配置变更

```bash
# 方式 1：热重载（推荐）
curl -X POST http://localhost:9090/-/reload

# 方式 2：重启
# Ctrl+C 停掉，重新执行 prometheus --config.file=prometheus.yml
```

### Grafana 大盘变更

修改 `grafana/dashboards/*.json` 后，Grafana 每 10 秒自动检测并加载，无需重启。

---

## 8. 故障排查

| 问题 | 检查 |
|------|------|
| Grafana 大盘无数据 | 1. Prometheus Targets 是否 UP？(`:9090/targets`)  2. Python `/metrics` 是否可访问？(`curl localhost:8000/metrics`)  3. 是否触发过代码生成请求？ |
| Python `/metrics` 404 | `pip install prometheus-client prometheus-fastapi-instrumentator` |
| Prometheus 连不上 Python | 检查 `prometheus.yml` 中 Python target 是 `localhost:8000`，路径是 `/metrics` |
| Grafana 连不上 Prometheus | Docker 内用 `host.docker.internal:9090`，检查 `grafana/datasources/prometheus.yml` |
| 指标全是 0 | 触发一次 `POST /api/generate-code` 请求即可 |
| 大盘面板报错 | 检查指标名是否拼写正确，Prometheus 中查询 `{__name__=~"ai_code_gen.*"}` 确认指标存在 |

---

## 9. 文件索引

| 文件 | 作用 |
|------|------|
| `prometheus.yml` | Prometheus 抓取配置（Java + Python + 自监控） |
| `docker-compose.monitoring.yml` | Grafana Docker 部署 |
| `python-agent/monitoring.py` | Python 指标定义 + FastAPI 埋点 |
| `python-agent/server/main.py` | FastAPI 集成 `setup_monitoring(app)` |
| `grafana/datasources/prometheus.yml` | Grafana 数据源自动配置 |
| `grafana/dashboards/ai-workflow-overview.json` | Python 工作流大盘 |
| `grafana/ai_model_grafana_config.json` | Java AI 模型大盘（已有） |

---

## 10. 进阶：添加新指标

在 `python-agent/monitoring.py` 中三步完成：

```python
# 1. 定义指标
my_new_metric = Counter("ai_my_new_metric", "描述", ["label1"])

# 2. 在业务代码中记录
from monitoring import my_new_metric
my_new_metric.labels(label1="value").inc()

# 3. 在 Grafana 大盘 JSON 中添加面板
# 编辑 ai-workflow-overview.json，添加新 panel
```

无需重启 Prometheus——新指标会随 `/metrics` 端点自动暴露。
