"""
LangGraph 工作流 —— 将 8 个 Agent 组装为状态图

拓扑:
  START → ModeDetector → Intent
                            │
              ┌─────────────┤
              │ modify      │ new/rebuild
              ▼             ▼
           Coder          PM → Architect → Fork(Coder + ImageCollector)
              │                                │
              └────────────────────────────────┘
                              │
                          Reviewer
                              │
              passed ──► Builder → END
              failed ──► Coder (带上 issue 列表重试)
              retry>=3 ──► HumanIntervention → END
"""
import os
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from state.code_gen_state import CodeGenState
from config import config

from agents.supervisor_agent import supervisor_decision
from agents.mode_detector import mode_detector
from agents.intent_agent import intent_agent
from agents.pm_agent import pm_agent
from agents.architect_agent import architect_agent
from agents.coder_agent import coder_agent
from agents.reviewer_agent import reviewer_agent
from agents.image_collector_agent import image_collector_agent
from agents.builder_agent import builder_agent
from workflow.autogen_discussion import autogen_discussion_node


def _route_after_intent(state: CodeGenState) -> str:
    """Intent Agent 之后的路由：modify 模式跳过 PM + Architect，直接到 Coder。"""
    if state.get("phase") != "intent_done":
        return "end"
    if state.get("mode") in ("modify",):
        return "coder_agent"
    return "pm_agent"


def fork_coder_and_images(state: CodeGenState) -> CodeGenState:
    """Fork 节点：先 Image Collector（零 LLM，快），再 Coder（LLM 调用）"""
    state = image_collector_agent(state)
    state = coder_agent(state)
    return state


def end_node(state: CodeGenState) -> CodeGenState:
    """终止节点：汇总最终结果"""
    review = state.get("review") or {}
    build = state.get("build_result") or {}
    indexing = state.get("indexing_result") or {}
    quality_gate = state.get("quality_gate_result") or {}
    state["final_result"] = {
        "status": "completed",
        "phase": state.get("phase"),
        "code_files_count": len(state.get("code_files", [])),
        "images_count": len(state.get("images", [])),
        "review_score": review.get("score"),
        "review_passed": review.get("passed"),
        "build_success": build.get("success"),
        "indexing_success": indexing.get("success"),
        "indexing_message": indexing.get("message"),
        # P0 质量门禁
        "quality_gate_passed": quality_gate.get("passed"),
        "quality_gate_reason": quality_gate.get("reason"),
        "syntax_check_passed": quality_gate.get("syntax_check_passed"),
    }
    state["phase"] = "completed"
    return state


def create_code_gen_workflow() -> StateGraph:
    """构建 LangGraph 状态图"""
    wf = StateGraph(CodeGenState)

    # ===== 注册节点 =====
    wf.add_node("mode_detector", mode_detector)
    wf.add_node("intent_agent", intent_agent)
    wf.add_node("pm_agent", pm_agent)
    wf.add_node("architect_agent", architect_agent)
    wf.add_node("fork_coder_and_images", fork_coder_and_images)
    wf.add_node("coder_agent", coder_agent)           # 重试时单独调用
    wf.add_node("reviewer_agent", reviewer_agent)
    wf.add_node("autogen_discussion", autogen_discussion_node)  # AutoGen 三方讨论
    wf.add_node("builder_agent", builder_agent)
    wf.add_node("human_intervention", end_node)
    wf.add_node("end", end_node)

    # ===== 固定边 =====
    wf.set_entry_point("mode_detector")
    wf.add_edge("mode_detector", "intent_agent")
    # Intent → PM (new/rebuild) 或 Coder (modify 跳过 PM+Architect) 或 END (clarify/error)
    wf.add_conditional_edges(
        "intent_agent",
        _route_after_intent,
        {"pm_agent": "pm_agent", "coder_agent": "coder_agent", "end": "end"},
    )
    wf.add_edge("pm_agent", "architect_agent")
    wf.add_edge("architect_agent", "fork_coder_and_images")
    wf.add_edge("fork_coder_and_images", "reviewer_agent")

    # ===== 条件边：Reviewer → Builder / AutoGen讨论 / Coder(重试) / HumanIntervention =====
    wf.add_conditional_edges(
        "reviewer_agent",
        supervisor_decision,
        {
            "builder_agent": "builder_agent",
            "autogen_discussion": "autogen_discussion",
            "coder_agent": "coder_agent",
            "human_intervention": "human_intervention",
            "end": "end",
        }
    )

    # AutoGen 讨论后进入 Coder 重写
    wf.add_edge("autogen_discussion", "coder_agent")

    # 重试回路：Coder → Reviewer
    wf.add_edge("coder_agent", "reviewer_agent")

    # 终止
    wf.add_edge("builder_agent", "end")
    wf.add_edge("end", END)
    wf.add_edge("human_intervention", END)

    return wf


def _build_initial_state(user_request: str, user_id: str, app_id: str,
                         code_gen_type: str, user_role: str = "user",
                         trace_id: str = "") -> CodeGenState:
    """构建工作流初始 State。"""
    project_dir = os.path.join(config.CODE_OUTPUT_DIR, f"{code_gen_type}_{app_id}")
    return {
        "user_request": user_request,
        "user_id": user_id,
        "app_id": app_id,
        "code_gen_type": code_gen_type,
        "user_role": user_role,
        "trace_id": trace_id,
        "project_dir": project_dir,
        "mode": "new",
        "has_existing_code": False,
        "intent": None,
        "clarification": None,
        "existing_prd": None,
        "existing_architecture": None,
        "existing_code_files": [],
        "prd": None,
        "architecture": None,
        "code_files": [],
        "review": None,
        "retry_count": 0,
        "max_retries": config.MAX_RETRIES,
        "images": [],
        "build_result": None,
        "indexing_result": None,
        "phase": "init",
        "messages": [],
        "final_result": None,
        "error": None,
    }


def run_workflow(user_request: str, user_id: str = "demo", app_id: str = "demo",
                 code_gen_type: str = "vue_project", user_role: str = "user",
                 trace_id: str = "") -> CodeGenState:
    """执行完整工作流（同步）"""
    initial: CodeGenState = _build_initial_state(user_request, user_id, app_id, code_gen_type, user_role, trace_id)
    workflow = create_code_gen_workflow()
    compiled = workflow.compile(checkpointer=MemorySaver())
    config_dict = {"configurable": {"thread_id": f"{user_id}_{app_id}"}}
    return compiled.invoke(initial, config_dict)


async def run_workflow_async(user_request: str, user_id: str = "demo",
                              app_id: str = "demo",
                              code_gen_type: str = "vue_project",
                              user_role: str = "user",
                              trace_id: str = "") -> CodeGenState:
    """执行完整工作流（异步流式）。

    使用 LangGraph astream() —— 每个 Agent 节点完成后 yield 一次 state 快照。
    调用方通过 async for 消费中间状态，实现真正的 SSE 流式输出。

    Yields:
        CodeGenState 快照（每个 superstep 一次）
    """
    initial: CodeGenState = _build_initial_state(user_request, user_id, app_id, code_gen_type, user_role, trace_id)
    workflow = create_code_gen_workflow()
    compiled = workflow.compile(checkpointer=MemorySaver())
    config_dict = {"configurable": {"thread_id": f"{user_id}_{app_id}"}}

    final_state = initial
    async for chunk in compiled.astream(initial, config_dict, stream_mode="values"):
        final_state = chunk
        yield final_state
