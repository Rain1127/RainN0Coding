"""The fact-accuracy scorer must reject stale values and preserve case pairing."""

from benchmark.memory_fact_ab import CASES, build_history, score_answer, select_cases


def test_score_answer_accepts_equivalent_fact_without_old_value():
    question = {"aliases": ["XLSX", "Excel（XLSX）"], "reject": ["CSV"]}

    assert score_answer("最终使用 XLSX 文件", question)
    assert not score_answer("之前是 CSV，现在用 XLSX", question)
    assert not score_answer("CSV", question)


def test_cases_have_unique_questions_and_facts_outside_recent_window():
    assert len(CASES) == 7
    for case in CASES:
        history = build_history(case)
        assert len(history) == case.get("message_count", 28)
        assert len(case["questions"]) in (4, 8)
        assert len({question["id"] for question in case["questions"]}) == len(case["questions"])
        assert all(history[index]["role"] == "user" for index in case["events"])
        assert all(index < len(history) - 10 for index in case["events"])


def test_extended_cases_are_long_and_have_distinct_dialogue():
    extended = CASES[4:]
    assert [case["message_count"] for case in extended] == [72, 84, 96]
    assert all(len(case["questions"]) == 8 for case in extended)
    for case in extended:
        history = build_history(case)
        non_event_user_messages = {
            message["content"] for index, message in enumerate(history)
            if index % 2 == 0 and index not in case["events"]
        }
        assert len(non_event_user_messages) >= 12
        assert any("不再" in content or "取消" in content for content in case["events"].values())


def test_case_sets_preserve_the_original_baseline():
    assert select_cases("baseline") == CASES[:4]
    assert select_cases("extended") == CASES[4:]
    assert select_cases("all") == CASES
