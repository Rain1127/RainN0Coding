"""Atomic creation with explicit overwrite semantics for strict edit runs."""
from langchain_core.tools import tool
from tools.context import get_tool_policy
from tools.file_edit import authorize, file_lock, check_hash, atomic_write, result, failure, EditRejected


@tool
def create_file(path: str, content: str, overwrite: bool = False, expected_hash: str | None = None) -> str:
    """Create a file. Existing files in strict edit runs require overwrite=true and the hash from read_file; prefer modify_file."""
    try:
        full = authorize('create_file', path, content=content)
        with file_lock(full):
            raw = full.read_bytes() if full.is_file() else None
            if raw is not None and get_tool_policy().get('editing') and (not overwrite or expected_hash is None):
                raise EditRejected('existing_file_requires_explicit_overwrite_hash', next_action='read_file and modify_file')
            check_hash(raw, expected_hash)
            updated = content.encode('utf-8')
            if raw != updated:
                atomic_write(full, updated, raw)
            if not get_tool_policy().get('editing'):
                return f'文件写入成功: {path}'
            return result(path, raw, updated, status='created' if raw is None else ('unchanged' if raw == updated else 'overwritten'))
    except Exception as exc:
        if not get_tool_policy().get('editing') and isinstance(exc, EditRejected) and exc.reason == 'guardrail_blocked':
            return 'guardrail_blocked:' + str(exc.details.get('rule_id'))
        return failure(exc)
