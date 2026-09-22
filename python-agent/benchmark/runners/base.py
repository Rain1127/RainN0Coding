from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from benchmark.contracts import LoadedCase, RawRunRecord


@dataclass(frozen=True)
class RunContext:
    run_id: str
    offline: bool
    record_dir: Path | None = None

    def assert_mode_allowed(self, mode: str) -> None:
        if self.offline and mode == "live":
            raise ValueError("live mode is not allowed in an offline suite")


class Runner(Protocol):
    def run(self, case: LoadedCase, context: RunContext) -> list[RawRunRecord]: ...
