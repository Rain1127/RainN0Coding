"""Finish verification of an existing successful task; never submit generation."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urljoin, urlsplit
from html.parser import HTMLParser

import httpx

os.umask(0o077)
report = Path(sys.argv[1])
summary = json.loads(report.read_text())
app_id, task_id = summary['app_id'], summary['task_id']
client = httpx.Client(base_url='http://127.0.0.1', timeout=300)


def request(path, body=None):
    response = client.get('/api' + path) if body is None else client.post('/api' + path, json=body)
    response.raise_for_status()
    result = response.json()
    assert result['code'] == 0, (path, result.get('code'), result.get('message'))
    return result['data']


request('/user/login', json.loads(Path('/etc/rainn0coding/smoke-account.json').read_text()))
path = '/app/generation/tasks/' + task_id
task = request(path)
assert task['status'] == 'SUCCEEDED'
history_path = '/chatHistory/app/' + app_id + '?pageSize=50'
history = request(history_path)['records']
assert len(history) == 2, 'Unexpected duplicate/missing messages'
files = []
with client.stream('GET', '/api' + path + '/events?after=0') as response:
    response.raise_for_status()
    for line in response.iter_lines():
        if line.startswith('data:'):
            event = json.loads(line[5:].strip())
            if event.get('type') == 'code_file':
                files.append(event.get('path', event.get('file_path')))
assert files
payload = json.dumps({'version': 1, 'taskId': task_id}) + '\n'
subprocess.run(['docker', 'exec', '-i', '-e', 'KAFKA_HEAP_OPTS=-Xms32m -Xmx64m', 'rainn0coding-kafka',
                '/opt/kafka/bin/kafka-console-producer.sh', '--bootstrap-server', '127.0.0.1:9092',
                '--topic', 'rain-code-generation-v1'], input=payload, text=True, check=True,
               capture_output=True, timeout=60)
time.sleep(5)
assert request(path)['lastEventId'] == task['lastEventId']
assert len(request(history_path)['records']) == 2
if '--repair-scaffold' in sys.argv:
    # Repair only this explicitly identified smoke output. Preserve the old shell.
    assert app_id.isdecimal()
    output = Path('/opt/rainn0coding/shared/tmp/code_output') / ('html_' + app_id)
    root = output / 'index.html'
    actual = output / 'src' / 'index.html'
    expected = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>AI Generated App</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body>
  <div id="app"></div>
  <script type="module" src="/src/main.ts"></script>
</body>
</html>'''
    assert actual.is_file() and 'Kafka队列验收' in actual.read_text()
    assert not (output / 'src' / 'main.ts').exists()
    if root.exists():
        assert root.read_text().strip() == expected
        backup = report.parent / (app_id + '-scaffold-before-fix.html')
        assert not backup.exists()
        root.rename(backup)
    summary['static_scaffold_repaired'] = True
preview_url = request('/app/deploy', {'appId': app_id})
preview = client.get(preview_url)
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
for asset in assets.urls:
    url = urljoin(preview_url, asset)
    if urlsplit(url).netloc != urlsplit(preview_url).netloc:
        continue
    response = client.get(url)
    response.raise_for_status()
    assert response.content and 'text/html' not in response.headers.get('content-type', '')
summary.update(success=True, generated_successfully=True, history_messages=len(history),
               code_files=len(files), duplicate_delivery_no_repeat=True, final_event_id=task['lastEventId'],
               preview_status=preview.status_code, preview_url=preview_url, assets_checked=len(assets.urls))
report.write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, ensure_ascii=False))
