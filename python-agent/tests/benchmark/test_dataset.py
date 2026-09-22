from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmark.dataset import load_dataset


def _case(case_id: str, *, record: str | None = None) -> dict:
    execution = {"mode": "replay"}
    if record is not None:
        execution["record"] = record
    return {
        "id": case_id,
        "target": "intent",
        "category": "classification",
        "execution": execution,
        "input": {"prompt": "classify this request"},
        "expectations": {"equals": {"intent": "code_generation"}},
        "metric_tags": ["smoke"],
        "output_metrics": ["accuracy"],
        "gate": {"required": True},
        "provenance": {
            "source": "curated",
            "reviewed": True,
            "sanitized": True,
        },
    }


def _write_yaml(path: Path, dataset_version: str, cases: list[dict]) -> None:
    import yaml

    path.write_text(
        yaml.safe_dump(
            {"schema_version": 1, "dataset_version": dataset_version, "cases": cases},
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_loads_versions_and_resolves_replay_record(tmp_path: Path) -> None:
    source = tmp_path / "cases.yaml"
    record = tmp_path / "fixtures" / "output.json"
    record.parent.mkdir()
    record.write_text(json.dumps({"intent": "code_generation"}), encoding="utf-8")
    _write_yaml(source, "2026.09.1", [_case("intent-001", record="fixtures/output.json")])

    loaded = load_dataset(tmp_path)

    assert len(loaded) == 1
    assert loaded[0].case.schema_version == 1
    assert loaded[0].case.dataset_version == "2026.09.1"
    assert loaded[0].record_path == record.resolve()
    assert loaded[0].record_path.is_absolute()


def test_rejects_duplicate_ids_across_yaml_files(tmp_path: Path) -> None:
    _write_yaml(tmp_path / "a.yaml", "2026.09.1", [_case("duplicate")])
    _write_yaml(tmp_path / "b.yml", "2026.09.2", [_case("duplicate")])

    with pytest.raises(ValueError, match="duplicate benchmark case id"):
        load_dataset(tmp_path)


def test_rejects_record_outside_dataset_root(tmp_path: Path) -> None:
    source = tmp_path / "cases.yaml"
    _write_yaml(source, "2026.09.1", [_case("escape", record="../secret.json")])
    (tmp_path.parent / "secret.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="outside dataset root"):
        load_dataset(tmp_path)
