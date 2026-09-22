from benchmark.contracts import BenchmarkCase
from benchmark.evaluators.assertions import evaluate_case


def _case(expectations: dict, *, output_metrics: dict[str, str] | None = None) -> BenchmarkCase:
    return BenchmarkCase(
        id="reviewer-xss",
        dataset_version="v1",
        target="reviewer",
        category="security",
        execution={"mode": "replay", "record": "reviewer-xss.json"},
        input={},
        expectations=expectations,
        metric_tags={"required_text.issues": "critical_defect_recall"},
        output_metrics=output_metrics or {},
        provenance={"source": "curated", "reviewed": True, "sanitized": True},
    )


def test_evaluate_case_accepts_matching_review_assertions_and_metrics():
    result = evaluate_case(
        _case(
            {
                "equals": {"review.passed": False},
                "required_paths": ["review.score", "review.issues"],
                "required_text": {"review.issues": ["xss", "v-html"]},
                "forbidden_text": {"review.issues": ["safe to ship"]},
            },
            output_metrics={"review.score": "review_score"},
        ),
        {
            "review": {
                "passed": False,
                "score": 40,
                "issues": [{"description": "v-html XSS"}],
            },
            "metrics": {"latency_ms": 12},
        },
        observed_metrics={"latency_ms": 12},
    )

    assert result.passed is True
    assert result.assertions_total == 5
    assert result.assertions_passed == 5
    assert {assertion.metric for assertion in result.assertions} == {
        "task_correctness",
        "output_protocol_completeness",
        "critical_defect_recall",
        "safety_compliance",
    }
    assert result.observed_metrics == {"review_score": 40.0, "latency_ms": 12.0}
    assert result.infrastructure_error is None


def test_evaluate_case_reports_missing_nested_path_as_case_failure():
    result = evaluate_case(
        _case({"required_paths": ["review.score"]}),
        {"review": {"passed": False}},
    )

    assert result.passed is False
    assert result.infrastructure_error is None
    assert result.failures == ["review.score: required path is missing"]

