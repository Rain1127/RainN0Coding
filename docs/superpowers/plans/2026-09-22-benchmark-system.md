# Benchmark Evaluation System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Build a production-ready benchmark loop for Intent, Coder, Reviewer, Supervisor, RAG, and end-to-end generation, with offline PR gates, nightly live-LLM runs, versioned baselines, and JSON plus standalone HTML reports.

**Architecture:** Add a new python-agent/benchmark package around the existing agent_eval and RAGAS code. Keep execution, evaluation, aggregation, baseline comparison, gating, and rendering separate so raw outputs can be rescored without rerunning models. PR runs stay deterministic and offline; nightly runs use the existing LiteLLM gateway and the same report contract.

**Tech Stack:** Python 3.12, Pydantic 2, PyYAML, pytest, existing LangGraph agents, existing LiteLLM gateway, existing RAGAS integration, standard-library HTML/JSON generation, GitHub Actions.

---

## Preflight and file map

The repository currently contains unrelated uncommitted changes. Before executing this plan, preserve them and ensure each commit stages only the files listed by its task. Do not overwrite the existing root uv.lock, static assets, plan files, or unrelated pyproject.toml edits.

New package responsibilities:

- python-agent/benchmark/contracts.py: stable Pydantic contracts for cases, records, evaluation results, reports, and baselines.
- python-agent/benchmark/dataset.py: YAML discovery, validation, duplicate detection, and safe fixture resolution.
- python-agent/benchmark/evaluators/assertions.py: declarative equality, path, required-text, and forbidden-text rules.
- python-agent/benchmark/evaluators/metrics.py: retrieval metrics and aggregate statistics.
- python-agent/benchmark/evaluators/code_execution.py: isolated file materialization and allowlisted subprocess checks.
- python-agent/benchmark/runners/base.py: runner protocol and common execution context.
- python-agent/benchmark/runners/deterministic.py: production Supervisor and pure-function execution.
- python-agent/benchmark/runners/replay.py: evaluation of saved outputs.
- python-agent/benchmark/runners/rag.py: injected retriever execution and labeled retrieval scoring.
- python-agent/benchmark/runners/live_llm.py: real Intent, Reviewer, Coder, and workflow execution with usage capture.
- python-agent/benchmark/orchestrator.py: suite execution without scoring or rendering logic.
- python-agent/benchmark/baseline.py: compatible-baseline lookup and immutable promotion.
- python-agent/benchmark/gates.py: hard-fail, absolute-threshold, and regression policies.
- python-agent/benchmark/reporting/json_report.py: canonical machine-readable report.
- python-agent/benchmark/reporting/html_report.py: standalone human-readable report generated only from JSON.
- python-agent/benchmark/cli.py: validate, run, compare, and baseline promote commands.
- python-agent/benchmarks/: versioned datasets, suites, policies, baselines, and report assets.
- python-agent/tests/benchmark/: focused unit and integration tests.
- .github/workflows/benchmark.yml: offline PR and live nightly jobs.

## Task 1: Establish benchmark contracts and strict dataset loading

**Files:**
- Create: python-agent/benchmark/__init__.py
- Create: python-agent/benchmark/contracts.py
- Create: python-agent/benchmark/dataset.py
- Create: python-agent/tests/benchmark/test_dataset.py
- Modify: python-agent/pyproject.toml
- Modify: python-agent/uv.lock

- [ ] **Step 1: Add the benchmark marker and direct YAML dependency**

Add pyyaml>=6.0 to project.dependencies and add this marker to tool.pytest.ini_options.markers:

~~~toml
"benchmark: deterministic benchmark framework and dataset contract tests",
~~~

Run:

~~~powershell
cd python-agent
uv lock
~~~

Expected: exit code 0 and python-agent/uv.lock records PyYAML as a direct project dependency without changing unrelated dependency pins.

- [ ] **Step 2: Write failing dataset contract tests**

Create python-agent/tests/benchmark/test_dataset.py:

~~~python
from pathlib import Path

import pytest

from benchmark.dataset import load_cases


def test_load_cases_injects_dataset_version_and_resolves_fixture(tmp_path: Path):
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    (fixtures / "output.json").write_text('{"phase":"intent_done"}', encoding="utf-8")
    (tmp_path / "cases.yaml").write_text(
        """
schema_version: 1
dataset_version: "2026.09.1"
cases:
  - id: intent-basic
    target: intent
    category: correctness
    difficulty: basic
    tags: [pr]
    execution: {mode: replay, record: fixtures/output.json}
    input: {user_request: "创建登录页"}
    expectations:
      equals: {phase: intent_done}
    provenance: {source: curated, reviewed: true, sanitized: true}
""",
        encoding="utf-8",
    )

    loaded = load_cases(tmp_path)

    assert loaded[0].case.dataset_version == "2026.09.1"
    assert loaded[0].record_path == (fixtures / "output.json").resolve()


def test_load_cases_rejects_duplicate_ids(tmp_path: Path):
    payload = """
schema_version: 1
dataset_version: "2026.09.1"
cases:
  - id: duplicate
    target: supervisor
    category: routing
    execution: {mode: deterministic}
    input: {}
    expectations: {}
    provenance: {source: curated, reviewed: true, sanitized: true}
"""
    (tmp_path / "one.yaml").write_text(payload, encoding="utf-8")
    (tmp_path / "two.yaml").write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate benchmark case id"):
        load_cases(tmp_path)


def test_load_cases_rejects_record_outside_dataset(tmp_path: Path):
    (tmp_path / "cases.yaml").write_text(
        """
schema_version: 1
dataset_version: "2026.09.1"
cases:
  - id: escape
    target: intent
    category: security
    execution: {mode: replay, record: ../secret.json}
    input: {}
    expectations: {}
    provenance: {source: curated, reviewed: true, sanitized: true}
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="outside dataset root"):
        load_cases(tmp_path)
~~~

- [ ] **Step 3: Run the tests and verify the package is missing**

Run:

~~~powershell
cd python-agent
& '.\.venv\Scripts\python.exe' -m pytest tests/benchmark/test_dataset.py -q --basetemp .test-tmp-benchmark
~~~

Expected: collection fails with ModuleNotFoundError for benchmark.dataset.

- [ ] **Step 4: Implement the initial contracts**

Create python-agent/benchmark/__init__.py with an empty module docstring.

Create python-agent/benchmark/contracts.py:

~~~python
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


ExecutionMode = Literal["deterministic", "replay", "live", "rag", "e2e"]
Target = Literal["intent", "coder", "reviewer", "supervisor", "rag", "e2e"]


class ExecutionSpec(BaseModel):
    mode: ExecutionMode
    record: str | None = None
    repeats: int = Field(default=1, ge=1, le=20)


class Expectations(BaseModel):
    equals: dict[str, Any] = Field(default_factory=dict)
    required_paths: list[str] = Field(default_factory=list)
    required_text: dict[str, list[str]] = Field(default_factory=dict)
    forbidden_text: dict[str, list[str]] = Field(default_factory=dict)
    required_files: list[str] = Field(default_factory=list)
    relevant_document_ids: list[str] = Field(default_factory=list)


class Provenance(BaseModel):
    source: Literal["curated", "historical_bug", "synthetic", "sanitized_user"]
    reviewed: bool
    sanitized: bool


class BenchmarkCase(BaseModel):
    id: str
    schema_version: int = 1
    dataset_version: str
    target: Target
    category: str
    difficulty: Literal["basic", "medium", "hard"] = "medium"
    tags: list[str] = Field(default_factory=list)
    execution: ExecutionSpec
    input: dict[str, Any] = Field(default_factory=dict)
    expectations: Expectations = Field(default_factory=Expectations)
    metric_tags: dict[str, str] = Field(default_factory=dict)
    output_metrics: dict[str, str] = Field(default_factory=dict)
    gate: dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance

    @field_validator("id", "dataset_version", "category")
    @classmethod
    def non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class LoadedCase(BaseModel):
    case: BenchmarkCase
    source_path: Path
    record_path: Path | None = None
~~~

Add from pathlib import Path to the imports in contracts.py.

- [ ] **Step 5: Implement strict YAML loading and safe record resolution**

Create python-agent/benchmark/dataset.py:

~~~python
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from benchmark.contracts import BenchmarkCase, LoadedCase


def _inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def _load_file(source: Path) -> dict[str, Any]:
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{source}: dataset must be an object")
    if payload.get("schema_version") != 1:
        raise ValueError(f"{source}: expected schema_version 1")
    if not isinstance(payload.get("cases"), list):
        raise ValueError(f"{source}: cases must be a list")
    return payload


def load_cases(
    dataset_path: str | Path,
    asset_root: str | Path | None = None,
) -> list[LoadedCase]:
    root = Path(dataset_path).resolve()
    safe_asset_root = Path(asset_root).resolve() if asset_root else root
    if not root.is_dir():
        raise ValueError(f"dataset root does not exist: {root}")
    loaded: list[LoadedCase] = []
    seen: set[str] = set()
    for source in sorted([*root.rglob("*.yaml"), *root.rglob("*.yml")]):
        payload = _load_file(source)
        dataset_version = str(payload.get("dataset_version", "")).strip()
        if not dataset_version:
            raise ValueError(f"{source}: dataset_version is required")
        for raw in payload["cases"]:
            case = BenchmarkCase.model_validate(
                {
                    **raw,
                    "schema_version": payload["schema_version"],
                    "dataset_version": dataset_version,
                }
            )
            if case.id in seen:
                raise ValueError(f"duplicate benchmark case id: {case.id}")
            seen.add(case.id)
            record_path = None
            if case.execution.record:
                resolved = (source.parent / case.execution.record).resolve()
                if not _inside(safe_asset_root, resolved):
                    raise ValueError(f"{case.id}: record is outside dataset root")
                if not resolved.is_file():
                    raise ValueError(f"{case.id}: record does not exist: {resolved}")
                record_path = str(resolved)
            loaded.append(
                LoadedCase(
                    case=case,
                    source_path=source.resolve(),
                    record_path=Path(record_path) if record_path else None,
                )
            )
    if not loaded:
        raise ValueError(f"no benchmark cases found under {root}")
    return loaded
~~~

- [ ] **Step 6: Run the dataset tests**

Run:

~~~powershell
cd python-agent
& '.\.venv\Scripts\python.exe' -m pytest tests/benchmark/test_dataset.py -q --basetemp .test-tmp-benchmark
~~~

Expected: 3 passed.

- [ ] **Step 7: Commit Task 1**

~~~powershell
git add python-agent/benchmark python-agent/tests/benchmark/test_dataset.py python-agent/pyproject.toml python-agent/uv.lock
git commit -m "feat: add benchmark dataset contracts"
~~~

## Task 2: Migrate existing Golden Cases and define suites

**Files:**
- Create: python-agent/benchmark/migrate_agent_eval.py
- Create: python-agent/tests/benchmark/test_migrate_agent_eval.py
- Create: python-agent/benchmarks/datasets/regression/core-golden.yaml
- Create: python-agent/benchmarks/records/intent-fallback-vue.json
- Create: python-agent/benchmarks/records/reviewer-detects-xss.json
- Create: python-agent/benchmarks/suites/pr.yaml
- Create: python-agent/benchmarks/suites/nightly.yaml
- Create: python-agent/benchmarks/policies/default.yaml
- Modify: .gitignore

- [ ] **Step 1: Write a failing migration test**

Create python-agent/tests/benchmark/test_migrate_agent_eval.py:

~~~python
from pathlib import Path

import yaml

from benchmark.migrate_agent_eval import migrate_directory


def test_migration_preserves_all_six_existing_case_ids(tmp_path: Path):
    source = Path(__file__).parents[2] / "agent_eval" / "golden" / "dev"
    destination = tmp_path / "core-golden.yaml"

    count = migrate_directory(source, destination, dataset_version="2026.09.1")
    payload = yaml.safe_load(destination.read_text(encoding="utf-8"))

    assert count == 6
    assert {case["id"] for case in payload["cases"]} == {
        "intent-fallback-vue",
        "reviewer-detects-xss",
        "supervisor-review-passed",
        "supervisor-code-retry",
        "supervisor-architecture-discussion",
        "supervisor-retry-exhausted",
    }
    assert next(case for case in payload["cases"] if case["target"] == "supervisor")["execution"]["mode"] == "deterministic"
~~~

- [ ] **Step 2: Run the migration test and verify failure**

Run:

~~~powershell
cd python-agent
& '.\.venv\Scripts\python.exe' -m pytest tests/benchmark/test_migrate_agent_eval.py -q --basetemp .test-tmp-benchmark
~~~

Expected: collection fails because benchmark.migrate_agent_eval does not exist.

- [ ] **Step 3: Implement the compatibility migration**

Create python-agent/benchmark/migrate_agent_eval.py:

~~~python
from __future__ import annotations

import json
from pathlib import Path

import yaml


def migrate_directory(source: str | Path, destination: str | Path, dataset_version: str) -> int:
    migrated = []
    for path in sorted(Path(source).rglob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for old in payload.get("cases", []):
            target = old["agent"]
            case = {
                "id": old["id"],
                "target": target,
                "category": old["category"],
                "difficulty": "medium",
                "tags": ["pr", "migrated"],
                "execution": {
                    "mode": "deterministic" if target == "supervisor" else "replay",
                    **(
                        {}
                        if target == "supervisor"
                        else {"record": f"../../records/{old['id']}.json"}
                    ),
                },
                "input": old["input_state"],
                "expectations": old["expectations"],
                "metric_tags": old.get("metric_tags", {}),
                "output_metrics": old.get("output_metrics", {}),
                "provenance": {
                    "source": "curated",
                    "reviewed": True,
                    "sanitized": True,
                },
            }
            migrated.append(case)
    output = {
        "schema_version": 1,
        "dataset_version": dataset_version,
        "cases": migrated,
    }
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        yaml.safe_dump(output, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return len(migrated)
~~~

- [ ] **Step 4: Generate and review the migrated dataset**

Run:

~~~powershell
cd python-agent
& '.\.venv\Scripts\python.exe' -c "from benchmark.migrate_agent_eval import migrate_directory; print(migrate_directory('agent_eval/golden/dev','benchmarks/datasets/regression/core-golden.yaml','2026.09.1'))"
~~~

Expected: prints 6. Inspect every generated case and confirm that its expectations and metric tags match the original JSON.

Create the two reviewed replay records using the outputs already documented by agent_eval:

~~~json
{
  "output": {
    "phase": "intent_done",
    "error": null,
    "intent": {
      "primary_intent": "code generation",
      "slots": {"code_gen_type": "vue_project"}
    },
    "clarification": {"questions": []}
  },
  "metrics": {}
}
~~~

~~~json
{
  "output": {
    "passed": false,
    "score": 40,
    "issues": [{"description": "XSS caused by v-html"}]
  },
  "metrics": {}
}
~~~

- [ ] **Step 5: Add suite and policy files**

Create python-agent/benchmarks/suites/pr.yaml:

~~~yaml
schema_version: 1
name: pr
dataset_roots:
  - ../datasets/regression
  - ../datasets/adversarial
allowed_modes: [deterministic, replay, rag, e2e]
offline: true
fail_on_infrastructure_error: true
policy: ../policies/default.yaml
baseline_dir: ../baselines
~~~

Create python-agent/benchmarks/suites/nightly.yaml:

~~~yaml
schema_version: 1
name: nightly
dataset_roots:
  - ../datasets/regression
  - ../datasets/nightly
  - ../datasets/adversarial
allowed_modes: [deterministic, replay, live, rag, e2e]
offline: false
fail_on_infrastructure_error: true
policy: ../policies/default.yaml
baseline_dir: ../baselines
~~~

Create python-agent/benchmarks/policies/default.yaml with no invented production thresholds:

~~~yaml
schema_version: 1
hard_fail_metrics:
  - route_accuracy
  - retry_route_accuracy
  - architecture_escalation_accuracy
  - retry_limit_enforcement
  - critical_defect_recall
  - safety_compliance
  - build_failed
absolute_thresholds: {}
regression_thresholds: {}
~~~

Append these generated-artifact rules to .gitignore:

~~~gitignore
python-agent/benchmarks/records/runs/
python-agent/benchmarks/reports/
python-agent/.test-tmp-benchmark/
~~~

- [ ] **Step 6: Run migration and dataset tests**

Run:

~~~powershell
cd python-agent
& '.\.venv\Scripts\python.exe' -m pytest tests/benchmark/test_dataset.py tests/benchmark/test_migrate_agent_eval.py -q --basetemp .test-tmp-benchmark
~~~

Expected: 4 passed.

- [ ] **Step 7: Commit Task 2**

~~~powershell
git add .gitignore python-agent/benchmark/migrate_agent_eval.py python-agent/tests/benchmark/test_migrate_agent_eval.py python-agent/benchmarks
git commit -m "feat: migrate golden cases into benchmark suites"
~~~

## Task 3: Implement assertion evaluation and canonical run records

**Files:**
- Modify: python-agent/benchmark/contracts.py
- Create: python-agent/benchmark/evaluators/__init__.py
- Create: python-agent/benchmark/evaluators/assertions.py
- Create: python-agent/tests/benchmark/test_assertions.py

- [ ] **Step 1: Write failing assertion tests**

Create python-agent/tests/benchmark/test_assertions.py:

~~~python
from benchmark.contracts import BenchmarkCase
from benchmark.evaluators.assertions import evaluate_assertions


def case(expectations):
    return BenchmarkCase.model_validate(
        {
            "id": "review-xss",
            "dataset_version": "2026.09.1",
            "target": "reviewer",
            "category": "security",
            "execution": {"mode": "replay"},
            "input": {},
            "expectations": expectations,
            "metric_tags": {"required_text.issues": "critical_defect_recall"},
            "provenance": {"source": "curated", "reviewed": True, "sanitized": True},
        }
    )


def test_assertions_report_named_metrics_and_failures():
    result = evaluate_assertions(
        case(
            {
                "equals": {"passed": False},
                "required_paths": ["score", "issues"],
                "required_text": {"issues": ["xss", "v-html"]},
                "forbidden_text": {"issues": ["safe to ship"]},
            }
        ),
        {"passed": False, "score": 40, "issues": [{"description": "v-html XSS"}]},
    )

    assert result.passed is True
    assert result.assertions_total == 5
    assert {item.metric for item in result.assertions} >= {
        "task_correctness",
        "output_protocol_completeness",
        "critical_defect_recall",
        "safety_compliance",
    }


def test_missing_path_is_a_case_failure_not_infrastructure_error():
    result = evaluate_assertions(case({"required_paths": ["review.score"]}), {})

    assert result.passed is False
    assert result.infrastructure_error is None
    assert result.failures == ["review.score: required path is missing"]
~~~

- [ ] **Step 2: Run the tests and verify missing result contracts**

Run:

~~~powershell
cd python-agent
& '.\.venv\Scripts\python.exe' -m pytest tests/benchmark/test_assertions.py -q --basetemp .test-tmp-benchmark
~~~

Expected: collection fails because evaluate_assertions is missing.

- [ ] **Step 3: Extend contracts with traceable evaluation records**

Append to python-agent/benchmark/contracts.py:

~~~python
class MetricAssertion(BaseModel):
    metric: str
    passed: bool
    rule: str
    path: str


class CaseEvaluation(BaseModel):
    case_id: str
    attempt_index: int = 0
    target: Target
    category: str
    passed: bool
    assertions_passed: int
    assertions_total: int
    assertions: list[MetricAssertion] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
    output: dict[str, Any] = Field(default_factory=dict)
    observed_metrics: dict[str, float | None] = Field(default_factory=dict)
    infrastructure_error: str | None = None
~~~

- [ ] **Step 4: Implement declarative assertions**

Create python-agent/benchmark/evaluators/assertions.py by porting the proven agent_eval behavior and returning CaseEvaluation:

~~~python
from __future__ import annotations

from typing import Any

from benchmark.contracts import BenchmarkCase, CaseEvaluation, MetricAssertion


MISSING = object()
DEFAULT_METRICS = {
    "equals": "task_correctness",
    "required_paths": "output_protocol_completeness",
    "required_text": "evidence_recall",
    "forbidden_text": "safety_compliance",
}


def lookup(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return MISSING
        current = current[part]
    return current


def rendered_text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(rendered_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(rendered_text(item) for item in value)
    return str(value).lower()


def metric_name(case: BenchmarkCase, rule: str, path: str) -> str:
    return case.metric_tags.get(
        f"{rule}.{path}",
        case.metric_tags.get(rule, DEFAULT_METRICS[rule]),
    )


def evaluate_assertions(
    case: BenchmarkCase,
    output: dict[str, Any],
    observed_metrics: dict[str, float | None] | None = None,
    attempt_index: int = 0,
) -> CaseEvaluation:
    assertions: list[MetricAssertion] = []
    failures: list[str] = []

    def record(rule: str, path: str, passed: bool, failure: str) -> None:
        assertions.append(
            MetricAssertion(
                metric=metric_name(case, rule, path),
                passed=passed,
                rule=rule,
                path=path,
            )
        )
        if not passed:
            failures.append(failure)

    for path, expected in case.expectations.equals.items():
        actual = lookup(output, path)
        record("equals", path, actual == expected, f"{path}: expected {expected!r}, got {actual!r}")
    for path in case.expectations.required_paths:
        record(
            "required_paths",
            path,
            lookup(output, path) is not MISSING,
            f"{path}: required path is missing",
        )
    for path, alternatives in case.expectations.required_text.items():
        actual = lookup(output, path)
        text = "" if actual is MISSING else rendered_text(actual)
        ok = any(candidate.lower() in text for candidate in alternatives)
        record("required_text", path, ok, f"{path}: expected one of {alternatives!r}")
    for path, forbidden in case.expectations.forbidden_text.items():
        actual = lookup(output, path)
        text = "" if actual is MISSING else rendered_text(actual)
        matched = next((candidate for candidate in forbidden if candidate.lower() in text), None)
        record(
            "forbidden_text",
            path,
            matched is None,
            f"{path}: forbidden text {matched!r} found",
        )

    metrics = dict(observed_metrics or {})
    for path, name in case.output_metrics.items():
        value = lookup(output, path)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            metrics[name] = float(value)
    passed_count = sum(item.passed for item in assertions)
    return CaseEvaluation(
        case_id=case.id,
        attempt_index=attempt_index,
        target=case.target,
        category=case.category,
        passed=passed_count == len(assertions),
        assertions_passed=passed_count,
        assertions_total=len(assertions),
        assertions=assertions,
        failures=failures,
        output=output,
        observed_metrics=metrics,
    )
~~~

- [ ] **Step 5: Run assertion and legacy evaluator tests**

Run:

~~~powershell
cd python-agent
& '.\.venv\Scripts\python.exe' -m pytest tests/benchmark/test_assertions.py tests/test_agent_eval_evaluator.py -q --basetemp .test-tmp-benchmark
~~~

Expected: all tests pass, proving the new evaluator works without breaking the old evaluator.

- [ ] **Step 6: Commit Task 3**

~~~powershell
git add python-agent/benchmark/contracts.py python-agent/benchmark/evaluators python-agent/tests/benchmark/test_assertions.py
git commit -m "feat: add benchmark assertion evaluator"
~~~

## Task 4: Add runner protocol, deterministic execution, and replay

**Files:**
- Modify: python-agent/benchmark/contracts.py
- Create: python-agent/benchmark/runners/__init__.py
- Create: python-agent/benchmark/runners/base.py
- Create: python-agent/benchmark/runners/deterministic.py
- Create: python-agent/benchmark/runners/replay.py
- Create: python-agent/tests/benchmark/test_runners.py

- [ ] **Step 1: Write failing runner tests**

Create python-agent/tests/benchmark/test_runners.py:

~~~python
import json
from pathlib import Path

import pytest

from benchmark.contracts import BenchmarkCase, LoadedCase
from benchmark.runners.base import RunContext
from benchmark.runners.deterministic import DeterministicRunner
from benchmark.runners.replay import ReplayRunner


def benchmark_case(case_id: str, target: str, mode: str, input_value: dict):
    return BenchmarkCase.model_validate(
        {
            "id": case_id,
            "dataset_version": "2026.09.1",
            "target": target,
            "category": "routing",
            "execution": {"mode": mode},
            "input": input_value,
            "expectations": {},
            "provenance": {"source": "curated", "reviewed": True, "sanitized": True},
        }
    )


def test_deterministic_runner_calls_real_supervisor():
    case = benchmark_case(
        "review-passed",
        "supervisor",
        "deterministic",
        {"phase": "review_done", "review": {"passed": True}},
    )

    record = DeterministicRunner().run(
        LoadedCase(case=case, source_path="memory"),
        RunContext(run_id="run-1", offline=True),
    )[0]

    assert record.output == {"next_node": "builder_agent"}
    assert record.infrastructure_error is None


def test_replay_runner_reads_envelope(tmp_path: Path):
    path = tmp_path / "record.json"
    path.write_text(
        json.dumps({"output": {"phase": "intent_done"}, "metrics": {"latency_ms": 10}}),
        encoding="utf-8",
    )
    case = benchmark_case("intent", "intent", "replay", {})

    record = ReplayRunner().run(
        LoadedCase(case=case, source_path="memory", record_path=str(path)),
        RunContext(run_id="run-1", offline=True),
    )[0]

    assert record.output == {"phase": "intent_done"}
    assert record.observed_metrics == {"latency_ms": 10.0}


def test_offline_context_rejects_live_mode():
    case = benchmark_case("live", "intent", "live", {})

    with pytest.raises(ValueError, match="offline suite"):
        RunContext(run_id="run-1", offline=True).assert_mode_allowed(case.execution.mode)
~~~

- [ ] **Step 2: Run tests and verify missing runner modules**

Run:

~~~powershell
cd python-agent
& '.\.venv\Scripts\python.exe' -m pytest tests/benchmark/test_runners.py -q --basetemp .test-tmp-benchmark
~~~

Expected: collection fails because benchmark.runners does not exist.

- [ ] **Step 3: Add raw execution records and runner protocol**

Append to python-agent/benchmark/contracts.py:

~~~python
class RawRunRecord(BaseModel):
    case_id: str
    attempt_index: int = 0
    output: dict[str, Any] = Field(default_factory=dict)
    observed_metrics: dict[str, float | None] = Field(default_factory=dict)
    infrastructure_error: str | None = None
    started_at: str
    duration_ms: float
~~~

Create python-agent/benchmark/runners/base.py:

~~~python
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from benchmark.contracts import ExecutionMode, LoadedCase, RawRunRecord


@dataclass(frozen=True)
class RunContext:
    run_id: str
    offline: bool
    record_dir: Path | None = None

    def assert_mode_allowed(self, mode: ExecutionMode) -> None:
        if self.offline and mode == "live":
            raise ValueError("live mode is not allowed in an offline suite")


class Runner(Protocol):
    def run(self, loaded: LoadedCase, context: RunContext) -> list[RawRunRecord]:
        ...
~~~

Import Path from pathlib in runners/base.py.

- [ ] **Step 4: Implement deterministic and replay runners**

Create python-agent/benchmark/runners/deterministic.py:

~~~python
from datetime import UTC, datetime
from time import perf_counter

from agents.supervisor_agent import supervisor_decision
from benchmark.contracts import LoadedCase, RawRunRecord
from benchmark.runners.base import RunContext


class DeterministicRunner:
    def run(self, loaded: LoadedCase, context: RunContext) -> list[RawRunRecord]:
        context.assert_mode_allowed(loaded.case.execution.mode)
        started = datetime.now(UTC).isoformat()
        clock = perf_counter()
        if loaded.case.target != "supervisor":
            raise ValueError(f"no deterministic adapter for {loaded.case.target}")
        output = {"next_node": supervisor_decision(dict(loaded.case.input))}
        return [
            RawRunRecord(
                case_id=loaded.case.id,
                output=output,
                started_at=started,
                duration_ms=(perf_counter() - clock) * 1000,
            )
        ]
~~~

Create python-agent/benchmark/runners/replay.py:

~~~python
import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from benchmark.contracts import LoadedCase, RawRunRecord
from benchmark.runners.base import RunContext


class ReplayRunner:
    def run(self, loaded: LoadedCase, context: RunContext) -> list[RawRunRecord]:
        context.assert_mode_allowed(loaded.case.execution.mode)
        if not loaded.record_path:
            raise ValueError(f"{loaded.case.id}: replay record is required")
        started = datetime.now(UTC).isoformat()
        clock = perf_counter()
        envelope = json.loads(Path(loaded.record_path).read_text(encoding="utf-8"))
        output = envelope.get("output", envelope)
        metrics = envelope.get("metrics", {}) if "output" in envelope else {}
        if not isinstance(output, dict) or not isinstance(metrics, dict):
            raise ValueError(f"{loaded.case.id}: invalid replay envelope")
        observed = {
            name: float(value)
            for name, value in metrics.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }
        return [
            RawRunRecord(
                case_id=loaded.case.id,
                output=output,
                observed_metrics=observed,
                started_at=started,
                duration_ms=(perf_counter() - clock) * 1000,
            )
        ]
~~~

- [ ] **Step 5: Run runner tests**

Run:

~~~powershell
cd python-agent
& '.\.venv\Scripts\python.exe' -m pytest tests/benchmark/test_runners.py -q --basetemp .test-tmp-benchmark
~~~

Expected: 3 passed.

- [ ] **Step 6: Commit Task 4**

~~~powershell
git add python-agent/benchmark/contracts.py python-agent/benchmark/runners python-agent/tests/benchmark/test_runners.py
git commit -m "feat: add deterministic and replay benchmark runners"
~~~

## Task 5: Aggregate metrics and produce the canonical JSON report

**Files:**
- Modify: python-agent/benchmark/contracts.py
- Create: python-agent/benchmark/evaluators/metrics.py
- Create: python-agent/benchmark/redaction.py
- Create: python-agent/benchmark/reporting/__init__.py
- Create: python-agent/benchmark/reporting/json_report.py
- Create: python-agent/tests/benchmark/test_reporting.py

- [ ] **Step 1: Write failing report aggregation tests**

Create python-agent/tests/benchmark/test_reporting.py:

~~~python
import json

from benchmark.contracts import CaseEvaluation, MetricAssertion, RunMetadata
from benchmark.reporting.json_report import build_report, write_report


def evaluation(case_id, passed, latency):
    return CaseEvaluation(
        case_id=case_id,
        target="supervisor",
        category="routing",
        passed=passed,
        assertions_passed=int(passed),
        assertions_total=1,
        assertions=[
            MetricAssertion(
                metric="route_accuracy",
                passed=passed,
                rule="equals",
                path="next_node",
            )
        ],
        observed_metrics={"latency_ms": latency, "cost_usd": None},
    )


def test_report_keeps_null_cost_and_computes_percentiles(tmp_path):
    metadata = RunMetadata(
        run_id="run-1",
        suite="pr",
        git_sha="abc",
        dataset_versions=["2026.09.1"],
        dataset_fingerprint="dataset-hash",
        prompt_fingerprint="prompt-hash",
        model_aliases={},
        offline=True,
        started_at="2026-09-22T00:00:00+00:00",
    )

    report = build_report(metadata, [evaluation("one", True, 10), evaluation("two", False, 30)])
    output = tmp_path / "benchmark-result.json"
    write_report(report, output)
    persisted = json.loads(output.read_text(encoding="utf-8"))

    assert persisted["summary"]["case_pass_rate"] == 0.5
    assert persisted["metrics"]["latency_ms"]["p50"] == 10.0
    assert persisted["metrics"]["latency_ms"]["p95"] == 30.0
    assert "cost_usd" not in persisted["metrics"]


def test_report_redacts_secrets(tmp_path):
    metadata = RunMetadata(
        run_id="run-secret",
        suite="pr",
        git_sha="abc",
        dataset_versions=["2026.09.1"],
        dataset_fingerprint="dataset-hash",
        prompt_fingerprint="prompt-hash",
        model_aliases={},
        offline=True,
        started_at="2026-09-22T00:00:00+00:00",
    )
    report = build_report(
        metadata,
        [
            CaseEvaluation(
                case_id="secret",
                target="intent",
                category="security",
                passed=True,
                assertions_passed=0,
                assertions_total=0,
                output={"api_key": "sk-secret-value", "message": "Bearer abcdef123456"},
            )
        ],
    )
    output = tmp_path / "report.json"
    write_report(report, output)
    text = output.read_text(encoding="utf-8")
    assert "sk-secret-value" not in text
    assert "abcdef123456" not in text
~~~

- [ ] **Step 2: Run the test and verify missing report types**

Run:

~~~powershell
cd python-agent
& '.\.venv\Scripts\python.exe' -m pytest tests/benchmark/test_reporting.py -q --basetemp .test-tmp-benchmark
~~~

Expected: collection fails because RunMetadata or json_report is missing.

- [ ] **Step 3: Add run and report contracts**

Append to python-agent/benchmark/contracts.py:

~~~python
class RunMetadata(BaseModel):
    report_schema_version: int = 1
    run_id: str
    suite: str
    git_sha: str
    dataset_versions: list[str]
    dataset_fingerprint: str
    prompt_fingerprint: str
    model_aliases: dict[str, str]
    offline: bool
    started_at: str


class BenchmarkReport(BaseModel):
    metadata: RunMetadata
    summary: dict[str, int | float | str | bool]
    by_target: dict[str, dict[str, int | float]]
    by_category: dict[str, dict[str, int | float]]
    metrics: dict[str, dict[str, int | float]]
    gate: dict[str, Any] = Field(default_factory=dict)
    results: list[CaseEvaluation]
~~~

- [ ] **Step 4: Implement deterministic aggregate statistics**

Create python-agent/benchmark/redaction.py:

~~~python
import re
from typing import Any


SENSITIVE_KEY = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|password|secret|authorization|cookie)$"
)
BEARER = re.compile(r"(?i)Bearer\s+[A-Za-z0-9._~+/\-=]+")
OPENAI_STYLE = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")


def redact(value: Any, key: str = "") -> Any:
    if SENSITIVE_KEY.search(key):
        return "***REDACTED***"
    if isinstance(value, dict):
        return {name: redact(item, str(name)) for name, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return OPENAI_STYLE.sub(
            "***REDACTED***",
            BEARER.sub("Bearer ***REDACTED***", value),
        )
    return value
~~~

Create python-agent/benchmark/evaluators/metrics.py:

~~~python
from math import ceil
from statistics import pstdev


def describe(values: list[float]) -> dict[str, int | float]:
    ordered = sorted(values)
    return {
        "observations": len(ordered),
        "sum": sum(ordered),
        "mean": sum(ordered) / len(ordered),
        "min": ordered[0],
        "max": ordered[-1],
        "p50": ordered[(len(ordered) - 1) // 2],
        "p95": ordered[ceil(len(ordered) * 0.95) - 1],
        "stdev": pstdev(ordered) if len(ordered) > 1 else 0.0,
    }
~~~

Create python-agent/benchmark/reporting/json_report.py:

~~~python
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from benchmark.contracts import BenchmarkReport, CaseEvaluation, RunMetadata
from benchmark.evaluators.metrics import describe
from benchmark.redaction import redact


def _summary(results: list[CaseEvaluation]) -> dict[str, int | float]:
    grouped: dict[str, list[CaseEvaluation]] = defaultdict(list)
    for result in results:
        grouped[result.case_id].append(result)
    cases = len(grouped)
    passed_cases = sum(all(item.passed for item in attempts) for attempts in grouped.values())
    observations = len(results)
    passed_observations = sum(result.passed for result in results)
    checks = sum(result.assertions_total for result in results)
    checks_passed = sum(result.assertions_passed for result in results)
    return {
        "cases": cases,
        "passed": passed_cases,
        "case_pass_rate": passed_cases / cases if cases else 0.0,
        "observations": observations,
        "passed_observations": passed_observations,
        "observation_pass_rate": passed_observations / observations if observations else 0.0,
        "assertion_pass_rate": checks_passed / checks if checks else 0.0,
    }


def build_report(metadata: RunMetadata, results: list[CaseEvaluation]) -> BenchmarkReport:
    targets: dict[str, list[CaseEvaluation]] = defaultdict(list)
    categories: dict[str, list[CaseEvaluation]] = defaultdict(list)
    observed: dict[str, list[float]] = defaultdict(list)
    for result in results:
        targets[result.target].append(result)
        categories[result.category].append(result)
        for name, value in result.observed_metrics.items():
            if value is not None:
                observed[name].append(float(value))
    return BenchmarkReport(
        metadata=metadata,
        summary=_summary(results),
        by_target={name: _summary(group) for name, group in sorted(targets.items())},
        by_category={name: _summary(group) for name, group in sorted(categories.items())},
        metrics={name: describe(values) for name, values in sorted(observed.items())},
        results=results,
    )


def write_report(report: BenchmarkReport, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(redact(report.model_dump()), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
~~~

- [ ] **Step 5: Run report tests**

Run:

~~~powershell
cd python-agent
& '.\.venv\Scripts\python.exe' -m pytest tests/benchmark/test_reporting.py -q --basetemp .test-tmp-benchmark
~~~

Expected: 1 passed.

- [ ] **Step 6: Commit Task 5**

~~~powershell
git add python-agent/benchmark/contracts.py python-agent/benchmark/evaluators/metrics.py python-agent/benchmark/redaction.py python-agent/benchmark/reporting python-agent/tests/benchmark/test_reporting.py
git commit -m "feat: aggregate benchmark results into json reports"
~~~

## Task 6: Add suite orchestration and CLI validate/run commands

**Files:**
- Create: python-agent/benchmark/config.py
- Create: python-agent/benchmark/record_store.py
- Create: python-agent/benchmark/orchestrator.py
- Create: python-agent/benchmark/cli.py
- Create: python-agent/tests/benchmark/test_cli.py

- [ ] **Step 1: Write failing CLI integration tests**

Create python-agent/tests/benchmark/test_cli.py:

~~~python
import json
from pathlib import Path

from benchmark.cli import main


def test_validate_returns_zero_for_repository_pr_suite(capsys):
    code = main(["validate", "--suite", "benchmarks/suites/pr.yaml"])

    assert code == 0
    assert "validated" in capsys.readouterr().out.lower()


def test_run_writes_report_and_returns_zero(tmp_path: Path):
    output = tmp_path / "result.json"

    code = main(
        [
            "run",
            "--suite",
            "benchmarks/suites/pr.yaml",
            "--output",
            str(output),
            "--git-sha",
            "test-sha",
            "--record-dir",
            str(tmp_path / "records"),
        ]
    )

    report = json.loads(output.read_text(encoding="utf-8"))
    assert code == 0
    assert report["metadata"]["git_sha"] == "test-sha"
    assert report["summary"]["cases"] == 6
    assert len(list((tmp_path / "records").rglob("*.json"))) == 6
~~~

- [ ] **Step 2: Run CLI tests and verify failure**

Run:

~~~powershell
cd python-agent
& '.\.venv\Scripts\python.exe' -m pytest tests/benchmark/test_cli.py -q --basetemp .test-tmp-benchmark
~~~

Expected: collection fails because benchmark.cli does not exist.

- [ ] **Step 3: Implement suite configuration**

Create python-agent/benchmark/config.py with Pydantic validation and relative path resolution:

~~~python
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel


class SuiteConfig(BaseModel):
    schema_version: Literal[1]
    name: str
    dataset_roots: list[str]
    allowed_modes: list[str]
    offline: bool
    fail_on_infrastructure_error: bool
    policy: str
    baseline_dir: str


def load_suite(path: str | Path) -> tuple[SuiteConfig, Path]:
    source = Path(path).resolve()
    suite = SuiteConfig.model_validate(
        yaml.safe_load(source.read_text(encoding="utf-8"))
    )
    return suite, source.parent
~~~

- [ ] **Step 4: Implement orchestration**

Create python-agent/benchmark/record_store.py:

~~~python
import json
import re
from pathlib import Path

from benchmark.contracts import RawRunRecord
from benchmark.redaction import redact


def persist_record(record: RawRunRecord, record_dir: Path, run_id: str) -> Path:
    safe_case = re.sub(r"[^A-Za-z0-9_-]", "-", record.case_id).strip("-") or "case"
    target = record_dir / run_id / f"{safe_case}-{record.attempt_index}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(redact(record.model_dump()), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return target
~~~

Create python-agent/benchmark/orchestrator.py:

~~~python
from __future__ import annotations

from benchmark.contracts import CaseEvaluation, LoadedCase
from benchmark.evaluators.assertions import evaluate_assertions
from benchmark.runners.base import RunContext
from benchmark.runners.deterministic import DeterministicRunner
from benchmark.runners.replay import ReplayRunner
from benchmark.record_store import persist_record


RUNNERS = {
    "deterministic": DeterministicRunner(),
    "replay": ReplayRunner(),
}


def run_cases(cases: list[LoadedCase], context: RunContext) -> list[CaseEvaluation]:
    results = []
    for loaded in cases:
        mode = loaded.case.execution.mode
        context.assert_mode_allowed(mode)
        runner = RUNNERS.get(mode)
        if runner is None:
            raise ValueError(f"runner is not registered for mode: {mode}")
        try:
            records = runner.run(loaded, context)
            for record in records:
                if context.record_dir:
                    persist_record(record, context.record_dir, context.run_id)
                if record.infrastructure_error:
                    results.append(
                        CaseEvaluation(
                            case_id=loaded.case.id,
                            attempt_index=record.attempt_index,
                            target=loaded.case.target,
                            category=loaded.case.category,
                            passed=False,
                            assertions_passed=0,
                            assertions_total=0,
                            infrastructure_error=record.infrastructure_error,
                        )
                    )
                    continue
                metrics = {
                    **record.observed_metrics,
                    "duration_ms": record.duration_ms,
                }
                results.append(
                    evaluate_assertions(
                        loaded.case,
                        record.output,
                        metrics,
                        attempt_index=record.attempt_index,
                    )
                )
        except Exception as exc:
            failed_record = RawRunRecord(
                case_id=loaded.case.id,
                infrastructure_error=str(exc),
                started_at=datetime.now(UTC).isoformat(),
                duration_ms=0.0,
            )
            if context.record_dir:
                persist_record(failed_record, context.record_dir, context.run_id)
            results.append(
                CaseEvaluation(
                    case_id=loaded.case.id,
                    target=loaded.case.target,
                    category=loaded.case.category,
                    passed=False,
                    assertions_passed=0,
                    assertions_total=0,
                    infrastructure_error=str(exc),
                )
            )
    return results
~~~

Import UTC and datetime plus RawRunRecord in orchestrator.py.

- [ ] **Step 5: Implement CLI validate and run**

Create python-agent/benchmark/cli.py with main(argv=None) returning an integer and __main__ raising SystemExit(main()):

~~~python
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path

from benchmark.config import load_suite
from benchmark.contracts import RunMetadata
from benchmark.dataset import load_cases
from benchmark.orchestrator import run_cases
from benchmark.reporting.json_report import build_report, write_report
from benchmark.runners.base import RunContext
from config import config


def _git_sha() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        text=True,
        encoding="utf-8",
    ).strip()


def _prompt_fingerprint() -> str:
    root = Path(__file__).parents[1]
    digest = hashlib.sha256()
    paths = [
        *root.joinpath("agents").glob("*_agent.py"),
        root / "llm_factory.py",
        root / "workflow" / "autogen_discussion.py",
        root / "rag" / "ragas_evaluator.py",
    ]
    for path in sorted(paths):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _dataset_fingerprint(cases) -> str:
    digest = hashlib.sha256()
    for loaded in sorted(cases, key=lambda item: item.case.id):
        digest.update(
            json.dumps(
                loaded.case.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        if loaded.record_path:
            digest.update(loaded.record_path.read_bytes())
    return digest.hexdigest()


def _load_suite_cases(suite_path: str):
    suite, suite_dir = load_suite(suite_path)
    cases = []
    for relative in suite.dataset_roots:
        root = (suite_dir / relative).resolve()
        if root.exists():
            cases.extend(load_cases(root, asset_root=suite_dir.parent))
    disallowed = sorted(
        {
            item.case.execution.mode
            for item in cases
            if item.case.execution.mode not in suite.allowed_modes
        }
    )
    if disallowed:
        raise ValueError(f"suite contains disallowed modes: {disallowed}")
    return suite, cases


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--suite", required=True)
    run = sub.add_parser("run")
    run.add_argument("--suite", required=True)
    run.add_argument("--output", required=True)
    run.add_argument("--git-sha")
    run.add_argument("--record-dir", default="benchmarks/records/runs")
    args = parser.parse_args(argv)

    try:
        suite, cases = _load_suite_cases(args.suite)
        if args.command == "validate":
            print(f"validated {len(cases)} benchmark cases for suite {suite.name}")
            return 0
        run_id = str(uuid.uuid4())
        metadata = RunMetadata(
            run_id=run_id,
            suite=suite.name,
            git_sha=args.git_sha or _git_sha(),
            dataset_versions=sorted({item.case.dataset_version for item in cases}),
            dataset_fingerprint=_dataset_fingerprint(cases),
            prompt_fingerprint=_prompt_fingerprint(),
            model_aliases=dict(config.LLM_MODEL_ALIASES),
            offline=suite.offline,
            started_at=datetime.now(UTC).isoformat(),
        )
        results = run_cases(
            cases,
            RunContext(
                run_id=run_id,
                offline=suite.offline,
                record_dir=Path(args.record_dir),
            ),
        )
        report = build_report(metadata, results)
        write_report(report, args.output)
        return 2 if any(item.infrastructure_error for item in results) else 0
    except Exception as exc:
        print(f"benchmark infrastructure error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
~~~

- [ ] **Step 6: Run CLI tests and the repository PR suite**

Run:

~~~powershell
cd python-agent
$env:PYTHONPATH='.'
& '.\.venv\Scripts\python.exe' -m pytest tests/benchmark/test_cli.py -q --basetemp .test-tmp-benchmark
& '.\.venv\Scripts\python.exe' -m benchmark.cli validate --suite benchmarks/suites/pr.yaml
& '.\.venv\Scripts\python.exe' -m benchmark.cli run --suite benchmarks/suites/pr.yaml --output benchmarks/reports/pr-result.json
~~~

Expected: tests pass, validate reports 6 cases, run exits 0, and pr-result.json contains six traceable results.

- [ ] **Step 7: Commit Task 6**

~~~powershell
git add python-agent/benchmark/config.py python-agent/benchmark/record_store.py python-agent/benchmark/orchestrator.py python-agent/benchmark/cli.py python-agent/tests/benchmark/test_cli.py
git commit -m "feat: add benchmark suite cli"
~~~

## Task 7: Implement immutable baselines and three-level gates

**Files:**
- Modify: python-agent/benchmark/contracts.py
- Create: python-agent/benchmark/baseline.py
- Create: python-agent/benchmark/gates.py
- Modify: python-agent/benchmark/cli.py
- Create: python-agent/tests/benchmark/test_gates.py

- [ ] **Step 1: Write failing gate and promotion tests**

Create python-agent/tests/benchmark/test_gates.py:

~~~python
from pathlib import Path

import pytest

from benchmark.baseline import compatibility_key, promote
from benchmark.contracts import BenchmarkReport, RunMetadata
from benchmark.gates import evaluate_gate


def report(pass_rate: float, metric: float, run_id: str = "candidate"):
    return BenchmarkReport(
        metadata=RunMetadata(
            run_id=run_id,
            suite="pr",
            git_sha="sha",
            dataset_versions=["2026.09.1"],
            dataset_fingerprint="dataset-hash",
            prompt_fingerprint="prompt",
            model_aliases={"structured": "code-structured"},
            offline=True,
            started_at="2026-09-22T00:00:00+00:00",
        ),
        summary={"cases": 1, "passed": int(pass_rate == 1), "case_pass_rate": pass_rate, "assertion_pass_rate": pass_rate},
        by_target={},
        by_category={},
        metrics={"latency_ms": {"mean": metric}},
        results=[],
    )


def test_compatibility_key_excludes_git_sha():
    one = report(1.0, 10, "one")
    two = report(1.0, 10, "two")
    two.metadata.git_sha = "different"

    assert compatibility_key(one) == compatibility_key(two)


def test_gate_distinguishes_quality_regression():
    result = evaluate_gate(
        candidate=report(0.8, 12),
        baseline=report(1.0, 10, "baseline"),
        policy={
            "hard_fail_metrics": [],
            "absolute_thresholds": {"case_pass_rate": {"minimum": 0.9}},
            "regression_thresholds": {"latency_ms.mean": {"max_increase_ratio": 0.1}},
        },
    )

    assert result["passed"] is False
    assert {failure["type"] for failure in result["failures"]} == {"absolute", "regression"}


def test_promote_refuses_to_overwrite_existing_baseline(tmp_path: Path):
    first = promote(report(1.0, 10, "first"), tmp_path)

    with pytest.raises(FileExistsError):
        promote(report(1.0, 10, "second"), tmp_path)

    assert first.is_file()
~~~

- [ ] **Step 2: Run gate tests and verify failure**

Run:

~~~powershell
cd python-agent
& '.\.venv\Scripts\python.exe' -m pytest tests/benchmark/test_gates.py -q --basetemp .test-tmp-benchmark
~~~

Expected: collection fails because benchmark.baseline and benchmark.gates are missing.

- [ ] **Step 3: Implement baseline identity and immutable promotion**

Create python-agent/benchmark/baseline.py:

~~~python
import hashlib
import json
from pathlib import Path

from benchmark.contracts import BenchmarkReport
from benchmark.redaction import redact


def compatibility_key(report: BenchmarkReport) -> str:
    identity = {
        "suite": report.metadata.suite,
        "dataset_versions": report.metadata.dataset_versions,
        "dataset_fingerprint": report.metadata.dataset_fingerprint,
        "prompt_fingerprint": report.metadata.prompt_fingerprint,
        "model_aliases": report.metadata.model_aliases,
        "offline": report.metadata.offline,
    }
    return hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]


def promote(report: BenchmarkReport, baseline_dir: str | Path) -> Path:
    root = Path(baseline_dir)
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{compatibility_key(report)}.json"
    if target.exists():
        raise FileExistsError(f"baseline already exists: {target}")
    target.write_text(
        json.dumps(redact(report.model_dump()), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return target


def load_compatible(
    report: BenchmarkReport,
    baseline_dir: str | Path,
) -> BenchmarkReport | None:
    target = Path(baseline_dir) / f"{compatibility_key(report)}.json"
    if not target.exists():
        return None
    return BenchmarkReport.model_validate_json(target.read_text(encoding="utf-8"))
~~~

- [ ] **Step 4: Implement absolute and regression gate evaluation**

Create python-agent/benchmark/gates.py:

~~~python
from __future__ import annotations

from typing import Any

from benchmark.contracts import BenchmarkReport


def _numeric(report: BenchmarkReport, path: str) -> float:
    if "." not in path and path in report.summary:
        value = report.summary[path]
    else:
        current: Any = report.metrics
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                raise ValueError(f"gate metric is missing: {path}")
            current = current[part]
        value = current
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"gate metric is not numeric: {path}")
    return float(value)


def evaluate_gate(
    candidate: BenchmarkReport,
    baseline: BenchmarkReport | None,
    policy: dict,
) -> dict:
    failures: list[dict] = []
    warnings: list[dict] = []
    comparisons: list[dict] = []
    hard_metrics = set(policy.get("hard_fail_metrics", []))
    for result in candidate.results:
        for assertion in result.assertions:
            if not assertion.passed and assertion.metric in hard_metrics:
                failures.append(
                    {
                        "type": "hard",
                        "metric": assertion.metric,
                        "case_id": result.case_id,
                    }
                )
    for path, rule in policy.get("absolute_thresholds", {}).items():
        value = _numeric(candidate, path)
        if "minimum" in rule and value < float(rule["minimum"]):
            failures.append({"type": "absolute", "metric": path, "actual": value})
        if "maximum" in rule and value > float(rule["maximum"]):
            failures.append({"type": "absolute", "metric": path, "actual": value})
    for path, rule in policy.get("regression_thresholds", {}).items():
        if baseline is None:
            warnings.append({"type": "no_baseline", "metric": path})
            continue
        current = _numeric(candidate, path)
        previous = _numeric(baseline, path)
        comparison = {
            "metric": path,
            "baseline": previous,
            "actual": current,
            "delta": current - previous,
            "increase_ratio": None if previous == 0 else (current - previous) / previous,
        }
        comparisons.append(comparison)
        if "max_drop" in rule and previous - current > float(rule["max_drop"]):
            failures.append(
                {
                    "type": "regression",
                    "metric": path,
                    "baseline": previous,
                    "actual": current,
                }
            )
        if "max_increase_ratio" in rule:
            if previous == 0:
                raise ValueError(f"cannot calculate increase ratio from zero: {path}")
            ratio = (current - previous) / previous
            if ratio > float(rule["max_increase_ratio"]):
                failures.append(
                    {
                        "type": "regression",
                        "metric": path,
                        "baseline": previous,
                        "actual": current,
                        "increase_ratio": ratio,
                    }
                )
    return {
        "passed": not failures,
        "failures": failures,
        "warnings": warnings,
        "comparisons": comparisons,
        "baseline_run_id": baseline.metadata.run_id if baseline else None,
    }
~~~

Missing or nonnumeric policy metrics raise ValueError and therefore produce infrastructure exit code 2; they are never silently interpreted as zero.

- [ ] **Step 5: Add compare and baseline promote CLI commands**

Extend benchmark.cli with:

~~~text
python -m benchmark.cli compare --candidate <report> --baseline <report> --policy <yaml>
python -m benchmark.cli baseline promote --report <report> --baseline-dir benchmarks/baselines
~~~

compare writes the gate result into the candidate report, rewrites the JSON atomically through a temporary sibling file, returns 0 when passed, 1 for quality regression, and 2 for invalid policy or incompatible baseline. baseline promote validates compatibility and refuses silent overwrite.

Use these handlers:

~~~python
import json
import os
import yaml

from benchmark.baseline import compatibility_key, promote
from benchmark.contracts import BenchmarkReport
from benchmark.gates import evaluate_gate


def _read_report(path: str) -> BenchmarkReport:
    return BenchmarkReport.model_validate_json(Path(path).read_text(encoding="utf-8"))


def _atomic_report_write(report: BenchmarkReport, path: str) -> None:
    target = Path(path)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, target)


def _compare(candidate_path: str, baseline_path: str, policy_path: str) -> int:
    candidate = _read_report(candidate_path)
    baseline = _read_report(baseline_path)
    if compatibility_key(candidate) != compatibility_key(baseline):
        raise ValueError("candidate and baseline are incompatible")
    policy = yaml.safe_load(Path(policy_path).read_text(encoding="utf-8"))
    candidate.gate = evaluate_gate(candidate, baseline, policy)
    _atomic_report_write(candidate, candidate_path)
    return 0 if candidate.gate["passed"] else 1


def _promote(report_path: str, baseline_dir: str) -> int:
    target = promote(_read_report(report_path), baseline_dir)
    print(f"promoted baseline: {target}")
    return 0
~~~

Wire the argparse subcommands directly to these handlers. Catch ValueError, FileExistsError, OSError, and Pydantic validation errors at the main boundary and return 2.

Also update the run command after build_report and before write_report:

~~~python
policy_path = (suite_dir / suite.policy).resolve()
baseline_dir = (suite_dir / suite.baseline_dir).resolve()
policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
baseline = load_compatible(report, baseline_dir)
report.gate = evaluate_gate(report, baseline, policy)
write_report(report, args.output)
if any(item.infrastructure_error for item in results):
    return 2
return 0 if report.gate["passed"] else 1
~~~

Change _load_suite_cases to return suite_dir together with suite and cases. Add tests proving run returns 1 when a hard assertion fails, 2 when a replay record is missing, and 0 when all gates pass. This makes run itself the CI gate; compare remains useful for explicitly selected historical reports.

- [ ] **Step 6: Run gate and CLI tests**

Run:

~~~powershell
cd python-agent
& '.\.venv\Scripts\python.exe' -m pytest tests/benchmark/test_gates.py tests/benchmark/test_cli.py -q --basetemp .test-tmp-benchmark
~~~

Expected: all tests pass, including exit-code assertions added for 0, 1, and 2.

- [ ] **Step 7: Commit Task 7**

~~~powershell
git add python-agent/benchmark/contracts.py python-agent/benchmark/baseline.py python-agent/benchmark/gates.py python-agent/benchmark/cli.py python-agent/tests/benchmark/test_gates.py python-agent/tests/benchmark/test_cli.py
git commit -m "feat: add benchmark baselines and regression gates"
~~~

## Task 8: Generate a standalone HTML report from canonical JSON

The canonical artifact names are benchmark-result.json and benchmark-report.html; suite-specific commands may use prefixed names such as pr-result.json and pr-report.html.

**Files:**
- Create: python-agent/benchmark/reporting/html_report.py
- Create: python-agent/benchmark/reporting/template.html
- Modify: python-agent/benchmark/cli.py
- Create: python-agent/tests/benchmark/test_html_report.py

- [ ] **Step 1: Write failing standalone-report tests**

Create python-agent/tests/benchmark/test_html_report.py:

~~~python
from pathlib import Path

from benchmark.reporting.html_report import render_html


def test_html_is_single_file_and_contains_gate_and_failures(tmp_path: Path):
    report = {
        "metadata": {"run_id": "run-1", "suite": "pr", "git_sha": "abc"},
        "summary": {"cases": 2, "passed": 1, "case_pass_rate": 0.5},
        "by_target": {"supervisor": {"cases": 2, "passed": 1, "case_pass_rate": 0.5}},
        "by_category": {},
        "metrics": {"latency_ms": {"p50": 10, "p95": 20}},
        "gate": {"passed": False, "failures": [{"type": "absolute", "metric": "case_pass_rate"}]},
        "results": [{"case_id": "failed-case", "passed": False, "failures": ["wrong route"]}],
    }

    output = tmp_path / "report.html"
    render_html(report, output)
    html = output.read_text(encoding="utf-8")

    assert "run-1" in html
    assert "failed-case" in html
    assert "wrong route" in html
    assert "https://" not in html
    assert "<script src=" not in html
~~~

- [ ] **Step 2: Run the test and verify missing renderer**

Run:

~~~powershell
cd python-agent
& '.\.venv\Scripts\python.exe' -m pytest tests/benchmark/test_html_report.py -q --basetemp .test-tmp-benchmark
~~~

Expected: collection fails because html_report is missing.

- [ ] **Step 3: Add an offline HTML template**

Create template.html with embedded styles, semantic tables, accessible color contrast, a gate-status banner, summary cards, target metrics, operational metrics, baseline failures, and a case-detail table. Use one replacement token named BENCHMARK_DATA_JSON and no external fonts, scripts, images, or CDN references.

The inline JavaScript must parse the embedded application/json element and render values from the report. It must never calculate pass rates, percentiles, or gate decisions.

Use this complete initial template:

~~~html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Benchmark Report</title>
  <style>
    :root { color-scheme: light; font-family: "Segoe UI", sans-serif; }
    body { margin: 0; background: #f5f7fb; color: #172033; }
    main { width: min(1180px, calc(100% - 32px)); margin: 24px auto 48px; }
    header, section { background: white; border: 1px solid #dfe5ef; border-radius: 12px; padding: 20px; margin-bottom: 16px; }
    .passed { border-left: 8px solid #17803d; }
    .failed { border-left: 8px solid #b42318; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit,minmax(180px,1fr)); gap: 12px; }
    .card { background: #f8fafc; border-radius: 8px; padding: 14px; }
    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: left; border-bottom: 1px solid #e5e7eb; padding: 10px; vertical-align: top; }
    code { white-space: pre-wrap; word-break: break-word; }
    textarea { width: 100%; min-height: 120px; box-sizing: border-box; }
    @media (max-width: 640px) { main { width: min(100% - 16px,1180px); } th:nth-child(3), td:nth-child(3) { display: none; } }
  </style>
</head>
<body>
  <main>
    <header id="status"></header>
    <section><h2>总体指标</h2><div id="summary" class="grid"></div></section>
    <section><h2>评测对象</h2><div id="targets" class="grid"></div></section>
    <section><h2>运行指标</h2><div id="metrics" class="grid"></div></section>
    <section><h2>门禁详情</h2><pre id="gate"></pre></section>
    <section><h2>面试摘要</h2><textarea id="interview" readonly></textarea></section>
    <section>
      <h2>案例详情</h2>
      <table><thead><tr><th>案例</th><th>结果</th><th>失败原因</th></tr></thead><tbody id="cases"></tbody></table>
    </section>
  </main>
  <script id="benchmark-data" type="application/json">BENCHMARK_DATA_JSON</script>
  <script>
    const report = JSON.parse(document.getElementById("benchmark-data").textContent);
    function element(tag, text, className) {
      const node = document.createElement(tag);
      node.textContent = text;
      if (className) node.className = className;
      return node;
    }
    const gatePassed = report.gate && report.gate.passed !== false;
    const status = document.getElementById("status");
    status.className = gatePassed ? "passed" : "failed";
    status.appendChild(element("h1", "Benchmark " + (gatePassed ? "PASS" : "FAIL")));
    status.appendChild(element(
      "p",
      "Run " + report.metadata.run_id + " · Suite " + report.metadata.suite
        + " · Git " + report.metadata.git_sha
    ));
    function cards(target, values) {
      Object.entries(values).forEach(([name, value]) => {
        const card = element("article", "", "card");
        card.appendChild(element("strong", name));
        card.appendChild(element("div", JSON.stringify(value)));
        target.appendChild(card);
      });
    }
    cards(document.getElementById("summary"), report.summary || {});
    cards(document.getElementById("targets"), report.by_target || {});
    cards(document.getElementById("metrics"), report.metrics || {});
    document.getElementById("gate").textContent = JSON.stringify(report.gate || {}, null, 2);
    document.getElementById("interview").value =
      "本次 " + report.metadata.suite + " Benchmark 共评测 "
      + report.summary.cases + " 个案例、" + report.summary.observations
      + " 次观测，案例通过率为 " + report.summary.case_pass_rate
      + "，门禁结果为 " + (gatePassed ? "通过" : "未通过") + "。";
    const rows = document.getElementById("cases");
    (report.results || []).forEach(item => {
      const row = document.createElement("tr");
      row.appendChild(element("td", item.case_id + " #" + (item.attempt_index || 0)));
      row.appendChild(element("td", item.passed ? "PASS" : "FAIL"));
      const details = document.createElement("td");
      details.appendChild(element("code", JSON.stringify(item.failures || [])));
      row.appendChild(details);
      rows.appendChild(row);
    });
  </script>
</body>
</html>
~~~

Keep the DOM textContent helpers unchanged so model output cannot inject report markup. Keep the same IDs so the tests and renderer contract remain stable.

- [ ] **Step 4: Implement safe rendering**

Create python-agent/benchmark/reporting/html_report.py:

~~~python
import json
from pathlib import Path


def render_html(report: dict, output: str | Path) -> None:
    template = (Path(__file__).parent / "template.html").read_text(encoding="utf-8")
    payload = json.dumps(report, ensure_ascii=False).replace("</", "<\\/")
    rendered = template.replace("BENCHMARK_DATA_JSON", payload)
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding="utf-8")
~~~

- [ ] **Step 5: Update run command to produce JSON and HTML together**

Add optional --html-output. When omitted, derive a .html sibling from --output. Load the just-written JSON and call render_html; if rendering fails, return infrastructure exit code 2 and retain the JSON for diagnosis.

- [ ] **Step 6: Run report tests and inspect the generated page**

Run:

~~~powershell
cd python-agent
& '.\.venv\Scripts\python.exe' -m pytest tests/benchmark/test_html_report.py tests/benchmark/test_reporting.py tests/benchmark/test_cli.py -q --basetemp .test-tmp-benchmark
& '.\.venv\Scripts\python.exe' -m benchmark.cli run --suite benchmarks/suites/pr.yaml --output benchmarks/reports/pr-result.json --html-output benchmarks/reports/pr-report.html
~~~

Expected: tests pass and both report files are created. Open pr-report.html locally and verify Chinese text, gate status, summary, target cards, metrics, and failed-case details at desktop and narrow widths.

- [ ] **Step 7: Commit Task 8**

~~~powershell
git add python-agent/benchmark/reporting python-agent/benchmark/cli.py python-agent/tests/benchmark/test_html_report.py python-agent/tests/benchmark/test_cli.py
git commit -m "feat: render standalone benchmark reports"
~~~

## Task 9: Add labeled RAG metrics and a RAG runner

**Files:**
- Modify: python-agent/benchmark/evaluators/metrics.py
- Create: python-agent/benchmark/runners/rag.py
- Modify: python-agent/benchmark/orchestrator.py
- Modify: python-agent/rag/retrieval_engine.py
- Create: python-agent/benchmarks/datasets/regression/rag.yaml
- Create: python-agent/benchmarks/fixtures/rag/search-results.json
- Create: python-agent/tests/benchmark/test_rag_benchmark.py
- Modify: python-agent/tests/test_retrieval_common.py

- [ ] **Step 1: Write failing retrieval metric tests**

Create python-agent/tests/benchmark/test_rag_benchmark.py:

~~~python
import pytest

from benchmark.evaluators.metrics import retrieval_metrics


def test_retrieval_metrics_use_labeled_document_ids():
    metrics = retrieval_metrics(
        retrieved_ids=["doc-b", "doc-x", "doc-a"],
        relevant_ids={"doc-a", "doc-b"},
        k=3,
    )

    assert metrics["precision_at_k"] == pytest.approx(2 / 3)
    assert metrics["recall_at_k"] == 1.0
    assert metrics["mrr"] == 1.0
    assert metrics["ndcg_at_k"] == pytest.approx(0.919720789)


def test_retrieval_metrics_reject_empty_labels():
    with pytest.raises(ValueError, match="relevant document labels"):
        retrieval_metrics(["doc-a"], set(), 5)
~~~

- [ ] **Step 2: Run the tests and verify failure**

Run:

~~~powershell
cd python-agent
& '.\.venv\Scripts\python.exe' -m pytest tests/benchmark/test_rag_benchmark.py -q --basetemp .test-tmp-benchmark
~~~

Expected: import fails because retrieval_metrics does not exist.

- [ ] **Step 3: Implement Precision@K, Recall@K, MRR, and nDCG**

Add to benchmark/evaluators/metrics.py:

~~~python
import math


def retrieval_metrics(
    retrieved_ids: list[str],
    relevant_ids: set[str],
    k: int,
) -> dict[str, float]:
    if not relevant_ids:
        raise ValueError("relevant document labels are required")
    ranked = retrieved_ids[:k]
    hits = [1 if item in relevant_ids else 0 for item in ranked]
    precision = sum(hits) / k
    recall = sum(hits) / len(relevant_ids)
    reciprocal = next((1 / rank for rank, hit in enumerate(hits, 1) if hit), 0.0)
    dcg = sum(hit / math.log2(rank + 1) for rank, hit in enumerate(hits, 1))
    ideal_hits = [1] * min(len(relevant_ids), k)
    idcg = sum(hit / math.log2(rank + 1) for rank, hit in enumerate(ideal_hits, 1))
    return {
        "precision_at_k": precision,
        "recall_at_k": recall,
        "mrr": reciprocal,
        "ndcg_at_k": dcg / idcg if idcg else 0.0,
    }
~~~

- [ ] **Step 4: Implement RAG replay and injected-live execution**

First refactor RetrievalEngine without changing retrieval behavior: move lines that deduplicate and rerank raw channel results into a public retrieve_results(ctx) method returning list[RetrievalResult], and make retrieve(ctx) call postprocessor.format(self.retrieve_results(ctx)). Add a regression test to test_retrieval_common.py proving retrieve still returns the same formatted string while retrieve_results exposes the ranked objects.

Create python-agent/benchmark/runners/rag.py:

~~~python
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Callable

from benchmark.contracts import BenchmarkCase, LoadedCase, RawRunRecord
from benchmark.evaluators.metrics import retrieval_metrics
from benchmark.runners.base import RunContext


def _document_id(item: dict) -> str:
    metadata = item.get("metadata", {})
    explicit = metadata.get("document_id")
    if explicit:
        return str(explicit)
    collection = item.get("source_collection", "")
    for field in ("api_name", "component_name", "pattern_name", "error_signature", "file_path"):
        if metadata.get(field):
            return f"{collection}:{metadata[field]}"
    raise ValueError("retrieval result has no stable document id")


def _replay(case: BenchmarkCase, record_path: Path) -> list[dict]:
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    results = payload.get(case.id)
    if not isinstance(results, list):
        raise ValueError(f"{case.id}: RAG replay results are missing")
    return results


class RagRunner:
    def __init__(self, retrieve: Callable[[BenchmarkCase], list[dict]] | None = None):
        self.retrieve = retrieve

    def run(self, loaded: LoadedCase, context: RunContext) -> list[RawRunRecord]:
        started = datetime.now(UTC).isoformat()
        clock = perf_counter()
        if self.retrieve:
            results = self.retrieve(loaded.case)
        elif loaded.record_path:
            results = _replay(loaded.case, loaded.record_path)
        else:
            raise ValueError(f"{loaded.case.id}: RAG runner requires a retriever or replay record")
        ids = [_document_id(item) for item in results]
        metrics = retrieval_metrics(
            ids,
            set(loaded.case.expectations.relevant_document_ids),
            int(loaded.case.input.get("k", len(ids) or 1)),
        )
        ragas_input = loaded.case.input.get("ragas")
        if ragas_input:
            if context.offline:
                raise ValueError("RAGAS judge is not allowed in an offline suite")
            from rag.ragas_evaluator import evaluate_offline
            from request_context import bind_request_context

            request_id = f"benchmark-{context.run_id}-{loaded.case.id}-ragas"
            with bind_request_context(
                request_id=request_id,
                trace_id=request_id,
                user_id="benchmark",
                app_id="benchmark-rag",
            ):
                rows = evaluate_offline(
                    [
                        {
                            "question": ragas_input["question"],
                            "answer": ragas_input["answer"],
                            "contexts": [str(item.get("content", "")) for item in results],
                            "ground_truth": ragas_input["ground_truth"],
                        }
                    ]
                )
            if not rows:
                raise RuntimeError("RAGAS evaluation returned no result")
            metrics.update(
                {
                    name: float(value)
                    for name, value in rows[0].items()
                    if isinstance(value, (int, float)) and not isinstance(value, bool)
                }
            )
        return [
            RawRunRecord(
                case_id=loaded.case.id,
                output={"retrieved_document_ids": ids, "retrieved_count": len(ids)},
                observed_metrics=metrics,
                started_at=started,
                duration_ms=(perf_counter() - clock) * 1000,
            )
        ]
~~~

For nightly real retrieval, inject an adapter that builds RetrievalContext from case.input, calls retrieval_engine.retrieve_results(ctx), and converts each RetrievalResult with model-independent fields: source_collection, source_channel, score, and metadata.

The runner output shape is:

~~~python
{
    "retrieved_document_ids": ["framework_api:vue-ref", "component_library:form"],
    "retrieved_count": 2,
}
~~~

Its observed_metrics merge retrieval_metrics output with retrieval latency. The runner must not reuse rag.ragas_evaluator.evaluate_online as formal precision because that function uses a score threshold rather than relevance labels.

- [ ] **Step 5: Add reviewed RAG fixtures**

Create a small regression file with real IDs from seeded framework_api and component_library records. Each query must include relevant_document_ids verified against the fixture. Add fixed replay results to search-results.json so PR remains offline. Mark real retrieval plus RAGAS cases as nightly and use evaluate_offline only in the non-offline suite.

- [ ] **Step 6: Register RagRunner and run tests**

Add rag to orchestrator.RUNNERS. Run:

~~~powershell
cd python-agent
& '.\.venv\Scripts\python.exe' -m pytest tests/benchmark/test_rag_benchmark.py tests/benchmark/test_cli.py -q --basetemp .test-tmp-benchmark
~~~

Expected: all tests pass and PR suite includes labeled RAG metrics without loading Milvus, Qdrant, embeddings, or an LLM.

- [ ] **Step 7: Commit Task 9**

~~~powershell
git add python-agent/benchmark/evaluators/metrics.py python-agent/benchmark/runners/rag.py python-agent/benchmark/orchestrator.py python-agent/rag/retrieval_engine.py python-agent/benchmarks/datasets/regression/rag.yaml python-agent/benchmarks/fixtures/rag/search-results.json python-agent/tests/benchmark/test_rag_benchmark.py python-agent/tests/test_retrieval_common.py
git commit -m "feat: add labeled rag benchmark metrics"
~~~

## Task 10: Add isolated Coder checks and end-to-end fixture evaluation

**Files:**
- Create: python-agent/benchmark/evaluators/code_execution.py
- Create: python-agent/benchmark/runners/end_to_end.py
- Modify: python-agent/benchmark/orchestrator.py
- Create: python-agent/benchmarks/datasets/regression/coder-e2e.yaml
- Create: python-agent/benchmarks/fixtures/projects/valid-html/index.html
- Create: python-agent/benchmarks/fixtures/projects/invalid-python/main.py
- Create: python-agent/tests/benchmark/test_code_execution.py
- Create: python-agent/tests/benchmark/test_end_to_end_runner.py

- [ ] **Step 1: Write failing safe-execution tests**

Create test_code_execution.py covering:

~~~python
def test_materialize_rejects_parent_traversal(tmp_path):
    with pytest.raises(ValueError, match="unsafe generated path"):
        materialize_files([{"path": "../escape.py", "content": "x = 1"}], tmp_path)


def test_python_syntax_failure_is_a_quality_failure(tmp_path):
    result = evaluate_code(
        files=[{"path": "main.py", "content": "def broken(:\n"}],
        project_dir=tmp_path,
        command=["python", "-m", "py_compile", "main.py"],
        timeout_seconds=10,
    )
    assert result["passed"] is False
    assert result["metric"] == "build_failed"
    assert result["infrastructure_error"] is None


def test_missing_tool_is_infrastructure_error(tmp_path):
    result = evaluate_code(
        files=[{"path": "main.py", "content": "x = 1\n"}],
        project_dir=tmp_path,
        command=["definitely-missing-benchmark-tool"],
        timeout_seconds=10,
    )
    assert result["infrastructure_error"]
~~~

- [ ] **Step 2: Run tests and verify missing evaluator**

Run:

~~~powershell
cd python-agent
& '.\.venv\Scripts\python.exe' -m pytest tests/benchmark/test_code_execution.py -q --basetemp .test-tmp-benchmark
~~~

Expected: collection fails because code_execution is missing.

- [ ] **Step 3: Implement safe materialization and subprocess execution**

Use pathlib.Path.resolve plus relative_to to confine every generated file to a per-case temporary root. Run subprocess.run with an argument list, shell=False, captured UTF-8 output, a configured timeout, and no inherited secret-bearing environment values beyond an explicit allowlist. Return quality failure for nonzero compiler/build exit and infrastructure error for missing tools, timeout, or OS errors.

Do not import or call builder_agent directly because it writes into configured project directories, may run npm install, and may index successful code into the vector store.

Create python-agent/benchmark/evaluators/code_execution.py:

~~~python
from __future__ import annotations

import os
import subprocess
from pathlib import Path


SAFE_ENV_KEYS = ("PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "TEMP", "TMP")


def materialize_files(files: list[dict], project_dir: str | Path) -> list[Path]:
    root = Path(project_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    written = []
    for item in files:
        relative = Path(str(item.get("path", "")))
        if not relative.parts or relative.is_absolute():
            raise ValueError(f"unsafe generated path: {relative}")
        target = (root / relative).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"unsafe generated path: {relative}") from exc
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(item.get("content", "")), encoding="utf-8")
        written.append(target)
    return written


def evaluate_code(
    files: list[dict],
    project_dir: str | Path,
    command: list[str],
    timeout_seconds: int,
) -> dict:
    materialize_files(files, project_dir)
    environment = {key: os.environ[key] for key in SAFE_ENV_KEYS if key in os.environ}
    try:
        completed = subprocess.run(
            command,
            cwd=Path(project_dir),
            shell=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            env=environment,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        return {
            "passed": False,
            "metric": "build_failed",
            "log": "",
            "infrastructure_error": str(exc),
        }
    log = (completed.stdout + "\n" + completed.stderr)[-4000:]
    return {
        "passed": completed.returncode == 0,
        "metric": "build_failed" if completed.returncode else "build_success",
        "log": log,
        "infrastructure_error": None,
    }
~~~

- [ ] **Step 4: Implement an end-to-end replay runner**

EndToEndRunner reads a recorded final CodeGenState, verifies phase/final_status, required generated paths, review result, quality_gate_result, and build_result, then passes code_files to code_execution when the case declares an execution command. A live workflow adapter is added in Task 11; PR uses only reviewed saved states.

Create python-agent/benchmark/runners/end_to_end.py:

~~~python
from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from benchmark.contracts import LoadedCase, RawRunRecord
from benchmark.evaluators.code_execution import evaluate_code
from benchmark.runners.base import RunContext


class EndToEndRunner:
    def run(self, loaded: LoadedCase, context: RunContext) -> list[RawRunRecord]:
        if not loaded.record_path:
            raise ValueError(f"{loaded.case.id}: end-to-end replay record is required")
        started = datetime.now(UTC).isoformat()
        clock = perf_counter()
        envelope = json.loads(loaded.record_path.read_text(encoding="utf-8"))
        state = envelope.get("output", envelope)
        if not isinstance(state, dict):
            raise ValueError(f"{loaded.case.id}: final state must be an object")
        output = dict(state)
        command = loaded.case.input.get("execution_command")
        if command is not None:
            if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
                raise ValueError(f"{loaded.case.id}: execution_command must be a string list")
            with tempfile.TemporaryDirectory(prefix="benchmark-code-") as temporary:
                check = evaluate_code(
                    files=list(state.get("code_files", [])),
                    project_dir=temporary,
                    command=command,
                    timeout_seconds=int(loaded.case.input.get("timeout_seconds", 60)),
                )
            if check["infrastructure_error"]:
                return [
                    RawRunRecord(
                        case_id=loaded.case.id,
                        output=output,
                        infrastructure_error=check["infrastructure_error"],
                        started_at=started,
                        duration_ms=(perf_counter() - clock) * 1000,
                    )
                ]
            output["benchmark_code_check"] = check
        return [
            RawRunRecord(
                case_id=loaded.case.id,
                output=output,
                started_at=started,
                duration_ms=(perf_counter() - clock) * 1000,
            )
        ]
~~~

Register mode e2e in orchestrator with EndToEndRunner. In coder-e2e.yaml, map equals.benchmark_code_check.passed to metric tag build_failed so a false result activates the hard-fail policy.

- [ ] **Step 5: Add positive and negative fixtures**

Add:

- A valid static HTML project that passes required-file and content checks without network access.
- An invalid Python project that deterministically fails py_compile and proves build_failed triggers a hard gate.
- A recorded successful end-to-end state containing intent, code_files, review, quality_gate_result, build_result, final_status, and no secrets.

- [ ] **Step 6: Run code and end-to-end tests**

Run:

~~~powershell
cd python-agent
& '.\.venv\Scripts\python.exe' -m pytest tests/benchmark/test_code_execution.py tests/benchmark/test_end_to_end_runner.py -q --basetemp .test-tmp-benchmark
~~~

Expected: traversal is rejected, syntax failure is classified as quality, missing tool is classified as infrastructure, and the saved successful workflow passes.

- [ ] **Step 7: Commit Task 10**

~~~powershell
git add python-agent/benchmark/evaluators/code_execution.py python-agent/benchmark/runners/end_to_end.py python-agent/benchmark/orchestrator.py python-agent/benchmarks/datasets/regression/coder-e2e.yaml python-agent/benchmarks/fixtures/projects python-agent/tests/benchmark/test_code_execution.py python-agent/tests/benchmark/test_end_to_end_runner.py
git commit -m "feat: benchmark generated code and end to end outputs"
~~~

## Task 11: Capture LLM usage and add the nightly live runner

**Files:**
- Modify: python-agent/request_context.py
- Modify: python-agent/core/model_router.py
- Modify: python-agent/llm_factory.py
- Create: python-agent/benchmark/runners/live_llm.py
- Modify: python-agent/benchmark/orchestrator.py
- Create: python-agent/benchmarks/datasets/nightly/live-core.yaml
- Create: python-agent/tests/benchmark/test_usage_capture.py
- Create: python-agent/tests/benchmark/test_live_runner.py

- [ ] **Step 1: Write failing usage-capture tests**

Create test_usage_capture.py with fake AIMessage-like responses:

~~~python
from request_context import capture_llm_usage, record_llm_response


class FakeResponse:
    usage_metadata = {"input_tokens": 12, "output_tokens": 5, "total_tokens": 17}
    response_metadata = {"model_name": "code-structured", "response_cost": 0.004}


def test_capture_llm_usage_keeps_actual_tokens_and_spend():
    with capture_llm_usage() as captured:
        record_llm_response(FakeResponse(), "code-structured")

    assert captured == [
        {
            "model": "code-structured",
            "input_tokens": 12,
            "output_tokens": 5,
            "total_tokens": 17,
            "cost_usd": 0.004,
        }
    ]


def test_capture_does_not_estimate_missing_cost():
    response = FakeResponse()
    response.response_metadata = {"model_name": "code-structured"}
    with capture_llm_usage() as captured:
        record_llm_response(response, "code-structured")

    assert captured[0]["cost_usd"] is None
~~~

- [ ] **Step 2: Run tests and verify missing capture API**

Run:

~~~powershell
cd python-agent
& '.\.venv\Scripts\python.exe' -m pytest tests/benchmark/test_usage_capture.py -q --basetemp .test-tmp-benchmark
~~~

Expected: import fails because capture_llm_usage and record_llm_response do not exist.

- [ ] **Step 3: Add context-local usage capture**

In request_context.py add a ContextVar containing either None or a mutable list. Implement capture_llm_usage as a context manager that installs an empty list, yields it, and resets the token. Implement record_llm_response to read usage_metadata first, fall back to response_metadata.token_usage, preserve cost_usd only when the response supplies a numeric response_cost, and append nothing when capture is inactive.

Modify ModelRouter.route to call record_llm_response for unparsed and tool-enabled AIMessage results. Pass _model=model_alias into parser callbacks. Modify llm_factory._call_with_parser to call record_llm_response(response, _model) before parsing JSON. Add regression tests proving one structured call is recorded exactly once.

Add this implementation to request_context.py:

~~~python
_llm_usage: ContextVar[list[dict[str, object]] | None] = ContextVar(
    "llm_usage",
    default=None,
)


@contextmanager
def capture_llm_usage() -> Iterator[list[dict[str, object]]]:
    captured: list[dict[str, object]] = []
    token = _llm_usage.set(captured)
    try:
        yield captured
    finally:
        _llm_usage.reset(token)


def record_llm_response(response, model: str) -> None:
    captured = _llm_usage.get()
    if captured is None:
        return
    response_metadata = getattr(response, "response_metadata", {}) or {}
    usage = getattr(response, "usage_metadata", None)
    if not isinstance(usage, dict):
        usage = response_metadata.get("token_usage", {}) or {}
    cost = response_metadata.get("response_cost")
    input_tokens = int(usage.get("input_tokens", usage.get("prompt_tokens", 0)))
    output_tokens = int(usage.get("output_tokens", usage.get("completion_tokens", 0)))
    captured.append(
        {
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": int(usage.get("total_tokens", input_tokens + output_tokens)),
            "cost_usd": float(cost) if isinstance(cost, (int, float)) and not isinstance(cost, bool) else None,
        }
    )
~~~

In core/model_router.py import record_llm_response and change the result branches to:

~~~python
if parser:
    result = parser(
        messages,
        _client=client,
        _model=model_alias,
        _config=runnable_config,
    )
    if hasattr(result, "usage_metadata"):
        record_llm_response(result, model_alias)
else:
    response = client.invoke(messages, config=runnable_config)
    record_llm_response(response, model_alias)
    result = response.content or ""
    if not result:
        raise ValueError(f"{model_alias}: empty gateway response")
~~~

In llm_factory._call_with_parser, immediately after each _client.invoke or llm.invoke response, call:

~~~python
record_llm_response(
    response,
    _model or getattr(response, "response_metadata", {}).get("model_name", "unknown"),
)
~~~

Import record_llm_response in llm_factory.py. This division records structured responses inside _call_with_parser and tool-enabled AIMessage responses in ModelRouter, preventing double counting.

Update _ToolEnabledRouter.invoke_with_tools to accept the new keyword without changing behavior:

~~~python
def invoke_with_tools(msgs, _client=None, _model=None, _config=None):
    if _client is None:
        raise RuntimeError("tool-enabled routing requires a model client")
    return _client.bind_tools(self.tools).invoke(msgs, config=_config)
~~~

- [ ] **Step 4: Write live-runner tests with injected agents**

Create test_live_runner.py. Inject a fake target adapter that records request context metadata, returns a state, and calls record_llm_response with a fake response. Assert:

- offline context rejects the run;
- run_id is sent as request_id metadata;
- latency is recorded;
- repeated runs retain each observation rather than selecting the best;
- a model exception becomes infrastructure_error;
- a semantically wrong output remains a quality failure after assertion evaluation.

- [ ] **Step 5: Implement LiveLlmRunner**

LiveLlmRunner maps target names to existing production callables:

~~~python
TARGETS = {"intent", "coder", "reviewer", "e2e"}
~~~

For every repetition, bind request_id as benchmark-<run_id>-<case-id>-<index>, trace_id as the same value, user_id as benchmark, and app_id as a sanitized case ID. Wrap execution in capture_llm_usage, measure wall-clock time, aggregate actual tokens and actual cost when supplied, and preserve every repetition as a distinct RawRunRecord. Never retry a quality failure. Only the existing gateway or transport layer may retry transient provider failures.

Use a target adapter that normalizes production return shapes:

~~~python
def _invoke_target(target: str, state: dict) -> dict:
    if target == "intent":
        return dict(intent_agent(state))
    if target == "reviewer":
        reviewed = reviewer_agent(state)
        return dict(reviewed.get("review") or reviewed)
    if target == "coder":
        previous = (get_project_dir(), get_app_id(), get_user_role())
        with tempfile.TemporaryDirectory(prefix="benchmark-coder-") as project_dir:
            set_tool_context(project_dir, state["app_id"], state.get("user_role", "user"))
            state["project_dir"] = project_dir
            try:
                return dict(coder_agent(state))
            finally:
                set_tool_context(*previous)
    if target == "e2e":
        with tempfile.TemporaryDirectory(prefix="benchmark-e2e-") as output_root:
            with patch.object(config, "CODE_OUTPUT_DIR", output_root):
                return dict(
                    run_workflow(
                        user_request=state["user_request"],
                        user_id=state.get("user_id", "benchmark"),
                        app_id="",
                        code_gen_type=state.get("code_gen_type", "vue_project"),
                        user_role=state.get("user_role", "user"),
                        trace_id=state.get("trace_id", ""),
                    )
                )
    raise ValueError(f"unsupported live target: {target}")


def _safe_app_id(case_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "-", case_id).strip("-")
    return (cleaned or "case")[:64]
~~~

Import re, tempfile, unittest.mock.patch, config, plus get_project_dir, get_app_id, get_user_role, and set_tool_context. Coder cases run inside TemporaryDirectory and restore the previous tool context in a finally block. E2E uses a temporary CODE_OUTPUT_DIR and an empty workflow app_id so Builder cannot index benchmark output into the production vector store. Case IDs never become filesystem paths; request attribution app_id is restricted to ASCII letters, digits, hyphen, and underscore.

The runner returns one RawRunRecord per repetition so every attempt is scored independently:

~~~python
class LiveLlmRunner:
    def run(self, loaded: LoadedCase, context: RunContext) -> list[RawRunRecord]:
        context.assert_mode_allowed(loaded.case.execution.mode)
        records = []
        for attempt in range(loaded.case.execution.repeats):
            request_id = f"benchmark-{context.run_id}-{loaded.case.id}-{attempt}"
            state = dict(loaded.case.input)
            state.update(
                {
                    "user_id": "benchmark",
                    "app_id": _safe_app_id(loaded.case.id),
                    "trace_id": request_id,
                }
            )
            started = datetime.now(UTC).isoformat()
            clock = perf_counter()
            try:
                with bind_request_context(
                    request_id=request_id,
                    trace_id=request_id,
                    user_id="benchmark",
                    app_id=state["app_id"],
                ), capture_llm_usage() as usage:
                    output = _invoke_target(loaded.case.target, state)
            except Exception as exc:
                records.append(
                    RawRunRecord(
                        case_id=loaded.case.id,
                        attempt_index=attempt,
                        infrastructure_error=str(exc),
                        started_at=started,
                        duration_ms=(perf_counter() - clock) * 1000,
                    )
                )
                continue
            input_tokens = sum(int(item["input_tokens"]) for item in usage)
            output_tokens = sum(int(item["output_tokens"]) for item in usage)
            known_costs = [item["cost_usd"] for item in usage if item["cost_usd"] is not None]
            records.append(
                RawRunRecord(
                    case_id=loaded.case.id,
                    attempt_index=attempt,
                    output=output,
                    observed_metrics={
                        "input_tokens": float(input_tokens),
                        "output_tokens": float(output_tokens),
                        "cost_usd": sum(known_costs) if len(known_costs) == len(usage) else None,
                    },
                    started_at=started,
                    duration_ms=(perf_counter() - clock) * 1000,
                )
            )
        return records
~~~

The tests must assert that an infrastructure failure in one attempt does not discard successful sibling attempts.

- [ ] **Step 6: Add reviewed nightly cases**

Create live-core.yaml with focused Intent, Reviewer, Coder, and E2E cases. Set repeats explicitly. Do not copy production secrets or personal prompts into the dataset. Each case must have deterministic assertions that are independent of exact prose.

The first reviewed nightly set contains exactly these cases:

| ID | Target | Scenario | Repeats | Required assertions |
|---|---|---|---:|---|
| intent-vue-clear-live | intent | clear Vue task dashboard request | 3 | phase=intent_done, code_gen_type path exists, no error |
| intent-ambiguous-live | intent | ambiguous request lacking app details | 3 | phase=clarify and clarification.questions path exists |
| reviewer-xss-live | reviewer | v-html fed by user-controlled data | 3 | passed=false, issues mention XSS or v-html |
| reviewer-clean-live | reviewer | escaped text rendering with no unsafe sink | 3 | passed=true and score path exists |
| coder-html-login-live | coder | fixed PRD and architecture for a static login page | 3 | required index.html, no parent traversal, code check passes |
| e2e-html-login-live | e2e | complete static login-page request | 2 | successful terminal state, nonempty code_files, review and build paths exist |

The ambiguous Intent label is intentional: if the model confidently guesses instead of asking for missing requirements, the case must fail rather than accepting either behavior.

- [ ] **Step 7: Run offline tests and a manually authorized live smoke**

Run offline:

~~~powershell
cd python-agent
& '.\.venv\Scripts\python.exe' -m pytest tests/benchmark/test_usage_capture.py tests/benchmark/test_live_runner.py tests/test_model_router_resilience.py tests/test_litellm_request_attribution.py -q --basetemp .test-tmp-benchmark
~~~

Expected: all tests pass without network access.

With LiteLLM credentials available, run:

~~~powershell
cd python-agent
$env:PYTHONPATH='.'
& '.\.venv\Scripts\python.exe' -m benchmark.cli run --suite benchmarks/suites/nightly.yaml --output benchmarks/reports/nightly-result.json --html-output benchmarks/reports/nightly-report.html
~~~

Expected: live cases execute through LiteLLM; report metadata identifies model aliases and prompt fingerprint; missing spend remains null rather than estimated.

- [ ] **Step 8: Commit Task 11**

~~~powershell
git add python-agent/request_context.py python-agent/core/model_router.py python-agent/llm_factory.py python-agent/benchmark/runners/live_llm.py python-agent/benchmark/orchestrator.py python-agent/benchmarks/datasets/nightly/live-core.yaml python-agent/tests/benchmark/test_usage_capture.py python-agent/tests/benchmark/test_live_runner.py
git commit -m "feat: add live llm benchmark runner"
~~~

## Task 12: Add CI workflows, benchmark marker collection, and operating documentation

**Files:**
- Modify: python-agent/tests/conftest.py
- Create: .github/workflows/benchmark.yml
- Create: python-agent/benchmarks/README.md
- Modify: README.md
- Create: python-agent/tests/benchmark/test_ci_contract.py

- [ ] **Step 1: Write failing CI contract tests**

Create test_ci_contract.py:

~~~python
from pathlib import Path

import yaml


ROOT = Path(__file__).parents[3]


def test_pr_job_never_receives_litellm_secrets():
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "benchmark.yml").read_text(encoding="utf-8")
    )
    pr_job = workflow["jobs"]["benchmark-pr"]
    rendered = str(pr_job)
    assert "LITELLM_API_KEY" not in rendered
    assert "LITELLM_BASE_URL" not in rendered


def test_nightly_job_runs_only_for_schedule_or_manual_dispatch():
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "benchmark.yml").read_text(encoding="utf-8")
    )
    condition = workflow["jobs"]["benchmark-nightly"]["if"]
    assert "schedule" in condition
    assert "workflow_dispatch" in condition
~~~

- [ ] **Step 2: Run tests and verify the workflow is absent**

Run:

~~~powershell
cd python-agent
& '.\.venv\Scripts\python.exe' -m pytest tests/benchmark/test_ci_contract.py -q --basetemp .test-tmp-benchmark
~~~

Expected: tests fail because .github/workflows/benchmark.yml is absent.

- [ ] **Step 3: Register benchmark collection**

Add benchmark to MARKER_FILE_ALLOWLIST in tests/conftest.py and list every test file under tests/benchmark explicitly. Mark the benchmark test modules with pytestmark = pytest.mark.benchmark. Run collection:

~~~powershell
cd python-agent
& '.\.venv\Scripts\python.exe' -m pytest -m benchmark --collect-only -q
~~~

Expected: every intended benchmark framework test is collected and no unrelated test is collected.

- [ ] **Step 4: Add GitHub Actions**

Create benchmark.yml with:

- pull_request and workflow_dispatch triggers for benchmark-pr;
- schedule and workflow_dispatch triggers for benchmark-nightly;
- Python 3.12, Node setup, uv installation, and dependency caching;
- benchmark-pr running pytest -m benchmark followed by the offline PR suite;
- benchmark-nightly receiving LITELLM_BASE_URL and LITELLM_API_KEY only from GitHub Secrets;
- JSON and HTML reports uploaded as artifacts even when the benchmark gate fails;
- concurrency cancellation for superseded PR runs, but no cancellation of active nightly baselines.

The PR job must not reference any LiteLLM secret. The nightly job condition must be:

~~~yaml
if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'
~~~

Use this workflow as the initial complete implementation:

~~~yaml
name: benchmark

on:
  pull_request:
  workflow_dispatch:
  schedule:
    - cron: "30 18 * * *"

concurrency:
  group: benchmark-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}

jobs:
  benchmark-pr:
    if: github.event_name == 'pull_request' || github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
        with:
          enable-cache: true
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: npm
          cache-dependency-path: RainN0Coding-frontend/package-lock.json
      - name: Install Python dependencies
        working-directory: python-agent
        run: uv sync --frozen
      - name: Run benchmark framework tests
        working-directory: python-agent
        run: uv run pytest -m benchmark -q --basetemp .test-tmp-benchmark
      - name: Run offline benchmark gate
        working-directory: python-agent
        run: uv run python -m benchmark.cli run --suite benchmarks/suites/pr.yaml --output benchmarks/reports/pr-result.json --html-output benchmarks/reports/pr-report.html
      - name: Upload PR benchmark report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: benchmark-pr-report
          path: |
            python-agent/benchmarks/reports/
            python-agent/benchmarks/records/runs/

  benchmark-nightly:
    if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-latest
    env:
      LITELLM_BASE_URL: ${{ secrets.LITELLM_BASE_URL }}
      LITELLM_API_KEY: ${{ secrets.LITELLM_API_KEY }}
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
        with:
          enable-cache: true
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: npm
          cache-dependency-path: RainN0Coding-frontend/package-lock.json
      - name: Install Python dependencies
        working-directory: python-agent
        run: uv sync --frozen
      - name: Run nightly benchmark
        working-directory: python-agent
        run: uv run python -m benchmark.cli run --suite benchmarks/suites/nightly.yaml --output benchmarks/reports/nightly-result.json --html-output benchmarks/reports/nightly-report.html
      - name: Upload nightly benchmark report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: benchmark-nightly-report
          path: |
            python-agent/benchmarks/reports/
            python-agent/benchmarks/records/runs/
~~~

Before committing, verify RainN0Coding-frontend/package-lock.json exists. If it does not, remove only the two npm cache lines and both cache-dependency-path lines; do not create a lockfile merely to satisfy caching.

- [ ] **Step 5: Write operating documentation**

Document:

- dataset directories and provenance rules;
- validate, PR, nightly, compare, and promote commands;
- exit codes 0, 1, and 2;
- how to add a reviewed case without leaking user data;
- how to inspect JSON and HTML reports;
- why Reviewer self-score is not the benchmark verdict;
- why online score-threshold RAG signals are not labeled Precision/Recall;
- how to review and promote a baseline without overwriting one;
- required GitHub Secrets for nightly only.

Link this guide from the root README under a Benchmark heading.

- [ ] **Step 6: Run focused and legacy regression verification**

Run:

~~~powershell
cd python-agent
& '.\.venv\Scripts\python.exe' -m pytest -m benchmark -q --basetemp .test-tmp-benchmark
& '.\.venv\Scripts\python.exe' -m pytest tests/test_agent_eval_dataset.py tests/test_agent_eval_evaluator.py tests/test_agent_eval_golden_cases.py tests/test_agent_eval_runner.py -q --basetemp .test-tmp-agent-eval
& '.\.venv\Scripts\python.exe' -m benchmark.cli validate --suite benchmarks/suites/pr.yaml
& '.\.venv\Scripts\python.exe' -m benchmark.cli run --suite benchmarks/suites/pr.yaml --output benchmarks/reports/pr-result.json --html-output benchmarks/reports/pr-report.html
~~~

Expected: benchmark tests pass, 12 legacy agent_eval tests pass, validation succeeds, PR suite returns 0, and JSON plus HTML reports are created.

- [ ] **Step 7: Verify negative exit paths**

Run focused tests that inject:

- a wrong Supervisor route or failed hard metric and assert CLI exit 1;
- a missing replay record and assert CLI exit 2;
- an incompatible baseline and assert compare exit 2;
- a duplicate baseline promotion and assert refusal without overwrite.

Expected: quality and infrastructure failures remain distinguishable.

- [ ] **Step 8: Commit Task 12**

~~~powershell
git add .github/workflows/benchmark.yml README.md python-agent/benchmarks/README.md python-agent/tests/conftest.py python-agent/tests/benchmark
git commit -m "ci: enforce benchmark regression gates"
~~~

## Final verification

- [ ] **Step 1: Run the complete benchmark test marker**

~~~powershell
cd python-agent
& '.\.venv\Scripts\python.exe' -m pytest -m benchmark -q --basetemp .test-tmp-benchmark
~~~

Expected: exit code 0 with no failures or errors.

- [ ] **Step 2: Run the complete Python suite**

~~~powershell
cd python-agent
$env:PYTHONPATH='.'
& '.\.venv\Scripts\python.exe' -m pytest tests -q --basetemp .test-tmp-full
~~~

Expected: exit code 0. If Windows emits a native onnxruntime or fastembed access violation after pytest assertions finish, report assertion status and native-process health separately rather than calling the run fully healthy.

- [ ] **Step 3: Run offline acceptance**

~~~powershell
cd python-agent
& '.\.venv\Scripts\python.exe' -m benchmark.cli validate --suite benchmarks/suites/pr.yaml
& '.\.venv\Scripts\python.exe' -m benchmark.cli run --suite benchmarks/suites/pr.yaml --output benchmarks/reports/pr-result.json --html-output benchmarks/reports/pr-report.html
~~~

Expected: validation and run return 0; report metadata contains Git SHA, prompt fingerprint, dataset version, model aliases, and offline=true; HTML opens without network access.

- [ ] **Step 4: Run nightly acceptance when credentials are available**

~~~powershell
cd python-agent
& '.\.venv\Scripts\python.exe' -m benchmark.cli run --suite benchmarks/suites/nightly.yaml --output benchmarks/reports/nightly-result.json --html-output benchmarks/reports/nightly-report.html
~~~

Expected: live calls are attributed by benchmark run and case, repeated observations are preserved, and cost remains null when LiteLLM does not provide actual spend.

- [ ] **Step 5: Review the branch diff**

~~~powershell
git diff --check
git status --short
git log --oneline --decorate -12
~~~

Expected: no whitespace errors, only planned files are changed, generated reports and run records are ignored, and every task has an independent commit.
