"""创建文件 —— 对标 Java FileWriteTool"""

import os
from langchain_core.tools import tool
from tools.context import get_project_dir
from tools.path_guard import resolve_project_path


@tool
def create_file(path: str, content: str) -> str:
    """写入文件到指定路径。路径相对于项目根目录。会自动创建父目录，如果文件已存在则覆盖。

    Args:
        path: 文件的相对路径，例如 "src/components/Header.vue"
        content: 要写入文件的内容
    """
    project_dir = get_project_dir()
    if not project_dir:
        return "错误：工作目录未设置，无法写入文件"

    try:
        full_path = resolve_project_path(project_dir, path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"文件写入成功: {path}"
    except ValueError as e:
        return f"错误：{e}"
    except Exception as e:
        return f"文件写入失败: {path}, 错误: {e}"
