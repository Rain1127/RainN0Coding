# yu-ai-code-mother

AI-powered code generation platform with a Java gateway and a Python multi-agent engine.

## Architecture

- `src/`: Spring Boot 3 backend, auth, CRUD, rate limiting, SSE proxy
- `python-agent/`: FastAPI + LangGraph 8-agent workflow, RAG, Milvus integration
- `milvus/`, `grafana/`, `prometheus.yml`, `otel-collector-config.yml`: local infrastructure and observability
- `docs/`: design notes, runbooks, and implementation records

Request flow:

`Frontend -> Spring Boot (/api) -> Python FastAPI SSE -> LangGraph workflow -> Spring SSE proxy -> Client`

## Quick Start

### Java backend

```powershell
$env:JAVA_HOME="D:/Program Files/Java/jdk-23"
mvn compile -DskipTests
mvn test
```

### Python agent

```powershell
cd python-agent
$env:PYTHONPATH="D:/yu-ai-code-mother/python-agent"
.venv/Scripts/python.exe server/main.py
```

### Frontend

Frontend code is expected in `yu-ai-code-mother-frontend/` when working in the full local setup.

```powershell
cd yu-ai-code-mother-frontend
npm run dev
```

## Environment Setup

- Java runtime config uses `src/main/resources/application.yml`
- Local-only secrets belong in ignored files such as `src/main/resources/application-local.yml`
- Python agent secrets belong in `python-agent/.env`
- Start from `python-agent/.env.example` and replace placeholders locally

## Repository Notes

- This repository intentionally keeps runtime secrets out of tracked files
- Operational notes and design docs are under `docs/`
- If you plan to open-source this repo, consider moving temporary planning artifacts out of the repository root
