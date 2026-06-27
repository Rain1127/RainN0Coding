"""退出工具调用 —— 对标 Java ExitTool"""

from langchain_core.tools import tool


@tool
def exit_tool() -> str:
    """当任务已完成或无需继续调用工具时，使用此工具退出操作，防止循环。调用此工具后不应再调用其他工具。"""
    return "不要继续调用工具，可以输出最终结果了"
