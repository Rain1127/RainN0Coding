# Agent Guardrails Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a centralized Python guardrail engine that protects the `/api/generate-code` entry chain, the coder file-tool chain, and risky output events with graded `allow / warn / block` enforcement.

**Architecture:** Add a dedicated `python-agent/guardrails/` package with shared models, policy defaults, audit logging, and a single evaluation engine. Wire that engine into `server/main.py`, `workflow/sse_stream.py`, and the file tools so prompt, tool, and output decisions all use the same result shape and rule IDs.

**Tech Stack:** FastAPI, Pydantic, asyncio, pytest, existing LangChain tool wrappers, existing Python agent runtime modules under `python-agent/`.

---

## File Structure

- Create `python-agent/guardrails/models.py`: shared `GuardrailDecision`, `PromptContext`, `ToolAction`, `OutputEvent`, and `GuardrailAuditRecord` models.
- Create `python-agent/guardrails/policy.py`: severity/action enums, protected file patterns, allowed extension sets, and configurable threshold helpers.
- Create `python-agent/guardrails/audit.py`: structured audit logger helper used by all guardrail paths.
- Create `python-agent/guardrails/prompt_guard.py`: prompt and request-metadata checks.
- Create `python-agent/guardrails/tool_guard.py`: tool-action checks before filesystem access.
- Create `python-agent/guardrails/output_guard.py`: `code_file` and other risky event checks.
- Create `python-agent/guardrails/engine.py`: centralized facade with `evaluate_prompt`, `evaluate_tool_action`, and `evaluate_output_event`.
- Create `python-agent/guardrails/__init__.py`: re-export stable public API for imports.
- Modify `python-agent/config.py`: add guardrail configuration values.
- Modify `python-agent/server/main.py`: run prompt guard before workflow start and return structured block responses.
- Modify `python-agent/workflow/sse_stream.py`: run output guard before forwarding risky events.
- Modify `python-agent/tools/create_file.py`: call centralized tool guard before filesystem write.
- Modify `python-agent/tools/read_file.py`: call centralized tool guard before filesystem read.
- Modify `python-agent/tools/modify_file.py`: call centralized tool guard before replacement.
- Modify `python-agent/tools/delete_file.py`: remove local ad hoc protection logic and call centralized tool guard.
- Modify `python-agent/tools/list_files.py`: call centralized tool guard before wide directory traversal.
- Create `python-agent/tests/test_guardrails_prompt.py`: focused prompt-guard tests.
- Create `python-agent/tests/test_guardrails_tools.py`: focused tool-guard and tool-wiring tests.
- Create `python-agent/tests/test_guardrails_output.py`: focused output-guard tests.
- Modify `docs/production-hardening-harness.md`: add the new focused guardrail test commands.
- Modify `.planning/2026-06-30-production-hardening/progress.md`: record route 2 implementation and verification evidence.

---

### Task 1: Add Guardrail Config and Shared Models

**Files:**
- Modify: `python-agent/config.py`
- Create: `python-agent/guardrails/models.py`
- Create: `python-agent/guardrails/policy.py`
- Create: `python-agent/guardrails/__init__.py`
- Test: `python-agent/tests/test_guardrails_prompt.py`

- [ ] **Step 1: Write the failing shared-model and config tests**

```python
import importlib


def test_guardrail_config_defaults(monkeypatch):
    monkeypatch.delenv("GUARDRAILS_ENABLED", raising=False)
    monkeypatch.delenv("GUARDRAILS_AUDIT_LOW_RISK", raising=False)
    monkeypatch.delenv("GUARDRAILS_MAX_PROMPT_CHARS", raising=False)
    monkeypatch.delenv("GUARDRAILS_MAX_FILE_WRITE_BYTES", raising=False)
    monkeypatch.delenv("GUARDRAILS_MAX_MODIFY_REPLACEMENT_BYTES", raising=False)
    monkeypatch.delenv("GUARDRAILS_MAX_LIST_FILES_DEPTH", raising=False)

    import config as config_module

    importlib.reload(config_module)
    cfg = config_module.config

    assert cfg.GUARDRAILS_ENABLED is True
    assert cfg.GUARDRAILS_AUDIT_LOW_RISK is False
    assert cfg.GUARDRAILS_MAX_PROMPT_CHARS == 12000
    assert cfg.GUARDRAILS_MAX_FILE_WRITE_BYTES == 200_000
    assert cfg.GUARDRAILS_MAX_MODIFY_REPLACEMENT_BYTES == 120_000
    assert cfg.GUARDRAILS_MAX_LIST_FILES_DEPTH == 6


def test_guardrail_decision_shape():
    from guardrails.models import GuardrailDecision

    decision = GuardrailDecision.allow("prompt.ok", {"source": "test"})

    assert decision.action == "allow"
    assert decision.severity == "low"
    assert decision.rule_id == "prompt.ok"
    assert decision.details == {"source": "test"}
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_guardrails_prompt.py -v
```

Expected: import or attribute failures because the guardrail config and models do not exist yet.

- [ ] **Step 3: Add guardrail config to `config.py`**

```python
    GUARDRAILS_ENABLED: bool = os.getenv("GUARDRAILS_ENABLED", "true").lower() == "true"
    GUARDRAILS_AUDIT_LOW_RISK: bool = os.getenv("GUARDRAILS_AUDIT_LOW_RISK", "false").lower() == "true"
    GUARDRAILS_MAX_PROMPT_CHARS: int = int(os.getenv("GUARDRAILS_MAX_PROMPT_CHARS", "12000"))
    GUARDRAILS_MAX_FILE_WRITE_BYTES: int = int(os.getenv("GUARDRAILS_MAX_FILE_WRITE_BYTES", "200000"))
    GUARDRAILS_MAX_MODIFY_REPLACEMENT_BYTES: int = int(
        os.getenv("GUARDRAILS_MAX_MODIFY_REPLACEMENT_BYTES", "120000")
    )
    GUARDRAILS_MAX_LIST_FILES_DEPTH: int = int(os.getenv("GUARDRAILS_MAX_LIST_FILES_DEPTH", "6"))
```

- [ ] **Step 4: Add the shared guardrail models**

Create `python-agent/guardrails/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class GuardrailDecision:
    action: str
    severity: str
    rule_id: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def allow(cls, rule_id: str, details: dict[str, Any] | None = None) -> "GuardrailDecision":
        return cls("allow", "low", rule_id, "allowed", details or {})

    @classmethod
    def warn(
        cls, rule_id: str, message: str, details: dict[str, Any] | None = None
    ) -> "GuardrailDecision":
        return cls("warn", "medium", rule_id, message, details or {})

    @classmethod
    def block(
        cls, rule_id: str, message: str, details: dict[str, Any] | None = None
    ) -> "GuardrailDecision":
        return cls("block", "high", rule_id, message, details or {})


@dataclass(slots=True)
class PromptContext:
    prompt: str
    request_id: str
    trace_id: str
    user_id: str
    app_id: str
    history: list[Any] = field(default_factory=list)


@dataclass(slots=True)
class ToolAction:
    tool_name: str
    project_dir: str
    relative_path: str = ""
    content: str = ""
    old_content: str = ""
    new_content: str = ""
    dir_path: str = ""
    user_role: str = "user"


@dataclass(slots=True)
class OutputEvent:
    event_type: str
    path: str = ""
    content: str = ""
    request_id: str = ""
    trace_id: str = ""


@dataclass(slots=True)
class GuardrailAuditRecord:
    rule_id: str
    action: str
    severity: str
    message: str
    request_id: str = ""
    trace_id: str = ""
    user_id: str = ""
    app_id: str = ""
    tool_name: str = ""
    path: str = ""
    details: dict[str, Any] = field(default_factory=dict)
```

- [ ] **Step 5: Add the shared policy constants**

Create `python-agent/guardrails/policy.py`:

```python
from __future__ import annotations

from config import config

PROTECTED_FILE_NAMES = {
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "pyproject.toml",
    "pom.xml",
    "vite.config.js",
    "vite.config.ts",
    "main.ts",
    "main.js",
    "App.vue",
}

SENSITIVE_FILE_MARKERS = {
    ".env",
    ".pem",
    ".key",
    ".p12",
    "id_rsa",
    "id_ed25519",
    ".ssh",
}

ALLOWED_WRITE_EXTENSIONS = {
    ".vue",
    ".ts",
    ".js",
    ".tsx",
    ".jsx",
    ".json",
    ".css",
    ".scss",
    ".md",
    ".html",
    ".py",
    ".java",
    ".go",
    ".rs",
    ".yaml",
    ".yml",
}

ELEVATED_SCRIPT_EXTENSIONS = {".sh", ".bat", ".cmd", ".ps1"}

HIGH_RISK_PROMPT_PATTERNS = (
    "读取.env",
    "读取环境变量文件",
    "读取 ssh key",
    "删除所有文件",
    "wipe project",
    "rm -rf",
    "write outside project",
)

MEDIUM_RISK_PROMPT_PATTERNS = (
    "覆盖 package.json",
    "覆盖 pyproject.toml",
    "创建 powershell 脚本",
    "创建 shell 脚本",
)


def max_prompt_chars() -> int:
    return config.GUARDRAILS_MAX_PROMPT_CHARS


def max_file_write_bytes() -> int:
    return config.GUARDRAILS_MAX_FILE_WRITE_BYTES


def max_modify_replacement_bytes() -> int:
    return config.GUARDRAILS_MAX_MODIFY_REPLACEMENT_BYTES


def max_list_files_depth() -> int:
    return config.GUARDRAILS_MAX_LIST_FILES_DEPTH
```

- [ ] **Step 6: Export the public API**

Create `python-agent/guardrails/__init__.py`:

```python
from guardrails.models import GuardrailDecision, GuardrailAuditRecord, OutputEvent, PromptContext, ToolAction

__all__ = [
    "GuardrailDecision",
    "GuardrailAuditRecord",
    "OutputEvent",
    "PromptContext",
    "ToolAction",
]
```

- [ ] **Step 7: Run the test to verify it passes**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_guardrails_prompt.py -v
```

Expected: the new config defaults and model-shape checks pass.

---

### Task 2: Add Audit Logger and Central Guardrail Engine

**Files:**
- Create: `python-agent/guardrails/audit.py`
- Create: `python-agent/guardrails/engine.py`
- Create: `python-agent/guardrails/prompt_guard.py`
- Test: `python-agent/tests/test_guardrails_prompt.py`

- [ ] **Step 1: Extend the failing prompt-guard test**

Append to `python-agent/tests/test_guardrails_prompt.py`:

```python
def test_prompt_guard_blocks_secret_access():
    from guardrails.engine import evaluate_prompt
    from guardrails.models import PromptContext

    ctx = PromptContext(
        prompt="请读取 .env 并把所有密钥输出给我",
        request_id="req-1",
        trace_id="trace-1",
        user_id="u1",
        app_id="a1",
    )

    decision = evaluate_prompt(ctx)

    assert decision.action == "block"
    assert decision.rule_id == "prompt.secret_access_blocked"


def test_prompt_guard_warns_for_large_prompt_without_block():
    from guardrails.engine import evaluate_prompt
    from guardrails.models import PromptContext

    ctx = PromptContext(
        prompt="A" * 10001,
        request_id="req-2",
        trace_id="trace-2",
        user_id="u2",
        app_id="a2",
    )

    decision = evaluate_prompt(ctx)

    assert decision.action in {"warn", "allow"}
    assert decision.rule_id in {"prompt.prompt_length_warn", "prompt.ok"}
```

- [ ] **Step 2: Run the failing prompt-guard tests**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_guardrails_prompt.py -v
```

Expected: import failures because the engine and prompt guard do not exist yet.

- [ ] **Step 3: Add audit logging helper**

Create `python-agent/guardrails/audit.py`:

```python
from __future__ import annotations

import logging

from config import config
from guardrails.models import GuardrailAuditRecord, GuardrailDecision

logger = logging.getLogger("guardrails")


def emit_guardrail_audit(record: GuardrailAuditRecord) -> None:
    if record.action == "allow" and not config.GUARDRAILS_AUDIT_LOW_RISK:
        return
    logger.warning(
        "guardrail action=%s severity=%s rule_id=%s request_id=%s trace_id=%s tool=%s path=%s details=%s",
        record.action,
        record.severity,
        record.rule_id,
        record.request_id,
        record.trace_id,
        record.tool_name,
        record.path,
        record.details,
    )


def audit_from_decision(
    decision: GuardrailDecision,
    *,
    request_id: str = "",
    trace_id: str = "",
    user_id: str = "",
    app_id: str = "",
    tool_name: str = "",
    path: str = "",
) -> None:
    emit_guardrail_audit(
        GuardrailAuditRecord(
            rule_id=decision.rule_id,
            action=decision.action,
            severity=decision.severity,
            message=decision.message,
            request_id=request_id,
            trace_id=trace_id,
            user_id=user_id,
            app_id=app_id,
            tool_name=tool_name,
            path=path,
            details=decision.details,
        )
    )
```

- [ ] **Step 4: Add prompt evaluation logic**

Create `python-agent/guardrails/prompt_guard.py`:

```python
from __future__ import annotations

from guardrails.models import GuardrailDecision, PromptContext
from guardrails.policy import HIGH_RISK_PROMPT_PATTERNS, MEDIUM_RISK_PROMPT_PATTERNS, max_prompt_chars


def evaluate_prompt_context(ctx: PromptContext) -> GuardrailDecision:
    lowered = ctx.prompt.lower()

    for pattern in HIGH_RISK_PROMPT_PATTERNS:
        if pattern.lower() in lowered:
            return GuardrailDecision.block(
                "prompt.secret_access_blocked" if ".env" in pattern or "key" in pattern.lower() else "prompt.path_escape_blocked",
                "prompt requested a blocked operation",
                {"matched_pattern": pattern},
            )

    for pattern in MEDIUM_RISK_PROMPT_PATTERNS:
        if pattern.lower() in lowered:
            return GuardrailDecision.warn(
                "prompt.protected_file_warn",
                "prompt requested a high-impact change",
                {"matched_pattern": pattern},
            )

    if len(ctx.prompt) > max_prompt_chars():
        return GuardrailDecision.warn(
            "prompt.prompt_length_warn",
            "prompt is unusually large",
            {"prompt_length": len(ctx.prompt)},
        )

    return GuardrailDecision.allow("prompt.ok", {"prompt_length": len(ctx.prompt)})
```

- [ ] **Step 5: Add centralized engine facade**

Create `python-agent/guardrails/engine.py`:

```python
from __future__ import annotations

from guardrails.models import GuardrailDecision, OutputEvent, PromptContext, ToolAction
from guardrails.prompt_guard import evaluate_prompt_context


def evaluate_prompt(ctx: PromptContext) -> GuardrailDecision:
    return evaluate_prompt_context(ctx)


def evaluate_tool_action(action: ToolAction) -> GuardrailDecision:
    raise NotImplementedError("tool guard not implemented yet")


def evaluate_output_event(event: OutputEvent) -> GuardrailDecision:
    raise NotImplementedError("output guard not implemented yet")
```

- [ ] **Step 6: Run the prompt-guard tests**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_guardrails_prompt.py -v
```

Expected: prompt tests pass, while the tool/output placeholders remain untouched.

---

### Task 3: Add Tool Guardrails and Wire Them Into File Tools

**Files:**
- Create: `python-agent/guardrails/tool_guard.py`
- Modify: `python-agent/guardrails/engine.py`
- Modify: `python-agent/tools/create_file.py`
- Modify: `python-agent/tools/read_file.py`
- Modify: `python-agent/tools/modify_file.py`
- Modify: `python-agent/tools/delete_file.py`
- Modify: `python-agent/tools/list_files.py`
- Test: `python-agent/tests/test_guardrails_tools.py`

- [ ] **Step 1: Write the failing tool-guard tests**

Create `python-agent/tests/test_guardrails_tools.py`:

```python
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools import create_file, delete_file, modify_file, read_file, set_tool_context


def test_create_file_blocks_project_escape():
    with tempfile.TemporaryDirectory() as tmpdir:
        set_tool_context(tmpdir, "app-1", "user")
        result = create_file.invoke({"path": "../escape.txt", "content": "bad"})
        assert "guardrail_blocked" in result


def test_delete_file_blocks_protected_package_json_for_admin():
    with tempfile.TemporaryDirectory() as tmpdir:
        set_tool_context(tmpdir, "app-2", "admin")
        create_file.invoke({"path": "package.json", "content": "{}"})
        result = delete_file.invoke({"path": "package.json"})
        assert "guardrail_blocked" in result


def test_modify_file_warns_for_entrypoint_change_but_continues():
    with tempfile.TemporaryDirectory() as tmpdir:
        set_tool_context(tmpdir, "app-3", "user")
        create_file.invoke({"path": "src/main.ts", "content": "console.log('a')"})
        result = modify_file.invoke(
            {
                "path": "src/main.ts",
                "old_content": "console.log('a')",
                "new_content": "console.log('b')",
            }
        )
        assert "文件修改成功" in result
        content = read_file.invoke({"path": "src/main.ts"})
        assert "console.log('b')" in content
```

- [ ] **Step 2: Run the failing tool-guard tests**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_guardrails_tools.py -v
```

Expected: tests fail because the centralized tool-guard logic does not exist yet.

- [ ] **Step 3: Add the tool-guard evaluator**

Create `python-agent/guardrails/tool_guard.py`:

```python
from __future__ import annotations

import os

from guardrails.models import GuardrailDecision, ToolAction
from guardrails.policy import (
    ALLOWED_WRITE_EXTENSIONS,
    ELEVATED_SCRIPT_EXTENSIONS,
    PROTECTED_FILE_NAMES,
    SENSITIVE_FILE_MARKERS,
    max_file_write_bytes,
    max_list_files_depth,
    max_modify_replacement_bytes,
)


def evaluate_tool_action_context(action: ToolAction) -> GuardrailDecision:
    target = action.relative_path or action.dir_path
    target_name = os.path.basename(target)
    target_lower = target.lower()

    if ".." in target.replace("\\", "/").split("/"):
        return GuardrailDecision.block(
            "tool.path_escape_blocked",
            "tool action attempted to escape the project root",
            {"path": target},
        )

    if any(marker in target_lower for marker in SENSITIVE_FILE_MARKERS):
        return GuardrailDecision.block(
            "tool.sensitive_file_blocked",
            "tool action targeted a sensitive file",
            {"path": target},
        )

    if action.tool_name == "delete_file" and target_name in PROTECTED_FILE_NAMES:
        return GuardrailDecision.block(
            "tool.delete_protected_file_blocked",
            "tool action attempted to delete a protected file",
            {"path": target},
        )

    _, ext = os.path.splitext(target_name)
    if action.tool_name in {"create_file", "modify_file"} and ext and ext.lower() not in ALLOWED_WRITE_EXTENSIONS | ELEVATED_SCRIPT_EXTENSIONS:
        return GuardrailDecision.block(
            "tool.extension_blocked",
            "tool action targeted a disallowed file extension",
            {"path": target, "extension": ext.lower()},
        )

    if action.tool_name == "create_file" and len(action.content.encode("utf-8")) > max_file_write_bytes():
        return GuardrailDecision.block(
            "tool.write_too_large_blocked",
            "tool write content exceeded the configured limit",
            {"path": target},
        )

    if action.tool_name == "modify_file" and len(action.new_content.encode("utf-8")) > max_modify_replacement_bytes():
        return GuardrailDecision.block(
            "tool.modify_too_large_blocked",
            "tool modification exceeded the configured limit",
            {"path": target},
        )

    if action.tool_name == "modify_file" and target_name in PROTECTED_FILE_NAMES:
        return GuardrailDecision.warn(
            "tool.modify_entrypoint_warn",
            "tool action modified a protected entry file",
            {"path": target},
        )

    if action.tool_name == "create_file" and ext.lower() in ELEVATED_SCRIPT_EXTENSIONS:
        return GuardrailDecision.warn(
            "tool.create_script_warn",
            "tool action created an executable script",
            {"path": target},
        )

    if action.tool_name == "list_files":
        depth = len([part for part in action.dir_path.replace("\\", "/").split("/") if part])
        if depth > max_list_files_depth():
            return GuardrailDecision.block(
                "tool.list_depth_blocked",
                "tool directory traversal depth exceeded the configured limit",
                {"dir_path": action.dir_path, "depth": depth},
            )

    return GuardrailDecision.allow("tool.ok", {"tool_name": action.tool_name, "path": target})
```

- [ ] **Step 4: Connect the engine to the tool guard**

Replace the placeholder in `python-agent/guardrails/engine.py`:

```python
from guardrails.tool_guard import evaluate_tool_action_context


def evaluate_tool_action(action: ToolAction) -> GuardrailDecision:
    return evaluate_tool_action_context(action)
```

- [ ] **Step 5: Wire each tool through the centralized decision path**

Use this pattern in each tool:

```python
from guardrails.audit import audit_from_decision
from guardrails.engine import evaluate_tool_action
from guardrails.models import ToolAction

decision = evaluate_tool_action(
    ToolAction(
        tool_name="create_file",
        project_dir=project_dir,
        relative_path=path,
        content=content,
        user_role=get_user_role(),
    )
)
audit_from_decision(decision, tool_name="create_file", path=path)
if decision.action == "block":
    return f"guardrail_blocked:{decision.rule_id}:{decision.message}"
```

Specific requirements:

- `delete_file.py`
  Remove `_PROTECTED_FILES` and let the centralized guard decide.
- `read_file.py` and `list_files.py`
  Add guard checks even though they do not mutate state.
- `modify_file.py`
  Evaluate guard before reading and replacing content.

- [ ] **Step 6: Run the tool-guard test file**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_guardrails_tools.py -v
```

Expected: the block and warn scenarios pass through the centralized tool guard.

---

### Task 4: Add Output Guardrails and Wire Them Into SSE Event Forwarding

**Files:**
- Create: `python-agent/guardrails/output_guard.py`
- Modify: `python-agent/guardrails/engine.py`
- Modify: `python-agent/workflow/sse_stream.py`
- Test: `python-agent/tests/test_guardrails_output.py`

- [ ] **Step 1: Write the failing output-guard tests**

Create `python-agent/tests/test_guardrails_output.py`:

```python
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_output_guard_blocks_protected_path_code_file():
    from guardrails.engine import evaluate_output_event
    from guardrails.models import OutputEvent

    decision = evaluate_output_event(
        OutputEvent(event_type="code_file", path=".env", content="SECRET=1", request_id="req-1", trace_id="trace-1")
    )

    assert decision.action == "block"
    assert decision.rule_id == "output.protected_path_blocked"


def test_output_guard_blocks_oversize_code_file(monkeypatch):
    from guardrails.engine import evaluate_output_event
    from guardrails.models import OutputEvent

    decision = evaluate_output_event(
        OutputEvent(
            event_type="code_file",
            path="src/App.vue",
            content="A" * 250000,
            request_id="req-2",
            trace_id="trace-2",
        )
    )

    assert decision.action == "block"
    assert decision.rule_id == "output.oversize_code_file_blocked"
```

- [ ] **Step 2: Run the failing output-guard tests**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_guardrails_output.py -v
```

Expected: import failures because the output guard does not exist yet.

- [ ] **Step 3: Add output-guard evaluator**

Create `python-agent/guardrails/output_guard.py`:

```python
from __future__ import annotations

import os

from guardrails.models import GuardrailDecision, OutputEvent
from guardrails.policy import PROTECTED_FILE_NAMES, SENSITIVE_FILE_MARKERS, max_file_write_bytes


def evaluate_output_event_context(event: OutputEvent) -> GuardrailDecision:
    if event.event_type != "code_file":
        return GuardrailDecision.allow("output.ok", {"event_type": event.event_type})

    path_lower = event.path.lower()
    target_name = os.path.basename(event.path)

    if any(marker in path_lower for marker in SENSITIVE_FILE_MARKERS) or target_name in PROTECTED_FILE_NAMES:
        return GuardrailDecision.block(
            "output.protected_path_blocked",
            "generated output targeted a protected or sensitive path",
            {"path": event.path},
        )

    if len(event.content.encode("utf-8")) > max_file_write_bytes():
        return GuardrailDecision.block(
            "output.oversize_code_file_blocked",
            "generated output exceeded the configured size limit",
            {"path": event.path},
        )

    return GuardrailDecision.allow("output.ok", {"path": event.path})
```

- [ ] **Step 4: Connect the engine to the output guard**

Replace the placeholder in `python-agent/guardrails/engine.py`:

```python
from guardrails.output_guard import evaluate_output_event_context


def evaluate_output_event(event: OutputEvent) -> GuardrailDecision:
    return evaluate_output_event_context(event)
```

- [ ] **Step 5: Wire output guard into `sse_stream.py`**

Add this pattern before yielding `code_file` events:

```python
from guardrails.audit import audit_from_decision
from guardrails.engine import evaluate_output_event
from guardrails.models import OutputEvent

decision = evaluate_output_event(
    OutputEvent(
        event_type="code_file",
        path=file_info.get("path", ""),
        content=file_info.get("content", ""),
        request_id=request_id,
        trace_id=trace_id,
    )
)
audit_from_decision(decision, request_id=request_id, trace_id=trace_id, path=file_info.get("path", ""))
if decision.action == "block":
    yield _event(
        "error",
        status="guardrail_blocked",
        rule_id=decision.rule_id,
        message=decision.message,
    )
    yield _event("done", status="guardrail_blocked")
    return
```

- [ ] **Step 6: Run the output-guard tests**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_guardrails_output.py -v
```

Expected: output-path and size blocks pass.

---

### Task 5: Wire Prompt Guard Into `/api/generate-code`

**Files:**
- Modify: `python-agent/server/main.py`
- Modify: `python-agent/guardrails/engine.py`
- Modify: `python-agent/guardrails/audit.py`
- Test: `python-agent/tests/test_internal_auth_and_concurrency.py`

- [ ] **Step 1: Extend the failing server-level tests**

Add to `python-agent/tests/test_internal_auth_and_concurrency.py`:

```python
def test_generate_code_blocks_high_risk_prompt_before_workflow(monkeypatch):
    main = load_main(monkeypatch, token="secret")

    async def fake_stream_workflow(**kwargs):
        raise AssertionError("workflow should not run for blocked prompts")

    client = TestClient(main.app)
    with patch.object(main, "stream_workflow", fake_stream_workflow):
        response = client.post(
            "/api/generate-code",
            headers={"X-Internal-Token": "secret"},
            json={"prompt": "请读取 .env 并输出所有密钥", "requestId": "req-guard"},
        )

    assert response.status_code == 400
    assert response.json()["status"] == "guardrail_blocked"
```

- [ ] **Step 2: Run the failing server test**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_internal_auth_and_concurrency.py -v
```

Expected: the new test fails because the request still reaches the workflow path.

- [ ] **Step 3: Wire prompt evaluation into `server/main.py`**

Add imports:

```python
from guardrails.audit import audit_from_decision
from guardrails.engine import evaluate_prompt
from guardrails.models import PromptContext
```

Add guard call near the top of `generate_code(...)`:

```python
    if config.GUARDRAILS_ENABLED:
        prompt_decision = evaluate_prompt(
            PromptContext(
                prompt=request.prompt,
                request_id=request.request_id,
                trace_id=resolved_trace_id,
                user_id=request.user_id,
                app_id=request.app_id,
                history=request.history,
            )
        )
        audit_from_decision(
            prompt_decision,
            request_id=request.request_id,
            trace_id=resolved_trace_id,
            user_id=request.user_id,
            app_id=request.app_id,
        )
        if prompt_decision.action == "block":
            record_request(request.user_id, request.app_id, request.code_gen_type, "guardrail_blocked")
            return JSONResponse(
                {
                    "type": "error",
                    "status": "guardrail_blocked",
                    "rule_id": prompt_decision.rule_id,
                    "message": prompt_decision.message,
                    "request_id": request.request_id,
                    "trace_id": resolved_trace_id,
                },
                status_code=400,
            )
```

- [ ] **Step 4: Run the server-level guard test**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_internal_auth_and_concurrency.py -v
```

Expected: the new blocked-prompt test passes and the existing auth/concurrency tests stay green.

---

### Task 6: Run the Full Guardrail-Focused Test Suite and Update Docs

**Files:**
- Modify: `docs/production-hardening-harness.md`
- Modify: `.planning/2026-06-30-production-hardening/progress.md`
- Test: `python-agent/tests/test_guardrails_prompt.py`
- Test: `python-agent/tests/test_guardrails_tools.py`
- Test: `python-agent/tests/test_guardrails_output.py`
- Test: `python-agent/tests/test_internal_auth_and_concurrency.py`

- [ ] **Step 1: Update the harness documentation**

Append to `docs/production-hardening-harness.md`:

```markdown
## Python Guardrail Focused Tests

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_guardrails_prompt.py tests/test_guardrails_tools.py tests/test_guardrails_output.py tests/test_internal_auth_and_concurrency.py tests/test_workflow_imports_unittest.py -v
```

Expected result: prompt blocks, tool guards, output guards, and server-level guardrail wiring all pass without real model calls.
```
```

- [ ] **Step 2: Run the focused guardrail suite**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_guardrails_prompt.py tests/test_guardrails_tools.py tests/test_guardrails_output.py tests/test_internal_auth_and_concurrency.py tests/test_workflow_imports_unittest.py -v
```

Expected: all focused guardrail and existing auth/concurrency tests pass.

- [ ] **Step 3: Update progress tracking**

Append to `.planning/2026-06-30-production-hardening/progress.md`:

```markdown
- Route 2 design approved: centralized Python guardrail engine with prompt, tool, and output protection.
- Route 2 implementation completed: prompt guard, tool guard, output guard, centralized audit decisions, and focused guardrail tests.
- Verification: Python guardrail focused suite result: <actual result>.
```

- [ ] **Step 4: Run a final smoke verification**

Run:

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_guardrails_prompt.py tests/test_guardrails_tools.py tests/test_guardrails_output.py -v
```

Expected: quick smoke remains green after docs/progress edits.

---

## Plan Self-Review

- Spec coverage: prompt guard, tool guard, output guard, centralized engine, audit logging, focused tests, and server/workflow/tool integration are all covered by explicit tasks.
- Placeholder scan: no `TODO`, `TBD`, or “handle appropriately” placeholders remain; each task includes paths, commands, and code.
- Type consistency: `GuardrailDecision`, `PromptContext`, `ToolAction`, `OutputEvent`, `evaluate_prompt`, `evaluate_tool_action`, and `evaluate_output_event` are named consistently across tasks.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-01-agent-guardrails.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
