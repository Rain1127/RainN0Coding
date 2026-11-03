"""Frozen live Coder benchmark. All inference uses the CNY-limited proxy."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cases', default='')
    parser.add_argument('--harness', action='store_true')
    parser.add_argument('--features', default='')
    parser.add_argument('--contract-file', type=Path)
    args = parser.parse_args()
    from dotenv import dotenv_values
    env = dotenv_values('/etc/rainn0coding/python.env')
    os.environ.update({k: str(v) for k, v in env.items() if v is not None})
    os.environ.update(LITELLM_BASE_URL='http://127.0.0.1:14000/v1', OTEL_SDK_DISABLED='true',
                      LANGSMITH_TRACING='false', PLAYWRIGHT_CHROMIUM_EXECUTABLE='/usr/bin/google-chrome')
    scratch = args.output.parent / 'evaluation-data'
    os.environ.update(SQLITE_DB_PATH=str(scratch / 'exact.sqlite'),
                      CODE_STORE_DIR=str(scratch / 'verified'),
                      CHECKPOINT_DB_PATH=str(scratch / 'checkpoints.sqlite'),
                      CODE_OUTPUT_DIR=str(scratch / 'output'))
    import logging
    logging.basicConfig(level=logging.INFO)
    if os.geteuid() == 0:
        import pwd
        account = pwd.getpwnam('rainn0coding')
        os.setgroups([])
        os.setgid(account.pw_gid)
        os.setuid(account.pw_uid)
    scratch.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(args.source / 'python-agent'))
    from config import config
    config.LLM_TIMEOUT = 240
    config.TASK_MAX_LLM_CALLS = 12
    config.TASK_MAX_TOKENS = 200000
    config.TASK_MAX_SECONDS = 600
    config.FEEDBACK_WRITES_ENABLED = False
    from agents.coder_agent import coder_agent
    from workflow.budget import budget_scope
    from workflow.runtime_validation import validate_page
    from request_context import bind_request_context
    dataset_path = args.source / 'python-agent/benchmarks/harness/tasks.json'
    dataset = json.loads(dataset_path.read_text())
    report = {'dataset': dataset['version'], 'dataset_sha256': hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
              'prompt_version': dataset['prompt_version'], 'repeats': 1, 'harness': args.harness,
              'observations': [], 'cost': 'see persistent model-budget.json; never infer zero from missing usage'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    selected = set(filter(None, args.cases.split(',')))
    for case in dataset['cases']:
        if selected and case['id'] not in selected:
            continue
        project = args.output.parent / ('artifacts-' + args.output.stem) / case['id']
        project.mkdir(parents=True, exist_ok=True)
        files = dict(case['files'])
        if case.get('long_lines'):
            files['index.html'] = '<!doctype html><meta charset="utf-8"><nav>保留导航</nav>\n' + ''.join(
                f'<p>示例段落 {i}</p>\n' for i in range(case['long_lines'])) + '<footer>版本一</footer>'
        for path, content in files.items():
            (project / path).write_text(content, encoding='utf-8')
        state = {'user_request': case['request'], 'user_id': 'harness-eval', 'app_id': case['id'],
                 'artifact_run_id': 'eval-' + args.output.stem + '-' + case['id'],
                 'code_gen_type': 'html', 'mode': 'modify' if files else 'new',
                 'project_dir': str(project), 'user_role': 'user', 'retry_count': 0,
                 'architecture': {'file_list': [{'path': p} for p in (files or {'index.html': ''})]},
                 'existing_code_files': [{'path': p, 'content': c} for p, c in files.items()],
                 'change_plan': {'files': list(files or {'index.html': ''})},
                 'harness_policy': {k: (k in args.features.split(',') if args.features else args.harness)
                                    for k in ['acceptance', 'context', 'editing', 'events', 'executor', 'instructions']}}
        clock = time.monotonic()
        try:
            if args.contract_file:
                from workflow.acceptance import AcceptanceProposal, freeze_contract
                fixed = json.loads(args.contract_file.read_text())
                freeze_contract(state, AcceptanceProposal.model_validate({'features': fixed['features']}),
                                reason='frozen shared A/B conditions')
            with bind_request_context(request_id=state['artifact_run_id'], trace_id=state['artifact_run_id'],
                                      user_id='harness-eval', app_id=case['id']), budget_scope(state):
                state = coder_agent(state)
            result = validate_page(project, {'version': dataset['version'] + '-' + case['id'], 'steps': case['steps']},
                                   report_dir=project.parent / (case['id'] + '.acceptance'))
            contract_result = None
            if state.get('acceptance_contract'):
                from workflow.acceptance import validate_fixed_contract
                contract_result = validate_fixed_contract(state, project, project.parent / (case['id'] + '.contract-evidence'))
            observation = {'case': case['id'], 'kind': case['kind'], 'phase': state.get('phase'),
                           'error': state.get('error'), 'runtime': result, 'budget': state.get('budget_report'),
                           'contract_result': contract_result,
                           'context': state.get('context_report'),
                           'elapsed_seconds': time.monotonic() - clock}
        except Exception as exc:
            observation = {'case': case['id'], 'infrastructure_error': type(exc).__name__,
                           'elapsed_seconds': time.monotonic() - clock}
        report['observations'].append(observation)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'case': case['id'], 'phase': observation.get('phase'),
                          'runtime': (observation.get('runtime') or {}).get('status')}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
