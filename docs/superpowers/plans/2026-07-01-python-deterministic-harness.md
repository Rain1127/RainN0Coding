# Python Deterministic Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic pytest-centered harness layer for the Python agent with explicit `unit / integration / harness` markers, minimal shared fixtures, and stable verification commands.

**Architecture:** Keep pytest as the only runner and organize the existing production-hardening tests instead of introducing a new framework. Add marker registration in `pyproject.toml`, extract the smallest useful shared helpers into `tests/conftest.py`, mark the current focused suites conservatively, and verify both file-based and marker-based execution paths.

**Tech Stack:** Python 3.12, pytest, FastAPI TestClient, existing Python test suite under `python-agent/tests`, existing harness docs under `docs/`.

---

## File Structure

- Modify `python-agent/pyproject.toml`
  - Register `unit`, `integration`, and `harness` markers in pytest config.
- Create `python-agent/tests/conftest.py`
  - Shared deterministic helpers only: guardrail reload, tool-context temp dir, fake conversation memory, JSON event collection helper.
- Modify `python-agent/tests/test_guardrails_prompt.py`
  - Move repeated reload helpers to `conftest.py`.
  - Mark the file or tests as `unit`.
- Modify `python-agent/tests/test_guardrails_tools.py`
  - Reuse shared temp tool context fixture if it reduces duplication cleanly.
  - Mark as `integration` and `harness`.
- Modify `python-agent/tests/test_guardrails_output.py`
  - Reuse shared fake memory / event collection helpers where appropriate.
  - Mark as `integration` and `harness`.
- Modify `python-agent/tests/test_internal_auth_and_concurrency.py`
  - Mark as `integration` and `harness`.
- Modify `python-agent/tests/test_tools.py`
  - Mark as `integration` and `harness`.
- Modify `python-agent/tests/test_workflow_imports_unittest.py`
  - Mark as `harness`.
- Modify `docs/production-hardening-harness.md`
  - Document the new marker-based execution model and canonical commands.
- Modify `.planning/2026-06-30-production-hardening/progress.md`
  - Record area 3 implementation and actual verification evidence.

---

### Task 1: Register Harness Markers in Pytest

**Files:**
- Modify: `python-agent/pyproject.toml`
- Test: `python-agent/tests/test_guardrails_prompt.py`

- [ ] **Step 1: Write the failing pytest marker config check**

Append this test to `python-agent/tests/test_guardrails_prompt.py`:

```python
def test_pytest_marker_config_exists():
    import tomllib
    from pathlib import Path

    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    markers = data["tool"]["pytest"]["ini_options"]["markers"]

    assert "unit: deterministic pure-python checks" in markers
    assert "integration: runtime boundary checks inside python-agent" in markers
    assert "harness: focused production-hardening verification suites" in markers
```

- [ ] **Step 2: Run the single test to verify it fails**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_guardrails_prompt.py::test_pytest_marker_config_exists -v
```

Expected: FAIL with missing `tool.pytest.ini_options.markers`.

- [ ] **Step 3: Add pytest marker registration to `pyproject.toml`**

Append this block to `python-agent/pyproject.toml` after the UV configuration:

```toml
[tool.pytest.ini_options]
markers = [
    "unit: deterministic pure-python checks",
    "integration: runtime boundary checks inside python-agent",
    "harness: focused production-hardening verification suites",
]
```

- [ ] **Step 4: Re-run the marker config test**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_guardrails_prompt.py::test_pytest_marker_config_exists -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add python-agent/pyproject.toml python-agent/tests/test_guardrails_prompt.py
git commit -m "test: register python harness pytest markers"
```

---

### Task 2: Add Minimal Shared Deterministic Test Fixtures

**Files:**
- Create: `python-agent/tests/conftest.py`
- Modify: `python-agent/tests/test_guardrails_prompt.py`
- Test: `python-agent/tests/test_guardrails_prompt.py`

- [ ] **Step 1: Write a failing test that uses shared conftest helpers**

Append this test near the existing reload helper tests in `python-agent/tests/test_guardrails_prompt.py`:

```python
def test_conftest_reload_helpers_available(monkeypatch, reload_guardrail_modules, reload_config_module_fixture):
    config_module = reload_config_module_fixture(monkeypatch)

    assert config_module.config.GUARDRAILS_ENABLED is True

    reload_guardrail_modules()
    import importlib

    policy_module = importlib.import_module("guardrails.policy")
    assert policy_module.max_prompt_chars() == 12000
```

- [ ] **Step 2: Run the single test to verify it fails**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_guardrails_prompt.py::test_conftest_reload_helpers_available -v
```

Expected: FAIL because the `reload_guardrail_modules` and `reload_config_module_fixture` fixtures do not exist yet.

- [ ] **Step 3: Create `python-agent/tests/conftest.py` with minimal shared helpers**

Create this file:

```python
import importlib
import json
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DEFAULT_GUARDRAIL_ENV_KEYS = [
    "GUARDRAILS_ENABLED",
    "GUARDRAILS_AUDIT_LOW_RISK",
    "GUARDRAILS_MAX_PROMPT_CHARS",
    "GUARDRAILS_MAX_FILE_WRITE_BYTES",
    "GUARDRAILS_MAX_MODIFY_REPLACEMENT_BYTES",
    "GUARDRAILS_MAX_LIST_FILES_DEPTH",
]


@pytest.fixture
def reload_guardrail_modules():
    def _reload() -> None:
        for module_name in [
            "guardrails",
            "guardrails.audit",
            "guardrails.engine",
            "guardrails.models",
            "guardrails.output_guard",
            "guardrails.policy",
            "guardrails.prompt_guard",
            "guardrails.tool_guard",
        ]:
            sys.modules.pop(module_name, None)

    return _reload


@pytest.fixture
def reload_config_module_fixture():
    def _reload(monkeypatch, env_keys: list[str] | None = None):
        for key in env_keys or DEFAULT_GUARDRAIL_ENV_KEYS:
            monkeypatch.delenv(key, raising=False)
        sys.modules.pop("config", None)
        return importlib.import_module("config")

    return _reload


@pytest.fixture
def tool_context():
    from tools import set_tool_context

    @contextmanager
    def _tool_context(app_id: str = "test-app", user_role: str = "user"):
        with tempfile.TemporaryDirectory() as tmpdir:
            set_tool_context(tmpdir, app_id, user_role)
            yield tmpdir

    return _tool_context


@pytest.fixture
def fake_conversation_memory():
    class _FakeConversationMemory:
        def get_context(self, thread_id):
            return {"summary": "", "recent_messages": []}

        def add_message(self, thread_id, role, content):
            return None

    return _FakeConversationMemory()


@pytest.fixture
def collect_json_events():
    async def _collect(async_iterable):
        events = []
        async for event in async_iterable:
            events.append(json.loads(event))
        return events

    return _collect
```

- [ ] **Step 4: Replace local reload helpers in `test_guardrails_prompt.py` with fixture usage**

Make these edits in `python-agent/tests/test_guardrails_prompt.py`:

```python
import importlib
import pytest


pytestmark = pytest.mark.unit


def test_guardrails_config_defaults(monkeypatch, reload_config_module_fixture):
    config_module = reload_config_module_fixture(monkeypatch)
    cfg = config_module.config
    ...


def test_guardrails_policy_helpers_follow_reloaded_config(monkeypatch, reload_guardrail_modules, reload_config_module_fixture):
    reload_guardrail_modules()
    config_module = reload_config_module_fixture(monkeypatch)
    policy_module = importlib.import_module("guardrails.policy")
    ...


def test_guardrails_package_exports(reload_guardrail_modules):
    reload_guardrail_modules()
    guardrails_module = importlib.import_module("guardrails")
    ...
```

Also remove the old inline helper functions:

```python
def reload_config_module(...):
    ...


def reload_guardrails_modules():
    ...
```

- [ ] **Step 5: Run the guardrails prompt suite**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_guardrails_prompt.py -v
```

Expected: PASS, including the new conftest-fixture test.

- [ ] **Step 6: Commit**

```bash
git add python-agent/tests/conftest.py python-agent/tests/test_guardrails_prompt.py
git commit -m "test: add shared deterministic python harness fixtures"
```

---

### Task 3: Mark Focused Guardrail and Tool Suites

**Files:**
- Modify: `python-agent/tests/test_guardrails_prompt.py`
- Modify: `python-agent/tests/test_guardrails_tools.py`
- Modify: `python-agent/tests/test_guardrails_output.py`
- Modify: `python-agent/tests/test_tools.py`
- Test: `python-agent/tests/test_guardrails_prompt.py`
- Test: `python-agent/tests/test_guardrails_tools.py`
- Test: `python-agent/tests/test_guardrails_output.py`
- Test: `python-agent/tests/test_tools.py`

- [ ] **Step 1: Write a failing marker-selection smoke test**

Append this test to `python-agent/tests/test_guardrails_prompt.py`:

```python
def test_guardrails_prompt_module_is_marked_unit():
    marker_names = {mark.name for mark in test_guardrails_prompt_module_is_marked_unit.pytestmark}
    assert "unit" in marker_names
```

Expected implementation note: this will fail until a module-level `pytestmark = pytest.mark.unit` exists.

- [ ] **Step 2: Run the single marker smoke test**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_guardrails_prompt.py::test_guardrails_prompt_module_is_marked_unit -v
```

Expected: FAIL because the file is not yet marked.

- [ ] **Step 3: Add explicit markers to the focused suites**

Apply these module-level markers:

In `python-agent/tests/test_guardrails_prompt.py`:

```python
import pytest

pytestmark = pytest.mark.unit
```

In `python-agent/tests/test_guardrails_tools.py`:

```python
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.harness]
```

In `python-agent/tests/test_guardrails_output.py`:

```python
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.harness]
```

In `python-agent/tests/test_tools.py`:

```python
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.harness]
```

- [ ] **Step 4: Re-run the focused files directly**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_guardrails_prompt.py tests/test_guardrails_tools.py tests/test_guardrails_output.py tests/test_tools.py -v
```

Expected: PASS. Marker additions should not change behavior.

- [ ] **Step 5: Commit**

```bash
git add python-agent/tests/test_guardrails_prompt.py python-agent/tests/test_guardrails_tools.py python-agent/tests/test_guardrails_output.py python-agent/tests/test_tools.py
git commit -m "test: mark focused python guardrail and tool suites"
```

---

### Task 4: Mark FastAPI and Workflow Harness Suites

**Files:**
- Modify: `python-agent/tests/test_internal_auth_and_concurrency.py`
- Modify: `python-agent/tests/test_workflow_imports_unittest.py`
- Test: `python-agent/tests/test_internal_auth_and_concurrency.py`
- Test: `python-agent/tests/test_workflow_imports_unittest.py`

- [ ] **Step 1: Write a failing marker smoke test for the API harness file**

Append this test to `python-agent/tests/test_internal_auth_and_concurrency.py`:

```python
def test_internal_auth_suite_has_harness_marker():
    marker_names = {mark.name for mark in test_internal_auth_suite_has_harness_marker.pytestmark}
    assert "harness" in marker_names
```

- [ ] **Step 2: Run the single marker smoke test**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_internal_auth_and_concurrency.py::test_internal_auth_suite_has_harness_marker -v
```

Expected: FAIL because no module-level harness marker exists yet.

- [ ] **Step 3: Add explicit markers to the API and workflow harness files**

In `python-agent/tests/test_internal_auth_and_concurrency.py`:

```python
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.harness]
```

In `python-agent/tests/test_workflow_imports_unittest.py`:

```python
import pytest

pytestmark = pytest.mark.harness
```

- [ ] **Step 4: Re-run the focused API and workflow files**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_internal_auth_and_concurrency.py tests/test_workflow_imports_unittest.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add python-agent/tests/test_internal_auth_and_concurrency.py python-agent/tests/test_workflow_imports_unittest.py
git commit -m "test: mark python api and workflow harness suites"
```

---

### Task 5: Verify Marker-Selected Harness Commands

**Files:**
- Modify: `python-agent/tests/test_guardrails_tools.py`
- Modify: `python-agent/tests/test_guardrails_output.py`
- Modify: `python-agent/tests/test_internal_auth_and_concurrency.py`
- Test: `python-agent/tests/test_guardrails_prompt.py`
- Test: `python-agent/tests/test_guardrails_tools.py`
- Test: `python-agent/tests/test_guardrails_output.py`
- Test: `python-agent/tests/test_internal_auth_and_concurrency.py`
- Test: `python-agent/tests/test_workflow_imports_unittest.py`
- Test: `python-agent/tests/test_tools.py`

- [ ] **Step 1: Use the shared `tool_context` and `fake_conversation_memory` fixtures where they reduce duplication cleanly**

Make these minimal test cleanups:

In `python-agent/tests/test_guardrails_tools.py`, replace the inline `tempfile.TemporaryDirectory()` setup with the shared fixture shape:

```python
def test_create_file_blocks_project_escape(tool_context):
    with tool_context(app_id="app-1", user_role="user"):
        result = create_file.invoke({"path": "../escape.txt", "content": "bad"})
        assert "guardrail_blocked" in result
```

Apply the same pattern to the other two tests in the file.

In `python-agent/tests/test_guardrails_output.py`, replace the inline fake memory class usage with `fake_conversation_memory`:

```python
def test_stream_workflow_emits_guardrail_blocked_for_protected_output(monkeypatch, fake_conversation_memory, collect_json_events):
    import workflow.sse_stream as sse_stream
    ...
    monkeypatch.setattr(sse_stream, "conversation_memory", fake_conversation_memory)
    ...
    events = asyncio.run(
        collect_json_events(sse_stream.stream_workflow("hello", request_id="req-out", trace_id="trace-out"))
    )
```

Keep this cleanup shallow. Do not rewrite unrelated test structure.

- [ ] **Step 2: Re-run the directly targeted focused files**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_guardrails_prompt.py tests/test_guardrails_tools.py tests/test_guardrails_output.py tests/test_internal_auth_and_concurrency.py tests/test_workflow_imports_unittest.py tests/test_tools.py -v
```

Expected: PASS.

- [ ] **Step 3: Run the marker-selected `unit` suite**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest -m unit -v
```

Expected: PASS and select the prompt/guardrail pure-python suite.

- [ ] **Step 4: Run the marker-selected `integration` suite**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest -m integration -v
```

Expected: PASS and include the FastAPI, SSE, tool, and file-tool runtime boundary suites.

- [ ] **Step 5: Run the marker-selected `harness` suite**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest -m harness -v
```

Expected: PASS and provide the focused production-hardening Python confidence suite.

- [ ] **Step 6: Commit**

```bash
git add python-agent/tests/conftest.py python-agent/tests/test_guardrails_tools.py python-agent/tests/test_guardrails_output.py python-agent/tests/test_internal_auth_and_concurrency.py python-agent/tests/test_workflow_imports_unittest.py
git commit -m "test: validate deterministic python harness marker suites"
```

---

### Task 6: Document the Harness Contract and Record Evidence

**Files:**
- Modify: `docs/production-hardening-harness.md`
- Modify: `.planning/2026-06-30-production-hardening/progress.md`
- Test: `python-agent/tests/test_guardrails_prompt.py`
- Test: `python-agent/tests/test_guardrails_tools.py`
- Test: `python-agent/tests/test_guardrails_output.py`
- Test: `python-agent/tests/test_internal_auth_and_concurrency.py`
- Test: `python-agent/tests/test_workflow_imports_unittest.py`
- Test: `python-agent/tests/test_tools.py`

- [ ] **Step 1: Update `docs/production-hardening-harness.md` with marker-based execution guidance**

Add this section below the existing Python guardrail focused commands:

```markdown
## Python Deterministic Harness Markers

- `unit`: deterministic pure-python checks such as guardrail rules and config behavior
- `integration`: runtime boundary checks inside `python-agent`, including FastAPI `TestClient`, SSE output wiring, and tool integration
- `harness`: focused production-hardening verification suites used for release-confidence checks

### Unit Command

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest -m unit -v
```

### Integration Command

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest -m integration -v
```

### Canonical Harness Command

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest -m harness -v
```

Expected result: marker-selected deterministic suites pass without requiring Redis, Milvus, or real LLM providers.
```

- [ ] **Step 2: Run the documented canonical harness command exactly as written**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest -m harness -v
```

Expected: PASS.

- [ ] **Step 3: Record area 3 implementation evidence in progress tracking**

Append these bullets to `.planning/2026-06-30-production-hardening/progress.md`:

```markdown
- Route 3 design approved: deterministic Python pytest harness with `unit`, `integration`, and `harness` markers.
- Route 3 implementation completed: pytest marker registration, shared deterministic `conftest.py` helpers, focused suite categorization, and marker-based harness commands.
- Verification: Python deterministic harness marker suites passed: `pytest -m unit -v`, `pytest -m integration -v`, and `pytest -m harness -v`.
```

Replace the final line with the actual observed outcomes once you run the commands.

- [ ] **Step 4: Run the final focused smoke verification**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_guardrails_prompt.py tests/test_guardrails_tools.py tests/test_guardrails_output.py tests/test_internal_auth_and_concurrency.py tests/test_workflow_imports_unittest.py tests/test_tools.py -v
```

Expected: PASS after docs and progress edits.

- [ ] **Step 5: Commit**

```bash
git add docs/production-hardening-harness.md .planning/2026-06-30-production-hardening/progress.md
git commit -m "docs: record deterministic python harness contract"
```

---

## Plan Self-Review

- Spec coverage: marker registration, shared conftest helpers, explicit focused-suite categorization, marker-based commands, documentation, and verification evidence are each covered by dedicated tasks.
- Placeholder scan: no `TODO`, `TBD`, or vague "handle appropriately" steps remain; every task includes file paths, exact commands, and expected outputs.
- Type consistency: the plan consistently uses `unit`, `integration`, and `harness` marker names, a single `conftest.py` helper surface, and the same canonical harness command throughout.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-01-python-deterministic-harness.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
