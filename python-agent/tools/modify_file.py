"""Modify file tool."""

import os

from guardrails.audit import audit_from_decision
from guardrails.engine import evaluate_tool_action
from guardrails.models import ToolAction
from langchain_core.tools import tool
from tools.context import get_app_id, get_project_dir, get_user_role
from tools.guard import PERMISSION_DENIED_MSG, check_tool_permission
from tools.path_guard import resolve_project_path


@tool
def modify_file(path: str, old_content: str, new_content: str) -> str:
    """Replace all matching old_content with new_content in a file."""
    if not check_tool_permission("modify_file"):
        return PERMISSION_DENIED_MSG

    project_dir = get_project_dir()
    if not project_dir:
        return "错误：未设置工作目录，无法修改文件"

    try:
        decision = evaluate_tool_action(
            ToolAction(
                tool_name="modify_file",
                project_dir=project_dir,
                relative_path=path,
                old_content=old_content,
                new_content=new_content,
                user_role=get_user_role(),
            )
        )
        audit_from_decision(
            decision,
            app_id=get_app_id(),
            tool_name="modify_file",
            path=path,
        )
        if decision.action == "block":
            return f"guardrail_blocked:{decision.rule_id}:{decision.message}"

        full_path = resolve_project_path(project_dir, path)
        if not os.path.isfile(full_path):
            return f"错误：文件不存在或不是文件 - {path}"
        with open(full_path, "r", encoding="utf-8") as f:
            original = f.read()

        if old_content not in original:
            return f"警告：文件中未找到要替换的内容，文件未修改 - {path}"

        modified = original.replace(old_content, new_content)

        if modified == original:
            return f"信息：替换后文件内容未发生变化 - {path}"

        with open(full_path, "w", encoding="utf-8") as f:
            f.write(modified)

        return f"文件修改成功: {path}"
    except ValueError as e:
        return f"错误：{e}"
    except Exception as e:
        return f"修改文件失败: {path}, 错误: {e}"
