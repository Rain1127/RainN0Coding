"""工具管理器 —— 对标 Java ToolManager"""

from tools.create_file import create_file
from tools.read_file import read_file
from tools.modify_file import modify_file
from tools.delete_file import delete_file
from tools.list_files import list_files
from tools.exit_tool import exit_tool
from langchain_core.tools import tool


@tool('read_file')
def legacy_read_file(path: str) -> str:
    """Read the complete content of a project file."""
    return read_file.invoke({'path': path})

_ALL_TOOLS = [create_file, legacy_read_file, modify_file, delete_file, list_files, exit_tool]

_NAME_MAP = {t.name: t for t in _ALL_TOOLS}


def get_all_tools(policy: dict | None = None) -> list:
    """返回所有已注册的 LangChain tool 对象"""
    tools = list(_ALL_TOOLS)
    if (policy or {}).get('context') or (policy or {}).get('editing'):
        tools = [read_file if t.name == 'read_file' else t for t in tools]
    if (policy or {}).get('context'):
        from tools.on_demand import search_code, retrieve_context, read_progress
        tools += [search_code, retrieve_context, read_progress]
    if (policy or {}).get('editing'):
        from tools.apply_patch import apply_patch
        tools.append(apply_patch)
    if (policy or {}).get('executor') and (policy or {}).get('events'):
        from tools.run_checks import run_checks
        tools.append(run_checks)
    return tools


def get_tool_by_name(name: str):
    """按名称查找工具，未找到返回 None"""
    return _NAME_MAP.get(name)
