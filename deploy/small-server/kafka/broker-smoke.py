"""Run before enabling application consumption; independent topic, no model calls."""
import json
import subprocess
import time
import uuid

topic = 'queue-verification-' + uuid.uuid4().hex
prefix = ['docker', 'exec', '-i', '-e', 'KAFKA_HEAP_OPTS=-Xms32m -Xmx64m', 'rainn0coding-kafka']


def cli(tool, *args, **kwargs):
    return subprocess.run(prefix + ['/opt/kafka/bin/' + tool + '.sh', '--bootstrap-server', '127.0.0.1:9092', *args],
                          check=True, capture_output=True, text=True, timeout=60, **kwargs).stdout


cli('kafka-topics', '--create', '--topic', topic, '--partitions', '1', '--replication-factor', '1',
    '--config', 'retention.ms=3600000')
markers = ['queue-marker-' + str(i) for i in range(5)]
cli('kafka-console-producer', '--topic', topic, input='\n'.join(markers) + '\n')
subprocess.run(['docker', 'restart', 'rainn0coding-kafka'], check=True, capture_output=True, timeout=90)
for _ in range(60):
    result = subprocess.check_output(['docker', 'inspect', '--format', '{{.State.Health.Status}}', 'rainn0coding-kafka'], text=True)
    if result.strip() == 'healthy':
        break
    time.sleep(2)
else:
    raise RuntimeError('Kafka did not become healthy')
actual = cli('kafka-console-consumer', '--topic', topic, '--from-beginning', '--max-messages', '5', '--timeout-ms', '20000').splitlines()
assert actual == markers, 'Persistence or order mismatch'
print(json.dumps({'topic': topic, 'messages': len(actual), 'ordered': True, 'persisted_after_restart': True}), flush=True)
