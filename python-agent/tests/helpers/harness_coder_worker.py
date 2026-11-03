"""Exercise the production Coder loop and exit after a committed tool result."""
import hashlib
import json
import os
from pathlib import Path
import sys

from langchain_core.messages import AIMessage, ToolMessage

from agents import coder_agent as coder
from core import model_router
from workflow import run_control
from workflow.budget import budget_scope
from workflow.run_journal import RunJournal

root = Path(sys.argv[1])
stage = sys.argv[2]
project = root / 'site'
project.mkdir(exist_ok=True)
if stage == 'crash':
    (project / 'nav.html').write_text('nav=red\n')
state = {
    'app_id': 'app', 'user_id': 'owner', 'request_id': 'run', 'artifact_run_id': 'artifact',
    'project_dir': str(project), 'user_request': 'Change the navigation color.',
    'mode': 'modify', 'code_gen_type': 'html',
    'architecture': {'file_list': [{'path': 'nav.html'}]}, 'change_plan': {'files': ['nav.html']},
    'harness_policy': {'events': True, 'editing': True},
}
store = run_control.RunStore(root / 'run.db')
run_control.default_run_store = lambda: store
coder.build_rag_context = lambda *args, **kwargs: ''


def edit(call_id, before, old, new):
    return {'id': call_id, 'name': 'modify_file', 'args': {
        'path': 'nav.html', 'old_content': old, 'new_content': new,
        'expected_hash': hashlib.sha256(before.encode()).hexdigest(),
    }}


class Client:
    def __init__(self, **kwargs):
        pass

    def bind_tools(self, *args, **kwargs):
        return self

    def invoke(self, messages, **kwargs):
        with (root / 'provider-calls').open('a') as handle:
            handle.write(stage + '\n')
        if stage == 'crash':
            calls = [
                edit('first', 'nav=red\n', 'red', 'redblue'),
                edit('second', 'nav=redblue\n', 'blue', 'bluegreen'),
            ]
        else:
            assert stage == 'resume'
            assert [message.tool_call_id for message in messages if isinstance(message, ToolMessage)] == ['first', 'second']
            calls = [{'id': 'exit', 'name': 'exit_tool', 'args': {}}]
        return AIMessage(content='', tool_calls=calls,
                         usage_metadata={'input_tokens': 7, 'output_tokens': 3, 'total_tokens': 10})


model_router.ChatOpenAI = Client
if stage == 'crash':
    original_finish = RunJournal._finish_tool

    def finish_and_crash(self, step, *args, **kwargs):
        result = original_finish(self, step, *args, **kwargs)
        if step.endswith(':t1'):
            os._exit(40)
        return result

    RunJournal._finish_tool = finish_and_crash

with budget_scope(state):
    coder.coder_agent(state)
assert stage != 'crash', state
(root / f'{stage}.json').write_text(json.dumps(state))
