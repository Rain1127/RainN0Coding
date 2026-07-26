# 项目启动清单

本文档用于在本地启动 `yu-ai-code-mother` 项目。推荐按顺序启动：基础设施 -> Python Agent -> Java 后端 -> Vue 前端。

## 1. 服务总览

| 服务 | 作用 | 默认端口 / 地址 | 是否必需 |
| --- | --- | --- | --- |
| MySQL | 业务数据库，存储用户、应用、聊天记录等 | `localhost:3306` | 必需 |
| Redis | 登录态、缓存、限流 | `localhost:6379` | 必需 |
| Milvus | RAG 向量检索 | `localhost:19530` 或 lite 本地文件 | AI 生成建议启用 |
| Python FastAPI Agent | LangGraph 多 Agent AI 生成引擎 | `http://localhost:8000` | 必需 |
| Java Spring Boot Backend | 业务网关、认证、CRUD、SSE 代理 | `http://localhost:8123/api` | 必需 |
| Vue Frontend | Web 前端界面 | 通常为 `http://localhost:5173` | 必需 |
| Prometheus | 监控 Spring Boot Actuator 指标 | 按本地配置 | 可选 |

## 2. 启动前检查

- JDK 使用 `D:/Program Files/Java/jdk-23`，Lombok 注解处理需要 JDK 23+。
- MySQL 已启动，并存在数据库 `rainn0coding`。
- Redis 已启动。
- Python 虚拟环境存在：`python-agent/.venv/Scripts/python.exe`。
- `python-agent/.env` 已配置模型 API Key、Milvus、Redis 等参数。
- 前端依赖已安装，或准备执行 `npm install`。
- 如果使用 Milvus standalone，Docker Desktop 与 WSL2 需要正常运行。

## 3. 启动 MySQL

确认 MySQL 服务已启动，并创建数据库：

```sql
CREATE DATABASE IF NOT EXISTS rainn0coding;
```

如果项目需要初始化表结构，请执行项目提供的 SQL 初始化脚本。

## 4. 启动 Redis

启动 Redis 后，确认 Java 后端能够连接到配置中的 Redis 地址。

Redis 用于：

- Sa-Token 登录态
- 缓存
- 接口限流
- Python Agent 记忆摘要，视配置而定

## 5. 启动 Milvus

如果使用 Docker standalone 模式：

```bash
cd milvus
docker compose up -d
```

首次启动或重建 Milvus 后，需要写入 RAG 种子数据：

```powershell
cd python-agent
$env:PYTHONPATH='.'
& '.\.venv\Scripts\python.exe' rag/seed_milvus.py
```

如果使用 `MILVUS_MODE=lite`，请确认 `.env` 中 Milvus lite 路径配置正确。

## 6. 启动 Python Agent

进入 Python Agent 目录：

```bash
cd python-agent
```

推荐使用虚拟环境 Python 直接启动，避免 Windows 下 `uv` 导致 torch DLL 兼容问题：

```powershell
$env:PYTHONPATH='D:/yu-ai-code-mother/python-agent'
& '.\.venv\Scripts\python.exe' server/main.py
```

也可以使用 uvicorn：

```bash
uv run uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload
```

健康检查：

```bash
curl http://localhost:8000/api/health
```

预期服务地址：

```text
http://localhost:8000
```

## 7. 启动 Java 后端

在项目根目录执行：

```powershell
$env:JAVA_HOME='D:/Program Files/Java/jdk-23'
$env:Path="$env:JAVA_HOME/bin;$env:Path"
mvn compile -DskipTests
```

启动 Spring Boot：

```powershell
$env:JAVA_HOME='D:/Program Files/Java/jdk-23'
$env:Path="$env:JAVA_HOME/bin;$env:Path"
mvn spring-boot:run
```

也可以直接使用 IDE 启动主应用类。

预期服务地址：

```text
http://localhost:8123/api
```

启动前请确认：

- MySQL 正常连接
- Redis 正常连接
- Python Agent `http://localhost:8000` 正常

## 8. 启动 Vue 前端

进入前端目录：

```bash
cd RainN0Coding-frontend
```

首次启动先安装依赖：

```bash
npm install
```

启动开发服务器：

```bash
npm run dev
```

预期访问地址通常为：

```text
http://localhost:5173
```

如果端口被占用，以 Vite 控制台实际输出为准。

## 9. 可选：启动 Prometheus

如果需要采集 Spring Boot Actuator 指标：

```bash
prometheus --config.file=prometheus.yml
```

Prometheus 默认会根据 `prometheus.yml` 抓取：

```text
http://localhost:8123/api/actuator/prometheus
```

## 10. 推荐验证顺序

1. 检查 MySQL、Redis 已运行。
2. 检查 Milvus 已运行，或 Milvus lite 配置正确。
3. 执行 Python 健康检查：

   ```bash
   curl http://localhost:8000/api/health
   ```

4. 启动 Java 后端，确认控制台无数据库、Redis、Python Agent 连接错误。
5. 打开前端页面。
6. 测试注册 / 登录。
7. 创建应用并发送代码生成请求。
8. 确认 SSE 流式返回正常。
9. 确认生成代码可以保存、预览、下载。

## 11. 常用测试命令

Java 测试：

```powershell
$env:JAVA_HOME='D:/Program Files/Java/jdk-23'
$env:Path="$env:JAVA_HOME/bin;$env:Path"
mvn test
```

运行单个 Java 测试类：

```powershell
$env:JAVA_HOME='D:/Program Files/Java/jdk-23'
$env:Path="$env:JAVA_HOME/bin;$env:Path"
mvn test -Dtest=AiCodeGeneratorFacadeTest
```

Python 测试：

```powershell
cd python-agent
$env:PYTHONPATH='.'
& '.\.venv\Scripts\python.exe' -m pytest tests/ -v
```

前端构建：

```bash
cd RainN0Coding-frontend
npm run build
```

## 12. 最小启动顺序

```text
MySQL -> Redis -> Milvus -> Python Agent -> Java Backend -> Vue Frontend
```
