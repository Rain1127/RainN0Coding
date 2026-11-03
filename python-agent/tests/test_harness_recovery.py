"""P4 release gates use real child process exits, private SQLite and file effects."""
import json
from pathlib import Path
import subprocess
import sys
import pytest
from langchain_core.messages import HumanMessage
from workflow.run_control import RunStore, RunControlError
from workflow.run_journal import RunJournal, RecoveryConflict, active_journal
from workflow.budget import budget_scope
from tools.context import set_tool_context
from tools.on_demand import set_coder_state
from tools.modify_file import modify_file


def crashed(tmp_path, window):
    script = Path(__file__).parent / 'helpers/harness_crash_worker.py'
    result = subprocess.run([sys.executable, str(script), str(tmp_path), window], capture_output=True, text=True, timeout=30)
    assert result.returncode == {'before': 31, 'after_file': 32, 'after_result': 33, 'conflict': 32, 'model': 34,
                                'model_inflight': 35, 'model_intent': 36, 'model_event_gap': 37,
                                'tool_event_gap': 38, 'slow_tool': 39}[window], result.stderr
    project = tmp_path / 'site'
    state = {'user_id': 'owner', 'app_id': 'app', 'project_dir': str(project), 'artifact_run_id': 'artifact',
             'harness_policy': {'events': True, 'editing': True}, 'mode': 'modify', 'change_plan': {'files': ['nav.html']}}
    set_tool_context(str(project), 'app', 'user', state['harness_policy'])
    set_coder_state(state)
    return RunStore(tmp_path / 'run.db'), state


@pytest.mark.parametrize('window', ['before', 'after_file', 'after_result', 'tool_event_gap'])
def test_crash_windows_reconcile_without_duplicate_modification(tmp_path, window):
    store, state = crashed(tmp_path, window)
    call = json.loads((tmp_path / 'call.json').read_text())
    count = 0
    class Tool:
        def invoke(self, args):
            nonlocal count
            count += 1
            return modify_file.invoke(args)
    with budget_scope(state):
        journal = RunJournal(state, store, 'run')
        assert state['mode'] == 'modify'
        result = journal.execute(call, 0, Tool())
        assert json.loads(result)['ok']
        assert (tmp_path / 'site/nav.html').read_text() == 'nav=redblue\n'
        assert count == (1 if window == 'before' else 0)
        journal.execute(call, 0, Tool())
        assert count == (1 if window == 'before' else 0)
    assert state['budget_report']['calls'] == 1
    assert state['budget_report']['tokens'] == 10
    page = store.public_events('run', 'owner', 'app')
    assert len({e['seq'] for e in page['events']}) == len(page['events'])
    assert sum(e['type'] == 'tool_intent' for e in page['events']) == 1
    assert sum(e['type'] == 'tool_result' for e in page['events']) == 1
    with pytest.raises(RunControlError):
        store.public_events('run', 'different-user', 'app')
    assert (tmp_path / 'run.harness-private.db').stat().st_mode & 0o077 == 0


def test_external_change_keeps_candidate_and_stops_replay(tmp_path):
    store, state = crashed(tmp_path, 'conflict')
    path = tmp_path / 'site/nav.html'
    path.write_text('external green')
    with budget_scope(state):
        journal = RunJournal(state, store, 'run')
        with pytest.raises(RecoveryConflict, match='file_state_conflict'):
            journal.execute(json.loads((tmp_path / 'call.json').read_text()), 0, modify_file)
    assert path.read_text() == 'external green'


def test_persisted_model_response_is_replayed_without_new_call_or_budget_charge(tmp_path, monkeypatch):
    store, state = crashed(tmp_path, 'model')
    import core.model_router as module
    def prohibited(**kwargs):
        raise AssertionError('A persisted response must not cause a provider request')
    monkeypatch.setattr(module, 'ChatOpenAI', prohibited)
    with budget_scope(state):
        journal = RunJournal(state, store, 'run')
        token = active_journal.set(journal)
        try:
            assert module.ModelRouter().route('reasoning', [HumanMessage(content='request')], allow_degraded=False) == 'durable reply'
        finally:
            active_journal.reset(token)
    assert state['budget_report']['calls'] == 1
    assert state['budget_report']['tokens'] == 10
    assert (tmp_path / 'model-count').read_text() == '1'


def test_unknown_model_request_keeps_reservations_and_marks_usage_missing(tmp_path):
    store, state = crashed(tmp_path, 'model_inflight')
    with budget_scope(state):
        RunJournal(state, store, 'run')
    report = state['budget_report']
    assert report['calls'] == 1 and report['charged_tokens'] >= 8192
    assert report['tokens'] is None and report['cost_usd'] is None
    assert report['reserved_active_seconds'] == 30
    assert report['active_seconds_quality'] == 'conservative_after_interruption'


@pytest.mark.parametrize('window', ['model_intent', 'model_event_gap'])
def test_model_intent_and_event_crash_windows_recover(tmp_path, monkeypatch, window):
    store, state = crashed(tmp_path, window)
    import core.model_router as module
    class Client:
        def __init__(self, **kwargs):
            assert window == 'model_intent', 'Persisted response must be reused'
        def invoke(self, *args, **kwargs):
            from langchain_core.messages import AIMessage
            return AIMessage(content='durable reply', usage_metadata={'input_tokens': 7, 'output_tokens': 3, 'total_tokens': 10})
    monkeypatch.setattr(module, 'ChatOpenAI', Client)
    with budget_scope(state):
        journal = RunJournal(state, store, 'run')
        token = active_journal.set(journal)
        try:
            assert module.ModelRouter().route('reasoning', [HumanMessage(content='request')], allow_degraded=False) == 'durable reply'
        finally:
            active_journal.reset(token)
    assert state['budget_report']['calls'] == 1
    assert sum(e['type'] == 'model_result' for e in store.public_events('run', 'owner', 'app')['events']) == 1


def test_interrupted_tool_retains_heartbeat_time_and_uncertainty_reservation(tmp_path):
    store, state = crashed(tmp_path, 'slow_tool')
    with budget_scope(state):
        journal = RunJournal(state, store, 'run')
        journal.execute(json.loads((tmp_path / 'call.json').read_text()), 0, modify_file)
    report = state['budget_report']
    assert report['observed_active_seconds'] >= 0.5
    assert report['reserved_active_seconds'] == 10
    assert report['active_seconds_quality'] == 'conservative_after_interruption'


def test_coder_recovers_full_tool_batch_without_duplicate_provider_or_file_effect(tmp_path):
    script = Path(__file__).parent / 'helpers/harness_coder_worker.py'
    for stage, exit_code in [('crash', 40), ('resume', 0), ('completed', 0)]:
        result = subprocess.run([sys.executable, str(script), str(tmp_path), stage],
                                capture_output=True, text=True, timeout=30)
        assert result.returncode == exit_code, result.stdout + result.stderr
        assert (tmp_path / 'site/nav.html').read_text() == 'nav=redbluegreen\n'
    assert (tmp_path / 'provider-calls').read_text().splitlines() == ['crash', 'resume']
    state = json.loads((tmp_path / 'completed.json').read_text())
    assert state['phase'] == 'code_done'
    assert state['budget_report']['calls'] == 2
    assert state['budget_report']['tokens'] == 20
    events = RunStore(tmp_path / 'run.db').public_events('run', 'owner', 'app')['events']
    assert sum(event['type'] == 'tool_result' for event in events) == 3
