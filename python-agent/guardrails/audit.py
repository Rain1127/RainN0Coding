import importlib
import logging

from guardrails.models import GuardrailAuditRecord, GuardrailDecision


logger = logging.getLogger("guardrails")


def emit_guardrail_audit(record: GuardrailAuditRecord) -> None:
    if record.action == "allow" and not _current_config().GUARDRAILS_AUDIT_LOW_RISK:
        return

    payload = {
        "action": record.action,
        "severity": record.severity,
        "rule_id": record.rule_id,
        "message": record.message,
        "request_id": record.request_id or "",
        "trace_id": record.trace_id or "",
        "user_id": record.user_id or "",
        "app_id": record.app_id or "",
        "tool_name": record.tool_name or "",
        "path": record.path or "",
        "details": record.details,
    }
    logger.warning("guardrail_audit %s", payload)


def audit_from_decision(
    decision: GuardrailDecision,
    *,
    request_id: str = "",
    trace_id: str = "",
    user_id: str = "",
    app_id: str = "",
    tool_name: str = "",
    path: str = "",
) -> None:
    emit_guardrail_audit(
        GuardrailAuditRecord(
            rule_id=decision.rule_id,
            action=decision.action,
            severity=decision.severity,
            message=decision.message,
            request_id=request_id,
            trace_id=trace_id,
            user_id=user_id,
            app_id=app_id,
            tool_name=tool_name,
            path=path,
            details=dict(decision.details),
        )
    )


def _current_config():
    return importlib.import_module("config").config
