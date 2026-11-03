import pytest
from agents.change_plan import simple_target, diff_changes
from workflow.budget import Budget, BudgetExceeded


def test_safe_local_task_saves_intent_call_and_complex_task_escalates():
    state = {"mode": "modify", "existing_code_files": [{"path": "src/Header.vue", "content": "old"}]}
    assert simple_target({**state, "user_request": "只修改导航栏颜色"}) == "src/Header.vue"
    assert simple_target({**state, "user_request": "导航增加登录权限接口"}) is None


def test_unplanned_file_is_rejected():
    state = {"mode": "modify", "change_plan": {"files": ["Header.vue"]},
        "existing_code_files": [{"path": "Header.vue", "content": "red"}, {"path": "Main.vue", "content": "old"}],
        "code_files": [{"path": "Header.vue", "content": "blue"}, {"path": "Main.vue", "content": "changed"}]}
    result = diff_changes(state)
    assert result["phase"] == "error"
    assert result["change_result"]["unexpected"] == ["Main.vue"]
    assert "+blue" in result["change_result"]["files"][0]["diff"]


def test_call_and_token_budget_are_finite(monkeypatch):
    import workflow.budget as module
    monkeypatch.setattr(module.config, "TASK_MAX_LLM_CALLS", 1, raising=False)
    budget = Budget()
    assert budget.reserve(["prompt"]) > 0
    budget.observe(None)
    assert budget.report()["tokens"] is None
    with pytest.raises(BudgetExceeded, match="call"):
        budget.reserve(["again"])
    monkeypatch.setattr(module.config, "TASK_MAX_TOKENS", 1, raising=False)
    with pytest.raises(BudgetExceeded, match="token"):
        Budget().reserve(["prompt"])


def test_time_budget_survives_resume():
    with pytest.raises(BudgetExceeded, match="time"):
        Budget({"started_at": 1, "active_seconds": 999999}).check()


def test_pause_does_not_consume_active_budget_and_partial_cost_is_unknown():
    budget=Budget({"started_at": 1, "active_seconds": 0})
    budget.check()
    budget.reserve(["request"])
    budget.observe({"total_tokens": 2, "cost_usd": 0.1})
    budget.reserve(["request"])
    budget.observe({"total_tokens": 2, "cost_usd": None})
    assert budget.report()["cost_usd"] is None
