"""Run with the existing local Python venv; transfer the output separately from source."""
import argparse
import json
import os
from pathlib import Path

import yaml
from dotenv import dotenv_values

parser = argparse.ArgumentParser()
parser.add_argument('--source', required=True, type=Path)
parser.add_argument('--output', required=True, type=Path)
args = parser.parse_args()
allowed = {
    'DEEPSEEK_API_KEY', 'DEEPSEEK_BASE_URL', 'DEEPSEEK_MODEL', 'CHAT_MODEL',
    'REASONING_MODEL', 'ZHIPU_API_KEY', 'ZHIPU_BASE_URL', 'ZHIPU_FLASH_MODEL',
    'PEXELS_API_KEY', 'LANGSMITH_API_KEY', 'LANGSMITH_ENDPOINT', 'LANGSMITH_PROJECT',
}
source = dotenv_values(args.source / 'python-agent/.env')
python_values = {key: value for key, value in source.items() if key in allowed and value}
if not python_values.get('DEEPSEEK_API_KEY'):
    raise SystemExit('Missing local DeepSeek credential; no secret output written.')
local_yaml = yaml.safe_load((args.source / 'src/main/resources/application-local.yml').read_text(encoding='utf-8'))
cos = local_yaml.get('cos', {}).get('client', {})
expected = {'host', 'secretId', 'secretKey', 'region', 'bucket'}
if not expected.issubset(cos):
    raise SystemExit('Local COS settings are incomplete; no secret output written.')
args.output.parent.mkdir(parents=True, exist_ok=True)
with os.fdopen(os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w', encoding='utf-8') as handle:
    json.dump({'python': python_values, 'cos': {key: cos[key] for key in expected}}, handle)
print('Private transfer file prepared; values omitted.')
