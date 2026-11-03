from workflow.repair import after_validation


def state(kind="code"):
    return {"build_result": {"status": "failed", "failure_kind": kind, "log": "src/App.vue:7 unexpected token"},
            "code_files": [{"path": "src/App.vue", "content": "bad"}]}


def test_code_failure_repairs_then_revalidates_success():
    run = state()
    assert after_validation(run) == "coder_agent"
    assert run["build_repair_count"] == 1
    assert "App.vue:7" in run["build_repair_context"]["log"]
    run["build_result"] = {"status": "succeeded"}
    assert after_validation(run) == "runtime_validation"


def test_environment_and_dependency_do_not_rewrite_code():
    for kind in ("environment", "dependency", "timeout"):
        run = state(kind)
        assert after_validation(run) == "end"
        assert "build_repair_count" not in run


def test_repeat_and_no_progress_stop():
    run = state()
    after_validation(run)
    assert after_validation(run) == "end"
    assert run["repair_stop_reason"] == "repeated_error_or_no_progress"


def test_limit_and_timeout(monkeypatch):
    for extra, expected in (({"build_repair_count": 2}, "repair_limit"), ({"repair_started_at": 1}, "repair_timeout")):
        run = {**state(), **extra}
        assert after_validation(run) == "end"
        assert run["repair_stop_reason"] == expected
