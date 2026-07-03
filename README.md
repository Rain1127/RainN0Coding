# RainN0Coding

AI-powered multi-agent code generation platform built around a Spring Boot gateway and a FastAPI/LangGraph agent engine.

## Overview

RainN0Coding turns a user prompt into runnable project code through a multi-stage generation pipeline. The Java service handles auth, CRUD, rate limiting, and SSE proxying, while the Python service runs the agent workflow, retrieval pipeline, and code generation logic.

Request flow:

`Client -> Spring Boot (/api) -> FastAPI SSE -> LangGraph workflow -> Spring SSE proxy -> Client`

## Repository Structure

- `src/`: Spring Boot backend and API gateway
- `python-agent/`: FastAPI service, LangGraph agents, guardrails, and RAG pipeline
- `milvus/`: local vector database setup
- `grafana/`, `prometheus.yml`, `otel-collector-config.yml`: observability stack
- `sql/`, `mysql-init.sql`: database schema and bootstrap SQL
- `docs/`: selected reference and deployment documentation

## Tech Stack

- Java 21 + Spring Boot 3
- Python 3.12 + FastAPI + LangGraph
- MySQL + Redis
- Milvus vector search
- Prometheus + Grafana + OpenTelemetry

## Quick Start

### 1. Java backend

```powershell
$env:JAVA_HOME="D:/Program Files/Java/jdk-23"
mvn compile -DskipTests
mvn test
```

### 2. Python agent

```powershell
cd python-agent
$env:PYTHONPATH="."
.venv/Scripts/python.exe server/main.py
```

### 3. Infrastructure

```powershell
cd milvus
docker compose up -d
```

## Configuration

- Main Java config: `src/main/resources/application.yml`
- Local Java overrides: `src/main/resources/application-local.yml`
- Python agent env file: `python-agent/.env`
- Example Python env file: `python-agent/.env.example`

Keep secrets in ignored local files only. Do not commit real API keys, tokens, or passwords.

## Documentation

- [API文档](docs/API文档.md)
- [API接口文档](docs/API接口文档.md)
- [Milvus Guide](docs/MILVUS_GUIDE.md)
- [Docker Milvus Guide](docs/DOCKER_MILVUS_GUIDE.md)
- [Technical Reference](docs/TECHNICAL_REFERENCE.md)
- [Tencent Cloud Deployment Runbook](docs/tencent-cloud-deployment-runbook.md)

## Notes

- This repository currently focuses on the backend and agent services.
- Frontend code, if used in your local setup, can live in a separate companion repository or workspace.
