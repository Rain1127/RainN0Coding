from types import SimpleNamespace

import pytest

from agents.builder_agent import builder_agent


@pytest.mark.parametrize("kind, expected", [
    ("vue_project", ["npm", "run", "build", "--", "--base=./"]),
    ("nodejs", ["npm", "run", "build"]),
])
def test_build_supports_subdirectory_without_changing_node_backend(tmp_path, monkeypatch, kind, expected):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("agents.builder_agent.subprocess.run", run)
    result = builder_agent({
        "code_gen_type": kind, "project_dir": str(tmp_path),
        "code_files": [{"path": "index.html", "content": "<html></html>"}],
        "review": {"score": 90, "passed": True, "issues": []},
    })
    assert result["build_result"]["success"]
    assert calls[1] == expected


@pytest.mark.parametrize("kind", ["html", "multi_file"])
def test_static_page_does_not_get_shadowed_by_vue_scaffold(tmp_path, monkeypatch, kind):
    nested = tmp_path / "src" / "index.html"
    nested.parent.mkdir()
    nested.write_text("<html><body>generated static content</body></html>", encoding="utf-8")
    monkeypatch.setattr("agents.builder_agent.subprocess.run", lambda *a, **k:
                        SimpleNamespace(returncode=0, stdout="ok", stderr=""))
    result = builder_agent({
        "code_gen_type": kind, "project_dir": str(tmp_path),
        "code_files": [{"path": "src/index.html", "content": nested.read_text(encoding="utf-8")}],
        "review": {"score": 90, "passed": True, "issues": []},
    })
    assert result["build_result"]["success"]
    assert "generated static content" in nested.read_text(encoding="utf-8")
    assert not (tmp_path / "index.html").exists(), "A Vue shell shadows the actual static page"
    assert not (tmp_path / "package.json").exists()
