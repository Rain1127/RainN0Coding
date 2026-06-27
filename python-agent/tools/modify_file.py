"""修改文件 —— 对标 Java FileModifyTool。仅 admin/user 可用。"""

import os
from langchain_core.tools import tool
from tools.context import get_project_dir
from tools.guard import check_tool_permission, PERMISSION_DENIED_MSG
from tools.path_guard import resolve_project_path


@tool
def modify_file(path: str, old_content: str, new_content: str) -> str:
    """修改文件内容，用new_content替换文件中所有的old_content。

    Args:
        path: 文件的相对路径
        old_content: 要替换的旧内容（精确匹配，区分大小写）
        new_content: 替换后的新内容
    """
    if not check_tool_permission("modify_file"):
        return PERMISSION_DENIED_MSG

    project_dir = get_project_dir()
    if not project_dir:
        return "错误：工作目录未设置，无法修改文件"

    try:
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
