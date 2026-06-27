# CODEBUDDY.md This file provides guidance to CodeBuddy when working with code in this repository.

## Commands

### Install dependencies
```bash
uv sync
```
Uses `pyproject.toml` with Tsinghua PyPI mirror. Requires Python >=3.12 and uv package manager.

### Run server
```bash
uv run python -m server.main
```
Starts FastAPI on port 8000 (configurable via `SERVER_PORT` env). Requires `.env` with `DEEPSEEK_API_KEY`.

### Run tests
```bash
uv run pytest tests/                    # all tests
uv run pytest tests/test_e2e_workflow.py # single test file
uv run pytest tests/test_all_agents.py -k "test_pm_agent"  # single test
```
Tests call real LLM APIs — they require valid `DEEPSEEK_API_KEY` in `.env`.

### Seed Milvus knowledge base
```bash
uv run python -m rag.seed_milvus
```
Populates Milvus collections with seed data (Vue 3 APIs, components, design patterns, error patterns).

## Architecture

### System Overview

A **7-Agent collaborative code generation system** orchestrated by LangGraph StateGraph. User natural-language requests flow through specialized agents, each producing structured output that feeds the next stage. The system serves as a Python backend for a Java parent application, communicating via SSE streaming.

**Data flow:**
```
User Request → FastAPI(SSE) → LangGraph Workflow
  → Intent Agent → PM Agent → Architect Agent
  → Fork[Image Collector + Coder Agent(RAG-enhanced)]
  → Reviewer Agent → (passed) Builder Agent → END
                    → (failed, retryable) Coder Agent ← retry loop (max 3)
                    → (failed, exceeded) HumanIntervention → END
```

### Agent Pipeline (agents/)

Each agent is a pure function `(state: CodeGenState) -> dict` that reads input fields, writes output fields, and sets `state.phase`. The `supervisor_agent.py` is a zero-LLM router that reads `phase` and decides the next node via LangGraph conditional edges.

| Agent | LLM | Input | Output | Phase |
|-------|-----|-------|--------|-------|
| Intent | lightweight | user_request | intent, should_clarify | intent_done / clarify |
| PM | structured | user_request, intent | prd (Feature list, page spec) | prd_done |
| Architect | structured | prd, code_gen_type | architecture (ComponentNode tree, FileSpec list, DataFlow list) | arch_done |
| Coder | reasoning | architecture, code_gen_type, retry issues | code_files (list of path+content) | code_done |
| Image Collector | none | prd | images | — |
| Reviewer | structured | code_files, architecture | review (score, issues list; pass>=80) | review_done |
| Builder | none | code_files, images | build_result | build_done |

All LLM agents use `llm_factory.create_json_parser()` with Pydantic output schemas, not free-text parsing.

### State Management (state/)

`CodeGenState(TypedDict, total=False)` is the single shared state object across all agents and the LangGraph graph. Key field groups: input (user_request, code_gen_type), per-agent outputs (intent, prd, architecture, code_files, review, images, build_result), and control (phase, retry_count, max_retries, messages). LangGraph auto-merges partial state dicts returned by each agent node.

### LLM Infrastructure (core/ + llm_factory.py)

Three-tier model routing with circuit breaker protection:
- **model_registry.py** defines 3 model groups: `reasoning` (Coder, 3 candidates), `structured` (PM/Architect/Reviewer, 2 candidates), `lightweight` (Intent, 2 candidates). Primary: DeepSeek; fallback: Qwen.
- **circuit_breaker.py** implements CLOSED→OPEN→HALF_OPEN state machine per candidate. 3 consecutive failures triggers OPEN; 30s cooldown before HALF_OPEN probe.
- **model_router.py** tries candidates by priority within a group, auto-switching on failure or breaker trip. Special handling: Qwen/DashScope on Windows uses `curl` subprocess to bypass TLS issues.
- **llm_factory.py** provides `create_json_parser(schema, field_spec, group)` — the primary interface for agents. Returns a callable that routes through model_router and parses JSON output into Pydantic models.

### RAG System (rag/)

Multi-channel retrieval enhancing Coder Agent prompts:
- **embedding_service.py** — BAAI/bge-small-zh-v1.5 (512-dim), lazy-loaded singleton
- **milvus_client.py** — Dual-mode (Lite file / Standalone Docker) Milvus wrapper. 5 collections: code_store, component_library, design_pattern, error_pattern, framework_api
- **retrieval_engine.py** — Two parallel channels: IntentDirectedRetriever (phase→specific collection) + GlobalVectorRetriever (all collections). Post-processing: 3-step dedup (hash→source→semantic) → 4-factor reranking (semantic 40% + source weight 25% + success history 20% + freshness 15%)
- **rag_builder.py** — Bridge between Coder Agent and retrieval engine. `build_rag_context()` per file; `index_code_files()` for post-build knowledge ingestion (defined but not auto-invoked)

### Workflow Orchestration (workflow/)

- **code_gen_workflow.py** — LangGraph StateGraph assembly. Fork node runs Image Collector (fast, no LLM) then Coder. Conditional edge after Reviewer routes based on review.passed and retry_count.
- **sse_stream.py** — Consumes LangGraph `astream()` snapshots, yields SSE events (phase_start, phase_complete, code_file, review_issue, code_retry, clarify, done, error). Integrates conversation memory: loads history on start, saves on completion.
- **autogen_discussion.py** — AutoGen-based Coder×Reviewer×Architect group chat for architectural issues. Implemented but not integrated into main workflow.

### Memory (memory/)

`ConversationMemory` — sliding window (10 messages) + LLM summary compression (triggered at 15 messages). Redis Hash backend with in-memory dict fallback. Summaries are 200-char Chinese text generated by DeepSeek API. Context injection: summary + last 6 messages prepended to new requests.

### Multi-Language Support

`LANGUAGE_CONFIGS` in `config.py` defines 9 tech stacks (vue_project, html, multi_file, python, java, go, rust, nodejs, generic). PM, Architect, Coder, and Reviewer agents dynamically generate their system prompts based on `state.code_gen_type`, selecting the appropriate role names, framework conventions, and code style rules.

### SSE Event Protocol

Java backend calls `POST /api/generate-code` and transparently proxies SSE byte stream to frontend. Event types: workflow_start, memory_loaded, phase_start, phase_complete, code_file, review_issue, code_retry, clarify, trace_summary, done, error.

### External Dependencies

- **LLM**: DeepSeek (primary), Qwen/DashScope (fallback) — API keys in `.env`
- **Vector DB**: Milvus (Lite mode default, no Docker required)
- **Cache**: Redis (optional, in-memory fallback)
- **Embedding**: sentence-transformers with BAAI/bge-small-zh-v1.5 (local)
