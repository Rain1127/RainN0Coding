from agent_eval.contracts import GoldenCase
from agent_eval.evaluator import evaluate_case


def _case(expectations):
    return GoldenCase(
        id="reviewer-xss",
        agent="reviewer",
        category="security",
        input_state={"phase": "code_done"},
        expectations=expectations,
    )


def test_evaluate_case_accepts_matching_fields_and_issue_text():
    result = evaluate_case(
        _case(
            {
                "equals": {"passed": False},
                "required_paths": ["score", "issues"],
                "required_text": {"issues": ["xss", "unescaped user input"]},
                "forbidden_text": {"issues": ["sql injection"]},
            }
        ),
        {
            "passed": False,
            "score": 48,
            "issues": [{"category": "security", "description": "XSS: unescaped user input"}],
        },
    )

    assert result.passed is True
    assert result.assertions_total == 5
    assert result.assertions_passed == 5


def test_evaluate_case_reports_path_aware_failures():
    result = evaluate_case(
        _case({"equals": {"passed": False}, "required_paths": ["issues"], "required_text": {"issues": ["xss"]}}),
        {"passed": True, "issues": []},
    )

    assert result.passed is False
    assert result.assertions_total == 3
    assert result.assertions_passed == 1
    assert any("passed" in failure for failure in result.failures)
    assert any("issues" in failure for failure in result.failures)


def test_evaluate_case_records_named_metric_for_every_assertion():
    result = evaluate_case(
        GoldenCase(
            id="route-pass",
            agent="supervisor",
            category="routing",
            input_state={},
            expectations={"equals": {"next_node": "builder_agent"}},
            metric_tags={"equals.next_node": "route_accuracy"},
        ),
        {"next_node": "builder_agent"},
    )

    assert [(assertion.metric, assertion.passed) for assertion in result.assertions] == [("route_accuracy", True)]
