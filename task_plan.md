# Code Health Audit Plan

Goal: Inspect the current project for likely bugs, security issues, performance problems, and technical debt without modifying product code.

## Phases

| Phase | Status | Scope |
| --- | --- | --- |
| 1. Repository orientation | complete | Map structure, changed files, build/test surfaces |
| 2. Java backend review | complete | Controllers, services, auth, SSE proxy, persistence |
| 3. Python agent review | complete | FastAPI, LangGraph workflow, tools, RAG, SSE |
| 4. Frontend review | complete | API calls, routing, auth state, build-time risks |
| 5. Verification and synthesis | complete | Run targeted static/build checks where feasible and produce findings |

## Decisions

- Treat existing repository files as user-owned; do not revert or clean them.
- Focus on high-risk execution paths rather than exhaustive style nits.
- Exclude generated/static assets and local data caches from broad text scans unless directly relevant.

## Errors Encountered

| Error | Attempt | Resolution |
| --- | --- | --- |
| PowerShell did not accept POSIX-style `PYTHONPATH=.` command | Tried py_compile with Unix env prefix | Re-ran using `$env:PYTHONPATH='.'` |
| Python pytest unavailable | Ran `.venv/Scripts/python.exe -m pytest ...` | Recorded missing `pytest` dependency; used import checks for Python workflow |
| Java full tests failed | Ran `mvn test -DskipTests=false` | Root cause from surefire: Redis refused connection; separate parser assertion failure also present |
