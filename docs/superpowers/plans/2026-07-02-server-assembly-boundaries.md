# Server Assembly Boundaries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract FastAPI app-assembly concerns from `python-agent/server/main.py` into focused `lifespan`, `middleware`, and `routes` modules without changing runtime behavior.

**Architecture:** Keep endpoint handlers, request models, and logging/tracing helper code in `python-agent/server/main.py`, and move only the wiring seams out. The app should still be built in `main.py`, but `lifespan`, middleware registration, and route registration should come from narrow helper modules with explicit interfaces.

**Tech Stack:** Python 3.12, FastAPI, Starlette `TestClient`, pytest, asyncio

---

## File Structure

- Create `python-agent/server/lifespan.py`
  - Own the FastAPI lifespan context manager and cleanup-task state.
- Create `python-agent/server/middleware.py`
  - Own middleware registration with preserved order and current CORS setup.
- Create `python-agent/server/routes.py`
  - Own route-to-handler registration only.
- Modify `python-agent/server/main.py`
  - Remove inline lifespan definition and inline middleware/route registration bodies.
  - Keep handler implementations, models, and logging/tracing setup.
- Modify `python-agent/tests/test_internal_auth_and_concurrency.py`
  - Update the cleanup-task assertion to follow the extracted lifespan state.

---

### Task 1: Extract Lifespan Wiring

**Files:**
- Create: `python-agent/server/lifespan.py`
- Modify: `python-agent/server/main.py`
- Modify: `python-agent/tests/test_internal_auth_and_concurrency.py`
- Test: `python-agent/tests/test_internal_auth_and_concurrency.py`

- [ ] **Step 1: Write the failing test update for extracted cleanup-task state**

In `python-agent/tests/test_internal_auth_and_concurrency.py`, replace the existing direct `main._cleanup_task` assertion test with this version:

```python
def test_testclient_shutdown_clears_cleanup_task_reference(monkeypatch):
    main = load_main(monkeypatch, token="secret")
    _install_fake_runtime_modules(monkeypatch)

    import server.lifespan as server_lifespan

    with TestClient(main.app):
        assert server_lifespan.get_cleanup_task() is not None

    assert server_lifespan.get_cleanup_task() is None
```

This should fail before production changes because `server.lifespan` does not exist yet.

- [ ] **Step 2: Run the single cleanup-task regression test and verify it fails first**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_internal_auth_and_concurrency.py::test_testclient_shutdown_clears_cleanup_task_reference -v
```

Expected: FAIL with an import error for `server.lifespan` or missing `get_cleanup_task`.

- [ ] **Step 3: Create `python-agent/server/lifespan.py`**

Create this file:

```python
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from config import config

_cleanup_task: asyncio.Task | None = None


def get_cleanup_task() -> asyncio.Task | None:
    return _cleanup_task


@asynccontextmanager
async def lifespan(app: FastAPI):
    from server.main import logger, _periodic_quality_cleanup

    global _cleanup_task

    try:
        from rag.sqlite_store import sqlite_store

        sqlite_store.connect()
        sqlite_store.init_tables()
        logger.info(f"SqliteStore initialized: {config.SQLITE_DB_PATH}")
    except Exception as e:
        logger.warning(f"SqliteStore init failed (grep search disabled): {e}")

    try:
        import os

        os.makedirs(config.CODE_STORE_DIR, exist_ok=True)
        logger.info(f"CodeStore directory ready: {config.CODE_STORE_DIR}")
    except Exception as e:
        logger.warning(f"CodeStore directory create failed: {e}")

    try:
        from rag.feedback_tracker import feedback_tracker

        feedback_tracker.connect()
        feedback_tracker.init_tables()
        logger.info("FeedbackTracker initialized")
    except Exception as e:
        logger.warning(f"FeedbackTracker init failed: {e}")

    _cleanup_task = asyncio.create_task(_periodic_quality_cleanup())
    logger.info(
        f"Quality cleanup task started (interval={config.QUALITY_CLEANUP_INTERVAL_HOURS}h, "
        f"min_age={config.QUALITY_MIN_AGE_DAYS}d)"
    )
    logger.info(f"Search engine mode: {'Hybrid (grep+RAG)' if config.USE_HYBRID_ENGINE else 'Vector-only (RAG)'}")

    try:
        yield
    finally:
        if _cleanup_task:
            _cleanup_task.cancel()
            try:
                await _cleanup_task
            except asyncio.CancelledError:
                pass
            _cleanup_task = None
            logger.info("Quality cleanup task stopped")

        try:
            from rag.milvus_client import milvus_store

            milvus_store.close()
            logger.info("Milvus connection closed")
        except Exception:
            pass
        try:
            from rag.sqlite_store import sqlite_store

            sqlite_store.close()
            logger.info("SqliteStore connection closed")
        except Exception:
            pass
        try:
            from rag.feedback_tracker import feedback_tracker

            feedback_tracker.close()
            logger.info("FeedbackTracker connection closed")
        except Exception:
            pass
```

- [ ] **Step 4: Update `python-agent/server/main.py` to consume the extracted lifespan**

Make these changes in `python-agent/server/main.py`:

1. Remove:

```python
from contextlib import asynccontextmanager
```

2. Add:

```python
from server.lifespan import lifespan
```

3. Remove the inline lifecycle state and function:

```python
_cleanup_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    ...
```

4. Keep:

```python
app = FastAPI(
    title="AI Code Gen Agents",
    version="1.0.0",
    description="7-Agent cooperative code generation system - Python smart backend",
    lifespan=lifespan,
)
```

- [ ] **Step 5: Re-run the cleanup-task regression and the warning regression**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_internal_auth_and_concurrency.py::test_testclient_shutdown_clears_cleanup_task_reference tests/test_internal_auth_and_concurrency.py::test_testclient_lifecycle_does_not_emit_on_event_deprecation_warning -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add python-agent/server/lifespan.py python-agent/server/main.py python-agent/tests/test_internal_auth_and_concurrency.py
git commit -m "refactor: extract server lifespan wiring"
```

---

### Task 2: Extract Middleware Registration

**Files:**
- Create: `python-agent/server/middleware.py`
- Modify: `python-agent/server/main.py`
- Test: `python-agent/tests/test_internal_auth_and_concurrency.py`

- [ ] **Step 1: Write a failing smoke test that proves middleware registration still happens through app assembly**

Add this test to `python-agent/tests/test_internal_auth_and_concurrency.py`:

```python
def test_app_keeps_internal_auth_and_logging_middleware(monkeypatch):
    main = load_main(monkeypatch, token="secret")

    middleware_names = [middleware.cls.__name__ for middleware in main.app.user_middleware]

    assert "CORSMiddleware" in middleware_names
    assert len(main.app.middleware_stack.app.user_middleware) >= 0
```

Then immediately replace it with the actually stable version below before implementation:

```python
def test_app_keeps_cors_middleware_registration(monkeypatch):
    main = load_main(monkeypatch, token="secret")

    middleware_names = [middleware.cls.__name__ for middleware in main.app.user_middleware]

    assert "CORSMiddleware" in middleware_names
```

Use the stable version as the real test. This should continue to pass through the extraction if assembly stays correct.

Now add a second failing monkeypatch-based test that requires the new registration function:

```python
def test_main_imports_register_middleware(monkeypatch):
    import server.main as main

    assert hasattr(main, "register_middleware")
```

Expected implementation note: this fails until `main.py` imports the extracted helper by name.

- [ ] **Step 2: Run the new middleware-import test and verify it fails first**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_internal_auth_and_concurrency.py::test_main_imports_register_middleware -v
```

Expected: FAIL because `register_middleware` is not yet imported into `server.main`.

- [ ] **Step 3: Create `python-agent/server/middleware.py`**

Create this file:

```python
import hmac
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import config
from server.main import PUBLIC_PATHS, logger


async def internal_token_auth(request: Request, call_next):
    path = request.url.path
    if request.method == "OPTIONS" or path in PUBLIC_PATHS or not path.startswith("/api"):
        return await call_next(request)
    if not config.INTERNAL_API_TOKEN:
        if config.INTERNAL_API_ALLOW_MISSING_TOKEN:
            return await call_next(request)
        return JSONResponse({"detail": "internal authentication is misconfigured"}, status_code=503)

    provided = request.headers.get("X-Internal-Token", "")
    if not hmac.compare_digest(provided, config.INTERNAL_API_TOKEN):
        return JSONResponse({"detail": "unauthorized internal request"}, status_code=401)

    return await call_next(request)


async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    logger.info(f"{request.method} {request.url.path} -> {response.status_code} ({duration:.2f}s)")
    return response


def register_middleware(app: FastAPI) -> None:
    app.middleware("http")(internal_token_auth)
    app.middleware("http")(log_requests)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
```

- [ ] **Step 4: Update `python-agent/server/main.py` to use the middleware registrar**

Make these changes in `python-agent/server/main.py`:

1. Remove these imports:

```python
import hmac
import time
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
```

Keep `JSONResponse` only if still needed elsewhere in handlers.

2. Add:

```python
from server.middleware import register_middleware
```

3. Remove the inline middleware definitions and inline CORS registration:

```python
@app.middleware("http")
async def internal_token_auth(...):
    ...


@app.middleware("http")
async def log_requests(...):
    ...

app.add_middleware(
    CORSMiddleware,
    ...
)
```

4. Replace them with:

```python
register_middleware(app)
```

- [ ] **Step 5: Re-run the middleware tests and focused suite**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_internal_auth_and_concurrency.py::test_main_imports_register_middleware tests/test_internal_auth_and_concurrency.py::test_app_keeps_cors_middleware_registration -v
```

Then run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_internal_auth_and_concurrency.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add python-agent/server/middleware.py python-agent/server/main.py python-agent/tests/test_internal_auth_and_concurrency.py
git commit -m "refactor: extract server middleware registration"
```

---

### Task 3: Extract Route Registration

**Files:**
- Create: `python-agent/server/routes.py`
- Modify: `python-agent/server/main.py`
- Test: `python-agent/tests/test_internal_auth_and_concurrency.py`

- [ ] **Step 1: Write a failing route-registration import test**

Add this test to `python-agent/tests/test_internal_auth_and_concurrency.py`:

```python
def test_main_imports_register_routes(monkeypatch):
    main = load_main(monkeypatch, token="secret")

    assert hasattr(main, "register_routes")
```

- [ ] **Step 2: Run the single route-registration test and verify it fails first**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_internal_auth_and_concurrency.py::test_main_imports_register_routes -v
```

Expected: FAIL because `register_routes` is not yet imported into `server.main`.

- [ ] **Step 3: Create `python-agent/server/routes.py`**

Create this file:

```python
from fastapi import FastAPI


def register_routes(
    app: FastAPI,
    *,
    generate_code_handler,
    route_code_gen_type_handler,
    health_handler,
) -> None:
    app.post("/api/generate-code")(generate_code_handler)
    app.post("/api/route-codegen-type")(route_code_gen_type_handler)
    app.get("/api/health")(health_handler)
```

- [ ] **Step 4: Update `python-agent/server/main.py` to use extracted route registration**

Make these changes in `python-agent/server/main.py`:

1. Add:

```python
from server.routes import register_routes
```

2. Remove the route decorators from the existing handlers:

```python
@app.post("/api/generate-code")
@app.post("/api/route-codegen-type")
@app.get("/api/health")
```

3. After the handler definitions, register them explicitly:

```python
register_routes(
    app,
    generate_code_handler=generate_code,
    route_code_gen_type_handler=route_code_gen_type_api,
    health_handler=health,
)
```

Do not rename handlers in this task.

- [ ] **Step 5: Re-run the route-registration test and focused suite**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_internal_auth_and_concurrency.py::test_main_imports_register_routes -v
```

Then run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_internal_auth_and_concurrency.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add python-agent/server/routes.py python-agent/server/main.py python-agent/tests/test_internal_auth_and_concurrency.py
git commit -m "refactor: extract server route registration"
```

---

### Task 4: Run Focused Regression Verification

**Files:**
- Modify: `python-agent/server/lifespan.py`
- Modify: `python-agent/server/middleware.py`
- Modify: `python-agent/server/routes.py`
- Modify: `python-agent/server/main.py`
- Modify: `python-agent/tests/test_internal_auth_and_concurrency.py`
- Test: `python-agent/tests/test_internal_auth_and_concurrency.py`
- Test: `python-agent/tests/test_tracing.py`

- [ ] **Step 1: Run the focused tracing and server boundary verification**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_tracing.py tests/test_internal_auth_and_concurrency.py -v
```

Expected: PASS.

- [ ] **Step 2: Run the canonical harness verification**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest -m harness -v
```

Expected: PASS.

- [ ] **Step 3: Commit the final verified state if needed**

```bash
git add python-agent/server/lifespan.py python-agent/server/middleware.py python-agent/server/routes.py python-agent/server/main.py python-agent/tests/test_internal_auth_and_concurrency.py
git commit -m "test: verify server assembly boundary extraction"
```

Only do this commit if the execution workflow left the branch without the earlier commits.

---

## Plan Self-Review

- Spec coverage: the plan covers lifespan extraction, middleware registration extraction, route registration extraction, preserving handler locations, and focused plus harness verification.
- Placeholder scan: each task includes concrete file paths, explicit code snippets, exact commands, and expected outcomes; no placeholder language remains.
- Type consistency: the plan consistently uses `lifespan`, `register_middleware`, `register_routes`, and `get_cleanup_task` across the extraction steps and tests.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-02-server-assembly-boundaries.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
