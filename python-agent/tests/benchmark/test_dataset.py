from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from benchmark.dataset import load_cases


pytestmark = pytest.mark.benchmark

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
        "metric_tags": {"suite": "smoke"},
        "output_metrics": {"primary": "accuracy"},
        "gate": {"required": True},
        "provenance": {
            "source": "curated",
            "reviewed": True,
            "sanitized": True,
        },
    }


def _write_yaml(path: Path, dataset_version: str, cases: list[dict]) -> None:
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

    loaded = load_cases(tmp_path)

    assert len(loaded) == 1
    assert loaded[0].case.schema_version == 1
    assert loaded[0].case.dataset_version == "2026.09.1"
    assert loaded[0].record_path == record.resolve()
    assert loaded[0].record_path.is_absolute()


def test_rejects_duplicate_ids_across_yaml_files(tmp_path: Path) -> None:
    _write_yaml(tmp_path / "a.yaml", "2026.09.1", [_case("duplicate")])
    _write_yaml(tmp_path / "b.yml", "2026.09.2", [_case("duplicate")])

    with pytest.raises(ValueError, match="duplicate benchmark case id"):
        load_cases(tmp_path)


def test_rejects_record_outside_dataset_root(tmp_path: Path) -> None:
    source = tmp_path / "cases.yaml"
    _write_yaml(source, "2026.09.1", [_case("escape", record="../secret.json")])
    (tmp_path.parent / "secret.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="outside dataset root"):
        load_cases(tmp_path)


@pytest.mark.parametrize("schema_version", [True, 1.0])
def test_rejects_schema_version_values_that_are_not_integer_one(
    tmp_path: Path, schema_version: object
) -> None:
    source = tmp_path / "invalid.yaml"
    source.write_text(
        yaml.safe_dump(
            {"schema_version": schema_version, "dataset_version": "2026.09.1", "cases": [_case("invalid")]},
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="schema_version must be exactly 1"):
        load_cases(tmp_path)


def test_rejects_unknown_case_fields(tmp_path: Path) -> None:
    case = _case("unknown-field")
    case["expectatons"] = {"equals": {"intent": "code_generation"}}
    _write_yaml(tmp_path / "cases.yaml", "2026.09.1", [case])

    with pytest.raises(ValueError, match="expectatons"):
        load_cases(tmp_path)


def test_explicit_asset_root_error_names_asset_root(tmp_path: Path) -> None:
    source = tmp_path / "cases.yaml"
    assets = tmp_path / "assets"
    assets.mkdir()
    _write_yaml(source, "2026.09.1", [_case("asset-escape", record="outside.json")])

    with pytest.raises(ValueError, match="outside asset root"):
        load_cases(tmp_path, asset_root=assets)


def test_malformed_yaml_error_includes_source_path(tmp_path: Path) -> None:
    source = tmp_path / "malformed.yaml"
    source.write_text("schema_version: [", encoding="utf-8")

    with pytest.raises(ValueError, match=re.escape(str(source))):
        load_cases(tmp_path)


@pytest.mark.parametrize(("reviewed", "sanitized"), [(False, True), (True, False), (False, False)])
def test_formal_loader_rejects_unreviewed_or_unsanitized_cases_by_default(
    tmp_path: Path, reviewed: bool, sanitized: bool
) -> None:
    case = _case("private-case")
    case["provenance"] = {
        "source": "sanitized_user",
        "reviewed": reviewed,
        "sanitized": sanitized,
    }
    _write_yaml(tmp_path / "cases.yaml", "2026.09.1", [case])

    with pytest.raises(ValueError, match="must be reviewed and sanitized"):
        load_cases(tmp_path)


def test_loader_allows_unreviewed_cases_only_when_explicitly_enabled(tmp_path: Path) -> None:
    case = _case("development-case")
    case["provenance"] = {
        "source": "sanitized_user",
        "reviewed": False,
        "sanitized": False,
    }
    _write_yaml(tmp_path / "cases.yaml", "dev", [case])

    loaded = load_cases(tmp_path, allow_unreviewed=True)

    assert loaded[0].case.id == "development-case"
    assert loaded[0].case.provenance.reviewed is False
    assert loaded[0].case.provenance.sanitized is False
