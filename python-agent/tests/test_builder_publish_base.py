import pytest

from agents.builder_agent import builder_agent
from workflow.execution import ExecutionResult


@pytest.mark.parametrize("kind, expected", [
    ("vue_project", ["npm", "run", "build", "--", "--base=./"]),
    ("nodejs", ["npm", "run", "build"]),
])
def test_build_supports_subdirectory_without_changing_node_backend(tmp_path, monkeypatch, kind, expected):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return ExecutionResult('succeeded', None, 0, 'ok', 0, 'local')

    monkeypatch.setattr("workflow.execution.process_result", run)
    result = builder_agent({
        "code_gen_type": kind, "project_dir": str(tmp_path),
        "code_files": [{"path": "index.html", "content": "<html></html>"}],
        "review": {"score": 90, "passed": True, "issues": []},
    })
    assert result["build_result"]["success"]
    assert calls[1][1:] == expected[1:]
    assert "npm" in calls[1][0].lower()


@pytest.mark.parametrize("kind, mode", [("html", "modify"), ("multi_file", "new")])
def test_static_page_does_not_get_shadowed_by_vue_scaffold(tmp_path, kind, mode):
    nested = tmp_path / "src" / "index.html"
    nested.parent.mkdir()
    nested.write_text("<html><body>generated static content</body></html>", encoding="utf-8")
    result = builder_agent({
        "code_gen_type": kind, "mode": mode, "project_dir": str(tmp_path),
        "code_files": [{"path": "src/index.html", "content": nested.read_text(encoding="utf-8")}],
        "review": {"score": 90, "passed": True, "issues": []},
    })
    assert result["build_result"]["status"] == "not_required"
    assert result["build_result"]["success"] is None
    assert "generated static content" in nested.read_text(encoding="utf-8")
    assert not (tmp_path / "index.html").exists(), "A Vue shell shadows the actual static page"
    assert not (tmp_path / "package.json").exists()
