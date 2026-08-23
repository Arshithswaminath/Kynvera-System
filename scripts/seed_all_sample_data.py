#!/usr/bin/env python3
"""Fill every SQLAlchemy model with local sample rows so dashboards are not empty.

Usage (from project root):
  ./venv/bin/python scripts/seed_all_sample_data.py

Idempotent: unique SAMPLE- keys / [SAMPLE] tags. Re-runs merge, they do not wipe
existing real data.

Refuses a remote/Postgres URL unless SEED_ALL_ALLOW_REMOTE=1.
"""
from __future__ import annotations

import hashlib
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

SEED_TAG = '[SAMPLE]'
DEMO_PASSWORD = os.environ.get('SEED_TEAM_PASSWORD', 'DemoTech2026!')
TINY_PNG = (
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
    b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01'
    b'\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
)
SIG = (
    'data:image/png;base64,'
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
)


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _days(n: int) -> datetime:
    return _utcnow() + timedelta(days=n)


def _assert_local_db(app) -> None:
    url = (app.config.get('SQLALCHEMY_DATABASE_URI') or '').lower()
    allow = os.environ.get('SEED_ALL_ALLOW_REMOTE', '').strip() in ('1', 'true', 'yes')
    remote = (
        url.startswith('postgres')
        or 'render.com' in url
        or 'amazonaws.com' in url
    )
    if remote and 'sqlite' not in url and not allow:
        raise SystemExit(
            f'Refusing to seed a remote database ({url!r}). '
            'Set SEED_ALL_ALLOW_REMOTE=1 to override.'
        )


def _goc(model, defaults: dict | None = None, **filters):
    from app.models import db
    row = model.query.filter_by(**filters).first()
    if row:
        return row, False
    payload = dict(filters)
    if defaults:
        payload.update(defaults)
    row = model(**payload)
    db.session.add(row)
    db.session.flush()
    return row, True


def _ensure_user(*, username, email, full_name, role='user', designation=None, **access):
    from app.models import db, User
    user = User.query.filter_by(username=username).first()
    if user:
        if designation and not user.designation:
            user.designation = designation
        for key, val in access.items():
            if key.startswith('access_') and not getattr(user, key, False):
                setattr(user, key, val)
        if not user.admin_visible_password:
            user.set_password(DEMO_PASSWORD)
        return user
    user = User(
        username=username,
        email=email,
        full_name=full_name,
        role=role,
        designation=designation,
        is_active=True,
        password_changed=True,
        phone='+971 50 100 0000',
        employment_start_date=date(2022, 3, 1),
        job_designation=full_name,
        annual_leave_days=30,
        other_leave_days=15,
        assigned_project='Marina Towers',
    )
    for key, val in access.items():
        if hasattr(user, key):
            setattr(user, key, val)
    user.set_password(DEMO_PASSWORD)
    db.session.add(user)
    db.session.flush()
    return user


def seed_reference_catalogs():
    """Existing get-or-create seeds: locations, assets, teams, ticket fields, vendors."""
    from app.models import Asset, TicketProject, TicketSupervisorTeam, User
    from module_ticketing.ticket_field_catalog import seed_ticket_field_catalogs
    from module_ticketing.project_resources import (
        seed_sample_vendors_if_empty,
        seed_supervisor_roster_from_legacy,
    )

    if TicketProject.query.count() == 0:
        from scripts.seed_ticketing_data import seed_ticketing_data
        seed_ticketing_data()

    if Asset.query.count() == 0:
        from scripts.seed_fm_assets import seed as seed_fm_assets
        seed_fm_assets()

    has_demo = User.query.filter_by(username='demo_sup_alpha').first()
    if not has_demo or TicketSupervisorTeam.query.count() == 0:
        from scripts.seed_supervisors_teams import seed_supervisors_teams
        seed_supervisors_teams(password=DEMO_PASSWORD)

    seed_ticket_field_catalogs()
    seed_sample_vendors_if_empty()
    seed_supervisor_roster_from_legacy()


def seed_people():
    from app.models import db, DocHubAccess, User

    admin = (
        User.query.filter_by(role='admin').first()
        or _ensure_user(
            username=os.environ.get('DEFAULT_ADMIN_USERNAME', 'Kynvera'),
            email='admin@injaaz.com',
            full_name='System Administrator',
            role='admin',
        )
    )
    om = _ensure_user(
        username='demo_ops_mgr', email='ops@demo.injaaz.local',
        full_name='Demo Operations Manager', designation='operations_manager',
        access_ticketing=True, access_hr=True, access_hvac=True,
        access_civil=True, access_cleaning=True, access_submitted_forms=True,
        access_report_generation=True, is_ticket_reporter=True,
    )
    bd = _ensure_user(
        username='demo_bd', email='bd@demo.injaaz.local',
        full_name='Demo Business Development', designation='business_development',
        access_business_development=True, access_ticketing=True, access_quotations=True,
    )
    proc = _ensure_user(
        username='demo_procurement', email='proc@demo.injaaz.local',
        full_name='Demo Procurement', designation='procurement',
        access_procurement_module=True, access_ticketing=True,
    )
    gm = _ensure_user(
        username='demo_gm', email='gm@demo.injaaz.local',
        full_name='Demo General Manager', designation='general_manager',
        access_hr=True, access_ticketing=True, access_qhsi=True,
        access_submitted_forms=True,
    )
    hr = _ensure_user(
        username='demo_hr', email='hr@demo.injaaz.local',
        full_name='Demo HR Manager', designation='hr_manager',
        access_hr=True, access_files=True,
    )
    qhsi = _ensure_user(
        username='demo_qhsi', email='qhsi@demo.injaaz.local',
        full_name='Demo QHSI Officer',
        access_qhsi=True, access_hvac=True, access_civil=True, access_cleaning=True,
    )
    files_user = _ensure_user(
        username='demo_files', email='files@demo.injaaz.local',
        full_name='Demo Files User', access_files=True,
    )
    reporter = _ensure_user(
        username='demo_reporter', email='reporter@demo.injaaz.local',
        full_name='Fatima Al Maktoum',
        access_ticketing=True, is_ticket_reporter=True,
        job_designation='Client Services',
    )

    tech = User.query.filter_by(username='demo_tech_alpha_1').first()
    sup = User.query.filter_by(username='demo_sup_alpha').first()
    if tech:
        tech.operations_manager_id = om.id
        tech.reporting_manager_id = sup.id if sup else om.id
    if reporter:
        reporter.reporting_manager_id = om.id

    for u in (om, bd, proc, gm, hr, qhsi, files_user, reporter, tech, sup):
        if not u:
            continue
        _goc(DocHubAccess, {'can_access': True, 'updated_by': admin.id}, user_id=u.id)

    db.session.flush()
    return {
        'admin': admin, 'om': om, 'bd': bd, 'proc': proc, 'gm': gm,
        'hr': hr, 'qhsi': qhsi, 'files': files_user, 'reporter': reporter,
        'tech': tech, 'sup': sup,
    }


def seed_admin_and_bd(people):
    from app.models import (
        db, Device, BDProject, BDFollowUp, BDContact, BDActivity,
        AdminPersonalProject, AdminPersonalProgressStep, KnowledgeBaseEntry,
        NotificationConfig, MmrChargeableConfig, DatabaseBackup,
    )
    from module_mmr.mmr_service import DEFAULT_MMR_CHARGEABLE_CONFIG

    admin = people['admin']
    for i, spec in enumerate((
        ('DEV-S001', 'Facilities Laptop — Ahmed', 'Laptop', 'macOS', 'online', 96),
        ('DEV-S002', 'Site Tablet — Tower A', 'Tablet', 'iPadOS', 'idle', 81),
        ('DEV-S003', 'Ops Desktop', 'Desktop', 'Windows 11', 'offline', 70),
    ), start=1):
        did, name, dtype, os_name, status, health = spec
        _goc(
            Device,
            {
                'name': name, 'device_type': dtype, 'os': os_name, 'status': status,
                'health': health, 'assigned_user_id': admin.id,
                'serial_or_asset_tag': f'SN-SAMPLE-{i:03d}',
                'last_active_at': _days(-i),
            },
            device_id=did,
        )

    from app.bd.sample_data import ensure_bd_sample_pipeline
    ensure_bd_sample_pipeline(people['bd'].id)
    if BDActivity.query.filter(BDActivity.title.like(f'{SEED_TAG}%')).count() == 0:
        db.session.add(BDActivity(
            icon='🤝', title=f'{SEED_TAG} Kick-off meeting held',
            description='Agreed draft SLA and chargeable policy.',
            badge='Marina Towers', event_time=_days(-4),
            created_by=people['bd'].id,
        ))

    proj, created = _goc(
        AdminPersonalProject,
        {
            'summary': 'Local demo of personal progress tracking.',
            'status': 'active', 'priority': 'high', 'category': 'Product',
            'start_date': date.today() - timedelta(days=10),
            'target_date': date.today() + timedelta(days=20),
            'tags': ['demo', 'sample'], 'is_current_focus': True, 'sort_order': 1,
            'notes': SEED_TAG,
        },
        user_id=admin.id, title=f'{SEED_TAG} Local demo readiness',
    )
    if created or AdminPersonalProgressStep.query.filter_by(project_id=proj.id).count() == 0:
        for i, (title, status) in enumerate((
            ('Confirm seed data', 'done'),
            ('Walk every module', 'in_progress'),
            ('Share with team', 'pending'),
        ), start=1):
            db.session.add(AdminPersonalProgressStep(
                project_id=proj.id, title=title, status=status,
                sort_order=i, due_date=date.today() + timedelta(days=i),
                completed_at=_utcnow() if status == 'done' else None,
            ))

    _goc(
        KnowledgeBaseEntry,
        {
            'content': 'Sample knowledge used by Ask Kynvera on local. HVAC filters are replaced quarterly on Marina Tower A AHUs.',
            'keywords': 'hvac, filter, marina, sample',
            'category': 'Operations', 'source_type': 'text', 'is_active': True,
            'created_by': admin.id, 'answer_link': '/tickets/',
        },
        title=f'{SEED_TAG} HVAC filter change SOP',
    )

    if NotificationConfig.query.count() == 0:
        db.session.add(NotificationConfig(config_json={
            'inspection': {
                'to': [people['om'].email], 'cc': [people['gm'].email],
                'include_submitter': True,
            },
            'hr': {
                'to': [people['hr'].email], 'cc': [people['gm'].email],
                'include_submitter': True,
            },
        }))
    if MmrChargeableConfig.query.count() == 0:
        db.session.add(MmrChargeableConfig(config_json=dict(DEFAULT_MMR_CHARGEABLE_CONFIG)))

    _goc(
        DatabaseBackup,
        {
            'created_by_user_id': admin.id, 'environment': 'local', 'engine': 'sqlite',
            'size_bytes': 2_400_000, 'status': 'ok', 'kind': 'download',
        },
        filename='injaaz-sample-backup.sqlite',
    )


def seed_email_and_notifications(people):
    from app.models import (
        db, EmailLog, EmailRecipientGroup, EmailAutomation, EmailAutomationAttachment,
        Notification, Session, AuditLog, PushDeviceToken,
        IntegrationApiKey, OutboundWebhook, AssistantPendingAction,
    )

    admin = people['admin']
    if EmailLog.query.filter(EmailLog.subject.like(f'{SEED_TAG}%')).count() == 0:
        db.session.add(EmailLog(
            status='sent', source='ticket', subject=f'{SEED_TAG} Ticket assigned TKT-SAMPLE01',
            to_emails=people['tech'].email if people['tech'] else 'tech@demo.injaaz.local',
            sent_by_user_id=admin.id, related_id='TKT-SAMPLE01',
            body_preview='You have been assigned a work order at Marina Towers.',
            attachment_count=0,
        ))
        db.session.add(EmailLog(
            status='failed', source='mmr', subject=f'{SEED_TAG} MMR daily report',
            to_emails='ops@demo.injaaz.local', sent_by_user_id=admin.id,
            body_preview='Would send the chargeable workbook.',
            error_message='No mail credentials configured (sample).',
        ))

    grp, _ = _goc(
        EmailRecipientGroup,
        {
            'emails': f"{people['om'].email}, {people['gm'].email}",
            'scope': 'public', 'owner_id': people['bd'].id,
        },
        name=f'{SEED_TAG} Ops + GM',
    )
    auto, created = _goc(
        EmailAutomation,
        {
            'scope': 'personal', 'owner_id': people['bd'].id,
            'to_emails': people['om'].email, 'cc_emails': people['gm'].email,
            'subject': f'{SEED_TAG} Weekly BD digest',
            'body': '<p>Sample automation — does not send until you enable mail.</p>',
            'enabled': False, 'schedule_enabled': False, 'schedule_hour': 9,
        },
        name=f'{SEED_TAG} Weekly BD digest',
    )
    if created:
        db.session.add(EmailAutomationAttachment(
            automation_id=auto.id, kind='folder_latest', sort_order=0,
        ))

    for user, title in (
        (people['tech'], 'Ticket assigned'),
        (people['hr'], 'Leave request pending'),
        (people['om'], 'Inspection awaiting review'),
    ):
        if not user:
            continue
        if Notification.query.filter_by(user_id=user.id, title=f'{SEED_TAG} {title}').first():
            continue
        db.session.add(Notification(
            user_id=user.id, title=f'{SEED_TAG} {title}',
            message=f'{SEED_TAG} Local demo notification.',
            notification_type='info', is_read=False,
        ))

    _goc(
        Session,
        {
            'expires_at': _days(-1), 'is_revoked': True, 'created_at': _days(-2),
        },
        token_jti='sample-revoked-jti-0001', user_id=admin.id,
    )
    if AuditLog.query.filter_by(action='sample_seed').count() == 0:
        db.session.add(AuditLog(
            user_id=admin.id, action='sample_seed', resource_type='database',
            resource_id='local', ip_address='127.0.0.1',
            details={'tag': SEED_TAG},
        ))

    _goc(
        PushDeviceToken,
        {'platform': 'web'},
        token='sample-web-push-token-local-only',
        user_id=admin.id,
    )
    demo_key = 'inj_sample_local_demo_key_do_not_use'
    _goc(
        IntegrationApiKey,
        {
            'key_hash': hashlib.sha256(demo_key.encode()).hexdigest(),
            'is_active': True, 'created_by': admin.id,
        },
        name=f'{SEED_TAG} Local demo key',
        key_prefix=demo_key[:12],
    )
    _goc(
        OutboundWebhook,
        {
            'target_url': 'http://127.0.0.1:9/sample-webhook',
            'secret': 'sample-secret',
            'events': ['ticket.created', 'ticket.closed'],
            'is_active': False,
        },
        name=f'{SEED_TAG} Local webhook (disabled)',
    )
    _goc(
        AssistantPendingAction,
        {
            'payload': {
                'summary': {'title': 'AC not cooling — Apt 1501', 'project': 'Marina Towers'},
            },
            'status': 'pending', 'expires_at': _days(1),
        },
        user_id=admin.id, action_type='create_ticket',
    )


def seed_ticketing_rows(people):
    from app.models import (
        db, Ticket, TicketProject, TicketProperty, TicketZone, TicketSubZone,
        TicketBaseUnit, TicketNote, TicketImage, TicketMaterial, TicketManpower,
        TicketAsset, TicketEmailIntake, TicketTriageLog, Asset, Technician,
        TicketProjectSupervisor, TicketProjectTeamMember, TicketVendor,
        TicketProjectVendor, PortfolioForecast,
    )

    project = TicketProject.query.filter_by(name='Marina Towers').first() or TicketProject.query.first()
    prop = TicketProperty.query.filter_by(project_id=project.id).first() if project else TicketProperty.query.first()
    zone = TicketZone.query.filter_by(property_id=prop.id).first() if prop else None
    sub = TicketSubZone.query.filter_by(zone_id=zone.id).first() if zone else None
    unit = TicketBaseUnit.query.filter_by(sub_zone_id=sub.id).first() if sub else None
    asset = Asset.query.filter_by(asset_id='AST-0001').first() or Asset.query.first()
    reporter = people['reporter'] or people['admin']
    sup = people['sup'] or people['admin']
    tech = people['tech'] or people['admin']

    if project and people['sup']:
        _goc(TicketProjectSupervisor, project_id=project.id, user_id=people['sup'].id)
        project.supervisor_id = people['sup'].id
        project.finance_emails = 'finance.marina@example.local'
        project.ops_emails = people['om'].email
        project.bd_project_id = project.bd_project_id
    if project and people['tech']:
        _goc(TicketProjectTeamMember, project_id=project.id, user_id=people['tech'].id)
    vendor = TicketVendor.query.first()
    if project and vendor:
        _goc(TicketProjectVendor, project_id=project.id, vendor_id=vendor.id)

    loc = {
        'project': project.name if project else 'Marina Towers',
        'property_name': prop.name if prop else 'Tower A',
        'zone': zone.name if zone else 'Podium',
        'sub_zone': sub.name if sub else 'Ground Floor',
        'base_unit': unit.name if unit else 'Lobby',
        'property_id': prop.id if prop else None,
        'zone_id': zone.id if zone else None,
        'sub_zone_id': sub.id if sub else None,
        'base_unit_id': unit.id if unit else None,
    }

    lifecycle = [
        ('TKT-SAMPLE01', 'open', 'AC not cooling — sample open', False),
        ('TKT-SAMPLE02', 'assigned', 'Lighting circuit trip — assigned', False),
        ('TKT-SAMPLE03', 'site_attended', 'Water leak under sink — on site', False),
        ('TKT-SAMPLE04', 'work_started', 'AHU filter replacement — in progress', False),
        ('TKT-SAMPLE05', 'work_completed', 'Door closer replacement — awaiting verify', True),
        ('TKT-SAMPLE06', 'verification', 'Gym AC drain flush — supervisor check', True),
        ('TKT-SAMPLE07', 'provider_closed', 'Corridor lamp — provider closed', True),
        ('TKT-SAMPLE08', 'on_hold', 'Chiller vibration — waiting parts', False),
        ('TKT-SAMPLE09', 'cancelled', 'Duplicate complaint — cancelled', False),
        ('TKT-SAMPLE10', 'closed', 'Lobby deep clean — closed', True),
        ('TKT-SAMPLE11', 'open', 'Email intake draft — from client', False),
    ]

    uploads = ROOT / 'generated' / 'uploads' / 'sample'
    uploads.mkdir(parents=True, exist_ok=True)
    img_path = uploads / 'ticket-sample.png'
    if not img_path.exists():
        img_path.write_bytes(TINY_PNG)

    tickets = {}
    for code, status, title, chargeable in lifecycle:
        ticket, created = _goc(
            Ticket,
            {
                'reporter_id': reporter.id,
                'assigned_to_id': tech.id if status not in ('open', 'cancelled') else None,
                'supervisor_id': sup.id,
                'technician_id': tech.id if status not in ('open', 'cancelled') else None,
                'service_group': 'HVAC',
                'category': 'Air Conditioning',
                'fault_type': 'No Cooling',
                'priority': 'high' if 'chiller' in title.lower() else 'medium',
                'title': f'{SEED_TAG} {title}',
                'work_description': f'{SEED_TAG} Demo work order so every ticket status is visible.\n\nInspect, repair, and record materials.',
                **loc,
                'is_chargeable': chargeable,
                'projected_cost': 450.0 if chargeable else 0,
                'total_cost': 380.0 if status in ('closed', 'provider_closed') else None,
                'markup_pct': 10 if chargeable else None,
                'status': status,
                'on_hold_reason': 'Waiting for Materials' if status == 'on_hold' else None,
                'cancelled_reason': 'Duplicate ticket' if status == 'cancelled' else None,
                'site_attended_at': _days(-2).isoformat() if status not in ('open', 'cancelled') else None,
                'work_started_at': _days(-1).isoformat() if status in (
                    'work_started', 'work_completed', 'verification', 'provider_closed', 'closed',
                ) else None,
                'work_completed_at': _utcnow().isoformat() if status in (
                    'work_completed', 'verification', 'provider_closed', 'closed',
                ) else None,
                'asset_id': asset.id if asset else None,
                'sla_hours': 24,
                'source': 'email' if code == 'TKT-SAMPLE11' else 'manual',
                'source_sender_email': 'client@marina.example' if code == 'TKT-SAMPLE11' else None,
                'source_subject': 'AC not working in Apt 1501' if code == 'TKT-SAMPLE11' else None,
                'created_at': _days(-5),
            },
            ticket_id=code,
        )
        ticket.status = status
        tickets[code] = ticket
        if created:
            db.session.add(TicketNote(
                ticket_id=ticket.id, user_id=reporter.id,
                content=f'{SEED_TAG} Reported from site walk.', note_type='note',
            ))
            db.session.add(TicketNote(
                ticket_id=ticket.id, user_id=sup.id,
                content=f'Status set to {status}', note_type='status_change',
            ))
            db.session.add(TicketImage(
                ticket_id=ticket.id, filename='ticket-sample.png',
                file_path=str(img_path), caption=f'{SEED_TAG} Before photo',
                uploaded_by=reporter.id,
            ))
            db.session.add(TicketMaterial(
                ticket_id=ticket.id, material_name='HEPA Filter 24x24',
                quantity=2, unit='pcs', unit_price=85, total_price=170,
                from_procurement=True, notes=SEED_TAG,
            ))
            db.session.add(TicketManpower(
                ticket_id=ticket.id, worker_name=tech.full_name,
                worker_user_id=tech.id, hours=2.5, rate_per_hour=45,
                total_cost=112.5, work_date=date.today() - timedelta(days=1),
                notes=SEED_TAG,
            ))
            if asset:
                _goc(TicketAsset, ticket_id=ticket.id, asset_pk=asset.id, is_primary=True)

    intake_ticket = tickets.get('TKT-SAMPLE11')
    if intake_ticket and TicketEmailIntake.query.filter_by(ticket_id=intake_ticket.id).count() == 0:
        db.session.add(TicketEmailIntake(
            from_email='client@marina.example', from_name='Marina Concierge',
            to_email='tickets@injaaz.local', subject='AC not working in Apt 1501',
            raw_body=f'{SEED_TAG} Please send a technician.',
            message_id='<sample-msg-001@injaaz.local>', status='processed',
            ticket_id=intake_ticket.id,
        ))

    first = tickets.get('TKT-SAMPLE01')
    if first and TicketTriageLog.query.filter_by(ticket_code='TKT-SAMPLE01').count() == 0:
        db.session.add(TicketTriageLog(
            ticket_id=first.id, ticket_code='TKT-SAMPLE01',
            actor_user_id=people['admin'].id,
            prompt_inputs={'title': first.title},
            raw_response='{"priority":"high","sla_hours":8}',
            suggested={'priority': 'high', 'sla_hours': 8, 'reasoning': 'No cooling in occupied unit.'},
            accepted={'priority': 'medium', 'sla_hours': 24},
            decision='overridden',
        ))

    if Technician.query.filter(Technician.employee_id.like('EMP-SAMPLE-%')).count() == 0:
        db.session.add(Technician(
            employee_id='EMP-SAMPLE-HVAC-01', full_name='Yusuf Rahman',
            designation='HVAC Technician', department='HVAC',
            specialization='Chillers', phone='+971 50 222 3344',
            email='yusuf.sample@injaaz.local', salary=6500,
            joining_date=date(2023, 6, 1), status='active',
            notes=SEED_TAG, supervisor_user_id=sup.id if sup else None,
        ))

    if PortfolioForecast.query.count() == 0:
        db.session.add(PortfolioForecast(
            payload={
                'horizon_days': 90,
                'expected_failures': 4,
                'budget_aed': 85000,
                'spares': ['AHU belts', 'Filter packs'],
                'note': SEED_TAG,
            },
            method='sample', created_by=people['admin'].id,
        ))


def seed_submissions(people):
    from app.models import db, Submission, Job, File

    def add_sub(sid, module_type, site, form_data, status='completed', workflow='completed', visit=None):
        row, created = _goc(
            Submission,
            {
                'user_id': people['admin'].id,
                'module_type': module_type,
                'site_name': site,
                'visit_date': visit or date.today(),
                'status': status,
                'workflow_status': workflow,
                'supervisor_id': people['sup'].id if people['sup'] else people['admin'].id,
                'operations_manager_id': people['om'].id,
                'business_dev_id': people['bd'].id,
                'procurement_id': people['proc'].id,
                'general_manager_id': people['gm'].id,
                'form_data': form_data,
                'doc_number': sid,
            },
            submission_id=sid,
        )
        return row, created

    try:
        from scripts.auto_test_hr_forms import _sample_form_data
        hr_samples = _sample_form_data()
    except Exception:
        hr_samples = {
            'leave_application': {
                'employee_name': 'Ahmed Hassan', 'leave_type': 'annual',
                'total_days_requested': '5', 'form_type': 'leave_application',
            },
        }

    hr_types = [
        'leave_application', 'commencement', 'duty_resumption', 'passport_release',
        'grievance', 'visa_renewal', 'interview_assessment', 'staff_appraisal',
        'station_clearance', 'performance_evaluation', 'contract_renewal', 'asset_handover',
    ]
    for form in hr_types:
        fd = dict(hr_samples.get(form) or hr_samples.get('leave_application') or {})
        fd.setdefault('form_type', form)
        sid = f'HR-SAMPLE-{form.replace("_", "-").upper()[:18]}'
        add_sub(sid, f'hr_{form}', 'Head Office', fd, status='submitted', workflow='submitted')

    insp_fd = {
        'project_name': 'Marina Towers',
        'inspector_name': people['qhsi'].full_name,
        'summary': f'{SEED_TAG} Routine inspection.',
        'items': [{
            'area': 'AHU Room L3', 'description': 'Filter differential high.',
            'severity': 'observation', 'photos': [],
        }],
    }
    for module, sid in (
        ('hvac_mep', 'INSP-SAMPLE-HVAC'),
        ('civil', 'INSP-SAMPLE-CIVIL'),
        ('cleaning', 'INSP-SAMPLE-CLEAN'),
    ):
        sub, created = add_sub(sid, module, 'Marina Towers', insp_fd, status='completed', workflow='completed')
        if created:
            job = Job(
                job_id=f'JOB-{sid[-8:]}', submission_id=sub.id, status='completed',
                progress=100, result_data={'pdf': None, 'excel': None, 'sample': True},
                started_at=_days(-1), completed_at=_utcnow(),
            )
            db.session.add(job)
            db.session.flush()
            db.session.add(File(
                file_id=f'FILE-{sid[-8:]}', submission_id=sub.id,
                file_type='report_pdf', filename=f'{sid}.pdf',
                file_path='', is_cloud=False, file_size=12000, mime_type='application/pdf',
            ))

    add_sub(
        'QHSI-SAMPLE-INSP', 'qhsi_inspection', 'Marina Towers',
        {
            'project_name': 'Marina Towers', 'visit_date': date.today().isoformat(),
            'location': 'Tower A podium', 'department': 'QHSE',
            'inspector_name': people['qhsi'].full_name,
            'summary': f'{SEED_TAG} Housekeeping round.',
            'items': [{'area': 'Lobby', 'description': 'Wet floor sign missing', 'severity': 'observation', 'photos': []}],
        },
        status='submitted', workflow='operations_manager_review',
    )
    add_sub(
        'QHSI-SAMPLE-STAFF', 'qhsi_staff_compliance', 'Marina Towers',
        {'note': SEED_TAG, 'imported': True},
        status='submitted', workflow='submitted',
    )

    add_sub(
        'CAT-MAT-SAMPLE1', 'catalog_material', 'HEPA Filter 24x24',
        {'department': 'HVAC', 'material_name': 'HEPA Filter 24x24', 'brand': 'Camfil', 'uom': 'PCS', 'unit_price': 85},
    )
    add_sub(
        'CAT-MAT-SAMPLE2', 'catalog_material', 'LED Tube 18W',
        {'department': 'Electrical', 'material_name': 'LED Tube 18W', 'brand': 'Philips', 'uom': 'PCS', 'unit_price': 22},
    )
    add_sub(
        'PROC-MAT-SAMPLE1', 'procurement_material', 'HEPA Filter 24x24',
        {
            'material_name': 'HEPA Filter 24x24', 'property': 'Tower A', 'category': 'HVAC',
            'description': SEED_TAG, 'unit': 'pcs', 'quantity': 12, 'unit_price': 85,
            'total_price': 1020, 'supplier': 'Gulf Filters LLC',
        },
    )
    add_sub(
        'PROC-PROP-SAMPLE1', 'procurement_property', 'Tower A',
        {'property_name': 'Tower A', 'address': 'Dubai Marina', 'description': SEED_TAG},
        status='active', workflow='active',
    )


def seed_qhsi_and_hr_trackers(people):
    from app.models import (
        db, QhsiTraining, QhseComplianceImport, QhseStaffComplianceRow,
        HiringCandidate, HiringDocument, LeaveEmployee, LeaveLog, LeavePlan,
        ManpowerTrade, ManpowerProject, ManpowerVacancy, recompute_monthly_usage,
        LEAVE_TRACKER_YEAR, HIRING_PHASE1_DOC_TYPES,
    )

    _goc(
        QhsiTraining,
        {
            'project_name': 'Marina Towers',
            'title': f'{SEED_TAG} Toolbox talk — working at height',
            'training_type': 'toolbox', 'scheduled_at': _days(3),
            'duration_minutes': 45, 'location': 'Tower A podium',
            'facilitator_name': people['qhsi'].full_name,
            'facilitator_id': people['qhsi'].id,
            'attendees': [
                {'name': people['tech'].full_name if people['tech'] else 'Tech', 'role': 'technician'},
            ],
            'status': 'scheduled', 'notes': SEED_TAG,
            'created_by_id': people['qhsi'].id,
        },
        training_id='QHSI-TRN-SAMPLE01',
    )

    batch, created = _goc(
        QhseComplianceImport,
        {
            'filename': 'sample-staff-compliance.xlsx', 'row_count': 4,
            'employee_count': 2, 'stats_json': {'ok': 3, 'issue': 1, 'missing': 0},
            'imported_by_id': people['qhsi'].id,
        },
        import_id='QHSI-IMP-SAMPLE01',
    )
    if created or QhseStaffComplianceRow.query.filter_by(import_batch_id=batch.id).count() == 0:
        for emp, item, cond in (
            ('Ahmed Hassan', 'Safety shoes', 'ok'),
            ('Ahmed Hassan', 'Helmet', 'ok'),
            ('Yusuf Rahman', 'Safety shoes', 'ok'),
            ('Yusuf Rahman', 'Hi-vis vest', 'issue'),
        ):
            db.session.add(QhseStaffComplianceRow(
                import_batch_id=batch.id, employee_name=emp, employee_id='INJ-0042',
                project_name='Marina Towers', record_date=date.today().isoformat(),
                department='Operations', supervisor_name=people['sup'].full_name if people['sup'] else '',
                notes=SEED_TAG, item_type='ppe', item_label=item, condition=cond,
            ))

    cand, created = _goc(
        HiringCandidate,
        {
            'full_name': 'Noura Al Mansoori', 'role': 'HVAC Technician',
            'department': 'Operations', 'phone': '+971 50 555 0101',
            'email': 'noura.sample@example.local',
            'pipeline_status': 'gathering_documents',
            'comments': SEED_TAG, 'created_by': people['hr'].id,
        },
        hr_ref='HR-CAND-SAMPLE-01',
    )
    if created:
        for dt in HIRING_PHASE1_DOC_TYPES[:3]:
            db.session.add(HiringDocument(
                candidate_id=cand.id, doc_type=dt, status='uploaded',
                filename=f'{dt}-sample.pdf', mime_type='application/pdf',
                file_size=8400, uploaded_at=_utcnow(), uploaded_by=people['hr'].id,
                notes=SEED_TAG,
            ))

    emp, created = _goc(
        LeaveEmployee,
        {
            'full_name': 'Ahmed Hassan', 'designation': 'Facility Supervisor',
            'company': 'Kynvera', 'annual_entitlement': 30, 'active': True,
        },
        emp_id='INJ-0042',
    )
    emp2, _ = _goc(
        LeaveEmployee,
        {
            'full_name': 'Yusuf Rahman', 'designation': 'HVAC Technician',
            'company': 'Kynvera', 'annual_entitlement': 30, 'active': True,
        },
        emp_id='INJ-0077',
    )
    if LeaveLog.query.filter_by(employee_id=emp.id).count() == 0:
        log = LeaveLog(
            employee_id=emp.id, leave_type='annual',
            leave_date=date(LEAVE_TRACKER_YEAR, 8, 10),
            end_date=date(LEAVE_TRACKER_YEAR, 8, 14),
            days=5, notes=SEED_TAG, created_by=people['hr'].id,
        )
        db.session.add(log)
        db.session.add(LeaveLog(
            employee_id=emp2.id, leave_type='sick',
            leave_date=date(LEAVE_TRACKER_YEAR, 8, 3),
            days=1, notes=SEED_TAG, created_by=people['hr'].id,
        ))
        db.session.flush()
        recompute_monthly_usage(emp.id, 'annual', LEAVE_TRACKER_YEAR, 8)
        recompute_monthly_usage(emp2.id, 'sick', LEAVE_TRACKER_YEAR, 8)
    if LeavePlan.query.filter_by(employee_id=emp.id).count() == 0:
        db.session.add(LeavePlan(
            employee_id=emp.id,
            start_date=date(LEAVE_TRACKER_YEAR, 12, 20),
            end_date=date(LEAVE_TRACKER_YEAR, 12, 31),
            days=12, notes=f'{SEED_TAG} Year-end leave', created_by=people['hr'].id,
        ))

    hvac_trade, _ = _goc(ManpowerTrade, {'sort_order': 1, 'active': True}, name='HVAC Technician')
    elec_trade, _ = _goc(ManpowerTrade, {'sort_order': 2, 'active': True}, name='Electrician')
    mp_proj, _ = _goc(ManpowerProject, {'sort_order': 1, 'active': True}, name='Marina Towers')
    if ManpowerVacancy.query.filter_by(trade_id=hvac_trade.id, project_id=mp_proj.id).count() == 0:
        db.session.add(ManpowerVacancy(
            trade_id=hvac_trade.id, project_id=mp_proj.id,
            requirement_type='new', status='interviewing',
            candidate_name='Noura Al Mansoori', contact_number='+971 50 555 0101',
            remarks=SEED_TAG, hiring_candidate_id=cand.id, created_by=people['hr'].id,
        ))
        db.session.add(ManpowerVacancy(
            trade_id=elec_trade.id, project_id=mp_proj.id,
            requirement_type='replacement', replacement_name='Omar Khalid',
            status='open', remarks=SEED_TAG, created_by=people['hr'].id,
        ))


def seed_files_module(people):
    from app.models import db, FilesFolder, FilesItem, FilesDriveConnection
    from module_files.service import ensure_default_folders, _files_root

    folders = ensure_default_folders(created_by=people['admin'].id)
    leave_folder = folders.get('hr/leave') or FilesFolder.query.filter_by(path_key='hr/leave').first()
    if leave_folder and FilesItem.query.filter_by(folder_id=leave_folder.id, filename='leave-sample-note.txt').count() == 0:
        root = Path(_files_root())
        dest = root / 'sample' / 'leave-sample-note.txt'
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(f'{SEED_TAG} Local files demo.\n', encoding='utf-8')
        db.session.add(FilesItem(
            folder_id=leave_folder.id,
            name='Leave tracker sample note',
            filename='leave-sample-note.txt',
            mime_type='text/plain',
            size_bytes=dest.stat().st_size,
            stored_path=str(dest),
            source_module='leave', source_kind='upload',
            sync_status='local', created_by=people['files'].id,
        ))
    if FilesDriveConnection.query.count() == 0:
        db.session.add(FilesDriveConnection(
            connected_email=None, refresh_token_enc=None,
            connected_by=people['admin'].id,
        ))


def print_counts():
    from app.models import db
    print('\n=== Model row counts ===')
    rows = []
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        table = getattr(cls, '__tablename__', None)
        if not table:
            continue
        try:
            n = cls.query.count()
        except Exception as exc:
            n = f'error: {exc}'
        rows.append((table, n))
    for table, n in sorted(rows, key=lambda r: r[0]):
        flag = 'EMPTY' if n == 0 else str(n)
        print(f'  {table:40} {flag}')
    empty = [t for t, n in rows if n == 0]
    if empty:
        print('\nStill empty:', ', '.join(empty))
    else:
        print('\nAll models have at least one row.')
    print(f'\nDemo password for seeded users: {DEMO_PASSWORD}')
    print('Users: demo_ops_mgr, demo_bd, demo_procurement, demo_gm, demo_hr,')
    print('       demo_qhsi, demo_files, demo_reporter, demo_sup_alpha, demo_tech_alpha_1')


def seed_all_sample_data() -> dict:
    from app.models import db
    seed_reference_catalogs()
    people = seed_people()
    seed_admin_and_bd(people)
    seed_email_and_notifications(people)
    seed_ticketing_rows(people)
    seed_submissions(people)
    seed_qhsi_and_hr_trackers(people)
    seed_files_module(people)
    db.session.commit()
    return {'ok': True, 'password': DEMO_PASSWORD}


def main():
    from Injaaz import create_app
    from app.models import db

    app = create_app()
    with app.app_context():
        _assert_local_db(app)
        db.create_all()
        print('Seeding sample data into every model…')
        seed_all_sample_data()
        print_counts()


if __name__ == '__main__':
    main()
