"""Unique-by-default edits with explicit batch count and optional stale-read guard."""
from langchain_core.tools import tool
from tools.file_edit import authorize, file_lock, check_hash, atomic_write, result, failure, replace_checked, EditRejected
from tools.context import get_tool_policy


@tool
def modify_file(path: str, old_content: str, new_content: str, mode: str = 'unique',
                expected_count: int | None = None, expected_hash: str | None = None) -> str:
    """Replace one exact match. Batch mode='all' REQUIRES expected_count. Pass read_file.sha256 as expected_hash; newline differences require rereading."""
    try:
        full = authorize('modify_file', path, old_content=old_content, new_content=new_content)
        if get_tool_policy().get('editing') and expected_hash is None:
            raise EditRejected('modify_requires_expected_hash', next_action='read_file to obtain sha256')
        with file_lock(full):
            if not full.is_file():
                raise EditRejected('file_not_found', path=path)
            raw = full.read_bytes()
            check_hash(raw, expected_hash)
            modified, count = replace_checked(raw.decode('utf-8'), old_content, new_content,
                                              mode=mode, expected_count=expected_count)
            updated = modified.encode('utf-8')
            if updated != raw:
                atomic_write(full, updated, raw)
            if not get_tool_policy().get('editing'):
                return f'文件修改成功: {path}' if updated != raw else f'信息：替换后文件内容未发生变化 - {path}'
            return result(path, raw, updated, matches=count, status='modified' if updated != raw else 'unchanged')
    except Exception as exc:
        if not get_tool_policy().get('editing'):
            if isinstance(exc, EditRejected) and exc.reason == 'file_not_found':
                return f'错误：文件不存在或不是文件 - {path}'
            if isinstance(exc, EditRejected) and exc.reason == 'match_count_mismatch':
                return f'警告：文件中未找到要替换的内容，文件未修改 - {path}'
            if isinstance(exc, EditRejected) and exc.reason == 'permission_denied':
                return '权限不足：当前用户角色无权执行此操作'
            if isinstance(exc, EditRejected) and exc.reason == 'guardrail_blocked':
                return 'guardrail_blocked:' + str(exc.details.get('rule_id'))
        return failure(exc)
