"""P3 release gates across matching, concurrent changes, atomicity and scope."""
import json
from pathlib import Path
import pytest
from tools.context import set_tool_context
from tools.on_demand import set_coder_state
from tools.read_file import read_file
from tools.modify_file import modify_file
from tools.create_file import create_file
from tools.delete_file import delete_file
from tools.apply_patch import apply_patch


@pytest.fixture
def project(tmp_path):
    root = tmp_path / 'site'
    root.mkdir()
    set_tool_context(str(root), 'edit', 'user', {'editing': True})
    set_coder_state({'mode': 'modify', 'change_plan': {'files': ['nav.html']}})
    yield root
    set_tool_context('', '')
    set_coder_state(None)


def read_hash():
    return json.loads(read_file.invoke({'path': 'nav.html'}))['sha256']


def test_unique_batch_stale_and_unchanged_edits(project):
    path = project / 'nav.html'
    path.write_text('导航 red\n页尾 red\n', encoding='utf-8')
    original = path.read_bytes()
    args = {'path': 'nav.html', 'old_content': 'red', 'new_content': 'blue', 'expected_hash': read_hash()}
    assert json.loads(modify_file.invoke(args))['reason'] == 'ambiguous_match'
    assert path.read_bytes() == original
    assert json.loads(modify_file.invoke(dict(args, mode='all')))['reason'] == 'batch_requires_expected_count'
    done = json.loads(modify_file.invoke(dict(args, mode='all', expected_count=2)))
    assert done['ok'] and done['match_count'] == 2
    assert path.read_text().count('blue') == 2
    stale = read_hash()
    path.write_text('外部新内容 blue', encoding='utf-8')
    assert json.loads(modify_file.invoke({'path': 'nav.html', 'old_content': 'blue', 'new_content': 'green', 'expected_hash': stale}))['reason'] == 'stale_hash'
    assert path.read_text() == '外部新内容 blue'
    same = json.loads(modify_file.invoke({'path': 'nav.html', 'old_content': 'blue', 'new_content': 'blue', 'expected_hash': read_hash()}))
    assert same['status'] == 'unchanged' and same['before_hash'] == same['after_hash']
    assert not json.loads(modify_file.invoke({'path': 'nav.html', 'old_content': '', 'new_content': 'x', 'expected_hash': read_hash()}))['ok']


def test_all_patch_hunks_validate_before_unicode_crlf_write(project):
    path = project / 'nav.html'
    original = '顶部 Ω\r\n导航 red\r\n页尾 🌟\r\n'.encode('utf-8')
    path.write_bytes(original)
    failed = apply_patch.invoke({'path': 'nav.html', 'expected_hash': read_hash(), 'hunks': [
        {'old_content': '导航 red', 'new_content': '导航 blue'},
        {'old_content': '不存在', 'new_content': 'bad'}]})
    assert not json.loads(failed)['ok'] and path.read_bytes() == original
    done = apply_patch.invoke({'path': 'nav.html', 'expected_hash': read_hash(), 'hunks': [
        {'context_before': '顶部 Ω\r\n', 'old_content': '导航 red', 'new_content': '导航 blue', 'context_after': '\r\n页尾 🌟\r\n'}]})
    assert json.loads(done)['ok']
    assert path.read_bytes() == original.replace(b'red', b'blue')


def test_plan_paths_role_and_contract_still_protected(project):
    (project / 'nav.html').write_text('original')
    (project / 'other.html').write_text('preserved')
    assert json.loads(create_file.invoke({'path': 'other.html', 'content': 'overwrite'}))['reason'] == 'outside_change_plan'
    assert json.loads(create_file.invoke({'path': 'nav.html', 'content': 'overwrite'}))['reason'] == 'existing_file_requires_explicit_overwrite_hash'
    assert json.loads(delete_file.invoke({'path': 'nav.html', 'expected_hash': read_hash()}))['reason'] == 'permission_denied'
    assert not json.loads(create_file.invoke({'path': '../outside.html', 'content': 'bad'}))['ok']
    assert (project / 'other.html').read_text() == 'preserved'
    (project / 'acceptance.json').write_text('{}')
    (project / 'alias.json').symlink_to(project / 'acceptance.json')
    set_coder_state({'mode': 'modify', 'change_plan': {'files': ['acceptance.json']}})
    assert not json.loads(create_file.invoke({'path': 'alias.json', 'content': '{}', 'overwrite': True, 'expected_hash': 'irrelevant'}))['ok']


def test_builder_rejects_change_after_review(project):
    import hashlib
    from agents.builder_agent import builder_agent
    path = project / 'nav.html'
    path.write_text('<h1>reviewed</h1>')
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    path.write_text('<h1>external change</h1>')
    state = {'project_dir': str(project), 'code_gen_type': 'html', 'mode': 'modify',
             'code_files': [{'path': 'nav.html', 'content': '<h1>reviewed</h1>'}],
             'coder_file_hashes': {'nav.html': expected}, 'harness_policy': {'editing': True}}
    result = builder_agent(state)
    assert result['build_result']['status'] == 'unverified'
    assert result['build_result']['failure_kind'] == 'conflict'
    assert path.read_text() == '<h1>external change</h1>'


@pytest.mark.parametrize('mutated', ['package-lock.json', 'unrelated.ts'])
def test_build_cannot_publish_unplanned_source_or_lock_mutation(project, monkeypatch, mutated):
    import agents.builder_agent as module
    from workflow.execution import ExecutionResult
    (project / 'nav.html').write_text('<h1>nav</h1>')
    (project / 'package.json').write_text('{"scripts":{"build":"vite build"}}')
    (project / 'package-lock.json').write_text('{}')
    (project / 'vite.config.ts').write_text('export default {}')
    (project / 'index.html').write_text('<h1>entry</h1>')
    calls = []
    def command(argv, **kwargs):
        calls.append(argv)
        (project / mutated).write_text('unexpected build change')
        return ExecutionResult('succeeded', None, 0, '', 0, 'local')
    monkeypatch.setattr('workflow.execution.process_result', command)
    state = {'project_dir': str(project), 'code_gen_type': 'vue_project', 'mode': 'modify',
             'code_files': [{'path': 'nav.html', 'content': '<h1>nav</h1>'}],
             'change_plan': {'files': ['nav.html']}, 'harness_policy': {'editing': True},
             'review': {'passed': True, 'score': 100, 'issues': []}}
    result = module.builder_agent(state)
    assert calls[0][1:] == ['ci', '--ignore-scripts']
    assert result['build_result']['status'] == 'unverified'
    assert result['build_scope_result']['unexpected'] == [mutated]
