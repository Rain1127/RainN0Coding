"""读取文件 —— 对标 Java FileReadTool"""

import os
from langchain_core.tools import tool
from tools.context import get_project_dir
from tools.path_guard import resolve_project_path


@tool
def read_file(path: str) -> str:
    """读取指定路径的文件内容。

    Args:
        path: 文件的相对路径，例如 "src/App.vue"
    """
    project_dir = get_project_dir()
    if not project_dir:
        return "错误：工作目录未设置，无法读取文件"

    try:
        full_path = resolve_project_path(project_dir, path)
        if not os.path.isfile(full_path):
            return f"错误：文件不存在或不是文件 - {path}"
        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()
    except ValueError as e:
        return f"错误：{e}"
    except Exception as e:
        return f"读取文件失败: {path}, 错误: {e}"
