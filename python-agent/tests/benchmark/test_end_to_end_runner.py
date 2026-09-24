from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

from benchmark.contracts import BenchmarkCase, LoadedCase, RunMetadata
from benchmark.evaluators.assertions import evaluate_assertions
from benchmark.gates import evaluate_gate
from benchmark.runners.base import RunContext
from benchmark.runners.end_to_end import EndToEndRunner
from benchmark.cli import _load_cases
from benchmark.config import load_suite
from benchmark.orchestrator import run_cases
from benchmark.reporting.json_report import build_report


def _state(*, content: str = "<main>benchmark ready</main>") -> dict:
    return {
        "phase": "completed",
        "final_status": "success",
        "intent": {"primary_intent": "create_web_page"},
        "code_files": [{"path": "index.html", "content": content}],
        "review": {"passed": True, "score": 92, "issues": []},
        "quality_gate_result": {"passed": True, "review_score": 92},
        "build_result": {"success": True, "log": "offline fixture"},
    }


def _loaded(
    tmp_path: Path,
    *,
    state: object | None = None,
    mode: str = "e2e",
    target: str = "e2e",
    repeats: int = 1,
    input_data: dict | None = None,
    expectations: dict | None = None,
    metric_tags: dict[str, str] | None = None,
) -> LoadedCase:
    record = tmp_path / "state.json"
    record.write_text(json.dumps({"output": _state() if state is None else state}), encoding="utf-8")
    case = BenchmarkCase.model_validate(
        {
            "id": "e2e-fixture",
            "dataset_version": "test",
            "target": target,
            "category": "workflow",
            "execution": {"mode": mode, "record": "state.json", "repeats": repeats},
            "input": input_data or {},
            "expectations": expectations
            or {
                "equals": {
                    "phase": "completed",
                    "final_status": "success",
                    "review.passed": True,
                    "quality_gate_result.passed": True,
                    "build_result.success": True,
                    "benchmark_required_files.passed": True,
                },
                "required_files": ["index.html"],
            },
            "metric_tags": metric_tags or {},
            "provenance": {"source": "curated", "reviewed": True, "sanitized": True},
        }
    )
    return LoadedCase(case=case, source_path=tmp_path / "case.yaml", record_path=record)


def test_saved_successful_workflow_passes_declarative_assertions(tmp_path: Path) -> None:
    loaded = _loaded(tmp_path)

    record = EndToEndRunner().run(loaded, RunContext("run", True))[0]
    evaluation = evaluate_assertions(loaded.case, record.output, record.observed_metrics)

    assert record.infrastructure_error is None
    assert record.output["benchmark_required_files"] == {"passed": True, "missing": []}
    assert evaluation.passed is True


def test_pr_e2e_fixture_runs_offline_and_passes_build_gate() -> None:
    suite_path = Path(__file__).resolve().parents[2] / "benchmarks" / "suites" / "pr.yaml"
    suite, suite_dir = load_suite(suite_path)
    loaded = next(item for item in _load_cases(suite, suite_dir) if item.case.id == "e2e-valid-html-replay")

    result = run_cases([loaded], RunContext("run", True))[0]

    assert result.infrastructure_error is None
    assert result.passed is True
    assert result.output["benchmark_code_check"]["passed"] is True
    build_assertion = next(item for item in result.assertions if item.path == "benchmark_code_check.passed")
    assert build_assertion.metric == "build_failed"


def test_saved_success_state_uses_the_reviewed_valid_html_fixture() -> None:
    fixtures = Path(__file__).resolve().parents[2] / "benchmarks" / "fixtures"
    state = json.loads((fixtures / "e2e" / "success.json").read_text(encoding="utf-8"))["output"]
    valid_html = (fixtures / "projects" / "valid-html" / "index.html").read_text(encoding="utf-8")

    assert state["code_files"] == [{"path": "index.html", "content": valid_html}]


def test_invalid_python_build_failure_triggers_the_default_hard_gate(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    invalid_python = (root / "benchmarks" / "fixtures" / "projects" / "invalid-python" / "main.py").read_text(
        encoding="utf-8"
    )
    state = _state(content=invalid_python)
    state["code_files"] = [{"path": "main.py", "content": invalid_python}]
    loaded = _loaded(
        tmp_path,
        state=state,
        input_data={
            "execution_command": [sys.executable, "-m", "py_compile", "main.py"],
            "timeout_seconds": 10,
        },
        expectations={
            "equals": {"benchmark_code_check.passed": True},
            "required_files": ["main.py"],
        },
        metric_tags={"equals.benchmark_code_check.passed": "build_failed"},
    )

    evaluation = run_cases([loaded], RunContext("run", True))[0]
    report = build_report(
        RunMetadata(
            run_id="run",
            suite="test",
            git_sha="test",
            dataset_versions=["test"],
            dataset_fingerprint="test",
            prompt_fingerprint="test",
            model_aliases={},
            offline=True,
            started_at="2026-09-24T00:00:00+00:00",
        ),
        [evaluation],
    )
    policy = yaml.safe_load((root / "benchmarks" / "policies" / "default.yaml").read_text(encoding="utf-8"))
    gate = evaluate_gate(report, None, policy)

    assert evaluation.infrastructure_error is None
    assert evaluation.passed is False
    assert evaluation.output["benchmark_code_check"]["metric"] == "build_failed"
    assert any(assertion.metric == "build_failed" and not assertion.passed for assertion in evaluation.assertions)
    assert gate["passed"] is False
    assert any(failure["type"] == "hard" and failure["metric"] == "build_failed" for failure in gate["failures"])


def test_optional_code_execution_is_evaluated_as_quality(tmp_path: Path) -> None:
    loaded = _loaded(
        tmp_path,
        state=_state(content="def broken(:\n"),
        input_data={
            "execution_command": [sys.executable, "-m", "py_compile", "index.html"],
            "timeout_seconds": 10,
        },
        expectations={
            "equals": {"benchmark_code_check.passed": True},
            "required_files": ["index.html"],
        },
    )

    record = EndToEndRunner().run(loaded, RunContext("run", True))[0]
    evaluation = evaluate_assertions(loaded.case, record.output)

    assert record.infrastructure_error is None
    assert record.output["benchmark_code_check"]["metric"] == "build_failed"
    assert evaluation.passed is False


def test_code_execution_infrastructure_failure_is_not_quality(tmp_path: Path) -> None:
    loaded = _loaded(tmp_path, input_data={"execution_command": ["missing-e2e-tool"], "timeout_seconds": 10})

    record = EndToEndRunner().run(loaded, RunContext("run", True))[0]

    assert record.infrastructure_error
    assert "benchmark_code_check" not in record.output


def test_repeats_have_unique_attempts_and_temporary_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import benchmark.runners.end_to_end as module

    roots: list[Path] = []

    def fake_evaluate_code(**kwargs: object) -> dict:
        root = Path(kwargs["project_dir"])  # type: ignore[arg-type]
        assert root.is_dir()
        roots.append(root)
        return {"passed": True, "metric": "build_success", "log": "", "infrastructure_error": None}

    monkeypatch.setattr(module, "evaluate_code", fake_evaluate_code)
    loaded = _loaded(
        tmp_path,
        repeats=2,
        input_data={"execution_command": [sys.executable, "-V"], "timeout_seconds": 10},
    )

    records = EndToEndRunner().run(loaded, RunContext("run", True))

    assert [record.attempt_index for record in records] == [0, 1]
    assert len(set(roots)) == 2
    assert all(not root.exists() for root in roots)


@pytest.mark.parametrize(("mode", "target"), [("replay", "e2e"), ("e2e", "coder")])
def test_runner_requires_e2e_mode_and_target(tmp_path: Path, mode: str, target: str) -> None:
    loaded = _loaded(tmp_path, mode=mode, target=target)

    with pytest.raises(ValueError, match="e2e runner requires"):
        EndToEndRunner().run(loaded, RunContext("run", True))


@pytest.mark.parametrize(
    "state",
    [
        [],
        {"phase": "completed"},
        {**_state(), "code_files": "not-a-list"},
        {**_state(), "review": []},
        {**_state(), "quality_gate_result": []},
        {**_state(), "build_result": []},
    ],
)
def test_runner_rejects_malformed_recorded_final_state(tmp_path: Path, state: object) -> None:
    loaded = _loaded(tmp_path, state=state)

    with pytest.raises(ValueError, match="e2e-fixture: invalid final state"):
        EndToEndRunner().run(loaded, RunContext("run", True))


@pytest.mark.parametrize(
    "input_data",
    [
        {"execution_command": "python"},
        {"execution_command": []},
        {"execution_command": ["python", ""]},
        {"execution_command": ["python"], "timeout_seconds": 0},
        {"execution_command": ["python"], "timeout_seconds": 601},
    ],
)
def test_runner_rejects_invalid_execution_configuration(tmp_path: Path, input_data: dict) -> None:
    loaded = _loaded(tmp_path, input_data=input_data)

    with pytest.raises(ValueError, match="e2e-fixture: (execution_command|timeout_seconds)"):
        EndToEndRunner().run(loaded, RunContext("run", True))
