"""Guarded, optimistic, atomic single-file edits; no cross-file transaction."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import tempfile
from guardrails.audit import audit_from_decision
from guardrails.engine import evaluate_tool_action
from guardrails.models import ToolAction
from tools.context import get_project_dir, get_app_id, get_user_role, get_tool_policy
from tools.guard import check_tool_permission
from tools.path_guard import resolve_project_path


class EditRejected(ValueError):
    def __init__(self, reason, **details):
        self.reason, self.details = reason, details
        super().__init__(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest() if raw is not None else None


def authorize(tool_name, path, *, content='', old_content='', new_content=''):
    if not check_tool_permission(tool_name):
        raise EditRejected('permission_denied')
    decision = evaluate_tool_action(ToolAction(tool_name=tool_name, project_dir=get_project_dir(),
        relative_path=path, content=content, old_content=old_content, new_content=new_content, user_role=get_user_role()))
    audit_from_decision(decision, app_id=get_app_id(), tool_name=tool_name, path=path)
    if decision.action == 'block':
        raise EditRejected('guardrail_blocked', rule_id=decision.rule_id, message=decision.message)
    full = Path(resolve_project_path(get_project_dir(), path))
    relative = full.relative_to(Path(get_project_dir()).resolve()).as_posix()
    if get_tool_policy().get('editing'):
        from tools.on_demand import _state
        state = _state.get() or {}
        plan = state.get('change_plan')
        scope = state.get('instruction_scope')
        if scope is not None and relative not in scope:
            raise EditRejected('outside_instruction_scope', path=path)
        if state.get('mode') == 'modify' and (not plan or relative not in plan.get('files', [])):
            raise EditRejected('outside_change_plan', path=path)
    if relative != path.replace('\\', '/'):
        canonical = evaluate_tool_action(ToolAction(tool_name=tool_name, project_dir=get_project_dir(),
            relative_path=relative, content=content, old_content=old_content, new_content=new_content, user_role=get_user_role()))
        if canonical.action == 'block':
            raise EditRejected('guardrail_blocked', rule_id=canonical.rule_id, message=canonical.message)
    return full


@contextmanager
def file_lock(path):
    root = Path(get_project_dir()).resolve()
    directory = root.parent / '.harness-edit-locks' / hashlib.sha256(str(root).encode()).hexdigest()[:24]
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = directory / (hashlib.sha256(str(path).encode()).hexdigest() + '.lock')
    with lock_path.open('a+b') as handle:
        if os.name == 'nt':
            import msvcrt
            handle.seek(0, 2)
            if handle.tell() == 0:
                handle.write(b'0'); handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == 'nt':
                handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def check_hash(raw, expected_hash):
    current = digest(raw)
    if expected_hash is not None and current != expected_hash:
        raise EditRejected('stale_hash', expected_hash=expected_hash, actual_hash=current,
                           next_action='read_file again; do not overwrite newer content')


def atomic_write(path, raw, original):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix='.harness-write-', suffix='.tmp', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(raw); handle.flush(); os.fsync(handle.fileno())
        os.chmod(temporary, (path.stat().st_mode & 0o777) if path.exists() else 0o644)
        current = path.read_bytes() if path.exists() else None
        if current != original:
            raise EditRejected('concurrent_file_change', actual_hash=digest(current))
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def result(path, before, after, *, matches=0, status='modified', **extra):
    return json.dumps({'ok': True, 'path': path, 'status': status, 'before_hash': digest(before),
                       'after_hash': digest(after), 'match_count': matches, **extra}, ensure_ascii=False)


def failure(exc):
    if isinstance(exc, EditRejected):
        return json.dumps({'ok': False, 'reason': exc.reason, **exc.details}, ensure_ascii=False)
    return json.dumps({'ok': False, 'reason': 'file_operation_failed', 'error': str(exc)}, ensure_ascii=False)


def replace_checked(original, old, new, *, mode='unique', expected_count=None):
    if not old:
        raise EditRejected('empty_match_rejected')
    count = original.count(old)
    if mode not in {'unique', 'all'}:
        raise EditRejected('invalid_replace_mode')
    if mode == 'all' and (expected_count is None or expected_count < 1):
        raise EditRejected('batch_requires_expected_count')
    required = 1 if mode == 'unique' else expected_count
    if expected_count is not None and mode == 'unique' and expected_count != 1:
        raise EditRejected('unique_requires_one_match')
    if count != required:
        raise EditRejected('ambiguous_match' if count > required else 'match_count_mismatch',
                           expected_count=required, actual_count=count, next_action='read_file/search_code to refine the exact text')
    return original.replace(old, new, count), count
