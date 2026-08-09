#!/usr/bin/env python3
"""Full check: all Claude/LLM prompts via application HTTP APIs (no browser).

Usage:
  ./venv/bin/python scripts/check_llm_prompts.py
  CHECK_BASE_URL=http://127.0.0.1:5002 ./venv/bin/python scripts/check_llm_prompts.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv() -> None:
    env_path = ROOT / '.env'
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def req(base: str, method: str, path: str, token: str | None = None, body=None, timeout: int = 180):
    data = None if body is None else json.dumps(body).encode()
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    request = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            raw = resp.read().decode()
            payload = json.loads(raw) if raw else {}
            return resp.status, payload
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {'_raw': raw[:400]}
        return exc.code, payload
    except Exception as exc:  # noqa: BLE001
        return 0, {'error': str(exc)}


def main() -> int:
    os.chdir(ROOT)
    _load_dotenv()
    base = os.environ.get('CHECK_BASE_URL', 'http://127.0.0.1:5002').rstrip('/')
    username = os.environ.get('DEFAULT_ADMIN_USERNAME', 'admin')
    password = os.environ.get('DEFAULT_ADMIN_PASSWORD', '')

    print('=== 1) Config / wiring ===')
    sys.path.insert(0, str(ROOT))
    from Injaaz import create_app

    app = create_app()
    with app.app_context():
        from module_assistant.llm import is_llm_enabled

        enabled = bool(is_llm_enabled())
        key = (app.config.get('ANTHROPIC_API_KEY') or '').strip()
        print(
            f"provider={app.config.get('ASSISTANT_LLM_PROVIDER')} "
            f"model={app.config.get('ASSISTANT_LLM_MODEL')}"
        )
        print(
            f"ANTHROPIC_API_KEY={'SET' if key else 'MISSING'} "
            f"ASSISTANT_LLM_ENABLED={app.config.get('ASSISTANT_LLM_ENABLED')} "
            f"is_llm_enabled={enabled}"
        )

    print('\n=== 2) Prompt surfaces (all server-side via module_assistant.llm) ===')
    for name in (
        'Cost narrative → GET /assets/api/narrative',
        'Portfolio forecast → POST /assets/api/forecast',
        'Asset failure/RUL → POST /assets/api/assets/<code>/predict',
        'Digital twin → POST /assets/api/floor-plans/<id>/recommend',
        'Ticket AI triage → POST /tickets/api/tickets/triage-preview',
        'Assistant LLM chat → POST /api/assistant/chat (when no structured intent)',
    ):
        print(f'  - {name}')

    print(f'\n=== 3) Live HTTP checks against {base} ===')
    status, login = req(base, 'POST', '/api/auth/login', body={'username': username, 'password': password})
    token = login.get('access_token') or login.get('token')
    if not token and isinstance(login.get('data'), dict):
        token = login['data'].get('access_token') or login['data'].get('token')
    print(f'login_status={status} token={"yes" if token else "no"}')
    if not token:
        print('LOGIN_FAIL', list(login.keys()), str(login)[:300])
        return 2

    st, plans = req(base, 'GET', '/assets/api/floor-plans', token=token)
    plan_id = plans['plans'][0]['id'] if st == 200 and plans.get('plans') else None
    print(f'floor_plan_id={plan_id}')

    st_a, _ = req(base, 'POST', '/api/assistant/chat', token=token, body={'message': 'hi'})
    asst_path = '/api/assistant/chat' if st_a not in (0, 404) else '/api/assistant/message'

    checks = [
        ('narrative', 'GET', '/assets/api/narrative', None, 'llm'),
        ('forecast', 'POST', '/assets/api/forecast', {}, 'llm'),
        ('predict AST-0001', 'POST', '/assets/api/assets/AST-0001/predict', {}, 'llm'),
        (
            'twin recommend',
            'POST',
            f'/assets/api/floor-plans/{plan_id}/recommend' if plan_id else '',
            {},
            'llm',
        ),
        (
            'triage-preview',
            'POST',
            '/tickets/api/tickets/triage-preview',
            {
                'title': 'Chiller high pressure alarm',
                'work_description': 'Tower A basement CH-01 high discharge pressure',
                'service_group': 'HVAC',
                'category': 'Chiller',
                'property_name': 'Tower A',
                'zone': 'Basement',
            },
            'llm',
        ),
        (
            'assistant critical assets',
            'POST',
            asst_path,
            {'message': 'List critical assets'},
            'structured_ok',  # may pass without LLM via intent tools
        ),
        (
            'assistant free chat',
            'POST',
            asst_path,
            {'message': 'Say hello in one short sentence as the FM assistant.'},
            'llm_chat',
        ),
    ]

    results = []
    for name, method, path, body, kind in checks:
        if not path:
            print(f'FAIL  {name}: skipped (no floor plan)')
            results.append((name, False))
            continue
        st, payload = req(base, method, path, token=token, body=body)
        err = payload.get('error') if isinstance(payload, dict) else None
        ok = 200 <= st < 300 and bool(payload.get('success', True))

        if kind == 'llm' and name == 'narrative':
            # Soft-fail path when LLM off: 200 + narrative null
            if enabled:
                ok = ok and bool(payload.get('narrative'))
            else:
                ok = False
                err = err or 'LLM off → narrative null'
        elif kind == 'llm_chat':
            # Free chat only uses Claude when enabled; otherwise fallback text still 200
            reply = (
                payload.get('reply')
                or payload.get('message')
                or (payload.get('data') or {}).get('reply')
                or (payload.get('data') or {}).get('message')
                or ''
            )
            if enabled:
                ok = ok and bool(str(reply).strip())
            else:
                ok = False
                err = err or 'LLM off — free chat will not use Claude'

        detail = err or f'http {st}'
        if ok:
            if name == 'forecast':
                fc = payload.get('forecast') or {}
                detail = str(fc.get('payload') or fc)[:140]
            elif name.startswith('predict'):
                detail = str(payload.get('prediction') or '')[:140]
            elif name == 'narrative':
                detail = (payload.get('narrative') or '')[:140]
            elif name == 'triage-preview':
                detail = str(payload.get('suggestion') or '')[:140]
            elif name.startswith('assistant'):
                data = payload.get('data') if isinstance(payload.get('data'), dict) else payload
                detail = str(data.get('reply') or data.get('message') or data)[:140]
            elif name == 'twin recommend':
                detail = str(payload.get('summary') or '')[:140]
            else:
                detail = 'ok'
            if err:
                detail = f'http {st}: {err}'

        print(f'{"PASS" if ok else "FAIL"}  {name}: {detail}')
        results.append((name, ok))

    passed = sum(1 for _, ok in results if ok)
    print('\n=== Summary ===')
    print(f'{passed}/{len(results)} passed')
    print(f'LLM_ENABLED={enabled}')
    if not enabled:
        print(
            'BLOCKER: add to .env then restart ./run:\n'
            '  ASSISTANT_LLM_PROVIDER=claude\n'
            '  ANTHROPIC_API_KEY=sk-ant-...\n'
            '  ASSISTANT_LLM_MODEL=claude-haiku-4-5\n'
            '  ASSISTANT_LLM_ENABLED=true'
        )
        return 1
    return 0 if passed == len(results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
