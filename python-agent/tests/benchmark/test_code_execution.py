from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

from benchmark.evaluators.code_execution import evaluate_code, materialize_files


def test_materialize_rejects_parent_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsafe generated path"):
        materialize_files([{"path": "../escape.py", "content": "x = 1"}], tmp_path)


@pytest.mark.parametrize("path", ["", "   ", ".", "C:/escape.py"])
def test_materialize_rejects_empty_or_absolute_paths(tmp_path: Path, path: str) -> None:
    with pytest.raises(ValueError, match="unsafe generated path"):
        materialize_files([{"path": path, "content": "x"}], tmp_path)


@pytest.mark.parametrize("path", ["a.txt.", "a.txt ", "dir./main.py", "dir /main.py"])
def test_materialize_rejects_windows_trailing_dot_or_space_aliases(tmp_path: Path, path: str) -> None:
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
        command=[sys.executable, "-m", "py_compile", "main.py"],
        timeout_seconds=10,
    )

    assert result["passed"] is False
    assert result["metric"] == "build_failed"
    assert result["infrastructure_error"] is None


def test_invalid_python_project_fixture_is_a_quality_failure(tmp_path: Path) -> None:
    fixture = Path(__file__).resolve().parents[2] / "benchmarks" / "fixtures" / "projects" / "invalid-python" / "main.py"
    result = evaluate_code(
        files=[{"path": "main.py", "content": fixture.read_text(encoding="utf-8")}],
        project_dir=tmp_path,
        command=[sys.executable, "-m", "py_compile", "main.py"],
        timeout_seconds=10,
    )

    assert result["passed"] is False
    assert result["metric"] == "build_failed"
    assert result["infrastructure_error"] is None


def test_valid_html_project_fixture_passes_offline_check(tmp_path: Path) -> None:
    fixture = Path(__file__).resolve().parents[2] / "benchmarks" / "fixtures" / "projects" / "valid-html" / "index.html"
    result = evaluate_code(
        files=[{"path": "index.html", "content": fixture.read_text(encoding="utf-8")}],
        project_dir=tmp_path,
        command=[
            sys.executable,
            "-c",
            "from pathlib import Path; text = Path('index.html').read_text(encoding='utf-8'); "
            "raise SystemExit(0 if 'benchmark-ready' in text else 1)",
        ],
        timeout_seconds=10,
    )

    assert result["passed"] is True
    assert result["metric"] == "build_success"
    assert result["infrastructure_error"] is None


def test_missing_tool_is_infrastructure_error(tmp_path: Path) -> None:
    result = evaluate_code(
        files=[{"path": "main.py", "content": "x = 1\n"}],
        project_dir=tmp_path,
        command=["definitely-missing-benchmark-tool"],
        timeout_seconds=10,
    )

    assert result["infrastructure_error"]
    assert result["passed"] is False


def test_timeout_terminates_the_entire_process_tree_before_a_child_can_write(tmp_path: Path) -> None:
    marker = tmp_path / "child-marker.txt"
    child = "import pathlib,sys,time; time.sleep(2.5); pathlib.Path(sys.argv[1]).write_text('escaped')"
    launcher = (
        "import subprocess,sys,time; "
        "subprocess.Popen([sys.executable, '-c', " + repr(child) + ", sys.argv[1]]); "
        "time.sleep(30)"
    )
    started = time.monotonic()

    result = evaluate_code(
        files=[{"path": "launcher.py", "content": launcher}],
        project_dir=tmp_path / "project",
        command=[sys.executable, "launcher.py", str(marker)],
        timeout_seconds=1,
    )
    elapsed = time.monotonic() - started
    time.sleep(2.75)

    assert result["infrastructure_error"] == "code execution timed out after 1 seconds"
    assert elapsed < 2.25
    assert not marker.exists()


def test_execution_uses_explicit_environment_allowlist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BENCHMARK_TEST_SECRET", "must-not-leak")
    result = evaluate_code(
        files=[{"path": "main.py", "content": "x = 1\n"}],
        project_dir=tmp_path,
        command=[sys.executable, "-c", "import os; print(os.getenv('BENCHMARK_TEST_SECRET', 'clean'))"],
        timeout_seconds=10,
    )

    assert result["passed"] is True
    assert "clean" in result["log"]
    assert "must-not-leak" not in result["log"]


def test_execution_redacts_and_limits_logs(tmp_path: Path) -> None:
    result = evaluate_code(
        files=[{"path": "main.py", "content": "x = 1\n"}],
        project_dir=tmp_path,
        command=[sys.executable, "-c", "print('password=hunter2 ' + 'x' * 10000)"],
        timeout_seconds=10,
    )

    assert "hunter2" not in result["log"]
    assert "***REDACTED***" in result["log"]
    assert len(result["log"]) <= 4000


@pytest.mark.parametrize(
    ("command", "timeout"),
    [([], 10), ([""], 10), ([sys.executable, 1], 10), ([sys.executable], 0), ([sys.executable], 601)],
)
def test_execution_rejects_invalid_command_or_timeout(
    tmp_path: Path, command: list[object], timeout: int
) -> None:
    with pytest.raises(ValueError):
        evaluate_code(
            files=[{"path": "main.py", "content": "x = 1\n"}],
            project_dir=tmp_path,
            command=command,  # type: ignore[arg-type]
            timeout_seconds=timeout,
        )
