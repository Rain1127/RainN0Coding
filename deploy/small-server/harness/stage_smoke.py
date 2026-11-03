"""End-to-end paid smoke test against the cloud candidate's loopback gateway."""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import sys
import time
from uuid import uuid4

import httpx

BASE = 'http://127.0.0.1:18123/api'
PROMPT = '用原生 HTML 做一个无外部依赖的单文件展示页。顶部导航显示精确文字「站点导航」，正文显示精确文字「正文已就绪」。'
CORRECTION = '保留顶部导航和正文，在页脚增加精确可见的文字「联调已确认」。'


class RateLimited(RuntimeError):
    pass


def response(client, method, path, **kwargs):
    result = client.request(method, BASE + path, **kwargs)
    result.raise_for_status()
    payload = result.json()
    if payload['code'] == 42900:
        raise RateLimited(path)
    if payload['code'] != 0:
        raise RuntimeError(f"{path}: {payload['code']} {payload.get('message')}")
    return payload.get('data')


def login(client):
    account = 'harness' + secrets.token_hex(4)
    password = secrets.token_hex(12)
    body = {'userAccount': account, 'userPassword': password}
    for path, data in (('/user/register', {**body, 'checkPassword': password}), ('/user/login', body)):
        try:
            response(client, 'POST', path, json=data)
        except RateLimited:
            time.sleep(61)
            response(client, 'POST', path, json=data)


def events(client, path, *, after=None, stop_after=None):
    seen = []
    current = {}
    headers = {'Last-Event-ID': str(after)} if after is not None else {}
    with client.stream('GET', BASE + path, headers=headers, timeout=40) as stream:
        stream.raise_for_status()
        for line in stream.iter_lines():
            if line.startswith('id:'):
                current['id'] = int(line[3:].strip())
            elif line.startswith('data:'):
                try:
                    current['data'] = json.loads(line[5:].strip())
                except ValueError:
                    continue
            elif not line:
                if 'id' in current and 'data' in current:
                    seen.append(current)
                    if (stop_after and len(seen) >= stop_after) or current['data'].get('type') == 'done':
                        break
                current = {}
    return seen


def run(report, save):
    with httpx.Client(timeout=60) as owner, httpx.Client(
        timeout=30, transport=httpx.HTTPTransport(local_address='127.0.0.2')
    ) as stranger:
        login(owner)
        login(stranger)
        app_id = response(owner, 'POST', '/app/add', json={'initPrompt': PROMPT})
        task = response(owner, 'POST', '/app/generation/tasks',
                        json={'appId': str(app_id), 'message': PROMPT, 'idempotencyKey': str(uuid4())})
        task_id = task['taskId']
        task_path = '/app/generation/tasks/' + task_id
        params = {'appId': str(app_id), 'runId': task_id}
        instruction_path = '/app/chat/gen/instructions'
        report.update(app_id=str(app_id), run_id=task_id)
        save(report)
        unauthorized = stranger.get(BASE + instruction_path, params=params)
        assert unauthorized.status_code in (401, 403) or unauthorized.json()['code'] != 0
        report['non_owner_denied'] = True
        instruction = {**params, 'instructionId': str(uuid4()), 'action': 'submit',
                       'target': 'next_step', 'content': CORRECTION}
        deadline = time.monotonic() + 150
        while time.monotonic() < deadline:
            ready = owner.get(BASE + instruction_path, params=params)
            if ready.is_success and ready.json()['code'] == 0:
                assert ready.json()['data']['enabled']
                break
            time.sleep(1)
        else:
            raise RuntimeError('The queue did not register an active Python run')
        first = response(owner, 'POST', instruction_path, json=instruction)
        assert first['status'] in ('queued', 'planning', 'prepared')
        again = response(owner, 'POST', instruction_path, json=instruction)
        assert again['instruction_id'] == first['instruction_id']
        next_run = {**instruction, 'instructionId': str(uuid4()), 'target': 'next_run', 'content': '下一轮增加帮助页'}
        response(owner, 'POST', instruction_path, json=next_run)
        initial = events(owner, task_path + '/events', stop_after=3)
        assert initial, 'No replayable Java queue events'
        report['disconnect_cursor'] = initial[-1]['id']
        save(report)
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            status = response(owner, 'GET', task_path)
            report['queue_status'] = status['status']
            if status['status'] in ('SUCCEEDED', 'FAILED', 'INTERRUPTED'):
                break
            time.sleep(3)
        else:
            raise RuntimeError('Candidate generation exceeded the smoke deadline')
        rows = response(owner, 'GET', instruction_path, params=params)['instructions']
        report['instructions'] = [{key: row[key] for key in ('instruction_id', 'status', 'step_id', 'contract_version', 'reason')}
                                  for row in rows]
        steps = response(owner, 'GET', '/app/chat/gen/steps', params={**params, 'limit': 200})['events']
        report['step_events'] = [{'seq': row['seq'], 'step_id': row['step_id'], 'type': row['type']} for row in steps]
        resumed = events(owner, task_path + '/events', after=initial[-1]['id'])
        assert resumed and all(event['id'] > initial[-1]['id'] for event in resumed)
        assert len({event['id'] for event in resumed}) == len(resumed)
        report['replayed_events'] = len(resumed)
        report['terminal'] = next((event['data'].get('status') for event in reversed(resumed)
                                   if event['data'].get('type') == 'done'), None)
        assert status['status'] == 'SUCCEEDED', status.get('errorMessage')
        assert [row['status'] for row in rows] == ['included', 'next_run_ready'], report['instructions']
        assert any(row['type'] == 'instruction_included' and row['step_id'] == rows[0]['step_id'] for row in steps)
        assert rows[0]['contract_version'] >= 2

        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, executable_path=os.environ['PLAYWRIGHT_CHROMIUM_EXECUTABLE'])
            session = browser.new_context()
            for cookie in owner.cookies.jar:
                session.add_cookies([{'name': cookie.name, 'value': cookie.value, 'url': BASE}])
            page = session.new_page()
            page.goto(BASE + '/chat/' + str(app_id), wait_until='domcontentloaded')
            panel = page.get_by_role('region', name='生成补充指令')
            panel.get_by_text('补充指令', exact=False).first.click(timeout=20_000)
            panel.get_by_text('已纳入模型请求', exact=False).wait_for(timeout=10_000)
            panel.get_by_role('button', name='填入下一轮需求').click(timeout=10_000)
            assert any(value == '下一轮增加帮助页' for value in page.locator('textarea').evaluate_all('(nodes) => nodes.map(n => n.value)'))
            report['vue_receipt_and_next_run_draft'] = True
            browser.close()

        root = Path('/opt/rainn0coding/harness-20261102/stage-app/tmp/code_output')
        artifact = next(iter(root.glob(f'*_{app_id}/index.html')))
        html = artifact.read_text(encoding='utf-8')
        assert all(text in html for text in ('站点导航', '正文已就绪', '联调已确认'))
        report['candidate_published_with_all_three_requirements'] = True
        report['status'] = 'passed'


if __name__ == '__main__':
    report = {'status': 'running', 'base': BASE}
    path = Path(sys.argv[1])

    def save(data):
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    try:
        run(report, save)
    except Exception as exc:
        report.update(status='failed', error=str(exc))
        raise
    finally:
        save(report)
