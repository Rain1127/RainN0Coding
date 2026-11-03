"""Read file tool."""

import os
import hashlib
import json

from guardrails.audit import audit_from_decision
from guardrails.engine import evaluate_tool_action
from guardrails.models import ToolAction
from langchain_core.tools import tool
from tools.context import get_app_id, get_project_dir, get_user_role, get_tool_policy
from tools.path_guard import resolve_project_path


@tool
def read_file(path: str, start_line: int = 1, end_line: int | None = None, offset: int = 0, limit: int = 6000) -> str:
    """Read a file or a 1-based line range. Large results have next_offset; reuse identical range with that offset to read the remainder."""
    project_dir = get_project_dir()
    if not project_dir:
        return "错误：未设置工作目录，无法读取文件"

    try:
        decision = evaluate_tool_action(
            ToolAction(
                tool_name="read_file",
                project_dir=project_dir,
                relative_path=path,
                user_role=get_user_role(),
            )
        )
        audit_from_decision(
            decision,
            app_id=get_app_id(),
            tool_name="read_file",
            path=path,
        )
        if decision.action == "block":
            return f"guardrail_blocked:{decision.rule_id}:{decision.message}"

        full_path = resolve_project_path(project_dir, path)
        if not os.path.isfile(full_path):
            return f"错误：文件不存在或不是文件 - {path}"
        with open(full_path, 'rb') as handle:
            raw = handle.read()
        content = raw.decode('utf-8')
        policy = get_tool_policy()
        if not policy.get('context') and not policy.get('editing') and start_line == 1 and end_line is None and offset == 0:
            return content
        if start_line < 1 or (end_line is not None and end_line < start_line) or offset < 0 or not 1 <= limit <= 20000:
            return json.dumps({'ok': False, 'reason': 'invalid_read_range'})
        lines = content.splitlines(keepends=True)
        selected = ''.join(lines[start_line - 1:end_line])
        text = selected[offset:offset + limit]
        next_offset = offset + len(text)
        return json.dumps({'ok': True, 'path': path, 'sha256': hashlib.sha256(raw).hexdigest(),
            'start_line': start_line, 'end_line': min(end_line or len(lines), len(lines)),
            'total_lines': len(lines), 'offset': offset, 'content': text,
            'truncated': next_offset < len(selected),
            'next_offset': next_offset if next_offset < len(selected) else None,
            'continuation': 'Use identical start_line/end_line with next_offset, or select another line range'}, ensure_ascii=False)
    except ValueError as e:
        return f"错误：{e}"
    except Exception as e:
        return f"读取文件失败: {path}, 错误: {e}"
