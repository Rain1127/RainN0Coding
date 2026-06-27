"""列出目录结构 —— 对标 Java FileDirReadTool"""

import os
from langchain_core.tools import tool
from tools.context import get_project_dir
from tools.path_guard import resolve_project_path

_IGNORED_NAMES = {
    "node_modules", ".git", "dist", "build", ".DS_Store",
    ".env", "target", ".mvn", ".idea", ".vscode", "coverage",
    "__pycache__", ".venv", "venv", ".pytest_cache",
}

_IGNORED_EXTENSIONS = {".log", ".tmp", ".cache", ".lock", ".pyc"}


@tool
def list_files(dir_path: str = "") -> str:
    """读取目录结构，获取指定目录下的所有文件和子目录信息。留空则读取整个项目结构。

    Args:
        dir_path: 目录的相对路径，为空则读取整个项目根目录
    """
    project_dir = get_project_dir()
    if not project_dir:
        return "错误：工作目录未设置，无法读取目录"

    lines = ["项目目录结构:"]

    try:
        target = resolve_project_path(project_dir, dir_path)
        if not os.path.isdir(target):
            return f"错误：目录不存在或不是目录 - {dir_path or '根目录'}"
        for root, dirs, files in os.walk(target):
            # 原地修改 dirs 来跳过忽略的目录
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
