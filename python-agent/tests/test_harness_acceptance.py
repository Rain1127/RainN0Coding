"""P1 release gates: real browser behavior and immutable contract authority."""
import json
from pathlib import Path
import pytest
from workflow.acceptance import AcceptanceProposal, freeze_contract, validate_fixed_contract


HTML = '''<!doctype html><meta charset="utf-8"><h1>验收样例</h1>
<input id="search"><select id="filter"><option value="all">全部</option><option value="veg">蔬菜</option></select>
<div class="row" data-type="fruit">苹果</div><div class="row" data-type="fruit">香蕉</div><div class="row" data-type="veg">胡萝卜</div>
<button id="next">下一页</button><p id="page">第一页</p>
<form><input id="name" required><button type="submit">保存</button></form><p id="feedback"></p>
<script>
document.querySelector('#search').oninput=e=>document.querySelectorAll('.row').forEach(r=>r.hidden=!r.textContent.includes(e.target.value));
document.querySelector('#filter').onchange=e=>document.querySelectorAll('.row').forEach(r=>r.hidden=e.target.value!=='all'&&r.dataset.type!==e.target.value);
document.querySelector('#next').onclick=()=>document.querySelector('#page').textContent='第二页';
document.querySelector('form').onsubmit=e=>{e.preventDefault();document.querySelector('#feedback').textContent='已保存'};
</script>'''


def make_state(tmp_path):
    project = tmp_path / 'site'
    project.mkdir()
    (project / 'index.html').write_text(HTML, encoding='utf-8')
    state = {'project_dir': str(project), 'user_request': '搜索、筛选、分页、表单反馈', 'artifact_run_id': 'p1-browser'}
    proposal = AcceptanceProposal.model_validate({'features': [
        {'name': '搜索', 'source_quote': '搜索', 'steps': [
            {'action': 'fill', 'selector': '#search', 'value': '苹果'},
            {'action': 'count', 'selector': '.row:visible', 'count': 1},
            {'action': 'text', 'value': '苹果'}]},
        {'name': '筛选', 'source_quote': '筛选', 'steps': [
            {'action': 'select', 'selector': '#filter', 'value': 'veg'},
            {'action': 'count', 'selector': '.row:visible', 'count': 1},
            {'action': 'text', 'value': '胡萝卜'}]},
        {'name': '分页', 'source_quote': '分页', 'steps': [
            {'action': 'click', 'selector': '#next'}, {'action': 'text', 'value': '第二页'}]},
        {'name': '表单反馈', 'source_quote': '表单反馈', 'steps': [
            {'action': 'fill', 'selector': '#name', 'value': '示例用户'},
            {'action': 'click', 'selector': 'button[type=submit]'}, {'action': 'text', 'value': '已保存'}]},
    ]})
    freeze_contract(state, proposal)
    return state


@pytest.mark.parametrize('feature,event', [('搜索', 'oninput'), ('筛选', 'onchange'), ('分页', 'onclick'), ('表单反馈', 'onsubmit')])
def test_page_load_cannot_hide_behavior_failure(tmp_path, feature, event):
    state = make_state(tmp_path)
    project = Path(state['project_dir'])
    (project / 'index.html').write_text(HTML.replace('.' + event + '=', '.unused='), encoding='utf-8')
    result = validate_fixed_contract(state, project, tmp_path / 'evidence')
    assert result['status'] == 'failed', result
    assert next(f for f in result['features'] if f['name'] == feature)['status'] == 'failed'
    assert result['contract_hash'] == state['acceptance_contract']['content_hash']
    assert result['artifact_run_id'] == 'p1-browser'


def test_fixed_conditions_execute_and_unknowns_never_pass(tmp_path):
    state = make_state(tmp_path)
    project = Path(state['project_dir'])
    assert validate_fixed_contract(state, project, tmp_path / 'evidence')['status'] == 'succeeded'
    freeze_contract(state, AcceptanceProposal.model_validate({'features': [
        {'name': '外部账号', 'source_quote': '', 'unverified_reason': '待确认：缺少账号和接口规范'}]}), reason='additional requirement')
    assert state['acceptance_contract']['version'] == 2
    assert len(state['acceptance_contract']['features']) == 5
    assert validate_fixed_contract(state, project, tmp_path / 'unknown')['status'] == 'unverified'


def test_coder_export_cannot_change_fixed_failure_condition(tmp_path):
    state = make_state(tmp_path)
    project = Path(state['project_dir'])
    forged = dict(state['acceptance_contract'], features=[], status='passed')
    (project / 'acceptance.json').write_text(json.dumps(forged), encoding='utf-8')
    result = validate_fixed_contract(state, project, tmp_path / 'forgery')
    assert result['status'] == 'unverified'
    assert result['failure_kind'] == 'specification'


def test_new_user_requirement_can_supersede_color_but_repair_cannot(tmp_path):
    project = tmp_path / 'site'
    project.mkdir()
    state = {'project_dir': str(project), 'user_request': '导航设为红色', 'artifact_run_id': 'color', 'mode': 'new'}
    old = freeze_contract(state, AcceptanceProposal.model_validate({'features': [
        {'name': '导航颜色', 'source_quote': '导航设为红色', 'steps': [
            {'action': 'style', 'selector': 'nav', 'attribute': 'background-color', 'value': 'rgb(255, 0, 0)'}]}]}))
    original_path = Path(state['acceptance_contract_path'])
    proposal = AcceptanceProposal.model_validate({'features': [
        {'name': '导航颜色', 'source_quote': '导航改为蓝色', 'supersedes': [old['features'][0]['id']], 'steps': [
            {'action': 'style', 'selector': 'nav', 'attribute': 'background-color', 'value': 'rgb(0, 0, 255)'}]}]})
    state.update(mode='modify', user_request='导航改为蓝色')
    with pytest.raises(ValueError):
        freeze_contract(state, proposal, reason='repair of failed condition')
    current = freeze_contract(state, proposal, reason='new user requirement', allow_supersede=True)
    assert len(current['features']) == 1
    assert current['version'] == 2
    assert json.loads(original_path.read_text()) == old
    assert current['previous_contract_hash'] == old['content_hash']
    (project / 'index.html').write_text('<nav style="background:blue">首页</nav>')
    assert validate_fixed_contract(state, project, tmp_path / 'new-color')['status'] == 'succeeded'
