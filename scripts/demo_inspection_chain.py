#!/usr/bin/env python3
"""Seed inspection-chain demo accounts, then walk a live form through every role.

Requires the app to already be running (default http://127.0.0.1:5002).

  ./venv/bin/python scripts/seed_inspection_chain_accounts.py
  ./venv/bin/python scripts/demo_inspection_chain.py --base-url http://127.0.0.1:5002
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

SIG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
PASSWORD = os.environ.get("SEED_TEAM_PASSWORD", "DemoTech2026!")

STEPS = (
    ("demo_tech_alpha_1", None, "technician submit"),
    ("demo_sup_alpha", "approve-supervisor", "supervisor_review → operations_manager_review"),
    ("demo_ops_mgr", "approve-ops-manager", "operations_manager_review → bd_procurement_review"),
    ("demo_bd", "approve-bd", "BD signed (waiting on Procurement)"),
    ("demo_procurement", "approve-procurement", "bd_procurement_review → general_manager_review"),
    ("demo_gm", "approve-gm", "general_manager_review → completed"),
)


def _json(method: str, url: str, token: str | None = None, body: dict | None = None, timeout: int = 90) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"error": raw[:400]}
        raise SystemExit(f"{method} {url} → HTTP {exc.code}: {payload}") from exc
    except URLError as exc:
        raise SystemExit(f"Cannot reach {url}: {exc.reason}. Is ./run listening?") from exc


def _login(base: str, username: str) -> str:
    payload = _json("POST", f"{base}/api/auth/login", body={"username": username, "password": PASSWORD})
    token = payload.get("access_token")
    if not token:
        raise SystemExit(f"Login failed for {username}: {payload}")
    return token


def _mint_tokens(usernames: tuple[str, ...]) -> dict[str, str]:
    from dotenv import load_dotenv
    from flask_jwt_extended import create_access_token

    load_dotenv(ROOT / ".env")
    from Injaaz import create_app
    from app.models import User

    app = create_app()
    tokens: dict[str, str] = {}
    with app.app_context():
        for username in usernames:
            user = User.query.filter_by(username=username).first()
            if not user:
                raise SystemExit(f"User not found: {username}. Run scripts/seed_inspection_chain_accounts.py")
            tokens[username] = create_access_token(identity=str(user.id))
    return tokens


def _status(base: str, token: str, sid: str) -> str:
    payload = _json("GET", f"{base}/api/workflow/submissions/{sid}", token=token)
    return str(payload.get("workflow_status") or payload.get("status") or "")


def _pending_ids(base: str, token: str) -> list[str]:
    payload = _json("GET", f"{base}/api/workflow/submissions/pending", token=token)
    rows = payload.get("submissions") or []
    return [str(r.get("submission_id") or "") for r in rows]


def _submit(base: str, token: str) -> str:
    today = date.today().isoformat()
    payload = _json(
        "POST",
        f"{base}/inspection/submit-with-urls",
        token=token,
        body={
            "site_name": "Inspection chain demo — Marina Towers",
            "visit_date": today,
            "category": "General",
            "tech_signature": SIG,
            "items": [
                {
                    "asset": "AHU-01",
                    "system": "HVAC",
                    "description": "Live chain demo inspection item",
                    "quantity": "1",
                    "brand": "Carrier",
                    "specification": "Demo",
                    "comments": "Submitted by demo technician",
                    "photo_urls": [],
                }
            ],
        },
    )
    sid = payload.get("submission_id")
    if not sid:
        raise SystemExit(f"Submit did not return a submission_id: {payload}")
    return str(sid)


def main() -> int:
    parser = argparse.ArgumentParser(description="Live inspection-chain demo")
    parser.add_argument("--base-url", default="http://127.0.0.1:5002")
    parser.add_argument("--skip-seed", action="store_true")
    parser.add_argument("--via-login", action="store_true", help="Use /api/auth/login (subject to 5/min rate limit)")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    if not args.skip_seed:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
        from Injaaz import create_app
        from scripts.seed_inspection_chain_accounts import _assert_local_db, seed_inspection_chain_accounts

        app = create_app()
        _assert_local_db(app)
        with app.app_context():
            seed_inspection_chain_accounts(password=PASSWORD)

    names = tuple(username for username, _, _ in STEPS)
    if args.via_login:
        tokens = {name: _login(base, name) for name in names[:4]}
        # Stay under login rate limit (5/min) for the last two roles.
        import time
        time.sleep(61)
        for name in names[4:]:
            tokens[name] = _login(base, name)
    else:
        tokens = _mint_tokens(names)

    tech_token = tokens["demo_tech_alpha_1"]
    sid = _submit(base, tech_token)
    status = _status(base, tech_token, sid)
    print(f"Submitted {sid}")
    print(f"  after technician: {status}")
    if status != "supervisor_review":
        raise SystemExit(f"Expected supervisor_review after technician submit, got {status!r}")

    expected_after = {
        "approve-supervisor": "operations_manager_review",
        "approve-ops-manager": "bd_procurement_review",
        "approve-bd": "bd_procurement_review",
        "approve-procurement": "general_manager_review",
        "approve-gm": "completed",
    }

    for username, action, label in STEPS[1:]:
        token = tokens[username]
        pending = _pending_ids(base, token)
        if sid not in pending:
            raise SystemExit(f"{username} pending queue does not include {sid}. Saw: {pending[:8]}")
        payload = _json(
            "POST",
            f"{base}/api/workflow/submissions/{sid}/{action}",
            token=token,
            body={"comments": f"Demo {username} signed", "signature": SIG, "verified": True},
        )
        status = str(
            (payload.get("submission") or {}).get("workflow_status")
            or _status(base, token, sid)
        )
        want = expected_after[action]
        print(f"  {username} ({action}): {status}  — {label}")
        if status != want:
            raise SystemExit(f"Expected {want} after {action}, got {status!r}")

    print()
    print(f"OK — {sid} completed through Technician → Supervisor → OM → BD → Procurement → GM")
    print("Logins (shared password DemoTech2026! unless SEED_TEAM_PASSWORD is set):")
    print("  demo_tech_alpha_1  demo_sup_alpha  demo_ops_mgr  demo_bd  demo_procurement  demo_gm")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
