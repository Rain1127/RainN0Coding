"""Run as root on the server. Preserve existing database and Grafana credentials."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--public-host', required=True)
parser.add_argument('--secrets', required=True, type=Path)
args = parser.parse_args()
if not re.fullmatch(r'[A-Za-z0-9.-]+', args.public_host):
    raise SystemExit('Invalid public hostname')
directory = Path('/etc/rainn0coding')
directory.mkdir(mode=0o700, exist_ok=True)
payload = json.loads(args.secrets.read_text(encoding='utf-8'))
items = json.loads(subprocess.check_output([
    'docker', 'inspect', '--format', '{{json .Config.Env}}', 'rainn0coding-mysql'
], text=True))
database = dict(item.split('=', 1) for item in items if '=' in item)
token_file = directory / 'internal-token'
if not token_file.exists():
    token_file.write_text(secrets.token_urlsafe(32), encoding='ascii')
    token_file.chmod(0o600)
token = token_file.read_text(encoding='ascii').strip()

def save_environment(name, values):
    # systemd EnvironmentFile and Docker env_file accept these quoted values.
    # Reject multiline/NUL rather than risking unintended environment entries.
    lines = []
    for key, value in values.items():
        text = str(value)
        if any(char in text for char in '\r\n\0'):
            raise ValueError(f'Multiline value not allowed for {key}')
        escaped = text.replace('\\', '\\\\').replace('"', '\\"')
        lines.append(f'{key}="{escaped}"\n')
    path = directory / name
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w', encoding='utf-8') as handle:
        handle.writelines(lines)
    path.chmod(0o600)

common = {
    'REDIS_HOST': '127.0.0.1', 'REDIS_PORT': '6379',
    'OTEL_EXPORTER_OTLP_TRACES_ENDPOINT': 'http://127.0.0.1:4318/v1/traces',
}
java = {
    **common, 'SPRING_PROFILES_ACTIVE': 'prod', 'SERVER_ADDRESS': '127.0.0.1',
    'MYSQL_URL': 'jdbc:mysql://127.0.0.1:3306/rainn0coding?useUnicode=true&characterEncoding=UTF-8&serverTimezone=Asia/Shanghai',
    'MYSQL_USERNAME': database['MYSQL_USER'], 'MYSQL_PASSWORD': database['MYSQL_PASSWORD'],
    'PYTHON_AI_BASE_URL': 'http://127.0.0.1:8000', 'PYTHON_AI_INTERNAL_TOKEN': token,
    'APP_DEPLOY_HOST': f'http://{args.public_host}/api/static',
    'APP_CORS_ALLOWED_ORIGIN_PATTERNS': f'http://{args.public_host}',
    'AI_CODEGEN_MAX_CONCURRENT_REQUESTS': '3',
    'SPRING_DATASOURCE_HIKARI_MAXIMUM_POOL_SIZE': '5',
    'SPRING_DATASOURCE_HIKARI_MINIMUM_IDLE': '1',
    'OTEL_SERVICE_NAME': 'RainN0Coding-backend',
    'OTEL_TRACES_EXPORTER': 'otlp', 'OTEL_METRICS_EXPORTER': 'none', 'OTEL_LOGS_EXPORTER': 'none',
    'OTEL_EXPORTER_OTLP_PROTOCOL': 'http/protobuf',
    'MANAGEMENT_ENDPOINT_HEALTH_SHOW_DETAILS': 'never',
}
java.update({'COS_CLIENT_' + key.upper(): value for key, value in payload['cos'].items()})
python = {
    **payload['python'], **common, 'APP_ENV': 'production',
    'JAVA_BASE_URL': 'http://127.0.0.1:8123',
    'INTERNAL_API_TOKEN': token, 'INTERNAL_API_ALLOW_MISSING_TOKEN': 'false',
    'AGENT_MAX_CONCURRENT_REQUESTS': '3', 'VECTOR_DB_PROVIDER': 'qdrant',
    'QDRANT_URL': 'http://127.0.0.1:6333',
    'EMBEDDING_MODEL': '/opt/rainn0coding/tools/models/bge-small-zh-v1.5',
    'HF_HUB_OFFLINE': '1',
    'CODE_OUTPUT_DIR': '/opt/rainn0coding/shared/tmp/code_output',
    'SQLITE_DB_PATH': '/opt/rainn0coding/shared/rag_data/exact_search.db',
    'CODE_STORE_DIR': '/opt/rainn0coding/shared/verified_code',
    'OTEL_EXPORTER_ENABLED': 'true', 'LANGSMITH_TRACING': 'false',
}
save_environment('java.env', java)
save_environment('python.env', python)
if not (directory / 'grafana.env').exists():
    save_environment('grafana.env', {
        'GF_SECURITY_ADMIN_USER': 'admin',
        'GF_SECURITY_ADMIN_PASSWORD': secrets.token_urlsafe(24),
    })
print('Runtime configuration written with restricted permissions; credentials omitted.')
