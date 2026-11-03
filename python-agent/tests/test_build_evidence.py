import importlib
from unittest.mock import Mock

import pytest

builder = importlib.import_module("agents.builder_agent")
from workflow.resilience import finalize_state
from workflow.execution import ExecutionResult


@pytest.mark.parametrize("outcome,status,kind", [
    ("ok", "succeeded", None), ("code", "failed", "code"),
    ("missing", "unverified", "environment"), ("timeout", "failed", "timeout"),
    ("dependency", "failed", "dependency"),
])
def test_build_evidence_is_not_fabricated(tmp_path, monkeypatch, outcome, status, kind):
    def run(cmd, **kwargs):
        if outcome == "missing":
            return ExecutionResult('unverified', 'environment', None, 'npm missing', 0, 'local')
        if outcome == "timeout":
            return ExecutionResult('failed', 'timeout', None, 'npm timed out', 0, 'local')
        failed = outcome == "dependency" or (outcome == "code" and "build" in cmd)
        return ExecutionResult('failed' if failed else 'succeeded', kwargs['failure'] if failed else None,
                               int(failed), 'src/App.vue:42 error' if failed else 'ok', 0, 'local')
    monkeypatch.setattr("workflow.execution.process_result", run)
    index = Mock()
    feedback = Mock()
    monkeypatch.setattr("rag.rag_builder.index_code_files", index)
    monkeypatch.setattr("rag.feedback_tracker.feedback_tracker.apply_feedback", feedback)
    state = builder.builder_agent({
        "app_id": "evidence", "code_gen_type": "vue_project", "project_dir": str(tmp_path),
        "code_files": [{"path": "src/App.vue", "content": "<template>ok</template>"}],
        "review": {"score": 90, "passed": True, "issues": []},
    })
    assert state["build_result"]["status"] == status
    assert state["build_result"]["failure_kind"] == kind
    final = finalize_state(state)["final_result"]
    assert final["status"] == ("success" if outcome == "ok" else "partial_success")
    assert index.call_count == feedback.call_count == 0  # runtime acceptance and publication are still pending


def test_missing_syntax_tool_blocks_gate(tmp_path, monkeypatch):
    (tmp_path / "main.py").write_text("print('ok')", encoding="utf-8")
    monkeypatch.setattr(builder.shutil, "which", lambda _: None)
    state = builder.builder_agent({
        "code_gen_type": "python", "project_dir": str(tmp_path),
        "code_files": [{"path": "main.py", "content": "print('ok')"}],
        "review": {"score": 90, "passed": True, "issues": []},
    })
    assert state["build_result"]["status"] == "unverified"
    assert state["quality_gate_result"]["passed"] is False
