#!/usr/bin/env python3
"""Full operational smoke test against a running Injaaz server.

Checks pages + JSON APIs across auth, ticketing, HR, assets, MMR, workflow,
procurement, QHSI, inspection, assistant, and admin.

Usage:
  CHECK_BASE_URL=http://127.0.0.1:5002 ./venv/bin/python scripts/operational_smoke_test.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PASS = 0
FAIL = 0
WARN = 0
RESULTS: list[tuple[str, str, str]] = []


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


def req(
    base: str,
    method: str,
    path: str,
    token: str | None = None,
    body=None,
    timeout: int = 60,
    expect_json: bool = True,
):
    data = None if body is None else json.dumps(body).encode()
    headers = {'Accept': 'application/json, text/html, */*'}
    if body is not None:
        headers['Content-Type'] = 'application/json'
    if token:
        headers['Authorization'] = f'Bearer {token}'
    request = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            raw = resp.read()
            ctype = resp.headers.get('Content-Type', '')
            if expect_json and 'json' in ctype:
                try:
                    payload = json.loads(raw.decode() or '{}')
                except json.JSONDecodeError:
                    payload = {'_raw': raw[:300].decode(errors='replace')}
            else:
                payload = {'_html': True, '_bytes': len(raw), '_ctype': ctype}
            return resp.status, payload
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw.decode() or '{}')
        except Exception:
            payload = {'_raw': raw[:400].decode(errors='replace')}
        return exc.code, payload
    except Exception as exc:  # noqa: BLE001
        return 0, {'error': str(exc)}


def record(name: str, ok: bool, detail: str = '', warn: bool = False) -> None:
    global PASS, FAIL, WARN
    if warn and not ok:
        WARN += 1
        status = 'WARN'
    elif ok:
        PASS += 1
        status = 'PASS'
    else:
        FAIL += 1
        status = 'FAIL'
    RESULTS.append((status, name, detail))
    print(f'  [{status}] {name}' + (f' — {detail}' if detail else ''))


def expect_status(name: str, status: int, payload, allowed=(200,), warn_on=()):
    if status in allowed:
        record(name, True, f'HTTP {status}')
        return True
    if status in warn_on:
        record(name, False, f'HTTP {status}: {str(payload)[:180]}', warn=True)
        return False
    record(name, False, f'HTTP {status}: {str(payload)[:180]}')
    return False


def page_ok(base, token, path, name=None):
    name = name or f'PAGE {path}'
    status, payload = req(base, 'GET', path, token=token, expect_json=False)
    return expect_status(name, status, payload, allowed=(200,))


def api_ok(base, token, method, path, name=None, body=None, allowed=(200,), warn_on=()):
    name = name or f'{method} {path}'
    status, payload = req(base, method, path, token=token, body=body)
    ok = expect_status(name, status, payload, allowed=allowed, warn_on=warn_on)
    return ok, status, payload


def main() -> int:
    os.chdir(ROOT)
    _load_dotenv()
    base = os.environ.get('CHECK_BASE_URL', 'http://127.0.0.1:5002').rstrip('/')
    username = (
        os.environ.get('DEFAULT_ADMIN_USERNAME')
        or os.environ.get('CHECK_USERNAME')
        or 'Kynvera'
    )
    password = (
        os.environ.get('DEFAULT_ADMIN_PASSWORD')
        or os.environ.get('CHECK_PASSWORD')
        or 'Arshith&Taha@2026'
    )

    print(f'\n=== Operational smoke test → {base} ===\n')

    # ── 1. Health / public ──────────────────────────────────
    print('1) Health & public pages')
    st, payload = req(base, 'GET', '/health')
    expect_status('GET /health', st, payload, allowed=(200,))
    if st == 200 and isinstance(payload, dict):
        record(
            'health.database',
            payload.get('database') == 'healthy' or payload.get('status') == 'healthy',
            str(payload.get('database') or payload.get('status')),
        )
    for path in ('/', '/login', '/offline', '/manifest.json'):
        page_ok(base, None, path)

    # ── 2. Auth ─────────────────────────────────────────────
    print('\n2) Auth flow')
    st, login = req(base, 'POST', '/api/auth/login', body={'username': username, 'password': password})
    if not expect_status('POST /api/auth/login', st, login, allowed=(200,)):
        print('\nCannot continue without login. Aborting.')
        return 1
    token = (
        login.get('access_token')
        or login.get('token')
        or (login.get('data') or {}).get('access_token')
    )
    if not token:
        # Some responses nest under tokens
        tokens = login.get('tokens') or {}
        token = tokens.get('access_token') or tokens.get('access')
    if not token:
        record('auth.access_token', False, f'No token in response keys={list(login.keys())}')
        print('\nAborting — no access token.')
        return 1
    record('auth.access_token', True, 'present')

    ok, st, me = api_ok(base, token, 'GET', '/api/auth/me')
    if ok:
        user = me.get('user') or me.get('data') or me
        record(
            'auth.me.username',
            bool(user.get('username') or user.get('email')),
            str(user.get('username') or user.get('email') or user.get('role')),
        )
    api_ok(base, token, 'GET', '/api/hub/config', allowed=(200, 404), warn_on=(404,))
    api_ok(base, token, 'POST', '/api/auth/refresh', allowed=(200, 401, 422), warn_on=(401, 422))

    # ── 3. Dashboard / shells ───────────────────────────────
    print('\n3) Dashboard & module shells')
    for path in (
        '/dashboard',
        '/about',
        '/admin',
        '/admin/dashboard',
        '/dochub',
        '/workflow/pending-reviews',
        '/workflow/submitted-forms',
    ):
        page_ok(base, token, path)

    # ── 4. Ticketing ────────────────────────────────────────
    print('\n4) Ticketing')
    for path in (
        '/tickets/',
        '/tickets/list',
        '/tickets/new',
        '/tickets/drafts',
        '/tickets/settings',
    ):
        page_ok(base, token, path)

    api_ok(base, token, 'GET', '/tickets/api/options')
    api_ok(base, token, 'GET', '/tickets/api/settings/projects')
    api_ok(base, token, 'GET', '/tickets/api/settings/location-tree')
    ok, st, opts = api_ok(base, token, 'GET', '/tickets/api/options')
    _, _, proj_payload = api_ok(base, token, 'GET', '/tickets/api/settings/projects')
    projects = proj_payload.get('projects') or []
    if not projects:
        record('tickets.projects.seeded', False, 'no projects — run scripts/seed_ticketing_data.py', warn=True)

    # Create a ticket with required operational fields
    created_ticket_id = None
    project_name = ''
    if projects:
        p0 = projects[0]
        project_name = (p0.get('name') if isinstance(p0, dict) else str(p0)) or ''
    options = (opts.get('options') if isinstance(opts, dict) else {}) or {}
    # Prefer HVAC / AC fault path when catalog present
    service_group = 'HVAC systems'
    category = 'Air Conditioner'
    fault_type = 'Not Cooling'
    cats = options.get('categories') if isinstance(options, dict) else None
    if isinstance(cats, dict) and cats:
        service_group = next(iter(cats.keys()))
        cat_list = cats.get(service_group) or []
        if cat_list:
            category = cat_list[0]
            fault_type = category
    priority = 'medium'
    pri_list = options.get('priorities') if isinstance(options, dict) else None
    if isinstance(pri_list, list) and pri_list:
        first = pri_list[0]
        priority = first.get('value') if isinstance(first, dict) else str(first)

    create_body = {
        'title': f'Operational smoke test {int(time.time())}',
        'project': project_name or 'Marina Towers',
        'service_group': service_group,
        'category': category,
        'fault_type': fault_type,
        'priority': priority,
        'work_description': 'Automated operational smoke test — safe to close.',
    }

    ok, st, created = api_ok(
        base,
        token,
        'POST',
        '/tickets/api/tickets',
        name='POST /tickets/api/tickets (create)',
        body=create_body,
        allowed=(200, 201),
        warn_on=(400, 422),
    )
    if ok:
        created_ticket_id = (
            created.get('ticket_id')
            or created.get('id')
            or (created.get('ticket') or {}).get('ticket_id')
            or (created.get('ticket') or {}).get('id')
            or (created.get('data') or {}).get('ticket_id')
            or (created.get('data') or {}).get('id')
        )
        if created_ticket_id:
            page_ok(base, token, f'/tickets/{created_ticket_id}', f'PAGE /tickets/{created_ticket_id}')
            api_ok(
                base,
                token,
                'POST',
                f'/tickets/api/tickets/{created_ticket_id}/notes',
                name='POST ticket note',
                body={'content': 'Smoke test note'},
                allowed=(200, 201),
                warn_on=(400, 404, 405, 422),
            )
        else:
            record('ticket.create.id', False, f'created but no id: keys={list(created.keys())}', warn=True)

    api_ok(
        base,
        token,
        'POST',
        '/tickets/api/tickets/triage-preview',
        name='POST triage-preview',
        body={
            'title': 'AC not cooling in lobby',
            'description': 'HVAC unit blowing warm air near reception.',
            'location': 'Building A Lobby',
        },
        allowed=(200,),
        warn_on=(400, 503, 501),
    )

    # ── 5. HR ───────────────────────────────────────────────
    print('\n5) HR module')
    for path in (
        '/hr/',
        '/hr/my-requests',
        '/hr/pending-review',
        '/hr/approved-forms',
        '/hr/leave-application-form',
        '/hr/hiring',
        '/hr/leave-tracker',
    ):
        page_ok(base, token, path)

    api_ok(base, token, 'GET', '/hr/api/notifications/unread-count')
    api_ok(base, token, 'GET', '/hr/api/notifications', allowed=(200,), warn_on=(404,))
    api_ok(base, token, 'GET', '/hr/api/hiring/candidates', allowed=(200,), warn_on=(404,))
    api_ok(base, token, 'GET', '/hr/api/leave-tracker/employees', allowed=(200,), warn_on=(404,))
    api_ok(base, token, 'GET', '/hr/api/leave-tracker/logs', allowed=(200,), warn_on=(404,))
    api_ok(base, token, 'GET', '/hr/api/leave-tracker/plans', allowed=(200,), warn_on=(404,))
    api_ok(base, token, 'GET', '/hr/api/leave-tracker/template', allowed=(200,), warn_on=(404,))

    # Minimal leave form submit (may warn if validation strict)
    leave_payload = {
        'form_type': 'leave_application',
        'data': {
            'employee_name': 'Smoke Test User',
            'employee_id': 'SMOKE-001',
            'leave_type': 'Annual',
            'from_date': '2026-08-10',
            'to_date': '2026-08-12',
            'reason': 'Operational smoke test',
            'number_of_days': 3,
        },
    }
    api_ok(
        base,
        token,
        'POST',
        '/hr/api/submit',
        name='POST /hr/api/submit (leave)',
        body=leave_payload,
        allowed=(200, 201),
        warn_on=(400, 422),
    )

    # ── 6. Assets ───────────────────────────────────────────
    print('\n6) FM Assets')
    for path in (
        '/assets/',
        '/assets/executive',
        '/assets/twin',
        '/assets/list',
        '/assets/map',
        '/assets/new',
    ):
        page_ok(base, token, path)

    ok, st, assets = api_ok(base, token, 'GET', '/assets/api/assets')
    asset_code = None
    if ok:
        items = assets.get('assets') or assets.get('data') or assets.get('items') or []
        if isinstance(items, list) and items:
            a0 = items[0]
            # Detail routes key on asset_id (e.g. AST-0002), not numeric PK
            asset_code = a0.get('asset_id') or a0.get('asset_code') or a0.get('code')
            if asset_code:
                page_ok(base, token, f'/assets/{asset_code}', f'PAGE /assets/{asset_code}')
                api_ok(base, token, 'GET', f'/assets/api/assets/{asset_code}')
            else:
                record('assets.detail.key', False, f'no asset_id on item keys={list(a0.keys())}', warn=True)
        else:
            record('assets.list.nonempty', False, 'no assets seeded', warn=True)

    api_ok(base, token, 'GET', '/assets/api/kpis', allowed=(200,), warn_on=(404, 501))
    api_ok(base, token, 'GET', '/assets/api/narrative', allowed=(200,), warn_on=(404, 501, 503))

    # ── 7. MMR ──────────────────────────────────────────────
    print('\n7) MMR / Report Generation')
    page_ok(base, token, '/admin/mmr/')
    page_ok(base, token, '/admin/mmr-chargeable')
    api_ok(base, token, 'GET', '/admin/mmr/api/current-upload', allowed=(200,), warn_on=(404,))
    api_ok(base, token, 'GET', '/admin/mmr/api/email-config', allowed=(200,), warn_on=(404,))
    api_ok(base, token, 'GET', '/admin/mmr/api/automation-status', allowed=(200,), warn_on=(404,))
    api_ok(base, token, 'GET', '/admin/mmr/api/cycles', allowed=(200,), warn_on=(404,))

    # Prefer raw CAFM export (Reactive Workorder Details); else generated report
    sample = None
    for cand in [
        ROOT / 'HR Documents' / 'RM Deatils MMR (4).xlsx',
        ROOT / 'HR Documents - Copy' / 'RM Deatils MMR (4).xlsx',
    ]:
        if cand.exists():
            sample = cand
            break
    if sample is None:
        for cand in ROOT.rglob('*Resolved and Pending Complaints*.xlsx'):
            if 'generated' in str(cand):
                continue
            sample = cand
            break
    if sample and sample.exists():
        try:
            boundary = '----injaazSmokeBoundary'
            file_bytes = sample.read_bytes()
            filename = sample.name
            body_parts = [
                f'--{boundary}\r\n'.encode(),
                f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
                b'Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n',
                file_bytes,
                b'\r\n',
                f'--{boundary}--\r\n'.encode(),
            ]
            data = b''.join(body_parts)
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': f'multipart/form-data; boundary={boundary}',
                'Accept': 'application/json',
            }
            request = urllib.request.Request(
                base + '/admin/mmr/api/upload',
                data=data,
                headers=headers,
                method='POST',
            )
            try:
                with urllib.request.urlopen(request, timeout=120) as resp:
                    raw = resp.read().decode()
                    payload = json.loads(raw) if raw else {}
                    expect_status(
                        f'POST /admin/mmr/api/upload ({sample.name})',
                        resp.status,
                        payload,
                        allowed=(200, 201),
                    )
            except urllib.error.HTTPError as exc:
                raw = exc.read().decode(errors='replace')
                expect_status(
                    'POST /admin/mmr/api/upload',
                    exc.code,
                    {'_raw': raw[:200]},
                    allowed=(200, 201),
                    warn_on=(400, 413, 422),
                )
        except Exception as exc:  # noqa: BLE001
            record('POST /admin/mmr/api/upload', False, str(exc), warn=True)
    else:
        record('MMR sample xlsx', False, 'no sample file found — skip upload', warn=True)

    # Download may regenerate from uploaded file (raw CAFM or saved report)
    st, payload = req(base, 'GET', '/admin/mmr/api/download-report', token=token, expect_json=False, timeout=120)
    expect_status('GET /admin/mmr/api/download-report', st, payload, allowed=(200,), warn_on=(404, 400))

    # ── 8. Inspection / trade forms ─────────────────────────
    print('\n8) Inspection & trade forms')
    for path in (
        '/inspection/',
        '/inspection/form',
    ):
        page_ok(base, token, path)
    api_ok(base, token, 'GET', '/inspection/dropdowns', allowed=(200,), warn_on=(404,))

    # ── 9. Procurement / QHSI / DocHub / BD ─────────────────
    print('\n9) Procurement, QHSI, DocHub, BD')
    for path in (
        '/procurement/',
        '/procurement/materials',
        '/qhsi/',
        '/bd/email-module',
        '/admin/devices',
        '/admin/bd',
        '/admin/team-management',
        '/admin/knowledge-base',
        '/admin/personal-progress',
    ):
        page_ok(base, token, path)

    api_ok(base, token, 'GET', '/procurement/api/materials', allowed=(200,), warn_on=(404,))
    api_ok(base, token, 'GET', '/qhsi/api/stats', allowed=(200,), warn_on=(404,))
    api_ok(base, token, 'GET', '/api/docs', allowed=(200,), warn_on=(404,))
    api_ok(base, token, 'GET', '/api/admin/dashboard-overview', allowed=(200,), warn_on=(404,))
    api_ok(base, token, 'GET', '/api/admin/users', allowed=(200,), warn_on=(404,))
    api_ok(base, token, 'GET', '/api/workflow/submissions/pending', allowed=(200,), warn_on=(404,))
    api_ok(base, token, 'GET', '/api/workflow/dashboard-stats', allowed=(200,), warn_on=(404,))

    # ── 10. Assistant ───────────────────────────────────────
    print('\n10) Assistant')
    api_ok(
        base,
        token,
        'POST',
        '/api/assistant/chat',
        name='POST /api/assistant/chat',
        body={'message': 'Reply with exactly: smoke-ok'},
        allowed=(200,),
        warn_on=(503, 501, 400),
    )

    # ── Summary ─────────────────────────────────────────────
    print('\n' + '=' * 60)
    print(f'RESULTS: {PASS} passed, {FAIL} failed, {WARN} warnings')
    print('=' * 60)
    if FAIL:
        print('\nFailures:')
        for status, name, detail in RESULTS:
            if status == 'FAIL':
                print(f'  - {name}: {detail}')
    if WARN:
        print('\nWarnings:')
        for status, name, detail in RESULTS:
            if status == 'WARN':
                print(f'  - {name}: {detail}')
    print()
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
