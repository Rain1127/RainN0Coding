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
