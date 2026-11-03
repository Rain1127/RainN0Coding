"""Offline regressions for defects observed in the paid full-workflow A/B."""
import asyncio
import importlib
import json

import pytest
from langchain_core.messages import AIMessage

from workflow.resilience import (
    apply_architect_fallback, finalize_state, guarded_phase_call,
)


@pytest.mark.parametrize("returned", [
    {"phase": "error", "error": "budget exhausted"},
    {"phase": "error"},
    {"phase": "code_done", "error": "provider failed"},
])
def test_returned_agent_error_is_not_a_good_phase(returned):
    async def coder(state):
        return {**state, **returned}

    result = asyncio.run(guarded_phase_call("coder", {
        "phase": "arch_done", "last_good_phase": "architect",
    }, coder))

    assert result["phase"] == "error"
    assert result.get("error"), "SSE must receive an error even when the Agent omitted the message"
    assert result["failed_phase"] == "coder"
    assert result["last_good_phase"] == "architect"
    assert result["phase_failures"][-1]["error_type"] == "agent_error"
    assert finalize_state(result)["final_result"]["status"] == "failed"


def test_downstream_runner_does_not_overwrite_original_failure():
    async def reviewer(state):
        pytest.fail("Reviewer must not run after a terminal Coder error")

    result = asyncio.run(guarded_phase_call("reviewer", {
        "phase": "error", "error": "coder failed", "failed_phase": "coder",
        "last_good_phase": "architect", "phase_failures": [],
    }, reviewer))

    assert result["failed_phase"] == "coder"
    assert result["last_good_phase"] == "architect"


@pytest.mark.parametrize("signal, expected_phase", [
    ({"phase": "error", "error": "budget exhausted"}, None),
    ({"phase": "completed", "error": "budget exhausted"}, None),
    ({"phase": "error"}, None),
    ({"phase": "build_done", "build_result": {"success": False}}, "builder"),
    ({"phase": "build_done", "quality_gate_result": {"passed": False}}, "builder"),
    ({"phase": "review_done", "review": {"passed": False}}, "reviewer"),
])
@pytest.mark.parametrize("with_code", [False, True])
def test_finalizer_does_not_hide_unsuccessful_outcomes(signal, expected_phase, with_code):
    state = {"code_gen_type": "html", **signal}
    if with_code:
        state["code_files"] = [{"path": "index.html", "content": "<html>draft</html>"}]
    final = finalize_state(state)["final_result"]
    assert final["status"] == ("partial_success" if with_code else "failed")
    if expected_phase:
        assert final["failed_phase"] == expected_phase


def test_empty_vue_file_is_not_usable_partial_code():
    result = finalize_state({
        "phase": "error", "failed_phase": "coder", "code_gen_type": "vue_project",
        "code_files": [{"path": "src/App.vue", "content": ""}],
    })
    assert result["final_status"] == "failed"
    assert result["partial_code_available"] is False


def test_metadata_only_is_not_usable_partial_code():
    result = finalize_state({
        "phase": "error", "failed_phase": "coder", "code_gen_type": "html",
        "code_files": [{"path": "architecture.json", "content": "{}"},
                       {"path": "prd.json", "content": "{}"}],
    })
    assert result["final_status"] == "failed"
    assert result["partial_code_available"] is False


@pytest.mark.parametrize("state, expected", [
    ({"phase": "clarify"}, "success"),
    ({"phase": "build_done", "build_result": {"success": True},
      "quality_gate_result": {"passed": True}, "review": {"passed": True}}, "success"),
    ({"phase": "build_done", "degraded": True, "failed_phase": "pm",
      "code_gen_type": "html", "code_files": [{"path": "index.html", "content": "ok"}]},
     "degraded_success"),
])
def test_existing_success_and_clarification_semantics_are_preserved(state, expected):
    assert finalize_state(state)["final_status"] == expected


@pytest.mark.parametrize("kind, required", [
    ("vue_project", "CSS:"), ("java", "component_tree 表示模块"),
    ("html", "index.html"),
])
def test_architect_receives_complete_design_rules(kind, required):
    from agents.architect_agent import _build_arch_prompt
    prompt = _build_arch_prompt(kind)
    assert "## 设计规则" in prompt
    assert required in prompt
    if kind == "html":
        assert "App.vue" not in prompt
        assert "内联" in prompt


def test_html_config_and_coder_prompt_declare_entry():
    from config import get_lang_config
    from agents.coder_agent import _build_coder_prompt
    assert get_lang_config("html")["entry"] == "index.html"
    assert "index.html" in _build_coder_prompt("html")


def test_architect_html_fallback_uses_root_entry():
    result = apply_architect_fallback({"code_gen_type": "html"}, "architect_timeout")
    assert result["architecture"]["file_list"][0]["path"] == "index.html"


@pytest.mark.parametrize("entry, expected", [("src/index.html", "error"), ("index.html", "arch_done")])
def test_architect_validates_entry_before_persisting(monkeypatch, tmp_path, entry, expected):
    module = importlib.import_module("agents.architect_agent")
    arch = module.Architecture(tech_stack={}, component_tree=[], data_flow=[], file_list=[
        {"path": entry, "description": "static entry", "file_type": "page"},
    ])
    monkeypatch.setattr(module, "create_json_parser", lambda *a, **k: lambda *a, **k: arch)
    result = module.architect_agent({
        "code_gen_type": "html", "prd": {"page_name": "test"}, "project_dir": str(tmp_path),
    })
    assert result["phase"] == expected
    assert (tmp_path / "architecture.json").exists() == (expected == "arch_done")


def _html_state(tmp_path, entry="index.html"):
    return {
        "phase": "arch_done", "code_gen_type": "html", "project_dir": str(tmp_path),
        "app_id": "html-contract", "mode": "new",
        "architecture": {"file_list": [{"path": entry}], "tech_stack": {},
                         "component_tree": [], "data_flow": []},
    }


def test_coder_rejects_invalid_html_architecture_before_model_call(monkeypatch, tmp_path):
    module = importlib.import_module("agents.coder_agent")
    monkeypatch.setattr(module, "build_rag_context", lambda *a, **k: "")
    monkeypatch.setattr(module, "create_tool_enabled_llm", lambda *a, **k:
                        pytest.fail("Invalid HTML architecture must be rejected before model creation"))
    result = module.coder_agent(_html_state(tmp_path, "src/index.html"))
    assert result["phase"] == "error"
    assert "index.html" in result["error"]


@pytest.mark.parametrize("entry, expected", [("src/index.html", "error"), ("index.html", "code_done")])
def test_coder_validates_direct_json_result(monkeypatch, tmp_path, entry, expected):
    module = importlib.import_module("agents.coder_agent")

    class LLM:
        def invoke(self, *a, **k):
            return AIMessage(content=json.dumps({"files": [{"path": entry, "content": "<html>ok</html>"}]}))

    monkeypatch.setattr(module, "build_rag_context", lambda *a, **k: "")
    monkeypatch.setattr(module, "create_tool_enabled_llm", lambda *a, **k: LLM())
    result = module.coder_agent(_html_state(tmp_path))
    assert result["phase"] == expected


def test_coder_exit_cannot_complete_with_only_metadata(monkeypatch, tmp_path):
    module = importlib.import_module("agents.coder_agent")
    (tmp_path / "architecture.json").write_text("{}", encoding="utf-8")

    class LLM:
        def invoke(self, *a, **k):
            return AIMessage(content="", tool_calls=[
                {"name": "exit_tool", "args": {}, "id": "exit", "type": "tool_call"},
            ])

    monkeypatch.setattr(module, "build_rag_context", lambda *a, **k: "")
    monkeypatch.setattr(module, "create_tool_enabled_llm", lambda *a, **k: LLM())
    result = module.coder_agent(_html_state(tmp_path))
    assert result["phase"] == "error"
    assert "index.html" in result["error"]


@pytest.mark.parametrize("entry, content, expected", [
    ("src/index.html", "<html>ok</html>", False),
    ("index.html", "", False), ("index.html", "<html>ok</html>", True),
])
def test_builder_validates_actual_static_entry(monkeypatch, tmp_path, entry, content, expected):
    module = importlib.import_module("agents.builder_agent")
    file = tmp_path / entry
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(content, encoding="utf-8")
    monkeypatch.setattr(module, "_run_syntax_check", lambda *a, **k:
                        {"passed": True, "log": "mock offline", "tool_available": True})
    result = module.builder_agent({
        "mode": "new", "code_gen_type": "html", "project_dir": str(tmp_path),
        "code_files": [{"path": entry, "content": content}],
        "review": {"passed": True, "score": 90, "issues": []},
    })
    assert result["build_result"]["success"] is (None if expected else False)
    assert not (tmp_path / "package.json").exists()
    if not expected:
        assert finalize_state(result)["final_status"] != "success"


def test_full_graph_stops_after_returned_coder_error(monkeypatch):
    module = importlib.import_module("workflow.code_gen_workflow")

    def stage(phase):
        return lambda state: {**state, "phase": phase}

    monkeypatch.setattr(module, "mode_detector", stage("mode_detected"))
    monkeypatch.setattr(module, "intent_agent", stage("intent_done"))
    monkeypatch.setattr(module, "pm_agent", stage("prd_done"))
    monkeypatch.setattr(module, "architect_agent", stage("arch_done"))
    monkeypatch.setattr(module, "image_collector_agent", stage("arch_done"))
    monkeypatch.setattr(module, "coder_agent", lambda state:
                        {**state, "phase": "error", "error": "mock budget exhausted"})
    monkeypatch.setattr(module, "reviewer_agent", lambda state:
                        pytest.fail("Full graph must stop before Reviewer model call"))
    monkeypatch.setattr(module, "builder_agent", lambda state:
                        pytest.fail("Full graph must stop before Builder"))
    result = module.run_workflow("offline test", "test", "offline-failure", "html")
    assert result["final_status"] == "failed"
    assert result["failed_phase"] == "coder"
    assert result["last_good_phase"] == "image_collector"


def test_full_graph_generates_root_html_with_real_tools(monkeypatch, tmp_path):
    module = importlib.import_module("workflow.code_gen_workflow")
    architect = importlib.import_module("agents.architect_agent")
    coder = importlib.import_module("agents.coder_agent")
    builder = importlib.import_module("agents.builder_agent")
    arch = architect.Architecture(tech_stack={"framework": "HTML5"}, component_tree=[], data_flow=[],
        file_list=[{"path": "index.html", "description": "entry", "file_type": "page"}])
    monkeypatch.setattr(architect, "create_json_parser", lambda *a, **k: lambda *a, **k: arch)

    class LLM:
        calls = 0

        def invoke(self, *a, **k):
            self.calls += 1
            assert self.calls == 1
            return AIMessage(content="", tool_calls=[{
                "name": "create_file", "args": {"path": "index.html", "content": "<!doctype html><html>ready</html>"},
                "id": "create-root", "type": "tool_call",
            }])

    llm = LLM()
    monkeypatch.setattr(coder, "build_rag_context", lambda *a, **k: "")
    monkeypatch.setattr(coder, "create_tool_enabled_llm", lambda *a, **k: llm)
    monkeypatch.setattr(builder, "_run_syntax_check", lambda *a, **k:
                        {"passed": True, "log": "offline mock", "tool_available": True})
    monkeypatch.setattr(module, "mode_detector", lambda state: {**state, "phase": "mode_detected"})
    monkeypatch.setattr(module, "intent_agent", lambda state: {**state, "phase": "intent_done"})
    monkeypatch.setattr(module, "pm_agent", lambda state:
                        {**state, "phase": "prd_done", "prd": {"page_name": "test"}, "project_dir": str(tmp_path)})
    monkeypatch.setattr(module, "image_collector_agent", lambda state: state)
    monkeypatch.setattr(module, "reviewer_agent", lambda state:
                        {**state, "phase": "review_done", "review": {"passed": True, "score": 95, "issues": []}})
    result = module.run_workflow("offline root page", "test", "", "html")
    assert result["final_status"] == "success"
    assert result["build_result"]["status"] == "not_required"
    assert result["runtime_result"]["status"] == "succeeded"
    assert result["quality_gate_result"]["passed"] is True
    assert llm.calls == 1
    assert "ready" in (tmp_path / "index.html").read_text(encoding="utf-8")
    assert not (tmp_path / "package.json").exists()


def test_builder_rejects_whitespace_on_disk_despite_nonempty_state(monkeypatch, tmp_path):
    from agents.builder_agent import builder_agent
    (tmp_path / "index.html").write_text("   \n", encoding="utf-8")
    monkeypatch.setattr("agents.builder_agent._run_syntax_check", lambda *a, **k:
                        {"passed": True, "log": "mock", "tool_available": True})
    result = builder_agent({
        "code_gen_type": "html", "project_dir": str(tmp_path),
        "code_files": [{"path": "index.html", "content": "<html>old state</html>"}],
        "review": {"passed": True, "score": 90, "issues": []},
    })
    assert result["build_result"]["success"] is False


def test_sse_error_without_message_cannot_emit_success(monkeypatch, fake_conversation_memory, collect_json_events):
    module = importlib.import_module("workflow.sse_stream")

    async def states(*a, **k):
        yield {"phase": "error", "code_files": []}

    monkeypatch.setattr(module, "conversation_memory", fake_conversation_memory)
    monkeypatch.setattr(module, "run_workflow_async", states)
    events = asyncio.run(collect_json_events(module.stream_workflow("offline failure")))
    assert events[-1]["type"] == "done"
    assert events[-1]["status"] in ("failed", "error")
    assert any(event["type"] == "error" for event in events)
