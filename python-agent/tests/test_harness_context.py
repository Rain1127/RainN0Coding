"""P2 gates: bounded requests, paired tools and retrievable unchanged file truth."""
import json
from pathlib import Path
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
import pytest
from workflow.coder_context import CoderContext, ContextWindowExceeded, message_groups
from tools.context import set_tool_context
from tools.read_file import read_file
from tools.on_demand import search_code, set_coder_state, read_progress


def test_long_tool_history_compacts_without_losing_constraints_or_pairs(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_CONTEXT_WINDOW_TOKENS', '18000')
    monkeypatch.setenv('HARNESS_CONTEXT_OUTPUT_RESERVE', '1000')
    project = tmp_path / 'site'
    project.mkdir()
    state = {'project_dir': str(project), 'artifact_run_id': 'long', 'user_request': '只修改导航，保留登录行为',
             'change_plan': {'files': ['nav.html']}, 'acceptance_contract': {'contract_id': 'fixed-contract'}}
    state['review'] = {'autogen_context': '三方结论：修复导入但保留登录校验'}
    state['repair_experiences'] = [{'evidence': 'verified-repair-reference'}]
    manager = CoderContext(state, [])
    messages = [SystemMessage(content='Never modify outside the plan'), HumanMessage(content='Architecture')]
    for i in range(10):
        messages.extend([AIMessage(content='', tool_calls=[{'name': 'read_file', 'args': {'path': 'nav.html'}, 'id': f't{i}'}]),
                         ToolMessage(content=('旧过程' * 1200) + str(i), tool_call_id=f't{i}')])
    compact = manager.prepare(messages)
    assert state['context_report']['compactions'] == 1
    text = '\n'.join(str(m.content) for m in compact)
    assert '只修改导航，保留登录行为' in text
    assert 'fixed-contract' in text and 'nav.html' in text
    assert '三方结论：修复导入但保留登录校验' in text and 'verified-repair-reference' in text
    message_groups(compact[2:])  # raises for orphaned/missing results
    ref = state['context_report']['requests'][0]['raw_reference']
    assert ('旧过程' * 100) in Path(ref).read_text(encoding='utf-8')
    set_coder_state(state)
    set_tool_context(str(project), 'long', policy={'context': True})
    assert json.loads(read_progress.invoke({'reference': ref, 'limit': 1000}))['ok']
    assert not json.loads(read_progress.invoke({'reference': str(tmp_path / 'outside')}))['ok']


def test_single_oversized_protected_requirement_stops_with_saved_progress(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_CONTEXT_WINDOW_TOKENS', '500')
    monkeypatch.setenv('HARNESS_CONTEXT_OUTPUT_RESERVE', '100')
    project = tmp_path / 'site'
    project.mkdir()
    state = {'project_dir': str(project), 'user_request': '必须保留的完整约束' * 500}
    with pytest.raises(ContextWindowExceeded, match='context_window_exhausted'):
        CoderContext(state, []).prepare([SystemMessage(content='rules'), HumanMessage(content='context')])
    assert Path(state['context_report']['requests'][0]['raw_reference']).is_file()


def test_unicode_long_line_and_tail_can_be_read_exactly_after_external_edit(tmp_path):
    project = tmp_path / 'site'
    project.mkdir()
    content = '开头\r\n' + '长行Ω' * 5000 + '\r\n页尾\r\n'
    path = project / 'index.html'
    path.write_bytes(content.encode('utf-8'))
    set_tool_context(str(project), 'unicode', policy={'context': True})
    chunks = []
    offset = 0
    while True:
        result = json.loads(read_file.invoke({'path': 'index.html', 'offset': offset, 'limit': 2000}))
        chunks.append(result['content'])
        if result['next_offset'] is None:
            break
        offset = result['next_offset']
    assert ''.join(chunks) == content
    original = result['sha256']
    path.write_bytes(content.replace('页尾', '新页尾').encode('utf-8'))
    tail = json.loads(read_file.invoke({'path': 'index.html', 'start_line': 3}))
    assert tail['content'] == '新页尾\r\n'
    assert tail['sha256'] != original
    found = json.loads(search_code.invoke({'query': '新页尾'}))
    assert found['matches'][0]['line'] == 3
    (project / '.env').write_text('KEY=forbidden-marker')
    assert not json.loads(search_code.invoke({'query': 'forbidden-marker'}))['matches']


def test_context_output_reserve_is_the_actual_router_output_cap(monkeypatch):
    from core.model_router import ModelRouter
    from workflow.budget import budget_scope, output_limit_scope
    captured = {}
    class Client:
        def __init__(self, **kwargs):
            captured.update(kwargs)
        def invoke(self, messages, config=None):
            return AIMessage(content='ok', usage_metadata={'input_tokens': 50, 'output_tokens': 10, 'total_tokens': 60})
    monkeypatch.setattr('core.model_router.ChatOpenAI', Client)
    state = {}
    with budget_scope(state), output_limit_scope(500):
        assert ModelRouter().route('reasoning', [HumanMessage(content='request')], allow_degraded=False) == 'ok'
    assert captured['max_tokens'] == 500
    assert state['budget_report']['tokens'] == 60
