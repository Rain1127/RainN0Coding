"""Real API acceptance test. Keeps its dedicated account credentials on the server."""
import json
import argparse
import os
from pathlib import Path
import secrets
import time
import uuid

from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

parser = argparse.ArgumentParser()
parser.add_argument('--app-id')
parser.add_argument('--message')
parser.add_argument('--publish-only', action='store_true')
args = parser.parse_args()
if args.publish_only and not args.app_id:
    parser.error('--publish-only requires --app-id')
os.umask(0o077)
evidence = Path('/opt/rainn0coding/shared/verification')
evidence.mkdir(parents=True, exist_ok=True)
account_file = Path('/etc/rainn0coding/smoke-account.json')
client = httpx.Client(base_url='http://127.0.0.1', timeout=httpx.Timeout(900, connect=10))

def post(path, data):
    response = client.post(path, json=data, headers={'Idempotency-Key': str(uuid.uuid4())})
    response.raise_for_status()
    result = response.json()
    if result.get('code') != 0:
        raise RuntimeError(f'{path}: {result.get("code")} {result.get("message")}')
    return result.get('data')

if account_file.exists():
    account = json.loads(account_file.read_text())
else:
    account = {'userAccount': 'cloud_smoke_' + secrets.token_hex(4), 'userPassword': secrets.token_urlsafe(24)}
    post('/api/user/register', {**account, 'checkPassword': account['userPassword']})
    account_file.write_text(json.dumps(account))
post('/api/user/login', account)
print('REGISTER_LOGIN_PASS', flush=True)
prompt = ('请使用 Vue 3 + Vite 生成一个可直接 npm install 和 npm run build 的极简待办清单应用，'
          '单页，标题“云端部署验收”，提供添加任务、勾选完成、删除任务、显示剩余数量；'
          '使用原生 CSS 和 localStorage，不用任何组件库、图片、网络接口、路由或后端。'
          '这是明确的实现需求，请直接执行，不需要澄清。')
prompt = args.message or prompt
app_id = args.app_id or post('/api/app/add', {'initPrompt': prompt})
print('APP_SELECTED', app_id, flush=True)
result_path = evidence / f'app-{app_id}.json'
if args.publish_only:
    summary = json.loads(result_path.read_text())
else:
    summary = {'app_id': str(app_id), 'started': time.time(), 'success': False}
    result_path.write_text(json.dumps(summary))
    events = []
    with client.stream('GET', '/api/app/chat/gen/code', params={'appId': app_id, 'message': prompt},
                       headers={'Idempotency-Key': str(uuid.uuid4())}) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line.startswith('data:') or not line[5:].strip():
                continue
            raw = json.loads(line[5:].strip())
            payload = raw.get('d', raw)
            event = json.loads(payload) if isinstance(payload, str) else payload
            events.append(event)
            with (evidence / f'app-{app_id}-events.jsonl').open('a') as event_file:
                event_file.write(json.dumps(event, ensure_ascii=False) + '\n')
            kind = event.get('type')
            if kind in {'phase_start', 'phase_complete', 'error', 'done', 'clarify'}:
                print(json.dumps({key: event[key] for key in ('type', 'phase', 'status', 'message') if key in event}, ensure_ascii=False), flush=True)
            if kind == 'done':
                summary['workflow_status'] = event.get('status')
                summary['success'] = event.get('status') == 'success'
            if event.get('trace_id'):
                summary['trace_id'] = event['trace_id']
    summary['elapsed_seconds'] = round(time.time() - summary['started'], 1)
    (evidence / f'app-{app_id}-events.json').write_text(json.dumps(events, ensure_ascii=False))
    result_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    if not summary['success']:
        raise SystemExit('GENERATION_FAILED: inspect dedicated evidence')
deploy_url = post('/api/app/deploy', {'appId': app_id})
preview = client.get(deploy_url)
preview.raise_for_status()
assert '<html' in preview.text.lower()

class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'script' and attrs.get('src'):
            self.urls.append(attrs['src'])
        if tag == 'link' and attrs.get('rel') == 'stylesheet':
            self.urls.append(attrs['href'])

assets = Assets()
assets.feed(preview.text)
assert assets.urls, 'No built JS/CSS assets found'
for path in assets.urls:
    url = urljoin(deploy_url, path)
    assert urlsplit(url).netloc == urlsplit(deploy_url).netloc, 'Unexpected external asset'
    response = client.get(url)
    response.raise_for_status()
    assert response.content and 'text/html' not in response.headers.get('content-type', ''), url
summary['assets_checked'] = len(assets.urls)
summary['deploy_url'] = deploy_url
summary['preview_status'] = preview.status_code
result_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
print('BUILD_PREVIEW_ASSETS_PASS', json.dumps(summary, ensure_ascii=False), flush=True)
