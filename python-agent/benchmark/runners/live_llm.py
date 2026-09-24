from __future__ import annotations

import re
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from time import perf_counter
from typing import Callable
from unittest.mock import patch

from benchmark.contracts import LoadedCase, RawRunRecord
from benchmark.evaluators.code_execution import validate_generated_files
from benchmark.redaction import redact_error
from benchmark.runners.base import RunContext
from request_context import bind_request_context, capture_llm_usage


TARGETS = frozenset({"intent", "reviewer", "coder", "e2e"})
TargetInvoker = Callable[[str, dict], dict]


def _safe_app_id(case_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "-", case_id).strip("-")
    return (cleaned or "case")[:64]


def _load_target(target: str) -> Callable:
    """Import production targets only when a live case actually executes."""
    if target == "intent":
        from agents.intent_agent import intent_agent

        return intent_agent
    if target == "reviewer":
        from agents.reviewer_agent import reviewer_agent

        return reviewer_agent
    if target == "coder":
        from agents.coder_agent import coder_agent

        return coder_agent
    if target == "e2e":
        from workflow.code_gen_workflow import run_workflow

        return run_workflow
    raise ValueError(f"unsupported live target: {target}")


def _mark_generated_code(output: dict) -> dict:
    """Expose deterministic path/schema checks for live generated artifacts."""
    try:
        validate_generated_files(output.get("code_files"))
    except ValueError as exc:
        output["benchmark_code_check"] = {
            "passed": False,
            "metric": "build_failed",
            "log": redact_error(exc),
        }
    else:
        output["benchmark_code_check"] = {
            "passed": True,
            "metric": "build_success",
            "log": "generated file paths and contents are valid",
        }
    return output


def _invoke_target(target: str, state: dict) -> dict:
    callable_target = _load_target(target)
    if target == "intent":
        return dict(callable_target(state))
    if target == "reviewer":
        reviewed = callable_target(state)
        return dict(reviewed.get("review") or reviewed)
    if target == "coder":
        from tools import get_app_id, get_project_dir, get_user_role, set_tool_context

        previous = (get_project_dir(), get_app_id(), get_user_role())
        with tempfile.TemporaryDirectory(prefix="benchmark-coder-") as project_dir:
            set_tool_context(project_dir, state["app_id"], state.get("user_role", "user"))
            state["project_dir"] = project_dir
            try:
                return _mark_generated_code(dict(callable_target(state)))
            finally:
                set_tool_context(*previous)
    if target == "e2e":
        from config import config

        with tempfile.TemporaryDirectory(prefix="benchmark-e2e-") as output_root:
            with patch.object(config, "CODE_OUTPUT_DIR", output_root):
                return dict(
                    callable_target(
                        user_request=state["user_request"],
                        user_id=state.get("user_id", "benchmark"),
                        app_id="",
                        code_gen_type=state.get("code_gen_type", "vue_project"),
                        user_role=state.get("user_role", "user"),
                        trace_id=state.get("trace_id", ""),
                    )
                )
    raise ValueError(f"unsupported live target: {target}")


def _usage_metrics(usage: list[dict[str, object]]) -> dict[str, float | None]:
    input_tokens = sum(int(item["input_tokens"]) for item in usage)
    output_tokens = sum(int(item["output_tokens"]) for item in usage)
    total_tokens = sum(int(item["total_tokens"]) for item in usage)
    costs = [item["cost_usd"] for item in usage]
    cost = (
        sum(float(item) for item in costs)
        if costs and all(item is not None for item in costs)
        else None
    )
    return {
        "input_tokens": float(input_tokens),
        "output_tokens": float(output_tokens),
        "total_tokens": float(total_tokens),
        "cost_usd": cost,
    }


class LiveLlmRunner:
    def __init__(self, target_invoker: TargetInvoker | None = None):
        self._target_invoker = target_invoker or _invoke_target

    def run(self, loaded: LoadedCase, context: RunContext) -> list[RawRunRecord]:
        case = loaded.case
        context.assert_mode_allowed(case.execution.mode)
        if case.execution.mode != "live":
            raise ValueError(f"{case.id}: live runner requires live mode")
        if case.target not in TARGETS:
            raise ValueError(f"{case.id}: unsupported live target: {case.target}")

        records: list[RawRunRecord] = []
        safe_case_id = _safe_app_id(case.id)
        for attempt in range(case.execution.repeats):
            request_id = f"benchmark-{context.run_id}-{safe_case_id}-{attempt}"
            state = deepcopy(case.input)
            state.update(
                {
                    "request_id": request_id,
                    "user_id": "benchmark",
                    "app_id": safe_case_id,
                    "trace_id": request_id,
                }
            )
            started = datetime.now(timezone.utc).isoformat()
            clock = perf_counter()
            usage: list[dict[str, object]] = []
            try:
                with bind_request_context(
                    request_id=request_id,
                    trace_id=request_id,
                    user_id="benchmark",
                    app_id=safe_case_id,
                ), capture_llm_usage() as usage:
                    output = dict(self._target_invoker(case.target, state))
                records.append(
                    RawRunRecord(
                        case_id=case.id,
                        attempt_index=attempt,
                        output=output,
                        observed_metrics=_usage_metrics(usage),
                        started_at=started,
                        duration_ms=(perf_counter() - clock) * 1000,
                    )
                )
            except Exception as exc:
                records.append(
                    RawRunRecord(
                        case_id=case.id,
                        attempt_index=attempt,
                        observed_metrics=_usage_metrics(usage) if usage else {},
                        infrastructure_error=redact_error(exc),
                        started_at=started,
                        duration_ms=(perf_counter() - clock) * 1000,
                    )
                )
        return records
