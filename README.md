# RainN0Coding

RainN0Coding 是一个基于多智能体协作的 AI 代码生成平台，整体由 Spring Boot 网关服务与 FastAPI/LangGraph 智能体引擎组成。

## 项目简介

项目的核心目标是将用户输入的需求描述，经过多阶段智能体工作流处理，最终生成可运行的项目代码。

- Java 服务负责鉴权、CRUD、限流、请求编排和 SSE 代理
- Python 服务负责智能体编排、RAG 检索、代码生成与守护逻辑

请求链路如下：

`客户端 -> Spring Boot (/api) -> FastAPI SSE -> LangGraph 工作流 -> Spring SSE 代理 -> 客户端`

## 仓库结构

- `src/`：Spring Boot 后端与 API 网关
- `python-agent/`：FastAPI 服务、LangGraph 智能体、Guardrails 与 RAG 管线
- `milvus/`：本地向量数据库相关配置
- `grafana/`、`prometheus.yml`、`otel-collector-config.yml`：监控与观测配置
- `sql/`、`mysql-init.sql`：数据库建表与初始化脚本
- `docs/`：保留的参考文档与部署文档

## 技术栈

- Java 21 + Spring Boot 3
- Python 3.12 + FastAPI + LangGraph
- MySQL + Redis
- Milvus 向量检索
- Prometheus + Grafana + OpenTelemetry

## 快速开始

### 1. 启动 Java 后端

```powershell
$env:JAVA_HOME="D:/Program Files/Java/jdk-23"
mvn compile -DskipTests
mvn test
```

### 2. 启动 Python Agent

```powershell
cd python-agent
$env:PYTHONPATH="."
.venv/Scripts/python.exe server/main.py
```

### 3. 启动基础设施

```powershell
cd milvus
docker compose up -d
```

## 配置说明

- Java 主配置：`src/main/resources/application.yml`
- Java 本地覆盖配置：`src/main/resources/application-local.yml`
- Python Agent 本地环境变量：`python-agent/.env`
- Python Agent 示例环境变量：`python-agent/.env.example`

请仅在本地忽略文件中保存真实密钥、Token 和密码，不要提交任何真实敏感信息。

## 文档入口

- [API文档](docs/API文档.md)
- [API接口文档](docs/API接口文档.md)
- [Milvus Guide](docs/MILVUS_GUIDE.md)
- [Docker Milvus Guide](docs/DOCKER_MILVUS_GUIDE.md)
- [Technical Reference](docs/TECHNICAL_REFERENCE.md)
- [Tencent Cloud Deployment Runbook](docs/tencent-cloud-deployment-runbook.md)

## 说明

- 当前仓库主要聚焦后端与智能体服务
- 如果你的本地环境包含前端工程，建议以前端独立仓库或独立工作区的方式维护
