"""Cloud-only evaluation proxy with a persistent 6 CNY reservation ledger.

Uses the existing gateway and provider balance endpoint; never writes credentials.
The reservation uses peak uncached Pro prices for every alias, even Flash.
An unknown/failed response retains its full reservation. Calls are serialized.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_CEILING
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
import hmac
import json
import os
import time
import urllib.error
import urllib.request
from dotenv import dotenv_values

ROOT = Path('/home/ubuntu/harness-20261102')
LEDGER = ROOT / 'reports/model-budget.json'
LOCK = Lock()
GATEWAY = dotenv_values('/etc/rainn0coding/litellm.env')
RUNTIME = dotenv_values('/etc/rainn0coding/python.env')
TOKEN = RUNTIME['LITELLM_API_KEY']
MAX_MICROYUAN = 6_000_000


def balance():
    base = GATEWAY.get('DEEPSEEK_API_BASE', '').rstrip('/').removesuffix('/v1')
    if base != 'https://api.deepseek.com':
        raise RuntimeError('Unverified provider pricing; paid evaluation disabled')
    request = urllib.request.Request(base + '/user/balance', headers={
        'Authorization': 'Bearer ' + GATEWAY['DEEPSEEK_API_KEY']})
    with urllib.request.urlopen(request, timeout=20) as response:
        data = json.load(response)
    if not data.get('is_available'):
        raise RuntimeError('Provider unavailable')
    for item in data.get('balance_infos', []):
        if item.get('currency') == 'CNY':
            return int(Decimal(item['total_balance']) * 1_000_000)
    raise RuntimeError('No CNY provider balance')


def save(data):
    temporary = LEDGER.with_suffix('.tmp')
    with temporary.open('w', encoding='utf-8') as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(LEDGER)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def reply(self, status, payload):
        print(json.dumps({'http_status': status, 'path': self.path}), flush=True)
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != '/v1/chat/completions' or not hmac.compare_digest(
                self.headers.get('Authorization', ''), 'Bearer ' + TOKEN):
            return self.reply(403, {'error': 'evaluation route denied'})
        size = int(self.headers.get('Content-Length', '0'))
        if size <= 0 or size > 2_000_000:
            return self.reply(413, {'error': 'invalid evaluation request size'})
        data = json.loads(self.rfile.read(size))
        if data.get('stream') or data.get('model') not in {
                'code-reasoning', 'code-structured', 'code-lightweight'}:
            return self.reply(400, {'error': 'unsupported evaluation request'})
        data['max_tokens'] = min(int(data.get('max_tokens') or 4096), 4096)
        # LiteLLM router control, not a model-generated command.
        data.update(disable_fallbacks=True, num_retries=0)
        body = json.dumps(data, ensure_ascii=False).encode()
        reserve = int((Decimal(len(body) + 4096) * 9 +
                       Decimal(data['max_tokens']) * 27).to_integral_value(rounding=ROUND_CEILING))
        with LOCK:
            ledger = json.loads(LEDGER.read_text()) if LEDGER.exists() else {
                'limit_cny': 6, 'charged_microyuan': 0, 'calls': [],
                'pricing_source': 'https://api-docs.deepseek.com/zh-cn/quick_start/pricing',
                'reservation': 'peak uncached input 9/output 27 CNY per million; UTF-8 byte input upper bound',
                'cost_semantics': 'conservative provider-account balance delta; unrelated spend may be included'}
            if ledger['charged_microyuan'] + reserve > MAX_MICROYUAN:
                return self.reply(402, {'error': '6 CNY evaluation budget exhausted'})
            try:
                before = balance()
            except Exception:
                return self.reply(503, {'error': 'CNY accounting unavailable; no paid request sent'})
            item = {'id': len(ledger['calls']) + 1, 'model': data['model'],
                    'reserved_microyuan': reserve, 'charged_microyuan': reserve,
                    'status': 'reserved', 'started_at': time.time()}
            ledger['calls'].append(item)
            ledger['charged_microyuan'] += reserve
            save(ledger)
            try:
                request = urllib.request.Request('http://127.0.0.1:4000/v1/chat/completions',
                    data=body, headers={'Authorization': 'Bearer ' + TOKEN,
                                       'Content-Type': 'application/json'})
                with urllib.request.urlopen(request, timeout=240) as response:
                    response_body = response.read()
                result = json.loads(response_body)
                model = str(result.get('model', ''))
                if not model.startswith('deepseek') and model != data['model']:
                    raise RuntimeError('Unexpected evaluation provider; accounting stopped')
                after = balance()
                # Provider display can round to cents: keep at least a 0.02 CNY
                # allowance per request, bounded above by its reservation.
                charged = max(20_000, before - after + 20_000)
                ledger['charged_microyuan'] += charged - reserve
                item.update(status='completed', charged_microyuan=charged,
                            rounding_allowance_microyuan=20_000,
                            usage=result.get('usage'), reported_model=model,
                            elapsed_seconds=time.time() - item['started_at'])
                save(ledger)
                return self.reply(200, response_body)
            except urllib.error.HTTPError as error:
                item.update(status='upstream_error', http_status=error.code)
                save(ledger)
                return self.reply(error.code, {'error': 'gateway evaluation request failed; reservation retained'})
            except Exception:
                item['status'] = 'uncertain_cost_reservation_retained'
                save(ledger)
                return self.reply(503, {'error': 'evaluation accounting uncertain; reservation retained'})


if __name__ == '__main__':
    ROOT.joinpath('reports').mkdir(parents=True, exist_ok=True)
    balance()  # fail before listening when billing cannot be checked
    ThreadingHTTPServer(('127.0.0.1', 14000), Handler).serve_forever()
