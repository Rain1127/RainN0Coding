from __future__ import annotations

from pathlib import Path
import re

import pytest
import yaml


pytestmark = pytest.mark.benchmark

ROOT = Path(__file__).parents[3]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "benchmark.yml"
PINNED_ACTIONS = {
    "actions/checkout": "11d5960a326750d5838078e36cf38b85af677262",
    "actions/setup-python": "a26af69be951a213d495a4c3e4e4022e16d87065",
    "astral-sh/setup-uv": "d0d8abe699bfb85fec6de9f7adb5ae17292296ff",
    "actions/setup-node": "49933ea5288caeca8642d1e84afbd3f7d6820020",
    "actions/upload-artifact": "ea165f8d65b6e75b540449e92b4886f43607fa02",
}


def _workflow() -> dict:
    document = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _triggers(workflow: dict) -> dict:
    # PyYAML follows YAML 1.1 and parses an unquoted `on` key as boolean True.
    triggers = workflow.get("on", workflow.get(True))
    assert isinstance(triggers, dict)
    return triggers


def _render(value: object) -> str:
    return yaml.safe_dump(value, sort_keys=True)


def test_workflow_declares_pr_manual_and_scheduled_triggers() -> None:
    triggers = _triggers(_workflow())

    assert {"pull_request", "workflow_dispatch", "schedule"} <= set(triggers)
    assert triggers["schedule"]


def test_pr_job_is_offline_and_never_receives_litellm_secrets() -> None:
    pr_job = _workflow()["jobs"]["benchmark-pr"]
    rendered = _render(pr_job)

    assert "LITELLM_API_KEY" not in rendered
    assert "LITELLM_BASE_URL" not in rendered
    assert "pytest -m benchmark" in rendered
    assert "benchmarks/suites/pr.yaml" in rendered
    assert "benchmarks/suites/nightly.yaml" not in rendered


def test_nightly_job_runs_only_for_schedule_or_manual_dispatch() -> None:
    nightly_job = _workflow()["jobs"]["benchmark-nightly"]

    assert nightly_job["if"] == (
        "github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'"
    )
    run_step = next(
        step for step in nightly_job["steps"] if step.get("name") == "Run nightly benchmark"
    )
    assert run_step["env"] == {
        "LITELLM_BASE_URL": "${{ secrets.LITELLM_BASE_URL }}",
        "LITELLM_API_KEY": "${{ secrets.LITELLM_API_KEY }}",
        "MILVUS_MODE": "lite",
    }
    for step in nightly_job["steps"]:
        if step is not run_step:
            assert "LITELLM_API_KEY" not in _render(step)
            assert "LITELLM_BASE_URL" not in _render(step)
    assert "benchmarks/suites/nightly.yaml" in _render(run_step)


def test_nightly_seeds_lite_vector_store_before_running_and_stops_on_failure() -> None:
    steps = _workflow()["jobs"]["benchmark-nightly"]["steps"]
    seed_index = next(index for index, step in enumerate(steps) if step.get("name") == "Seed RAG vector store")
    run_index = next(index for index, step in enumerate(steps) if step.get("name") == "Run nightly benchmark")
    seed = steps[seed_index]

    assert seed_index < run_index
    assert seed["run"] == "uv run python -m rag.seed_vector_store"
    assert seed["env"] == {"MILVUS_MODE": "lite"}
    assert seed.get("continue-on-error", False) is False
    assert "if" not in steps[run_index]


def test_workflow_uses_read_only_permissions_and_nonpersistent_checkout_credentials() -> None:
    workflow = _workflow()

    assert workflow["permissions"] == {"contents": "read"}
    for job in workflow["jobs"].values():
        checkout = next(
            step for step in job["steps"] if step.get("uses", "").startswith("actions/checkout@")
        )
        assert checkout["with"]["persist-credentials"] is False


def test_all_actions_are_pinned_to_full_commit_shas_with_version_comments() -> None:
    workflow = _workflow()
    action_refs = [
        step["uses"]
        for job in workflow["jobs"].values()
        for step in job["steps"]
        if "uses" in step
    ]

    assert action_refs
    assert all(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}", ref) for ref in action_refs)
    for reference in action_refs:
        action, sha = reference.split("@", maxsplit=1)
        assert sha == PINNED_ACTIONS[action]
    workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")
    uses_lines = [line.strip() for line in workflow_text.splitlines() if line.strip().startswith("uses:") or line.strip().startswith("- uses:")]
    assert uses_lines
    assert all(re.search(r"\s+#\s+v\d+\s*$", line) for line in uses_lines)


@pytest.mark.parametrize("job_name", ["benchmark-pr", "benchmark-nightly"])
def test_reports_and_raw_records_are_always_uploaded(job_name: str) -> None:
    job = _workflow()["jobs"][job_name]
    upload_steps = [
        step
        for step in job["steps"]
        if step.get("uses", "").startswith("actions/upload-artifact@")
    ]

    assert len(upload_steps) == 1
    upload = upload_steps[0]
    assert upload["if"] == "always()"
    assert "python-agent/benchmarks/reports/" in upload["with"]["path"]
    assert "python-agent/benchmarks/records/runs/" in upload["with"]["path"]


@pytest.mark.parametrize("job_name", ["benchmark-pr", "benchmark-nightly"])
def test_jobs_pin_python_node_and_use_existing_lockfiles_for_caches(job_name: str) -> None:
    job = _workflow()["jobs"][job_name]
    rendered = _render(job)

    assert "actions/setup-python@" in rendered
    assert "python-version: '3.12'" in rendered
    assert "astral-sh/setup-uv@" in rendered
    assert "python-agent/uv.lock" in rendered
    assert "actions/setup-node@" in rendered
    assert "node-version: '22'" in rendered
    assert "cache: npm" in rendered
    assert "RainN0Coding-frontend/package-lock.json" in rendered
    assert (ROOT / "python-agent" / "uv.lock").is_file()
    assert (ROOT / "RainN0Coding-frontend" / "package-lock.json").is_file()


def test_concurrency_cancels_superseded_prs_but_not_nightly_runs() -> None:
    concurrency = _workflow()["concurrency"]

    assert "github.event.pull_request.number" in concurrency["group"]
    assert "github.ref" in concurrency["group"]
    assert concurrency["cancel-in-progress"] == "${{ github.event_name == 'pull_request' }}"
