from guardrails.models import GuardrailDecision, OutputEvent, PromptContext, ToolAction
from guardrails.output_guard import evaluate_output_event_context
from guardrails.prompt_guard import evaluate_prompt_context
from guardrails.tool_guard import evaluate_tool_action_context


def evaluate_prompt(ctx: PromptContext) -> GuardrailDecision:
    return evaluate_prompt_context(ctx)


def evaluate_tool_action(action: ToolAction) -> GuardrailDecision:
    return evaluate_tool_action_context(action)


def evaluate_output_event(event: OutputEvent) -> GuardrailDecision:
    return evaluate_output_event_context(event)
