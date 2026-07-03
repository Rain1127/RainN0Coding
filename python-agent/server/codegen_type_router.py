"""Code generation type routing owned by the Python agent side."""
import logging

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from config import LANGUAGE_CONFIGS
from llm_factory import create_json_parser

logger = logging.getLogger("server.codegen_type_router")

DEFAULT_CODE_GEN_TYPE = "vue_project"
SUPPORTED_CODE_GEN_TYPES = sorted(LANGUAGE_CONFIGS.keys())


class CodeGenTypeRouteResult(BaseModel):
    code_gen_type: str = Field(description="One supported code generation type")


ROUTE_FIELD_SPEC = """Output ONLY a valid JSON object with this EXACT shape:
{
  "code_gen_type": "one of: vue_project, html, multi_file, python, java, go, rust, nodejs, generic"
}
Output ONLY the JSON, no markdown, no explanation."""


def _build_route_prompt() -> str:
    supported_values = ", ".join(SUPPORTED_CODE_GEN_TYPES)
    return f"""你是代码生成类型路由器。

请根据用户需求，从以下候选类型中选择最合适的一个：
{supported_values}

选择规则：
1. 单页宣传页、简单静态页面优先选 html
2. 多页面原生前端项目优先选 multi_file
3. 现代前端应用、管理后台、需要组件化、路由或状态管理时优先选 vue_project
4. 明确要求 Python / Java / Go / Rust / Node.js 项目时选择对应语言
5. 无法明确判断时返回 vue_project

只返回 JSON，不要解释。"""


_route_parser = create_json_parser(
    CodeGenTypeRouteResult,
    ROUTE_FIELD_SPEC,
    group="structured",
    agent_name="codegen_type_router",
)


def normalize_code_gen_type(raw_value: str | None) -> str | None:
    if not raw_value:
        return None
    normalized = raw_value.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in SUPPORTED_CODE_GEN_TYPES:
        return normalized
    return None


def route_code_gen_type(user_prompt: str, user_id: str | None = None) -> str:
    messages = [
        SystemMessage(content=_build_route_prompt()),
        HumanMessage(content=f"用户需求：{user_prompt}"),
    ]
    try:
        result = _route_parser(messages, user_id=user_id)
        if result is None:
            return DEFAULT_CODE_GEN_TYPE
        normalized = normalize_code_gen_type(result.code_gen_type)
        return normalized or DEFAULT_CODE_GEN_TYPE
    except Exception as e:
        logger.warning("codegen type routing failed, fallback to %s: %s", DEFAULT_CODE_GEN_TYPE, e)
        return DEFAULT_CODE_GEN_TYPE
