"""Regression: ticketing project settings and triage-confirm authorization."""
import uuid

import pytest


def _login_headers(client, username, password='TestPass123!'):
    r = client.post('/api/auth/login', json={'username': username, 'password': password})
    assert r.status_code == 200, r.get_json()
    token = r.get_json().get('access_token')
    assert token
    return {'Authorization': f'Bearer {token}'}


def _make_user(app, *, username, access_ticketing=True, designation=None, role='user'):
    from app.models import db, User

    with app.app_context():
        user = User(
            username=username,
            email=f'{username}@test.example',
            full_name=username.replace('_', ' ').title(),
            role=role,
            designation=designation,
            is_active=True,
            password_changed=True,
            access_ticketing=access_ticketing,
        )
        user.set_password('TestPass123!')
        db.session.add(user)
        db.session.commit()
        return user.id, user.username


@pytest.fixture
def tkt_users(app):
    suffix = uuid.uuid4().hex[:8]
    tech_id, tech_u = _make_user(app, username=f'tech_{suffix}', designation=None)
    admin_id, admin_u = _make_user(app, username=f'admin_{suffix}', role='admin')
    ops_id, ops_u = _make_user(
        app, username=f'ops_{suffix}', designation='operations_manager'
    )
    return {
        'tech': (tech_id, tech_u),
        'admin': (admin_id, admin_u),
        'ops': (ops_id, ops_u),
    }


def test_technician_cannot_rewrite_project_invoice_emails(client, app, tkt_users):
    """Bare access_ticketing must not update finance/ops invoice recipients."""
    from app.models import TicketProject, db

    tech_id, tech_u = tkt_users['tech']
    with app.app_context():
        p = TicketProject(name=f'Proj-{uuid.uuid4().hex[:6]}', finance_emails='finance@safe.example')
        db.session.add(p)
        db.session.commit()
        pid = p.id

    headers = _login_headers(client, tech_u)
    r = client.put(
        f'/tickets/api/settings/projects/{pid}',
        headers=headers,
        json={'finance_emails': 'attacker@evil.example', 'ops_emails': 'attacker@evil.example'},
    )
    assert r.status_code == 403, r.get_json()

    with app.app_context():
        refreshed = db.session.get(TicketProject, pid)
        assert refreshed.finance_emails == 'finance@safe.example'
        assert refreshed.ops_emails is None


def test_technician_cannot_create_project(client, app, tkt_users):
    _, tech_u = tkt_users['tech']
    headers = _login_headers(client, tech_u)
    r = client.post(
        '/tickets/api/settings/projects',
        headers=headers,
        json={'name': f'Hijack-{uuid.uuid4().hex[:6]}', 'finance_emails': 'attacker@evil.example'},
    )
    assert r.status_code == 403, r.get_json()


def test_admin_can_update_project_emails(client, app, tkt_users):
    from app.models import TicketProject, db

    _, admin_u = tkt_users['admin']
    with app.app_context():
        p = TicketProject(name=f'AdminProj-{uuid.uuid4().hex[:6]}')
        db.session.add(p)
        db.session.commit()
        pid = p.id

    headers = _login_headers(client, admin_u)
    r = client.put(
        f'/tickets/api/settings/projects/{pid}',
        headers=headers,
        json={'finance_emails': 'finance@client.example'},
    )
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['success'] is True

    with app.app_context():
        refreshed = db.session.get(TicketProject, pid)
        assert refreshed.finance_emails == 'finance@client.example'


def test_ops_manager_can_create_project(client, app, tkt_users):
    _, ops_u = tkt_users['ops']
    headers = _login_headers(client, ops_u)
    name = f'OpsProj-{uuid.uuid4().hex[:6]}'
    r = client.post(
        '/tickets/api/settings/projects',
        headers=headers,
        json={'name': name},
    )
    assert r.status_code == 201, r.get_json()
    assert r.get_json()['project']['name'] == name


def test_triage_confirm_cannot_mutate_invisible_ticket(client, app, tkt_users):
    """triage-confirm must not rewrite priority/SLA on tickets the caller cannot view."""
    from app.models import Ticket, TicketTriageLog, db

    tech_id, tech_u = tkt_users['tech']
    other_id, _ = _make_user(app, username=f'other_{uuid.uuid4().hex[:8]}')

    with app.app_context():
        ticket = Ticket(
            ticket_id='TKT-' + uuid.uuid4().hex[:8].upper(),
            reporter_id=other_id,
            project='Tower',
            service_group='HVAC',
            category='Cooling',
            fault_type='Leak',
            priority='medium',
            title='Invisible ticket',
            work_description='Should not be mutable by unrelated tech',
            status='open',
            sla_hours=24,
        )
        db.session.add(ticket)
        db.session.flush()
        log = TicketTriageLog(
            ticket_id=ticket.id,
            ticket_code=ticket.ticket_id,
            suggested={'priority': 'low', 'sla_hours': 48},
            decision='preview',
        )
        db.session.add(log)
        db.session.commit()
        ticket_code = ticket.ticket_id
        triage_log_id = log.id
        ticket_db_id = ticket.id

    headers = _login_headers(client, tech_u)
    r = client.post(
        '/tickets/api/tickets/triage-confirm',
        headers=headers,
        json={
            'triage_log_id': triage_log_id,
            'ticket_id': ticket_code,
            'apply_to_ticket': True,
            'accepted': {'priority': 'critical', 'sla_hours': 1},
        },
    )
    assert r.status_code == 403, r.get_json()

    with app.app_context():
        refreshed = db.session.get(Ticket, ticket_db_id)
        assert refreshed.priority == 'medium'
        assert refreshed.sla_hours == 24


def test_add_missing_table_columns_is_dialect_aware(app):
    """Helper must use SQLAlchemy inspect, not SQLite-only PRAGMA."""
    from sqlalchemy import text
    from app.models import db
    from module_ticketing.routes import _add_missing_table_columns

    table = f'tkt_mig_probe_{uuid.uuid4().hex[:8]}'
    with app.app_context():
        with db.engine.begin() as conn:
            conn.execute(text(f'CREATE TABLE {table} (id INTEGER PRIMARY KEY)'))
        try:
            _add_missing_table_columns(table, [('finance_emails', 'VARCHAR(500)')])
            from sqlalchemy import inspect as sa_inspect
            cols = {c['name'] for c in sa_inspect(db.engine).get_columns(table)}
            assert 'finance_emails' in cols
        finally:
            with db.engine.begin() as conn:
                conn.execute(text(f'DROP TABLE {table}'))
