#!/usr/bin/env python3
"""Create local demo logins for the inspection approval chain.

Technician → Supervisor → Operations Manager → BD + Procurement → GM

Usage (from project root):
  ./venv/bin/python scripts/seed_inspection_chain_accounts.py

Shared password (override with SEED_TEAM_PASSWORD): DemoTech2026!

Idempotent. Does not load SAMPLE dashboard rows. Refuses remote Postgres unless
SEED_ALL_ALLOW_REMOTE=1.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

DEMO_PASSWORD = os.environ.get("SEED_TEAM_PASSWORD", "DemoTech2026!")

INSPECTION_ACCESS = dict(
    access_hvac=True,
    access_civil=True,
    access_cleaning=True,
    access_submitted_forms=True,
    access_ticketing=True,
)

CHAIN_USERS = (
    {
        "username": "demo_ops_mgr",
        "email": "ops@demo.injaaz.local",
        "full_name": "Demo Operations Manager",
        "designation": "operations_manager",
        "extra": {**INSPECTION_ACCESS, "access_hr": True},
    },
    {
        "username": "demo_bd",
        "email": "bd@demo.injaaz.local",
        "full_name": "Demo Business Development",
        "designation": "business_development",
        "extra": {
            "access_business_development": True,
            "access_quotations": True,
            "access_ticketing": True,
            "access_submitted_forms": True,
        },
    },
    {
        "username": "demo_procurement",
        "email": "proc@demo.injaaz.local",
        "full_name": "Demo Procurement",
        "designation": "procurement",
        "extra": {
            "access_procurement_module": True,
            "access_ticketing": True,
            "access_submitted_forms": True,
        },
    },
    {
        "username": "demo_gm",
        "email": "gm@demo.injaaz.local",
        "full_name": "Demo General Manager",
        "designation": "general_manager",
        "extra": {**INSPECTION_ACCESS, "access_hr": True, "access_procurement_module": True},
    },
)


def _assert_local_db(app) -> None:
    url = (app.config.get("SQLALCHEMY_DATABASE_URI") or "").lower()
    allow = os.environ.get("SEED_ALL_ALLOW_REMOTE", "").strip().lower() in ("1", "true", "yes")
    remote = url.startswith("postgres") or "render.com" in url or "amazonaws.com" in url
    if remote and "sqlite" not in url and not allow:
        raise SystemExit(
            f"Refusing to seed a remote database ({url!r}). "
            "Set SEED_ALL_ALLOW_REMOTE=1 to override."
        )


def _ensure_user(*, username, email, full_name, designation, extra=None):
    from app.models import User, db

    extra = extra or {}
    user = User.query.filter_by(username=username).first()
    created = False
    if not user:
        user = User(
            username=username,
            email=email,
            full_name=full_name,
            role="user",
            designation=designation,
            is_active=True,
            password_changed=True,
        )
        user.set_password(DEMO_PASSWORD)
        db.session.add(user)
        db.session.flush()
        created = True
    user.designation = designation
    user.is_active = True
    user.password_changed = True
    user.full_name = user.full_name or full_name
    if email and not user.email:
        user.email = email
    for key, val in extra.items():
        if hasattr(user, key):
            setattr(user, key, val)
    user.set_password(DEMO_PASSWORD)
    return user, created


def _grant_inspection_access(user) -> None:
    for key, val in INSPECTION_ACCESS.items():
        if hasattr(user, key):
            setattr(user, key, val)
    user.password_changed = True
    user.is_active = True
    user.set_password(DEMO_PASSWORD)


def seed_inspection_chain_accounts(password: str | None = None) -> dict:
    """Idempotent. Requires an application context."""
    global DEMO_PASSWORD
    if password:
        DEMO_PASSWORD = password

    from app.models import TicketSupervisorTeam, User, db
    from scripts.seed_supervisors_teams import seed_supervisors_teams

    teams = seed_supervisors_teams(password=DEMO_PASSWORD)

    created = list(teams.get("created_supervisors") or []) + list(teams.get("created_technicians") or [])
    people = {}

    for spec in CHAIN_USERS:
        user, was_new = _ensure_user(
            username=spec["username"],
            email=spec["email"],
            full_name=spec["full_name"],
            designation=spec["designation"],
            extra=spec.get("extra") or {},
        )
        people[spec["username"]] = user
        if was_new:
            created.append(spec["username"])

    tech = User.query.filter_by(username="demo_tech_alpha_1").first()
    sup = User.query.filter_by(username="demo_sup_alpha").first()
    om = people["demo_ops_mgr"]
    if tech:
        _grant_inspection_access(tech)
        tech.designation = "technician"
        tech.reporting_manager_id = sup.id if sup else None
        tech.operations_manager_id = om.id
        people["demo_tech_alpha_1"] = tech
    if sup:
        _grant_inspection_access(sup)
        sup.designation = "supervisor"
        people["demo_sup_alpha"] = sup

    if tech and sup:
        pair = TicketSupervisorTeam.query.filter_by(
            supervisor_id=sup.id, technician_id=tech.id
        ).first()
        if not pair:
            db.session.add(TicketSupervisorTeam(supervisor_id=sup.id, technician_id=tech.id, is_active=True))
        else:
            pair.is_active = True

    db.session.commit()
    return {
        "password": DEMO_PASSWORD,
        "created": created,
        "people": {name: u.id for name, u in people.items() if u},
    }


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    from Injaaz import create_app

    app = create_app()
    _assert_local_db(app)
    with app.app_context():
        result = seed_inspection_chain_accounts()

    print("Inspection chain demo accounts are ready.")
    print(f"Shared password: {result['password']}")
    if result["created"]:
        print("Created / reset: " + ", ".join(result["created"]))
    print()
    print("  Technician            demo_tech_alpha_1")
    print("  Supervisor            demo_sup_alpha")
    print("  Operations Manager    demo_ops_mgr")
    print("  Business Development  demo_bd")
    print("  Procurement           demo_procurement")
    print("  General Manager       demo_gm")
    print()
    print("Path: Technician → Supervisor → OM → BD + Procurement → GM")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
