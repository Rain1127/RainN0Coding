"""
Intent Agent - 用户意图识别。

在 PM Agent 之前运行，将自然语言需求映射为结构化意图。
当 LLM 不可用时，降级到规则路由，避免整条工作流在 intent 阶段直接失败。
"""

import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agents.agent_logging import log_agent_fail, log_agent_ok, log_agent_start, summarize_request
from config import config
from intent_tree import INTENT_ROOT, format_intent_tree_flat
from llm_factory import create_json_parser
from server.codegen_type_router import route_code_gen_type
from state.code_gen_state import CodeGenState

_cached_custom_tree: str | None = None
_cache_loaded: bool = False


class IntentRecognitionResult(BaseModel):
    primary_intent: str = Field(description="最可能的意图路径，如 '代码生成 / 后端代码生成 / 生成 API'")
    secondary_intents: list[str] = Field(default_factory=list, description="可能的次要意图")
    confidence: float = Field(description="置信度 0.0~1.0", ge=0.0, le=1.0)
    confidence_reason: str = Field(description="置信度判断依据，一到两句话")
    key_entities: list[str] = Field(default_factory=list, description="用户提到的关键对象")
    slots: dict[str, str] = Field(default_factory=dict, description="已提取的槽位")
    missing_slots: list[str] = Field(default_factory=list, description="缺失但重要的槽位")
    should_clarify: bool = Field(description="是否需要澄清")
    clarification_questions: list[str] = Field(default_factory=list, description="建议向用户提问的问题")
    retrieval_hint: str = Field(default="", description="给 RAG 检索模块的提示")


BASE_TREE_TEXT = format_intent_tree_flat(INTENT_ROOT)

FALLBACK_INTENT_MAP = {
    "vue_project": "代码生成 / 前端代码生成 / 生成 Vue 项目",
    "html": "代码生成 / 前端代码生成 / 生成 HTML 页面",
    "multi_file": "代码生成 / 前端代码生成 / 生成多文件页面",
    "python": "代码生成 / 后端代码生成 / 生成 Python 服务",
    "java": "代码生成 / 后端代码生成 / 生成 Java 服务",
    "go": "代码生成 / 后端代码生成 / 生成 Go 服务",
    "rust": "代码生成 / 后端代码生成 / 生成 Rust 服务",
    "nodejs": "代码生成 / 后端代码生成 / 生成 Node.js 服务",
    "generic": "代码生成 / 通用代码生成 / 生成项目",
}


def _get_custom_tree() -> str | None:
    """从 Java 后端加载管理员自定义意图树。"""
    global _cached_custom_tree, _cache_loaded
    if _cache_loaded:
        return _cached_custom_tree
    _cache_loaded = True
    try:
        response = httpx.get(f"{config.JAVA_BASE_URL}/api/intent-config/tree", timeout=5)
        if response.status_code == 200:
            data = response.json().get("data", {})
            if data.get("customized") and data.get("treeJson"):
                _cached_custom_tree = data["treeJson"]
                return _cached_custom_tree
    except Exception:
        pass
    return None


def _build_intent_prompt() -> str:
    """构建 Intent Agent 的 system prompt。"""
    custom = _get_custom_tree()
    tree_text = custom if custom else BASE_TREE_TEXT
    source = "管理员自定义" if custom else "默认"
    return f"""你是一个用户意图识别专家。你的任务是将用户的自然语言输入分类到以下意图树中（{source}）。

## 意图分类树

{tree_text}

## 识别规则

1. 优先匹配叶子节点，从三级意图开始逐级回退
2. 置信度判断：
   - 0.80~1.00：明确匹配到叶子节点，关键信息充足
   - 0.60~0.79：匹配到二级意图，但三级意图不够明确
   - 0.40~0.59：只匹配到一级意图，细节不足
   - 0.00~0.39：无法可靠判断
3. 根据匹配结果提取用户已经提供的槽位信息
4. should_clarify=true 的条件：
   - 置信度 < 0.60
   - 或多个意图置信度接近
   - 或关键槽位缺失
   - 或用户表达存在指代但无法解析
5. 澄清问题最多 1~2 个，直接对应缺失槽位

## 输出格式
严格输出 JSON，不要额外文本。
"""


INTENT_FIELD_SPEC = """Output ONLY a valid JSON object with these EXACT field names:
{
  "primary_intent": "string (intent path, e.g. '代码生成 / 后端代码生成 / 生成 API')",
  "secondary_intents": ["string"],
  "confidence": 0.0,
  "confidence_reason": "string",
  "key_entities": ["string"],
  "slots": {"key": "value"},
  "missing_slots": ["string"],
  "should_clarify": true,
  "clarification_questions": ["string"],
  "retrieval_hint": "string"
}
Output ONLY the JSON, no markdown, no explanation."""


def recognize_intent(user_request: str, user_id: str | None = None) -> IntentRecognitionResult | None:
    """使用 LLM 识别用户意图。"""
    parser = create_json_parser(
        IntentRecognitionResult,
        INTENT_FIELD_SPEC,
        group="lightweight",
        agent_name="intent_agent",
    )
    messages = [
        SystemMessage(content=_build_intent_prompt()),
        HumanMessage(content=f"用户输入：{user_request}"),
    ]
    return parser(messages, user_id=user_id)


def _fallback_intent(user_request: str, user_id: str | None, reason: str) -> IntentRecognitionResult:
    """当 LLM 不可用时，使用规则路由结果构造一个可继续执行的意图。"""
    code_gen_type = route_code_gen_type(user_request, user_id=user_id)
    primary_intent = FALLBACK_INTENT_MAP.get(code_gen_type, FALLBACK_INTENT_MAP["generic"])
    return IntentRecognitionResult(
        primary_intent=primary_intent,
        secondary_intents=[],
        confidence=0.55,
        confidence_reason=f"LLM unavailable, fallback to rule router: {reason}",
        key_entities=[],
        slots={"code_gen_type": code_gen_type},
        missing_slots=[],
        should_clarify=False,
        clarification_questions=[],
        retrieval_hint=code_gen_type,
    )


def intent_agent(state: CodeGenState) -> CodeGenState:
    """LangGraph 节点：识别意图并写回状态。"""
    user_request = state.get("user_request", "")
    log_agent_start("Intent Agent", f"正在识别用户意图，request={summarize_request(user_request)}")
    if not user_request:
        state["error"] = "用户输入为空，无法识别意图"
        state["phase"] = "error"
        log_agent_fail("Intent Agent", "缺少 user_request，无法识别意图")
        return state

    used_fallback = False
    try:
        result = recognize_intent(user_request, user_id=state.get("user_id"))
    except Exception as exc:
        result = _fallback_intent(user_request, state.get("user_id"), str(exc))
        used_fallback = True

    if result is None:
        result = _fallback_intent(
            user_request,
            state.get("user_id"),
            "all model candidates unavailable",
        )
        used_fallback = True

    state["intent"] = result.model_dump()
    state["error"] = None

    if result.confidence < 0.40:
        state["phase"] = "clarify"
        state["clarification"] = {
            "questions": result.clarification_questions,
            "missing_slots": result.missing_slots,
        }
    else:
        state["phase"] = "intent_done"
        if result.confidence < 0.60:
            state["clarification"] = {
                "note": f"LLM 不可用或中等置信度({result.confidence:.0%})，按假设继续执行",
                "assumed_intent": result.primary_intent,
            }

    log_agent_ok(
        "Intent Agent",
        f"意图识别完成，intent={result.primary_intent} confidence={result.confidence:.0%} "
        f"clarify={'yes' if result.should_clarify else 'no'} source={'fallback' if used_fallback else 'llm'}",
    )
    return state
