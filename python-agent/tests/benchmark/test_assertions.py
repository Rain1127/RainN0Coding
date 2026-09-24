from benchmark.contracts import BenchmarkCase
from benchmark.evaluators.assertions import evaluate_assertions


def _case(expectations: dict, *, output_metrics: dict[str, str] | None = None) -> BenchmarkCase:
    return BenchmarkCase(
        id="reviewer-xss",
        dataset_version="v1",
        target="reviewer",
        category="security",
        execution={"mode": "replay", "record": "reviewer-xss.json"},
        input={},
        expectations=expectations,
        metric_tags={"required_text.review.issues": "critical_defect_recall"},
        output_metrics=output_metrics or {},
        provenance={"source": "curated", "reviewed": True, "sanitized": True},
    )


def test_evaluate_case_accepts_matching_review_assertions_and_metrics():
    result = evaluate_assertions(
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
    result = evaluate_assertions(
        _case({"required_paths": ["review.score"]}),
        {"review": {"passed": False}},
    )

    assert result.passed is False
    assert result.infrastructure_error is None
    assert result.failures == ["review.score: required path is missing"]


def test_metric_resolution_does_not_fall_back_to_leaf_path():
    case = _case(
        {"required_text": {"review.issues": ["xss"]}},
    ).model_copy(update={"metric_tags": {"required_text.issues": "leaf_metric", "required_text": "rule_metric"}})

    result = evaluate_assertions(case, {"review": {"issues": "xss"}})

    assert result.assertions[0].metric == "rule_metric"


def test_required_files_are_native_assertions_against_generated_code_files():
    case = _case({"required_files": ["index.html", "src/app.js"]}).model_copy(
        update={
            "metric_tags": {
                "required_files": "file_coverage",
                "required_files.src/app.js": "critical_file_coverage",
            }
        }
    )

    result = evaluate_assertions(
        case,
        {"code_files": [{"path": "index.html", "content": "<main />"}]},
    )

    assert result.passed is False
    assert result.assertions_total == 2
    assert [(item.path, item.passed, item.metric) for item in result.assertions] == [
        ("index.html", True, "file_coverage"),
        ("src/app.js", False, "critical_file_coverage"),
    ]
    assert result.failures == ["src/app.js: required generated file is missing"]


def test_required_files_fail_when_generated_file_schema_is_invalid():
    result = evaluate_assertions(
        _case({"required_files": ["index.html"]}),
        {"code_files": [{"path": "../index.html", "content": "unsafe"}]},
    )

    assert result.passed is False
    assert result.assertions_total == 1
    assert result.assertions[0].metric == "output_protocol_completeness"
    assert result.failures == ["index.html: generated files are invalid"]


def test_required_files_use_the_same_windows_safe_component_grammar():
    result = evaluate_assertions(
        _case({"required_files": ["a.txt:stream", "bad?.py", "nested/CON.txt"]}),
        {"code_files": [{"path": "index.html", "content": "safe"}]},
    )

    assert result.passed is False
    assert result.assertions_total == 3
    assert all(not item.passed for item in result.assertions)
    assert result.failures == [
        "a.txt:stream: required generated file path is invalid",
        "bad?.py: required generated file path is invalid",
        "nested/CON.txt: required generated file path is invalid",
    ]
