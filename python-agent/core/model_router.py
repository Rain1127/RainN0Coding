"""Thin business-model router backed by the LiteLLM gateway."""

from langchain_openai import ChatOpenAI

from config import config
from core.model_registry import get_model_alias
from monitoring import record_llm_call
from request_context import get_request_metadata
from tracing import start_span


class ModelRouter:
    """Map a business model group to one LiteLLM request."""

    def route(
        self,
        group_name: str,
        messages: list,
        parser=None,
        allow_degraded: bool = True,
        langsmith_extra: dict | None = None,
    ):
        model_alias = get_model_alias(group_name)
        runnable_config = dict(langsmith_extra or {})
        gateway_metadata = get_request_metadata()
        gateway_metadata.update(runnable_config.get("metadata", {}))

        with start_span(
            "llm.gateway",
            {"llm.group": group_name, "llm.model": model_alias},
        ):
            try:
                client = ChatOpenAI(
                    model=model_alias,
                    api_key=config.LITELLM_API_KEY,
                    base_url=config.LITELLM_BASE_URL,
                    timeout=config.LLM_TIMEOUT,
                    max_retries=0,
                    temperature=0.0,
                    extra_body={"metadata": gateway_metadata},
                )
                if parser:
                    result = parser(
                        messages,
                        _client=client,
                        _config=runnable_config,
                    )
                else:
                    response = client.invoke(messages, config=runnable_config)
                    result = response.content or ""
                    if not result:
                        raise ValueError(f"{model_alias}: empty gateway response")
                record_llm_call(model_alias, status="success")
                return result
            except Exception as exc:
                record_llm_call(model_alias, status="error")
                if allow_degraded:
                    return None
                raise RuntimeError(
                    f"{group_name}: LiteLLM gateway call failed"
                ) from exc


model_router = ModelRouter()
