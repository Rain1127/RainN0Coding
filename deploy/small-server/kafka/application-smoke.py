"""Live queue acceptance with the existing private smoke account and one model run.

Run only in an idle maintenance window. Never print credentials or generated code.
"""
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

import httpx

os.umask(0o077)
client = httpx.Client(base_url='http://127.0.0.1', timeout=1000)
evidence = Path('/opt/rainn0coding/shared/verification')
evidence.mkdir(exist_ok=True, parents=True)
summary = {'started': time.time()}
report = evidence / ('queue-' + uuid.uuid4().hex + '.json')


def record(**values):
    summary.update(values)
    report.write_text(json.dumps(summary, indent=2))
    print(json.dumps(values, ensure_ascii=False), flush=True)


def request(path, body=None):
    response = client.get('/api' + path) if body is None else client.post('/api' + path, json=body)
    response.raise_for_status()
    result = response.json()
    assert result.get('code') == 0, (path, result.get('code'), result.get('message'))
    return result.get('data')


def sql(statement):
    result = subprocess.run(['docker', 'exec', '-i', 'rainn0coding-mysql', 'sh', '-c',
                             'exec mysql -N -B -uroot -p"$MYSQL_ROOT_PASSWORD" rainn0coding'],
                            input=statement, text=True, capture_output=True, check=True)
    return result.stdout.strip()


def wait_health(url):
    for _ in range(90):
        try:
            if httpx.get(url, timeout=5).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(2)
    raise RuntimeError('Service health timeout')


def kafka_ready():
    for _ in range(90):
        value = subprocess.check_output(['docker', 'inspect', '--format', '{{.State.Health.Status}}', 'rainn0coding-kafka'], text=True)
        if value.strip() == 'healthy':
            return
        time.sleep(2)
    raise RuntimeError('Kafka health timeout')


def events(after=0, disconnect=False, pause=False):
    cursor = after
    received = []
    pause_sent = False
    with client.stream('GET', '/api' + task_path + '/events', params={'after': after}) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if line.startswith('id:'):
                cursor = int(line[3:].strip())
            elif line.startswith('data:'):
                event = json.loads(line[5:].strip())
                received.append(event)
                kind = event.get('type')
                if kind in ('phase_start', 'phase_complete', 'done', 'error'):
                    print(json.dumps({k: event[k] for k in ('type', 'phase', 'status') if k in event}), flush=True)
                if disconnect and kind == 'phase_start':
                    return cursor, received
                if pause and not pause_sent and kind == 'phase_complete':
                    result = request(task_path + '/pause', {})
                    assert result['taskId'] == task_id
                    pause_sent = True
    return cursor, received


request('/user/login', json.loads(Path('/etc/rainn0coding/smoke-account.json').read_text()))
assert sql("SELECT COUNT(*) FROM generation_task WHERE status IN ('QUEUED','RUNNING','PAUSING');") == '0', 'Other work active'
prompt = ('请直接生成单个HTML文件的静态介绍网页，不需要后端、网络请求或图片。'
          '页面标题“Kafka队列验收”，白色背景，蓝色标题，三张说明卡片，CSS写在HTML中。'
          '这是明确完整的实现需求，无需澄清。')
app_id = request('/app/add', {'initPrompt': prompt})
submission = {'appId': str(app_id), 'message': prompt, 'idempotencyKey': str(uuid.uuid4())}
record(app_id=str(app_id))

try:
    subprocess.run(['docker', 'stop', 'rainn0coding-kafka'], check=True, capture_output=True, timeout=90)
    task = request('/app/generation/tasks', submission)
    task_id = task['taskId']
    task_path = '/app/generation/tasks/' + task_id
    assert request('/app/generation/tasks', submission)['taskId'] == task_id
    record(task_id=task_id, duplicate_submit_same_id=True)
    for _ in range(30):
        pending = sql("SELECT CONCAT(published,':',attempts) FROM generation_outbox WHERE task_id='" + task_id + "';")
        if pending.startswith('0:') and int(pending.split(':')[1]) > 0:
            break
        time.sleep(2)
    else:
        raise RuntimeError('Outbox failure retention was not observed')
    assert request(task_path)['status'] == 'QUEUED'
    assert request(task_path + '/pause', {})['status'] == 'PAUSED'
    subprocess.run(['systemctl', 'restart', 'rainn0coding-java'], check=True, timeout=120)
    wait_health('http://127.0.0.1:8123/api/actuator/health')
    assert request(task_path)['status'] == 'PAUSED'
    record(broker_outage_retained_outbox=True, queued_pause_survived_java_restart=True)
finally:
    subprocess.run(['docker', 'start', 'rainn0coding-kafka'], check=True, capture_output=True, timeout=90)
    kafka_ready()

with httpx.Client(base_url='http://127.0.0.1') as anonymous:
    response = anonymous.get('/api' + task_path)
    assert response.status_code != 200 or response.json().get('code') != 0
record(anonymous_read_rejected=True)

task = request(task_path + '/resume', {})
assert task['taskId'] == task_id
cursor, first = events(max(0, int(task['lastEventId']) - 1), disconnect=True)
assert any(e.get('type') == 'phase_start' for e in first)
for _ in range(90):
    current = request(task_path)
    if int(current['lastEventId']) > cursor:
        break
    time.sleep(2)
else:
    raise RuntimeError('No progress after browser disconnect')
assert current['status'] != 'PAUSED'
record(disconnected_task_continued=True)
cursor, middle = events(cursor, pause=True)
assert request(task_path)['status'] == 'PAUSED', 'Live checkpoint pause not reached'
record(live_pause_saved=True)

# Atomically stop admission/claim while checking that no other run is active.
sql('UPDATE generation_queue_lock SET paused=1 WHERE id=1;')
try:
    assert sql("SELECT COUNT(*) FROM generation_task WHERE status IN ('RUNNING','PAUSING');") == '0'
    subprocess.run(['systemctl', 'restart', 'rainn0coding-python'], check=True, timeout=120)
    wait_health('http://127.0.0.1:8000/api/health')
    assert request(task_path)['status'] == 'PAUSED'
    record(checkpoint_survived_python_restart=True)
finally:
    sql('UPDATE generation_queue_lock SET paused=0 WHERE id=1;')

resumed = request(task_path + '/resume', {})
assert resumed['taskId'] == task_id
cursor, final = events(cursor)
assert request(task_path)['status'] == 'SUCCEEDED', 'Generation did not succeed'
assert any(e.get('type') == 'code_file' for e in final), 'No code file events'
history = request('/chatHistory/app/' + str(app_id) + '?pageSize=100')['records']
assert len(history) == 2, 'Expected exactly one user and one completion message'
record(generated_successfully=True, history_messages=len(history), reconnect_cursor=cursor)

# Re-delivery of a completed task must not invoke the model or add history.
payload = json.dumps({'version': 1, 'taskId': task_id}) + '\n'
subprocess.run(['docker', 'exec', '-i', '-e', 'KAFKA_HEAP_OPTS=-Xms32m -Xmx64m', 'rainn0coding-kafka',
                '/opt/kafka/bin/kafka-console-producer.sh', '--bootstrap-server', '127.0.0.1:9092',
                '--topic', 'rain-code-generation-v1'], input=payload, text=True, check=True,
               capture_output=True, timeout=60)
time.sleep(5)
assert int(request(task_path)['lastEventId']) == cursor
assert len(request('/chatHistory/app/' + str(app_id) + '?pageSize=100')['records']) == 2
record(duplicate_delivery_no_repeat=True)
preview_url = request('/app/deploy', {'appId': app_id})
preview = client.get(preview_url)
preview.raise_for_status()
assert '<html' in preview.text.lower()
record(preview_status=preview.status_code, preview_url=preview_url,
       elapsed_seconds=round(time.time() - summary['started'], 1), success=True)
