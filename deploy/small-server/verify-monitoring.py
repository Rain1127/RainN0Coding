"""Read-only verification of metrics, Grafana provisioning and optional trace linkage."""
import argparse
import base64
import json
from pathlib import Path
import shlex
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('--trace-id')
args = parser.parse_args()

def read(url, headers=None):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=20) as response:
        return json.load(response)

targets = read('http://127.0.0.1:9090/api/v1/targets')['data']['activeTargets']
jobs = {target['labels']['job']: target['health'] for target in targets}
assert jobs.get('java-gateway') == 'up' and jobs.get('python-agent') == 'up', jobs
print('PROMETHEUS_TARGETS', json.dumps(jobs))
credentials = {}
for line in Path('/etc/rainn0coding/grafana.env').read_text().splitlines():
    if '=' in line:
        name, value = line.split('=', 1)
        credentials[name] = shlex.split(value)[0]
encoded = base64.b64encode((credentials['GF_SECURITY_ADMIN_USER'] + ':' + credentials['GF_SECURITY_ADMIN_PASSWORD']).encode()).decode()
headers = {'Authorization': 'Basic ' + encoded}
for uid in ['prometheus', 'tempo']:
    health = read(f'http://127.0.0.1:3001/api/datasources/uid/{uid}/health', headers)
    assert health.get('status') == 'OK', (uid, health)
    print('GRAFANA_DATASOURCE', uid, health['status'])
dashboards = read('http://127.0.0.1:3001/api/search?query=AI%20Workflow', headers)
assert any(item.get('uid') == 'ai-workflow-monitoring' for item in dashboards)
print('GRAFANA_DASHBOARD_PASS')
if args.trace_id:
    trace = read('http://127.0.0.1:3200/api/traces/' + args.trace_id)
    services = set()
    spans = 0
    for batch in trace.get('batches', trace.get('resourceSpans', [])):
        for attribute in batch.get('resource', {}).get('attributes', []):
            if attribute.get('key') == 'service.name':
                services.add(attribute.get('value', {}).get('stringValue'))
        for scope in batch.get('scopeSpans', batch.get('instrumentationLibrarySpans', [])):
            spans += len(scope.get('spans', []))
    assert {'RainN0Coding-backend', 'python-agent'}.issubset(services), services
    print('CORRELATED_TRACE_PASS', args.trace_id, sorted(services), 'spans', spans)
