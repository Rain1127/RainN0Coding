"""Explicit execution adapters for deterministic production agents only."""
from __future__ import annotations

from typing import Any

from agents.supervisor_agent import supervisor_decision
from agent_eval.contracts import GoldenCase


def execute_supervisor(case: GoldenCase) -> dict[str, Any]:
    return {"next_node": supervisor_decision(case.input_state)}
