"""Seed record chunking helpers for long RAG seed entries."""

from __future__ import annotations

import re
from typing import Any

DEFAULT_MAX_CHARS = 1200


def chunk_text(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> list[str]:
    """Split text on paragraph boundaries, then hard-wrap oversized blocks."""
    cleaned = _normalize_text(text)
    if not cleaned:
        return []
    if len(cleaned) <= max_chars:
        return [cleaned]

    blocks = [block.strip() for block in re.split(r"\n\s*\n", cleaned) if block.strip()]
    if not blocks:
        return _wrap_by_lines(cleaned, max_chars)

    chunks: list[str] = []
    current_blocks: list[str] = []
    current_len = 0

    for block in blocks:
        if len(block) > max_chars:
            if current_blocks:
                chunks.append("\n\n".join(current_blocks))
                current_blocks = []
                current_len = 0
            chunks.extend(_wrap_by_lines(block, max_chars))
            continue

        separator_len = 2 if current_blocks else 0
        projected_len = current_len + separator_len + len(block)
        if current_blocks and projected_len > max_chars:
            chunks.append("\n\n".join(current_blocks))
            current_blocks = [block]
            current_len = len(block)
        else:
            if current_blocks:
                current_len += separator_len + len(block)
            else:
                current_len = len(block)
            current_blocks.append(block)

    if current_blocks:
        chunks.append("\n\n".join(current_blocks))

    return [chunk for chunk in chunks if chunk.strip()]


def expand_seed_record(
    item: dict[str, Any],
    name_field: str | None,
    content_field: str,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[dict[str, Any]]:
    """Expand a seed item into chunked records when the content is too long."""
    content = str(item.get(content_field, "") or "")
    chunks = chunk_text(content, max_chars=max_chars)
    if len(chunks) <= 1:
        return [dict(item)]

    base_name = str(item.get(name_field, "") or "") if name_field else ""
    total = len(chunks)
    records: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks, start=1):
        record = dict(item)
        record[content_field] = chunk
        if name_field and base_name:
            record[name_field] = f"{base_name} [part {index}/{total}]"
        records.append(record)
    return records


def _normalize_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _wrap_by_lines(text: str, max_chars: int) -> list[str]:
    lines = _normalize_text(text).split("\n")
    chunks: list[str] = []
    current_lines: list[str] = []
    current_len = 0

    for line in lines:
        line_len = len(line)
        separator_len = 1 if current_lines else 0
        if current_lines and current_len + separator_len + line_len > max_chars:
            chunks.append("\n".join(current_lines))
            current_lines = [line]
            current_len = line_len
        else:
            if current_lines:
                current_len += separator_len + line_len
            else:
                current_len = line_len
            current_lines.append(line)

    if current_lines:
        chunks.append("\n".join(current_lines))

    return [chunk for chunk in chunks if chunk.strip()]

