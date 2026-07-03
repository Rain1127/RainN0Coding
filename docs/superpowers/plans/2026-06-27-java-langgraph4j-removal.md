# Java LangGraph4j Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove deprecated Java-side LangGraph4j runtime code, tests, and build dependency so the repo matches the Python-only agent architecture.

**Architecture:** Keep the Java application as the gateway into the Python SSE service and delete the dead Java-side workflow stack entirely. Update only the developer-facing docs that describe the active architecture.

**Tech Stack:** Spring Boot, Maven, Java 21+, Python FastAPI agent

---

### Task 1: Remove the last Java runtime entrypoint

**Files:**
- Delete: `src/main/java/com/yupi/yuaicodemother/controller/WorkflowSseController.java`
- Verify: `src/main/java/com/yupi/yuaicodemother/core/AiCodeGeneratorFacade.java`

- [ ] Delete the controller that exposes `/workflow/*` endpoints backed by Java LangGraph4j.
- [ ] Confirm the production generation path still centers on `AiCodeGeneratorFacade` and Python SSE integration.

### Task 2: Remove Java LangGraph4j sources and tests

**Files:**
- Delete: `src/main/java/com/yupi/yuaicodemother/langgraph4j/**`
- Delete: `src/test/java/com/yupi/yuaicodemother/langgraph4j/**`

- [ ] Delete the full Java `langgraph4j` package from main sources.
- [ ] Delete the full Java `langgraph4j` package from test sources.
- [ ] Search the repository for remaining Java references and clean up any compile leftovers.

### Task 3: Remove the build dependency and update docs

**Files:**
- Modify: `pom.xml`
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`

- [ ] Remove `org.bsc.langgraph4j:langgraph4j-core` from Maven dependencies.
- [ ] Update the two developer-facing docs to say the Java-side agent path has been removed and the Python agent is the only workflow implementation.

### Task 4: Verify the cleanup

**Files:**
- Verify: repository search results

- [ ] Run repository-wide `rg` checks for `langgraph4j` references that would indicate remaining Java coupling.
- [ ] Run `mvn test` and confirm the project still passes after the removal.
