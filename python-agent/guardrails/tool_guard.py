import os

from guardrails.models import GuardrailDecision, ToolAction
from guardrails.policy import (
    ALLOWED_WRITE_EXTENSIONS,
    ELEVATED_SCRIPT_EXTENSIONS,
    PROTECTED_FILE_NAMES,
    SENSITIVE_FILE_MARKERS,
    max_file_write_bytes,
    max_list_files_depth,
    max_modify_replacement_bytes,
)


def evaluate_tool_action_context(action: ToolAction) -> GuardrailDecision:
    target = action.relative_path or action.dir_path or ""  # 原始操作路径
    normalized = target.replace("\\", "/")
    target_name = os.path.basename(normalized)  # 检查具体文件名
    target_lower = normalized.lower()
    _, ext = os.path.splitext(target_name)
    ext = ext.lower()  # 文件扩展名

    # 防止跳出上一级，路径穿越
    if ".." in [part for part in normalized.split("/") if part]:
        return GuardrailDecision.block(
            "tool.path_escape_blocked",
            "tool action attempted to escape the project root",
            {"path": target},
        )

    # 防止访问如ssh等敏感文件
    if any(marker in target_lower for marker in SENSITIVE_FILE_MARKERS):
        return GuardrailDecision.block(
            "tool.sensitive_file_blocked",
            "tool action targeted a sensitive file",
            {"path": target},
        )

    # 防止删除关键文件
    if action.tool_name == "delete_file" and target_name in PROTECTED_FILE_NAMES:
        return GuardrailDecision.block(
            "tool.delete_protected_file_blocked",
            "tool action attempted to delete a protected file",
            {"path": target},
        )

    # 防止创建不允许的文件扩展名
    if action.tool_name in {"create_file", "modify_file"} and ext:
        allowed_extensions = ALLOWED_WRITE_EXTENSIONS | ELEVATED_SCRIPT_EXTENSIONS
        if ext not in allowed_extensions:
            return GuardrailDecision.block(
                "tool.extension_blocked",
                "tool action targeted a disallowed file extension",
                {"path": target, "extension": ext},
            )

    # 防止单次创建内容超过配置上限
    if action.tool_name == "create_file":
        if len(action.content.encode("utf-8")) > max_file_write_bytes():
            return GuardrailDecision.block(
                "tool.write_too_large_blocked",
                "tool write content exceeded the configured limit",
                {"path": target},
            )
        if ext in ELEVATED_SCRIPT_EXTENSIONS:
            return GuardrailDecision.warn(
                "tool.create_script_warn",
                "tool action created an executable script",
                {"path": target},
            )

    # 防止单次修改内容超过配置上限
    if action.tool_name == "modify_file":
        if len(action.new_content.encode("utf-8")) > max_modify_replacement_bytes():
            return GuardrailDecision.block(
                "tool.modify_too_large_blocked",
                "tool modification exceeded the configured limit",
                {"path": target},
            )
        if target_name in PROTECTED_FILE_NAMES:
            return GuardrailDecision.warn(
                "tool.modify_entrypoint_warn",
                "tool action modified a protected entry file",
                {"path": target},
            )

    # 防止列目录深度超过配置上限
    if action.tool_name == "list_files":
        depth = len([part for part in normalized.split("/") if part])
        if depth > max_list_files_depth():
            return GuardrailDecision.block(
                "tool.list_depth_blocked",
                "tool directory traversal depth exceeded the configured limit",
                {"dir_path": action.dir_path, "depth": depth},
            )

    return GuardrailDecision.allow("tool.ok", {"tool_name": action.tool_name, "path": target})
