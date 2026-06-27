"""工具管理器 —— 对标 Java ToolManager"""

from tools.create_file import create_file
from tools.read_file import read_file
from tools.modify_file import modify_file
from tools.delete_file import delete_file
from tools.list_files import list_files
from tools.exit_tool import exit_tool

_ALL_TOOLS = [create_file, read_file, modify_file, delete_file, list_files, exit_tool]

_NAME_MAP = {t.name: t for t in _ALL_TOOLS}


def get_all_tools() -> list:
    """返回所有已注册的 LangChain tool 对象"""
    return _ALL_TOOLS


def get_tool_by_name(name: str):
    """按名称查找工具，未找到返回 None"""
    return _NAME_MAP.get(name)
