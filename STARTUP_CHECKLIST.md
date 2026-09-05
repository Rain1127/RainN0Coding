# 项目本地启动清单（无 Docker Compose）

本地启动顺序：

```text
MySQL -> PostgreSQL -> Redis -> LiteLLM -> Milvus Lite -> Python -> Java -> Vue -> Prometheus/Grafana
```

## 1. 服务边界

| 服务 | 作用 | 默认地址 |
| --- | --- | --- |
| MySQL | 用户、应用、聊天记录等业务数据 | `127.0.0.1:3306` |
| PostgreSQL | LiteLLM 虚拟密钥、预算和消费记录 | `127.0.0.1:5432` |
| Redis | Java 会话/限流与 LiteLLM 鉴权缓存（不同命名空间） | `127.0.0.1:6379` |
| LiteLLM | 模型选择、重试、故障转移、配额、消费与指标 | `http://127.0.0.1:4000` |
| Milvus Lite | 本地 RAG 向量检索文件 | Python 进程内 |
| Python FastAPI | LangGraph 工作流与 SSE | `http://127.0.0.1:8000` |
| Java Spring Boot | 业务网关、认证、CRUD、SSE 代理 | `http://127.0.0.1:8123/api` |
| Vue | 开发前端 | `http://127.0.0.1:5173` |

DeepSeek、智谱密钥只放在 `infrastructure/litellm/.env`。`python-agent/.env` 只保存 LiteLLM 虚拟密钥，不能再保存厂商密钥。

## 2. 启动 MySQL

使用本机 MySQL 服务，确认端口可用并创建业务数据库：

```sql
CREATE DATABASE IF NOT EXISTS rainn0coding;
```

按项目 SQL 初始化表结构。Java 的 `MYSQL_URL`、`MYSQL_USERNAME`、`MYSQL_PASSWORD` 指向该数据库。

## 3. 启动 PostgreSQL

使用本机 PostgreSQL 服务，在 `psql` 交互会话中创建 LiteLLM 专用角色和数据库：

```text
psql -U postgres
CREATE ROLE litellm LOGIN;
\password litellm
CREATE DATABASE litellm_gateway OWNER litellm;
\q
```

`\password` 会交互读取密码，不会把明文密码写进命令历史。

## 4. 启动 Redis

启动本机 Redis，并确认密码与以下两处一致：

- Java 使用 Redis DB 0 处理登录态、缓存和限流。
- LiteLLM 使用 `litellm` 命名空间缓存鉴权结果，不启用响应语义缓存。

## 5. 配置并启动 LiteLLM

首次运行：

```powershell
Copy-Item infrastructure/litellm/.env.example infrastructure/litellm/.env
```

编辑 `infrastructure/litellm/.env`，填写随机 `LITELLM_MASTER_KEY`、PostgreSQL `DATABASE_URL`、Redis 密码、DeepSeek 密钥和智谱密钥。不要提交该文件。

在单独终端启动网关：

```powershell
& '.\infrastructure\litellm\start-local.ps1'
```

首次启动会在 `infrastructure/litellm/.venv` 安装固定版本的 LiteLLM，不会修改 `python-agent` 的依赖。

创建仅允许三个业务模型的 Python 服务虚拟密钥：

```powershell
$env:LITELLM_MASTER_KEY = Read-Host 'LiteLLM master key'
& '.\infrastructure\litellm\provision-agent-key.ps1'
```

将脚本最后输出的虚拟密钥复制到 `python-agent/.env`：

```dotenv
LITELLM_BASE_URL=http://127.0.0.1:4000/v1
LITELLM_HEALTH_URL=http://127.0.0.1:4000/health/liveliness
LITELLM_API_KEY=粘贴刚生成的虚拟密钥
LLM_REASONING_MODEL=code-reasoning
LLM_STRUCTURED_MODEL=code-structured
LLM_LIGHTWEIGHT_MODEL=code-lightweight
```

验证网关边界：

```powershell
$env:LITELLM_API_KEY = Read-Host 'Python agent virtual key'
& '.\infrastructure\litellm\health-check.ps1'
```

## 6. 启用本地向量检索

本地不启动 Compose。使用 `python-agent/.env` 中的 Milvus Lite：

```dotenv
VECTOR_DB_PROVIDER=milvus
MILVUS_MODE=lite
```

首次运行后写入种子数据：

```powershell
Set-Location python-agent
$env:PYTHONPATH='.'
& '.\.venv\Scripts\python.exe' rag/seed_milvus.py
```

## 7. 启动 Python Agent

```powershell
Set-Location python-agent
$env:PYTHONPATH='.'
& '.\.venv\Scripts\python.exe' server/main.py
```

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

验收：`status=ok`，`llm_gateway.configured=true`，`llm_gateway.reachable=true`，并列出三个 `code-*` 模型。

## 8. 启动 Java 后端

```powershell
$env:JAVA_HOME='D:/Program Files/Java/jdk-23'
$env:Path="$env:JAVA_HOME/bin;$env:Path"
mvn spring-boot:run
```

确认 MySQL、Redis 正常连接，并且 `PYTHON_AI_BASE_URL` 指向 `http://127.0.0.1:8000`。

## 9. 启动 Vue 前端

```powershell
Set-Location RainN0Coding-frontend
npm install
npm run dev
```

打开 Vite 输出的本地地址，完成注册/登录、创建应用和代码生成。

## 10. 启动 Prometheus 与 Grafana

Prometheus 使用 master key 抓取受保护的 LiteLLM 指标。先在仓库根目录创建已被 `.gitignore` 排除的 token 文件，文件中只能包含密钥本身，不能带 `Bearer ` 前缀：

```powershell
New-Item -ItemType Directory -Path secrets -Force | Out-Null
$env:LITELLM_MASTER_KEY | Set-Content -LiteralPath secrets/litellm_metrics_token -NoNewline
```

```powershell
prometheus --config.file=prometheus.yml
```

Prometheus 必须同时抓取 Java、Python 和 LiteLLM；Grafana 导入仓库中的 provisioning 与 dashboards 配置。

## 11. 完整验收

1. `health-check.ps1` 全部显示 `[PASS]`。
2. FastAPI `/api/health` 显示网关已配置且可达。
3. 前端发起一次代码生成，Java 继续透明代理 SSE。
4. LiteLLM 日志显示 `code-*` 别名，Python 日志不出现厂商 URL。
5. PostgreSQL 中的消费记录在 LiteLLM 重启后仍存在。
6. Prometheus 能查询 LiteLLM 请求、失败、延迟、token、费用和 fallback 指标。
7. 使用低预算测试虚拟密钥触发预算拒绝，不影响 Python 服务正式虚拟密钥。

## 12. 回归命令

```powershell
Set-Location python-agent
$env:PYTHONPATH='.'
& '.\.venv\Scripts\python.exe' -m pytest tests -v
```

```powershell
$env:JAVA_HOME='D:/Program Files/Java/jdk-23'
$env:Path="$env:JAVA_HOME/bin;$env:Path"
mvn test
```

```powershell
Set-Location RainN0Coding-frontend
npm test
npm run build
```

## 13. 本次自动化验收记录（2026-09-05）

- LiteLLM 配置、请求上下文、路由边界、健康检查和监控契约：最新定向回归 `49 passed`。
- LiteLLM 隔离回退契约：主模型返回 500 后重试一次并切换备用模型；双模型失败时返回非 2xx，`2 passed`。
- Java：`113 tests`，`0 failures`，`0 errors`。
- Vue：`266 passed`，`vue-tsc -b` 通过，Vite 生产构建通过（产物写入系统临时目录，未覆盖仓库静态资源）。
- Python 全量：`202 passed, 7 skipped, 1 failed`。唯一失败为本机 `127.0.0.1:6333` 未运行 Qdrant；另有 `onnxruntime/fastembed` 的 Windows 原生访问冲突诊断，但 pytest 仍完成并给出上述结果。
- 生产 Python 代码未检出 DeepSeek/智谱 API Key 名称或厂商直连 URL；密钥扫描命中项均为 `.env.example` 占位符或 RAG 示例文本，不是真实凭据。

本机真实链路验收仍待完成：当前仅 MySQL 3306 在监听，PostgreSQL 5432、Redis 6379、LiteLLM 4000、Python 8000、Java 8123 和 Prometheus 9090 均未启动，且 `infrastructure/litellm/.env` 尚未创建。配置好本地服务与真实厂商密钥后，按第 1～11 节执行即可完成最终验收。
