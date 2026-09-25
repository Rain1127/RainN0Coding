from __future__ import annotations

from pathlib import Path

import pytest
import yaml


pytestmark = pytest.mark.benchmark

ROOT = Path(__file__).parents[3]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "benchmark.yml"


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
    rendered = _render(nightly_job)
    assert "secrets.LITELLM_API_KEY" in rendered
    assert "secrets.LITELLM_BASE_URL" in rendered
    assert "benchmarks/suites/nightly.yaml" in rendered


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
