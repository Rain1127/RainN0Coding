from pathlib import Path

import yaml

from benchmark.migrate_agent_eval import migrate_directory


def test_migrate_dev_golden_cases_to_core_dataset(tmp_path):
    source = Path(__file__).parents[2] / "agent_eval" / "golden" / "dev"
    destination = tmp_path / "core-golden.yaml"

    count = migrate_directory(source, destination, dataset_version="2026.09.1")

    document = yaml.safe_load(destination.read_text(encoding="utf-8"))
    assert count == 6
    assert document["schema_version"] == 1
    assert document["dataset_version"] == "2026.09.1"
    assert [case["id"] for case in document["cases"]] == [
        "intent-fallback-vue",
        "reviewer-detects-xss",
        "supervisor-review-passed",
        "supervisor-code-retry",
        "supervisor-architecture-discussion",
        "supervisor-retry-exhausted",
    ]
    assert all(
        case["execution"]["mode"] == "deterministic"
        for case in document["cases"]
        if case["target"] == "supervisor"
    )
