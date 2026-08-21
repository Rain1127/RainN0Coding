# Coder Agent Deterministic Termination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop new-project Coder runs as soon as every required file is present, and report an error instead of `code_done` when the tool-round limit is exhausted without a valid completion signal.

**Architecture:** Add two small pure helpers to `coder_agent.py`: one checks required-file coverage inside the guarded project directory, and one classifies tool results as failures. The existing ReAct loop tracks a valid termination reason, applies deterministic file coverage only in new mode, and rejects round-limit exhaustion before collecting files. Focused tests drive the change with a fake LLM and the real temporary-directory file tools.

**Tech Stack:** Python 3.12, pytest, LangChain `AIMessage`, existing file tools and guardrails.

---

### Task 1: Add regression tests for deterministic termination

**Files:**
- Create: `python-agent/tests/test_coder_termination.py`
- Test: `python-agent/tests/test_coder_termination.py`

- [ ] **Step 1: Create deterministic test helpers and the early-completion test**

Create `python-agent/tests/test_coder_termination.py` with a queued fake LLM, a shared state factory, and a test whose only model response creates every required file without calling `exit_tool`:

```python
from langchain_core.messages import AIMessage

from agents.coder_agent import coder_agent


class QueuedLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def invoke(self, messages, config=None):
        if self.calls >= len(self.responses):
            raise AssertionError("Coder requested an unnecessary extra LLM round")
        response = self.responses[self.calls]
        self.calls += 1
        return response


def _tool_response(*tool_calls):
    return AIMessage(content="", tool_calls=list(tool_calls))


def _tool_call(name, args, call_id):
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


def _state(tmp_path, *, mode="new", paths=("src/App.vue",)):
    return {
        "phase": "arch_done",
        "code_gen_type": "vue_project",
        "app_id": "termination-test",
        "mode": mode,
        "retry_count": 0,
        "project_dir": str(tmp_path),
        "architecture": {
            "file_list": [{"path": path, "file_type": "source"} for path in paths],
            "component_tree": [],
            "data_flow": [],
            "tech_stack": {},
        },
    }


def _install_coder_dependencies(monkeypatch, llm):
    monkeypatch.setattr("agents.coder_agent.build_rag_context", lambda *args, **kwargs: "")
    monkeypatch.setattr("agents.coder_agent.create_tool_enabled_llm", lambda *args, **kwargs: llm)


def test_new_mode_stops_when_all_required_files_exist(monkeypatch, tmp_path):
    llm = QueuedLLM([
        _tool_response(
            _tool_call(
                "create_file",
                {"path": "src/App.vue", "content": "<template>ready</template>"},
                "create-app",
            )
        )
    ])
    _install_coder_dependencies(monkeypatch, llm)

    result = coder_agent(_state(tmp_path))

    assert result["phase"] == "code_done"
    assert llm.calls == 1
    assert [item["path"] for item in result["code_files"]] == ["src/App.vue"]
```

- [ ] **Step 2: Add the partial-project round-limit regression test**

Append a test that limits the loop to two rounds, creates only one of two required files, and verifies that the current false-success path becomes an explicit missing-file error:

```python
def test_new_mode_errors_when_round_limit_leaves_required_files_missing(monkeypatch, tmp_path):
    llm = QueuedLLM([
        _tool_response(
            _tool_call("create_file", {"path": "src/App.vue", "content": "ready"}, "create-app")
        ),
        _tool_response(_tool_call("list_files", {"dir_path": ""}, "list-project")),
    ])
    _install_coder_dependencies(monkeypatch, llm)
    monkeypatch.setattr("agents.coder_agent.MAX_TOOL_ROUNDS", 2)

    result = coder_agent(_state(tmp_path, paths=("src/App.vue", "src/main.ts")))

    assert result["phase"] == "error"
    assert result["error"] == "Coder Agent 达到工具调用轮数上限，仍缺少目标文件: src/main.ts"
    assert llm.calls == 2
```

- [ ] **Step 3: Add the modify-mode round-limit regression test**

Append a test proving that pre-existing files do not satisfy the new-mode completion predicate in modify mode:

```python
def test_modify_mode_requires_explicit_completion_before_round_limit(monkeypatch, tmp_path):
    app_file = tmp_path / "src" / "App.vue"
    app_file.parent.mkdir(parents=True)
    app_file.write_text("<template>existing</template>", encoding="utf-8")
    llm = QueuedLLM([
        _tool_response(_tool_call("read_file", {"path": "src/App.vue"}, "read-1")),
        _tool_response(_tool_call("read_file", {"path": "src/App.vue"}, "read-2")),
    ])
    _install_coder_dependencies(monkeypatch, llm)
    monkeypatch.setattr("agents.coder_agent.MAX_TOOL_ROUNDS", 2)

    result = coder_agent(_state(tmp_path, mode="modify"))

    assert result["phase"] == "error"
    assert result["error"] == "Coder Agent 达到工具调用轮数上限，修改任务未收到明确完成信号"
    assert llm.calls == 2
```

- [ ] **Step 4: Add the explicit-exit compatibility test**

Before running the RED check, append a regression test that preserves explicit
`exit_tool` completion in modify mode:

```python
def test_modify_mode_explicit_exit_still_completes(monkeypatch, tmp_path):
    app_file = tmp_path / "src" / "App.vue"
    app_file.parent.mkdir(parents=True)
    app_file.write_text("<template>updated</template>", encoding="utf-8")
    llm = QueuedLLM([
        _tool_response(_tool_call("exit_tool", {}, "exit")),
    ])
    _install_coder_dependencies(monkeypatch, llm)

    result = coder_agent(_state(tmp_path, mode="modify"))

    assert result["phase"] == "code_done"
    assert llm.calls == 1
```

- [ ] **Step 5: Run the focused tests and verify RED**

Run from `python-agent`:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_coder_termination.py -q
```

Expected: three tests fail for the intended missing behavior and the explicit
exit regression test passes. The first failing test reports an unnecessary
second LLM round; the other two observe the current false-success behavior
instead of the expected round-limit errors.

### Task 2: Implement deterministic completion and honest round-limit errors

**Files:**
- Modify: `python-agent/agents/coder_agent.py:12-27`
- Modify: `python-agent/agents/coder_agent.py:417-486`
- Test: `python-agent/tests/test_coder_termination.py`

- [ ] **Step 1: Add required-file and tool-result helpers**

Import the existing guarded path resolver and add two helpers above the Agent function:

```python
from tools.path_guard import resolve_project_path


_TOOL_FAILURE_PREFIXES = (
    "guardrail_blocked",
    "未知工具",
    "工具执行失败",
    "错误：",
    "文件写入失败",
    "读取文件失败",
    "修改文件失败",
    "删除文件失败",
    "读取目录失败",
    "权限不足：",
    "警告：文件中未找到",
)


def _tool_result_failed(result: object) -> bool:
    text = str(result).strip()
    return text.startswith(_TOOL_FAILURE_PREFIXES)


def _missing_required_files(project_dir: str, file_list: list[dict]) -> list[str]:
    missing = []
    for file_spec in file_list:
        path = str(file_spec.get("path", "")).strip().replace("\\", "/")
        if not path:
            continue
        try:
            full_path = resolve_project_path(project_dir, path)
        except ValueError:
            missing.append(path)
            continue
        if not os.path.isfile(full_path) or os.path.getsize(full_path) == 0:
            missing.append(path)
    return missing
```

- [ ] **Step 2: Track valid loop termination and per-round tool failure**

Initialize `completed = False` next to `exited`. At the beginning of every tool-call batch initialize `round_had_tool_failure = False`; after each tool result, update it with `_tool_result_failed(tool_result)`.

Preserve explicit exit behavior, but record valid completion:

```python
if exited:
    completed = True
    log_agent_ok("Coder Agent", "收到 exit_tool，结束代码生成循环")
    break
```

After the explicit-exit check, add the new-mode structural completion rule:

```python
if mode != "modify" and not round_had_tool_failure:
    missing_required_files = _missing_required_files(project_dir, file_list)
    if not missing_required_files:
        completed = True
        log_agent_ok(
            "Coder Agent",
            f"目标文件已全部生成，提前结束工具循环，round={round_num}/{MAX_TOOL_ROUNDS}",
        )
        break
```

In the no-tool-call branch, set `completed = True` before the existing direct-output parsing and `break`.

- [ ] **Step 3: Reject exhausted loops before collecting filesystem output**

Immediately after the loop and before `_collect_code_files`, add:

```python
if not completed:
    if mode == "modify":
        error = "Coder Agent 达到工具调用轮数上限，修改任务未收到明确完成信号"
    else:
        missing_required_files = _missing_required_files(project_dir, file_list)
        if missing_required_files:
            error = (
                "Coder Agent 达到工具调用轮数上限，仍缺少目标文件: "
                + ", ".join(missing_required_files)
            )
        else:
            error = "Coder Agent 达到工具调用轮数上限，工具失败导致任务未正常完成"
    state["error"] = error
    state["phase"] = "error"
    log_agent_fail("Coder Agent", error)
    return state
```

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_coder_termination.py -q
```

Expected: `4 passed`.

- [ ] **Step 5: Run existing Coder log tests**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_agent_logs.py -q
```

Expected: all tests pass; direct JSON completion logs remain unchanged.

### Task 3: Regression verification and implementation commit

**Files:**
- Modify: `python-agent/agents/coder_agent.py`
- Create: `python-agent/tests/test_coder_termination.py`

- [ ] **Step 1: Run the Python Agent regression suite**

Run from `python-agent` with the repository on `PYTHONPATH`:

```powershell
$env:PYTHONPATH = (Get-Location).Path
& '.\.venv\Scripts\python.exe' -m pytest tests -q
```

Expected: exit code 0 with no failed tests. Tests requiring unavailable external services may remain explicitly skipped, but no new failure is acceptable.

- [ ] **Step 2: Inspect only the intended implementation diff**

Run:

```powershell
git diff --check -- agents/coder_agent.py tests/test_coder_termination.py
git diff -- agents/coder_agent.py tests/test_coder_termination.py
```

Expected: only deterministic termination, honest exhaustion errors, and their focused tests appear.

- [ ] **Step 3: Commit only the implementation files**

Run from `python-agent`:

```powershell
git add -- agents/coder_agent.py tests/test_coder_termination.py
git diff --cached --check
git commit -m "fix: terminate coder when required files are complete"
```

Expected: one implementation commit containing exactly two files. Existing unrelated root worktree changes remain unstaged.

- [ ] **Step 4: Perform manual runtime acceptance after restart**

Stop and restart the PyCharm Python process after the current generation is finished. Submit one new small project and verify the logs contain either:

```text
[Coder Agent] OK 目标文件已全部生成，提前结束工具循环，round=N/20
```

or a legitimate explicit `exit_tool` completion before round 20. Confirm Reviewer and Builder continue normally. If the architecture requires more than 20 rounds and files remain missing, verify the request reports the missing-file error instead of `code_done`.
