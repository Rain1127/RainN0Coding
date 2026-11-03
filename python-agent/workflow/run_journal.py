"""Tool-boundary durability. Public events are redacted; recovery state is private.

LangGraph owns phase scheduling. This journal owns the in-progress Coder frame.
File effects are reconciled by before/after hashes, never by missing logs alone.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
from threading import Thread, Event
from langchain_core.messages import messages_to_dict, messages_from_dict
from benchmark.redaction import redact

active_journal = ContextVar('active_coder_journal', default=None)
READ_ONLY = {'read_file', 'list_files', 'search_code', 'retrieve_context', 'read_progress', 'exit_tool'}
FILE_WRITES = {'create_file', 'modify_file', 'apply_patch', 'delete_file'}
STATE_FIELDS = ('user_request', 'user_id', 'app_id', 'mode', 'project_dir', 'artifact_run_id',
    'harness_policy', 'architecture', 'prd', 'change_plan', 'acceptance_contract', 'acceptance_contract_path',
    'acceptance_generation_attempts', 'context_report', 'retrieval_events', 'coder_current_error',
    'review', 'repair_experiences', 'build_repair_context', 'code_files', 'coder_file_hashes', 'phase', 'error',
    'active_instructions', 'instruction_scope')


class RecoveryConflict(RuntimeError):
    pass


def migrate_public(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS harness_migrations(version INTEGER PRIMARY KEY, applied_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS run_events(
            seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, step_id TEXT NOT NULL,
            event_type TEXT NOT NULL, payload TEXT NOT NULL, created_at REAL NOT NULL,
            event_key TEXT NOT NULL UNIQUE);
        CREATE INDEX IF NOT EXISTS run_events_cursor ON run_events(run_id,seq);
        CREATE TABLE IF NOT EXISTS tool_executions(
            run_id TEXT NOT NULL, epoch TEXT NOT NULL, step_id TEXT NOT NULL, tool_call_id TEXT NOT NULL,
            tool_name TEXT NOT NULL, path TEXT, before_hash TEXT, after_hash TEXT,
            status TEXT NOT NULL, result_summary TEXT, elapsed_ms REAL,
            PRIMARY KEY(run_id,epoch,step_id));
    ''')
    db.execute('INSERT OR IGNORE INTO harness_migrations VALUES(1,?)', (time.time(),))


def public_events(store, run_id, user_id, app_id, after=0, limit=100):
    store.get(run_id, user_id, app_id)
    limit = max(1, min(200, int(limit)))
    with store.connection() as db:
        rows = db.execute('SELECT * FROM run_events WHERE run_id=? AND seq>? ORDER BY seq LIMIT ?',
                          (run_id, max(0, int(after)), limit + 1)).fetchall()
    items = [{'seq': r['seq'], 'run_id': run_id, 'step_id': r['step_id'], 'type': r['event_type'],
              'timestamp': r['created_at'], 'payload': json.loads(r['payload'])} for r in rows[:limit]]
    return {'events': items, 'step_cursor': items[-1]['seq'] if items else max(0, int(after)), 'has_more': len(rows) > limit}


class RunJournal:
    def __init__(self, state, store, run_id, *, standalone=False):
        self.state, self.store, self.run_id, self.standalone = state, store, run_id, standalone
        store.get(run_id, str(state['user_id']), str(state['app_id']))
        self.epoch = hashlib.sha256((state.get('artifact_run_id', '') + ':' + str(state.get('retry_count', 0)) +
                                    ':' + str(state.get('build_repair_count', 0))).encode()).hexdigest()[:20]
        self.private_path = store.path.with_suffix('.harness-private.db')
        with self.private() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS coder_frames(
                run_id TEXT NOT NULL, epoch TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(run_id,epoch));
                CREATE TABLE IF NOT EXISTS model_records(
                run_id TEXT NOT NULL, epoch TEXT NOT NULL, step_id TEXT NOT NULL, request_hash TEXT NOT NULL,
                request_payload TEXT NOT NULL, response_payload TEXT, PRIMARY KEY(run_id,epoch,step_id));
                CREATE TABLE IF NOT EXISTS tool_results(
                run_id TEXT NOT NULL, epoch TEXT NOT NULL, step_id TEXT NOT NULL, result TEXT NOT NULL,
                PRIMARY KEY(run_id,epoch,step_id));
                CREATE TABLE IF NOT EXISTS tool_clocks(
                run_id TEXT NOT NULL, epoch TEXT NOT NULL, step_id TEXT NOT NULL, observed_seconds REAL NOT NULL,
                inflight INTEGER NOT NULL, updated_at REAL NOT NULL, PRIMARY KEY(run_id,epoch));''')
            row = db.execute('SELECT payload FROM coder_frames WHERE run_id=? AND epoch=?', (run_id, self.epoch)).fetchone()
        self.recovering = row is not None
        self.frame = json.loads(row[0]) if row else {'messages': [], 'round': 1, 'next_tool': 0,
            'response_pending': False, 'completed': False, 'model_sequence': 0, 'state': {}}
        if row:
            saved = self.frame['state']
            for key in ('user_id', 'app_id', 'project_dir', 'artifact_run_id'):
                if str(saved.get(key, '')) != str(state.get(key, '')):
                    raise RecoveryConflict('recovery_identity_or_artifact_mismatch')
            state.update(saved)
            from workflow.budget import active_budget
            budget = active_budget.get()
            if budget and self.frame.get('budget'):
                budget.data = dict(self.frame['budget'])
                budget.pending = 0
                budget.phase_started = time.monotonic()
                if self.frame.get('model_inflight'):
                    with self.private() as db:
                        completed = db.execute('SELECT response_payload,request_payload FROM model_records WHERE run_id=? AND epoch=? AND step_id=?',
                            (self.run_id, self.epoch, self.frame.get('request_step'))).fetchone()
                    if completed and completed[0]:
                        from request_context import normalize_llm_usage
                        response = messages_from_dict([json.loads(completed[0])])[0]
                        budget.pending = self.frame.get('model_pending_tokens', 0)
                        budget.observe(normalize_llm_usage(response, json.loads(completed[1])['model']))
                        self.frame['model_inflight'] = False
                    else:
                        budget.data.update(usage_complete=False, cost_complete=False, breakdown_complete=False)
                        budget.data['reserved_active_seconds'] = budget.data.get('reserved_active_seconds', 0) + self.frame.get('model_timeout_seconds', 0)
                        budget.data['unknown_model_requests'] = budget.data.get('unknown_model_requests', 0) + 1
                        self.frame['model_inflight'] = False
                        self.event('model_interrupted', self.frame['request_step'], {'status': 'outcome_unknown',
                            'time_reservation_seconds': self.frame.get('model_timeout_seconds', 0)})
                with self.private() as db:
                    clock = db.execute('SELECT step_id,observed_seconds,inflight FROM tool_clocks WHERE run_id=? AND epoch=?',
                                       (self.run_id, self.epoch)).fetchone()
                    if clock:
                        budget.data['active_seconds'] = max(budget.data['active_seconds'], clock[1])
                    if clock and clock[2]:
                        # Private heartbeats retain observed execution. The final
                        # uncertain interval is reserved, never reported as observed.
                        budget.data['reserved_active_seconds'] = budget.data.get('reserved_active_seconds', 0) + 10
                        budget.data['interrupted_tool_time_reservations'] = budget.data.get('interrupted_tool_time_reservations', 0) + 1
                        db.execute('UPDATE tool_clocks SET inflight=0 WHERE run_id=? AND epoch=?', (self.run_id, self.epoch))
                        self.frame['tool_inflight'] = None
                        db.execute('INSERT OR REPLACE INTO coder_frames VALUES(?,?,?)',
                                   (self.run_id, self.epoch, self._frame_payload()))
                budget.check()
        self.save()
        self.flush_contract_events()
        self.repair_model_events()

    @contextmanager
    def private(self):
        self.private_path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.private_path, timeout=5)
        os.chmod(self.private_path, 0o600)
        try:
            db.execute('PRAGMA journal_mode=WAL')
            with db:
                yield db
        finally:
            db.close()

    def _insert_event(self, db, kind, step, payload, suffix=''):
        payload = {'schema_version': 1, 'artifact_run_id': self.state.get('artifact_run_id'),
                   'contract_version': (self.state.get('acceptance_contract') or {}).get('version'),
                   'prompt_version': 'harness-v1', **payload}
        db.execute('INSERT OR IGNORE INTO run_events(run_id,step_id,event_type,payload,created_at,event_key) VALUES(?,?,?,?,?,?)',
                       (self.run_id, step, kind, json.dumps(redact(payload), ensure_ascii=False), time.time(),
                        self.run_id + ':' + step + ':' + kind + ':' + suffix))

    def event(self, kind, step, payload, *, suffix=''):
        with self.store.connection() as db:
            self._insert_event(db, kind, step, payload, suffix)

    def contract_fixed(self, contract):
        pending = dict(self.frame.get('pending_contract_events', {}))
        step = self.epoch + ':contract-v' + str(contract['version'])
        pending[step] = {'contract_id': contract['contract_id'], 'content_hash': contract['content_hash'],
                         'contract_version': contract['version'], 'status': 'fixed'}
        self.save(pending_contract_events=pending)
        self.flush_contract_events()

    def flush_contract_events(self):
        pending = dict(self.frame.get('pending_contract_events', {}))
        if not pending:
            return
        for step, payload in list(pending.items()):
            try:
                self.event('contract_fixed', step, payload)
            except sqlite3.Error:
                # The private frame is the authority. Reconciliation can publish
                # the timeline entry after the shared SQLite writer is available.
                continue
            del pending[step]
        self.save(pending_contract_events=pending)

    def _frame_payload(self, messages=None, **changes):
        if messages is not None:
            self.frame['messages'] = messages_to_dict(messages)
        self.frame.update(changes)
        self.frame['state'] = {key: self.state[key] for key in STATE_FIELDS if key in self.state}
        from workflow.budget import active_budget
        budget = active_budget.get()
        if budget:
            self.frame['budget'] = {**budget.data, 'active_seconds': budget.observed_active_seconds()}
        return json.dumps(self.frame, ensure_ascii=False)

    def save(self, messages=None, **changes):
        payload = self._frame_payload(messages, **changes)
        with self.private() as db:
            db.execute('INSERT OR REPLACE INTO coder_frames VALUES(?,?,?)',
                       (self.run_id, self.epoch, payload))

    def restore_messages(self):
        return messages_from_dict(self.frame['messages'])

    def prepare_model(self, messages, model, group, extra, instruction_ids=None, coder_round=None):
        request = {'messages': messages_to_dict(messages), 'model': model, 'group': group, 'schema': extra}
        normalized = json.loads(json.dumps(request, ensure_ascii=False))
        for item in normalized['messages']:
            for field in ('response_metadata', 'usage_metadata', 'id'):
                item['data'].pop(field, None)
        key = hashlib.sha256(json.dumps(normalized, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if instruction_ids:
            request.update(instruction_ids=instruction_ids,
                           contract_version=(self.state.get('acceptance_contract') or {}).get('version'))
        if coder_round is not None:
            request['coder_round'] = coder_round
        if self.recovering:
            with self.private() as db:
                row = db.execute('SELECT step_id,response_payload FROM model_records WHERE run_id=? AND epoch=? AND request_hash=? AND response_payload IS NOT NULL ORDER BY rowid DESC LIMIT 1',
                                 (self.run_id, self.epoch, key)).fetchone()
            if row:
                self.frame['request_step'] = row[0]
                response = messages_from_dict([json.loads(row[1])])[0]
                response.response_metadata['harness_replayed'] = True
                return response
        self.recovering = False
        self.frame['model_sequence'] += 1
        step = self.epoch + ':m' + str(self.frame['model_sequence'])
        self.frame['request_step'] = step
        payload = self._frame_payload(model_inflight=False)
        with self.private() as db:
            db.execute('INSERT INTO model_records VALUES(?,?,?,?,?,NULL)',
                       (self.run_id, self.epoch, step, key, json.dumps(request, ensure_ascii=False)))
            db.execute('INSERT OR REPLACE INTO coder_frames VALUES(?,?,?)', (self.run_id, self.epoch, payload))
        self.event('model_request', step, {'model': model, 'group': group, 'message_count': len(messages), 'status': 'prepared'})
        return None

    def reserved(self, model, output_limit, timeout_seconds):
        from workflow.budget import active_budget
        budget = active_budget.get()
        payload = self._frame_payload(model_inflight=True, model_pending_tokens=budget.pending if budget else 0,
                                      model_timeout_seconds=timeout_seconds)
        with self.private() as db:
            row = db.execute('SELECT request_payload FROM model_records WHERE run_id=? AND epoch=? AND step_id=?',
                             (self.run_id, self.epoch, self.frame['request_step'])).fetchone()
            request = json.loads(row[0])
            request.update(started=True, output_limit=output_limit, timeout_seconds=timeout_seconds)
            db.execute('UPDATE model_records SET request_payload=? WHERE run_id=? AND epoch=? AND step_id=?',
                       (json.dumps(request, ensure_ascii=False), self.run_id, self.epoch, self.frame['request_step']))
            db.execute('INSERT OR REPLACE INTO coder_frames VALUES(?,?,?)', (self.run_id, self.epoch, payload))
        self.event('model_submitted', self.frame['request_step'], {'model': model, 'output_limit': output_limit, 'status': 'started'})

    def capture_response(self, response, usage):
        step = self.frame.get('request_step')
        if not step:
            return
        with self.private() as db:
            request = db.execute('SELECT request_payload FROM model_records WHERE run_id=? AND epoch=? AND step_id=?',
                                 (self.run_id, self.epoch, step)).fetchone()
            request = json.loads(request[0]) if request else {}
            if request.get('coder_round') is not None:
                # Persist the returned tool batch with the reply, before a later
                # correction can be claimed on restart.
                pending = [*messages_from_dict(request['messages']), response]
                payload = self._frame_payload(pending, model_inflight=False, response_pending=True,
                                              round=request['coder_round'], next_tool=0, round_had_tool_failure=False)
            else:
                payload = self._frame_payload(model_inflight=False)
            db.execute('UPDATE model_records SET response_payload=? WHERE run_id=? AND epoch=? AND step_id=?',
                       (json.dumps(messages_to_dict([response])[0], ensure_ascii=False), self.run_id, self.epoch, step))
            db.execute('INSERT OR REPLACE INTO coder_frames VALUES(?,?,?)', (self.run_id, self.epoch, payload))
        self.event('model_result', step, {'status': 'completed', 'tool_calls': len(getattr(response, 'tool_calls', [])), 'usage': usage})
        self._instruction_receipt(step, request)

    def _instruction_receipt(self, step, request):
        from workflow.instructions import receipt
        receipt(self, step, request.get('instruction_ids'), request.get('contract_version'))

    def repair_model_events(self):
        from request_context import normalize_llm_usage
        with self.private() as db:
            rows = db.execute('SELECT step_id,request_payload,response_payload FROM model_records WHERE run_id=? AND epoch=? ORDER BY rowid',
                              (self.run_id, self.epoch)).fetchall()
        for step, request, response in rows:
            request = json.loads(request)
            self.event('model_request', step, {'model': request['model'], 'group': request['group'],
                       'message_count': len(request['messages']), 'status': 'prepared'})
            if request.get('started'):
                self.event('model_submitted', step, {'model': request['model'], 'output_limit': request.get('output_limit'), 'status': 'started'})
            if response:
                response = messages_from_dict([json.loads(response)])[0]
                self.event('model_result', step, {'status': 'completed', 'tool_calls': len(getattr(response, 'tool_calls', [])),
                           'usage': normalize_llm_usage(response, request['model'])})
                self._instruction_receipt(step, request)
            elif self.recovering and not request.get('started'):
                self.event('model_interrupted', step, {'status': 'not_submitted'})

    @contextmanager
    def tool_clock(self, step):
        from workflow.budget import active_budget
        budget = active_budget.get()
        if budget is None:
            yield
            return
        def tick(inflight):
            with self.private() as db:
                db.execute('INSERT OR REPLACE INTO tool_clocks VALUES(?,?,?,?,?,?)',
                           (self.run_id, self.epoch, step, budget.observed_active_seconds(), inflight, time.time()))
        payload = self._frame_payload(tool_inflight=step)
        with self.private() as db:
            db.execute('INSERT OR REPLACE INTO tool_clocks VALUES(?,?,?,?,?,?)',
                       (self.run_id, self.epoch, step, budget.observed_active_seconds(), 1, time.time()))
            db.execute('INSERT OR REPLACE INTO coder_frames VALUES(?,?,?)', (self.run_id, self.epoch, payload))
        stop = Event()
        heartbeat_error = []
        def heartbeat():
            while not stop.wait(0.25):
                try: tick(1)
                except Exception as exc:
                    heartbeat_error.append(exc)
                    return
        thread = Thread(target=heartbeat, daemon=True)
        thread.start()
        try:
            yield
        finally:
            stop.set()
            thread.join()
            if heartbeat_error:
                raise RecoveryConflict('tool_time_checkpoint_failed; candidate retained')
            tick(0)
            self.save(tool_inflight=None)

    def frame_response(self, messages, round_num):
        self.save(messages, round=round_num, response_pending=True, next_tool=0)

    def _file_plan(self, name, args):
        from tools.file_edit import authorize, digest, check_hash, replace_checked, EditRejected
        full = authorize(name, args['path'], content=args.get('content', ''),
                         old_content=args.get('old_content', ''), new_content=args.get('new_content', ''))
        raw = full.read_bytes() if full.is_file() else None
        check_hash(raw, args.get('expected_hash'))
        strict = (self.state.get('harness_policy') or {}).get('editing')
        if name == 'create_file':
            if raw is not None and strict and (not args.get('overwrite') or args.get('expected_hash') is None):
                raise EditRejected('existing_file_requires_explicit_overwrite_hash')
            after = args['content'].encode()
            matches = 0
        else:
            if raw is None:
                raise EditRejected('file_not_found')
            if strict and args.get('expected_hash') is None:
                raise EditRejected('expected_hash_required')
            matches = 0
            if name == 'delete_file':
                after = None
            elif name == 'modify_file':
                text, matches = replace_checked(raw.decode(), args['old_content'], args['new_content'],
                    mode=args.get('mode', 'unique'), expected_count=args.get('expected_count'))
                after = text.encode()
            else:
                from tools.apply_patch import PatchHunk
                if not args.get('hunks') or len(args['hunks']) > 50 or not args.get('expected_hash'):
                    raise EditRejected('invalid_patch_hunks_or_hash')
                authorize('modify_file', args['path'], new_content=''.join(h.get('new_content', '') for h in args['hunks']))
                text = raw.decode()
                for h in args['hunks']:
                    h = PatchHunk.model_validate(h)
                    text, _ = replace_checked(text, h.context_before + h.old_content + h.context_after,
                                              h.context_before + h.new_content + h.context_after)
                    matches += 1
                after = text.encode()
        return full, digest(raw), digest(after), matches

    def execute(self, call, index, function):
        from tools.file_edit import failure, digest
        step = self.frame['request_step'] + ':t' + str(index)
        from workflow.budget import active_budget
        if active_budget.get():
            active_budget.get().check()
        name, args = call['name'], call.get('args', {})
        with self.store.connection() as db:
            row = db.execute('SELECT * FROM tool_executions WHERE run_id=? AND epoch=? AND step_id=?',
                             (self.run_id, self.epoch, step)).fetchone()
        started = time.monotonic()
        if row:
            if name in FILE_WRITES:
                from tools.path_guard import resolve_project_path
                full = Path(resolve_project_path(self.state['project_dir'], args['path']))
                actual = digest(full.read_bytes() if full.is_file() else None)
                if actual == row['after_hash']:
                    with self.private() as db:
                        saved = db.execute('SELECT result FROM tool_results WHERE run_id=? AND epoch=? AND step_id=?',
                                           (self.run_id, self.epoch, step)).fetchone()
                    value = saved[0] if saved else json.dumps({'ok': True, 'status': 'reconciled', 'path': args['path'],
                        'before_hash': row['before_hash'], 'after_hash': row['after_hash']})
                    if row['status'] != 'completed':
                        self._finish_tool(step, value, started, reconciled=True)
                    return value
                if row['status'] == 'completed' or actual != row['before_hash']:
                    self.event('recovery_conflict', step, {'tool': name, 'path': args.get('path'), 'status': 'conflict'})
                    raise RecoveryConflict('file_state_conflict; candidate retained: ' + args['path'])
            elif row['status'] == 'completed':
                with self.private() as db:
                    saved = db.execute('SELECT result FROM tool_results WHERE run_id=? AND epoch=? AND step_id=?',
                                       (self.run_id, self.epoch, step)).fetchone()
                if saved:
                    return saved[0]
            elif name not in READ_ONLY:
                raise RecoveryConflict('side_effect_outcome_unknown; no automatic replay: ' + name)
        else:
            try:
                _, before, after, _ = self._file_plan(name, args) if name in FILE_WRITES else (None, None, None, 0)
            except Exception as exc:
                value = failure(exc)
                self.event('tool_rejected', step, {'tool': name, 'path': args.get('path'), 'status': 'rejected'})
                return value
            with self.store.connection() as db:
                db.execute('INSERT INTO tool_executions VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                           (self.run_id, self.epoch, step, call.get('id', ''), name, args.get('path'), before, after, 'intended', None, None))
                self._insert_event(db, 'tool_intent', step, {'tool': name, 'path': args.get('path'), 'status': 'intended', 'before_hash': before, 'after_hash': after})
        try:
            with self.tool_clock(step):
                value = function.invoke(args) if function else '未知工具: ' + name
        except Exception as exc:
            if isinstance(exc, RecoveryConflict):
                raise
            value = failure(exc)
        self._finish_tool(step, str(value), started)
        return value

    def _finish_tool(self, step, value, started, reconciled=False):
        elapsed = round((time.monotonic() - started) * 1000, 2)
        with self.private() as db:
            db.execute('INSERT OR REPLACE INTO tool_results VALUES(?,?,?,?)', (self.run_id, self.epoch, step, value))
        try:
            parsed = json.loads(value)
        except ValueError:
            parsed = {'summary': str(value)[:200] if str(value).startswith(('错误', '权限', 'guardrail')) else 'Tool returned a result'}
        if not isinstance(parsed, dict):
            parsed = {'summary': 'Tool returned a result'}
        summary = {k: parsed[k] for k in ('ok', 'reason', 'status', 'before_hash', 'after_hash', 'match_count', 'summary',
                                          'profile', 'failure_kind', 'backend', 'exit_code') if k in parsed}
        failed = parsed.get('ok') is False or str(value).startswith(('错误', '权限', 'guardrail', '工具执行失败'))
        with self.store.connection() as db:
            db.execute('UPDATE tool_executions SET status=?,result_summary=?,elapsed_ms=?,after_hash=CASE WHEN ? THEN before_hash ELSE after_hash END WHERE run_id=? AND epoch=? AND step_id=?',
                       ('completed', json.dumps(redact(summary)), None if reconciled else elapsed, failed, self.run_id, self.epoch, step))
            row = db.execute('SELECT tool_name,path FROM tool_executions WHERE run_id=? AND epoch=? AND step_id=?',
                             (self.run_id, self.epoch, step)).fetchone()
            self._insert_event(db, 'tool_result', step, {'tool': row['tool_name'], 'path': row['path'], 'status': 'completed',
                'result': summary, 'elapsed_ms': None if reconciled else elapsed, 'reconciliation_ms': elapsed if reconciled else None})

    def finish(self, state):
        self.state = state
        from tools.path_guard import resolve_project_path
        from tools.file_edit import digest
        hashes = {f['path']: digest(Path(resolve_project_path(state['project_dir'], f['path'])).read_bytes())
                  for f in state.get('code_files', [])} if state.get('phase') == 'code_done' else {}
        self.save(completed=True, response_pending=False, completed_files=hashes)
        if self.standalone:
            self.store.update_status(self.run_id, 'failed' if state.get('error') else 'completed')

    def validate_completed(self):
        from tools.path_guard import resolve_project_path
        from tools.file_edit import digest
        for path, expected in self.frame.get('completed_files', {}).items():
            full = Path(resolve_project_path(self.state['project_dir'], path))
            if digest(full.read_bytes() if full.is_file() else None) != expected:
                raise RecoveryConflict('completed_candidate_changed; candidate retained: ' + path)


@contextmanager
def journal_scope(state):
    from workflow.harness_policy import enabled
    if not enabled(state, 'events'):
        yield None
        return
    from workflow.run_control import current_run, default_run_store, RunControlError
    session = current_run.get()
    store = session.store if session else default_run_store()
    run_id = session.run_id if session else state.get('request_id') or state.get('artifact_run_id')
    if not run_id:
        raise RecoveryConflict('durable run identity is required')
    if session is None:
        try:
            store.get(run_id, str(state['user_id']), str(state['app_id']))
        except RunControlError as exc:
            if exc.status_code != 404:
                raise
            store.create(run_id, str(state['user_id']), str(state['app_id']),
                         {'source': 'standalone_harness', 'harness_policy': state.get('harness_policy', {})})
    journal = RunJournal(state, store, run_id, standalone=session is None)
    token = active_journal.set(journal)
    try:
        yield journal
    finally:
        active_journal.reset(token)
