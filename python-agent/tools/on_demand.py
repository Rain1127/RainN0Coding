"""Read-only project search and attributed retrieval for Coder's current need."""
from contextvars import ContextVar
from pathlib import Path
import hashlib
import json
import os
from langchain_core.tools import tool
from tools.context import get_project_dir, get_user_role
from tools.path_guard import resolve_project_path
from tools.guard import check_tool_permission
from guardrails.engine import evaluate_tool_action
from guardrails.models import ToolAction

_state = ContextVar('coder_retrieval_state', default=None)
EXCLUDED = {'.git', 'node_modules', '.venv', 'dist', '__pycache__'}


def set_coder_state(state):
    _state.set(state)


@tool
def search_code(query: str, path: str = '', max_results: int = 30) -> str:
    """Search literal text inside project files. Return file/line locations; read_file supports ranges and offsets."""
    if not query or len(query) > 500 or not 1 <= max_results <= 100:
        return json.dumps({'ok': False, 'reason': 'invalid_search_arguments'})
    try:
        root = Path(resolve_project_path(get_project_dir(), path))
        if not check_tool_permission('search_code'):
            return json.dumps({'ok': False, 'reason': 'permission_denied'})
        def project_files():
            if root.is_file():
                yield root
                return
            for directory, dirs, names in os.walk(root):
                dirs[:] = sorted(d for d in dirs if d not in EXCLUDED and not Path(directory, d).is_symlink())
                for name in sorted(names):
                    yield Path(directory, name)
        files = project_files()
        matches = []
        scanned = 0
        for file in files:
            if not file.is_file() or file.is_symlink() or any(p in EXCLUDED for p in file.relative_to(Path(get_project_dir())).parts):
                continue
            if file.stat().st_size > 2_000_000:
                continue
            relative = file.relative_to(Path(get_project_dir())).as_posix()
            if evaluate_tool_action(ToolAction(tool_name='read_file', project_dir=get_project_dir(),
                    relative_path=relative, user_role=get_user_role())).action == 'block':
                continue
            scanned += 1
            if scanned > 500:
                return json.dumps({'ok': True, 'matches': matches, 'truncated': True, 'reason': 'file_scan_limit; narrow path'})
            try:
                content = file.read_text(encoding='utf-8')
            except (UnicodeError, OSError):
                continue
            for line, text in enumerate(content.splitlines(), 1):
                if query in text:
                    matches.append({'path': file.relative_to(Path(get_project_dir())).as_posix(), 'line': line,
                                    'excerpt': text[:600], 'excerpt_truncated': len(text) > 600})
                    if len(matches) >= max_results:
                        return json.dumps({'ok': True, 'matches': matches, 'truncated': True, 'reason': 'result_limit; narrow path or read ranges'}, ensure_ascii=False)
        return json.dumps({'ok': True, 'matches': matches, 'truncated': False}, ensure_ascii=False)
    except (ValueError, OSError) as exc:
        return json.dumps({'ok': False, 'reason': str(exc)}, ensure_ascii=False)


@tool
def retrieve_context(query: str, target_file: str = '', offset: int = 0, limit: int = 6000) -> str:
    """Retrieve references for one current file/error/feature; use only when needed, not every architecture file."""
    state = _state.get()
    if not check_tool_permission('retrieve_context') or not state or not query or len(query) > 2000 or offset < 0 or not 1 <= limit <= 12000:
        return json.dumps({'ok': False, 'reason': 'missing_retrieval_context_or_query'})
    if target_file:
        try:
            resolve_project_path(get_project_dir(), target_file)
        except ValueError as exc:
            return json.dumps({'ok': False, 'reason': str(exc)})
    key = hashlib.sha256((query + '\n' + target_file).encode()).hexdigest()
    cache = state.setdefault('_retrieval_cache', {})
    if key not in cache:
        from rag.rag_builder import build_rag_context
        from rag.feedback_tracker import attribution_scope
        with attribution_scope(state.get('artifact_run_id', ''), target_file):
            cache[key] = build_rag_context({'path': target_file, 'description': query}, state.get('architecture') or {},
                phase=state.get('phase', 'code'), user_request=query, retry_count=state.get('retry_count', 0),
                code_gen_type=state.get('code_gen_type', 'vue_project'), app_id=state.get('app_id', ''))
        state.setdefault('retrieval_events', []).append({'query': query, 'target_file': target_file,
            'run_id': state.get('artifact_run_id'), 'sha256': hashlib.sha256(cache[key].encode()).hexdigest()})
    result = cache[key]
    text = result[offset:offset + limit]
    return json.dumps({'ok': True, 'context': text, 'source': 'existing attributed RAG pipeline',
                       'offset': offset, 'next_offset': offset + len(text) if offset + len(text) < len(result) else None,
                       'truncated': offset + len(text) < len(result)}, ensure_ascii=False)


@tool
def read_progress(reference: str, offset: int = 0, limit: int = 6000) -> str:
    """Read a previous context snapshot using an exact reference from the handoff. File contents still require read_file."""
    state = _state.get() or {}
    allowed = {item['raw_reference'] for item in state.get('context_report', {}).get('requests', [])}
    if not check_tool_permission('read_progress') or reference not in allowed or offset < 0 or not 1 <= limit <= 12000:
        return json.dumps({'ok': False, 'reason': 'progress_reference_denied'})
    try:
        text = Path(reference).read_text(encoding='utf-8')
        part = text[offset:offset + limit]
        return json.dumps({'ok': True, 'content': part, 'next_offset': offset + len(part) if offset + len(part) < len(text) else None}, ensure_ascii=False)
    except OSError:
        return json.dumps({'ok': False, 'reason': 'progress_record_unavailable'})
