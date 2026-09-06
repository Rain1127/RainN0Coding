"""统一的 LLM 实例工厂 —— 通过 LiteLLM 使用业务模型组

所有 Agent 通过此模块获取模型调用能力。
"""
import json
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from config import config
from core.model_router import model_router
from request_context import build_litellm_metadata

# 创建 LLM 实例
def create_llm(temperature: float | None = None) -> ChatOpenAI:
    """创建使用 LiteLLM reasoning 别名的兼容客户端。"""
    return ChatOpenAI(
        model=config.LLM_REASONING_MODEL,
        api_key=config.LITELLM_API_KEY,
        base_url=config.LITELLM_BASE_URL,
        temperature=temperature if temperature is not None else config.LLM_TEMPERATURE,
        max_tokens=config.LLM_MAX_TOKENS,
        max_retries=0,
        extra_body={"metadata": build_litellm_metadata()},
    )


def _call_with_parser(messages: list, output_schema: type[BaseModel],
                      field_spec: str, group: str,
                      _client=None, _model=None, _config=None) -> BaseModel:
    """
    内部函数 —— 调用 LLM 并解析 JSON。

    支持两种路径:
      1. _client (ChatOpenAI) 由 Router 传入 → 路由器路径
      2. LangChain ChatOpenAI → 旧兼容路径（_client=None 时触发）

    _config: LangSmith RunnableConfig，透传到 _client.invoke(msgs, config=_config)
    """
    if _client is not None:
        # === 路由器路径：用 LangChain ChatOpenAI client ===
        msgs = list(messages)
        last_msg = msgs[-1]
        msgs[-1] = last_msg.__class__(
            content=last_msg.content + "\n\n" + field_spec
        )
        response = _client.invoke(msgs, config=_config)
        content = response.content or ""
    else:
        # === 旧兼容路径：LangChain ChatOpenAI ===
        llm = create_llm(temperature=config.LLM_TEMPERATURE_STRUCTURED)
        msgs = list(messages)
        last_msg = msgs[-1]
        msgs[-1] = last_msg.__class__(
            content=last_msg.content + "\n\n" + field_spec
        )
        response = llm.invoke(msgs)
        content = response.content

    content = _strip_code_fences(content)
    try:
        obj = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"LLM 返回了非法 JSON。原始内容前 500 字符:\n{content[:500]}"
        ) from e
    return output_schema.model_validate(obj)


def create_json_parser(output_schema: type[BaseModel], field_spec: str,
                       group: str = "structured", agent_name: str = None):
    """
    创建 JSON 解析器，由 LiteLLM 处理模型选择和故障转移。

    用法:
        parser = create_json_parser(PRD, PRD_FIELD_SPEC, group="structured",
                                    agent_name="pm_agent")
        result = parser(messages, user_id="user_123")  # user_id 可选

    Args:
        output_schema: Pydantic 模型类
        field_spec:    字段规格文本（追加到 prompt 末尾）
        group:         模型组: "reasoning" | "structured" | "lightweight"
        agent_name:    Agent 名称，用于 LangSmith trace tag（如 "pm_agent"）
    """
    def invoke(messages: list, user_id: str = None):
        # 构建 LangSmith trace metadata
        langsmith_extra = {
            "run_name": agent_name or group,
            "metadata": {},
        }
        if agent_name:
            langsmith_extra["tags"] = [agent_name, group]
        if user_id:
            langsmith_extra["metadata"]["user_id"] = user_id

        return model_router.route(
            group_name=group,
            messages=messages,
            parser=lambda msgs, **kw: _call_with_parser(
                msgs, output_schema, field_spec, group, **kw
            ),
            allow_degraded=True,
            langsmith_extra=langsmith_extra,
        )
    return invoke


def create_reasoning_llm() -> ChatOpenAI:
    """创建使用 LiteLLM reasoning 别名的推理客户端。"""
    return ChatOpenAI(
        model=config.LLM_REASONING_MODEL,
        api_key=config.LITELLM_API_KEY,
        base_url=config.LITELLM_BASE_URL,
        temperature=0.0,
        max_tokens=config.LLM_MAX_TOKENS,
        max_retries=0,
        extra_body={"metadata": build_litellm_metadata()},
    )


def create_llm_router(group: str = "lightweight", agent_name: str = None):
    """
    创建带路由的纯文本 LLM 调用（供 Intent Agent、Summarizer 等使用）。
    返回一个 callable: invoke(messages, user_id=None) → str | None

    Args:
        group:      模型组: "reasoning" | "structured" | "lightweight"
        agent_name: Agent 名称，用于 LangSmith trace tag
    """
    def invoke(messages: list, user_id: str = None) -> str | None:
        langsmith_extra = {
            "run_name": agent_name or group,
            "metadata": {},
        }
        if agent_name:
            langsmith_extra["tags"] = [agent_name, group]
        if user_id:
            langsmith_extra["metadata"]["user_id"] = user_id

        return model_router.route(
            group_name=group,
            messages=messages,
            parser=None,
            allow_degraded=True,
            langsmith_extra=langsmith_extra,
        )
    return invoke


class _ToolEnabledRouter:
    """LangChain-like adapter that keeps tool calls on the shared fallback router."""

    def __init__(self, tools: list, group: str):
        self.tools = tools
        self.group = group

    def invoke(self, messages: list, config: dict | None = None):
        def invoke_with_tools(msgs, _client=None, _config=None):
            if _client is None:
                raise RuntimeError("tool-enabled routing requires a model client")
            return _client.bind_tools(self.tools).invoke(msgs, config=_config)

        return model_router.route(
            group_name=self.group,
            messages=messages,
            parser=invoke_with_tools,
            allow_degraded=False,
            langsmith_extra=config,
        )


def create_tool_enabled_llm(tools: list, group: str = "reasoning"):
    """
    创建带工具绑定的 LLM（供 Coder Agent 的 ReAct 循环使用）。

    每轮调用都经过 ModelRouter；重试、冷却和故障转移由 LiteLLM 负责。
    reasoning_content 由 coder_agent 在消息回传前清除。

    Args:
        tools: LangChain @tool 装饰器创建的 Tool 对象列表
        group: 模型组: "reasoning" | "structured" | "lightweight"

    Returns:
        兼容 ``invoke(messages, config=...)`` 的路由适配器
    """
    return _ToolEnabledRouter(tools, group)


def _strip_code_fences(content: str) -> str:
    """去除 LLM JSON 输出中常见的 markdown 代码块包裹"""
    text = content.strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 2:
            inner = parts[1]
            if inner.startswith("json"):
                inner = inner[4:]
            text = inner.strip()
    return text
