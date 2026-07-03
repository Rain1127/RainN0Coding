"""List files tool."""

import os

from guardrails.audit import audit_from_decision
from guardrails.engine import evaluate_tool_action
from guardrails.models import ToolAction
from langchain_core.tools import tool
from tools.context import get_app_id, get_project_dir, get_user_role
from tools.path_guard import resolve_project_path

_IGNORED_NAMES = {
    "node_modules", ".git", "dist", "build", ".DS_Store",
    ".env", "target", ".mvn", ".idea", ".vscode", "coverage",
    "__pycache__", ".venv", "venv", ".pytest_cache",
}

_IGNORED_EXTENSIONS = {".log", ".tmp", ".cache", ".lock", ".pyc"}


@tool
def list_files(dir_path: str = "") -> str:
    """List project files and directories."""
    project_dir = get_project_dir()
    if not project_dir:
        return "错误：未设置工作目录，无法读取目录"

    lines = ["项目目录结构:"]

    try:
        decision = evaluate_tool_action(
            ToolAction(
                tool_name="list_files",
                project_dir=project_dir,
                dir_path=dir_path,
                user_role=get_user_role(),
            )
        )
        audit_from_decision(
            decision,
            app_id=get_app_id(),
            tool_name="list_files",
            path=dir_path,
        )
        if decision.action == "block":
            return f"guardrail_blocked:{decision.rule_id}:{decision.message}"

        target = resolve_project_path(project_dir, dir_path)
        if not os.path.isdir(target):
            return f"错误：目录不存在或不是目录 - {dir_path or '根目录'}"
        for root, dirs, files in os.walk(target):
            dirs[:] = [d for d in dirs if d not in _IGNORED_NAMES]

            depth = _get_depth(target, root)
            indent = "  " * depth

            for name in sorted(dirs):
                lines.append(f"{indent}{name}/")

            for name in sorted(files):
                if _should_ignore(name):
                    continue
                lines.append(f"{indent}{name}")
    except ValueError as e:
        return f"错误：{e}"
    except Exception as e:
        return f"读取目录失败: {e}"

    if len(lines) == 1:
        lines.append("(空目录)")

    return "\n".join(lines)


def _get_depth(base: str, current: str) -> int:
    rel = os.path.relpath(current, base)
    if rel == ".":
        return 0
    return rel.count(os.sep) + 1


def _should_ignore(name: str) -> bool:
    if name in _IGNORED_NAMES:
        return True
    _, ext = os.path.splitext(name)
    return ext.lower() in _IGNORED_EXTENSIONS
