import json
import pytest
from pydantic import ValidationError
import math

from benchmark.contracts import BenchmarkReport, CaseEvaluation, RunMetadata
from benchmark.evaluators.metrics import describe
from benchmark.reporting.json_report import build_report, read_report, write_report
from benchmark.redaction import redact


def _evaluation(case_id: str, attempt: int, passed: bool, latency: float) -> CaseEvaluation:
    return CaseEvaluation(
        case_id=case_id, attempt_index=attempt, target="supervisor", category="routing",
        passed=passed, assertions_passed=1 if passed else 0, assertions_total=1,
        assertions=[], observed_metrics={"latency_ms": latency, "cost_usd": None},
    )


def test_run_metadata_carries_reproducibility_fields():
    metadata = RunMetadata(
        report_schema_version=1, run_id="run-1", suite="suite-1", git_sha="abc123",
        dataset_versions=["data-1"], dataset_fingerprint="sha-data", prompt_fingerprint="sha-prompt",
        model_aliases={"default": "offline"}, offline=True, started_at="2026-09-22T00:00:00+00:00",
    )
    assert metadata.run_id == "run-1" and metadata.offline is True


def test_run_metadata_requires_model_aliases():
    with pytest.raises(ValidationError):
        RunMetadata(run_id="run-1", suite="suite", git_sha="abc", dataset_versions=["d"], dataset_fingerprint="df", prompt_fingerprint="pf", offline=True, started_at="now")


def test_report_group_statistics_reject_strings():
    with pytest.raises(ValidationError):
        BenchmarkReport(metadata=RunMetadata(run_id="r", suite="s", git_sha="g", dataset_versions=["d"], dataset_fingerprint="df", prompt_fingerprint="pf", model_aliases={}, offline=True, started_at="now"), summary={}, by_target={"supervisor": {"cases": "two"}}, by_category={}, metrics={}, results=[])


def test_case_evaluation_metrics_are_finite_numbers_or_none():
    valid = _evaluation("case-a", 0, True, 10)
    assert valid.observed_metrics["latency_ms"] == 10.0
    with pytest.raises(ValidationError):
        _evaluation("case-a", 0, True, math.nan)
    with pytest.raises(ValidationError):
        CaseEvaluation(case_id="a", target="supervisor", category="routing", passed=True, assertions_passed=0, assertions_total=0, observed_metrics={"x": True})


def test_build_report_preserves_none_metrics_and_rejects_duplicate_attempts():
    metadata = RunMetadata(run_id="r", suite="s", git_sha="g", dataset_versions=["d"], dataset_fingerprint="df", prompt_fingerprint="pf", model_aliases={}, offline=True, started_at="now")
    report = build_report(metadata, [_evaluation("a", 0, True, 10)])
    assert report.results[0].observed_metrics["cost_usd"] is None
    assert "cost_usd" not in report.metrics
    with pytest.raises(ValueError, match="duplicate"):
        build_report(metadata, [_evaluation("a", 0, True, 10), _evaluation("a", 0, True, 11)])


def test_write_report_redacts_nested_credentials_but_not_client_id(tmp_path):
    metadata = RunMetadata(run_id="r", suite="s", git_sha="g", dataset_versions=["d"], dataset_fingerprint="df", prompt_fingerprint="pf", model_aliases={}, offline=True, started_at="now")
    result = _evaluation("a", 0, True, 10).model_copy(update={"output": {"refresh_token": "refresh", "auth_token": "auth", "private_key": "key", "client_id": "keep"}})
    path = tmp_path / "report.json"
    write_report(build_report(metadata, [result]), path)
    text = path.read_text(encoding="utf-8")
    assert all(f'"{secret}"' not in text for secret in ("refresh", "auth", "key")) and "keep" in text


def test_write_report_redacts_camel_case_credentials(tmp_path):
    metadata = RunMetadata(run_id="r", suite="s", git_sha="g", dataset_versions=["d"], dataset_fingerprint="df", prompt_fingerprint="pf", model_aliases={}, offline=True, started_at="now")
    result = _evaluation("a", 0, True, 10).model_copy(update={"output": {"refreshToken": "refresh-value", "authToken": "auth-value", "accessToken": "access-value", "apiKey": "api-value", "privateKey": "private-value", "clientId": "safe-id"}})
    path = tmp_path / "report.json"
    write_report(build_report(metadata, [result]), path)
    text = path.read_text(encoding="utf-8")
    assert all(value not in text for value in ("refresh-value", "auth-value", "access-value", "api-value", "private-value"))
    assert "safe-id" in text


def test_write_report_is_canonical_across_mapping_insertion_order(tmp_path):
    metadata_a = RunMetadata(run_id="r", suite="s", git_sha="g", dataset_versions=["d"], dataset_fingerprint="df", prompt_fingerprint="pf", model_aliases={"z": "Z", "a": "A"}, offline=True, started_at="now")
    metadata_b = metadata_a.model_copy(update={"model_aliases": {"a": "A", "z": "Z"}})
    output_a = {"z": 1, "a": {"y": 2, "x": 3}}
    output_b = {"a": {"x": 3, "y": 2}, "z": 1}
    result_a = _evaluation("a", 0, True, 10).model_copy(update={"output": output_a})
    result_b = _evaluation("a", 0, True, 10).model_copy(update={"output": output_b})
    path_a, path_b = tmp_path / "a.json", tmp_path / "b.json"
    write_report(build_report(metadata_a, [result_a], gate={"z": 1, "a": {"b": 2, "a": 3}}), path_a)
    write_report(build_report(metadata_b, [result_b], gate={"a": {"a": 3, "b": 2}, "z": 1}), path_b)
    assert path_a.read_bytes() == path_b.read_bytes()


def test_report_is_deep_snapshot_and_canonical_sorted():
    metadata = RunMetadata(run_id="r", suite="s", git_sha="g", dataset_versions=["d"], dataset_fingerprint="df", prompt_fingerprint="pf", model_aliases={}, offline=True, started_at="now")
    first = _evaluation("b", 1, True, 20)
    second = _evaluation("a", 0, True, 10)
    report = build_report(metadata, [first, second])
    first.output["changed"] = True
    first.observed_metrics["latency_ms"] = 99
    assert [item.case_id for item in report.results] == ["a", "b"]
    assert "changed" not in report.results[1].output and report.results[1].observed_metrics["latency_ms"] == 20.0


def test_describe_empty_values_raise_value_error():
    with pytest.raises(ValueError, match="at least one"):
        describe([])


def test_build_write_read_report_aggregates_cases_and_metrics(tmp_path):
    metadata = RunMetadata(
        run_id="run-1", suite="suite-1", git_sha="abc", dataset_versions=["data-1"],
        dataset_fingerprint="d", prompt_fingerprint="p", model_aliases={}, offline=True,
        started_at="2026-09-22T00:00:00+00:00",
    )
    report = build_report(metadata, [_evaluation("case-a", 0, True, 10), _evaluation("case-b", 0, False, 30)])
    assert report.summary == {"cases": 2, "passed": 1, "case_pass_rate": 0.5, "observations": 2, "passed_observations": 1, "observation_pass_rate": 0.5, "assertion_pass_rate": 0.5}
    assert report.metrics["latency_ms"]["p50"] == 10
    assert report.metrics["latency_ms"]["p95"] == 30
    assert "cost_usd" not in report.metrics
    path = tmp_path / "nested" / "report.json"
    write_report(report, path)
    loaded = read_report(path)
    assert loaded.summary["case_pass_rate"] == 0.5
    assert '"cost_usd": null' in path.read_text(encoding="utf-8")


def test_report_redacts_secrets_recursively():
    value = {"api_key": "sk-secret-value", "message": "Bearer abcdef123456", "nested": [{"password": "pw"}]}
    redacted = redact(value)
    assert redacted["api_key"] == "***REDACTED***"
    assert "sk-secret-value" not in json.dumps(redacted)
    assert "Bearer abcdef123456" not in json.dumps(redacted)
    assert redacted["nested"][0]["password"] == "***REDACTED***"


def test_write_report_redacts_secrets_in_persisted_json(tmp_path):
    metadata = RunMetadata(run_id="run-1", suite="suite", git_sha="abc", dataset_versions=["d"], dataset_fingerprint="df", prompt_fingerprint="pf", model_aliases={}, offline=True, started_at="now")
    result = _evaluation("case-a", 0, True, 10).model_copy(update={"output": {"api_key": "sk-secret-value", "message": "Bearer abcdef123456"}})
    path = tmp_path / "report.json"
    write_report(build_report(metadata, [result]), path)
    text = path.read_text(encoding="utf-8")
    assert "sk-secret-value" not in text and "abcdef123456" not in text


def test_describe_uses_nearest_rank_percentiles():
    assert describe([10, 20, 30, 40]) == {
        "observations": 4, "sum": 100.0, "mean": 25.0, "min": 10.0,
        "max": 40.0, "p50": 20.0, "p95": 40.0, "stdev": 11.180339887498949,
    }
