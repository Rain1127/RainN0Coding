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


def _state(tmp_path, *, mode="new", paths=("src/App.vue",), retry_count=0):
    return {
        "phase": "arch_done",
        "code_gen_type": "vue_project",
        "app_id": "termination-test",
        "mode": mode,
        "retry_count": retry_count,
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


def test_new_mode_retry_does_not_complete_from_preexisting_files(monkeypatch, tmp_path):
    app_file = tmp_path / "src" / "App.vue"
    app_file.parent.mkdir(parents=True)
    app_file.write_text("<template>needs review fix</template>", encoding="utf-8")
    llm = QueuedLLM([
        _tool_response(_tool_call("list_files", {"dir_path": ""}, "list-project")),
        _tool_response(_tool_call("exit_tool", {}, "exit")),
    ])
    _install_coder_dependencies(monkeypatch, llm)

    result = coder_agent(_state(tmp_path, retry_count=1))

    assert result["phase"] == "code_done"
    assert llm.calls == 2
