# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI-powered code generation platform. User describes an app → 8-Agent collaborative AI generates complete runnable code with preview.

Three-tier architecture:
1. **Vue 3 frontend** (Vite + Ant Design Vue + Pinia)
2. **Java Spring Boot 3.5.9** (port 8123, `/api`) — business gateway: auth, rate-limiting, CRUD, SSE proxy
3. **Python FastAPI** (port 8000) — AI engine: LangGraph multi-agent workflow, RAG pipeline, Milvus vector search

Key data flow: `User prompt → Java Controller → PythonAiClient (WebClient) → Python FastAPI SSE → 8-Agent LangGraph workflow → SSE stream back → Java proxies to frontend`

## Build & Run Commands

### Java Backend (Spring Boot 3.5.9 / Java 21)

```bash
# Compile (use JDK 23 for lombok compatibility)
JAVA_HOME="D:/Program Files/Java/jdk-23" mvn compile -DskipTests

# Run tests
JAVA_HOME="D:/Program Files/Java/jdk-23" mvn test

# Run single test class
JAVA_HOME="D:/Program Files/Java/jdk-23" mvn test -Dtest=AiCodeGeneratorFacadeTest

# Start the app (from IDE or mvn spring-boot:run, needs MySQL + Redis running)

# Generate MyBatis code (custom generator)
mvn exec:java -Dexec.mainClass="com.yupi.yuaicodemother.generator.MyBatisCodeGenerator"
```

### Python Agent (FastAPI + LangGraph)

```bash
cd python-agent

# Start the API server (venv python avoids uv torch DLL issues on Windows)
PYTHONPATH=D:/yu-ai-code-mother/python-agent .venv/Scripts/python.exe server/main.py

# Or with uvicorn directly
uv run uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload

# Health check
curl http://localhost:8000/api/health

# Run tests
PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/ -v

# Seed Milvus data (must run once after fresh Milvus setup)
PYTHONPATH=. .venv/Scripts/python.exe rag/seed_milvus.py
```

### Frontend (Vue 3 + Vite)

```bash
cd yu-ai-code-mother-frontend
npm run dev      # Development server
npm run build    # vue-tsc type-check + vite build
npm run preview  # Preview production build
```

### Docker / Infrastructure

```bash
# Milvus standalone (requires Docker with WSL2 on Windows)
cd milvus && docker compose up -d

# Prometheus (scrapes Spring Boot Actuator at localhost:8123/api/actuator/prometheus)
prometheus --config.file=prometheus.yml
```

## Architecture

### Java Package Structure (`src/main/java/com/yupi/yuaicodemother/`)

| Package | Role |
|---------|------|
| `controller/` | REST endpoints: `AppController`, `UserController`, `ChatHistoryController`, `HealthController` |
| `core/` | Code generation pipeline: `AiCodeGeneratorFacade` (delegates to Python), `CodeParser`, `CodeFileSaver`, `python/PythonAiClient` (WebClient SSE proxy) |
| `ai/` | **Deprecated** — old LangChain4j direct LLM calls, being phased out in favor of Python |
| `service/` + `service/impl/` | Business services: `UserService`, `AppService`, `ChatHistoryService`, `ScreenshotService`, `ProjectDownloadService` |
| `mapper/` | MyBatis-Flex mapper interfaces (User, App, ChatHistory, AppVersion, IntentConfig) |
| `model/entity/`, `dto/`, `vo/`, `enums/` | Domain models |
| `config/` | Spring configs: CORS, CosClient, Redis, Sa-Token, Json, plus deprecated AI configs |
| `ratelimiter/` | `@RateLimit` annotation + AOP aspect backed by Redisson |
| `annotation/` + `aop/` | `@AuthCheck` annotation + `AuthInterceptor` |
| `exception/` | `BusinessException`, `GlobalExceptionHandler` |
| `monitor/` | AI model metrics collection (Micrometer) |
| `utils/` | `WebScreenshotUtils` (Selenium), `SpringContextUtil`, `CacheKeyUtils` |

### Python Agent Structure (`python-agent/`)

| Module | Files | Description |
|--------|-------|-------------|
| **Agents** | `intent_agent.py`, `pm_agent.py`, `architect_agent.py`, `coder_agent.py`, `reviewer_agent.py`, `image_collector_agent.py`, `builder_agent.py`, `supervisor_agent.py` | 8 Agents, each is a LangGraph node: `(CodeGenState) → CodeGenState` |
| **Workflow** | `code_gen_workflow.py` | Assembles LangGraph StateGraph: `START → Intent → PM → Architect → Fork(Coder + Images) → Reviewer ⇄ Coder(重试) → Builder → END` |
| **SSE Stream** | `sse_stream.py` | Wraps `astream()` async generator, emits phase-level progress events |
| **RAG** | `rag/` | Dual-channel retrieval engine, Milvus client, embedding service, seed data |
| **State** | `state/code_gen_state.py` | Shared `CodeGenState` TypedDict (16 fields) |
| **Config** | `config.py` | All env vars + multi-language tech stack registry (`LANGUAGE_CONFIGS`) |
| **LLM Factory** | `llm_factory.py` | `create_json_parser()` — manual JSON parse scheme (DeepSeek doesn't support `with_structured_output`) |
| **Server** | `server/main.py` | FastAPI app, `POST /api/generate-code` (SSE), `GET /api/health` |
| **Tools** | `tools/` | File I/O tools (create/read/modify/delete/list), guard, context |
| **Memory** | `memory/` | Conversation memory with sliding window + Redis-backed summary |
| **Model Routing** | `core/` | `model_router.py` + `circuit_breaker.py` — primary/fallback model routing with circuit breaker |

### LangGraph Workflow Topology

```
START → intent_agent → pm_agent → architect_agent → fork_coder_and_images
                                                        │
                              (Image Collector + Coder, serial)
                                                        │
                                                        ▼
                                                  reviewer_agent
                                                        │
                                    ┌───────────────────┼───────────────────┐
                                    │                   │                   │
                              passed            failed & retry<3     retry>=3
                                    │                   │                   │
                              builder_agent     coder_agent      human_intervention
                                    │         (retry loop)              │
                                   END              │                   END
                                                    └→ reviewer_agent
```

- **Intent Agent**: classifies the request, detects code gen type + confidence level
- **Supervisor**: rule-based routing (zero LLM) — reads `phase` + `review.passed` + `retry_count`, returns next node name
- **PM Agent**: user request → structured PRD (Pydantic: features, page_type, data_dependencies)
- **Architect Agent**: PRD → component tree, file list, data flows, tech stack
- **Coder Agent**: architecture → code files via `create_json_parser` (manual JSON parsing, since DeepSeek v4-pro doesn't support `json_mode`/`function_calling`)
- **Reviewer Agent**: 5-dimension review (syntax/logic/security/style/performance), manages `retry_count` increment
- **Image Collector**: zero LLM, rule-based image placeholder generation
- **Builder Agent**: zero LLM, writes files + scaffold (package.json, vite config) + `npm install && npm build`

### RAG Pipeline (Dual-Channel Retrieval)

**Channel A (Intent-Directed)**: Routes to specific Milvus Collections based on `phase` (e.g., coder → `component_library` + `framework_api`, reviewer → `error_pattern`)

**Channel B (Global Vector)**: Parallel search across all 5 Collections, covers blind spots

**Post-processing**: SHA256 dedup → semantic dedup (cosine > 0.95) → 4-factor rerank (semantic 0.40, source 0.25, success 0.20, freshness 0.15) → format as prompt blocks

**5 Milvus Collections**: `framework_api` (30), `component_library` (10), `design_pattern` (12), `error_pattern` (15), `code_store` (0, fills on build success)

**Embedding**: `BAAI/bge-small-zh-v1.5` (512-dim), local PyTorch CPU inference (~10ms/sample)

### Database Tables (MySQL `yu_ai_code_mother`)

- `user` — users, snowflake IDs, `userAccount` unique
- `app` — user applications, linked to userId, `deployKey` unique
- `chat_history` — conversation messages (user/ai), indexed by appId + createTime
- `app_version` — versioned code snapshots per app
- `intent_config` — custom intent recognition configuration

### Key Configuration

- Java port 8123, context-path `/api`, Python port 8000
- Redis DB 0 for session/cache/rate-limiting
- Sa-Token auth with Redis-backed sessions, 30-day TTL (see `application.yml` for `sa-token.timeout`)
- Rate limiting via `@RateLimit` annotation on chat endpoints (20 req/60s per IP)
- Python config via `.env` in `python-agent/`
- Multi-language support in `config.py` via `LANGUAGE_CONFIGS` dict: vue_project, html, multi_file, python, java, go, rust, nodejs, generic
- Milvus: `MILVUS_MODE` env var — `lite` (local file, no Docker) or `standalone` (Docker, port 19530)

## Important Constraints

- **DeepSeek v4-pro** is a reasoning model — does NOT support `response_format` (json_mode) or `function_calling`. All structured output uses manual JSON parsing (`create_json_parser` + `FIELD_SPEC` + `_strip_code_fences`)
- **No `with_structured_output`** — this LangChain feature doesn't work with DeepSeek. Every Agent uses the manual JSON pattern
- **Python on Windows**: `uv run` may silently upgrade torch, breaking DLL loading. Use `.venv/Scripts/python.exe` directly for running the server
- **Java-side agent workflows have been removed**. The only supported agent implementation lives in `python-agent/`, and Java stays on the gateway/SSE proxy path.
- **SSE event format**: Python emits standard `data: {"type":"...","phase":"...",...}` lines. Java facade extracts `code_file` events for file saving but otherwise transparently proxies
- **Lombok requires JDK 23+** for annotation processing — use `JAVA_HOME="D:/Program Files/Java/jdk-23"` when compiling
