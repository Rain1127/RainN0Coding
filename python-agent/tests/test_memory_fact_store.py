"""Current facts survive incremental compression and explicit corrections."""

import pytest

from memory.fact_store import (
    active_facts,
    apply_fact_ops,
    empty_fact_state,
    migrate_legacy_facts,
    select_active_facts,
)


def _message(number: int, content: str) -> dict:
    return {"id": f"m{number}", "role": "user", "content": content,
            "timestamp": float(number)}


def _upsert(number: int, key: str, value: str,
            category: str = "decision") -> tuple[dict, dict]:
    content = f"{key}最终确定为{value}。"
    return _message(number, content), {
        "op": "upsert", "key": key, "category": category,
        "value": value, "source_id": f"m{number}", "evidence": content,
    }


def test_more_than_eight_facts_survive_a_later_batch_without_mentions():
    pairs = [_upsert(i, f"字段{i}", f"值{i}") for i in range(1, 15)]
    state = apply_fact_ops(empty_fact_state(), [op for _, op in pairs],
                           [msg for msg, _ in pairs])

    state = apply_fact_ops(state, [], [_message(15, "继续完善列表空态。")])

    assert len(state["records"]) == 14
    assert len(active_facts(state)["decisions"]) == 14
    assert "字段1: 值1" in active_facts(state)["decisions"]


def test_correction_replaces_one_key_and_keeps_old_version_as_evidence():
    first_message, first_op = _upsert(1, "前端方案", "Angular")
    other_message, other_op = _upsert(2, "数据库", "MySQL")
    state = apply_fact_ops(empty_fact_state(), [first_op, other_op],
                           [first_message, other_message])
    correction = _message(3, "更正前端方案：最终采用Vue 3，不再采用Angular。")
    operation = {"op": "upsert", "key": "前端方案", "category": "decision",
                 "value": "Vue 3", "source_id": "m3", "evidence": correction["content"]}

    state = apply_fact_ops(state, [operation], [correction])

    assert state["records"]["前端方案"]["value"] == "Vue 3"
    assert state["records"]["前端方案"]["history"][0]["value"] == "Angular"
    assert state["records"]["数据库"]["value"] == "MySQL"
    assert "Angular" not in str(active_facts(state))


@pytest.mark.parametrize("bad_op", [
    {"op": "upsert", "key": "数据库", "category": "decision",
     "value": "MySQL", "source_id": "missing", "evidence": "数据库最终确定为MySQL。"},
    {"op": "upsert", "key": "数据库", "category": "decision",
     "value": "PostgreSQL", "source_id": "m1", "evidence": "数据库最终确定为MySQL。"},
])
def test_unverified_fact_operation_rejects_the_whole_batch(bad_op):
    with pytest.raises(ValueError):
        apply_fact_ops(empty_fact_state(), [bad_op],
                       [_message(1, "数据库最终确定为MySQL。")])


def test_old_evidence_cannot_overwrite_a_newer_correction():
    new_message, new_op = _upsert(3, "前端方案", "Vue 3")
    state = apply_fact_ops(empty_fact_state(), [new_op], [new_message])
    old_message, old_op = _upsert(2, "前端方案", "Angular")

    state = apply_fact_ops(state, [old_op], [old_message])

    assert state["records"]["前端方案"]["value"] == "Vue 3"


def test_v2_facts_remain_readable_during_migration():
    state = migrate_legacy_facts({"goal": "制作后台", "constraints": ["仅内网"],
                                  "decisions": ["前端方案确定为Vue 3"],
                                  "pending_tasks": []})

    assert active_facts(state)["goal"] == "制作后台"
    assert "前端方案确定为Vue 3" in active_facts(state)["decisions"]


def test_explicit_old_value_replaces_its_fact_even_if_model_renames_the_key():
    first, op = _upsert(1, "frontend", "Angular")
    state = apply_fact_ops(empty_fact_state(), [op], [first])
    correction = _message(2, "更正前端方案：最终采用Vue 3，不再采用Angular。")
    renamed = {"op": "upsert", "key": "前端方案", "category": "decision",
               "value": "Vue 3", "source_id": "m2", "evidence": correction["content"]}

    state = apply_fact_ops(state, [renamed], [correction])

    assert len(state["records"]) == 1
    assert "Angular" not in str(active_facts(state))
    assert "Vue 3" in str(active_facts(state))


def test_prompt_budget_selects_matching_fact_and_reports_omissions():
    pairs = [_upsert(i, f"字段{i}", f"值{i}") for i in range(1, 31)]
    state = apply_fact_ops(empty_fact_state(), [op for _, op in pairs],
                           [msg for msg, _ in pairs])

    selected, omitted = select_active_facts(state, "字段1的最终值是什么？", max_chars=100)

    assert "字段1: 值1" in selected["decisions"]
    assert omitted > 0
    assert len(str(selected)) < len(str(active_facts(state)))


def test_multiple_goal_facts_are_visible_in_context():
    project, project_op = _upsert(1, "项目正式名称", "远汐运维台", "goal")
    audience, audience_op = _upsert(2, "目标用户", "区域维护主管", "goal")

    state = apply_fact_ops(empty_fact_state(), [project_op, audience_op],
                           [project, audience])

    assert "远汐运维台" in active_facts(state)["goal"]
    assert "区域维护主管" in active_facts(state)["goal"]


def test_fact_evidence_does_not_persist_a_credential():
    source = _message(1, "项目正式名称为远汐运维台；api_key=sk-1234567890abcdef")
    operation = {"op": "upsert", "key": "项目正式名称", "category": "goal",
                 "value": "远汐运维台", "source_id": "m1", "evidence": source["content"]}

    state = apply_fact_ops(empty_fact_state(), [operation], [source])

    assert "远汐运维台" in active_facts(state)["goal"]
    assert "sk-1234567890abcdef" not in str(state)


def test_delete_cannot_remove_an_unrelated_fact():
    original, upsert = _upsert(1, "前端方案", "Vue 3")
    state = apply_fact_ops(empty_fact_state(), [upsert], [original])
    source = _message(2, "取消图表库方案。")
    unrelated_delete = {"op": "delete", "key": "前端方案",
                        "category": "decision", "value": "",
                        "source_id": "m2", "evidence": source["content"]}

    with pytest.raises(ValueError):
        apply_fact_ops(state, [unrelated_delete], [source])


def test_query_match_takes_priority_over_a_large_unrelated_goal():
    goal, goal_op = _upsert(1, "项目背景", "这是一个很长的项目背景介绍" * 8, "goal")
    decision, decision_op = _upsert(2, "数据库", "MySQL")
    state = apply_fact_ops(empty_fact_state(), [goal_op, decision_op],
                           [goal, decision])

    selected, omitted = select_active_facts(state, "数据库是什么？", max_chars=40)

    assert "数据库: MySQL" in selected["decisions"]
    assert omitted == 1


def test_corrections_follow_message_order_even_if_model_returns_ops_reversed():
    old_message, old_op = _upsert(1, "数据库", "PostgreSQL")
    new_message = _message(2, "更正数据库：最终采用MySQL，不再采用PostgreSQL。")
    new_op = {"op": "upsert", "key": "数据库", "category": "decision",
              "value": "MySQL", "source_id": "m2", "evidence": new_message["content"]}
    old_message["timestamp"] = new_message["timestamp"]

    state = apply_fact_ops(empty_fact_state(), [new_op, old_op],
                           [old_message, new_message])

    assert state["records"]["数据库"]["value"] == "MySQL"
