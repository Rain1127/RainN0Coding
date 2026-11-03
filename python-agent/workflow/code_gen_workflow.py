"""
LangGraph 工作流 - 将 8 个 Agent 组装为状态图

拓扑:
  START -> ModeDetector -> Intent
                            |
              +-------------+-------------+
              | modify                    | new/rebuild
              v                           v
           Coder                    PM -> Architect -> Fork(Coder + ImageCollector)
              |                                               |
              +-----------------------------------------------+
                                      |
                                   Reviewer
                                      |
              passed ---------------> Builder -> END
              failed ---------------> Coder (带上 issue 列表重试)
              retry>=3 -------------> HumanIntervention -> END
"""
import asyncio
import os
from contextlib import aclosing

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from agents.architect_agent import architect_agent
from agents.builder_agent import builder_agent
from agents.coder_agent import coder_agent
from agents.image_collector_agent import image_collector_agent
from agents.intent_agent import intent_agent
from agents.mode_detector import mode_detector
from agents.pm_agent import pm_agent
from agents.reviewer_agent import reviewer_agent
from agents.supervisor_agent import supervisor_decision
from config import config
from state.code_gen_state import CodeGenState
from workflow.autogen_discussion import autogen_discussion_node
from workflow.resilience import ensure_availability_defaults, finalize_state, guarded_phase_call
from workflow.repair import after_validation, record_repair_diff
from workflow.runtime_validation import runtime_validation
from agents.change_plan import change_plan, simple_target, diff_changes


def _route_after_intent(state: CodeGenState) -> str:
    """Intent Agent 之后的路由：modify 模式跳过 PM + Architect，直接到 Coder。"""
    if state.get("phase") != "intent_done":
        return "end"
    if state.get("mode") in ("modify",):
        return "change_plan"
    return "pm_agent"


async def intent_agent_node(state: CodeGenState) -> CodeGenState:
    return await guarded_phase_call("intent", state, intent_agent)


async def pm_agent_node(state: CodeGenState) -> CodeGenState:
    return await guarded_phase_call("pm", state, pm_agent)


async def architect_agent_node(state: CodeGenState) -> CodeGenState:
    return await guarded_phase_call("architect", state, architect_agent)


async def fork_coder_and_images(state: CodeGenState) -> CodeGenState:
    """Fork 节点：先 Image Collector（零 LLM，快），再 Coder（LLM 调用）。"""
    state = await guarded_phase_call("image_collector", state, image_collector_agent)
    state = await guarded_phase_call("coder", state, coder_agent)
    state = record_repair_diff(state)
    if state.get("mode") == "modify" and not state.get("error"):
        state = diff_changes(state)
    return state


async def builder_agent_node(state: CodeGenState) -> CodeGenState:
    state = await guarded_phase_call("builder", state, builder_agent)
    state["validation_route"] = after_validation(state)
    return state


async def coder_agent_node(state: CodeGenState) -> CodeGenState:
    state = await guarded_phase_call("coder", state, coder_agent)
    state = record_repair_diff(state)
    if state.get("mode") == "modify" and not state.get("error"):
        state = diff_changes(state)
    return state


async def change_plan_node(state: CodeGenState) -> CodeGenState:
    return await guarded_phase_call("architect", state, change_plan)


async def reviewer_agent_node(state: CodeGenState) -> CodeGenState:
    return await guarded_phase_call("reviewer", state, reviewer_agent)


async def runtime_validation_node(state: CodeGenState) -> CodeGenState:
    return await guarded_phase_call("builder", state, runtime_validation)


async def discussion_node(state: CodeGenState) -> CodeGenState:
    return await guarded_phase_call("architect", state, autogen_discussion_node)


def end_node(state: CodeGenState) -> CodeGenState:
    """终止节点：汇总最终结果。"""
    state = ensure_availability_defaults(state)
    state = finalize_state(state)
    if state.get("final_status") in ("success", "degraded_success") and state.get("build_result"):
        try:
            from workflow.artifacts import publish
            if state.get("artifact_publish_owner") == "gateway":
                state["artifact_status"] = "validated_candidate"
                with open(os.path.join(state["project_dir"], ".generation-run-id"), "w", encoding="utf-8") as marker:
                    marker.write(state["artifact_run_id"])
            else:
                state = publish(state)
            from workflow.validation_feedback import finalize_evidence
            state = finalize_evidence(state)
            state = finalize_state(state)
        except Exception as exc:
            state["error"] = f"Artifact publication failed: {exc}"
            state = finalize_state(state)
    elif state.get("artifact_run_id"):
        from workflow.validation_feedback import finalize_evidence
        state = finalize_evidence(state)
    return state


def create_code_gen_workflow(session=None) -> StateGraph:
    """构建 LangGraph 状态图。"""
    wf = StateGraph(CodeGenState)

    # ===== 注册节点 =====
    wf.add_node("mode_detector", mode_detector)
    wf.add_node("change_plan", change_plan_node)
    wf.add_node("intent_agent", intent_agent_node)
    wf.add_node("pm_agent", pm_agent_node)
    wf.add_node("architect_agent", architect_agent_node)
    wf.add_node("fork_coder_and_images", fork_coder_and_images)
    wf.add_node("coder_agent", coder_agent_node)
    wf.add_node("reviewer_agent", reviewer_agent_node)
    wf.add_node("autogen_discussion", discussion_node)
    wf.add_node("builder_agent", builder_agent_node)
    wf.add_node("runtime_validation", runtime_validation_node)
    wf.add_node("human_intervention", end_node)
    wf.add_node("end", end_node)

    # ===== 固定边 =====
    # Gates have no business side effects: resuming one cannot repeat a model call.
    def entry(name):
        return f"pause_before_{name}" if session else name

    if session:
        for name in list(wf.nodes):
            if name not in ("end", "human_intervention"):
                wf.add_node(entry(name), session.pause_gate)
                wf.add_edge(entry(name), name)

    wf.set_entry_point(entry("mode_detector"))
    wf.add_conditional_edges("mode_detector", lambda state: "change_plan" if simple_target(state) else "intent_agent", {
        "change_plan": entry("change_plan"), "intent_agent": entry("intent_agent"),
    })
    wf.add_conditional_edges("change_plan", lambda state: "pm_agent" if state.get("task_complexity") == "cross_module" else "coder_agent", {
        "pm_agent": entry("pm_agent"), "coder_agent": entry("coder_agent"),
    })
    # Intent -> PM (new/rebuild) 或 Coder (modify 跳过 PM+Architect) 或 END (clarify/error)
    wf.add_conditional_edges(
        "intent_agent",
        _route_after_intent,
        {"pm_agent": entry("pm_agent"), "change_plan": entry("change_plan"), "end": "end"},
    )
    wf.add_edge("pm_agent", entry("architect_agent"))
    wf.add_edge("architect_agent", entry("fork_coder_and_images"))
    wf.add_edge("fork_coder_and_images", entry("reviewer_agent"))

    # ===== 条件边：Reviewer -> Builder / AutoGen讨论 / Coder(重试) / HumanIntervention =====
    wf.add_conditional_edges(
        "reviewer_agent",
        supervisor_decision,
        {
            "builder_agent": entry("builder_agent"),
            "autogen_discussion": entry("autogen_discussion"),
            "coder_agent": entry("coder_agent"),
            "human_intervention": "human_intervention",
            "end": "end",
        },
    )

    # AutoGen 讨论后进入 Coder 重写
    wf.add_edge("autogen_discussion", entry("coder_agent"))

    # 重试回路：Coder -> Reviewer
    wf.add_edge("coder_agent", entry("reviewer_agent"))

    # 终止
    wf.add_conditional_edges("builder_agent", lambda state: state.get("validation_route", "end"), {
        "coder_agent": entry("coder_agent"), "runtime_validation": entry("runtime_validation"), "end": "end",
    })
    wf.add_conditional_edges("runtime_validation", lambda state: state.get("validation_route", "end"), {
        "coder_agent": entry("coder_agent"), "end": "end",
    })
    wf.add_edge("end", END)
    wf.add_edge("human_intervention", END)

    return wf


def _build_initial_state(
    user_request: str,
    user_id: str,
    app_id: str,
    code_gen_type: str,
    user_role: str = "user",
    trace_id: str = "",
) -> CodeGenState:
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
        "degraded": False,
        "degraded_reasons": [],
        "failed_phase": None,
        "last_good_phase": None,
        "partial_code_available": False,
        "final_status": None,
        "recovery_hint": None,
        "phase_failures": [],
    }


def run_workflow(
    user_request: str,
    user_id: str = "demo",
    app_id: str = "demo",
    code_gen_type: str = "vue_project",
    user_role: str = "user",
    trace_id: str = "",
) -> CodeGenState:
    """执行完整工作流（同步）。"""
    initial: CodeGenState = _build_initial_state(user_request, user_id, app_id, code_gen_type, user_role, trace_id)
    workflow = create_code_gen_workflow()
    compiled = workflow.compile(checkpointer=MemorySaver())
    config_dict = {"configurable": {"thread_id": f"{user_id}_{app_id}"}}
    return asyncio.run(compiled.ainvoke(initial, config_dict))


async def run_workflow_async(
    user_request: str,
    user_id: str = "demo",
    app_id: str = "demo",
    code_gen_type: str = "vue_project",
    user_role: str = "user",
    trace_id: str = "",
    session=None,
) -> CodeGenState:
    """执行完整工作流（异步流式）。"""
    initial: CodeGenState = _build_initial_state(user_request, user_id, app_id, code_gen_type, user_role, trace_id)
    if session is not None:
        initial["artifact_publish_owner"] = "gateway"
        async with aclosing(session.states(create_code_gen_workflow(session), initial)) as states:
            async for state in states:
                yield state
        return
    workflow = create_code_gen_workflow()
    compiled = workflow.compile(checkpointer=MemorySaver())
    config_dict = {"configurable": {"thread_id": f"{user_id}_{app_id}"}}

    final_state = initial
    async for chunk in compiled.astream(initial, config_dict, stream_mode="values"):
        final_state = chunk
        yield final_state
