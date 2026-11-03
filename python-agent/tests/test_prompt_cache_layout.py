from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

import llm_factory
from agents import coder_agent as coder_module
from langchain_core.messages import AIMessage


class _Output(BaseModel):
    value: str


def test_composer_keeps_fixed_prefix_and_request_last():
    compose_messages = getattr(llm_factory, "compose_messages", None)
    assert callable(compose_messages)
    first = compose_messages(
        agent="coder", system="fixed rules", context="project A",
        rag="reference A", retry="retry A", request="build A",
        field_spec="JSON schema",
    )
    second = compose_messages(
        agent="coder", system="fixed rules", context="project B",
        rag="reference B", retry="", request="build B",
        field_spec="JSON schema",
    )
    assert first[0] == second[0]
    assert isinstance(first[0], SystemMessage)
    assert "JSON schema" in first[0].content
    assert isinstance(first[-1], HumanMessage)
    assert first[-1].content.endswith("build A")
    assert "project A" not in first[0].content


def test_stable_system_version_is_not_duplicated_by_schema_composition():
    messages = llm_factory.compose_messages(agent="pm", system="rules", request="build")
    result = llm_factory._with_system_field_spec(messages, "schema")
    assert result[0].content.count("Prompt version:") == 1
    assert result[0].content.count("schema") == 1


def test_enriched_memory_moves_before_rag_and_retry():
    enriched = "[对话摘要] old\n[关键事实] facts\n[最近对话]\n用户: hi\n[当前请求] build now"
    messages = llm_factory.compose_messages(
        agent="coder", system="rules", context="project", rag="reference",
        retry="fix error", request=enriched,
    )
    human = messages[-1].content
    assert human.index("[对话摘要]") < human.index("reference")
    assert human.index("reference") < human.index("fix error")
    assert human.endswith("build now")


def test_json_parser_puts_field_spec_in_system_not_human(monkeypatch):
    captured = {}

    class FakeClient:
        def invoke(self, messages, config=None):
            captured["messages"] = messages
            return type("Response", (), {"content": '{"value":"ok"}'})()

    monkeypatch.setattr(llm_factory, "record_llm_response", lambda *_args: None)
    parsed = llm_factory._call_with_parser(
        [SystemMessage(content="fixed"), HumanMessage(content="dynamic")],
        _Output, "schema", "structured", _client=FakeClient(),
    )
    assert parsed.value == "ok"
    assert "schema" in captured["messages"][0].content
    assert captured["messages"][-1].content == "dynamic"


def test_coder_mode_change_preserves_system_and_tool_order(monkeypatch, tmp_path):
    captured = []
    monkeypatch.setattr(coder_module, "build_rag_context", lambda *_a, **_k: "")

    class FakeLlm:
        def invoke(self, messages, config=None):
            captured[-1]["messages"] = list(messages)
            return AIMessage(content='{"files":[{"path":"main.py","content":"print(1)"}]}')

    def fake_create(tools, group):
        captured.append({"tools": [tool.name for tool in tools]})
        return FakeLlm()

    monkeypatch.setattr(coder_module, "create_tool_enabled_llm", fake_create)
    for mode in ("new", "modify"):
        state = {
            "mode": mode, "code_gen_type": "python", "user_request": f"request {mode}",
            "project_dir": str(tmp_path / mode),
            "architecture": {"file_list": [{"path": "main.py", "description": "entry"}]},
        }
        coder_module.coder_agent(state)

    assert captured[0]["tools"] == captured[1]["tools"]
    assert captured[0]["messages"][0] == captured[1]["messages"][0]
    assert captured[0]["messages"][-1].content.endswith("request new")
    assert captured[1]["messages"][-1].content.endswith("request modify")
