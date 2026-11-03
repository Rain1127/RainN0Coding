"""Durable steering release gates across ownership, request boundary and recovery."""
import hashlib
import json
from uuid import uuid4

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
import pytest

from workflow import instructions, run_control
from workflow.acceptance import AcceptanceProposal, freeze_contract, validate_fixed_contract
from workflow.budget import budget_scope
from workflow.run_journal import RunJournal

POLICY = {'acceptance': True, 'editing': True, 'events': True, 'instructions': True}
OWNER = ('run', 'owner', 'app')


def store_with_run(tmp_path):
    store = run_control.RunStore(tmp_path / 'run.db')
    store.create(*OWNER, {'harness_policy': POLICY})
    return store


def test_owner_and_state_boundaries_through_internal_api(tmp_path, monkeypatch):
    from config import config
    from server.main import app
    store = store_with_run(tmp_path)
    monkeypatch.setattr(run_control, 'default_run_store', lambda: store)
    monkeypatch.setattr(config, 'INTERNAL_API_TOKEN', 'harness-test-token')
    client = TestClient(app)
    url = '/api/generation/instructions'
    headers = {'X-Internal-Token': 'harness-test-token'}
    body = {'runId': 'run', 'userId': 'owner', 'appId': 'app'}
    assert client.post(url, json=body).status_code == 401
    for key in ('userId', 'appId', 'runId'):
        assert client.post(url, json={**body, key: 'different'}, headers=headers).status_code == 404
    item = {**body, 'action': 'submit', 'instructionId': str(uuid4()), 'content': '下一轮增加帮助页', 'target': 'next_run'}
    first = client.post(url, json=item, headers=headers)
    assert first.status_code == 200 and first.json()['status'] == 'queued'
    assert client.post(url, json=item, headers=headers).json() == first.json()
    assert client.post(url, json={**item, 'content': 'changed'}, headers=headers).status_code == 409
    cancelled = {**item, 'instructionId': str(uuid4()), 'target': 'next_step'}
    assert client.post(url, json=cancelled, headers=headers).status_code == 200
    cancel_action = {**body, 'action': 'cancel', 'instructionId': cancelled['instructionId']}
    assert client.post(url, json=cancel_action, headers=headers).json()['status'] == 'cancelled'
    assert client.post(url, json=cancel_action, headers=headers).json()['status'] == 'cancelled'
    store.pause(*OWNER)
    assert instructions.claim(RunJournal({'user_id': 'owner', 'app_id': 'app'}, store, 'run')) is None
    waiting = {**cancelled, 'instructionId': str(uuid4())}
    assert client.post(url, json=waiting, headers=headers).status_code == 200
    assert instructions.claim(RunJournal({'user_id': 'owner', 'app_id': 'app'}, store, 'run')) is None
    store.update_status('run', 'completed')
    rows = client.post(url, json=body, headers=headers).json()['instructions']
    assert [row['status'] for row in rows] == ['next_run_ready', 'cancelled', 'cancelled']
    assert client.post(url, json={**waiting, 'instructionId': str(uuid4())}, headers=headers).status_code == 409


def test_correction_changes_model_request_and_keeps_original_contract_behavior(tmp_path, monkeypatch):
    from agents import coder_agent as coder
    from core import model_router
    root = tmp_path / 'site'
    root.mkdir()
    page = '<nav>Top navigation</nav><p>Red content</p>'
    (root / 'index.html').write_text(page)
    (root / 'nav.html').write_text('Protected navigation')
    def digest(text):
        return hashlib.sha256(text.encode()).hexdigest()
    state = {
        'user_id': 'owner', 'app_id': 'app', 'request_id': 'run', 'project_dir': str(root),
        'artifact_run_id': 'artifact', 'mode': 'modify', 'code_gen_type': 'html', 'harness_policy': POLICY,
        'user_request': 'Show red content and keep the top navigation', 'change_plan': {'files': ['index.html', 'nav.html']},
        'architecture': {'file_list': [{'path': 'index.html'}, {'path': 'nav.html'}]},
        'artifact_base': {'index.html': digest(page), 'nav.html': digest('Protected navigation')},
    }
    previous = freeze_contract(state, AcceptanceProposal.model_validate({'features': [
        {'name': 'Color label', 'source_quote': 'red content', 'steps': [{'action': 'text', 'value': 'Red content'}]},
        {'name': 'Navigation', 'source_quote': 'keep the top navigation', 'steps': [{'action': 'text', 'value': 'Top navigation'}]},
    ]}))
    store = store_with_run(tmp_path)
    monkeypatch.setattr(run_control, 'default_run_store', lambda: store)
    monkeypatch.setattr(coder, 'build_rag_context', lambda *args, **kwargs: '')
    correction = 'Show blue content, only edit index.html'
    instruction_id = str(uuid4())
    calls = []

    class Client:
        def __init__(self, model, **kwargs):
            self.model = model

        def bind_tools(self, tools):
            return self

        def invoke(self, messages, **kwargs):
            calls.append(self.model)
            usage = {'input_tokens': 7, 'output_tokens': 3, 'total_tokens': 10}
            if self.model == 'code-structured':
                assert correction in '\n'.join(str(message.content) for message in messages)
                assert instructions.list_for_owner(store, *OWNER)['instructions'][0]['status'] == 'planning'
                return AIMessage(content=json.dumps({'files': ['index.html'], 'features': [{
                    'name': 'New color label', 'source_quote': 'Show blue content',
                    'supersedes': [previous['features'][0]['id']],
                    'steps': [{'action': 'text', 'value': 'Blue content'}],
                }]}), usage_metadata=usage)
            if len(calls) == 1:
                instructions.submit(store, *OWNER, instruction_id, 'next_step', correction)
                instructions.submit(store, *OWNER, str(uuid4()), 'next_run', 'Add a second page')
                tool_calls = [{'name': 'read_file', 'args': {'path': 'index.html'}, 'id': 'read'}]
            elif len(calls) == 3:
                assert instructions.list_for_owner(store, *OWNER)['instructions'][0]['status'] == 'prepared'
                assert correction in '\n'.join(str(message.content) for message in messages)
                assert kwargs['config']['metadata']['instruction_ids'] == [instruction_id]
                tool_calls = [
                    {'name': 'modify_file', 'args': {'path': 'index.html', 'old_content': 'Red content', 'new_content': 'Blue content',
                                                     'expected_hash': digest(page)}, 'id': 'correct'},
                    {'name': 'modify_file', 'args': {'path': 'nav.html', 'old_content': 'Protected', 'new_content': 'Replaced',
                                                     'expected_hash': digest('Protected navigation')}, 'id': 'denied'},
                ]
            else:
                tool_calls = [{'name': 'exit_tool', 'args': {}, 'id': 'exit'}]
            return AIMessage(content='', tool_calls=tool_calls, usage_metadata=usage)

    monkeypatch.setattr(model_router, 'ChatOpenAI', Client)
    with budget_scope(state):
        coder.coder_agent(state)
    assert state['phase'] == 'code_done', state.get('error')
    assert state['budget_report']['calls'] == 4 and state['budget_report']['tokens'] == 40
    assert state['instruction_scope'] == ['index.html']
    assert (root / 'nav.html').read_text() == 'Protected navigation'
    revised = state['acceptance_contract']
    assert revised['version'] == 2 and revised['previous_contract_hash'] == previous['content_hash']
    assert previous['features'][1] in revised['features']
    owner_rows = instructions.list_for_owner(store, *OWNER)['instructions']
    assert [row['status'] for row in owner_rows] == ['included', 'next_run_ready']
    event = next(event for event in store.public_events(*OWNER)['events'] if event['type'] == 'instruction_included')
    assert event['step_id'] == owner_rows[0]['step_id']
    assert event['payload']['contract_version'] == 2
    assert correction not in json.dumps(event)
    actual = validate_fixed_contract(state, root, tmp_path / 'report')
    assert actual['status'] == 'succeeded', actual


def test_request_receipt_repairs_after_crash_without_duplicate_event(tmp_path, monkeypatch):
    from langchain_core.messages import HumanMessage
    store = store_with_run(tmp_path)
    instruction_id = str(uuid4())
    instructions.submit(store, *OWNER, instruction_id, 'next_step', 'Apply an approved change')
    state = {'user_id': 'owner', 'app_id': 'app', 'harness_policy': POLICY}
    journal = RunJournal(state, store, 'run')
    instructions.claim(journal)
    instructions.transition(journal, instruction_id, 'prepared')
    messages = [HumanMessage(content='Apply an approved change')]
    journal.prepare_model(messages, 'code-reasoning', 'reasoning', '', [instruction_id])
    original = journal._instruction_receipt
    monkeypatch.setattr(journal, '_instruction_receipt', lambda *args: None)
    journal.capture_response(AIMessage(content='done'), None)
    assert instructions.list_for_owner(store, *OWNER)['instructions'][0]['status'] == 'prepared'
    restored = RunJournal(dict(state), store, 'run')
    assert restored.prepare_model(messages, 'code-reasoning', 'reasoning', '').content == 'done'
    original(journal.frame['request_step'], {'instruction_ids': [instruction_id]})
    assert instructions.list_for_owner(store, *OWNER)['instructions'][0]['status'] == 'included'
    assert sum(event['type'] == 'instruction_included' for event in store.public_events(*OWNER)['events']) == 1


def test_durable_reply_restores_pending_tools_before_a_later_correction(tmp_path, monkeypatch):
    from langchain_core.messages import HumanMessage
    store = store_with_run(tmp_path)
    first, second = str(uuid4()), str(uuid4())
    instructions.submit(store, *OWNER, first, 'next_step', 'Apply first change')
    instructions.submit(store, *OWNER, second, 'next_step', 'Apply second change')
    state = {'user_id': 'owner', 'app_id': 'app', 'harness_policy': POLICY}
    journal = RunJournal(state, store, 'run')
    assert instructions.claim(journal)['instruction_id'] == first
    instructions.transition(journal, first, 'prepared')
    journal.prepare_model([HumanMessage(content='Apply first change')], 'code-reasoning', 'reasoning', '', [first], 2)
    monkeypatch.setattr(journal, '_instruction_receipt', lambda *args: None)
    journal.capture_response(AIMessage(content='', tool_calls=[{'name': 'exit_tool', 'args': {}, 'id': 'call'}]), None)
    restored = RunJournal(dict(state), store, 'run')
    assert restored.frame['response_pending'] and restored.frame['round'] == 2 and restored.frame['next_tool'] == 0
    assert restored.restore_messages()[-1].tool_calls[0]['id'] == 'call'
    assert [row['status'] for row in instructions.list_for_owner(store, *OWNER)['instructions']] == ['included', 'queued']


def test_empty_plan_rejected_and_contract_event_gap_is_recoverable(tmp_path, monkeypatch):
    import sqlite3
    from workflow.run_journal import active_journal
    store = store_with_run(tmp_path)
    root = tmp_path / 'site'
    root.mkdir()
    state = {'user_id': 'owner', 'app_id': 'app', 'harness_policy': POLICY, 'mode': 'new',
             'user_request': 'Show navigation', 'project_dir': str(root), 'artifact_run_id': 'artifact'}
    freeze_contract(state, AcceptanceProposal.model_validate({'features': [
        {'name': 'Navigation', 'source_quote': 'Show navigation', 'steps': [{'action': 'text', 'value': 'Nav'}]},
    ]}))
    journal = RunJournal(state, store, 'run')
    instructions.submit(store, *OWNER, str(uuid4()), 'next_step', 'Show a blue header')
    monkeypatch.setattr(instructions, 'propose', lambda *args: instructions.Correction())
    assert instructions.prepare_next(journal) is None
    assert state['acceptance_contract']['version'] == 1
    assert instructions.list_for_owner(store, *OWNER)['instructions'][0]['status'] == 'rejected'
    instruction_id = str(uuid4())
    instructions.submit(store, *OWNER, instruction_id, 'next_step', 'Add footer')
    monkeypatch.setattr(instructions, 'propose', lambda *args: instructions.Correction.model_validate({'features': [
        {'name': 'Footer', 'source_quote': 'Add footer', 'steps': [{'action': 'text', 'value': 'Footer'}]},
    ]}))
    publish = journal.event

    def event_gap(kind, *args, **kwargs):
        if kind == 'contract_fixed':
            raise sqlite3.OperationalError('simulated shared writer unavailable')
        return publish(kind, *args, **kwargs)

    monkeypatch.setattr(journal, 'event', event_gap)
    token = active_journal.set(journal)
    try:
        assert instructions.prepare_next(journal) == instruction_id
    finally:
        active_journal.reset(token)
    assert instructions.list_for_owner(store, *OWNER)['instructions'][1]['status'] == 'prepared'
    assert state['acceptance_contract']['version'] == 2
    assert not any(event['type'] == 'contract_fixed' for event in store.public_events(*OWNER)['events'])
    restored = RunJournal(dict(state), store, 'run')
    assert restored.state['acceptance_contract']['version'] == 2
    assert sum(event['type'] == 'contract_fixed' for event in store.public_events(*OWNER)['events']) == 1
