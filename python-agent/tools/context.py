"""工具公共上下文 —— 通过 contextvars 在线程/协程间安全传递工作目录和 app_id"""

from contextvars import ContextVar

_current_project_dir: ContextVar[str] = ContextVar("tool_project_dir", default="")
_current_app_id: ContextVar[str] = ContextVar("tool_app_id", default="")
_current_user_role: ContextVar[str] = ContextVar("tool_user_role", default="user")


def set_tool_context(project_dir: str, app_id: str, user_role: str = "user") -> None:
    _current_project_dir.set(project_dir)
    _current_app_id.set(app_id)
    _current_user_role.set(user_role)


def get_project_dir() -> str:
    return _current_project_dir.get()


def get_app_id() -> str:
    return _current_app_id.get()


def get_user_role() -> str:
    return _current_user_role.get()
