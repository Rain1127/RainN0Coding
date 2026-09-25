from __future__ import annotations

import ast
import os
from collections.abc import Callable, Mapping
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


_WINDOWS_FORBIDDEN_CHARACTERS = frozenset('<>:"|?*')
_WINDOWS_RESERVED_BASENAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)


def normalize_generated_path(raw_path: object) -> Path:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError(f"unsafe generated path: {raw_path!r}")
    components = raw_path.replace("\\", "/").split("/")
    for component in components:
        basename = component.split(".", 1)[0].rstrip(" .").upper()
        if (
            component in {"", ".", ".."}
            or component.rstrip(" .") != component
            or any(ord(character) < 32 for character in component)
            or any(character in _WINDOWS_FORBIDDEN_CHARACTERS for character in component)
            or basename in _WINDOWS_RESERVED_BASENAMES
        ):
            raise ValueError(f"unsafe generated path: {raw_path}")
    return Path(*components)


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
        relative = normalize_generated_path(item["path"])
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
        if target.exists() or target.is_symlink():
            raise ValueError(f"generated path collision: {relative}")
        try:
            with target.open("x", encoding="utf-8") as stream:
                stream.write(content)
        except FileExistsError as exc:
            raise ValueError(f"generated path collision: {relative}") from exc
        _confined(target, root, relative)
        written.append(target)
    return written


def _quality_result(passed: bool, log: str) -> dict[str, Any]:
    return {
        "passed": passed,
        "metric": "build_success" if passed else "build_failed",
        "log": log,
        "infrastructure_error": None,
    }


def _python_syntax(paths: list[Path]) -> dict[str, Any]:
    python_files = [path for path in paths if path.suffix.lower() == ".py"]
    if not python_files:
        return _quality_result(False, "python_syntax requires at least one .py file")
    for path in python_files:
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
        except (OSError, UnicodeDecodeError) as exc:
            raise ValueError(f"failed to read generated Python file: {path.name}") from exc
        except SyntaxError as exc:
            location = f"line {exc.lineno}" if exc.lineno is not None else "unknown line"
            return _quality_result(
                False,
                f"invalid Python syntax in {path.name} at {location}: {exc.msg}",
            )
    return _quality_result(True, f"parsed {len(python_files)} Python file(s) without execution")


class _StaticHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.saw_tag = False

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        del tag, attrs
        self.saw_tag = True

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        del tag, attrs
        self.saw_tag = True


def _static_html(paths: list[Path]) -> dict[str, Any]:
    html_files = [path for path in paths if path.suffix.lower() in {".html", ".htm"}]
    if not html_files:
        return _quality_result(False, "static_html requires at least one .html or .htm file")
    for path in html_files:
        parser = _StaticHTMLParser()
        try:
            parser.feed(path.read_text(encoding="utf-8"))
            parser.close()
        except (OSError, UnicodeDecodeError) as exc:
            raise ValueError(f"failed to read generated HTML file: {path.name}") from exc
        if not parser.saw_tag:
            return _quality_result(False, f"generated HTML file contains no elements: {path.name}")
    return _quality_result(True, f"parsed {len(html_files)} HTML file(s) without execution")


_PROFILE_EVALUATORS: dict[str, Callable[[list[Path]], dict[str, Any]]] = {
    "python_syntax": _python_syntax,
    "static_html": _static_html,
}
EXECUTION_PROFILES = frozenset(_PROFILE_EVALUATORS)


def evaluate_code(
    *,
    files: list[dict[str, Any]],
    project_dir: str | Path,
    execution_profile: str,
) -> dict[str, Any]:
    """Run an evaluator-owned, non-executing static profile over generated files."""
    evaluator = _PROFILE_EVALUATORS.get(execution_profile)
    if evaluator is None:
        raise ValueError(f"unknown execution profile: {execution_profile!r}")
    paths = materialize_files(files, project_dir)
    return evaluator(paths)
