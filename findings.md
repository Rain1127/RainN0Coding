# Code Health Audit Findings

This file stores raw observations from the current audit. Treat entries as notes until promoted into the final response.

## Repository Orientation

- Dirty worktree contains many untracked files, including `python-agent/.env`, `src/main/resources/application-local.yml`, built frontend assets under `src/main/resources/static`, local data/WAL files under `data`, and agent logs.
- `src/main/resources/application-local.yml` contains apparent Tencent COS credentials.
- `python-agent/.env` contains an apparent DeepSeek API key.
- `src/main/resources/application.yml` hard-codes MySQL password `123456`.
- Python builder and model router use subprocess calls; builder has `shell=True`.
- Broad search output was polluted by generated frontend assets; subsequent scans should exclude `src/main/resources/static`, `data`, `target`, `__pycache__`.

## Java Backend

- `AppVersionController` exposes unauthenticated CRUD and an unbounded `list()` endpoint for version records containing `appId` and `codeContent`.
- `StaticResourceController` builds paths from `{deployKey}` and wildcard resource path without normalizing and checking containment under preview/deploy root.
- `AppServiceImpl.getAppVOList()` bulk-loads users, then calls `getAppVO(app)` inside the stream; `getAppVO` performs `userService.getById` again, so N+1 remains.
- `AppServiceImpl.getQueryWrapper`, `ChatHistoryServiceImpl.getQueryWrapper`, and `UserServiceImpl.getQueryWrapper` pass user-controlled `sortField` directly into `orderBy`.
- Admin list endpoints in `AppController`, `ChatHistoryController`, and `UserController` do not cap `pageSize`; public list endpoints cap at 20 but admin endpoints can request huge pages.
- `UserServiceImpl.getEncryptPassword()` uses static salt + MD5 for passwords.

## Python Agent

- `agents/builder_agent.py` does not define `builder_agent`; main logic appears indented under `_run_syntax_check`. Verified with `from agents.builder_agent import builder_agent`, which raises `ImportError`.
- `tools/read_file.py`, `tools/modify_file.py`, `tools/delete_file.py`, and `tools/list_files.py` join and normalize paths but do not enforce containment within `project_dir`.
- `tools/create_file.py` has a containment check, but uses string `startswith`; that can misclassify sibling paths with the same prefix.
- `server/main.py` exposes FastAPI with `allow_origins=["*"]` and no service-to-service auth; relies on Java gateway by convention rather than enforcement.
- `builder_agent._run_syntax_check()` uses `subprocess.run(..., shell=True)` for command templates.

## Frontend / Static Assets

- `yu-ai-code-mother-frontend` exists but appears to contain no source files in this workspace; only built assets exist under `src/main/resources/static`.
- Built frontend assets use axios with `baseURL="/api"` and `withCredentials=true`; SSE fetch uses `credentials:"include"`.
- Java CORS config allows credentialed requests from any origin, which combines badly with cookie-based Sa-Token auth.

## Verification

- `mvn compile -DskipTests` passed with JDK 23.
- Python import check failed: `from workflow.code_gen_workflow import create_code_gen_workflow` raises `ImportError` because `builder_agent` is not exported.
- Python pytest could not run because `pytest` is not installed in `python-agent/.venv`.
- `mvn test -DskipTests=false` failed: 25 tests run, 1 failure, 23 errors. Main context-load root cause is Redis connection refused at `localhost:6379`; `CodeParserTest.parseMultiFileCode` also fails an assertion independently.

## Repository Hygiene

- `.gitignore` does not ignore several generated/sensitive local artifacts observed in the worktree: `python-agent/.env`, `data/`, `AliyunJavaAgent/logs/`, `__pycache__`, SQLite/WAL files.
