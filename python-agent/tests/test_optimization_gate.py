from pathlib import Path
import pytest
import yaml
from benchmark.gates import evaluate_gate
from benchmark.reporting.json_report import read_report

pytestmark = pytest.mark.benchmark


def test_fixed_baseline_rejects_quality_drop_and_missing_baseline():
    root=Path(__file__).resolve().parents[2]
    baseline=read_report(root / "python-agent/benchmarks/baselines/501811a5c8501b63/baseline.json")
    policy=yaml.safe_load((root / "python-agent/benchmarks/policies/default.yaml").read_text())
    candidate=baseline.model_copy(update={"summary":{**baseline.summary,"case_pass_rate":0.8}})
    gate=evaluate_gate(candidate,baseline,policy)
    assert not gate["passed"]
    assert any(f["type"]=="regression" and f["metric"]=="case_pass_rate" for f in gate["failures"])
    assert any(f["type"]=="no_baseline" for f in evaluate_gate(baseline,None,policy)["failures"])


def test_missing_required_metric_is_explicit():
    root=Path(__file__).resolve().parents[2]
    baseline=read_report(root / "python-agent/benchmarks/baselines/501811a5c8501b63/baseline.json")
    with pytest.raises(ValueError,match="missing"):
        evaluate_gate(baseline,baseline,{"regression_thresholds":{"runtime_pass_rate":{"max_drop":0}}})
