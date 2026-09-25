from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest

import benchmark.runners.live_llm as live_module
from benchmark.contracts import BenchmarkCase, ExecutionSpec, Expectations, LoadedCase, Provenance
from benchmark.dataset import load_cases
from benchmark.orchestrator import RUNNERS, run_cases
from benchmark.runners.base import RunContext
from benchmark.runners.live_llm import LiveLlmRunner, _invoke_target, _safe_app_id, _usage_metrics
from request_context import bind_request_context, get_request_metadata, record_llm_response
from tools import get_app_id, get_project_dir, get_user_role, set_tool_context


class FakeResponse:
    usage_metadata = {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5}
    response_metadata = {"response_cost": 0.25}


def _loaded(*, case_id="intent-live", target="intent", repeats=1, expectations=None, input_data=None):
    return LoadedCase(
        case=BenchmarkCase(
            id=case_id,
            dataset_version="test-v1",
            target=target,
            category="live",
            execution=ExecutionSpec(mode="live", repeats=repeats),
            input=input_data or {"user_request": "Build a safe page"},
            expectations=expectations or Expectations(),
            provenance=Provenance(source="synthetic", reviewed=True, sanitized=True),
        ),
        source_path=Path("live.yaml"),
    )


def test_live_runner_rejects_offline_and_non_live_cases():
    called = False

    def invoke(target, state):
        nonlocal called
        called = True
        return state

    with pytest.raises(ValueError, match="offline"):
        LiveLlmRunner(invoke).run(_loaded(), RunContext("run", True))
    assert called is False

    loaded = _loaded().model_copy(
        update={"case": _loaded().case.model_copy(update={"execution": ExecutionSpec(mode="replay")})}
    )
    with pytest.raises(ValueError, match="live mode"):
        LiveLlmRunner(invoke).run(loaded, RunContext("run", False))


def test_live_runner_preserves_repeats_context_usage_and_sibling_failures():
    observations = []
    calls = 0

    def invoke(target, state):
        nonlocal calls
        calls += 1
        observations.append((target, dict(state), get_request_metadata()))
        state["mutated"] = calls
        if calls == 2:
            raise RuntimeError("Authorization=Bearer sk-supersecret123")
        record_llm_response(FakeResponse(), "fake-model")
        return {"phase": "intent_done", "call": calls}

    with bind_request_context(request_id="outer", trace_id="outer", user_id="owner", app_id="owner-app"):
        records = LiveLlmRunner(invoke).run(
            _loaded(case_id="unsafe / case", repeats=3),
            RunContext("run-1", False),
        )
        assert get_request_metadata()["request_id"] == "outer"

    assert [record.attempt_index for record in records] == [0, 1, 2]
    assert records[0].output["call"] == 1
    assert records[1].infrastructure_error is not None
    assert "supersecret" not in records[1].infrastructure_error
    assert records[2].output["call"] == 3
    assert records[0].observed_metrics == {
        "input_tokens": 3.0,
        "output_tokens": 2.0,
        "total_tokens": 5.0,
        "cost_usd": 0.25,
    }
    assert records[1].observed_metrics == {}
    assert records[0].duration_ms >= 0
    assert [item[2]["request_id"] for item in observations] == [
        "benchmark-run-1-unsafe---case-0",
        "benchmark-run-1-unsafe---case-1",
        "benchmark-run-1-unsafe---case-2",
    ]
    assert all(item[2]["trace_id"] == item[2]["request_id"] for item in observations)
    assert all(item[2]["user_id"] == "benchmark" for item in observations)
    assert all(item[2]["app_id"] == "unsafe---case" for item in observations)
    assert all("mutated" not in item[1] for item in observations)


def test_empty_or_partially_unknown_usage_has_unknown_cost():
    calls = 0

    def invoke(target, state):
        nonlocal calls
        calls += 1
        record_llm_response(
            type(
                "UnknownCost",
                (),
                {
                    "usage_metadata": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
                    "response_metadata": {},
                },
            )(),
            "unknown",
        )
        if calls == 2:
            record_llm_response(FakeResponse(), "known")
        return {"ok": True}

    records = LiveLlmRunner(invoke).run(_loaded(repeats=2), RunContext("run", False))
    assert records[0].observed_metrics["cost_usd"] is None
    assert records[1].observed_metrics["cost_usd"] is None
    assert records[0].observed_metrics["total_tokens"] == 2.0
    assert records[1].observed_metrics["total_tokens"] == 7.0


def test_failed_attempt_preserves_usage_recorded_before_the_error():
    def invoke(target, state):
        record_llm_response(FakeResponse(), "fake-model")
        raise RuntimeError("provider post-processing failed")

    record = LiveLlmRunner(invoke).run(_loaded(), RunContext("run", False))[0]

    assert record.infrastructure_error == "provider post-processing failed"
    assert record.observed_metrics == {
        "input_tokens": 3.0,
        "output_tokens": 2.0,
        "total_tokens": 5.0,
        "cost_usd": 0.25,
    }


def test_quality_failure_is_scored_once_without_runner_retry(monkeypatch):
    calls = 0

    def invoke(target, state):
        nonlocal calls
        calls += 1
        record_llm_response(FakeResponse(), "fake-model")
        return {"phase": "wrong"}

    monkeypatch.setitem(RUNNERS, "live", LiveLlmRunner(invoke))
    loaded = _loaded(expectations=Expectations(equals={"phase": "intent_done"}))
    evaluations = run_cases([loaded], RunContext("run", False))

    assert calls == 1
    assert len(evaluations) == 1
    assert evaluations[0].passed is False
    assert evaluations[0].infrastructure_error is None


def test_successful_live_target_without_usage_is_infrastructure_error():
    record = LiveLlmRunner(lambda target, state: {"phase": "intent_done"}).run(
        _loaded(),
        RunContext("run", False),
    )[0]

    assert record.infrastructure_error == "intent live target completed without LLM usage"


def test_intent_fallback_without_usage_is_infrastructure_error():
    record = LiveLlmRunner(
        lambda target, state: {
            "phase": "intent_done",
            "error": None,
            "intent": {
                "confidence": 0.55,
                "confidence_reason": "LLM unavailable, fallback to rule router: provider failed",
            },
        }
    ).run(_loaded(), RunContext("run", False))[0]

    assert record.infrastructure_error == "intent live target completed without LLM usage"


@pytest.mark.parametrize("target", ["reviewer", "coder"])
def test_direct_target_phase_error_is_infrastructure_even_with_usage(target):
    def invoke(_target, state):
        record_llm_response(FakeResponse(), "fake-model")
        return {"phase": "error", "error": "token=sk-secretvalue123"}

    record = LiveLlmRunner(invoke).run(
        _loaded(target=target),
        RunContext("run", False),
    )[0]

    assert record.infrastructure_error == f"{target} infrastructure failure: phase_error"
    assert "secretvalue" not in record.infrastructure_error


def test_nonempty_agent_error_is_infrastructure_even_when_phase_is_not_error():
    def invoke(target, state):
        record_llm_response(FakeResponse(), "fake-model")
        return {"phase": "review_done", "error": "password=hunter2"}

    record = LiveLlmRunner(invoke).run(
        _loaded(target="reviewer"),
        RunContext("run", False),
    )[0]

    assert record.infrastructure_error == "reviewer infrastructure failure: agent_error"
    assert "hunter2" not in record.infrastructure_error


def test_e2e_phase_failure_uses_safe_reason_code_without_raw_secret():
    def invoke(target, state):
        record_llm_response(FakeResponse(), "fake-model")
        return {
            "phase": "completed",
            "final_status": "failed",
            "phase_failures": [
                {
                    "phase": "coder",
                    "reason_code": "coder_timeout",
                    "message": "Authorization=Bearer sk-secretvalue123",
                }
            ],
        }

    record = LiveLlmRunner(invoke).run(
        _loaded(target="e2e"),
        RunContext("run", False),
    )[0]

    assert record.infrastructure_error == "e2e infrastructure failure: coder_timeout"
    assert "secretvalue" not in record.infrastructure_error


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        (
            {
                "phase": "completed",
                "final_status": "degraded_success",
                "degraded": True,
                "degraded_reasons": ["reviewer_exception"],
            },
            "e2e infrastructure failure: reviewer_exception",
        ),
        (
            {
                "phase": "completed",
                "final_status": "failed",
                "failed_phase": "coder",
            },
            "e2e infrastructure failure: coder_failed",
        ),
    ],
)
def test_e2e_swallowed_production_failure_is_infrastructure(output, expected):
    def invoke(target, state):
        record_llm_response(FakeResponse(), "fake-model")
        return output

    record = LiveLlmRunner(invoke).run(
        _loaded(target="e2e"),
        RunContext("run", False),
    )[0]

    assert record.infrastructure_error == expected


def test_e2e_build_quality_failure_without_phase_failure_is_not_infrastructure():
    def invoke(target, state):
        record_llm_response(FakeResponse(), "fake-model")
        return {
            "phase": "completed",
            "final_status": "success",
            "build_result": {"success": False, "log": "npm build failed"},
            "phase_failures": [],
        }

    record = LiveLlmRunner(invoke).run(
        _loaded(target="e2e"),
        RunContext("run", False),
    )[0]

    assert record.infrastructure_error is None
    assert record.output["build_result"]["success"] is False


def test_untrusted_e2e_reason_code_is_not_copied_into_error_summary():
    def invoke(target, state):
        record_llm_response(FakeResponse(), "fake-model")
        return {
            "phase": "completed",
            "phase_failures": [
                {"phase": "coder", "reason_code": "token=sk-secretvalue123"}
            ],
        }

    record = LiveLlmRunner(invoke).run(
        _loaded(target="e2e"),
        RunContext("run", False),
    )[0]

    assert record.infrastructure_error == "e2e infrastructure failure: coder_failure"
    assert "secretvalue" not in record.infrastructure_error


def test_usage_metrics_are_total_for_overflow_and_malformed_entries():
    huge = 10**10000
    metrics = _usage_metrics(
        [
            {
                "input_tokens": huge,
                "output_tokens": 1,
                "total_tokens": huge,
                "cost_usd": 1e308,
            },
            {
                "input_tokens": 1,
                "output_tokens": 1,
                "total_tokens": 2,
                "cost_usd": 1e308,
            },
        ]
    )
    malformed = _usage_metrics([object(), {"input_tokens": True}])

    assert metrics == {
        "input_tokens": None,
        "output_tokens": 2.0,
        "total_tokens": None,
        "cost_usd": None,
    }
    assert malformed == {
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
        "cost_usd": None,
    }


def test_bad_partial_usage_cannot_drop_a_sibling_attempt(monkeypatch):
    calls = 0

    @contextmanager
    def bad_capture():
        yield [
            {
                "input_tokens": 10**10000,
                "output_tokens": "bad",
                "total_tokens": -1,
                "cost_usd": float("inf"),
            }
        ]

    def invoke(target, state):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("transport failed")
        return {"phase": "intent_done"}

    monkeypatch.setattr(live_module, "capture_llm_usage", bad_capture)
    records = LiveLlmRunner(invoke).run(_loaded(repeats=2), RunContext("run", False))

    assert len(records) == 2
    assert records[0].infrastructure_error == "transport failed"
    assert records[0].observed_metrics["input_tokens"] is None
    assert records[1].infrastructure_error is None
    assert records[1].output == {"phase": "intent_done"}


def test_safe_app_id_is_ascii_bounded_and_never_empty():
    assert _safe_app_id(" ../中文 id/ ") == "id"
    assert _safe_app_id("中文") == "case"
    assert len(_safe_app_id("a" * 100)) == 64


def test_coder_adapter_uses_temporary_directory_and_restores_tool_context(monkeypatch, tmp_path):
    original = tmp_path / "original"
    original.mkdir()
    set_tool_context(str(original), "original-app", "admin")
    seen = {}

    def fake_coder(state):
        seen["project_dir"] = get_project_dir()
        seen["app_id"] = get_app_id()
        seen["role"] = get_user_role()
        seen["exists"] = Path(get_project_dir()).is_dir()
        state["phase"] = "code_done"
        state["code_files"] = [{"path": "index.html", "content": "safe"}]
        return state

    monkeypatch.setattr(live_module, "_load_target", lambda target: fake_coder)
    result = _invoke_target(
        "coder",
        {"app_id": "case-app", "user_role": "user", "architecture": {"file_list": []}},
    )

    assert result["phase"] == "code_done"
    assert seen["exists"] is True
    assert seen["app_id"] == "case-app"
    assert seen["role"] == "user"
    assert not Path(seen["project_dir"]).exists()
    assert (get_project_dir(), get_app_id(), get_user_role()) == (str(original), "original-app", "admin")


def test_e2e_adapter_uses_empty_workflow_app_id_and_restores_output_dir(monkeypatch):
    from config import config

    original_output = config.CODE_OUTPUT_DIR
    seen = {}

    def fake_workflow(**kwargs):
        seen.update(kwargs)
        seen["output_dir"] = config.CODE_OUTPUT_DIR
        seen["exists"] = Path(config.CODE_OUTPUT_DIR).is_dir()
        return {"phase": "completed"}

    monkeypatch.setattr(live_module, "_load_target", lambda target: fake_workflow)
    result = _invoke_target(
        "e2e",
        {"user_request": "Build login", "user_id": "benchmark", "app_id": "case-app", "trace_id": "trace"},
    )

    assert result == {"phase": "completed"}
    assert seen["app_id"] == ""
    assert seen["exists"] is True
    assert not Path(seen["output_dir"]).exists()
    assert config.CODE_OUTPUT_DIR == original_output


def test_nightly_live_core_contains_exact_reviewed_matrix():
    dataset_root = Path(__file__).resolve().parents[2] / "benchmarks" / "datasets" / "nightly"
    cases = {loaded.case.id: loaded.case for loaded in load_cases(dataset_root, asset_root=dataset_root.parents[1])}
    live_ids = {case_id for case_id, case in cases.items() if case.execution.mode == "live"}

    assert live_ids == {
        "intent-vue-clear-live",
        "intent-ambiguous-live",
        "reviewer-xss-live",
        "reviewer-clean-live",
        "coder-html-login-live",
        "e2e-html-login-live",
    }
    assert {case_id: cases[case_id].execution.repeats for case_id in live_ids} == {
        "intent-vue-clear-live": 3,
        "intent-ambiguous-live": 3,
        "reviewer-xss-live": 3,
        "reviewer-clean-live": 3,
        "coder-html-login-live": 3,
        "e2e-html-login-live": 2,
    }
    assert all(cases[case_id].provenance.reviewed for case_id in live_ids)
    assert all(cases[case_id].provenance.sanitized for case_id in live_ids)
    assert cases["coder-html-login-live"].expectations.required_files == ["index.html"]
    assert cases["coder-html-login-live"].expectations.equals["benchmark_code_check.passed"] is True
    assert cases["e2e-html-login-live"].expectations.required_files == ["index.html"]
