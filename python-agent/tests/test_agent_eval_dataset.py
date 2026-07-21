import json

import pytest

from agent_eval.dataset import load_cases
from agent_eval.reporting import build_report
from agent_eval.contracts import EvaluationResult, GoldenCase, MetricAssertion


def test_load_cases_reads_json_files_recursively(tmp_path):
    path = tmp_path / "supervisor" / "routing.json"
    path.parent.mkdir()
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "cases": [
                    {
                        "id": "route-pass",
                        "agent": "supervisor",
                        "category": "routing",
                        "input_state": {"phase": "review_done"},
                        "expectations": {"equals": {"next_node": "builder_agent"}},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    cases = load_cases(tmp_path)

    assert [case.id for case in cases] == ["route-pass"]


def test_load_cases_rejects_duplicate_case_ids(tmp_path):
    for name in ("one.json", "two.json"):
        (tmp_path / name).write_text(
            json.dumps({"version": 1, "cases": [{"id": "duplicate", "agent": "intent", "category": "fallback", "input_state": {}, "expectations": {}}]}),
            encoding="utf-8",
        )

    with pytest.raises(ValueError, match="duplicate"):
        load_cases(tmp_path)


def test_build_report_groups_results_by_agent_and_category():
    case = GoldenCase("route-pass", "supervisor", "routing", {}, {})
    report = build_report(
        [
            EvaluationResult(case, True, 2, 2, []),
            EvaluationResult(case, False, 1, 2, ["wrong route"]),
        ]
    )

    assert report["summary"] == {"cases": 2, "passed": 1, "pass_rate": 0.5, "assertion_pass_rate": 0.75}
    assert report["by_agent"]["supervisor"]["pass_rate"] == 0.5
    assert report["by_category"]["routing"]["assertion_pass_rate"] == 0.75


def test_build_report_records_assertion_and_observed_metric_ledgers():
    case = GoldenCase("route-pass", "supervisor", "routing", {}, {})
    result = EvaluationResult(
        case,
        True,
        1,
        1,
        [],
        assertions=[MetricAssertion("route_accuracy", True, "equals", "next_node")],
        observed_metrics={"latency_ms": 120.0, "input_tokens": 40},
    )

    ledger = build_report([result])["metric_ledger"]

    assert ledger["overall"]["assertions"]["route_accuracy"] == {"checks": 1, "passed": 1, "failed": 0, "rate": 1.0}
    assert ledger["overall"]["observed"]["latency_ms"]["mean"] == 120.0
    assert ledger["by_agent"]["supervisor"]["observed"]["input_tokens"]["sum"] == 40.0
