import importlib

from agents.review_context import review_units, static_issues
reviewer = importlib.import_module("agents.reviewer_agent")


def test_lossless_chunks_cover_tail_and_minified_line():
    text = "# comment\n" * 1200 + "def bad(:\n"
    files = [{"path": "main.py", "content": text}, {"path": "long.js", "content": "a" * 30001}]
    units = review_units(files, 1000)
    for file in files:
        assert "".join(u["content"] for u in units if u["file"] == file["path"]) == file["content"]
    assert all(len(u["content"]) <= 1000 for u in units)
    assert static_issues(files)[0]["line"] == 1201


def test_static_checks_beginning_tail_and_cross_file():
    issues = static_issues([
        {"path": "start.py", "content": "if True\n    pass"},
        {"path": "tail.py", "content": "# padding\n" * 600 + "if True\n    pass"},
        {"path": "src/App.vue", "content": "import View from './Missing.vue'"},
    ])
    assert {i["file"] for i in issues} == {"start.py", "tail.py", "src/App.vue"}
    assert issues[1]["line"] == 601


def test_reviewer_does_not_claim_uncovered_code_passed(tmp_path, monkeypatch):
    monkeypatch.setattr(reviewer.config, "REVIEW_MAX_CALLS", 1, raising=False)
    monkeypatch.setattr(reviewer, "create_json_parser", lambda *a, **k:
                        lambda *a, **k: reviewer.ReviewResult(passed=True, score=95))
    state = reviewer.reviewer_agent({"project_dir": str(tmp_path), "code_gen_type": "python",
        "code_files": [{"path": "a.py", "content": "# filler\n" * 2000}]})
    assert state["review"]["passed"] is False
    assert state["review_coverage"]["uncovered"]
    assert state["review_coverage"]["tokens"] is None
