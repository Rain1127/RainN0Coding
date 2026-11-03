"""Owner-scoped steering queue and safe Coder boundary handling."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time

from pydantic import BaseModel, Field

from workflow.acceptance import AcceptanceFeature, AcceptanceProposal, ASSERTIONS, freeze_contract
from workflow.run_control import RunControlError

TERMINAL = {'completed', 'failed', 'cancelled'}
REQUIRED_POLICY = ('acceptance', 'editing', 'events', 'instructions')
MAX_INSTRUCTIONS = 8


def available(policy):
    return all((policy or {}).get(key) is True for key in REQUIRED_POLICY)


def migrate(db):
    db.execute('''CREATE TABLE IF NOT EXISTS generation_instructions(
        seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, instruction_id TEXT NOT NULL,
        target TEXT NOT NULL, content TEXT NOT NULL, status TEXT NOT NULL,
        reason TEXT, step_id TEXT, contract_version INTEGER,
        created_at REAL NOT NULL, updated_at REAL NOT NULL, UNIQUE(run_id,instruction_id))''')


def owner_run(db, run_id, user_id, app_id):
    row = db.execute('SELECT * FROM generation_runs WHERE run_id=? AND user_id=? AND app_id=?',
                     (run_id, user_id, app_id)).fetchone()
    if row is None:
        raise RunControlError('Generation task not found', 404)
    return row


def list_for_owner(store, run_id, user_id, app_id):
    with store.connection() as db:
        run = owner_run(db, run_id, user_id, app_id)
        rows = db.execute('SELECT * FROM generation_instructions WHERE run_id=? ORDER BY seq', (run_id,)).fetchall()
        return {'enabled': available(json.loads(run['payload']).get('harness_policy')),
                'run_status': run['status'], 'instructions': [dict(row) for row in rows]}


def submit(store, run_id, user_id, app_id, instruction_id, target, content):
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        run = owner_run(db, run_id, user_id, app_id)
        prior = db.execute('SELECT * FROM generation_instructions WHERE run_id=? AND instruction_id=?',
                           (run_id, instruction_id)).fetchone()
        if prior:
            if prior['target'] != target or prior['content'] != content:
                raise RunControlError('Instruction ID already has a different payload')
            return dict(prior)
        if not available(json.loads(run['payload']).get('harness_policy')):
            raise RunControlError('Instructions are unavailable for this run')
        if run['status'] in TERMINAL:
            raise RunControlError('Generation has ended')
        count = db.execute('SELECT COUNT(*) FROM generation_instructions WHERE run_id=?', (run_id,)).fetchone()[0]
        if count >= MAX_INSTRUCTIONS:
            raise RunControlError('Run instruction limit reached')
        now = time.time()
        db.execute('INSERT INTO generation_instructions(run_id,instruction_id,target,content,status,created_at,updated_at) '
                   "VALUES (?,?,?,?,'queued',?,?)", (run_id, instruction_id, target, content, now, now))
        return dict(db.execute('SELECT * FROM generation_instructions WHERE run_id=? AND instruction_id=?',
                               (run_id, instruction_id)).fetchone())


def cancel(store, run_id, user_id, app_id, instruction_id):
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        owner_run(db, run_id, user_id, app_id)
        row = db.execute('SELECT * FROM generation_instructions WHERE run_id=? AND instruction_id=?',
                         (run_id, instruction_id)).fetchone()
        if not row:
            raise RunControlError('Instruction not found', 404)
        if row['status'] in ('queued', 'next_run_ready'):
            db.execute("UPDATE generation_instructions SET status='cancelled',reason='cancelled_by_owner',updated_at=? "
                       'WHERE seq=?', (time.time(), row['seq']))
        elif row['status'] != 'cancelled':
            raise RunControlError('Instruction already crossed its processing boundary')
        return dict(db.execute('SELECT * FROM generation_instructions WHERE seq=?', (row['seq'],)).fetchone())


def settle(db, run_id, status):
    if status not in TERMINAL:
        return
    now = time.time()
    db.execute("UPDATE generation_instructions SET status='next_run_ready',updated_at=? "
               "WHERE run_id=? AND target='next_run' AND status='queued'", (now, run_id))
    db.execute("UPDATE generation_instructions SET status='cancelled',reason='run_ended_before_model_receipt',updated_at=? "
               "WHERE run_id=? AND target='next_step' AND status IN ('queued','planning','prepared')", (now, run_id))


def claim(journal):
    with journal.store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        state = journal.state
        run = owner_run(db, journal.run_id, str(state['user_id']), str(state['app_id']))
        if run['status'] in TERMINAL or run['pause_requested']:
            return None
        row = db.execute("SELECT * FROM generation_instructions WHERE run_id=? AND target='next_step' "
                         "AND status IN ('queued','planning','prepared') "
                         "ORDER BY CASE WHEN status='queued' THEN 1 ELSE 0 END,seq LIMIT 1", (journal.run_id,)).fetchone()
        if row and row['status'] == 'queued':
            db.execute("UPDATE generation_instructions SET status='planning',updated_at=? WHERE seq=?", (time.time(), row['seq']))
        return dict(row) if row else None


def transition(journal, instruction_id, status, *, reason=None):
    with journal.store.connection() as db:
        db.execute("UPDATE generation_instructions SET status=?,reason=?,updated_at=? WHERE run_id=? AND instruction_id=? "
                   "AND status IN ('planning','prepared')", (status, reason, time.time(), journal.run_id, instruction_id))


def receipt(journal, step_id, ids, contract_version):
    if not ids:
        return
    with journal.store.connection() as db:
        for instruction_id in ids:
            changed = db.execute("UPDATE generation_instructions SET status='included',step_id=?,contract_version=?,updated_at=? "
                                 "WHERE run_id=? AND instruction_id=? AND status='prepared'",
                                 (step_id, contract_version, time.time(), journal.run_id, instruction_id)).rowcount
            if changed:
                journal._insert_event(db, 'instruction_included', step_id, {
                    'instruction_id': instruction_id, 'request_id': journal.run_id,
                    'contract_version': contract_version, 'status': 'included',
                }, instruction_id)


class Correction(BaseModel):
    files: list[str] | None = Field(default=None, max_length=30)
    features: list[AcceptanceFeature] = Field(default_factory=list, max_length=12)
    rejection: str = Field(default='', max_length=240)


def propose(state, text):
    from llm_factory import create_json_parser
    from prompt_builder import compose_messages
    parser = create_json_parser(Correction, 'Return JSON matching ' + json.dumps(Correction.model_json_schema()),
                                group='structured', agent_name='run_correction', allow_degraded=False)
    return parser(compose_messages(agent='run_correction', system=(
        '判断这条纠偏能否安全应用到当前任务。禁止扩展原修改权限，且保留未被明确更改的验收条件。'
        '只在需要收紧文件范围时返回 files，其他情况返回 null。改变行为必须返回独立可执行的 features，'
        '每个 source_quote 必须逐字来自该条纠偏，保留行为也可用新断言验证。'
        '明确改变既有功能时列出对应 supersedes ID，保留其他条件。浏览器会主动加载候选页面；页面加载不是外部前提。'
        '可执行条件的 preconditions=[]、unverified_reason=""。缺前提或指令不属于当前任务时填写 rejection。'
    ), context=json.dumps({
        'goal': state.get('user_request'), 'plan': state.get('change_plan'),
        'scope': state.get('instruction_scope'), 'architecture': state.get('architecture'),
        'contract': state.get('acceptance_contract'),
    }, ensure_ascii=False), request=text), user_id=state['user_id'])


def validated_scope(state, requested):
    if requested is None:
        return None
    from tools.path_guard import resolve_project_path
    root = Path(state['project_dir']).resolve()
    previous = state.get('instruction_scope')
    if previous is None:
        previous = ((state.get('change_plan') or {}).get('files', []) if state['mode'] == 'modify'
                    else [item['path'] for item in (state.get('architecture') or {}).get('file_list', [])])
    paths = sorted({Path(resolve_project_path(str(root), path)).relative_to(root).as_posix() for path in requested})
    if not paths or not set(paths).issubset(previous):
        raise ValueError('scope_would_expand_or_is_empty')
    if state['mode'] == 'modify':
        # A correction cannot retroactively permit changes to now-protected files.
        base = state.get('artifact_base') or {}
        for path in set(previous) - set(paths):
            full = Path(resolve_project_path(str(root), path))
            actual = hashlib.sha256(full.read_bytes()).hexdigest() if full.is_file() else None
            if actual != base.get(path):
                raise ValueError('scope_conflicts_with_existing_candidate_edits')
    return paths


def prepare_next(journal):
    state = journal.state
    if not available(state.get('harness_policy')):
        return None
    row = claim(journal)
    if not row:
        return None
    instruction_id, text = row['instruction_id'], row['content']
    active = state.setdefault('active_instructions', [])
    if not any(item['instruction_id'] == instruction_id for item in active):
        saved = journal.frame.get('instruction_plan')
        try:
            if saved and saved['instruction_id'] == instruction_id:
                correction = Correction.model_validate(saved['proposal'])
            else:
                correction = propose(state, text)
                if correction is None:
                    raise ValueError('correction_planner_unavailable')
                journal.save(instruction_plan={'instruction_id': instruction_id, 'proposal': correction.model_dump()})
            if correction.rejection:
                raise ValueError('correction_incompatible_with_current_task')
            paths = validated_scope(state, correction.files)
            if not correction.features and (paths is None or paths == sorted((state.get('change_plan') or {}).get('files', []))):
                raise ValueError('correction_has_no_verified_effect')
            for feature in correction.features:
                if not feature.source_quote or feature.source_quote not in text or feature.unverified_reason or feature.preconditions or (
                    not any(step.action in ASSERTIONS for step in feature.steps)
                ):
                    raise ValueError('correction_conditions_not_independently_verifiable')
            replaced = [feature_id for feature in correction.features for feature_id in feature.supersedes]
            prior = state.get('acceptance_contract') or {}
            reason = 'instruction:' + instruction_id
            already_fixed = prior.get('change_reason') == reason
            if not already_fixed and (len(replaced) != len(set(replaced)) or set(replaced) - {feature['id'] for feature in prior.get('features', [])}):
                raise ValueError('correction_supersedes_an_unknown_or_duplicate_condition')
        except Exception as exc:
            from workflow.budget import BudgetExceeded
            reason = str(exc) if isinstance(exc, (ValueError, BudgetExceeded)) else 'correction_planner_unavailable'
            transition(journal, instruction_id, 'rejected', reason=reason[:240])
            journal.save(instruction_plan=None)
            journal.event('instruction_rejected', journal.epoch + ':i-' + instruction_id,
                          {'instruction_id': instruction_id, 'status': 'rejected', 'reason': reason[:240]})
            if isinstance(exc, BudgetExceeded):
                raise
            return None
        # From here the private plan is authoritative. An I/O failure is not a
        # semantic rejection and must never publish a contradictory receipt.
        if correction.features and not already_fixed:
            freeze_contract(state, AcceptanceProposal(features=correction.features), reason=reason,
                            allow_supersede=True, active_request=text)
        if paths is not None:
            state['instruction_scope'] = paths
            state['change_plan'] = {**(state.get('change_plan') or {}), 'files': paths}
        active.append({'instruction_id': instruction_id, 'content': text})
        journal.save(instruction_plan=None)
    transition(journal, instruction_id, 'prepared')
    return instruction_id
