"""Read-only, credential-filtered cloud preflight. Run with the server venv."""
from __future__ import annotations

import json
from pathlib import Path
import urllib.request
from dotenv import dotenv_values


def main():
    env = dotenv_values('/etc/rainn0coding/litellm.env')
    request = urllib.request.Request('http://127.0.0.1:4000/model/info', headers={
        'Authorization': 'Bearer ' + env['LITELLM_MASTER_KEY']})
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.load(response)
    allowed = ('input_cost_per_token', 'output_cost_per_token',
               'cache_read_input_token_cost', 'max_input_tokens', 'max_output_tokens',
               'litellm_provider', 'mode')
    models = []
    for item in payload.get('data', []):
        info = item.get('model_info', {})
        models.append({'alias': item.get('model_name'),
                       'provider_model': item.get('litellm_params', {}).get('model'),
                       'pricing': {k: info.get(k) for k in allowed}})
    print(json.dumps({'models': models}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
