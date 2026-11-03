"""Validate every context hunk before one atomic replacement."""
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from tools.file_edit import authorize, file_lock, check_hash, atomic_write, result, failure, replace_checked, EditRejected


class PatchHunk(BaseModel):
    old_content: str = Field(min_length=1)
    new_content: str
    context_before: str = ''
    context_after: str = ''


@tool
def apply_patch(path: str, hunks: list[PatchHunk], expected_hash: str) -> str:
    """Apply ordered exact context hunks to one file. Requires read_file.sha256. Any mismatch leaves the whole original file unchanged."""
    try:
        if not hunks or len(hunks) > 50 or not expected_hash:
            raise EditRejected('invalid_patch_hunks_or_hash')
        full = authorize('apply_patch', path, new_content=''.join(h.new_content for h in hunks))
        authorize('modify_file', path, new_content=''.join(h.new_content for h in hunks))
        with file_lock(full):
            if not full.is_file():
                raise EditRejected('file_not_found')
            raw = full.read_bytes()
            check_hash(raw, expected_hash)
            modified = raw.decode('utf-8')
            for hunk in hunks:
                old = hunk.context_before + hunk.old_content + hunk.context_after
                new = hunk.context_before + hunk.new_content + hunk.context_after
                modified, _ = replace_checked(modified, old, new)
            updated = modified.encode('utf-8')
            if updated != raw:
                atomic_write(full, updated, raw)
            return result(path, raw, updated, matches=len(hunks), status='modified' if updated != raw else 'unchanged')
    except Exception as exc:
        return failure(exc)
