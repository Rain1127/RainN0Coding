"""Read file tool."""

import os

from guardrails.audit import audit_from_decision
from guardrails.engine import evaluate_tool_action
from guardrails.models import ToolAction
from langchain_core.tools import tool
from tools.context import get_app_id, get_project_dir, get_user_role
from tools.path_guard import resolve_project_path


@tool
def read_file(path: str) -> str:
    """Read content from a project file."""
    project_dir = get_project_dir()
    if not project_dir:
        return "错误：未设置工作目录，无法读取文件"

    try:
        decision = evaluate_tool_action(
            ToolAction(
                tool_name="read_file",
                project_dir=project_dir,
                relative_path=path,
                user_role=get_user_role(),
            )
        )
        audit_from_decision(
            decision,
            app_id=get_app_id(),
            tool_name="read_file",
            path=path,
        )
        if decision.action == "block":
            return f"guardrail_blocked:{decision.rule_id}:{decision.message}"

        full_path = resolve_project_path(project_dir, path)
        if not os.path.isfile(full_path):
            return f"错误：文件不存在或不是文件 - {path}"
        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()
    except ValueError as e:
        return f"错误：{e}"
    except Exception as e:
        return f"读取文件失败: {path}, 错误: {e}"
