import re

from guardrails.models import GuardrailDecision, PromptContext
from guardrails.policy import (
    HIGH_RISK_PROMPT_PATTERNS,
    MEDIUM_RISK_PROMPT_PATTERNS,
    max_prompt_chars,
)

_SECRET_ACCESS_CLASSIFIERS = (
    r"(?i)\bread\s+\.env\b",
    r"(?i)\bshow\s+.*\.env\b",
    r"(?i)\benv(ironment)?\s*var(iable)?s?\b",
    r"(?i)\benv(ironment)?\s*var(iable)?s?\s*file\b",
    r"(?i)\bssh\s+key\b",
    r"(?i)\bshow\s+ssh\s+key\b",
    r"(?i)\bsecret(s)?\b",
    r"(?i)\bshow\s+secret\s+key\b",
    r"(?i)\bapi\s*key\b",
    r"(?i)\bsecret\s*key\b",
    r"(?i)\bprivate\s*key\b",
    r"\u8bfb\u53d6\s*\.env",
    r"\u73af\u5883\u53d8\u91cf",
    r"\u73af\u5883\u53d8\u91cf\u6587\u4ef6",
    r"\u8bfb\u53d6.*\u73af\u5883\u53d8\u91cf",
    r"\u5c55\u793a.*ssh\s*key",
    r"ssh\s*key",
    r"\u5bc6\u94a5",
    r"\u79d8\u94a5",
    r"\u51ed\u8bc1",
)

_PATH_ESCAPE_CLASSIFIERS = (
    r"(?i)\bdelete\s+all\s+files\b",
    r"(?i)\bwipe\s+project\b",
    r"(?i)\brm\s+-rf\b",
    r"(?i)\bwrite\s+outside\s+project\b",
    r"(?i)\boutside\s+project\b",
    r"\u5220\u9664\u5168\u90e8\u6587\u4ef6",
    r"\u6e05\u7a7a\u9879\u76ee",
    r"\u9879\u76ee\u5916",
    r"\u5199\u5165\u9879\u76ee\u5916",
)


def evaluate_prompt_context(ctx: PromptContext) -> GuardrailDecision:
    high_risk_rule_id = _classify_high_risk_prompt(ctx.prompt)
    if high_risk_rule_id:
        return _high_risk_decision(high_risk_rule_id, ctx.prompt)

    for pattern in MEDIUM_RISK_PROMPT_PATTERNS:
        if re.search(pattern, ctx.prompt):
            return GuardrailDecision.warn(
                "prompt.protected_file_warn",
                "prompt targets protected files or elevated script creation",
                _details(pattern, ctx.prompt),
            )

    prompt_length = len(ctx.prompt)
    limit = max_prompt_chars()
    if prompt_length > limit:
        details = _details(None, ctx.prompt)
        details["prompt_length"] = prompt_length
        details["max_prompt_chars"] = limit
        return GuardrailDecision.warn(
            "prompt.prompt_length_warn",
            "prompt exceeds configured length threshold",
            details,
        )

    return GuardrailDecision.allow("prompt.ok", {"prompt_length": len(ctx.prompt)})


def _classify_high_risk_prompt(prompt: str) -> str | None:
    if _matches_any_classifier(prompt, _SECRET_ACCESS_CLASSIFIERS):
        return "prompt.secret_access_blocked"
    if _matches_any_classifier(prompt, _PATH_ESCAPE_CLASSIFIERS):
        return "prompt.path_escape_blocked"
    if _matches_any_classifier(prompt, HIGH_RISK_PROMPT_PATTERNS):
        return "prompt.path_escape_blocked"
    return None


def _high_risk_decision(rule_id: str, prompt: str) -> GuardrailDecision:
    message_by_rule = {
        "prompt.secret_access_blocked": "prompt requests access to secrets or environment files",
        "prompt.path_escape_blocked": "prompt requests destructive or out-of-project actions",
    }
    return GuardrailDecision.block(
        rule_id,
        message_by_rule[rule_id],
        _details(None, prompt),
    )


def _matches_any_classifier(prompt: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, prompt) for pattern in patterns)


def _details(pattern: str | None, prompt: str) -> dict[str, int | str]:
    details: dict[str, int | str] = {
        "prompt_length": len(prompt),
    }
    if pattern:
        details["matched_pattern"] = pattern
    return details
