from __future__ import annotations

import json
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from benchmark.contracts import LoadedCase, RawRunRecord
from benchmark.evaluators.code_execution import (
    MAX_TIMEOUT_SECONDS,
    evaluate_code,
    validate_generated_files,
)
from benchmark.runners.base import RunContext


class EndToEndRunner:
    def run(self, loaded: LoadedCase, context: RunContext) -> list[RawRunRecord]:
        case = loaded.case
        context.assert_mode_allowed(case.execution.mode)
        if case.execution.mode != "e2e":
            raise ValueError(f"{case.id}: e2e runner requires e2e mode")
        if case.target != "e2e":
            raise ValueError(f"{case.id}: e2e runner requires e2e target")
        if loaded.record_path is None:
            raise ValueError(f"{case.id}: end-to-end replay record is required")

        state = self._load_final_state(case.id, loaded.record_path)
        validated_files = validate_generated_files(state["code_files"])
        generated_paths = {path.as_posix() for path, _ in validated_files}
        required_files = [self._required_file(case.id, item) for item in case.expectations.required_files]
        missing = [path for path in required_files if path not in generated_paths]

        command = case.input.get("execution_command")
        timeout_seconds = case.input.get("timeout_seconds", 60)
        if command is not None:
            if (
                not isinstance(command, list)
                or not command
                or not all(isinstance(item, str) and item.strip() for item in command)
            ):
                raise ValueError(f"{case.id}: execution_command must be a non-empty string list")
            if (
                isinstance(timeout_seconds, bool)
                or not isinstance(timeout_seconds, int)
                or not 1 <= timeout_seconds <= MAX_TIMEOUT_SECONDS
            ):
                raise ValueError(f"{case.id}: timeout_seconds must be between 1 and {MAX_TIMEOUT_SECONDS}")

        records: list[RawRunRecord] = []
        for attempt_index in range(case.execution.repeats):
            started_at = datetime.now(timezone.utc).isoformat()
            clock = perf_counter()
            output = deepcopy(state)
            output["benchmark_required_files"] = {"passed": not missing, "missing": list(missing)}
            infrastructure_error: str | None = None
            if command is not None:
                with tempfile.TemporaryDirectory(prefix="benchmark-code-") as temporary:
                    check = evaluate_code(
                        files=deepcopy(state["code_files"]),
                        project_dir=temporary,
                        command=list(command),
                        timeout_seconds=timeout_seconds,
                    )
                infrastructure_error = check["infrastructure_error"]
                if infrastructure_error is None:
                    output["benchmark_code_check"] = check
            records.append(
                RawRunRecord(
                    case_id=case.id,
                    attempt_index=attempt_index,
                    output=output,
                    infrastructure_error=infrastructure_error,
                    started_at=started_at,
                    duration_ms=(perf_counter() - clock) * 1000,
                )
            )
        return records

    @staticmethod
    def _load_final_state(case_id: str, record_path: Path) -> dict[str, Any]:
        try:
            raw: Any = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"{case_id}: invalid end-to-end replay record") from exc
        if not isinstance(raw, dict):
            raise ValueError(f"{case_id}: invalid final state")
        state = raw.get("output", raw)
        if not isinstance(state, dict):
            raise ValueError(f"{case_id}: invalid final state")

        required_types: dict[str, type] = {
            "phase": str,
            "final_status": str,
            "intent": dict,
            "code_files": list,
            "review": dict,
            "quality_gate_result": dict,
            "build_result": dict,
        }
        if any(
            name not in state
            or not isinstance(state[name], expected)
            or (expected is str and not state[name].strip())
            for name, expected in required_types.items()
        ):
            raise ValueError(f"{case_id}: invalid final state")
        return deepcopy(state)

    @staticmethod
    def _required_file(case_id: str, raw_path: object) -> str:
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError(f"{case_id}: required_files must contain safe non-empty paths")
        relative = Path(raw_path)
        if relative.is_absolute() or bool(relative.drive) or any(part in {"", ".", ".."} for part in relative.parts):
            raise ValueError(f"{case_id}: required_files must contain safe non-empty paths")
        return relative.as_posix()
