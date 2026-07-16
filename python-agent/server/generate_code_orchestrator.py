import json
import importlib
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from logging import Logger
from typing import Any

from guardrails.audit import audit_from_decision
from guardrails.engine import evaluate_prompt
from guardrails.models import PromptContext
from tracing import resolve_trace_id, set_current_trace_id


@dataclass(slots=True)
class ImmediateResponse:
    body: dict[str, Any]
    status_code: int


@dataclass(slots=True)
class GenerateCodeOrchestrationResult:
    immediate_response: ImmediateResponse | None = None
    event_generator: AsyncIterator[dict[str, str]] | None = None


def _config():
    return importlib.import_module("config").config


def __getattr__(name: str):
    if name == "config":
        return _config()
    raise AttributeError(name)


def _status_from_sse_event(event: str) -> str | None:
    try:
        payload = json.loads(event)
    except (TypeError, ValueError):
        return None

    event_type = payload.get("type")
    status = payload.get("status")
    if event_type == "error":
        return str(status or "error")
    if event_type == "done" and status and status != "success":
        return str(status)
    return None


def _guardrail_block_response(request, *, resolved_trace_id: str, prompt_decision) -> ImmediateResponse:
    return ImmediateResponse(
        body={
            "type": "error",
            "status": "guardrail_blocked",
            "rule_id": prompt_decision.rule_id,
            "message": prompt_decision.message,
            "request_id": request.request_id,
            "trace_id": resolved_trace_id,
        },
        status_code=400,
    )


def _overload_response(request, *, resolved_trace_id: str) -> ImmediateResponse:
    return ImmediateResponse(
        body={
            "type": "error",
            "status": "overloaded",
            "message": "AI Agent capacity is full. Please retry later.",
            "request_id": request.request_id,
            "trace_id": resolved_trace_id,
        },
        status_code=_config().AGENT_OVERLOAD_STATUS_CODE,
    )


async def orchestrate_generate_code(
    request,
    *,
    semaphore,
    stream_workflow: Callable[..., AsyncIterator[str]],
    record_request,
    active_requests_metric,
    logger: Logger,
) -> GenerateCodeOrchestrationResult:
    resolved_trace_id = resolve_trace_id(request.trace_id)
    set_current_trace_id(resolved_trace_id)

    if _config().GUARDRAILS_ENABLED:
        prompt_decision = evaluate_prompt(
            PromptContext(
                prompt=request.prompt,
                request_id=request.request_id,
                trace_id=resolved_trace_id,
                user_id=request.user_id,
                app_id=request.app_id,
                history=request.history,
            )
        )
        audit_from_decision(
            prompt_decision,
            request_id=request.request_id,
            trace_id=resolved_trace_id,
            user_id=request.user_id,
            app_id=request.app_id,
        )
        if prompt_decision.action == "block":
            record_request(request.user_id, request.app_id, request.code_gen_type, "guardrail_blocked")
            return GenerateCodeOrchestrationResult(
                immediate_response=_guardrail_block_response(
                    request,
                    resolved_trace_id=resolved_trace_id,
                    prompt_decision=prompt_decision,
                )
            )

    if semaphore.locked():
        record_request(request.user_id, request.app_id, request.code_gen_type, "overloaded")
        return GenerateCodeOrchestrationResult(
            immediate_response=_overload_response(
                request,
                resolved_trace_id=resolved_trace_id,
            )
        )

    await semaphore.acquire()
    active_requests_metric.inc()
    logger.info(
        f"Received code generation request: user={request.user_id}, app={request.app_id}, "
        f"request_id={request.request_id}, trace_id={resolved_trace_id}, prompt={request.prompt[:60]}..."
    )

    async def event_generator():
        status = "success"
        try:
            async for event in stream_workflow(
                user_request=request.prompt,
                user_id=request.user_id,
                app_id=request.app_id,
                code_gen_type=request.code_gen_type,
                user_role=request.user_role,
                trace_id=resolved_trace_id,
                request_id=request.request_id,
            ):
                event_status = _status_from_sse_event(event)
                if event_status and status == "success":
                    status = event_status
                yield {"data": event}
        except Exception:
            status = "error"
            raise
        finally:
            active_requests_metric.dec()
            record_request(request.user_id, request.app_id, request.code_gen_type, status)
            semaphore.release()

    return GenerateCodeOrchestrationResult(event_generator=event_generator())
