"""Shared path guard for project file tools."""

import os


def resolve_project_path(project_dir: str, path: str = "") -> str:
    """Resolve a user-supplied path and keep it inside project_dir."""
    if not project_dir:
        raise ValueError("project_dir is empty")

    project_root = os.path.realpath(project_dir)
    candidate = os.path.realpath(os.path.join(project_root, path or ""))

    if os.path.commonpath([project_root, candidate]) != project_root:
        raise ValueError(f"path escapes project directory: {path}")

    return candidate
