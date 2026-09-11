"""Inspection approval uses each designated role, not admin-as-everyone."""
from __future__ import annotations

from datetime import datetime, timezone

SIG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def _mk(app, username, designation, **extra):
    from app.models import User, db

    with app.app_context():
        u = User(
            username=username,
            email=f"{username}@example.com",
            full_name=username.replace("_", " ").title(),
            role="user",
            designation=designation,
            is_active=True,
            password_changed=True,
            **extra,
        )
        u.set_password("ChainPass123")
        db.session.add(u)
        db.session.commit()
        return u.id


def _token(client, username):
    r = client.post("/api/auth/login", json={"username": username, "password": "ChainPass123"})
    assert r.status_code == 200, r.get_json()
    return r.get_json()["access_token"]


def _headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def test_inspection_chain_each_role_signs_in_order(app, client):
    from app.models import TicketSupervisorTeam, db
    from common.db_utils import create_submission_db

    tech_id = _mk(app, "chain_tech", "technician", access_hvac=True, access_submitted_forms=True)
    sup_id = _mk(app, "chain_sup", "supervisor", access_hvac=True, access_submitted_forms=True)
    om_id = _mk(app, "chain_om", "operations_manager", access_hvac=True, access_submitted_forms=True)
    _mk(app, "chain_bd", "business_development", access_business_development=True, access_submitted_forms=True)
    _mk(app, "chain_proc", "procurement", access_procurement_module=True, access_submitted_forms=True)
    _mk(app, "chain_gm", "general_manager", access_hvac=True, access_submitted_forms=True)

    with app.app_context():
        from app.models import User

        tech = db.session.get(User, tech_id)
        tech.reporting_manager_id = sup_id
        tech.operations_manager_id = om_id
        db.session.add(TicketSupervisorTeam(supervisor_id=sup_id, technician_id=tech_id, is_active=True))
        db.session.commit()

        visit = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        sub = create_submission_db(
            "inspection",
            {"site_name": "Role chain site", "visit_date": visit, "items": []},
            site_name="Role chain site",
            visit_date=visit,
            user_id=tech_id,
        )
        sid = sub.submission_id
        assert sub.workflow_status == "supervisor_review"
        assert sub.supervisor_id == sup_id

    expected = [
        ("chain_sup", "approve-supervisor", "operations_manager_review"),
        ("chain_om", "approve-ops-manager", "bd_procurement_review"),
        ("chain_bd", "approve-bd", "bd_procurement_review"),
        ("chain_proc", "approve-procurement", "general_manager_review"),
        ("chain_gm", "approve-gm", "completed"),
    ]
    for username, action, want in expected:
        token = _token(client, username)
        pending = client.get("/api/workflow/submissions/pending", headers=_headers(token))
        assert pending.status_code == 200, pending.get_json()
        ids = [row["submission_id"] for row in pending.get_json().get("submissions") or []]
        assert sid in ids, f"{username} did not see {sid} in pending ({ids})"
        r = client.post(
            f"/api/workflow/submissions/{sid}/{action}",
            json={"comments": f"{username} ok", "signature": SIG, "verified": True},
            headers=_headers(token),
        )
        assert r.status_code == 200, r.get_json()
        body = r.get_json() or {}
        got = (body.get("submission") or {}).get("workflow_status")
        if not got:
            with app.app_context():
                from app.models import Submission

                got = Submission.query.filter_by(submission_id=sid).first().workflow_status
        assert got == want, f"after {action} expected {want}, got {got}"
