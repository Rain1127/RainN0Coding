from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from benchmark.redaction import redact_error


SAFE_ENV_KEYS = ("PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "TEMP", "TMP")
MAX_LOG_CHARACTERS = 4000
MAX_TIMEOUT_SECONDS = 600


def _relative_generated_path(raw_path: object) -> Path:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError(f"unsafe generated path: {raw_path!r}")
    relative = Path(raw_path)
    if (
        not relative.parts
        or relative.is_absolute()
        or bool(relative.drive)
        or any(part in {"", ".", ".."} for part in relative.parts)
        or relative.is_reserved()
    ):
        raise ValueError(f"unsafe generated path: {raw_path}")
    return relative


def validate_generated_files(files: object) -> list[tuple[Path, str]]:
    if not isinstance(files, list):
        raise ValueError("generated files must be a list")

    validated: list[tuple[Path, str]] = []
    logical_paths: set[str] = set()
    for item in files:
        if not isinstance(item, Mapping) or set(item) != {"path", "content"}:
            raise ValueError("generated file must contain exactly path and content strings")
        if not isinstance(item["path"], str):
            raise ValueError("generated file must contain exactly path and content strings")
        relative = _relative_generated_path(item["path"])
        content = item["content"]
        if not isinstance(content, str):
            raise ValueError("generated file must contain exactly path and content strings")
        logical = os.path.normcase(str(relative))
        if logical in logical_paths:
            raise ValueError(f"generated path collision: {relative}")
        for prior in logical_paths:
            if logical.startswith(prior + os.sep) or prior.startswith(logical + os.sep):
                raise ValueError(f"generated path collision: {relative}")
        logical_paths.add(logical)
        validated.append((relative, content))
    return validated


def _confined(path: Path, root: Path, relative: Path) -> Path:
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"unsafe generated path: {relative}") from exc
    return resolved


def materialize_files(files: list[dict[str, Any]], project_dir: str | Path) -> list[Path]:
    validated = validate_generated_files(files)
    root_path = Path(project_dir)
    root_path.mkdir(parents=True, exist_ok=True)
    root = root_path.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("project_dir must be a directory")

    targets: list[tuple[Path, Path, str]] = []
    canonical_targets: set[str] = set()
    for relative, content in validated:
        target = _confined(root / relative, root, relative)
        canonical = os.path.normcase(str(target))
        if canonical in canonical_targets:
            raise ValueError(f"generated path collision: {relative}")
        for prior in canonical_targets:
            if canonical.startswith(prior + os.sep) or prior.startswith(canonical + os.sep):
                raise ValueError(f"generated path collision: {relative}")
        canonical_targets.add(canonical)
        targets.append((relative, target, content))

    written: list[Path] = []
    for relative, target, content in targets:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except (FileExistsError, NotADirectoryError) as exc:
            raise ValueError(f"generated path collision: {relative}") from exc
        _confined(target.parent, root, relative)
        target = _confined(target, root, relative)
        if target.exists() and (target.is_dir() or target.is_symlink()):
            raise ValueError(f"generated path collision: {relative}")
        target.write_text(content, encoding="utf-8")
        _confined(target, root, relative)
        written.append(target)
    return written


def _validate_execution(command: object, timeout_seconds: object) -> tuple[list[str], int]:
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(item, str) and item.strip() for item in command)
    ):
        raise ValueError("execution command must be a non-empty string list")
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, int)
        or not 1 <= timeout_seconds <= MAX_TIMEOUT_SECONDS
    ):
        raise ValueError(f"timeout_seconds must be between 1 and {MAX_TIMEOUT_SECONDS}")
    return list(command), timeout_seconds


def evaluate_code(
    files: list[dict[str, Any]],
    project_dir: str | Path,
    command: list[str],
    timeout_seconds: int,
) -> dict[str, Any]:
    safe_command, safe_timeout = _validate_execution(command, timeout_seconds)
    materialize_files(files, project_dir)
    environment = {key: os.environ[key] for key in SAFE_ENV_KEYS if key in os.environ}
    environment.update({"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
    try:
        completed = subprocess.run(
            safe_command,
            cwd=Path(project_dir).resolve(),
            shell=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=safe_timeout,
            env=environment,
            check=False,
        )
    except FileNotFoundError:
        return {
            "passed": False,
            "metric": "build_failed",
            "log": "",
            "infrastructure_error": "code execution tool was not found",
        }
    except subprocess.TimeoutExpired:
        return {
            "passed": False,
            "metric": "build_failed",
            "log": "",
            "infrastructure_error": f"code execution timed out after {safe_timeout} seconds",
        }
    except OSError as exc:
        return {
            "passed": False,
            "metric": "build_failed",
            "log": "",
            "infrastructure_error": redact_error(f"code execution OS error {exc.errno or 'unknown'}"),
        }

    combined = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    redacted_log = redact_error(combined)
    if len(redacted_log) > MAX_LOG_CHARACTERS:
        half = MAX_LOG_CHARACTERS // 2
        log = redacted_log[:half] + redacted_log[-half:]
    else:
        log = redacted_log
    passed = completed.returncode == 0
    return {
        "passed": passed,
        "metric": "build_success" if passed else "build_failed",
        "log": log,
        "infrastructure_error": None,
    }
