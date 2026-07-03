"""Delete file tool."""

import os

from guardrails.audit import audit_from_decision
from guardrails.engine import evaluate_tool_action
from guardrails.models import ToolAction
from langchain_core.tools import tool
from tools.context import get_app_id, get_project_dir, get_user_role
from tools.guard import PERMISSION_DENIED_MSG, check_tool_permission
from tools.path_guard import resolve_project_path


@tool
def delete_file(path: str) -> str:
    """Delete a project file."""
    if not check_tool_permission("delete_file"):
        return PERMISSION_DENIED_MSG

    project_dir = get_project_dir()
    if not project_dir:
        return "错误：未设置工作目录，无法删除文件"

    try:
        decision = evaluate_tool_action(
            ToolAction(
                tool_name="delete_file",
                project_dir=project_dir,
                relative_path=path,
                user_role=get_user_role(),
            )
        )
        audit_from_decision(
            decision,
            app_id=get_app_id(),
            tool_name="delete_file",
            path=path,
        )
        if decision.action == "block":
            return f"guardrail_blocked:{decision.rule_id}:{decision.message}"

        full_path = resolve_project_path(project_dir, path)
        if not os.path.exists(full_path):
            return f"警告：文件不存在，无需删除 - {path}"

        if not os.path.isfile(full_path):
            return f"错误：指定路径不是文件，无法删除 - {path}"

        os.remove(full_path)
        return f"文件删除成功: {path}"
    except ValueError as e:
        return f"错误：{e}"
    except Exception as e:
        return f"删除文件失败: {path}, 错误: {e}"
