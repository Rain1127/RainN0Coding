"""
Coder Agent —— 程序员（工具增强版）

输入：Architect Agent 产出的架构方案
输出：CodeFile 列表 [{path, content}]
行为：ReAct 循环，LLM 可交替调用 create_file / read_file / modify_file /
      delete_file / list_files / exit_tool 工具完成代码生成
      收到 Reviewer 的重试请求时，附带 issue 列表重新生成

提示词根据 code_gen_type 动态生成，支持 Vue/Python/Java/Go/Rust/Node.js 等。
"""
import json
import os
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from config import config, get_lang_config
from state.code_gen_state import CodeGenState
from rag.rag_builder import build_rag_context
from llm_factory import create_tool_enabled_llm
from tools import (
    get_all_tools, set_tool_context, get_user_role,
    create_file, read_file, modify_file, delete_file, list_files, exit_tool,
)

# 最大工具调用轮数（对标 Java 侧 maxSequentialToolInvocations=20）
MAX_TOOL_ROUNDS = 20

# 工具名 → 函数映射
_TOOL_MAP = {
    "create_file": create_file,
    "read_file": read_file,
    "modify_file": modify_file,
    "delete_file": delete_file,
    "list_files": list_files,
    "exit_tool": exit_tool,
}


def _sanitize_ai_message(msg) -> None:
    """移除 AIMessage 中的 reasoning_content 非标字段，避免回传 API 校验失败。

    DeepSeek v4-pro thinking mode 在 API 响应中返回 reasoning_content，
    LangChain 将其存入 additional_kwargs。该字段不属于 OpenAI 标准 message schema，
    下一轮 ReAct 调用时会导致 API 校验错误。

    原地修改 message，对不含该字段的 message 是空操作。
    """
    if hasattr(msg, "additional_kwargs") and isinstance(msg.additional_kwargs, dict):
        msg.additional_kwargs.pop("reasoning_content", None)


# ============ Pydantic 输出模型（旧 JSON 模式的兜底） ============

class CodeFile(BaseModel):
    """单个代码文件"""
    path: str = Field(description="文件路径")
    content: str = Field(description="文件完整内容，包含所有 import/includes")


class CoderOutput(BaseModel):
    """Coder Agent 的完整输出（兜底 JSON 模式）"""
    files: list[CodeFile] = Field(description="生成的代码文件列表")
    notes: str | None = Field(default=None, description="备注说明")


# ============ System Prompt ============

def _build_coder_prompt(code_gen_type: str | None) -> str:
    lc = get_lang_config(code_gen_type)
    is_frontend = lc.get("is_frontend", False)
    rules = lc.get("code_style_rules", [])
    rules_text = "\n".join(f"{i+1}. {r}" for i, r in enumerate(rules)) if rules else "遵循该语言的标准编码规范"

    extras = []
    if lc.get("css"):
        extras.append(f"- CSS: {lc['css']}")
    if lc.get("state"):
        extras.append(f"- 状态管理: {lc['state']}")
    if lc.get("router"):
        extras.append(f"- 路由: {lc['router']}")
    if lc.get("build_tool"):
        extras.append(f"- 构建: {lc['build_tool']}")
    if lc.get("pkg_manager"):
        extras.append(f"- 包管理: {lc['pkg_manager']}")
    if lc.get("test"):
        extras.append(f"- 测试: {lc['test']}")
    extras_text = "\n".join(extras)

    tools_section = """## 可用工具

你可以使用以下工具完成任务。请用 create_file 逐个创建文件，每创建完一个文件可
用 read_file 检查内容是否正确，用 list_files 查看当前项目结构。全部文件创建完成后，
调用 exit_tool 退出。

- create_file(path, content): 创建文件
- read_file(path): 读取已有文件内容
- modify_file(path, old_content, new_content): 替换文件中的指定内容
- delete_file(path): 删除文件
- list_files(dir_path): 列出目录结构，dir_path 为空则列出整个项目
- exit_tool(): 全部完成时调用，调用后不能再用其他工具

## 工作流程
1. 先调用 list_files 查看当前项目已有文件
2. 逐个使用 create_file 创建架构方案 file_list 中的所有文件
3. 如果某个文件创建后发现需要调整，用 modify_file 修改
4. 全部文件创建完成后，调用 exit_tool 退出"""

    return f"""你是资深{lc['role']}。根据架构方案生成所有代码文件。

## 技术栈（严格遵循）
- 框架: {lc['framework']}
- 语言: {lc['lang']}
{extras_text}

## 代码规范（每条必遵守）
{rules_text}

## 完整性
- 每个文件必须完整可运行，包含所有必要的 import/include
- 不得使用占位符（如 "// TODO" 或 "/* 此处省略 */"）
- 遵循{lc['label']}的标准项目结构和命名约定

{tools_section}
"""


def _build_coder_modify_prompt(code_gen_type: str | None) -> str:
    """构建修改模式的 System Prompt —— 强调增量修改，不重新生成整个项目。"""
    lc = get_lang_config(code_gen_type)
    rules = lc.get("code_style_rules", [])
    rules_text = "\n".join(f"{i+1}. {r}" for i, r in enumerate(rules)) if rules else "遵循该语言的标准编码规范"

    return f"""你是资深{lc['role']}，正在进行**增量代码修改**（非从零新建）。

## 核心原则
1. **只修改受影响的文件**，不要重新生成不需要改的文件
2. **先读后改**：使用 read_file 查看现有文件内容，再用 modify_file 做定点修改
3. **保持一致性**：修改后的代码风格、命名、结构必须与现有代码完全一致
4. **不要删改无关代码**：仅针对用户需求修改相关部分

## 技术栈（严格遵循）
- 框架: {lc['framework']}
- 语言: {lc['lang']}

## 代码规范
{rules_text}

## 可用工具
- create_file(path, content): 创建新文件（仅在需要新增文件时使用）
- read_file(path): 读取已有文件内容
- modify_file(path, old_content, new_content): 替换文件中的指定内容（定点修改的核心工具）
- delete_file(path): 删除文件
- list_files(dir_path): 列出目录结构，dir_path 为空则列出整个项目
- exit_tool(): 全部完成时调用，调用后不能再用其他工具

## 工作流程
1. 先调用 list_files 了解项目当前文件结构
2. 定位需要修改的文件，用 read_file 读取其内容
3. 使用 modify_file 进行定点修改（只替换需要改的片段）
4. 如需新增文件，用 create_file 创建
5. 全部修改完成后，调用 exit_tool 退出"""


# ============ 格式化辅助函数 ============

def _format_component_tree(components: list, indent: int = 0) -> str:
    if not components:
        return "(无)"
    lines = []
    for comp in components:
        prefix = "  " * indent
        props = ", ".join(comp.get("props", [])) if comp.get("props") else "无"
        children = comp.get("children", [])
        lines.append(f"{prefix} - <{comp.get('name', '?')}>  "
                     f"[props: {props}]  "
                     f"({comp.get('description', '')})")
        if children:
            for child in children:
                lines.append(f"{prefix}     - <{child}>")
    return "\n".join(lines)


def _format_file_list(files: list) -> str:
    if not files:
        return "(无)"
    return "\n".join(
        f"- [{f.get('file_type', '?')}] `{f.get('path', '?')}` — {f.get('description', '')}"
        for f in files
    )


def _format_data_flow(flows: list) -> str:
    if not flows:
        return "(无)"
    return "\n".join(
        f"- {f.get('from_component', f.get('from_module', '?'))} -> "
        f"{f.get('to_component', f.get('to_module', '?'))}: "
        f"{f.get('data_type', f.get('data', '?'))} "
        f"(via {f.get('mechanism', '?')})"
        for f in flows
    )


def _format_existing_code_context(
    existing_files: list[dict] | None,
    existing_arch: dict | None,
) -> str:
    """格式化现有代码上下文，作为修改模式的参考信息注入 prompt。"""
    parts = ["## 现有项目结构（请在此基础上增量修改，不要重新生成整个项目）"]

    if existing_arch:
        comp_tree = existing_arch.get("component_tree", [])
        file_list = existing_arch.get("file_list", [])
        if comp_tree:
            parts.append("\n### 现有组件树")
            parts.append(_format_component_tree(comp_tree))
        if file_list:
            parts.append("\n### 现有架构文件清单")
            parts.append(_format_file_list(file_list))

    if existing_files:
        parts.append("\n### 现有文件列表")
        for f in existing_files:
            path = f.get("path", "")
            lines = len(f.get("content", "").split("\n"))
            parts.append(f"- `{path}` ({lines} 行)")
        parts.append("\n请先 read_file 查看需要修改的文件，再使用 modify_file 定点修改。")
        parts.append("只修改受影响的文件，不要重新生成或修改无关文件。")

    return "\n".join(parts)


def _format_issues(issues: list) -> str:
    if not issues:
        return ""
    lines = ["## 上一轮代码审查发现以下问题，请逐一修复："]
    for i, issue in enumerate(issues, 1):
        severity = issue.get("severity", "info")
        severity_mark = {"critical": "[严重]", "warn": "[警告]", "info": "[建议]"}.get(severity, "")
        lines.append(
            f"{i}. {severity_mark} **{issue.get('file', '?')}**: {issue.get('description', '')}"
        )
        if issue.get("suggestion"):
            lines.append(f"   -> 修复建议: {issue['suggestion']}")
    return "\n".join(lines)


def _collect_code_files(project_dir: str) -> list[dict]:
    """从项目目录收集所有已创建的文件，作为兜底"""
    code_files = []
    if not project_dir or not os.path.isdir(project_dir):
        return code_files
    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [d for d in dirs if d not in
                   {"node_modules", ".git", "__pycache__", ".venv", "dist", "build"}]
        for name in files:
            if name.endswith((".pyc", ".log", ".lock", ".tmp")):
                continue
            full = os.path.join(root, name)
            rel = os.path.relpath(full, project_dir).replace("\\", "/")
            try:
                with open(full, "r", encoding="utf-8") as f:
                    content = f.read()
                code_files.append({"path": rel, "content": content})
            except Exception:
                pass
    return code_files


# ============ Agent 主函数 ============

def coder_agent(state: CodeGenState) -> CodeGenState:
    """Coder Agent — ReAct 循环，LLM 通过工具操作文件系统"""

    code_gen_type = state.get("code_gen_type", "vue_project")
    app_id = state.get("app_id", "unknown")
    mode = state.get("mode", "new")
    retry_count = state.get("retry_count", 0)

    # 根据模式选择 System Prompt
    if mode == "modify":
        system_prompt = _build_coder_modify_prompt(code_gen_type)
    else:
        system_prompt = _build_coder_prompt(code_gen_type)

    # architecture 校验：modify 模式用 existing_architecture 兜底
    architecture = state.get("architecture") or state.get("existing_architecture")
    if not architecture:
        state["error"] = "Architecture 为空，Coder Agent 无法生成代码"
        state["phase"] = "error"
        return state

    file_list = architecture.get("file_list", [])
    if not file_list and mode != "modify":
        state["error"] = "Architecture.file_list 为空，没有需要生成的文件"
        state["phase"] = "error"
        return state

    # === 设置工具工作目录 ===
    project_dir = state.get("project_dir", "")
    if not project_dir:
        project_dir = os.path.join(
            config.CODE_OUTPUT_DIR,
            f"{code_gen_type}_{app_id}"
        )
        state["project_dir"] = project_dir
    os.makedirs(project_dir, exist_ok=True)
    user_role = state.get("user_role", "user")
    set_tool_context(project_dir, app_id, user_role)

    # === 重试上下文（含 AutoGen 讨论结论） ===
    review = state.get("review")
    retry_context = ""
    if review and not review.get("passed"):
        issues = review.get("issues", [])
        retry_context = _format_issues(issues)
        # 如果有 AutoGen 三方讨论结论，附加上
        autogen_ctx = review.get("autogen_context", "")
        if autogen_ctx:
            retry_context += "\n" + autogen_ctx

    # === RAG 检索 ===
    rag_contexts: dict[str, str] = {}
    for f in file_list:
        ctx = build_rag_context(
            f, architecture,
            phase=state.get("phase", "code"),
            retry_count=state.get("retry_count", 0),
            user_request=state.get("user_request", ""),
            code_gen_type=code_gen_type,
            app_id=app_id,
        )
        if ctx:
            rag_contexts[f.get("path", "")] = ctx
    rag_section = ""
    if rag_contexts:
        rag_section = "\n## 可复用资源（来自 RAG 多路检索 —— 优先使用，避免造轮子）\n\n"
        for path, ctx in rag_contexts.items():
            rag_section += f"### 为 `{path}` 检索到的参考:\n{ctx}\n\n"

    # === 构造初始消息 ===
    if mode == "modify":
        # 修改模式：注入现有代码上下文，强调增量修改
        user_prompt_parts = [
            "请根据以下用户需求，在现有代码基础上进行增量修改。",
            "先调用 list_files 查看项目当前结构，用 read_file 查看需要修改的文件，",
            "然后用 modify_file 做定点修改。只修改受影响的文件，不要重新生成无关文件。",
            "",
            "## 用户修改需求",
            state.get("user_request", ""),
            "",
            _format_existing_code_context(
                state.get("existing_code_files", []),
                state.get("existing_architecture"),
            ),
        ]
        # modify 模式下也有架构参考（新建模式的架构或已有架构）
        if architecture:
            user_prompt_parts.extend([
                "",
                "## 参考架构",
                _format_file_list(file_list) if file_list else "",
                _format_component_tree(architecture.get("component_tree", [])),
            ])
    else:
        user_prompt_parts = [
            "请根据以下架构方案生成所有代码文件。使用 create_file 工具逐个创建文件。",
            "先调用 list_files 查看项目结构，然后逐个创建文件，全部完成后调用 exit_tool。",
            "",
            "## 模块/组件树",
            _format_component_tree(architecture.get("component_tree", [])),
            "",
            "## 文件清单",
            _format_file_list(file_list),
            "",
            "## 数据流",
            _format_data_flow(architecture.get("data_flow", [])),
            "",
            "## 技术栈",
            str(architecture.get("tech_stack", {})),
        ]

    if rag_section:
        user_prompt_parts.append(rag_section)
    if retry_context:
        user_prompt_parts.extend(["", retry_context])

    user_message = "\n".join(user_prompt_parts)

    tools = get_all_tools()
    llm = create_tool_enabled_llm(tools, group="reasoning")

    # ===== LangSmith trace metadata =====
    _base_langsmith_extra = {
        "run_name": "coder_agent",
        "tags": ["coder_agent", "reasoning"],
        "metadata": {
            "user_id": state.get("user_id", "unknown"),
            "retry_count": retry_count,
        },
    }

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]

    # === ReAct 循环 ===
    code_files: list[dict] = []
    exited = False

    for round_num in range(1, MAX_TOOL_ROUNDS + 1):
        try:
            round_extra = dict(_base_langsmith_extra)
            round_extra.setdefault("metadata", {})
            round_extra["metadata"]["react_round"] = round_num
            response = llm.invoke(messages, config=round_extra)
        except Exception as e:
            print(f"[Coder Agent] LLM 调用失败 (第{round_num}轮): {e}")
            state["error"] = f"Coder Agent LLM 调用失败 (第{round_num}轮): {e}"
            state["phase"] = "error"
            return state

        _sanitize_ai_message(response)
        messages.append(response)

        # 是否有 tool_calls
        if hasattr(response, "tool_calls") and response.tool_calls:
            for tc in response.tool_calls:
                tool_name = tc.get("name", "")
                tool_args = tc.get("args", {})
                tool_id = tc.get("id", "")

                func = _TOOL_MAP.get(tool_name)
                if func is None:
                    tool_result = f"未知工具: {tool_name}"
                else:
                    try:
                        tool_result = func.invoke(tool_args)
                    except Exception as e:
                        tool_result = f"工具执行失败: {e}"

                if tool_name == "exit_tool":
                    exited = True

                messages.append(ToolMessage(content=str(tool_result),
                                            tool_call_id=tool_id))

            print(f"[Coder Agent] 第{round_num}轮: {len(response.tool_calls)} 次工具调用")

            if exited:
                print(f"[Coder Agent] exit_tool 被调用，退出 ReAct 循环")
                break
        else:
            # 没有 tool_calls —— 可能是 LLM 直接输出了文本（旧 JSON 模式兜底）
            content = response.content if hasattr(response, "content") else str(response)
            if content:
                try:
                    parsed = json.loads(_strip_code_fences(content))
                    if "files" in parsed:
                        code_files = [{"path": f["path"], "content": f["content"]}
                                      for f in parsed["files"]]
                        print(f"[Coder Agent] 兜底 JSON 解析: {len(code_files)} 文件")
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass
            break

    # === 收集结果 ===
    # 如果工具模式没有产生 code_files，从文件系统收集
    if not code_files:
        code_files = _collect_code_files(project_dir)

    if not code_files:
        state["error"] = "Coder Agent 未能生成任何代码文件"
        state["phase"] = "error"
        return state

    state["code_files"] = code_files
    state["phase"] = "code_done"

    total_lines = sum(len(f["content"].split("\n")) for f in code_files)
    print(f"[Coder Agent] 完成: {len(code_files)} 文件, 总计 {total_lines} 行代码")

    return state


def _strip_code_fences(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 2:
            inner = parts[1]
            if inner.startswith("json"):
                inner = inner[4:]
            text = inner.strip()
    return text
