"""The long-horizon A/B dataset and scoring must be fixed before cloud runs."""

from benchmark.memory_long_horizon_ab import (
    CHECKPOINTS,
    FACTS,
    active_version,
    build_dialogue,
    build_event_map,
    fact_retained,
    score_answer,
)


def test_fixed_turns_and_checkpoint_gold():
    assert CHECKPOINTS == (50, 100, 200)
    assert len(FACTS) == 14
    assert len({fact["id"] for fact in FACTS}) == len(FACTS)
    assert [sum(len(fact["versions"]) > 1 and fact["versions"][1][0] <= turn
                for fact in FACTS) for turn in CHECKPOINTS] == [4, 8, 12]

    events = build_event_map()
    assert len(events) == 26
    assert all(max(event_turn for event_turn in events if event_turn <= turn) <= turn - 6
               for turn in CHECKPOINTS)
    dialogue = build_dialogue()
    assert len(dialogue) == 400
    assert all(dialogue[(turn - 1) * 2]["role"] == "user" for turn in events)


def test_retention_and_update_scoring_reject_stale_values():
    frontend = next(fact for fact in FACTS if fact["id"] == "frontend")
    active = active_version(frontend, 50)
    assert active[1] == "Vue 3 PWA"
    assert fact_retained("[摘要] 前端确定为 Vue 3 PWA", frontend, 50)
    assert not fact_retained("[摘要] 前端原计划 Angular", frontend, 50)
    assert score_answer("Vue 3 PWA", frontend, 50)
    assert not score_answer("Angular", frontend, 50)
    assert not score_answer("从 Angular 改成 Vue 3 PWA", frontend, 50)
