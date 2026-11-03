from pathlib import Path

import pytest

from agents.mode_detector import mode_detector, _detect_language_signal
from workflow.artifacts import publish, recover, _atomic_json


@pytest.mark.parametrize("prompt", ["不要重新生成，只改颜色", "不用重做，修复按钮", "无需重新生成", "别覆盖原代码", "不重新生成，只修复", "[最近对话] 用户: 重新生成\n[当前请求] 修改颜色"])
def test_negated_rebuild_is_not_a_rebuild(prompt):
    assert _detect_language_signal(prompt) != "rebuild"


def test_rebuild_failure_and_pause_preserve_current(tmp_path):
    current = tmp_path / "html_1"
    current.mkdir()
    (current / "index.html").write_text("old", encoding="utf-8")
    state = mode_detector({"project_dir": str(current), "user_request": "重新生成"})
    candidate = Path(state["project_dir"])
    assert candidate != current
    (candidate / "index.html").write_text("new", encoding="utf-8")
    assert (current / "index.html").read_text() == "old"
    published = publish(state)
    assert (current / "index.html").read_text() == "new"
    assert (Path(published["previous_project_dir"]) / "index.html").read_text() == "old"


def test_crash_during_swap_recovers_previous(tmp_path):
    current = tmp_path / "html_1"
    current.mkdir()
    (current / "index.html").write_text("old")
    state = mode_detector({"project_dir": str(current), "user_request": "重新生成"})
    candidate = Path(state["project_dir"])
    backup = candidate.parent / (state["artifact_run_id"] + ".previous")
    _atomic_json(candidate.parent / "publishing.json", {"backup": backup.name, "candidate": candidate.name})
    current.rename(backup)
    recover(current)
    assert (current / "index.html").read_text() == "old"
    assert candidate.exists()


def test_reject_lost_update(tmp_path):
    current = tmp_path / "html_1"
    current.mkdir()
    (current / "index.html").write_text("old")
    state = mode_detector({"project_dir": str(current), "user_request": "修改颜色"})
    (current / "index.html").write_text("other-run")
    with pytest.raises(ValueError, match="changed"):
        publish(state)
    assert (current / "index.html").read_text() == "other-run"
