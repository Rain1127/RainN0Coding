import os

from guardrails.models import GuardrailDecision, OutputEvent
from guardrails.policy import PROTECTED_FILE_NAMES, SENSITIVE_FILE_MARKERS, max_file_write_bytes


def evaluate_output_event_context(event: OutputEvent) -> GuardrailDecision:
    if event.event_type != "code_file":
        return GuardrailDecision.allow("output.ok", {"event_type": event.event_type})

    path = event.path or ""
    path_lower = path.lower()
    target_name = os.path.basename(path)

    if any(marker in path_lower for marker in SENSITIVE_FILE_MARKERS) or target_name in PROTECTED_FILE_NAMES:
        return GuardrailDecision.block(
            "output.protected_path_blocked",
            "generated output targeted a protected or sensitive path",
            {"path": path},
        )

    if len((event.content or "").encode("utf-8")) > max_file_write_bytes():
        return GuardrailDecision.block(
            "output.oversize_code_file_blocked",
            "generated output exceeded the configured size limit",
            {"path": path},
        )

    return GuardrailDecision.allow("output.ok", {"path": path})
