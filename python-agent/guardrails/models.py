from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class GuardrailDecision:
    action: str
    severity: str
    rule_id: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def allow(cls, rule_id: str, details: dict[str, Any] | None = None) -> "GuardrailDecision":
        return cls(
            action="allow",
            severity="low",
            rule_id=rule_id,
            message="allowed",
            details=details or {},
        )

    @classmethod
    def warn(
        cls,
        rule_id: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> "GuardrailDecision":
        return cls(
            action="warn",
            severity="medium",
            rule_id=rule_id,
            message=message,
            details=details or {},
        )

    @classmethod
    def block(
        cls,
        rule_id: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> "GuardrailDecision":
        return cls(
            action="block",
            severity="high",
            rule_id=rule_id,
            message=message,
            details=details or {},
        )


@dataclass(slots=True)
class PromptContext:
    prompt: str
    request_id: str | None = None
    trace_id: str | None = None
    user_id: str | None = None
    app_id: str | None = None
    history: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class ToolAction:
    tool_name: str
    project_dir: str | None = None
    relative_path: str | None = None
    content: str | None = None
    old_content: str | None = None
    new_content: str | None = None
    dir_path: str | None = None
    user_role: str | None = None


@dataclass(slots=True)
class OutputEvent:
    event_type: str
    path: str | None = None
    content: str | None = None
    request_id: str | None = None
    trace_id: str | None = None


@dataclass(slots=True)
class GuardrailAuditRecord:
    rule_id: str
    action: str
    severity: str
    message: str
    request_id: str | None = None
    trace_id: str | None = None
    user_id: str | None = None
    app_id: str | None = None
    tool_name: str | None = None
    path: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
