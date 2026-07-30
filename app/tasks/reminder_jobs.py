"""Scheduled domain reminders: AMC renewal, payment follow-up, paid confirmation."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

logger = logging.getLogger(__name__)


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _already_sent(db, ReminderDispatchLog, entity_type, entity_id, milestone) -> bool:
    return db.session.query(ReminderDispatchLog.id).filter_by(
        entity_type=entity_type, entity_id=entity_id, milestone=milestone,
    ).first() is not None


def _mark_sent(db, ReminderDispatchLog, entity_type, entity_id, milestone, recipients: str):
    db.session.add(ReminderDispatchLog(
        entity_type=entity_type,
        entity_id=entity_id,
        milestone=milestone,
        recipients=recipients,
        sent_at=_utcnow(),
    ))


def _parse_emails(*blobs):
    out = set()
    for blob in blobs:
        if not blob:
            continue
        for part in str(blob).split(','):
            e = part.strip()
            if e and '@' in e:
                out.add(e.lower())
    return out


def _finance_cc():
    try:
        from module_finance.routes import _get_finance_settings
        cfg = _get_finance_settings() or {}
        return _parse_emails(cfg.get('invoice_email_cc'), cfg.get('invoice_email_to'), cfg.get('report_recipients'))
    except Exception:
        return set()


def run_amc_renewal_reminders(app=None):
    """45-day and 10-day reminders before FinanceContract.end_date / TicketProject.renewal_date."""
    if app is None:
        try:
            from kynver import create_app
            app = create_app()
        except Exception:
            try:
                from Injaaz import create_app
                app = create_app()
            except Exception:
                from Amaan import create_app
                app = create_app()

    with app.app_context():
        from app.models import db, FinanceContract, TicketProject, User, ReminderDispatchLog
        from common.email_service import send_email, is_email_configured

        today = date.today()
        sent = 0
        cc = _finance_cc()

        # Finance contracts
        contracts = FinanceContract.query.filter(
            FinanceContract.status == 'active',
            FinanceContract.end_date.isnot(None),
        ).all()
        for c in contracts:
            days_left = (c.end_date - today).days
            milestone = None
            if days_left == 45:
                milestone = 'amc_45d'
            elif days_left == 10:
                milestone = 'amc_10d'
            if not milestone:
                continue
            if _already_sent(db, ReminderDispatchLog, 'finance_contract', c.id, milestone):
                continue

            to_list = set(cc)
            # account_handler may be a name; try match user by full_name or email
            handler = (c.account_handler or '').strip()
            if handler:
                u = User.query.filter(
                    db.or_(User.full_name == handler, User.email == handler, User.username == handler)
                ).first()
                if u and u.email:
                    to_list.add(u.email.strip().lower())
                elif '@' in handler:
                    to_list.add(handler.lower())

            if not to_list:
                _mark_sent(db, ReminderDispatchLog, 'finance_contract', c.id, milestone, '(no recipients)')
                sent += 1
                continue

            label = '45 days' if milestone == 'amc_45d' else '10 days'
            subject = f'[AMC Renewal] {c.contract_id} expires in {label}'
            body = (
                f'AMC / contract {c.contract_id} ({c.client_name}) expires on {c.end_date}.\n'
                f'This is the {label}-before-expiry reminder.\n'
                f'Account handler: {c.account_handler or "—"}\n'
                f'Value: {c.contract_value or "—"}\n'
            )
            html = f"""
            <div style="font-family:sans-serif;max-width:560px">
              <h2 style="color:#a81222">AMC Renewal Reminder ({label})</h2>
              <p>Contract <strong>{c.contract_id}</strong> — {c.client_name}</p>
              <p>Expires: <strong>{c.end_date}</strong></p>
              <p>Please start renewal discussions with the client.</p>
            </div>
            """
            if is_email_configured():
                send_email(list(to_list), subject, body, html_body=html, cc=list(cc - to_list) or None)
            _mark_sent(db, ReminderDispatchLog, 'finance_contract', c.id, milestone, ','.join(sorted(to_list)))
            sent += 1

        # Ticket project renewal dates (secondary)
        projects = TicketProject.query.filter(
            TicketProject.is_active.is_(True),
            TicketProject.renewal_date.isnot(None),
        ).all()
        for p in projects:
            days_left = (p.renewal_date - today).days
            milestone = None
            if days_left == 45:
                milestone = 'amc_45d'
            elif days_left == 10:
                milestone = 'amc_10d'
            if not milestone:
                continue
            if _already_sent(db, ReminderDispatchLog, 'ticket_project', p.id, milestone):
                continue
            to_list = set(cc)
            if p.supervisor_user and p.supervisor_user.email:
                to_list.add(p.supervisor_user.email.strip().lower())
            if p.bd_project and p.bd_project.owner_user and p.bd_project.owner_user.email:
                to_list.add(p.bd_project.owner_user.email.strip().lower())
            label = '45 days' if milestone == 'amc_45d' else '10 days'
            subject = f'[Project Renewal] {p.name} — {label} reminder'
            body = f'Project {p.name} renewal date is {p.renewal_date} ({label} away).\n'
            if to_list and is_email_configured():
                send_email(list(to_list), subject, body)
            _mark_sent(db, ReminderDispatchLog, 'ticket_project', p.id, milestone,
                       ','.join(sorted(to_list)) or '(no recipients)')
            # Also flip linked BD deal status when within renewal window
            if p.bd_project and (p.bd_project.status or '') not in ('lost', 'won'):
                if days_left <= 45:
                    p.bd_project.status = 'under_renewal'
            sent += 1

        db.session.commit()
        logger.info('AMC renewal reminders sent: %s', sent)
        return {'sent': sent}


def run_payment_followup_reminders(app=None):
    """~Day 25 of 30-day terms: reminder on issued unpaid trading invoices + unpaid tickets."""
    if app is None:
        try:
            from kynver import create_app
            app = create_app()
        except Exception:
            try:
                from Injaaz import create_app
                app = create_app()
            except Exception:
                from Amaan import create_app
                app = create_app()

    with app.app_context():
        from app.models import db, TradingInvoice, Ticket, ReminderDispatchLog, Client
        from common.email_service import send_email, is_email_configured

        today = date.today()
        target = today + timedelta(days=5)  # due in 5 days ≈ day 25 of 30
        sent = 0
        finance_cc = _finance_cc()

        invoices = TradingInvoice.query.filter(
            TradingInvoice.status == 'issued',
            TradingInvoice.due_date.isnot(None),
            TradingInvoice.due_date == target,
        ).all()
        for inv in invoices:
            if _already_sent(db, ReminderDispatchLog, 'trading_invoice', inv.id, 'payment_d25'):
                continue
            client = inv.client
            to_list = _parse_emails(client.email if client else None)
            if not to_list:
                _mark_sent(db, ReminderDispatchLog, 'trading_invoice', inv.id, 'payment_d25', '(no client email)')
                sent += 1
                continue
            subject = f'Payment reminder — Invoice {inv.invoice_no} due {inv.due_date}'
            body = (
                f'Dear {client.client_name if client else "Client"},\n\n'
                f'This is a friendly reminder that invoice {inv.invoice_no} '
                f'for AED {inv.grand_total or 0:.2f} is due on {inv.due_date}.\n\n'
                f'Please arrange payment at your earliest convenience.\n'
            )
            html = f"""
            <div style="font-family:sans-serif;max-width:560px">
              <h2 style="color:#a81222">Payment Reminder</h2>
              <p>Invoice <strong>{inv.invoice_no}</strong> for
              <strong>AED {inv.grand_total or 0:.2f}</strong> is due on
              <strong>{inv.due_date}</strong>.</p>
            </div>
            """
            if is_email_configured():
                send_email(list(to_list), subject, body, html_body=html,
                           cc=list(finance_cc) or None)
            _mark_sent(db, ReminderDispatchLog, 'trading_invoice', inv.id, 'payment_d25',
                       ','.join(sorted(to_list)))
            sent += 1

        tickets = Ticket.query.filter(
            Ticket.payment_status == 'unpaid',
            Ticket.payment_due_date.isnot(None),
            Ticket.payment_due_date == target,
        ).all()
        for t in tickets:
            if _already_sent(db, ReminderDispatchLog, 'ticket', t.id, 'payment_d25'):
                continue
            # Prefer project client via finance contract notes / reporter — use finance CC + supervisor
            to_list = set(finance_cc)
            if t.supervisor and t.supervisor.email:
                to_list.add(t.supervisor.email.strip().lower())
            subject = f'Payment reminder — Job {t.ticket_id} due {t.payment_due_date}'
            body = (
                f'Service job {t.ticket_id} ({t.title}) has an unpaid invoice due {t.payment_due_date}.\n'
                f'ERP ref: {t.finance_invoice_ref or "—"}\n'
                f'Amount: AED {t.selling_price or t.actual_price or 0:.2f}\n'
            )
            if to_list and is_email_configured():
                send_email(list(to_list), subject, body)
            _mark_sent(db, ReminderDispatchLog, 'ticket', t.id, 'payment_d25',
                       ','.join(sorted(to_list)) or '(no recipients)')
            sent += 1

        db.session.commit()
        logger.info('Payment follow-up reminders sent: %s', sent)
        return {'sent': sent}


def send_paid_confirmation_for_ticket(ticket, marked_by=None):
    """Event email when finance marks a ticket invoice as paid."""
    from app.models import db, ReminderDispatchLog, User
    from common.email_service import send_email, is_email_configured

    if not ticket or _already_sent(db, ReminderDispatchLog, 'ticket', ticket.id, 'paid_confirm'):
        return False

    to_list = set()
    for uid in filter(None, {ticket.reporter_id, ticket.supervisor_id, ticket.assigned_to_id}):
        u = db.session.get(User, uid)
        if u and u.email:
            to_list.add(u.email.strip().lower())
    # BD owner via project link
    try:
        from app.models import TicketProject
        proj = TicketProject.query.filter_by(name=ticket.project).first()
        if proj and proj.bd_project and proj.bd_project.owner_user and proj.bd_project.owner_user.email:
            to_list.add(proj.bd_project.owner_user.email.strip().lower())
    except Exception:
        pass

    recipients = ','.join(sorted(to_list)) or '(no recipients)'
    if to_list and is_email_configured():
        who = (marked_by.full_name if marked_by else 'Finance')
        subject = f'Payment confirmed — {ticket.ticket_id}'
        body = (
            f'Invoice for job {ticket.ticket_id} has been marked paid by {who}.\n'
            f'ERP ref: {ticket.finance_invoice_ref or "—"}\n'
            f'Amount: AED {ticket.selling_price or ticket.actual_price or 0:.2f}\n'
        )
        send_email(list(to_list), subject, body)
    _mark_sent(db, ReminderDispatchLog, 'ticket', ticket.id, 'paid_confirm', recipients)
    return True


def send_paid_confirmation_for_trading_invoice(invoice, marked_by=None):
    from app.models import db, ReminderDispatchLog, User
    from common.email_service import send_email, is_email_configured

    if not invoice or _already_sent(db, ReminderDispatchLog, 'trading_invoice', invoice.id, 'paid_confirm'):
        return False

    to_list = set()
    owner = invoice.owner_user or invoice.created_by
    if owner and owner.email:
        to_list.add(owner.email.strip().lower())
    recipients = ','.join(sorted(to_list)) or '(no recipients)'
    if to_list and is_email_configured():
        who = (marked_by.full_name if marked_by else 'Finance')
        subject = f'Payment confirmed — {invoice.invoice_no}'
        body = (
            f'Trading invoice {invoice.invoice_no} marked paid by {who}.\n'
            f'Amount: AED {invoice.grand_total or 0:.2f}\n'
            f'Client: {invoice.client.client_name if invoice.client else "—"}\n'
        )
        send_email(list(to_list), subject, body)
    _mark_sent(db, ReminderDispatchLog, 'trading_invoice', invoice.id, 'paid_confirm', recipients)
    return True


def run_cd_inspection_reminders(app=None):
    """Email (and optional WhatsApp) at 2 days and 1 day before Civil Defense inspection_date."""
    if app is None:
        try:
            from kynver import create_app
            app = create_app()
        except Exception:
            try:
                from Injaaz import create_app
                app = create_app()
            except Exception:
                from Amaan import create_app
                app = create_app()

    with app.app_context():
        from app.models import db, InspectionNotification, User, ReminderDispatchLog
        from common.email_service import send_email, is_email_configured
        from common.whatsapp import send_whatsapp_message

        today = date.today()
        sent = 0
        open_statuses = ('pending', 'scheduled', 'overdue')
        notifs = InspectionNotification.query.filter(
            InspectionNotification.inspection_date.isnot(None),
            InspectionNotification.status.in_(open_statuses),
            InspectionNotification.outcome.is_(None),
        ).all()

        ops_users = User.query.filter(
            User.is_active == True,  # noqa: E712
            User.designation.in_(['operations_manager', 'supervisor']),
        ).all()
        default_emails = {u.email.strip().lower() for u in ops_users if u.email}
        wa_numbers = []
        for u in ops_users:
            phone = (getattr(u, 'phone', None) or '').strip()
            if phone:
                wa_numbers.append(phone)

        for notif in notifs:
            days_left = (notif.inspection_date - today).days
            if days_left == 2:
                milestone = 'cd_2d'
                label = '2 days'
            elif days_left == 1:
                milestone = 'cd_1d'
                label = '1 day'
            else:
                continue
            if _already_sent(db, ReminderDispatchLog, 'inspection_notification', notif.id, milestone):
                continue

            to_list = set(default_emails)
            recipients = ','.join(sorted(to_list)) or '(no recipients)'
            insp_date = notif.inspection_date.strftime('%d %b %Y') if notif.inspection_date else '—'
            subject = f'[Amaan] Civil Defense reminder ({label}) — {notif.site_name} ({insp_date})'
            body = (
                f'Reminder: Civil Defense / regulatory inspection in {label}.\n'
                f'Site: {notif.site_name}\n'
                f'Inspection date: {insp_date}\n'
                f'Type: {notif.inspection_type or "—"}\n'
                f'Ref: {notif.notif_id}\n'
                f'CD ref: {notif.civil_defense_ref or "—"}\n'
            )
            if to_list and is_email_configured():
                try:
                    send_email(list(to_list), subject, body)
                except Exception:
                    logger.exception('CD reminder email failed for %s', notif.notif_id)
            wa_body = (
                f'Amaan CD reminder ({label}): {notif.site_name} on {insp_date}. '
                f'Ref {notif.notif_id}'
            )
            try:
                send_whatsapp_message(wa_numbers, wa_body)
            except Exception:
                logger.exception('CD WhatsApp reminder failed for %s', notif.notif_id)

            _mark_sent(db, ReminderDispatchLog, 'inspection_notification', notif.id, milestone, recipients)
            sent += 1

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception('CD reminder commit failed')
            return 0
        logger.info('CD inspection reminders sent: %s', sent)
        return sent


def run_all_daily_reminders(app=None):
    """Entry point for the daily scheduler job."""
    amc = run_amc_renewal_reminders(app)
    pay = run_payment_followup_reminders(app)
    cd = run_cd_inspection_reminders(app)
    return {'amc': amc, 'payment': pay, 'cd': cd}
