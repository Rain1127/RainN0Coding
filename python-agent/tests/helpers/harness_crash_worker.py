"""Dedicated child killed only inside cloud fault-injection tests."""
import hashlib
import json
import os
from pathlib import Path
import sys
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from workflow.run_control import RunStore
from workflow.run_journal import RunJournal, active_journal
from workflow.budget import budget_scope
from tools.context import set_tool_context
from tools.on_demand import set_coder_state
from tools.modify_file import modify_file

root, window = Path(sys.argv[1]), sys.argv[2]
project = root / 'site'
project.mkdir(exist_ok=True)
path = project / 'nav.html'
path.write_text('nav=red\n')
state = {'user_id': 'owner', 'app_id': 'app', 'user_request': 'change nav', 'mode': 'modify',
         'project_dir': str(project), 'artifact_run_id': 'artifact',
         'change_plan': {'files': ['nav.html']}, 'harness_policy': {'events': True, 'editing': True}}
store = RunStore(root / 'run.db')
store.create('run', 'owner', 'app', {})
set_tool_context(str(project), 'app', 'user', state['harness_policy'])
set_coder_state(state)
with budget_scope(state) as budget:
    journal = RunJournal(state, store, 'run')
    active_journal.set(journal)
    if window in {'model', 'model_intent', 'model_event_gap'}:
        import core.model_router as module
        class Client:
            def __init__(self, **kwargs): pass
            def invoke(self, *args, **kwargs):
                (root / 'model-count').write_text('1')
                return AIMessage(content='durable reply', usage_metadata={'input_tokens': 7, 'output_tokens': 3, 'total_tokens': 10})
        module.ChatOpenAI = Client
        if window in {'model_intent', 'model_event_gap'}:
            event = journal.event
            def event_gap(kind, *args, **kwargs):
                if kind == ('model_request' if window == 'model_intent' else 'model_result'):
                    os._exit(36 if window == 'model_intent' else 37)
                return event(kind, *args, **kwargs)
            journal.event = event_gap
        module.ModelRouter().route('reasoning', [HumanMessage(content='request')], allow_degraded=False)
        os._exit(34)
    if window == 'model_inflight':
        journal.prepare_model([HumanMessage(content='request')], 'code-reasoning', 'reasoning', '')
        budget.reserve([HumanMessage(content='request')])
        journal.reserved('code-reasoning', 8192, 30)
        os._exit(35)
    budget.reserve([HumanMessage(content='request')])
    budget.observe({'input_tokens': 7, 'output_tokens': 3, 'total_tokens': 10})
    args = {'path': 'nav.html', 'old_content': 'red', 'new_content': 'redblue',
            'expected_hash': hashlib.sha256(path.read_bytes()).hexdigest()}
    call = {'name': 'modify_file', 'args': args, 'id': 'call-one'}
    (root / 'call.json').write_text(json.dumps(call))
    journal.frame['request_step'] = journal.epoch + ':m1'
    journal.frame_response([SystemMessage(content='rules'), HumanMessage(content='request'),
                            AIMessage(content='', tool_calls=[call])], 1)
    class Tool:
        def invoke(self, payload):
            if window == 'slow_tool':
                import time
                time.sleep(1)
                os._exit(39)
            if window == 'before': os._exit(31)
            result = modify_file.invoke(payload)
            if window in {'after_file', 'conflict'}: os._exit(32)
            return result
    if window == 'after_result':
        original = journal._finish_tool
        def finished(*args, **kwargs):
            original(*args, **kwargs)
            os._exit(33)
        journal._finish_tool = finished
    if window == 'tool_event_gap':
        insert = journal._insert_event
        def event_gap(db, kind, *args, **kwargs):
            if kind == 'tool_result': os._exit(38)
            return insert(db, kind, *args, **kwargs)
        journal._insert_event = event_gap
    journal.execute(call, 0, Tool())
raise AssertionError('Fault injection did not terminate the child')
