import json

from benchmark.contracts import CaseEvaluation, RunMetadata
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
        report_schema_version=1, run_id="run-1", suite_version="suite-1", git_sha="abc123",
        dataset_version="data-1", dataset_fingerprint="sha-data", prompt_fingerprint="sha-prompt",
        model_aliases={"default": "offline"}, offline=True, started_at="2026-09-22T00:00:00+00:00",
    )
    assert metadata.run_id == "run-1" and metadata.offline is True


def test_build_write_read_report_aggregates_cases_and_metrics(tmp_path):
    metadata = RunMetadata(
        run_id="run-1", suite_version="suite-1", git_sha="abc", dataset_version="data-1",
        dataset_fingerprint="d", prompt_fingerprint="p", model_aliases={}, offline=True,
        started_at="2026-09-22T00:00:00+00:00",
    )
    report = build_report(metadata, [_evaluation("case-a", 0, True, 10), _evaluation("case-b", 0, False, 30)])
    assert report.summary["case_pass_rate"] == 0.5
    assert report.metrics["latency_ms"]["p50"] == 10
    assert report.metrics["latency_ms"]["p95"] == 30
    assert "cost_usd" not in report.metrics
    path = tmp_path / "nested" / "report.json"
    write_report(report, path)
    loaded = read_report(path)
    assert loaded.summary["case_pass_rate"] == 0.5
    assert "cost_usd" not in path.read_text(encoding="utf-8")


def test_report_redacts_secrets_recursively():
    value = {"api_key": "sk-secret-value", "message": "Bearer abcdef123456", "nested": [{"password": "pw"}]}
    redacted = redact(value)
    assert redacted["api_key"] == "***REDACTED***"
    assert "sk-secret-value" not in json.dumps(redacted)
    assert "Bearer abcdef123456" not in json.dumps(redacted)
    assert redacted["nested"][0]["password"] == "***REDACTED***"


def test_describe_uses_nearest_rank_percentiles():
    assert describe([10, 20, 30, 40]) == {
        "observations": 4, "sum": 100.0, "mean": 25.0, "min": 10.0,
        "max": 40.0, "p50": 20.0, "p95": 40.0, "pstdev": 11.180339887498949,
    }
