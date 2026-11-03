"""Cloud release gates for the registered build and isolation profiles."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
from threading import Event, Thread
import time
from uuid import uuid4

import pytest

from workflow.execution import DockerBackend, ExecutionRequest, LocalBackend


@pytest.fixture
def sandbox():
    output = os.getenv('HARNESS_EXECUTOR_TEST_ROOT')
    worker = os.getenv('HARNESS_DOCKER_WORKER')
    if not (output and worker):
        pytest.skip('Requires the installed cloud executor')
    root = Path(output) / f'.executor-{uuid4().hex}.versions' / f'{uuid4().hex}.candidate'
    root.mkdir(parents=True)
    return root, DockerBackend(worker)


def package(root, scripts, dependencies=None):
    (root / 'package.json').write_text(json.dumps({
        'name': 'executor-fixture', 'version': '1.0.0', 'scripts': scripts, 'dependencies': dependencies or {},
    }))


def run(root, backend, profile, *, timeout=35, target=None, cancel=None, browser=None):
    return backend.run(ExecutionRequest('executor-check', str(root), profile, timeout, target, browser), cancel)


def test_real_build_dependency_and_isolation(sandbox, tmp_path):
    root, docker = sandbox
    package(root, {'build': 'node build.cjs'}, {'is-number': '7.0.0'})
    (root / 'build.cjs').write_text("const fs = require('node:fs'); fs.mkdirSync('dist', {recursive:true}); fs.writeFileSync('dist/built.txt', String(require('is-number')('1')))")
    for backend in (LocalBackend(), docker):
        installed = run(root, backend, 'npm-install')
        assert installed.status == 'succeeded', installed
        built = run(root, backend, 'npm-build')
        assert built.status == 'succeeded', built
        assert set(asdict(built)) == {'status', 'failure_kind', 'exit_code', 'log', 'elapsed_ms', 'backend', 'report'}
        assert (root / 'dist/built.txt').read_text() == 'true'
    sentinel = tmp_path / 'host-only.txt'
    sentinel.write_text('host-only')
    os.environ['HARNESS_TEST_SECRET'] = 'test-marker'
    (root / 'build.cjs').write_text(rf"""
        const fs = require('node:fs'), assert = require('node:assert/strict');
        assert(!fs.existsSync({json.dumps(str(sentinel))}));
        assert(!fs.existsSync('/var/run/docker.sock'));
        assert(!process.env.HARNESS_TEST_SECRET);
        const mapping = fs.readFileSync('/proc/self/uid_map', 'utf8').trim().split(/\s+/).map(Number);
        assert.equal(mapping[0], 0);
        assert.equal(mapping[1], {os.getuid()});
        assert.notEqual(mapping[1], 0);
        assert.match(fs.readFileSync('/proc/self/status', 'utf8'), /CapEff:\s+0+\s/);
        assert.equal(fs.readFileSync('/sys/fs/cgroup/memory.max', 'utf8').trim(), '536870912');
        assert.equal(fs.readFileSync('/sys/fs/cgroup/pids.max', 'utf8').trim(), '128');
        assert.throws(() => fs.writeFileSync('/bin/harness-write', 'x'));
        assert.equal(Object.keys(require('node:os').networkInterfaces()).join(), 'lo');
    """)
    isolated = run(root, docker, 'npm-build')
    assert isolated.status == 'succeeded', isolated
    (root / 'build.cjs').write_text(f"""
        const fs = require('node:fs');
        fs.mkdirSync('dist');
        fs.symlinkSync({json.dumps(str(sentinel))}, 'dist/loot.js');
    """)
    assert run(root, docker, 'npm-build').failure_kind == 'code'
    assert not (root / 'dist/loot.js').exists() and sentinel.read_text() == 'host-only'
    (root / 'build.cjs').write_text("throw new Error('build bug')")
    assert run(root, docker, 'npm-build').failure_kind == 'code'
    package(root, {}, {'invalid': 'https://example.invalid/private.tgz'})
    assert run(root, docker, 'npm-install').failure_kind == 'dependency'
    assert run(root, docker, 'lint').failure_kind == 'environment'


def test_timeout_and_cancel_terminate_owned_container_only(sandbox):
    root, docker = sandbox
    package(root, {'build': 'node linger.cjs'})
    (root / 'linger.cjs').write_text("""
        console.log('started');
        setTimeout(() => { require('node:fs').mkdirSync('dist'); require('node:fs').writeFileSync('dist/survived', '1'); }, 10000);
    """)
    unrelated = subprocess.Popen(['sleep', '30'])
    try:
        result = run(root, docker, 'npm-build', timeout=2)
        assert result.failure_kind == 'timeout', result
        assert unrelated.poll() is None
        cancel = Event()
        results = []
        job = Thread(target=lambda: results.append(run(root, docker, 'npm-build', cancel=cancel)))
        job.start()
        time.sleep(2)
        cancel.set()
        job.join(15)
        assert results and results[0].status == 'cancelled', results
        assert not (root / 'dist/survived').exists()
        assert unrelated.poll() is None
    finally:
        unrelated.terminate()
        unrelated.wait()


def test_browser_uses_actual_candidate_and_retains_failed_assertion(sandbox):
    root, docker = sandbox
    (root / 'index.html').write_text('<html><body><button>Ready</button></body></html>')
    def check(text):
        return run(root, docker, 'browser', target='.', browser={'feature': 'F001', 'contract': {
            'version': '1', 'steps': [{'action': 'text', 'value': text}],
        }})
    success = check('Ready')
    assert success.status == 'succeeded', success
    assert success.report['steps'][-1]['actual'] == 'passed'
    failure = check('Missing')
    assert failure.status == 'failed' and failure.failure_kind == 'code', failure
    assert Path(failure.report['screenshot']).is_file()
    (root / 'index.html').write_text('<script src="https://cdn.jsdelivr.net/npm/test.js"></script><body>Ready</body>')
    offline = check('Ready')
    assert offline.status == 'unverified' and offline.failure_kind == 'environment', offline


def test_coder_repairs_from_real_check_result(sandbox, tmp_path, monkeypatch):
    import hashlib
    from langchain_core.messages import AIMessage, ToolMessage
    from agents import coder_agent as coder
    from core import model_router
    from workflow import run_control
    from workflow.budget import budget_scope

    root, _ = sandbox
    package(root, {'typecheck': 'node --check value.js'})
    bad = 'const total = ;'
    source = root / 'value.js'
    source.write_text(bad)
    state = {
        'app_id': 'app', 'user_id': 'owner', 'request_id': 'check-run', 'artifact_run_id': root.stem,
        'project_dir': str(root), 'user_request': 'Fix the syntax error.',
        'mode': 'modify', 'code_gen_type': 'nodejs',
        'architecture': {'file_list': [{'path': 'value.js'}]}, 'change_plan': {'files': ['value.js']},
        'harness_policy': {'events': True, 'editing': True, 'executor': True},
    }
    store = run_control.RunStore(tmp_path / 'run.db')
    monkeypatch.setattr(run_control, 'default_run_store', lambda: store)
    monkeypatch.setattr(coder, 'build_rag_context', lambda *args, **kwargs: '')
    calls = [
        ('run_checks', {'profile': 'typecheck'}),
        ('modify_file', {'path': 'value.js', 'old_content': bad, 'new_content': 'const total = 1;',
                         'expected_hash': hashlib.sha256(bad.encode()).hexdigest()}),
        ('run_checks', {'profile': 'typecheck'}),
        ('exit_tool', {}),
    ]

    class Client:
        def __init__(self, **kwargs):
            pass

        def bind_tools(self, tools):
            assert 'run_checks' in {tool.name for tool in tools}
            return self

        def invoke(self, messages, **kwargs):
            results = [message for message in messages if isinstance(message, ToolMessage)]
            if len(results) == 1:
                failed = json.loads(results[-1].content)
                assert failed['failure_kind'] == 'code' and 'SyntaxError' in failed['log']
            if len(results) == 3:
                assert json.loads(results[-1].content)['ok']
            name, args = calls[len(results)]
            return AIMessage(content='', tool_calls=[{'id': str(len(results)), 'name': name, 'args': args}],
                             usage_metadata={'input_tokens': 7, 'output_tokens': 3, 'total_tokens': 10})

    monkeypatch.setattr(model_router, 'ChatOpenAI', Client)
    with budget_scope(state):
        coder.coder_agent(state)
    assert state['phase'] == 'code_done', state.get('error')
    assert source.read_text() == 'const total = 1;'
    assert state['budget_report']['check_calls'] == 2
    assert state['budget_report']['calls'] == 4
    events = store.public_events('check-run', 'owner', 'app')['events']
    assert [event['payload']['result']['ok'] for event in events
            if event['type'] == 'tool_result' and event['payload']['tool'] == 'run_checks'] == [False, True]


def test_generated_vue_build_and_browser_contract_in_rootless_worker(sandbox):
    from agents.builder_agent import builder_agent
    from workflow.acceptance import AcceptanceProposal, freeze_contract, validate_fixed_contract

    root, _ = sandbox
    state = {
        'project_dir': str(root), 'artifact_run_id': root.stem, 'app_id': 'vue-fixture',
        'mode': 'new', 'code_gen_type': 'vue_project', 'user_request': '显示候选 Vue 页面',
        'harness_policy': {'executor': True, 'acceptance': True},
        'review': {'passed': True, 'score': 95, 'issues': []},
        'code_files': [
            {'path': 'src/main.ts', 'content': "import {createApp} from 'vue'; import App from './App.vue'; createApp(App).mount('#app')"},
            {'path': 'src/App.vue', 'content': '<template><main>候选 Vue 页面</main></template>'},
        ],
    }
    freeze_contract(state, AcceptanceProposal.model_validate({'features': [{
        'name': 'Visible Vue content', 'source_quote': '候选 Vue 页面',
        'steps': [{'action': 'text', 'value': '候选 Vue 页面'}],
    }]}))
    built = builder_agent(state)
    assert built['build_result']['status'] == 'succeeded', built['build_result']
    result = validate_fixed_contract(built, root / 'dist', root.parent / (root.stem + '.acceptance'))
    assert result['status'] == 'succeeded', result
