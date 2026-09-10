"""Live cloud acceptance using the existing private smoke account.

Run as root. Pauses through Java, restarts only an idle Python service, then
resumes the same run. Secrets and complete generated content are never printed.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid

import httpx

os.umask(0o077)
evidence = Path('/opt/rainn0coding/shared/verification')
evidence.mkdir(parents=True, exist_ok=True)
client = httpx.Client(base_url='http://127.0.0.1', timeout=900)


def post(path, body):
    response = client.post('/api' + path, json=body)
    response.raise_for_status()
    result = response.json()
    assert result.get('code') == 0, (path, result.get('code'), result.get('message'))
    return result.get('data')


post('/user/login', json.loads(Path('/etc/rainn0coding/smoke-account.json').read_text()))
prompt = ('请直接生成单个HTML文件的极简静态展示网页，不需要任何后端、网络请求或图片。'
          '页面标题“断点续跑验收”，白色背景，蓝色标题和三张介绍卡片，CSS写在HTML中。'
          '这是一项明确完整的实现需求，无需澄清。')
app_id = post('/app/add', {'initPrompt': prompt})
run_id = str(uuid.uuid4())
summary = {'app_id': str(app_id), 'run_id': run_id, 'started_at': time.time()}
path = evidence / ('pause-resume-' + run_id + '.json')
path.write_text(json.dumps(summary))


def stream(path, params, should_pause=False):
    paused_requested = False
    events = []
    with client.stream('GET', '/api' + path, params=params,
                       headers={'Idempotency-Key': run_id, 'Accept': 'text/event-stream'}) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line.startswith('data:') or not line[5:].strip():
                continue
            raw = json.loads(line[5:].strip())
            event = raw.get('d', raw)
            event = json.loads(event) if isinstance(event, str) else event
            events.append(event)
            if event.get('type') in ('phase_complete', 'done', 'paused', 'error'):
                print(json.dumps({k: event[k] for k in ('type', 'phase', 'status', 'message') if k in event}, ensure_ascii=False), flush=True)
            if should_pause and not paused_requested and event.get('type') == 'phase_complete':
                status = post('/app/chat/gen/pause', {'appId': app_id, 'runId': run_id})
                assert status['run_id'] == run_id
                paused_requested = True
                print('PAUSE_ACCEPTED', status['status'], flush=True)
    return events


first = stream('/app/chat/gen/code', {'appId': app_id, 'message': prompt}, True)
assert any(e.get('type') == 'done' and e.get('status') == 'paused' for e in first), 'Not paused'
status = client.get('/api/app/chat/gen/status', params={'appId': app_id, 'runId': run_id}).json()
assert status['data']['status'] == 'paused', status
summary['paused'] = True
path.write_text(json.dumps(summary))

# Never restart while another user's generation is active.
for _ in range(90):
    metrics = httpx.get('http://127.0.0.1:8000/metrics', timeout=10).text
    active = re.search(r'^ai_code_gen_active_requests(?:\{[^}]*\})?\s+([\d.e+\-]+)', metrics, re.M)
    if active and float(active.group(1)) == 0:
        break
    time.sleep(2)
else:
    raise RuntimeError('Python still has active generation; restart acceptance deferred')
subprocess.run(['systemctl', 'restart', 'rainn0coding-python'], check=True)
for _ in range(90):
    try:
        if httpx.get('http://127.0.0.1:8000/api/health', timeout=10).status_code == 200:
            break
    except httpx.HTTPError:
        pass
    time.sleep(2)
else:
    raise RuntimeError('Python did not restart')
status = client.get('/api/app/chat/gen/status', params={'appId': app_id, 'runId': run_id}).json()
assert status['data']['status'] == 'paused', status
summary['restart_preserved_pause'] = True
path.write_text(json.dumps(summary))
print('RESTART_PRESERVED_CHECKPOINT', flush=True)
second = stream('/app/chat/gen/resume', {'appId': app_id, 'runId': run_id})
assert any(e.get('type') == 'done' and e.get('status') in ('success', 'partial_success', 'degraded_success') for e in second), 'Resume failed'
files = {e['path'] for e in second if e.get('type') == 'code_file'}
assert files, 'No restored/generated files received'
summary.update(success=True, files=len(files), elapsed_seconds=round(time.time()-summary['started_at'], 1))
path.write_text(json.dumps(summary, indent=2))
print('PAUSE_RESTART_RESUME_PASS', json.dumps(summary), flush=True)
