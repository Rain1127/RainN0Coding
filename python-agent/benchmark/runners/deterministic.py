from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from time import perf_counter

from agents.supervisor_agent import supervisor_decision
from benchmark.contracts import LoadedCase, RawRunRecord

from .base import RunContext


class DeterministicRunner:
    def run(self, case: LoadedCase, context: RunContext) -> list[RawRunRecord]:
        context.assert_mode_allowed(case.case.execution.mode)
        if case.case.execution.mode != "deterministic":
            raise ValueError(f"{case.case.id}: deterministic runner requires deterministic mode")
        if case.case.target != "supervisor":
            raise ValueError(f"no deterministic adapter for {case.case.target}")
        records: list[RawRunRecord] = []
        for attempt_index in range(case.case.execution.repeats):
            started_at = datetime.now(timezone.utc).isoformat()
            started = perf_counter()
            next_node = supervisor_decision(deepcopy(case.case.input))
            duration_ms = (perf_counter() - started) * 1000
            records.append(RawRunRecord(
                case_id=case.case.id,
                attempt_index=attempt_index,
                output={"next_node": next_node},
                started_at=started_at,
                duration_ms=duration_ms,
            ))
        return records
