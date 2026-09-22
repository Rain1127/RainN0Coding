from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from benchmark.contracts import CaseEvaluation, LoadedCase, RawRunRecord
from benchmark.evaluators.assertions import evaluate_assertions
from benchmark.record_store import persist_raw_record
from benchmark.runners.base import RunContext, Runner
from benchmark.runners.deterministic import DeterministicRunner
from benchmark.runners.replay import ReplayRunner


RUNNERS: dict[str, Runner] = {
    "deterministic": DeterministicRunner(),
    "replay": ReplayRunner(),
}


def _infrastructure_evaluation(case: LoadedCase, record: RawRunRecord) -> CaseEvaluation:
    return CaseEvaluation(
        case_id=case.case.id,
        attempt_index=record.attempt_index,
        target=case.case.target,
        category=case.case.category,
        passed=False,
        assertions_passed=0,
        assertions_total=0,
        failures=[record.infrastructure_error or "benchmark infrastructure error"],
        output=record.output,
        observed_metrics={**record.observed_metrics, "duration_ms": record.duration_ms},
        infrastructure_error=record.infrastructure_error,
    )


def run_cases(cases: Iterable[LoadedCase], context: RunContext) -> list[CaseEvaluation]:
    evaluations: list[CaseEvaluation] = []
    for loaded in cases:
        case = loaded.case
        try:
            context.assert_mode_allowed(case.execution.mode)
            runner = RUNNERS.get(case.execution.mode)
            if runner is None:
                raise ValueError(f"{case.id}: no runner for mode {case.execution.mode}")
            records = runner.run(loaded, context)
        except Exception as exc:
            records = [RawRunRecord(
                case_id=case.id,
                attempt_index=0,
                infrastructure_error=str(exc),
                started_at=datetime.now(timezone.utc).isoformat(),
                duration_ms=0,
            )]

        for record in records:
            if context.record_dir is not None:
                persist_raw_record(context.record_dir, context.run_id, record)
            if record.infrastructure_error is not None:
                evaluations.append(_infrastructure_evaluation(loaded, record))
                continue
            evaluations.append(evaluate_assertions(
                case,
                record.output,
                {**record.observed_metrics, "duration_ms": record.duration_ms},
                attempt_index=record.attempt_index,
            ))
    return evaluations
