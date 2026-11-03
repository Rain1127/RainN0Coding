"""Run a registered check in the candidate workspace."""
from dataclasses import asdict
import json
from typing import Literal

from langchain_core.tools import tool

from benchmark.redaction import redact
from tools.context import get_project_dir, get_tool_policy
from workflow.budget import BudgetExceeded, active_budget
from workflow.execution import execution_request, executor
from workflow.run_journal import active_journal


@tool
def run_checks(profile: Literal['typecheck', 'lint', 'test'], target: str | None = None) -> str:
    """Run a registered npm check. For test, supply one relative *.test.* or *.spec.* file. No shell commands."""
    policy = get_tool_policy()
    journal = active_journal.get()
    budget = active_budget.get()
    if not (policy.get('executor') and journal and budget):
        return json.dumps({'ok': False, 'status': 'unverified', 'failure_kind': 'environment',
                           'log': 'Isolated checks require an active journal and task budget'})
    state = {**journal.state, 'project_dir': get_project_dir(), 'harness_policy': policy}
    try:
        budget.reserve_check()
        # Persist the attempt before external work starts, including on process death.
        journal.save()
        result = executor(state).run(execution_request(state, profile, 45, target=target))
    except BudgetExceeded as exc:
        return json.dumps({'ok': False, 'status': 'failed', 'failure_kind': 'budget', 'log': str(exc)})
    return json.dumps(redact({'ok': result.status == 'succeeded', 'profile': profile, **asdict(result)}), ensure_ascii=False)
