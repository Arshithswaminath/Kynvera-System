"""
Finance & Invoicing Module
Handles contract tracking, monthly billing reports, costing, markup calculation,
and the 15% profit-margin approval gate.
URL prefix: /finance
"""
import uuid
import logging
from datetime import datetime, date, timezone
from calendar import monthrange

from flask import Blueprint, render_template, redirect, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func

from app.models import db, User, Ticket, FinanceContract, FinanceMonthlyReport

logger = logging.getLogger(__name__)

finance_bp = Blueprint('finance', __name__, url_prefix='/finance',
                       template_folder='templates')

MARGIN_THRESHOLD = 15.0   # percent — below this requires GM approval
CONTRACT_TYPES = ['monthly', 'quarterly', 'semi_annual', 'annual', 'one_time']
CONTRACT_TYPE_LABELS = {
    'monthly':     'Monthly',
    'quarterly':   'Quarterly',
    'semi_annual': 'Semi-Annual',
    'annual':      'Annual',
    'one_time':    'One-Time',
}


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _has_finance_access(user):
    if not user:
        return False
    if user.role == 'admin':
        return True
    return getattr(user, 'designation', None) in ('general_manager', 'operations_manager') or \
           getattr(user, 'access_ticketing', False)


def _finance_write_access(user):
    """Only admin / GM can create contracts or generate reports."""
    if not user:
        return False
    return user.role == 'admin' or getattr(user, 'designation', None) == 'general_manager'


def _compute_margin(ticket):
    """Return profit margin % given selling_price / actual_price on a ticket, or None."""
    if ticket.actual_price and ticket.actual_price > 0 and ticket.selling_price is not None:
        margin = ((ticket.selling_price - ticket.actual_price) / ticket.actual_price) * 100
        return round(margin, 2)
    return None


def _build_monthly_report_data(year: int, month: int):
    """Collect all closed/resolved tickets in a calendar month."""
    start = date(year, month, 1)
    _, last_day = monthrange(year, month)
    end = date(year, month, last_day)

    closed_tickets = Ticket.query.filter(
        Ticket.status.in_(['closed', 'resolved']),
        func.date(Ticket.closed_at) >= start,
        func.date(Ticket.closed_at) <= end,
    ).all()

    jobs = []
    total_value = 0.0
    for t in closed_tickets:
        val = t.selling_price or t.total_cost or 0.0
        total_value += val
        margin = _compute_margin(t)
        jobs.append({
            'ticket_id': t.ticket_id,
            'title': t.title,
            'project': t.project,
            'property': t.property_name or '',
            'service_group': t.service_group,
            'is_chargeable': t.is_chargeable,
            'total_cost': round(t.total_cost or 0, 2),
            'selling_price': round(t.selling_price or 0, 2),
            'margin_pct': margin,
            'closed_at': t.closed_at.isoformat() if t.closed_at else None,
            'finance_contract_id': t.finance_contract_id,
        })
    return jobs, round(total_value, 2)


# ──────────────────────────────────────────────────────────────────
# Page routes
# ──────────────────────────────────────────────────────────────────

@finance_bp.route('/')
@jwt_required()
def dashboard():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return redirect('/login')
    if not _has_finance_access(user):
        return redirect('/dashboard')
    return render_template('finance_dashboard.html', user=user)


@finance_bp.route('/contracts')
@jwt_required()
def contracts_page():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user or not _has_finance_access(user):
        return redirect('/dashboard')
    return render_template('finance_contracts.html', user=user,
                           contract_types=CONTRACT_TYPES,
                           contract_type_labels=CONTRACT_TYPE_LABELS)


@finance_bp.route('/reports')
@jwt_required()
def reports_page():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user or not _has_finance_access(user):
        return redirect('/dashboard')
    return render_template('finance_reports.html', user=user)


# ──────────────────────────────────────────────────────────────────
# API — Dashboard stats
# ──────────────────────────────────────────────────────────────────

@finance_bp.route('/api/stats', methods=['GET'])
@jwt_required()
def api_stats():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user or not _has_finance_access(user):
        return jsonify({'error': 'Access denied'}), 403

    today = date.today()
    closed_tickets = Ticket.query.filter(Ticket.status.in_(['closed', 'resolved'])).all()
    chargeable = [t for t in closed_tickets if t.is_chargeable]
    total_revenue = sum(t.selling_price or t.total_cost or 0 for t in chargeable)

    # Contract distribution for pie chart
    contracts = FinanceContract.query.filter_by(status='active').all()
    contract_dist = {}
    for c in contracts:
        label = CONTRACT_TYPE_LABELS.get(c.contract_type, c.contract_type)
        contract_dist[label] = contract_dist.get(label, 0) + 1

    # Jobs requiring GM approval
    gm_pending = Ticket.query.filter(
        Ticket.gm_approval_required == True,
        Ticket.gm_approved_at == None,
    ).count()

    # This month jobs
    this_month_start = date(today.year, today.month, 1)
    this_month_jobs = Ticket.query.filter(
        Ticket.status.in_(['closed', 'resolved']),
        func.date(Ticket.closed_at) >= this_month_start,
    ).count()

    return jsonify({
        'success': True,
        'stats': {
            'total_closed_jobs': len(closed_tickets),
            'chargeable_jobs': len(chargeable),
            'total_revenue': round(total_revenue, 2),
            'active_contracts': len(contracts),
            'gm_pending_approvals': gm_pending,
            'this_month_jobs': this_month_jobs,
            'contract_distribution': contract_dist,
        }
    })


# ──────────────────────────────────────────────────────────────────
# API — Contracts CRUD
# ──────────────────────────────────────────────────────────────────

@finance_bp.route('/api/contracts', methods=['GET'])
@jwt_required()
def api_list_contracts():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user or not _has_finance_access(user):
        return jsonify({'error': 'Access denied'}), 403

    status_filter = request.args.get('status', 'active')
    q = FinanceContract.query
    if status_filter:
        q = q.filter_by(status=status_filter)
    contracts = q.order_by(FinanceContract.end_date.asc()).all()
    return jsonify({'success': True, 'contracts': [c.to_dict() for c in contracts]})


@finance_bp.route('/api/contracts', methods=['POST'])
@jwt_required()
def api_create_contract():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user or not _finance_write_access(user):
        return jsonify({'error': 'Admin or GM only'}), 403

    data = request.get_json() or {}
    required = ['client_name', 'contract_type', 'start_date', 'end_date']
    for f in required:
        if not data.get(f):
            return jsonify({'error': f'{f} is required'}), 400

    try:
        start = date.fromisoformat(data['start_date'])
        end   = date.fromisoformat(data['end_date'])
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400

    contract_id = f"FIN-CON-{uuid.uuid4().hex[:8].upper()}"
    contract = FinanceContract(
        contract_id=contract_id,
        client_name=data['client_name'],
        property_name=data.get('property_name', ''),
        contract_type=data['contract_type'],
        service_type=data.get('service_type', ''),
        start_date=start,
        end_date=end,
        contract_value=float(data.get('contract_value') or 0),
        billing_day=int(data.get('billing_day') or 29),
        status='active',
        notes=data.get('notes', ''),
        created_by_id=user.id,
    )
    db.session.add(contract)
    db.session.commit()
    return jsonify({'success': True, 'contract': contract.to_dict()}), 201


@finance_bp.route('/api/contracts/<int:cid>', methods=['PATCH'])
@jwt_required()
def api_update_contract(cid):
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user or not _finance_write_access(user):
        return jsonify({'error': 'Admin or GM only'}), 403
    contract = FinanceContract.query.get_or_404(cid)
    data = request.get_json() or {}
    for field in ['client_name', 'property_name', 'contract_type', 'service_type',
                  'contract_value', 'billing_day', 'status', 'notes']:
        if field in data:
            setattr(contract, field, data[field])
    if 'start_date' in data:
        contract.start_date = date.fromisoformat(data['start_date'])
    if 'end_date' in data:
        contract.end_date = date.fromisoformat(data['end_date'])
    db.session.commit()
    return jsonify({'success': True, 'contract': contract.to_dict()})


@finance_bp.route('/api/contracts/<int:cid>', methods=['DELETE'])
@jwt_required()
def api_delete_contract(cid):
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user or user.role != 'admin':
        return jsonify({'error': 'Admin only'}), 403
    contract = FinanceContract.query.get_or_404(cid)
    db.session.delete(contract)
    db.session.commit()
    return jsonify({'success': True})


# ──────────────────────────────────────────────────────────────────
# API — Monthly Reports
# ──────────────────────────────────────────────────────────────────

@finance_bp.route('/api/reports', methods=['GET'])
@jwt_required()
def api_list_reports():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user or not _has_finance_access(user):
        return jsonify({'error': 'Access denied'}), 403
    reports = FinanceMonthlyReport.query.order_by(
        FinanceMonthlyReport.period_start.desc()).all()
    return jsonify({'success': True, 'reports': [r.to_dict() for r in reports]})


@finance_bp.route('/api/reports/generate', methods=['POST'])
@jwt_required()
def api_generate_report():
    """Generate (or regenerate) a monthly billing report for a given year/month."""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user or not _finance_write_access(user):
        return jsonify({'error': 'Admin or GM only'}), 403

    data = request.get_json() or {}
    today = date.today()
    year  = int(data.get('year', today.year))
    month = int(data.get('month', today.month))

    period_start = date(year, month, 1)
    _, last_day  = monthrange(year, month)
    period_end   = date(year, month, last_day)
    period_label = period_start.strftime('%B %Y')

    jobs, total_value = _build_monthly_report_data(year, month)

    # Upsert: one report per period
    existing = FinanceMonthlyReport.query.filter_by(
        period_start=period_start).first()
    if existing:
        existing.total_jobs   = len(jobs)
        existing.total_value  = total_value
        existing.report_data  = jobs
        existing.generated_by_id = user.id
        db.session.commit()
        return jsonify({'success': True, 'report': existing.to_dict(), 'jobs': jobs})

    report_id = f"FIN-RPT-{uuid.uuid4().hex[:8].upper()}"
    report = FinanceMonthlyReport(
        report_id=report_id,
        period_label=period_label,
        period_start=period_start,
        period_end=period_end,
        total_jobs=len(jobs),
        total_value=total_value,
        report_data=jobs,
        generated_by_id=user.id,
    )
    db.session.add(report)
    db.session.commit()
    return jsonify({'success': True, 'report': report.to_dict(), 'jobs': jobs}), 201


@finance_bp.route('/api/reports/<int:rid>/send', methods=['POST'])
@jwt_required()
def api_send_report(rid):
    """Email the monthly report to Finance team."""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user or not _finance_write_access(user):
        return jsonify({'error': 'Admin or GM only'}), 403

    report = FinanceMonthlyReport.query.get_or_404(rid)
    jobs = report.report_data or []

    # Build email HTML
    rows = ''.join(
        f"""<tr>
          <td style="padding:6px 8px;border-bottom:1px solid #f3f4f6;">{j['ticket_id']}</td>
          <td style="padding:6px 8px;border-bottom:1px solid #f3f4f6;">{j['title']}</td>
          <td style="padding:6px 8px;border-bottom:1px solid #f3f4f6;">{j['project']}</td>
          <td style="padding:6px 8px;border-bottom:1px solid #f3f4f6;">{'Yes' if j['is_chargeable'] else 'No'}</td>
          <td style="padding:6px 8px;border-bottom:1px solid #f3f4f6;text-align:right;">AED {j['selling_price']:.2f}</td>
        </tr>"""
        for j in jobs
    )
    html = f"""
<html><body style="font-family:sans-serif;color:#111;max-width:800px;margin:0 auto;">
  <div style="background:#d21725;padding:20px 24px;border-radius:10px 10px 0 0;">
    <h2 style="color:#fff;margin:0;">Monthly Finance Report — {report.period_label}</h2>
  </div>
  <div style="background:#fff;border:1px solid #e5e7eb;border-top:none;padding:24px;border-radius:0 0 10px 10px;">
    <p>Total Completed Jobs: <strong>{report.total_jobs}</strong> &nbsp;|&nbsp; Total Revenue: <strong>AED {report.total_value:,.2f}</strong></p>
    <table style="width:100%;border-collapse:collapse;font-size:.88rem;">
      <thead><tr style="background:#f9fafb;font-weight:700;font-size:.75rem;text-transform:uppercase;color:#9ca3af;">
        <th style="padding:8px;text-align:left;">Work Order</th>
        <th style="padding:8px;text-align:left;">Title</th>
        <th style="padding:8px;text-align:left;">Project</th>
        <th style="padding:8px;text-align:left;">Chargeable</th>
        <th style="padding:8px;text-align:right;">Amount</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>
    <p style="color:#6b7280;font-size:.8rem;margin-top:20px;">Generated by Amaan Application · {datetime.utcnow().strftime('%d %b %Y %H:%M')} UTC</p>
  </div>
</body></html>"""

    # Send to all admin + finance-designated users
    recipients = [u.email for u in User.query.filter(
        User.is_active == True,
        User.email.isnot(None),
    ).filter(
        db.or_(User.role == 'admin', User.designation == 'general_manager')
    ).all() if u.email]

    try:
        from common.email_service import send_email
        for r in recipients:
            send_email(
                to_email=r,
                subject=f'[Amaan Finance] Monthly Report — {report.period_label}',
                html_body=html,
                body=f'Monthly Finance Report {report.period_label}: {report.total_jobs} jobs, AED {report.total_value:,.2f}',
            )
        report.sent_to_finance_at = _utcnow()
        db.session.commit()
    except Exception as exc:
        logger.warning('Finance report email failed: %s', exc)
        return jsonify({'success': False, 'error': str(exc)}), 500

    return jsonify({'success': True, 'sent_to': len(recipients)})


# ──────────────────────────────────────────────────────────────────
# API — Costing Calculator / Margin Check
# ──────────────────────────────────────────────────────────────────

@finance_bp.route('/api/costing/calculate', methods=['POST'])
@jwt_required()
def api_calculate_costing():
    """
    Calculate profit margin and flag if GM approval required.
    Input: { manpower_cost, material_cost, overhead_pct, markup_pct }
    Output: { actual_price, selling_price, margin_pct, gm_approval_required }
    """
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'Not found'}), 404

    data = request.get_json() or {}
    manpower  = float(data.get('manpower_cost', 0) or 0)
    materials = float(data.get('material_cost', 0) or 0)
    overhead  = float(data.get('overhead_pct', 10) or 10)
    markup    = float(data.get('markup_pct', 0) or 0)

    raw_cost     = manpower + materials
    actual_price = raw_cost * (1 + overhead / 100)
    selling_price = actual_price * (1 + markup / 100)

    if actual_price > 0:
        margin_pct = ((selling_price - actual_price) / actual_price) * 100
    else:
        margin_pct = 0.0

    gm_required = bool(margin_pct < MARGIN_THRESHOLD and selling_price > 0)

    return jsonify({
        'success': True,
        'raw_cost': round(raw_cost, 2),
        'actual_price': round(actual_price, 2),
        'selling_price': round(selling_price, 2),
        'margin_pct': round(margin_pct, 2),
        'gm_approval_required': gm_required,
        'margin_threshold': MARGIN_THRESHOLD,
    })


# ──────────────────────────────────────────────────────────────────
# API — Jobs with contract/margin view
# ──────────────────────────────────────────────────────────────────

@finance_bp.route('/api/jobs', methods=['GET'])
@jwt_required()
def api_jobs():
    """Return closed jobs with costing data for Finance review."""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user or not _has_finance_access(user):
        return jsonify({'error': 'Access denied'}), 403

    page      = max(1, request.args.get('page', 1, type=int))
    per_page  = min(100, max(10, request.args.get('per_page', 30, type=int)))
    month_str = request.args.get('month')   # YYYY-MM
    status    = request.args.get('status', 'closed')

    q = Ticket.query.filter(Ticket.status.in_(['closed', 'resolved']))
    if month_str:
        try:
            y, m = [int(x) for x in month_str.split('-')]
            start = date(y, m, 1)
            _, ld = monthrange(y, m)
            end   = date(y, m, ld)
            q = q.filter(func.date(Ticket.closed_at) >= start,
                         func.date(Ticket.closed_at) <= end)
        except Exception:
            pass

    total = q.count()
    tickets = q.order_by(Ticket.closed_at.desc()).offset((page-1)*per_page).limit(per_page).all()

    jobs = []
    for t in tickets:
        margin = _compute_margin(t)
        jobs.append({
            'ticket_id': t.ticket_id,
            'title': t.title,
            'project': t.project,
            'property': t.property_name or '',
            'service_group': t.service_group,
            'is_chargeable': t.is_chargeable,
            'total_cost': round(t.total_cost or 0, 2),
            'actual_price': round(t.actual_price or 0, 2),
            'selling_price': round(t.selling_price or 0, 2),
            'markup_pct': t.markup_pct,
            'margin_pct': margin,
            'gm_approval_required': bool(t.gm_approval_required),
            'gm_approved': bool(t.gm_approved_at),
            'finance_contract_id': t.finance_contract_id,
            'closed_at': t.closed_at.isoformat() if t.closed_at else None,
        })

    return jsonify({'success': True, 'jobs': jobs, 'total': total, 'page': page, 'per_page': per_page})


# ──────────────────────────────────────────────────────────────────
# API — Finance workflow queue (pending / processing / completed)
# ──────────────────────────────────────────────────────────────────

@finance_bp.route('/api/queue', methods=['GET'])
@jwt_required()
def api_queue():
    """Tickets waiting for Finance to create the ERP invoice, plus those just closed."""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user or not _has_finance_access(user):
        return jsonify({'error': 'Access denied'}), 403

    bucket = request.args.get('bucket', 'pending')  # pending | completed
    limit  = min(50, max(5, request.args.get('limit', 20, type=int)))

    if bucket == 'completed':
        tickets = (Ticket.query
                   .filter(Ticket.finance_confirmed_at.isnot(None),
                           Ticket.status == 'closed')
                   .order_by(Ticket.finance_confirmed_at.desc())
                   .limit(limit).all())
    else:
        # Tickets enter the finance queue as soon as the supervisor verifies —
        # GM approval runs in parallel ('pending_gm_approval') or is done ('pending_finance').
        tickets = (Ticket.query
                   .filter(Ticket.status.in_(('pending_finance', 'pending_gm_approval')))
                   .order_by(Ticket.resolved_at.desc().nullslast(),
                             Ticket.updated_at.desc())
                   .limit(limit).all())

    items = []
    for t in tickets:
        items.append({
            'ticket_id': t.ticket_id,
            'title': t.title,
            'project': t.project,
            'property': t.property_name or '',
            'service_group': t.service_group,
            'priority': t.priority,
            'status': t.status,
            'is_chargeable': bool(t.is_chargeable),
            'selling_price': round(t.selling_price or 0, 2),
            'total_cost': round(t.total_cost or 0, 2),
            'margin_pct': _compute_margin(t),
            'service_report_url': f'/tickets/{t.ticket_id}/service-report',
            'invoice_url': f'/tickets/{t.ticket_id}/invoice',
            'ticket_url': f'/tickets/{t.ticket_id}',
            'created_at': t.created_at.isoformat() if t.created_at else None,
            'gm_approved_at': t.gm_approved_at.isoformat() if t.gm_approved_at else None,
            'resolved_at': t.resolved_at.isoformat() if t.resolved_at else None,
            'finance_confirmed_at': t.finance_confirmed_at.isoformat() if t.finance_confirmed_at else None,
            'finance_invoice_ref': t.finance_invoice_ref,
            'reporter_name': t.reporter.full_name if t.reporter else '',
            'supervisor_name': t.supervisor.full_name if t.supervisor else '',
        })

    # Counts for stats
    pending_count   = Ticket.query.filter(
        Ticket.status.in_(('pending_finance', 'pending_gm_approval'))).count()
    completed_today = (Ticket.query
                       .filter(func.date(Ticket.finance_confirmed_at) == date.today())
                       .count())
    completed_month = (Ticket.query
                       .filter(func.extract('year',  Ticket.finance_confirmed_at) == date.today().year,
                               func.extract('month', Ticket.finance_confirmed_at) == date.today().month)
                       .count())
    completed_total = Ticket.query.filter(Ticket.finance_confirmed_at.isnot(None)).count()

    return jsonify({
        'success': True,
        'items': items,
        'counts': {
            'pending': pending_count,
            'completed_today': completed_today,
            'completed_month': completed_month,
            'completed_total': completed_total,
        }
    })


# ──────────────────────────────────────────────────────────────────
# API — Link ticket to contract
# ──────────────────────────────────────────────────────────────────

@finance_bp.route('/api/tickets/<string:ticket_id>/link-contract', methods=['POST'])
@jwt_required()
def api_link_contract(ticket_id):
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user or not _has_finance_access(user):
        return jsonify({'error': 'Access denied'}), 403

    ticket = Ticket.query.filter_by(ticket_id=ticket_id).first_or_404()
    data = request.get_json() or {}
    contract_id = data.get('contract_id')
    if contract_id:
        contract = FinanceContract.query.get_or_404(int(contract_id))
        ticket.finance_contract_id = contract.id
    else:
        ticket.finance_contract_id = None
    db.session.commit()
    return jsonify({'success': True})
