from __future__ import annotations

import json
from pathlib import Path

from benchmark.cli import _git_sha, _load_cases, _prompt_fingerprint, main
from benchmark.config import load_suite
from benchmark.contracts import BenchmarkCase, LoadedCase, RawRunRecord, RunMetadata
from benchmark.orchestrator import RUNNERS, run_cases
from benchmark.redaction import redact_error
from benchmark.reporting.json_report import build_report
from benchmark.reporting.json_report import write_report
from benchmark.runners.base import RunContext


SUITE = "benchmarks/suites/pr.yaml"


def test_validate_pr_suite_prints_validated(capsys) -> None:
    assert main(["validate", "--suite", SUITE]) == 0
    assert capsys.readouterr().out == "validated 6 benchmark cases for suite pr\n"


def test_run_pr_suite_writes_report_metadata_and_raw_records(tmp_path: Path) -> None:
    output = tmp_path / "pr-result.json"
    html_output = tmp_path / "pr-report.html"
    record_dir = tmp_path / "records"

    assert main([
        "run", "--suite", SUITE, "--output", str(output), "--git-sha", "test-sha",
        "--record-dir", str(record_dir), "--html-output", str(html_output),
    ]) == 0

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["metadata"]["git_sha"] == "test-sha"
    assert report["summary"]["cases"] == 6
    assert len(list(record_dir.glob("*/*.json"))) == 6
    assert "test-sha" in html_output.read_text(encoding="utf-8")


def test_run_derives_html_output_as_json_sibling(tmp_path: Path) -> None:
    output = tmp_path / "result.json"

    assert main(["run", "--suite", SUITE, "--output", str(output), "--git-sha", "test-sha", "--record-dir", str(tmp_path / "records")]) == 0

    assert (tmp_path / "result.html").is_file()


def test_run_keeps_json_when_html_rendering_fails(tmp_path: Path, monkeypatch) -> None:
    import benchmark.cli as cli

    output = tmp_path / "result.json"

    def fail_render(*args, **kwargs) -> None:
        raise OSError("render failed")

    monkeypatch.setattr(cli, "render_html", fail_render)

    assert main(["run", "--suite", SUITE, "--output", str(output), "--git-sha", "test-sha", "--record-dir", str(tmp_path / "records")]) == 2

    assert json.loads(output.read_text(encoding="utf-8"))["metadata"]["git_sha"] == "test-sha"


def test_run_uses_default_record_directory_relative_to_current_directory(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "result.json"
    suite = Path(__file__).resolve().parents[2] / SUITE
    monkeypatch.chdir(tmp_path)

    assert main(["run", "--suite", str(suite), "--output", str(output), "--git-sha", "test-sha"]) == 0

    assert len(list((tmp_path / "benchmarks" / "records" / "runs").glob("*/*.json"))) == 6


def _loaded(case_id: str, mode: str = "deterministic", repeats: int = 1) -> LoadedCase:
    return LoadedCase(
        case=BenchmarkCase.model_validate({
            "id": case_id,
            "dataset_version": "test",
            "target": "supervisor",
            "category": "routing",
            "execution": {"mode": mode, "repeats": repeats},
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
    assert persisted == ["first", "first", "second"]
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


def test_suite_skips_future_dataset_root_when_a_valid_root_exists() -> None:
    suite, suite_dir = load_suite(SUITE)
    configured = "missing-dataset"
    staged = suite.model_copy(update={"dataset_roots": [configured, "../datasets/regression"]})

    assert len(_load_cases(staged, suite_dir)) == 6


def test_suite_fails_only_when_all_configured_dataset_roots_are_missing() -> None:
    suite, suite_dir = load_suite(SUITE)
    staged = suite.model_copy(update={"dataset_roots": ["missing-one", "missing-two"]})

    try:
        _load_cases(staged, suite_dir)
    except ValueError as exc:
        assert str(exc) == "suite contains no benchmark cases from existing dataset roots"
    else:
        raise AssertionError("expected no benchmark cases")


def test_prompt_fingerprint_requires_fixed_files(tmp_path: Path) -> None:
    (tmp_path / "agents").mkdir()
    (tmp_path / "llm_factory.py").write_text("x", encoding="utf-8")

    try:
        _prompt_fingerprint(tmp_path)
    except ValueError as exc:
        assert "workflow/autogen_discussion.py" in str(exc)
    else:
        raise AssertionError("expected missing fixed prompt file")


def test_git_sha_uses_repository_root(monkeypatch) -> None:
    import benchmark.cli as cli

    seen: dict[str, object] = {}

    def fake_check_output(command, **kwargs):
        seen.update(kwargs)
        return "abc\n"

    monkeypatch.setattr(cli.subprocess, "check_output", fake_check_output)
    assert _git_sha() == "abc"
    assert seen["cwd"] == Path(cli.__file__).resolve().parents[2]
    assert seen["encoding"] == "utf-8"


def test_orchestrator_rejects_malformed_runner_attempts(monkeypatch) -> None:
    class DuplicateAttemptRunner:
        def run(self, case: LoadedCase, context: RunContext) -> list[RawRunRecord]:
            return [
                RawRunRecord(case_id=case.case.id, attempt_index=0, started_at="2026-01-01T00:00:00+00:00", duration_ms=0),
                RawRunRecord(case_id=case.case.id, attempt_index=0, started_at="2026-01-01T00:00:00+00:00", duration_ms=0),
            ]

    monkeypatch.setitem(RUNNERS, "deterministic", DuplicateAttemptRunner())
    result = run_cases([_loaded("bad-attempts", repeats=2)], RunContext("run", True))

    assert len(result) == 1
    assert result[0].attempt_index == 0
    assert "attempt indexes" in result[0].infrastructure_error


def test_orchestrator_rejects_missing_runner_attempt(monkeypatch) -> None:
    class MissingAttemptRunner:
        def run(self, case: LoadedCase, context: RunContext) -> list[RawRunRecord]:
            return [RawRunRecord(case_id=case.case.id, attempt_index=1, started_at="2026-01-01T00:00:00+00:00", duration_ms=0)]

    monkeypatch.setitem(RUNNERS, "deterministic", MissingAttemptRunner())
    result = run_cases([_loaded("missing-attempt", repeats=2)], RunContext("run", True))

    assert len(result) == 1
    assert result[0].attempt_index == 0
    assert "attempt indexes" in result[0].infrastructure_error


def test_orchestrator_keeps_later_attempts_after_partial_record_failure(monkeypatch) -> None:
    import benchmark.orchestrator as orchestrator

    class ThreeAttemptRunner:
        def run(self, case: LoadedCase, context: RunContext) -> list[RawRunRecord]:
            return [RawRunRecord(case_id=case.case.id, attempt_index=index, output={"next_node": "builder_agent"}, started_at="2026-01-01T00:00:00+00:00", duration_ms=0) for index in range(3)]

    original_evaluate = orchestrator.evaluate_assertions

    def flaky_evaluate(*args, **kwargs):
        if kwargs["attempt_index"] == 1:
            raise RuntimeError("password=hunter2")
        return original_evaluate(*args, **kwargs)

    monkeypatch.setitem(RUNNERS, "deterministic", ThreeAttemptRunner())
    monkeypatch.setattr(orchestrator, "evaluate_assertions", flaky_evaluate)
    results = run_cases([_loaded("partial", repeats=3)], RunContext("run", True))

    assert [result.attempt_index for result in results] == [0, 1, 2]
    assert results[1].infrastructure_error == "password=***REDACTED***"
    assert build_report(RunMetadata(run_id="r", suite="s", git_sha="g", dataset_versions=[], dataset_fingerprint="d", prompt_fingerprint="p", model_aliases={}, offline=True, started_at="now"), results).summary["observations"] == 3


def test_evaluation_failure_persists_only_redacted_fallback_record(monkeypatch, tmp_path: Path) -> None:
    import benchmark.orchestrator as orchestrator

    class TwoAttemptRunner:
        def run(self, case: LoadedCase, context: RunContext) -> list[RawRunRecord]:
            return [
                RawRunRecord(case_id=case.case.id, attempt_index=index, output={"secret": "hunter2"}, started_at="2026-01-01T00:00:00+00:00", duration_ms=0)
                for index in range(2)
            ]

    original_evaluate = orchestrator.evaluate_assertions

    def failing_evaluate(*args, **kwargs):
        if kwargs["attempt_index"] == 0:
            raise RuntimeError("password=hunter2")
        return original_evaluate(*args, **kwargs)

    monkeypatch.setitem(RUNNERS, "deterministic", TwoAttemptRunner())
    monkeypatch.setattr(orchestrator, "evaluate_assertions", failing_evaluate)

    results = run_cases([_loaded("evaluation-failure", repeats=2)], RunContext("run", True, tmp_path))

    records = sorted(tmp_path.joinpath("run").glob("*.json"))
    assert len(records) == 2
    first = json.loads(records[0].read_text(encoding="utf-8"))
    assert first["attempt_index"] == 0
    assert first["infrastructure_error"] == "password=***REDACTED***"
    assert "secret" not in first["output"]
    assert [result.attempt_index for result in results] == [0, 1]


def test_error_redaction_hides_key_value_colon_and_basic_credentials() -> None:
    redacted = redact_error("password=hunter2 apiKey: abc123 Authorization: Basic topsecret")

    assert "hunter2" not in redacted
    assert "abc123" not in redacted
    assert "topsecret" not in redacted
    assert redacted.count("***REDACTED***") >= 3


def test_compare_returns_zero_and_records_passing_gate(tmp_path: Path) -> None:
    candidate = build_report(RunMetadata(run_id="candidate", suite="s", git_sha="new", dataset_versions=["v"], dataset_fingerprint="d", prompt_fingerprint="p", model_aliases={}, offline=True, started_at="now"), [])
    baseline = candidate.model_copy(update={"metadata": candidate.metadata.model_copy(update={"run_id": "baseline", "git_sha": "old"})})
    candidate_path, baseline_path, policy_path = tmp_path / "candidate.json", tmp_path / "baseline.json", tmp_path / "policy.yaml"
    write_report(candidate, candidate_path)
    write_report(baseline, baseline_path)
    policy_path.write_text("absolute_thresholds: {}\nregression_thresholds: {}\n", encoding="utf-8")

    assert main(["compare", "--candidate", str(candidate_path), "--baseline", str(baseline_path), "--policy", str(policy_path)]) == 0
    assert json.loads(candidate_path.read_text(encoding="utf-8"))["gate"]["passed"] is True


def test_compare_keeps_unrelated_fixed_tmp_file(tmp_path: Path) -> None:
    candidate = build_report(RunMetadata(run_id="candidate", suite="s", git_sha="new", dataset_versions=["v"], dataset_fingerprint="d", prompt_fingerprint="p", model_aliases={}, offline=True, started_at="now"), [])
    baseline = candidate.model_copy(update={"metadata": candidate.metadata.model_copy(update={"run_id": "baseline", "git_sha": "old"})})
    candidate_path, baseline_path, policy_path = tmp_path / "candidate.json", tmp_path / "baseline.json", tmp_path / "policy.yaml"
    write_report(candidate, candidate_path)
    write_report(baseline, baseline_path)
    policy_path.write_text("absolute_thresholds: {}\nregression_thresholds: {}\n", encoding="utf-8")
    unrelated = candidate_path.with_name(candidate_path.name + ".tmp")
    unrelated.write_text("keep", encoding="utf-8")

    assert main(["compare", "--candidate", str(candidate_path), "--baseline", str(baseline_path), "--policy", str(policy_path)]) == 0
    assert unrelated.read_text(encoding="utf-8") == "keep"


def test_compare_returns_one_for_regression_and_two_for_incompatible(tmp_path: Path) -> None:
    candidate = build_report(RunMetadata(run_id="candidate", suite="s", git_sha="new", dataset_versions=["v"], dataset_fingerprint="d", prompt_fingerprint="p", model_aliases={}, offline=True, started_at="now"), [])
    baseline = candidate.model_copy(update={"metadata": candidate.metadata.model_copy(update={"run_id": "baseline", "git_sha": "old"})})
    candidate_path, baseline_path, policy_path = tmp_path / "candidate.json", tmp_path / "baseline.json", tmp_path / "policy.yaml"
    write_report(candidate, candidate_path)
    write_report(baseline, baseline_path)
    policy_path.write_text("absolute_thresholds:\n  case_pass_rate:\n    min: 1.1\nregression_thresholds: {}\n", encoding="utf-8")
    assert main(["compare", "--candidate", str(candidate_path), "--baseline", str(baseline_path), "--policy", str(policy_path)]) == 1
    incompatible = baseline.model_copy(update={"metadata": baseline.metadata.model_copy(update={"suite": "other"})})
    write_report(incompatible, baseline_path)
    assert main(["compare", "--candidate", str(candidate_path), "--baseline", str(baseline_path), "--policy", str(policy_path)]) == 2


def test_baseline_promote_returns_two_on_overwrite(tmp_path: Path) -> None:
    report = build_report(RunMetadata(run_id="candidate", suite="s", git_sha="new", dataset_versions=["v"], dataset_fingerprint="d", prompt_fingerprint="p", model_aliases={}, offline=True, started_at="now"), [])
    report_path = tmp_path / "report.json"
    write_report(report, report_path)
    arguments = ["baseline", "promote", "--report", str(report_path), "--baseline-dir", str(tmp_path / "baselines")]
    assert main(arguments) == 0
    assert main(arguments) == 2


def _write_run_assets(tmp_path: Path, *, target: str, expected_node: str, policy: str) -> tuple[Path, Path]:
    suite = tmp_path / "suite.yaml"
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    suite.write_text(
        "schema_version: 1\nname: temporary\ndataset_roots: [dataset]\nallowed_modes: [deterministic]\n"
        "offline: true\nfail_on_infrastructure_error: true\npolicy: policy.yaml\nbaseline_dir: baselines\n",
        encoding="utf-8",
    )
    (tmp_path / "policy.yaml").write_text(policy, encoding="utf-8")
    (dataset / "case.yaml").write_text(
        "schema_version: 1\ndataset_version: test\ncases:\n"
        "- id: temporary-case\n  target: " + target + "\n  category: routing\n"
        "  execution: {mode: deterministic}\n"
        "  input: {phase: review_done, review: {passed: true}, retry_count: 0, max_retries: 3}\n"
        "  expectations:\n    equals: {next_node: " + expected_node + "}\n"
        "  metric_tags: {equals.next_node: route_accuracy}\n"
        "  provenance: {source: synthetic, reviewed: true, sanitized: true}\n",
        encoding="utf-8",
    )
    return suite, tmp_path / "report.json"


def test_run_returns_one_and_writes_gate_for_hard_assertion_failure(tmp_path: Path) -> None:
    suite, output = _write_run_assets(
        tmp_path, target="supervisor", expected_node="coder_agent",
        policy="hard_fail_metrics: [route_accuracy]\nabsolute_thresholds: {}\nregression_thresholds: {}\n",
    )

    assert main(["run", "--suite", str(suite), "--output", str(output), "--git-sha", "test-sha", "--record-dir", str(tmp_path / "records")]) == 1

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["gate"]["passed"] is False
    assert report["results"][0]["infrastructure_error"] is None


def test_run_returns_two_and_writes_report_for_runner_infrastructure_failure(tmp_path: Path) -> None:
    suite, output = _write_run_assets(
        tmp_path, target="intent", expected_node="builder_agent",
        policy="hard_fail_metrics: []\nabsolute_thresholds: {}\nregression_thresholds: {}\n",
    )

    assert main(["run", "--suite", str(suite), "--output", str(output), "--git-sha", "test-sha", "--record-dir", str(tmp_path / "records")]) == 2

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["results"][0]["infrastructure_error"] == "no deterministic adapter for intent"
