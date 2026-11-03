"""
PM Agent —— 产品经理

输入：用户一句话需求（"做一个电商首页"）
输出：结构化 PRD（Pydantic 模型）
行为：调用 LLM 1 次，手动 JSON 解析 + Pydantic validate
"""
import json
import os
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from agents.agent_logging import log_agent_fail, log_agent_ok, log_agent_start, summarize_request
from llm_factory import create_json_parser
from prompt_builder import compose_messages
from state.code_gen_state import CodeGenState
from config import get_lang_config
from workflow.acceptance import ASSERTIONS, AcceptanceStep, AcceptanceFeature, AcceptanceProposal, freeze_contract
from workflow.harness_policy import enabled


# ============ Pydantic 输出模型 ============

class Feature(BaseModel):
    name: str = Field(description="功能名称，如'商品轮播图'")
    description: str = Field(description="功能描述，一句话说明这个功能做什么")
    priority: str = Field(description="优先级：high / medium / low")
    interactions: list[str] = Field(description="用户交互方式列表，如['点击跳转', '左右滑动']")
    source_quote: str = Field(default='', description='逐字引用原始需求，不确定的规则待确认')
    acceptance_steps: list[AcceptanceStep] = Field(default_factory=list)
    unverified_reason: str = ''


class PRD(BaseModel):
    page_name: str = Field(description="页面名称")
    page_type: str = Field(description="landing|dashboard|e-commerce|blog|portfolio|admin|other")
    features: list[Feature] = Field(description="功能清单，至少 5 个")
    target_audience: str = Field(description="目标用户群体")
    color_preference: str = Field(description="色彩偏好建议")
    layout_type: str = Field(description="single-column|two-column|grid|masonry|dashboard-grid")
    data_dependencies: list[str] = Field(description="数据依赖清单")


# ============ Prompt ============

def _build_pm_prompt(code_gen_type: str | None) -> str:
    lc = get_lang_config(code_gen_type)
    is_frontend = lc.get("is_frontend", False)

    if is_frontend:
        return """你是一个资深产品经理。用户会用一句话描述他想要的页面，你的任务是将它转化为结构化的产品需求文档（PRD）。

## 输出规则
1. **功能清单要完整**：覆盖页面的所有核心交互，不要遗漏
2. **不要写任何代码**：只描述功能，不涉及技术实现
3. **每个功能都要标注优先级**：high（核心流程）/ medium（体验增强）/ low（锦上添花）
4. **按页面类型补充必要功能**：
   - 电商：商品展示、搜索/筛选、购物车入口、用户评价、促销区
   - 管理后台：数据表格、搜索栏、操作按钮、分页、批量操作
   - 落地页：Hero区、产品亮点、价格/套餐、CTA按钮、客户案例
   - 博客：文章列表、分类标签、搜索、作者信息、相关推荐
5. **数据依赖写成 API 名形式**（如"商品列表API"而非"商品数据"）
6. **色彩偏好要具体**（如"温暖橙色主调+白色背景"）
"""
    else:
        return f"""你是一个资深产品经理。用户会描述他想要的{lc['label']}后端服务/API/工具，你的任务是将它转化为结构化的需求文档（PRD）。

## 输出规则
1. **功能清单要完整**：覆盖所有核心业务逻辑，不要遗漏
2. **不要写任何代码**：只描述功能，不涉及技术实现
3. **每个功能都要标注优先级**：high（核心流程）/ medium（体验增强）/ low（锦上添花）
4. **按服务类型补充必要功能**：
   - REST API：端点定义、请求/响应格式、错误码、认证方式
   - 数据处理：数据源、处理流程、输出格式、性能要求
   - CLI工具：命令参数、交互流程、输出格式、错误处理
   - 后台服务：定时任务、消息队列、日志监控、配置管理
5. **数据依赖写成具体形式**（如"用户表(MySQL)"而非"用户数据"）
6. **技术约束要明确**：性能指标、可用性要求、安全要求
"""


PRD_FIELD_SPEC = """Output ONLY a valid JSON object with these EXACT field names:
{
  "page_name": "string",
  "page_type": "string (one of: landing, dashboard, e-commerce, blog, portfolio, admin, other)",
  "features": [
    {
      "name": "string",
      "description": "string",
      "priority": "string (one of: high, medium, low)",
      "interactions": ["string", "string"],
      "source_quote": "exact quote from user request",
      "acceptance_steps": [],
      "unverified_reason": ""
    }
  ],
  "target_audience": "string",
  "color_preference": "string",
  "layout_type": "string (one of: single-column, two-column, grid, masonry, dashboard-grid)",
  "data_dependencies": ["string", "string"]
}
Output ONLY the JSON, no markdown, no explanation."""


# ============ Agent 主函数 ============

def pm_agent(state: CodeGenState) -> CodeGenState:
    parser = create_json_parser(PRD, PRD_FIELD_SPEC, group="structured", agent_name="pm_agent")

    user_request = state.get("user_request", "")
    log_agent_start(
        "PM Agent",
        f"正在生成 PRD，code_gen_type={state.get('code_gen_type', 'vue_project')} "
        f"request={summarize_request(user_request)}",
    )

    if not user_request:
        state["error"] = "user_request 为空"
        state["phase"] = "error"
        log_agent_fail("PM Agent", "缺少 user_request，无法生成 PRD")
        return state

    code_gen_type = state.get("code_gen_type", "vue_project")

    system = _build_pm_prompt(code_gen_type)
    if enabled(state, 'acceptance'):
        system += ('\n功能引用必须是用户原文的一段连续文本。针对可观察行为给出 acceptance_steps，'
                   '例如 {"action":"text","selector":"nav","value":"用户指定的精确文本"}。'
                   '可直接执行的验收使用空 unverified_reason。缺失的外部依赖填写具体原因。')
    messages = compose_messages(agent="pm_agent", system=system,
                                request=f"用户需求：{user_request}")

    try:
        prd: PRD = parser(messages, user_id=state.get("user_id"))
    except Exception as e:
        state["error"] = f"PM Agent LLM 调用失败: {e}"
        state["phase"] = "error"
        log_agent_fail("PM Agent", f"生成 PRD 失败，原因={e}")
        return state

    if prd is None:
        state["error"] = "PM Agent 失败：所有模型候选不可用（全部已熔断或调用失败）"
        state["phase"] = "error"
        log_agent_fail("PM Agent", "生成 PRD 失败，可用模型候选为空")
        return state

    state["prd"] = prd.model_dump()
    import hashlib
    for feature in state['prd']['features']:
        feature['id'] = 'F-' + hashlib.sha256((feature['source_quote'] + '\n' + feature['name']).encode()).hexdigest()[:16]
    if enabled(state, 'acceptance') and state.get('mode') != 'modify' and prd.features and all(
        f.source_quote and f.source_quote in user_request and not f.unverified_reason
        and any(step.action in ASSERTIONS for step in f.acceptance_steps) for f in prd.features
    ):
        freeze_contract(state, AcceptanceProposal(features=[AcceptanceFeature(
            name=f.name, source_quote=f.source_quote, steps=f.acceptance_steps,
            unverified_reason=f.unverified_reason) for f in prd.features]))

    # 持久化 PRD 到磁盘，供后续修改模式复用
    _persist_prd(state)

    state["phase"] = "prd_done"

    log_agent_ok(
        "PM Agent",
        f"PRD 已生成，page_name={prd.page_name} feature_count={len(prd.features)} "
        f"high_priority_count={sum(1 for f in prd.features if f.priority == 'high')}",
    )
    return state


def _persist_prd(state: CodeGenState) -> None:
    """将 PRD 持久化到项目目录，供后续修改模式加载复用。"""
    project_dir = state.get("project_dir", "")
    if not project_dir:
        return
    try:
        os.makedirs(project_dir, exist_ok=True)
        prd_path = os.path.join(project_dir, "prd.json")
        with open(prd_path, "w", encoding="utf-8") as f:
            json.dump(state["prd"], f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # 持久化非关键，失败不影响流程
