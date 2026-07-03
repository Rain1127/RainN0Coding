# FastAPI Lifespan Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace deprecated FastAPI `on_event` lifecycle hooks in the Python agent server with a `lifespan` handler, while keeping startup, shutdown, and request behavior unchanged.

**Architecture:** Keep the migration local to `python-agent/server/main.py` by moving the existing startup and shutdown bodies into a single async lifespan context manager. Add one focused regression test in `python-agent/tests/test_internal_auth_and_concurrency.py` that exercises the existing `TestClient` path and proves the deprecated `on_event` warnings are gone.

**Tech Stack:** Python 3.12, FastAPI, Starlette `TestClient`, pytest, asyncio

---

## File Structure

- Modify `python-agent/server/main.py`
  - Replace `@app.on_event("startup")` and `@app.on_event("shutdown")` with an async lifespan context manager.
  - Keep the existing runtime initialization and cleanup responsibilities intact.
- Modify `python-agent/tests/test_internal_auth_and_concurrency.py`
  - Add a deterministic regression test that captures warnings around `TestClient(main.app)` lifecycle.
  - Add minimal fake store support needed for startup and shutdown paths to run cleanly under lifespan.

---

### Task 1: Add a Failing Lifecycle Warning Regression Test

**Files:**
- Modify: `python-agent/tests/test_internal_auth_and_concurrency.py`
- Test: `python-agent/tests/test_internal_auth_and_concurrency.py`

- [ ] **Step 1: Add a fake runtime helper and a failing warning regression test**

Make these edits in `python-agent/tests/test_internal_auth_and_concurrency.py`.

First, add the missing import near the top:

```python
import warnings
```

Then add this helper near `_FakeStore`:

```python
def _install_fake_runtime_modules(monkeypatch):
    milvus_module = types.ModuleType("rag.milvus_client")
    milvus_module.milvus_store = _FakeStore()

    sqlite_module = types.ModuleType("rag.sqlite_store")
    sqlite_module.sqlite_store = _FakeStore()

    feedback_module = types.ModuleType("rag.feedback_tracker")
    feedback_module.feedback_tracker = _FakeStore()

    monkeypatch.setitem(sys.modules, "rag.milvus_client", milvus_module)
    monkeypatch.setitem(sys.modules, "rag.sqlite_store", sqlite_module)
    monkeypatch.setitem(sys.modules, "rag.feedback_tracker", feedback_module)
```

Update `test_health_does_not_require_internal_token` to use the new helper:

```python
def test_health_does_not_require_internal_token(monkeypatch):
    main = load_main(monkeypatch, token="secret")
    _install_fake_runtime_modules(monkeypatch)

    client = TestClient(main.app)
    response = client.get("/api/health")

    assert response.status_code == 200
```

Add `init_tables` and `close` methods to `_FakeStore`:

```python
class _FakeStore:
    def connect(self):
        return None

    def init_tables(self):
        return None

    def close(self):
        return None
```

Add this new regression test above `test_internal_auth_suite_has_harness_marker`:

```python
def test_testclient_lifecycle_does_not_emit_on_event_deprecation_warning(monkeypatch):
    main = load_main(monkeypatch, token="secret")
    _install_fake_runtime_modules(monkeypatch)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with TestClient(main.app) as client:
            response = client.get("/api/health")

    assert response.status_code == 200
    assert not any("on_event is deprecated" in str(w.message) for w in caught)
```

- [ ] **Step 2: Run the single regression test and verify it fails first**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_internal_auth_and_concurrency.py::test_testclient_lifecycle_does_not_emit_on_event_deprecation_warning -v
```

Expected: FAIL because `server/main.py` still defines deprecated `@app.on_event(...)` hooks and `TestClient` startup emits the warning.

- [ ] **Step 3: Re-run the health test to confirm the fake runtime helper still supports the current path**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_internal_auth_and_concurrency.py::test_health_does_not_require_internal_token -v
```

Expected: PASS or, if it fails due to missing fake lifecycle methods, fix only the helper additions above before moving on.

- [ ] **Step 4: Commit**

```bash
git add python-agent/tests/test_internal_auth_and_concurrency.py
git commit -m "test: add fastapi lifespan warning regression"
```

---

### Task 2: Replace Deprecated Lifecycle Hooks with a Lifespan Handler

**Files:**
- Modify: `python-agent/server/main.py`
- Test: `python-agent/tests/test_internal_auth_and_concurrency.py`

- [ ] **Step 1: Add the lifespan import and remove the deprecated hook decorators**

In `python-agent/server/main.py`, update the imports at the top:

```python
from contextlib import asynccontextmanager
```

Then remove these two decorated functions entirely:

```python
@app.on_event("startup")
async def startup():
    ...


@app.on_event("shutdown")
async def shutdown():
    ...
```

- [ ] **Step 2: Add a single async lifespan context manager with the current startup and shutdown bodies**

Insert this block above `app = FastAPI(...)`:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage runtime resources for FastAPI startup and shutdown."""
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
            logger.info("Quality cleanup task stopped")
            _cleanup_task = None

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

Important:

- keep `_cleanup_task` as the existing module-global task handle
- keep the startup and shutdown logging materially the same
- keep resource-close failures non-fatal

- [ ] **Step 3: Construct the FastAPI app with the new lifespan handler**

Update the app construction block to:

```python
app = FastAPI(
    title="AI Code Gen Agents",
    version="1.0.0",
    description="7-Agent cooperative code generation system - Python smart backend",
    lifespan=lifespan,
)
```

Do not change route registration, middleware order, `setup_tracing(app)`, or `setup_monitoring(app)`.

- [ ] **Step 4: Re-run the warning regression test**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_internal_auth_and_concurrency.py::test_testclient_lifecycle_does_not_emit_on_event_deprecation_warning -v
```

Expected: PASS.

- [ ] **Step 5: Re-run the focused internal auth suite**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_internal_auth_and_concurrency.py -v
```

Expected: PASS with the `on_event` deprecation warnings removed from this suite.

- [ ] **Step 6: Commit**

```bash
git add python-agent/server/main.py python-agent/tests/test_internal_auth_and_concurrency.py
git commit -m "fix: migrate python agent lifecycle to fastapi lifespan"
```

---

### Task 3: Run Focused Regression Verification

**Files:**
- Modify: `python-agent/server/main.py`
- Modify: `python-agent/tests/test_internal_auth_and_concurrency.py`
- Test: `python-agent/tests/test_internal_auth_and_concurrency.py`

- [ ] **Step 1: Run the focused tracing and FastAPI boundary verification**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_tracing.py tests/test_internal_auth_and_concurrency.py -v
```

Expected: PASS. The suite should keep the tracing work green while proving the FastAPI lifecycle path still behaves correctly.

- [ ] **Step 2: Run the canonical harness verification**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest -m harness -v
```

Expected: PASS. The previous FastAPI `on_event is deprecated` warnings should no longer appear in this harness output.

- [ ] **Step 3: Commit the final verified state if needed**

```bash
git add python-agent/server/main.py python-agent/tests/test_internal_auth_and_concurrency.py
git commit -m "test: verify fastapi lifespan migration"
```

Only do this commit if the execution workflow left the branch without the earlier commits.

---

## Plan Self-Review

- Spec coverage: the plan covers the lifespan migration, startup/shutdown behavior preservation, targeted warning regression test, focused suite verification, and harness verification.
- Placeholder scan: every task includes concrete file paths, exact code snippets, exact commands, and expected outputs; no placeholder language remains.
- Type consistency: the plan consistently uses `lifespan`, `_cleanup_task`, `_install_fake_runtime_modules`, and the existing `load_main(...)` test entrypoint throughout.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-02-fastapi-lifespan-migration.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
