"""Per-run, checkpointable model-call, token and wall-clock limits."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import time
from config import config


class BudgetExceeded(RuntimeError):
    pass


active_budget = ContextVar("active_budget", default=None)


class Budget:
    def __init__(self, saved: dict | None = None):
        self.data = dict(saved or {})
        self.data.setdefault("started_at", time.time())
        self.data.setdefault("calls", 0)
        self.data.setdefault("charged_tokens", 0)
        self.data.setdefault("observed_tokens", 0)
        self.data.setdefault("usage_complete", True)
        self.data.setdefault("cost_usd", None)
        self.data.setdefault("cost_complete", True)
        self.data.setdefault("active_seconds", 0)
        self.phase_started = time.monotonic()
        self.pending = 0

    def check(self):
        if self.active_seconds() >= getattr(config, "TASK_MAX_SECONDS", 1200):
            self.data["stop_reason"] = "task_time_budget_exceeded"
            raise BudgetExceeded("task_time_budget_exceeded")

    def remaining_seconds(self):
        return max(0.01, getattr(config, "TASK_MAX_SECONDS", 1200) - self.active_seconds())

    def active_seconds(self):
        return self.data["active_seconds"] + time.monotonic() - self.phase_started

    def reserve(self, messages, extra_input: str = "") -> int:
        self.check()
        if self.data["calls"] >= getattr(config, "TASK_MAX_LLM_CALLS", 50):
            self.data["stop_reason"] = "task_call_budget_exceeded"
            raise BudgetExceeded("task_call_budget_exceeded")
        input_bound = sum(len(str(getattr(m, "content", m)).encode("utf-8")) + 32 for m in messages) + len(extra_input.encode("utf-8")) + 256
        remaining = getattr(config, "TASK_MAX_TOKENS", 250000) - self.data["charged_tokens"] - input_bound
        if remaining <= 0:
            self.data["stop_reason"] = "task_token_budget_exceeded"
            raise BudgetExceeded("task_token_budget_exceeded")
        output_limit = min(8192, remaining)
        self.pending = input_bound + output_limit
        self.data["charged_tokens"] += self.pending
        self.data["calls"] += 1
        return output_limit

    def observe(self, usage):
        if usage is None:
            self.data["usage_complete"] = False
            self.data["cost_complete"] = False
            self.pending = 0
            return
        tokens = usage["total_tokens"]
        self.data["charged_tokens"] += tokens - self.pending
        self.data["observed_tokens"] += tokens
        self.pending = 0
        if usage.get("cost_usd") is not None:
            self.data["cost_usd"] = (self.data["cost_usd"] or 0) + usage["cost_usd"]
        else:
            self.data["cost_complete"] = False

    def report(self):
        return {**self.data, "tokens": self.data["observed_tokens"] if self.data["usage_complete"] else None,
                "cost_usd": self.data["cost_usd"] if self.data["cost_complete"] else None,
                "active_seconds": self.active_seconds(),
                "elapsed_seconds": round(time.time() - self.data["started_at"], 3)}


@contextmanager
def budget_scope(state):
    budget = Budget(state.get("budget_report"))
    token = active_budget.set(budget)
    try:
        budget.check()
        yield budget
    finally:
        state["budget_report"] = budget.report()
        active_budget.reset(token)
