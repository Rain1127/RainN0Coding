"""Immutable, versioned requirement contracts. Generated code never owns results."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field, ValidationError, AliasChoices, model_validator

ASSERTIONS = {'text', 'absent_text', 'count', 'value', 'visible', 'attribute', 'style', 'invalid', 'click_change'}


class AcceptanceStep(BaseModel):
    action: Literal['fill', 'press', 'click', 'check', 'select', 'text', 'absent_text',
                    'count', 'value', 'visible', 'attribute', 'style', 'invalid', 'click_change']
    selector: str = Field(default='', max_length=500)
    value: str = Field(default='', max_length=2000, description='Machine assertion value. text/absent_text MUST contain nonempty exact text here; attribute/style use the expected property value.')
    expected: str = Field(default='', max_length=2000, description='Optional human-readable step description; not a substitute for value/count.')
    count: int | None = Field(default=None, ge=0, le=10000)
    scope: Literal['visible', 'all'] = Field(default='visible', description='count of displayed search/filter/page results uses visible; structural DOM checks such as script[src] and link use all.')
    attribute: str = Field(default='', max_length=80, validation_alias=AliasChoices('attribute', 'property', 'css_property'),
        description='REQUIRED for style/attribute: CSS property (e.g. background-color) or HTML attribute name. Put the expected computed value in value.')

    @model_validator(mode='after')
    def valid_action(self):
        if self.action not in {'text', 'absent_text'} and not self.selector:
            raise ValueError('This action requires a selector')
        if self.action == 'count' and self.count is None:
            raise ValueError('count assertion requires an expected count')
        if self.action in {'text', 'absent_text'} and not self.value:
            raise ValueError('Text assertion cannot be empty')
        if self.action in {'attribute', 'style'} and not self.attribute.replace('-', '').isalnum():
            raise ValueError('Expected an attribute/property name, not executable code')
        return self


class AcceptanceFeature(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    source_quote: str = Field(default='', max_length=2000)
    preconditions: list[str] = Field(default_factory=list, max_length=10)
    steps: list[AcceptanceStep] = Field(default_factory=list, max_length=40)
    unverified_reason: str = Field(default='', max_length=1000)
    supersedes: list[str] = Field(default_factory=list, max_length=30,
        description='Prior feature IDs explicitly changed by this new user requirement; never used during repair of the same request.')


class AcceptanceProposal(BaseModel):
    features: list[AcceptanceFeature] = Field(min_length=1, max_length=30)


def content_hash(value):
    body = {k: v for k, v in value.items() if k != 'content_hash'}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def validate_contract(contract):
    if contract.get('schema_version') != 1 or content_hash(contract) != contract.get('content_hash'):
        raise ValueError('Acceptance contract content hash/version mismatch')
    ids = set()
    for feature in contract['features']:
        AcceptanceFeature.model_validate(feature)
        if not feature.get('id') or feature['id'] in ids:
            raise ValueError('Missing/duplicate feature identity')
        ids.add(feature['id'])
    return contract


def previous_contract(state):
    path = Path(state['project_dir']) / 'acceptance.json'
    if not path.is_file():
        return None
    try:
        return validate_contract(json.loads(path.read_text(encoding='utf-8')))
    except (ValueError, KeyError, TypeError):
        return None


def freeze_contract(state, proposal, *, reason='initial requirements', allow_supersede=False, active_request=None):
    prior = state.get('acceptance_contract') or (previous_contract(state) if state.get('mode') == 'modify' else None)
    request = active_request if active_request is not None else state.get('user_request', '')
    features = []
    for spec in proposal.features:
        item = spec.model_dump()
        item['id'] = 'F-' + hashlib.sha256((spec.source_quote + '\n' + spec.name).encode()).hexdigest()[:16]
        if not spec.source_quote or spec.source_quote not in request:
            item['unverified_reason'] = '待确认：功能缺少可核对的原始需求引用'
        if not any(step.action in ASSERTIONS for step in spec.steps):
            item['unverified_reason'] = item['unverified_reason'] or '待确认：没有受支持的行为断言'
        features.append(item)
    # Only a new user request, before coding, can explicitly supersede conditions.
    # Prior immutable versions and the replacement reason remain available.
    superseded = []
    if prior:
        retained = {item['id']: item for item in prior['features']}
        for item in features:
            for replaced in item.get('supersedes', []):
                if not (allow_supersede and (state.get('mode') == 'modify' or active_request is not None) and
                        request != prior.get('source_request') and item['source_quote'] and
                        item['source_quote'] in request and replaced in retained):
                    raise ValueError('Cannot supersede a fixed condition without a new attributable user requirement')
                superseded.append({'feature': retained.pop(replaced), 'replaced_by': item['id'],
                                   'source_quote': item['source_quote'], 'reason': reason})
            if item['id'] in retained and item != retained[item['id']]:
                item['id'] += '-v' + str(prior['version'] + 1)
            retained[item['id']] = item
        features = list(retained.values())
    contract = {'schema_version': 1, 'contract_id': prior['contract_id'] if prior else 'AC-' + hashlib.sha256(request.encode()).hexdigest()[:20],
                'version': prior['version'] + 1 if prior else 1, 'run_id': state.get('artifact_run_id', ''),
                'source_request': request, 'change_reason': reason, 'features': features,
                'previous_contract_hash': prior.get('content_hash') if prior else None, 'superseded': superseded}
    contract['content_hash'] = content_hash(contract)
    # The authoritative copy is outside the Coder's project root.
    project = Path(state['project_dir'])
    namespace = hashlib.sha256((str(project.resolve()) + contract['run_id']).encode()).hexdigest()[:24]
    directory = project.parent / '.harness-contracts' / namespace
    directory.mkdir(parents=True, exist_ok=True)
    authoritative = directory / f"v{contract['version']}-{contract['content_hash']}.json"
    text = json.dumps(contract, ensure_ascii=False, indent=2)
    if authoritative.exists() and authoritative.read_text(encoding='utf-8') != text:
        raise ValueError('Cannot overwrite a fixed acceptance contract')
    from workflow.artifacts import _atomic_json
    if not authoritative.exists():
        _atomic_json(authoritative, contract)
    _atomic_json(project / 'acceptance.json', contract)
    state['acceptance_contract'] = contract
    state['acceptance_contract_path'] = str(authoritative)
    from workflow.run_journal import active_journal
    journal = active_journal.get()
    if journal:
        journal.contract_fixed(contract)
    return contract


def ensure_contract(state):
    from workflow.harness_policy import enabled
    if not enabled(state, 'acceptance'):
        return None
    if state.get('acceptance_contract'):
        return validate_contract(state['acceptance_contract'])
    # Contract publication itself is a server effect. Recover an already fixed
    # current-run contract before asking the model for another version.
    project = Path(state['project_dir'])
    namespace = hashlib.sha256((str(project.resolve()) + state.get('artifact_run_id', '')).encode()).hexdigest()[:24]
    directory = project.parent / '.harness-contracts' / namespace
    recovered = []
    for path in directory.glob('v*-*.json'):
        saved = validate_contract(json.loads(path.read_text(encoding='utf-8')))
        if saved.get('run_id') == state.get('artifact_run_id', '') and saved.get('source_request') == state.get('user_request', ''):
            recovered.append((saved['version'], path, saved))
    if recovered:
        version = max(item[0] for item in recovered)
        latest = [item for item in recovered if item[0] == version]
        if len(latest) != 1:
            raise ValueError('Conflicting fixed contract versions; manual reconciliation required')
        _, path, saved = latest[0]
        from workflow.artifacts import _atomic_json
        _atomic_json(project / 'acceptance.json', saved)
        state.update(acceptance_contract=saved, acceptance_contract_path=str(path))
        return saved
    from llm_factory import create_json_parser
    from prompt_builder import compose_messages
    parser = create_json_parser(AcceptanceProposal,
        'Output ONLY JSON matching this schema: ' + json.dumps(AcceptanceProposal.model_json_schema(), ensure_ascii=False),
        group='structured', agent_name='acceptance_contract', allow_degraded=False)
    previous = previous_contract(state) if state.get('mode') == 'modify' else None
    messages = compose_messages(agent='acceptance_contract',
        system='把明确需求转为独立行为验收。仅使用受约束动作和断言，禁止脚本。source_quote 必须逐字引用本次原始需求。'
               'text/absent_text 的 value 必须是非空的精确预期文本，不可只填 selector 或 expected。断言元素可见请用 visible。'
               'style 动作必须同时填写 attribute（例如 background-color）和 value（浏览器计算值，例如蓝色为 rgb(0, 0, 255)）。'
               '搜索/筛选/分页的结果数量用 count 且 scope=visible；隐藏结果不要求删除DOM。script/link等结构检查用 scope=all。'
               '搜索/筛选必须断言结果集合，分页必须断言切换后的内容，表单必须断言实际反馈。'
               '新需求明确改变旧行为时，在新功能 supersedes 中列出被替代的旧功能ID；仅替代明确改变的条件，其他条件保留。'
               '缺接口、账号、业务规则或不支持的能力写 unverified_reason=待确认，不得捏造。'
               'preconditions 只记录未满足的外部前提；已满足时为空。新页面可约定稳定的 data-testid。'
               '保留既有行为；CSS属性断言使用浏览器计算值。',
        context=json.dumps({'prd': state.get('prd'), 'plan': state.get('change_plan'),
                            'previous_contract': previous,
                            'existing_files': state.get('existing_code_files', [])}, ensure_ascii=False),
        request=state.get('user_request', ''))
    for attempt in range(2):
        state['acceptance_generation_attempts'] = attempt + 1
        try:
            proposal = parser(messages, user_id=state.get('user_id'))
            break
        except Exception as exc:
            root = exc
            while root.__cause__ is not None:
                root = root.__cause__
            if isinstance(root, ValidationError):
                diagnostic = json.dumps([{'field': e['loc'], 'message': e['msg'],
                    'fields_present': sorted(e['input']) if isinstance(e.get('input'), dict) else []}
                    for e in root.errors(include_url=False)], ensure_ascii=False)
            elif isinstance(root, json.JSONDecodeError):
                diagnostic = f'JSON invalid at line {root.lineno}, column {root.colno}'
            else:
                raise ValueError('acceptance_generation_failed: ' + type(root).__name__) from exc
            if attempt:
                raise ValueError('acceptance_schema_invalid: ' + diagnostic) from exc
            from langchain_core.messages import HumanMessage
            messages = messages + [HumanMessage(content='上次输出未通过结构校验，请保持原需求并修正字段，不可删除验收条件。错误：' + diagnostic)]
    if proposal is None:
        raise ValueError('Acceptance contract unavailable; no coding started')
    return freeze_contract(state, proposal, reason='new user requirement' if previous else 'initial requirements',
                           allow_supersede=bool(previous))


def validate_fixed_contract(state, root, report_dir):
    from workflow.runtime_validation import validate_candidate_page
    try:
        contract = validate_contract(state['acceptance_contract'])
        stored = json.loads(Path(state['acceptance_contract_path']).read_text(encoding='utf-8'))
        exported = json.loads((Path(state['project_dir']) / 'acceptance.json').read_text(encoding='utf-8'))
        if stored != contract or exported != contract:
            raise ValueError('Acceptance contract changed during coding')
    except (ValueError, KeyError, OSError, TypeError) as exc:
        return {'status': 'unverified', 'failure_kind': 'specification', 'log': str(exc), 'features': []}
    report_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for feature in contract['features']:
        if feature.get('unverified_reason') or feature.get('preconditions') or not feature['steps']:
            observation = {'status': 'unverified', 'failure_kind': 'specification',
                           'log': feature.get('unverified_reason') or '待确认：外部前提未满足或无可执行步骤', 'steps': []}
        else:
            observation = validate_candidate_page(state, root, {'version': str(contract['version']), 'steps': feature['steps']},
                                                  report_dir / feature['id'])
        results.append({'id': feature['id'], 'name': feature['name'], **observation})
    status = 'failed' if any(x['status'] == 'failed' for x in results) else (
        'succeeded' if results and all(x['status'] == 'succeeded' for x in results) else 'unverified')
    result = {'status': status, 'interaction_status': 'passed' if status == 'succeeded' else status,
              'failure_kind': next((x.get('failure_kind') for x in results if x['status'] == status), None) if status != 'succeeded' else None,
              'contract_id': contract['contract_id'], 'contract_version': contract['version'],
              'contract_hash': contract['content_hash'], 'artifact_run_id': state.get('artifact_run_id'),
              'features': results, 'steps': [step for f in results for step in f.get('steps', [])],
              'log': '\n'.join(f"{x['id']}: {x.get('log', '')}" for x in results if x['status'] != 'succeeded') or 'All fixed behavior conditions passed'}
    (report_dir / 'acceptance-report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result
