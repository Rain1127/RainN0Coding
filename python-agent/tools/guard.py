"""工具权限守卫 —— RBAC 权限校验

权限分级：
  - admin：所有工具可用
  - user：create / read / list / modify / exit 可用，delete 不可用
  - 未认证/未知角色：等同于 user（最小权限原则）
"""

from tools.context import get_user_role

TOOL_PERMISSIONS: dict[str, list[str]] = {
    "create_file": ["admin", "user"],
    "read_file":   ["admin", "user"],
    "list_files":  ["admin", "user"],
    "modify_file": ["admin", "user"],
    "delete_file": ["admin"],            # 仅 admin 可删除
    "exit_tool":   ["admin", "user"],
}

PERMISSION_DENIED_MSG = "权限不足：当前用户角色无权执行此操作"


def check_tool_permission(tool_name: str) -> bool:
    """校验当前用户是否有权使用指定工具。

    Args:
        tool_name: 工具名称，如 "delete_file"

    Returns:
        True 表示允许，False 表示拒绝
    """
    allowed_roles = TOOL_PERMISSIONS.get(tool_name)
    if allowed_roles is None:
        return True  # 未注册的工具默认放行（向前兼容）

    current_role = get_user_role()
    return current_role in allowed_roles
