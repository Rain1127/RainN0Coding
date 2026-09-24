from pathlib import Path
import json

import pytest
import yaml

from benchmark.dataset import load_cases
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


def _write_source(path: Path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _valid_case(case_id: str = "case-1") -> dict:
    return {
        "id": case_id,
        "agent": "supervisor",
        "category": "routing",
        "input_state": {"phase": "review_done"},
        "expectations": {"equals": {"next_node": "builder_agent"}},
    }


@pytest.mark.parametrize(
    ("payload", "message"),
    [([_valid_case()], "top-level JSON"), ({"version": 1}, "cases"), ({"version": 1, "cases": [None]}, "case index 0")],
)
def test_migration_rejects_malformed_source_with_path_and_context(tmp_path: Path, payload, message):
    source = tmp_path / "bad.json"
    _write_source(source, payload)

    with pytest.raises(ValueError, match=message):
        migrate_directory(tmp_path, tmp_path / "out.yaml", dataset_version="2026.09.1")


def test_migration_rejects_missing_required_field_with_case_context(tmp_path: Path):
    source = tmp_path / "bad.json"
    case = _valid_case()
    del case["agent"]
    _write_source(source, {"version": 1, "cases": [case]})

    with pytest.raises(ValueError, match=r"bad\.json.*case index 0.*case-1.*agent"):
        migrate_directory(tmp_path, tmp_path / "out.yaml", dataset_version="2026.09.1")


def test_migration_rejects_duplicate_ids_and_empty_sources(tmp_path: Path):
    _write_source(tmp_path / "a.json", {"version": 1, "cases": [_valid_case("same")]})
    _write_source(tmp_path / "b.json", {"version": 1, "cases": [_valid_case("same")]})
    with pytest.raises(ValueError, match=r"duplicate.*same"):
        migrate_directory(tmp_path, tmp_path / "out.yaml", dataset_version="2026.09.1")

    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError, match="no migrated cases"):
        migrate_directory(empty, tmp_path / "empty.yaml", dataset_version="2026.09.1")


@pytest.mark.parametrize("version", [None, True, 1.0, 2, "1"])
def test_migration_requires_literal_source_version_one(tmp_path: Path, version):
    source = tmp_path / "version.json"
    payload = {"cases": [_valid_case()]}
    if version is not None:
        payload["version"] = version
    _write_source(source, payload)
    with pytest.raises(ValueError, match=r"version\.json.*version"):
        migrate_directory(tmp_path, tmp_path / "out.yaml", dataset_version="2026.09.1")


@pytest.mark.parametrize(
    "field,value",
    [("id", 1), ("agent", ""), ("category", None), ("input_state", []), ("expectations", []), ("metric_tags", []), ("output_metrics", [])],
)
def test_migration_rejects_invalid_source_field_types(tmp_path: Path, field, value):
    source = tmp_path / "types.json"
    case = _valid_case()
    case[field] = value
    _write_source(source, {"version": 1, "cases": [case]})
    with pytest.raises(ValueError, match=r"types\.json.*case index 0"):
        migrate_directory(tmp_path, tmp_path / "out.yaml", dataset_version="2026.09.1")


def test_migration_rejects_unsupported_target_and_non_directory_source(tmp_path: Path):
    source = tmp_path / "target.json"
    case = _valid_case()
    case["agent"] = "unknown"
    _write_source(source, {"version": 1, "cases": [case]})
    with pytest.raises(ValueError, match=r"target\.json.*unsupported agent"):
        migrate_directory(tmp_path, tmp_path / "out.yaml", dataset_version="2026.09.1")
    with pytest.raises(ValueError, match="source directory"):
        migrate_directory(source, tmp_path / "out.yaml", dataset_version="2026.09.1")


def test_migration_is_deterministic_across_repeated_outputs(tmp_path: Path):
    source = Path(__file__).parents[2] / "agent_eval" / "golden" / "dev"
    destination = tmp_path / "same.yaml"
    first_count = migrate_directory(source, destination, dataset_version="2026.09.1")
    first_bytes = destination.read_bytes()
    second_count = migrate_directory(source, destination, dataset_version="2026.09.1")
    assert first_count == second_count == 6
    assert destination.read_bytes() == first_bytes


def test_committed_regression_dataset_loads_with_benchmark_asset_boundary():
    benchmark_root = Path(__file__).parents[2] / "benchmarks"
    loaded = load_cases(benchmark_root / "datasets" / "regression", asset_root=benchmark_root)
    assert len(loaded) == 8
    assert {case.record_path.name for case in loaded if case.record_path} == {
        "intent-fallback-vue.json",
        "reviewer-detects-xss.json",
        "search-results.json",
    }
