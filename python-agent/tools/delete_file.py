"""Owner-role guarded deletion with a stale-read precondition."""
from langchain_core.tools import tool
from tools.context import get_tool_policy
from tools.file_edit import authorize, file_lock, check_hash, result, failure, EditRejected


@tool
def delete_file(path: str, expected_hash: str | None = None) -> str:
    """Delete one project file. Strict edit runs require its current read_file.sha256; admin permission is still required."""
    try:
        full = authorize('delete_file', path)
        with file_lock(full):
            if not full.is_file():
                raise EditRejected('file_not_found')
            raw = full.read_bytes()
            if get_tool_policy().get('editing') and expected_hash is None:
                raise EditRejected('delete_requires_expected_hash')
            check_hash(raw, expected_hash)
            full.unlink()
            return result(path, raw, None, status='deleted') if get_tool_policy().get('editing') else f'文件删除成功: {path}'
    except Exception as exc:
        if not get_tool_policy().get('editing') and isinstance(exc, EditRejected):
            if exc.reason == 'permission_denied': return '权限不足：当前用户角色无权执行此操作'
            if exc.reason == 'guardrail_blocked': return 'guardrail_blocked:' + str(exc.details.get('rule_id'))
            if exc.reason == 'file_not_found': return f'警告：文件不存在，无需删除 - {path}'
        return failure(exc)
