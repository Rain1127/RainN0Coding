"""Thin business-model router backed by the LiteLLM gateway."""

from langchain_openai import ChatOpenAI

from config import config
from core.model_registry import get_model_alias
from monitoring import record_llm_call
from request_context import build_litellm_metadata, record_llm_response
from tracing import start_span
from workflow.budget import active_budget, active_output_limit, BudgetExceeded


class ModelRouter:
    """Map a business model group to one LiteLLM request."""

    def route(
        self,
        group_name: str,
        messages: list,
        parser=None,
        allow_degraded: bool = True,
        langsmith_extra: dict | None = None,
        budget_extra_input: str = "",
    ):
        model_alias = get_model_alias(group_name)
        from workflow.run_journal import active_journal
        journal = active_journal.get()
        metadata = (langsmith_extra or {}).get('metadata', {})
        coder_round = metadata.get('react_round') if (langsmith_extra or {}).get('run_name') == 'coder_agent' else None
        replay = journal.prepare_model(messages, model_alias, group_name, budget_extra_input,
                                       metadata.get('instruction_ids'), coder_round) if journal else None
        if replay is not None:
            class ReplayClient:
                def bind_tools(self, *args, **kwargs):
                    return self
                def invoke(self, *args, **kwargs):
                    return replay
            return parser(messages, _client=ReplayClient(), _model=model_alias, _config=langsmith_extra) if parser else replay.content
        budget = active_budget.get()
        output_limit = budget.reserve(messages, budget_extra_input) if budget else active_output_limit.get()
        if journal:
            journal.reserved(model_alias, output_limit, min(config.LLM_TIMEOUT, budget.remaining_seconds()) if budget else config.LLM_TIMEOUT)
        runnable_config = dict(langsmith_extra or {})
        if journal:
            runnable_config['metadata'] = {**runnable_config.get('metadata', {}),
                'harness_step_id': journal.frame['request_step'], 'artifact_run_id': journal.state.get('artifact_run_id'),
                'contract_version': (journal.state.get('acceptance_contract') or {}).get('version')}
        litellm_metadata = build_litellm_metadata(
            runnable_config.get("metadata", {})
        )

        with start_span(
            "llm.gateway",
            {"llm.group": group_name, "llm.model": model_alias},
        ):
            try:
                client = ChatOpenAI(
                    model=model_alias,
                    api_key=config.LITELLM_API_KEY,
                    base_url=config.LITELLM_BASE_URL,
                    timeout=min(config.LLM_TIMEOUT, budget.remaining_seconds()) if budget else config.LLM_TIMEOUT,
                    max_retries=0,
                    temperature=0.0,
                    extra_body={"metadata": litellm_metadata},
                    **({"max_tokens": output_limit} if output_limit is not None else {}),
                )
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
                if budget and budget.pending:
                    budget.observe(None)
                record_llm_call(model_alias, status="success")
                return result
            except Exception as exc:
                if isinstance(exc, BudgetExceeded):
                    raise
                if budget and budget.pending:
                    budget.observe(None)
                record_llm_call(model_alias, status="error")
                if allow_degraded:
                    return None
                raise RuntimeError(
                    f"{group_name}: LiteLLM gateway call failed"
                ) from exc


model_router = ModelRouter()
