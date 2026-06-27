"""删除文件 —— 对标 Java FileDeleteTool。仅 admin 角色可用。"""

import os
from langchain_core.tools import tool
from tools.context import get_project_dir
from tools.guard import check_tool_permission, PERMISSION_DENIED_MSG
from tools.path_guard import resolve_project_path

# 对标 Java FileDeleteTool.isImportantFile()
_PROTECTED_FILES = {
    "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "vite.config.js", "vite.config.ts", "vue.config.js",
    "tsconfig.json", "tsconfig.app.json", "tsconfig.node.json",
    "index.html", "main.js", "main.ts", "App.vue",
    ".gitignore", "README.md",
}


@tool
def delete_file(path: str) -> str:
    """删除指定路径的文件。重要文件（如package.json、配置文件等）受保护不可删除。

    Args:
        path: 文件的相对路径
    """
    if not check_tool_permission("delete_file"):
        return PERMISSION_DENIED_MSG

    project_dir = get_project_dir()
    if not project_dir:
        return "错误：工作目录未设置，无法删除文件"

    try:
        full_path = resolve_project_path(project_dir, path)
        if not os.path.exists(full_path):
            return f"警告：文件不存在，无需删除 - {path}"

        if not os.path.isfile(full_path):
            return f"错误：指定路径不是文件，无法删除 - {path}"

        file_name = os.path.basename(full_path)
        if file_name in _PROTECTED_FILES:
            return f"错误：不允许删除重要文件 - {file_name}"

        os.remove(full_path)
        return f"文件删除成功: {path}"
    except ValueError as e:
        return f"错误：{e}"
    except Exception as e:
        return f"删除文件失败: {path}, 错误: {e}"
