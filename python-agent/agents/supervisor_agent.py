"""
Supervisor Agent —— 编排者

职责：
- 读取 State 中的 phase 决定下一阶段
- 处理审查结果，决定通过 / 重试 / 人工介入
- 零 LLM 调用 —— 纯规则路由函数

LangGraph 用法：
    workflow.add_conditional_edges(
        "reviewer_agent",
        supervisor_decision,
        {
            "coder_agent": "coder_agent",
            "builder_agent": "builder_agent",
            "human_intervention": "human_intervention",
        }
    )
"""
from state.code_gen_state import CodeGenState
from config import config


def supervisor_decision(state: CodeGenState) -> str:
    """根据当前 phase 返回下一个节点名称。

    这是 LangGraph 条件边的路由函数。
    返回的字符串必须是 workflow.add_conditional_edges 中 mapping 的 key 之一。
    """
    phase = state.get("phase", "init")

    # phase → next_node 映射表
    routing_table: dict[str, str | callable] = {
        "init":        "pm_agent",
        "intent_done": "pm_agent",
        "clarify":     "end",
        "prd_done":    "architect_agent",
        "arch_done":   "fork_coder_and_images",
        "code_done":   "reviewer_agent",
        "review_done": _handle_review_result,   # 需要判断 passed/failed
        "build_done":  "end",
        "error":       "end",
        "completed":   "end",
    }

    handler = routing_table.get(phase, "end")

    if callable(handler):
        return handler(state)

    return handler


def _handle_review_result(state: CodeGenState) -> str:
    """处理审查结果 —— 通过 → 构建，架构级问题 → AutoGen 三方讨论，代码级问题 → 重写，超限 → 人工介入"""
    review = state.get("review") or {}
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", config.MAX_RETRIES)

    if review.get("passed"):
        return "builder_agent"

    if retry_count < max_retries:
        # 架构级问题走 AutoGen 三方讨论，代码级问题直接重试
        if _has_architectural_issues(review):
            return "autogen_discussion"
        return "coder_agent"

    return "human_intervention"


def _has_architectural_issues(review: dict) -> bool:
    """检测审查问题是否涉及架构层面 —— 需要 Architect 参与讨论。

    判断依据（满足任一即视为架构级问题）：
    1. issue.category 为 "architecture"
    2. suggestion 中提到组件树/数据流/文件清单/技术栈变更
    3. severity 为 "critical" 且涉及多个文件
    """
    issues = review.get("issues", [])
    if not issues:
        return False

    arch_keywords = [
        "component_tree", "data_flow", "file_list", "tech_stack",
        "组件树", "数据流", "文件清单", "技术栈", "架构",
        "拆分", "合并组件", "重构架构", "路由设计", "状态管理方案",
    ]

    for issue in issues:
        category = issue.get("category", "")
        if category == "architecture":
            return True

        desc = issue.get("description", "")
        suggestion = issue.get("suggestion", "")
        combined = (desc + " " + suggestion).lower()

        for kw in arch_keywords:
            if kw.lower() in combined:
                return True

    return False


def get_next_phase_for_current(phase: str) -> str | None:
    """工具函数：查询某个 phase 的下一个节点（不依赖完整 State）。

    用于调试和文档：一眼看出工作流的阶段流转。
    """
    mapping = {
        "init":        "prd_done (→ pm_agent)",
        "prd_done":    "arch_done (→ architect_agent)",
        "arch_done":   "code_done (→ fork_coder_and_images)",
        "code_done":   "review_done (→ reviewer_agent)",
        "review_done": "build_done 或 coder_agent(重试) 或 human_intervention(超限)",
        "build_done":  "completed",
    }
    return mapping.get(phase)
