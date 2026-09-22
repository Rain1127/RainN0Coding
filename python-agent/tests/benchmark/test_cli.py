from __future__ import annotations

import json
from pathlib import Path

from benchmark.cli import _load_cases, main
from benchmark.config import load_suite
from benchmark.contracts import BenchmarkCase, LoadedCase, RawRunRecord
from benchmark.orchestrator import RUNNERS, run_cases
from benchmark.runners.base import RunContext


SUITE = "benchmarks/suites/pr.yaml"


def test_validate_pr_suite_prints_validated(capsys) -> None:
    assert main(["validate", "--suite", SUITE]) == 0
    assert capsys.readouterr().out == "validated 6 benchmark cases for suite pr\n"


def test_run_pr_suite_writes_report_metadata_and_raw_records(tmp_path: Path) -> None:
    output = tmp_path / "pr-result.json"
    record_dir = tmp_path / "records"

    assert main([
        "run", "--suite", SUITE, "--output", str(output), "--git-sha", "test-sha",
        "--record-dir", str(record_dir),
    ]) == 0

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["metadata"]["git_sha"] == "test-sha"
    assert report["summary"]["cases"] == 6
    assert len(list(record_dir.glob("*/*.json"))) == 6


def test_run_uses_default_record_directory_relative_to_current_directory(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "result.json"
    suite = Path(__file__).resolve().parents[2] / SUITE
    monkeypatch.chdir(tmp_path)

    assert main(["run", "--suite", str(suite), "--output", str(output), "--git-sha", "test-sha"]) == 0

    assert len(list((tmp_path / "benchmarks" / "records" / "runs").glob("*/*.json"))) == 6


def _loaded(case_id: str, mode: str = "deterministic") -> LoadedCase:
    return LoadedCase(
        case=BenchmarkCase.model_validate({
            "id": case_id,
            "dataset_version": "test",
            "target": "supervisor",
            "category": "routing",
            "execution": {"mode": mode},
            "input": {"phase": "review_done", "review": {"passed": True}},
            "provenance": {"source": "synthetic", "reviewed": True, "sanitized": True},
        }),
        source_path=Path("case.yaml"),
    )


def test_run_cases_isolates_persist_and_evaluation_failures(monkeypatch, tmp_path: Path) -> None:
    import benchmark.orchestrator as orchestrator

    class FakeRunner:
        def run(self, case: LoadedCase, context: RunContext) -> list[RawRunRecord]:
            return [RawRunRecord(case_id=case.case.id, output={"next_node": "builder_agent"}, started_at="2026-01-01T00:00:00+00:00", duration_ms=1)]

    persisted: list[str] = []
    original_persist = orchestrator.persist_raw_record

    def flaky_persist(record_dir: Path, run_id: str, record: RawRunRecord) -> Path:
        persisted.append(record.case_id)
        if record.case_id == "first" and persisted.count("first") == 1:
            raise OSError("disk full")
        return original_persist(record_dir, run_id, record)

    original_evaluate = orchestrator.evaluate_assertions

    def flaky_evaluate(*args, **kwargs):
        if args[0].id == "second":
            raise RuntimeError("bad evaluator")
        return original_evaluate(*args, **kwargs)

    monkeypatch.setitem(RUNNERS, "deterministic", FakeRunner())
    monkeypatch.setattr(orchestrator, "persist_raw_record", flaky_persist)
    monkeypatch.setattr(orchestrator, "evaluate_assertions", flaky_evaluate)

    results = run_cases([_loaded("first"), _loaded("second")], RunContext("run", True, tmp_path))

    assert [result.case_id for result in results] == ["first", "second"]
    assert all(result.infrastructure_error for result in results)
    assert persisted == ["first", "first", "second", "second"]
    assert len(list((tmp_path / "run").glob("*.json"))) == 2


def test_cli_infrastructure_error_is_printed_to_stdout(tmp_path: Path, capsys) -> None:
    assert main(["validate", "--suite", str(tmp_path / "missing.yaml")]) == 2
    captured = capsys.readouterr()
    assert captured.out.startswith("benchmark infrastructure error: ")
    assert captured.err == ""


def test_disallowed_modes_message_uses_sorted_list_representation() -> None:
    suite, suite_dir = load_suite(SUITE)
    restricted = suite.model_copy(update={"allowed_modes": ["deterministic"]})

    try:
        _load_cases(restricted, suite_dir)
    except ValueError as exc:
        assert str(exc) == "suite contains disallowed modes: ['replay']"
    else:
        raise AssertionError("expected disallowed replay mode")


def test_missing_runner_message_is_exact() -> None:
    result = run_cases([_loaded("unregistered", "rag")], RunContext("run", True))

    assert result[0].infrastructure_error == "runner is not registered for mode: rag"
