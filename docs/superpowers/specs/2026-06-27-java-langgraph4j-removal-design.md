# Java LangGraph4j Removal Design

**Goal**

Remove the deprecated Java-side LangGraph4j workflow implementation so the repository reflects the real architecture: Java acts as the gateway, and the Python agent owns all agent workflow logic.

**Scope**

- Remove the Java runtime entrypoint that still exposes LangGraph4j workflows.
- Remove the Java `langgraph4j` source package and its tests.
- Remove the Maven dependency on `org.bsc.langgraph4j:langgraph4j-core`.
- Update developer-facing docs to state that the Java-side agent has been removed and Python is the only agent implementation.

**Out of Scope**

- Large historical documentation cleanup under `docs/`.
- Refactoring the Python agent workflow.
- Any behavior changes to the Java -> Python SSE generation path.

**Architecture Decision**

The Java application keeps only the gateway responsibilities that are still part of the production path, centered on [`AiCodeGeneratorFacade`](D:/RainN0Coding/src/main/java/com/rain/rainn0coding/core/AiCodeGeneratorFacade.java) and the Python HTTP/SSE integration. All Java-side workflow orchestration code under `src/main/java/com/rain/rainn0coding/langgraph4j/` is removed instead of being kept as deprecated code.

**Implementation Notes**

- Delete [`WorkflowSseController.java`](D:/RainN0Coding/src/main/java/com/rain/rainn0coding/controller/WorkflowSseController.java) because it is the last live Java HTTP entrypoint into LangGraph4j.
- Delete the full Java `langgraph4j` package from main and test sources.
- Remove the Maven dependency and then run a repository-wide search to confirm there are no remaining Java references.
- Keep direct developer docs in sync so future contributors do not mistake the deleted Java path for a supported implementation.

**Success Criteria**

- `rg` finds no remaining Java imports or packages referencing `com.rain.rainn0coding.langgraph4j`.
- `pom.xml` no longer declares `langgraph4j-core`.
- `mvn test` passes without the Java LangGraph4j sources or tests.
- `AGENTS.md` and `CLAUDE.md` clearly describe the Python-only agent architecture.
