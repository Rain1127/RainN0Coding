import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.intent_agent import intent_agent


def test_intent_agent_falls_back_to_rule_router_when_llm_returns_none(monkeypatch):
    monkeypatch.setattr("agents.intent_agent.recognize_intent", lambda user_request, user_id=None: None)
    monkeypatch.setattr("agents.intent_agent.route_code_gen_type", lambda user_request, user_id=None: "vue_project")

    state = {
        "user_request": "做一个任务管理后台",
        "user_id": "u1",
        "phase": "init",
    }

    result = intent_agent(state)

    assert result["phase"] == "intent_done"
    assert result["error"] is None
    assert result["intent"]["primary_intent"] == "代码生成 / 前端代码生成 / 生成 Vue 项目"
    assert result["intent"]["confidence"] == 0.55
    assert result["intent"]["should_clarify"] is False
    assert result["clarification"]["note"].startswith("LLM 不可用")


def test_intent_agent_falls_back_to_rule_router_when_llm_raises(monkeypatch):
    def fail_recognize(user_request, user_id=None):
        raise RuntimeError("all model calls failed")

    monkeypatch.setattr("agents.intent_agent.recognize_intent", fail_recognize)
    monkeypatch.setattr("agents.intent_agent.route_code_gen_type", lambda user_request, user_id=None: "python")

    state = {
        "user_request": "写一个 FastAPI 服务",
        "user_id": "u2",
        "phase": "init",
    }

    result = intent_agent(state)

    assert result["phase"] == "intent_done"
    assert result["error"] is None
    assert result["intent"]["primary_intent"] == "代码生成 / 后端代码生成 / 生成 Python 服务"
    assert result["intent"]["slots"]["code_gen_type"] == "python"
