"""Bounded, lossless review units plus inexpensive whole-project checks."""
from __future__ import annotations

import ast
import posixpath
import re


def review_units(files: list[dict], max_chars: int = 10000) -> list[dict]:
    units = []
    for file in files:
        content = file.get("content", "")
        lines = content.splitlines(keepends=True)
        start, buffer, size = 1, [], 0
        for number, line in enumerate(lines, 1):
            boundary = re.match(r"\s*(?:async def |def |class |export |function |<(?:template|script|style))", line)
            if buffer and (size + len(line) > max_chars or (boundary and size > max_chars // 2)):
                units.append({"file": file["path"], "start": start, "end": number - 1,
                              "content": "".join(buffer)})
                start, buffer, size = number, [], 0
            # A minified line can itself exceed the context budget.
            while len(line) > max_chars:
                if buffer:
                    units.append({"file": file["path"], "start": start, "end": number,
                                  "content": "".join(buffer)})
                    buffer, size = [], 0
                units.append({"file": file["path"], "start": number, "end": number,
                              "content": line[:max_chars]})
                line, start = line[max_chars:], number
            buffer.append(line)
            size += len(line)
        if buffer or not content:
            units.append({"file": file["path"], "start": start, "end": max(start, len(lines)),
                          "content": "".join(buffer)})
    return units


def dependency_manifest(files: list[dict]) -> str:
    return "\n".join(f"{f['path']}: " + " | ".join(
        line.strip() for line in f.get("content", "").splitlines()
        if re.match(r"\s*(?:import |from |export .*from)", line)
    ) for f in files)


def static_issues(files: list[dict]) -> list[dict]:
    paths = {f["path"] for f in files}
    issues = []
    def add(path, line, description):
        issues.append({"file": path, "line": line, "severity": "critical", "category": "syntax",
                       "description": description, "suggestion": "修复该位置并重新验证"})
    for file in files:
        path, content = file["path"], file.get("content", "")
        if path.endswith(".py"):
            try:
                ast.parse(content, filename=path)
            except SyntaxError as exc:
                add(path, exc.lineno, str(exc))
        if path.endswith((".vue", ".js", ".ts", ".jsx", ".tsx")):
            for match in re.finditer(r"(?:from\s*|import\s*\()\s*['\"]([.@][^'\"]+)['\"]", content):
                name = match.group(1).split("?")[0]
                if name.startswith("@/"):
                    target = "src/" + name[2:]
                elif name.startswith("."):
                    target = posixpath.normpath(posixpath.join(posixpath.dirname(path), name))
                else:
                    continue
                options = {target} | {target + ext for ext in (".ts", ".js", ".vue", ".tsx", ".jsx", ".json")}
                options |= {target + "/index" + ext for ext in (".ts", ".js", ".vue")}
                if not paths.intersection(options):
                    add(path, content[:match.start()].count("\n") + 1, f"本地引用不存在: {name}")
    return issues
