"""Idempotent sample pipeline for the Business Development module.

Fills deals, contacts, follow-ups, activity, quotations, and won-deal
ticketing links so the dashboard is usable locally. Existing rows with the
same deal name / contact email / follow-up title are left in place.
"""
from __future__ import annotations

from datetime import date, timedelta
import uuid

from common.datetime_utils import utc_now_naive
from app.models import (
    db, User, BDProject, BDFollowUp, BDContact, BDActivity,
    Quotation, QuotationItem, TicketProject,
    QUOTATION_DEFAULT_INTRO, QUOTATION_DEFAULT_NOTES,
    QUOTATION_DEFAULT_EXCLUSIONS, QUOTATION_DEFAULT_TERMS,
    QUOTATION_DEFAULT_SIGNATORY_NAME, QUOTATION_DEFAULT_SIGNOFF_LABEL,
)


def _today():
    return date.today()


def _now():
    return utc_now_naive()


def _days(n, hour=9):
    base = _now().replace(hour=int(hour), minute=0, second=0, microsecond=0)
    return base + timedelta(days=n)


DEALS = (
    # prospecting
    dict(name='Marina Gate FM Retainer', company='Marina Gate Properties',
         stage='prospecting', status='prospect', priority='med', value=185000,
         progress=12, next_action='Discovery call', close_in=45, idle=4,
         contact=('Hassan Alvi', 'hassan@marinagate.example')),
    dict(name='Al Zahra Tower Soft Services', company='Al Zahra Holdings',
         stage='prospecting', status='prospect', priority='low', value=96000,
         progress=8, next_action='Send capability deck', close_in=60, idle=6,
         contact=('Maha Al Suwaidi', 'maha@alzahra.example')),
    dict(name='Corniche Clinics Facility Care', company='Corniche Medical Group',
         stage='prospecting', status='prospect', priority='med', value=240000,
         progress=18, next_action='Site walkthrough', close_in=40, idle=3,
         contact=('Dr. Tariq Nasser', 'tariq@corniche.example')),
    # qualifying
    dict(name='Bay Square MEP Annual', company='Bay Square LLC',
         stage='qualifying', status='active', priority='high', value=410000,
         progress=38, next_action='Budget confirmation', close_in=21, idle=32,
         contact=('Yousef Karim', 'yousef@baysquare.example')),
    dict(name='Horizon Mall Cleaning Scope', company='Horizon Retail',
         stage='qualifying', status='active', priority='med', value=175000,
         progress=30, next_action='Scope clarification', close_in=35, idle=33,
         contact=('Rania Haddad', 'rania@horizonmall.example')),
    dict(name='Saqr Community Soft Services', company='Saqr Real Estate',
         stage='qualifying', status='proposal', priority='med', value=480000,
         progress=35, next_action='Site walkthrough', close_in=45, idle=8,
         contact=('Saqr Al Nuaimi', 'saqr@saqrre.example')),
    # proposal
    dict(name='Nexus Corp Platform Deal', company='Nexus Corp',
         stage='proposal', status='active', priority='high', value=480000,
         progress=72, next_action='Contract review', close_in=3, idle=2,
         contact=('Marcus Johnson', 'marcus@nexus.example')),
    dict(name='Emirates Heights HVAC Upgrade', company='Emirates Heights',
         stage='proposal', status='active', priority='high', value=620000,
         progress=65, next_action='Present commercial offer', close_in=5, idle=1,
         contact=('Layla Rahman', 'layla@emiratesheights.example')),
    dict(name='City Walk Pest Control Bundle', company='City Walk Ops',
         stage='proposal', status='proposal', priority='med', value=88000,
         progress=55, next_action='Await legal markup', close_in=12, idle=9,
         contact=('Faisal Noor', 'faisal@citywalk.example')),
    # negotiation
    dict(name='Ajman Port Logistics Facility', company='Ajman Port Authority',
         stage='negotiation', status='active', priority='high', value=890000,
         progress=78, next_action='Final pricing round', close_in=7, idle=5,
         contact=('Omar Faris', 'omar@ajmanport.example')),
    dict(name='Palm Residences Concierge FM', company='Palm Residences',
         stage='negotiation', status='active', priority='high', value=540000,
         progress=82, next_action='SLA negotiation', close_in=-5, idle=35,
         contact=('Nadia Chen', 'nadia@palm.example')),
    dict(name='TechPark Campus Soft Services', company='TechPark Developments',
         stage='negotiation', status='active', priority='med', value=360000,
         progress=70, next_action='Stakeholder alignment', close_in=10, idle=40,
         contact=('Kevin Osei', 'kevin@techpark.example')),
    dict(name='Marina Towers FM Renewal', company='Al Futtaim Group',
         stage='negotiation', status='active', priority='high', value=1250000,
         progress=62, next_action='Send revised SLA', close_in=21, idle=7,
         contact=('Layla Hassan', 'layla.hassan@alfuttaim.example')),
    # closing
    dict(name='Royal Hospital Environmental Services', company='Royal Hospital Group',
         stage='closing', status='active', priority='high', value=750000,
         progress=92, next_action='Signature chase', close_in=2, idle=1,
         contact=('Priya Menon', 'priya@royalhospital.example')),
    dict(name='Skyline Tower Fit-out Support', company='Skyline Developments',
         stage='closing', status='active', priority='med', value=215000,
         progress=88, next_action='Kickoff scheduling', close_in=4, idle=2,
         contact=('Samir Qureshi', 'samir@skyline.example')),
    # won
    dict(name='Museum District Annual FM', company='Museum District Trust',
         stage='closing', status='won', priority='high', value=680000,
         progress=100, next_action='Handover to delivery', close_in=-40, idle=40,
         contact=('Amira Saleh', 'amira@museumdistrict.example'), won=True),
    dict(name='Harbour View Soft Services', company='Harbour View RE',
         stage='closing', status='won', priority='med', value=295000,
         progress=100, next_action='Closed — won', close_in=-70, idle=70,
         contact=('Daniel Cruz', 'daniel@harbourview.example'), won=True),
    # lost / renewal
    dict(name='Desert Ridge Pilot Contract', company='Desert Ridge LLC',
         stage='proposal', status='lost', priority='med', value=150000,
         progress=100, next_action='Lost — price', close_in=-25, idle=25,
         contact=('Huda Mansoor', 'huda@desertridge.example')),
    dict(name='North Gate Security Bundle', company='North Gate Estates',
         stage='negotiation', status='lost', priority='low', value=110000,
         progress=100, next_action='Lost — incumbent', close_in=-55, idle=55,
         contact=('Peter Lang', 'peter@northgate.example')),
    dict(name='Excel Park Contract Renewal', company='Excel Park Municipality',
         stage='closing', status='under_renewal', priority='high', value=920000,
         progress=55, next_action='Renewal commercial pack', close_in=18, idle=6,
         contact=('Fatima Al Blooshi', 'fatima@excelpark.example'),
         renew_in=20),
)


CONTACTS = (
    dict(name='Marcus Johnson', title='VP of Technology', company='Nexus Corp',
         email='marcus@nexus.example', phone='+971 50 100 2001',
         tags=['Decision Maker', 'Champion']),
    dict(name='Layla Rahman', title='Facilities Director', company='Emirates Heights',
         email='layla@emiratesheights.example', phone='+971 50 100 2002',
         tags=['Decision Maker']),
    dict(name='Omar Faris', title='Procurement Lead', company='Ajman Port Authority',
         email='omar@ajmanport.example', phone='+971 50 100 2003',
         tags=['Procurement', 'Influencer']),
    dict(name='Nadia Chen', title='Operations Manager', company='Palm Residences',
         email='nadia@palm.example', phone='+971 50 100 2004',
         tags=['Champion']),
    dict(name='Hassan Alvi', title='Asset Manager', company='Marina Gate Properties',
         email='hassan@marinagate.example', phone='+971 50 100 2005',
         tags=['Prospect']),
    dict(name='Priya Menon', title='Head of Soft Services', company='Royal Hospital Group',
         email='priya@royalhospital.example', phone='+971 50 100 2006',
         tags=['Decision Maker']),
    dict(name='Layla Hassan', title='Facilities Director', company='Al Futtaim Group',
         email='layla.hassan@alfuttaim.example', phone='+971 4 123 4567',
         tags=['Decision Maker', 'Champion']),
    dict(name='Fatima Al Blooshi', title='Contracts Manager', company='Excel Park Municipality',
         email='fatima@excelpark.example', phone='+971 6 701 1100',
         tags=['Renewal', 'Decision Maker']),
)


def _followups_for(projects_by_name):
    def pid(name):
        p = projects_by_name.get(name)
        return p.id if p else None

    return (
        dict(title='Call with Marcus – Q4 proposal review', company='Nexus Corp',
             followup_type='call', due=_days(0, 15), status='open',
             details='Walk through commercial terms',
             project_id=pid('Nexus Corp Platform Deal')),
        dict(title='Send revised HVAC quote', company='Emirates Heights',
             followup_type='email', due=_days(0, 17), status='open',
             details='Include chiller option B',
             project_id=pid('Emirates Heights HVAC Upgrade')),
        dict(title='Overdue: Palm Residences SLA reply', company='Palm Residences',
             followup_type='email', due=_days(-2, 11), status='open',
             details='Waiting on client legal',
             project_id=pid('Palm Residences Concierge FM')),
        dict(title='Port Authority pricing workshop', company='Ajman Port Authority',
             followup_type='meeting', due=_days(1, 11), status='open',
             project_id=pid('Ajman Port Logistics Facility')),
        dict(title='Royal Hospital kickoff prep', company='Royal Hospital Group',
             followup_type='meeting', due=_days(2, 10), status='open',
             project_id=pid('Royal Hospital Environmental Services')),
        dict(title='Overdue: Bay Square budget confirm', company='Bay Square LLC',
             followup_type='call', due=_days(-1, 14), status='open',
             project_id=pid('Bay Square MEP Annual')),
        dict(title='Marina Gate discovery notes', company='Marina Gate Properties',
             followup_type='note', due=_days(3, 10), status='open',
             project_id=pid('Marina Gate FM Retainer')),
        dict(title='TechPark stakeholder sync', company='TechPark Developments',
             followup_type='meeting', due=_days(4, 10), status='open',
             project_id=pid('TechPark Campus Soft Services')),
        dict(title='Excel Park renewal commercial pack', company='Excel Park Municipality',
             followup_type='email', due=_days(1, 9), status='open',
             project_id=pid('Excel Park Contract Renewal')),
        dict(title='Call Layla — SLA markup', company='Al Futtaim Group',
             followup_type='call', due=_days(2, 10), status='open',
             project_id=pid('Marina Towers FM Renewal')),
    )


ACTIVITIES = (
    dict(icon='📞', bg='#e8f0fb', title='Call logged with Nexus Corp',
         description='Discussed Q4 proposal and close plan.', badge='Call', days=0),
    dict(icon='📧', bg='#fef6e4', title='Proposal sent — Emirates Heights',
         description='Commercial pack v2 emailed to Layla.', badge='Email', days=0),
    dict(icon='🤝', bg='#fff4ef', title='Site visit — Ajman Port',
         description='Walked warehouse zones with Omar.', badge='Meeting', days=-1),
    dict(icon='✅', bg='#fff4ef', title='Deal won — Museum District',
         description='Annual FM contract signed.', badge='Won', days=-3),
    dict(icon='⚠️', bg='#fdf0ee', title='Follow-up overdue — Palm Residences',
         description='SLA reply still pending.', badge='Alert', days=-2),
    dict(icon='📝', bg='#f3edfc', title='Note added — Marina Gate',
         description='Prospect interested in soft services bundle.', badge='Note', days=-4),
    dict(icon='🔄', bg='#e8f0fb', title='Stage moved — Bay Square',
         description='Qualifying → deeper discovery.', badge='Pipeline', days=-5),
    dict(icon='🏆', bg='#fff4ef', title='Deal won — Harbour View',
         description='Promoted to ticketing for delivery.', badge='Won', days=-8),
)


QUOTE_SPECS = (
    dict(deal='Nexus Corp Platform Deal', status='approved',
         items=(('Annual hard services retainer', 12, 28000),
                ('Helpdesk & CAFM licence', 1, 48000))),
    dict(deal='Emirates Heights HVAC Upgrade', status='draft',
         items=(('Chiller replacement — option B', 2, 145000),
                ('BMS integration', 1, 62000))),
    dict(deal='Royal Hospital Environmental Services', status='pending_approval',
         items=(('Environmental services — 12 months', 12, 48000),
                ('Medical waste coordination', 12, 12500))),
    dict(deal='Ajman Port Logistics Facility', status='approved',
         items=(('Warehouse FM package', 12, 52000),
                ('MHE preventive maintenance', 12, 18500))),
    dict(deal='Marina Towers FM Renewal', status='draft',
         items=(('Comprehensive FM — towers A–C', 12, 78000),
                ('SLA premium response', 12, 18000))),
    dict(deal='City Walk Pest Control Bundle', status='sent',
         items=(('Pest control annual programme', 12, 6200),)),
    dict(deal='Palm Residences Concierge FM', status='sent',
         items=(('Concierge FM retainer', 12, 38000),
                ('VIP response overlay', 12, 7000))),
)


def _owner_name(user_id):
    user = db.session.get(User, user_id) if user_id else None
    if user:
        return user.full_name or user.username
    return 'Business Development'


def _ensure_deal(spec, user_id, owner_name):
    existing = BDProject.query.filter_by(name=spec['name']).first()
    if existing:
        if existing.owner_user_id is None and user_id:
            existing.owner_user_id = user_id
        if not existing.owner:
            existing.owner = owner_name
        return existing, False
    close = _today() + timedelta(days=int(spec['close_in']))
    contact = spec.get('contact') or (None, None)
    proj = BDProject(
        name=spec['name'],
        company=spec['company'],
        stage=spec['stage'],
        status=spec['status'],
        priority=spec['priority'],
        value_amount=float(spec['value']),
        progress=int(spec['progress']),
        owner=owner_name,
        owner_user_id=user_id,
        next_action=spec['next_action'],
        expected_close_date=close,
        notes=spec.get('notes') or f"Sample pipeline deal for {spec['company']}.",
        primary_contact_name=contact[0],
        primary_contact_email=contact[1],
        created_by=user_id,
    )
    db.session.add(proj)
    db.session.flush()
    idle = int(spec.get('idle') or 0)
    if idle:
        db.session.query(BDProject).filter_by(id=proj.id).update(
            {'updated_at': _now() - timedelta(days=idle)},
            synchronize_session=False,
        )
    return proj, True


def _ensure_contact(spec, user_id):
    q = BDContact.query.filter_by(name=spec['name'])
    if spec.get('email'):
        existing = BDContact.query.filter_by(email=spec['email']).first() or q.first()
    else:
        existing = q.first()
    if existing:
        return existing
    row = BDContact(
        name=spec['name'],
        title=spec.get('title'),
        company=spec.get('company'),
        email=spec.get('email'),
        phone=spec.get('phone'),
        tags=list(spec.get('tags') or []),
        created_by=user_id,
    )
    db.session.add(row)
    return row


def _ensure_followup(spec, user_id):
    existing = BDFollowUp.query.filter_by(title=spec['title']).first()
    if existing:
        return existing
    row = BDFollowUp(
        title=spec['title'],
        company=spec.get('company'),
        followup_type=spec.get('followup_type') or 'note',
        due_at=spec.get('due'),
        status=spec.get('status') or 'open',
        details=spec.get('details'),
        project_id=spec.get('project_id'),
        created_by=user_id,
    )
    db.session.add(row)
    return row


def _ensure_activity(spec, user_id):
    existing = BDActivity.query.filter_by(title=spec['title']).first()
    if existing:
        return existing
    row = BDActivity(
        icon=spec.get('icon') or '📝',
        bg=spec.get('bg') or '#fff4ef',
        title=spec['title'],
        description=spec.get('description'),
        badge=spec.get('badge'),
        event_time=_now() + timedelta(days=int(spec.get('days') or 0)),
        created_by=user_id,
    )
    db.session.add(row)
    return row


def _ensure_quote(spec, proj, user_id):
    if not proj:
        return None
    existing = Quotation.query.filter_by(bd_project_id=proj.id).first()
    if existing:
        return existing
    quote_no = f'QT-{uuid.uuid4().hex[:8].upper()}'
    yy = _today().strftime('%y')
    yyyy = _today().strftime('%Y')
    token = quote_no.replace('QT-', '')[:6]
    quote = Quotation(
        quote_no=quote_no,
        ref_no=f'KYQ/{yy}RR{token}Rev1/{yyyy}',
        bd_project_id=proj.id,
        company_name=proj.company,
        contact_name=proj.primary_contact_name,
        contact_email=proj.primary_contact_email,
        kind_attn=proj.primary_contact_name,
        subject=f'Price for {proj.name}',
        project_name=proj.name,
        intro_text=QUOTATION_DEFAULT_INTRO,
        notes_text=QUOTATION_DEFAULT_NOTES,
        exclusions_text=QUOTATION_DEFAULT_EXCLUSIONS,
        terms_text=QUOTATION_DEFAULT_TERMS,
        signatory_name=QUOTATION_DEFAULT_SIGNATORY_NAME,
        signoff_label=QUOTATION_DEFAULT_SIGNOFF_LABEL,
        quote_date=_today(),
        valid_until=_today() + timedelta(days=10),
        status=spec.get('status') or 'draft',
        tax_pct=5.0,
        owner_user_id=user_id,
        created_by_id=user_id,
    )
    subtotal = 0.0
    for desc, qty, price in spec.get('items') or ():
        total = round(float(qty) * float(price), 2)
        subtotal += total
        quote.items.append(QuotationItem(
            description=desc, quantity=float(qty), unit='month' if qty >= 12 else 'ls',
            unit_price=float(price), total_price=total,
        ))
    quote.subtotal = round(subtotal, 2)
    quote.grand_total = quote.subtotal
    quote.tax_amount = round(quote.subtotal * 0.05, 2)
    if quote.status in ('approved', 'pending_approval'):
        quote.submitted_at = _now() - timedelta(days=2)
    if quote.status == 'approved':
        quote.approved_at = _now() - timedelta(days=1)
        quote.approved_by_id = user_id
    db.session.add(quote)
    return quote


def _ensure_ticket_link(proj, renew_in=None):
    if not proj:
        return None
    existing = TicketProject.query.filter_by(bd_project_id=proj.id).first()
    if existing:
        if renew_in is not None and not existing.renewal_date:
            existing.renewal_date = _today() + timedelta(days=int(renew_in))
        return existing
    tp = TicketProject(
        name=proj.name[:160],
        client_name=proj.company,
        description=proj.notes,
        bd_project_id=proj.id,
        project_value=proj.value_amount,
        is_active=True,
        renewal_date=(_today() + timedelta(days=int(renew_in))) if renew_in is not None else None,
        project_end_date=(_today() + timedelta(days=int(renew_in) + 30)) if renew_in is not None else None,
    )
    db.session.add(tp)
    return tp


def ensure_bd_sample_pipeline(user_id=None):
    """Create a full sample pipeline if rows are missing. Safe to call on every dashboard load."""
    if user_id is None:
        admin = User.query.filter_by(role='admin').first()
        user_id = admin.id if admin else None
    owner_name = _owner_name(user_id)

    projects_by_name = {}
    created_deals = 0
    for spec in DEALS:
        proj, created = _ensure_deal(spec, user_id, owner_name)
        projects_by_name[spec['name']] = proj
        if created:
            created_deals += 1
        if spec.get('won') or spec.get('renew_in') is not None:
            _ensure_ticket_link(proj, renew_in=spec.get('renew_in'))

    for spec in CONTACTS:
        _ensure_contact(spec, user_id)

    for spec in _followups_for(projects_by_name):
        _ensure_followup(spec, user_id)

    for spec in ACTIVITIES:
        _ensure_activity(spec, user_id)

    for spec in QUOTE_SPECS:
        _ensure_quote(spec, projects_by_name.get(spec['deal']), user_id)

    db.session.commit()
    return {'deals': len(projects_by_name), 'created': created_deals}
