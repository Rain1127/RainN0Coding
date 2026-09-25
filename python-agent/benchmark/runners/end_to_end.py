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
    EXECUTION_PROFILES,
    evaluate_code,
    normalize_generated_path,
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
        required_files = [self._required_file(case.id, item) for item in case.expectations.required_files]
        generated_files_valid = True
        generated_paths: set[str] = set()
        try:
            validated_files = validate_generated_files(state["code_files"])
            generated_paths = {path.as_posix() for path, _ in validated_files}
        except ValueError:
            generated_files_valid = False
        missing = (
            [path for path in required_files if path not in generated_paths]
            if generated_files_valid
            else list(required_files)
        )

        unsupported = sorted({"execution_command", "timeout_seconds"} & case.input.keys())
        if unsupported:
            raise ValueError(
                f"{case.id}: unsupported execution settings: {', '.join(unsupported)}; "
                "use execution_profile"
            )
        execution_profile = case.input.get("execution_profile")
        if execution_profile is not None:
            if not isinstance(execution_profile, str) or not execution_profile.strip():
                raise ValueError(f"{case.id}: execution_profile must be a non-empty string")
            if execution_profile not in EXECUTION_PROFILES:
                raise ValueError(f"{case.id}: unknown execution_profile: {execution_profile}")

        records: list[RawRunRecord] = []
        for attempt_index in range(case.execution.repeats):
            started_at = datetime.now(timezone.utc).isoformat()
            clock = perf_counter()
            output = deepcopy(state)
            output["benchmark_generated_files"] = {"passed": generated_files_valid}
            output["benchmark_required_files"] = {
                "passed": generated_files_valid and not missing,
                "missing": list(missing),
            }
            infrastructure_error: str | None = None
            if not generated_files_valid:
                output["benchmark_code_check"] = {
                    "passed": False,
                    "metric": "build_failed",
                    "log": "generated files failed validation",
                    "infrastructure_error": None,
                }
            elif execution_profile is not None:
                with tempfile.TemporaryDirectory(prefix="benchmark-code-") as temporary:
                    check = evaluate_code(
                        files=deepcopy(state["code_files"]),
                        project_dir=temporary,
                        execution_profile=execution_profile,
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
        try:
            return normalize_generated_path(raw_path).as_posix()
        except ValueError as exc:
            raise ValueError(f"{case_id}: required_files must contain safe non-empty paths") from exc
