"""Hourly SLA breach scan for service tickets."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_TERMINAL = frozenset({'closed', 'cancelled', 'resolved'})


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _already_sent(db, ReminderDispatchLog, entity_type: str, entity_id: int, milestone: str) -> bool:
    return db.session.query(ReminderDispatchLog.id).filter_by(
        entity_type=entity_type, entity_id=entity_id, milestone=milestone,
    ).first() is not None


def _mark_sent(db, ReminderDispatchLog, entity_type: str, entity_id: int, milestone: str, recipients: str):
    db.session.add(ReminderDispatchLog(
        entity_type=entity_type,
        entity_id=entity_id,
        milestone=milestone,
        recipients=recipients,
        sent_at=_utcnow(),
    ))


def _ops_escalation_emails(User):
    """Collect ops manager / GM / admin emails; optional finance settings override."""
    emails = set()
    try:
        from module_finance.routes import _get_finance_settings
        cfg = _get_finance_settings() or {}
        for key in ('sla_email_to', 'invoice_email_to'):
            raw = (cfg.get(key) or '').strip()
            for part in raw.split(','):
                e = part.strip()
                if e and '@' in e:
                    emails.add(e.lower())
    except Exception:
        pass

    for u in User.query.filter(User.is_active.is_(True)).all():
        des = (getattr(u, 'designation', None) or '').strip().lower()
        if u.role == 'admin' or des in ('operations_manager', 'general_manager'):
            if u.email:
                emails.add(u.email.strip().lower())
    return emails


def run_sla_breach_scan(app=None):
    """Find open tickets past sla_due_at; mark breached once and email ops + supervisor."""
    created = False
    if app is None:
        try:
            from kynver import create_app
            app = create_app()
            created = True
        except Exception:
            try:
                from Injaaz import create_app
                app = create_app()
                created = True
            except Exception:
                from Amaan import create_app
                app = create_app()
                created = True

    with app.app_context():
        from app.models import db, Ticket, User, ReminderDispatchLog, TicketProject
        from common.email_service import send_email, is_email_configured
        from common.sla import is_ticket_open_for_sla

        now = _utcnow()
        tickets = Ticket.query.filter(
            Ticket.sla_due_at.isnot(None),
            Ticket.sla_due_at < now,
            Ticket.sla_breached_at.is_(None),
            ~Ticket.status.in_(list(_TERMINAL)),
        ).all()

        if not tickets:
            logger.info('SLA scan: no breaches')
            return {'scanned': 0, 'breached': 0}

        ops_emails = _ops_escalation_emails(User)
        breached = 0
        for ticket in tickets:
            if not is_ticket_open_for_sla(ticket) and ticket.status in _TERMINAL:
                continue
            ticket.sla_breached_at = now
            if _already_sent(db, ReminderDispatchLog, 'ticket', ticket.id, 'sla_breach'):
                continue

            to_list = set(ops_emails)
            sup = ticket.supervisor or ticket.assigned_to
            if not sup and ticket.project:
                proj = TicketProject.query.filter_by(name=ticket.project).first()
                if proj and proj.supervisor_user:
                    sup = proj.supervisor_user
            if sup and getattr(sup, 'email', None):
                to_list.add(sup.email.strip().lower())

            if not to_list or not is_email_configured():
                _mark_sent(db, ReminderDispatchLog, 'ticket', ticket.id, 'sla_breach',
                           ','.join(sorted(to_list)) or '(no recipients)')
                breached += 1
                continue

            hours = ''
            try:
                from common.sla import sla_hours_for_priority
                hours = f'{sla_hours_for_priority(ticket.priority)}h'
            except Exception:
                pass

            subject = f'[SLA BREACH] {ticket.ticket_id} — {ticket.priority or "medium"} priority'
            body = (
                f'Service ticket {ticket.ticket_id} has breached its SLA.\n\n'
                f'Title: {ticket.title}\n'
                f'Project: {ticket.project}\n'
                f'Priority: {(ticket.priority or "").upper()} ({hours})\n'
                f'SLA due: {ticket.sla_due_at}\n'
                f'Status: {ticket.status}\n'
                f'Supervisor: {(sup.full_name if sup else "—")}\n'
            )
            html = f"""
            <div style="font-family:sans-serif;max-width:560px">
              <h2 style="color:#a81222;margin:0 0 12px">SLA Breach</h2>
              <p>Service ticket <strong>{ticket.ticket_id}</strong> has exceeded its priority SLA.</p>
              <table style="border-collapse:collapse;width:100%;font-size:14px">
                <tr><td style="padding:6px 0;font-weight:600">Title</td><td>{ticket.title}</td></tr>
                <tr><td style="padding:6px 0;font-weight:600">Project</td><td>{ticket.project}</td></tr>
                <tr><td style="padding:6px 0;font-weight:600">Priority</td><td>{(ticket.priority or '').upper()} ({hours})</td></tr>
                <tr><td style="padding:6px 0;font-weight:600">SLA due</td><td>{ticket.sla_due_at}</td></tr>
                <tr><td style="padding:6px 0;font-weight:600">Status</td><td>{ticket.status}</td></tr>
              </table>
            </div>
            """
            ok = send_email(list(to_list), subject, body, html_body=html)
            _mark_sent(
                db, ReminderDispatchLog, 'ticket', ticket.id, 'sla_breach',
                ','.join(sorted(to_list)) + ('' if ok else ' [send failed]'),
            )
            breached += 1

        db.session.commit()
        logger.info('SLA scan: marked %s breaches', breached)
        return {'scanned': len(tickets), 'breached': breached}
