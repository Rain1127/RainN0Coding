import json

from agent_eval.runner import evaluate_dataset


def test_evaluate_dataset_runs_live_supervisor_cases(tmp_path):
    (tmp_path / "routing.json").write_text(
        json.dumps(
            {
                "version": 1,
                "cases": [
                    {
                        "id": "review-passed",
                        "agent": "supervisor",
                        "category": "routing",
                        "input_state": {"phase": "review_done", "review": {"passed": True}},
                        "expectations": {"equals": {"next_node": "builder_agent"}},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report = evaluate_dataset(tmp_path, agent="supervisor")

    assert report["summary"]["pass_rate"] == 1.0
    assert report["results"][0]["actual_output"] == {"next_node": "builder_agent"}


def test_evaluate_dataset_uses_saved_records_for_llm_agents(tmp_path):
    (tmp_path / "intent.json").write_text(
        json.dumps(
            {
                "version": 1,
                "cases": [
                    {
                        "id": "intent-fallback",
                        "agent": "intent",
                        "category": "fallback",
                        "input_state": {},
                        "expectations": {"equals": {"phase": "intent_done"}},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    records = tmp_path / "records.json"
    records.write_text(json.dumps({"intent-fallback": {"phase": "intent_done"}}), encoding="utf-8")

    report = evaluate_dataset(tmp_path, records_path=records)

    assert report["summary"]["pass_rate"] == 1.0


def test_evaluate_dataset_preserves_saved_latency_and_token_metrics(tmp_path):
    (tmp_path / "intent.json").write_text(
        json.dumps({"version": 1, "cases": [{"id": "intent-latency", "agent": "intent", "category": "performance", "input_state": {}, "expectations": {}}]}),
        encoding="utf-8",
    )
    records = tmp_path / "records.json"
    records.write_text(
        json.dumps({"intent-latency": {"output": {}, "metrics": {"latency_ms": 75, "output_tokens": 24}}}),
        encoding="utf-8",
    )

    report = evaluate_dataset(tmp_path, records_path=records)

    assert report["results"][0]["observed_metrics"] == {"latency_ms": 75.0, "output_tokens": 24.0}
    assert report["metric_ledger"]["overall"]["observed"]["output_tokens"]["mean"] == 24.0
