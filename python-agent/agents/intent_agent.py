"""
Intent Agent —— 用户意图识别

在 PM Agent 之前运行。将用户自然语言输入映射到三层意图分类树，
输出结构化识别结果（意图路径 + 置信度 + 槽位 + 澄清标记）。

低置信度 → 暂停并返回澄清问题
高置信度 → 继续 PM Agent，意图信息传递到后续 RAG 检索
"""
import httpx
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from llm_factory import create_json_parser
from state.code_gen_state import CodeGenState
from intent_tree import format_intent_tree_flat, INTENT_ROOT
from config import config

# 缓存 admin 自定义意图树，避免每次都请求 Java API
_cached_custom_tree: str | None = None
_cache_loaded: bool = False


# ============ Pydantic 输出模型 ============

class IntentRecognitionResult(BaseModel):
    primary_intent: str = Field(description="最可能的意图路径，如 '代码生成 / 后端代码生成 / 生成 API'")
    secondary_intents: list[str] = Field(default_factory=list, description="可能的次要意图")
    confidence: float = Field(description="置信度 0.0~1.0", ge=0.0, le=1.0)
    confidence_reason: str = Field(description="置信度判断依据（一到两句话）")
    key_entities: list[str] = Field(default_factory=list, description="用户提到的关键对象：文件、函数、接口名等")
    slots: dict[str, str] = Field(default_factory=dict, description="已提取的槽位键值对")
    missing_slots: list[str] = Field(default_factory=list, description="缺失但重要的槽位")
    should_clarify: bool = Field(description="是否需要向用户澄清")
    clarification_questions: list[str] = Field(default_factory=list, description="推荐向用户提出的问题（1~2个）")
    retrieval_hint: str = Field(default="", description="给 RAG 检索模块的提示")


BASE_TREE_TEXT = format_intent_tree_flat(INTENT_ROOT)


def _get_custom_tree() -> str | None:
    """从 Java 后端加载管理员自定义意图树。"""
    global _cached_custom_tree, _cache_loaded
    if _cache_loaded:
        return _cached_custom_tree
    _cache_loaded = True
    try:
        java_base = f"http://localhost:{config.SERVER_PORT}"
        r = httpx.get(f"{java_base}/api/intent-config/tree", timeout=5)
        if r.status_code == 200:
            data = r.json().get("data", {})
            if data.get("customized") and data.get("treeJson"):
                _cached_custom_tree = data["treeJson"]
                return _cached_custom_tree
    except Exception:
        pass
    return None


def _build_intent_prompt() -> str:
    """构建意图识别 System Prompt，优先使用管理员自定义树。"""
    custom = _get_custom_tree()
    tree_text = custom if custom else BASE_TREE_TEXT
    source = "管理员自定义" if custom else "默认"
    return f"""你是一个用户意图识别专家。你的任务是将用户的自然语言输入分类到以下意图树中（{source}）。

## 意图分类树

{tree_text}

## 识别规则

1. **优先匹配叶子节点**：从三级意图开始匹配，逐级回退
2. **置信度判断**：
   - 0.80~1.00：明确匹配到叶子节点，关键词充足
   - 0.60~0.79：匹配到二级意图，但三级不够明确
   - 0.40~0.59：只匹配到一级意图，细节不足
   - 0.00~0.39：无法可靠判断
3. **槽位提取**：根据匹配到的意图节点，提取用户已提供的信息
4. **澄清判断**（should_clarify=true 的情况）：
   - 置信度 < 0.60
   - 或多个意图置信度接近
   - 或关键槽位缺失
   - 或用户表达中存在指代但无法解析
5. **澄清问题原则**：最多1~2个问题，直接对应缺失槽位，提供选项降低用户回答成本

## 输出格式
严格输出 JSON，不要任何额外文本。
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


# ============ Agent 主函数 ============

def recognize_intent(user_request: str, user_id: str = None) -> IntentRecognitionResult:
    """识别用户意图（独立调用，不依赖 State）。"""
    parser = create_json_parser(IntentRecognitionResult, INTENT_FIELD_SPEC, group="lightweight", agent_name="intent_agent")
    messages = [
        SystemMessage(content=_build_intent_prompt()),
        HumanMessage(content=f"用户输入：{user_request}"),
    ]
    return parser(messages, user_id=user_id)


def intent_agent(state: CodeGenState) -> CodeGenState:
    """
    意图识别 Agent —— LangGraph 节点。

    读取 state["user_request"]，输出结构化意图识别结果。
    高置信度 → phase="intent_done"，继续 PM
    中置信度 → phase="intent_done" 但标注假设
    低置信度 → phase="clarify"，暂停等待用户澄清
    """
    user_request = state.get("user_request", "")
    if not user_request:
        state["error"] = "用户输入为空，无法识别意图"
        state["phase"] = "error"
        return state

    try:
        result = recognize_intent(user_request, user_id=state.get("user_id"))
    except Exception as e:
        state["error"] = f"意图识别 LLM 调用失败: {e}"
        state["phase"] = "error"
        return state

    if result is None:
        state["error"] = "意图识别失败：所有模型候选不可用（全部已熔断或调用失败）"
        state["phase"] = "error"
        return state

    # 写入 State
    state["intent"] = result.model_dump()

    if result.confidence < 0.40:
        # 低置信度 —— 需要澄清
        state["phase"] = "clarify"
        state["clarification"] = {
            "questions": result.clarification_questions,
            "missing_slots": result.missing_slots,
        }
    else:
        # 中/高置信度 —— 继续
        state["phase"] = "intent_done"
        if result.confidence < 0.60:
            state["clarification"] = {
                "note": f"中置信度({result.confidence:.0%})，带假设执行",
                "assumed_intent": result.primary_intent,
            }

    print(f"[Intent Agent] {result.primary_intent} (confidence={result.confidence:.0%}, clarify={result.should_clarify})")
    return state
