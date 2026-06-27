"""Agent 间共享的状态对象 —— 所有 Agent 读写同一个 State

LangGraph 原生支持 TypedDict + Annotated reducer。
当 Agent 返回部分字段时，LangGraph 自动 merge 进 State。
"""
from __future__ import annotations
from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages


class CodeGenState(TypedDict, total=False):
    """代码生成工作流的全局状态

    total=False 意味着所有字段都是 Optional，
    LangGraph 执行时只传入初始值，Agent 节点按需填充。
    """

    # ========== 输入（Java 端传入）==========
    user_request: str          # 用户原始需求（"做一个电商首页"）
    user_id: str               # 用户 ID
    app_id: str                # 应用 ID
    code_gen_type: str         # 代码生成类型：vue_project | python | java | go | rust | nodejs | html | multi_file | generic
    user_role: str             # 用户角色：user / admin（从 Java Session 透传）
    trace_id: str               # 全链路追踪 ID（Java 生成的 UUID）

    # ========== 模式检测（Intent Agent 之前）==========
    mode: str                   # "new" | "modify" | "rebuild" —— 决定路由走向
    has_existing_code: bool     # 项目目录是否已有代码文件（状态信号）

    # ========== Intent Agent 产出 ==========
    intent: dict | None        # {primary_intent, confidence, slots, should_clarify, ...}
    clarification: dict | None # {questions, missing_slots} for low confidence

    # ========== 修改模式上下文（从磁盘加载的历史产物）==========
    existing_prd: dict | None           # 从 project_dir/prd.json 加载
    existing_architecture: dict | None  # 从 project_dir/architecture.json 加载
    existing_code_files: list[dict]     # 现有项目文件快照 [{path, content}]

    # ========== PM Agent 产出 ==========
    prd: dict | None           # {page_name, page_type, features, target_audience, ...}

    # ========== Architect Agent 产出 ==========
    architecture: dict | None  # {tech_stack, component_tree, file_list, data_flow}

    # ========== Coder Agent 产出 ==========
    code_files: list[dict]     # [{path, content}]

    # ========== Reviewer Agent 产出 ==========
    review: dict | None        # {passed, score, issues}
    retry_count: int           # 当前重试次数
    max_retries: int           # 最大重试次数，默认 3

    # ========== Image Collector 产出 ==========
    images: list[dict]         # [{url, category, description}]

    # ========== Builder Agent 产出 ==========
    build_result: dict | None  # {success, log, project_dir}

    # ========== Indexing 产出 ==========
    indexing_result: dict | None  # {success, message, indexed_count, total_count}

    # ========== Quality Gate 产出 ==========
    quality_gate_result: dict | None  # {passed, review_score, has_critical_issues, syntax_check_passed, syntax_log, reason}

    # ========== 工具与构建字段 ==========
    project_dir: str           # 工具操作的工作目录，由 workflow 在 architect 之后设置

    # ========== 控制字段 ==========
    phase: str                 # 当前阶段：init / prd_done / arch_done / code_done / review_done / build_done / completed / error
    messages: Annotated[list, add_messages]  # 对话历史（LangGraph 自动累加）
    final_result: dict | None  # 最终结果（返回给 Java 端）
    error: str | None          # 错误信息
