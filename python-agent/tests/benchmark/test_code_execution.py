from __future__ import annotations

import os
from pathlib import Path

import pytest

from benchmark.evaluators.code_execution import evaluate_code, materialize_files


pytestmark = pytest.mark.benchmark

def test_materialize_rejects_parent_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsafe generated path"):
        materialize_files([{"path": "../escape.py", "content": "x = 1"}], tmp_path)


@pytest.mark.parametrize("path", ["", "   ", ".", "C:/escape.py"])
def test_materialize_rejects_empty_or_absolute_paths(tmp_path: Path, path: str) -> None:
    with pytest.raises(ValueError, match="unsafe generated path"):
        materialize_files([{"path": path, "content": "x"}], tmp_path)


@pytest.mark.parametrize(
    "path",
    [
        "a.txt.",
        "a.txt ",
        "dir./main.py",
        "dir /main.py",
        "a.txt:stream",
        "bad?.py",
        "nested/CON.txt",
        "nested/lpt9.log",
        "control\x01.py",
        "nul\x00.py",
    ],
)
def test_materialize_rejects_windows_unsafe_components_on_every_platform(tmp_path: Path, path: str) -> None:
    with pytest.raises(ValueError, match="unsafe generated path"):
        materialize_files([{"path": path, "content": "x"}], tmp_path)


def test_materialize_refuses_to_overwrite_an_existing_regular_file(tmp_path: Path) -> None:
    target = tmp_path / "main.py"
    target.write_text("original", encoding="utf-8")

    with pytest.raises(ValueError, match="generated path collision"):
        materialize_files([{"path": "main.py", "content": "replacement"}], tmp_path)

    assert target.read_text(encoding="utf-8") == "original"


def test_materialize_refuses_to_write_through_an_existing_hardlink(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("outside-original", encoding="utf-8")
    link = tmp_path / "main.py"
    try:
        os.link(outside, link)
    except OSError:
        pytest.skip("hardlink creation is unavailable on this platform")

    with pytest.raises(ValueError, match="generated path collision"):
        materialize_files([{"path": "main.py", "content": "replacement"}], tmp_path)

    assert outside.read_text(encoding="utf-8") == "outside-original"


@pytest.mark.parametrize(
    "files",
    [
        "not-a-list",
        ["not-an-object"],
        [{"path": "main.py"}],
        [{"path": 123, "content": "x"}],
        [{"path": "main.py", "content": 123}],
        [{"path": "main.py", "content": "x", "language": "python"}],
    ],
)
def test_materialize_requires_strict_file_schema(tmp_path: Path, files: object) -> None:
    with pytest.raises(ValueError, match="generated files|generated file"):
        materialize_files(files, tmp_path)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "files",
    [
        [{"path": "app", "content": "file"}, {"path": "app/main.py", "content": "child"}],
        [{"path": "app/main.py", "content": "child"}, {"path": "app", "content": "file"}],
        [{"path": "main.py", "content": "one"}, {"path": "main.py", "content": "two"}],
    ],
)
def test_materialize_rejects_file_directory_and_duplicate_collisions(tmp_path: Path, files: list[dict]) -> None:
    with pytest.raises(ValueError, match="generated path collision"):
        materialize_files(files, tmp_path)


def test_materialize_rejects_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    link = tmp_path / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is unavailable on this platform")

    with pytest.raises(ValueError, match="unsafe generated path"):
        materialize_files([{"path": "linked/escape.py", "content": "x"}], tmp_path)
    assert not (outside / "escape.py").exists()


def test_python_syntax_failure_is_a_quality_failure(tmp_path: Path) -> None:
    result = evaluate_code(
        files=[{"path": "main.py", "content": "def broken(:\n"}],
        project_dir=tmp_path,
        execution_profile="python_syntax",
    )

    assert result["passed"] is False
    assert result["metric"] == "build_failed"
    assert result["infrastructure_error"] is None


def test_invalid_python_project_fixture_is_a_quality_failure(tmp_path: Path) -> None:
    fixture = Path(__file__).resolve().parents[2] / "benchmarks" / "fixtures" / "projects" / "invalid-python" / "main.py"
    result = evaluate_code(
        files=[{"path": "main.py", "content": fixture.read_text(encoding="utf-8")}],
        project_dir=tmp_path,
        execution_profile="python_syntax",
    )

    assert result["passed"] is False
    assert result["metric"] == "build_failed"
    assert result["infrastructure_error"] is None


def test_valid_html_project_fixture_passes_offline_check(tmp_path: Path) -> None:
    fixture = Path(__file__).resolve().parents[2] / "benchmarks" / "fixtures" / "projects" / "valid-html" / "index.html"
    result = evaluate_code(
        files=[{"path": "index.html", "content": fixture.read_text(encoding="utf-8")}],
        project_dir=tmp_path,
        execution_profile="static_html",
    )

    assert result["passed"] is True
    assert result["metric"] == "build_success"
    assert result["infrastructure_error"] is None


def test_python_syntax_profile_never_executes_generated_code(tmp_path: Path) -> None:
    marker = tmp_path / "must-not-exist.txt"
    source = f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n"
    result = evaluate_code(
        files=[{"path": "main.py", "content": source}],
        project_dir=tmp_path / "project",
        execution_profile="python_syntax",
    )

    assert result["passed"] is True
    assert not marker.exists()


@pytest.mark.parametrize(
    ("profile", "files"),
    [
        ("python_syntax", [{"path": "index.html", "content": "<main>ok</main>"}]),
        ("static_html", [{"path": "main.py", "content": "x = 1\n"}]),
    ],
)
def test_profiles_require_a_matching_generated_file(
    tmp_path: Path, profile: str, files: list[dict[str, str]]
) -> None:
    result = evaluate_code(files=files, project_dir=tmp_path, execution_profile=profile)

    assert result["passed"] is False
    assert result["metric"] == "build_failed"
    assert result["infrastructure_error"] is None


def test_evaluator_rejects_unknown_execution_profile(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown execution profile"):
        evaluate_code(
            files=[{"path": "main.py", "content": "x = 1\n"}],
            project_dir=tmp_path,
            execution_profile="arbitrary-command",
        )
