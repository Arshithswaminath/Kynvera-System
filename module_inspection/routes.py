"""
Inspection Form Module - HVAC, Civil, Cleaning forms + Civil Defense notification tracking.
URL prefix: /inspection
"""
import uuid
import logging
from datetime import datetime, date, timezone

from flask import Blueprint, render_template, redirect, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import db, User, InspectionNotification

logger = logging.getLogger(__name__)

inspection_bp = Blueprint('inspection_bp', __name__, url_prefix='/inspection',
                          template_folder='templates')


def _has_inspection_access(user):
    """User has access if they have any of HVAC, Civil, or Cleaning access, or are admin."""
    if not user:
        return False
    if user.role == 'admin':
        return True
    return (
        getattr(user, 'access_hvac', False) or
        getattr(user, 'access_civil', False) or
        getattr(user, 'access_cleaning', False)
    )


def _has_notif_write_access(user):
    """Sales, BD, or admin can register notifications."""
    if not user:
        return False
    if user.role == 'admin':
        return True
    return getattr(user, 'designation', None) in ('business_development',) or \
           getattr(user, 'access_business_development', False) or \
           _has_inspection_access(user)


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _send_inspection_email(notif: InspectionNotification, app=None,
                           custom_to=None, custom_cc=None,
                           custom_subject=None, custom_body=None):
    """Send email notifying the ops team of a new inspection date."""
    try:
        from common.email_service import send_email
        if custom_to:
            recipients = custom_to
        else:
            ops_users = User.query.filter(
                User.is_active == True,
                User.designation.in_(['operations_manager', 'supervisor'])
            ).all()
            recipients = [u.email for u in ops_users if u.email]
        days_notice = notif.days_notice() or 0
        days_remaining = notif.days_remaining() or 0
        html = f"""
<html><body style="font-family:sans-serif;color:#1a1a1a;">
<div style="max-width:600px;margin:0 auto;padding:24px;">
  <div style="background:#d21725;padding:20px 24px;border-radius:10px 10px 0 0;">
    <h2 style="color:#fff;margin:0;">New Inspection Scheduled</h2>
    <p style="color:rgba(255,255,255,.85);margin:6px 0 0;">Civil Defense / Regulatory Notification</p>
  </div>
  <div style="background:#fff;border:1px solid #e5e7eb;border-top:none;padding:24px;border-radius:0 0 10px 10px;">
    <table style="width:100%;border-collapse:collapse;">
      <tr><td style="padding:8px 0;font-weight:600;width:160px;">Reference ID</td><td style="padding:8px 0;">{notif.notif_id}</td></tr>
      <tr style="background:#f9fafb;"><td style="padding:8px 4px;font-weight:600;">Site / Property</td><td style="padding:8px 4px;">{notif.site_name}</td></tr>
      <tr><td style="padding:8px 0;font-weight:600;">Inspection Type</td><td style="padding:8px 0;">{notif.inspection_type or 'Not specified'}</td></tr>
      <tr style="background:#f9fafb;"><td style="padding:8px 4px;font-weight:600;">Civil Defense Ref</td><td style="padding:8px 4px;">{notif.civil_defense_ref or '—'}</td></tr>
      <tr><td style="padding:8px 0;font-weight:600;">Notification Date</td><td style="padding:8px 0;">{notif.notification_date.strftime('%d %b %Y') if notif.notification_date else '—'}</td></tr>
      <tr style="background:#f9fafb;"><td style="padding:8px 4px;font-weight:600;">Inspection Date</td><td style="padding:8px 4px;"><strong style="color:#d21725;">{notif.inspection_date.strftime('%d %b %Y') if notif.inspection_date else '—'}</strong></td></tr>
      <tr><td style="padding:8px 0;font-weight:600;">Days Notice</td><td style="padding:8px 0;">{days_notice} days</td></tr>
      <tr style="background:#f9fafb;"><td style="padding:8px 4px;font-weight:600;">Days Remaining</td><td style="padding:8px 4px;"><strong style="color:{'#16a34a' if days_remaining > 7 else '#d97706' if days_remaining > 3 else '#dc2626'};">{days_remaining} days</strong></td></tr>
    </table>
    {'<p style="background:#fef3c7;border:1px solid #fde68a;border-radius:8px;padding:12px;margin-top:16px;"><strong>Note:</strong> ' + notif.notes + '</p>' if notif.notes else ''}
    <p style="margin-top:24px;">Please assign technicians and prepare for this inspection. Log in to the Amaan platform for full details.</p>
    <p style="color:#6b7280;font-size:.85rem;margin-top:16px;">This is an automated notification from Amaan Application.</p>
  </div>
</div>
</body></html>"""
        plain = (
            f"New inspection scheduled.\n"
            f"Site: {notif.site_name}\n"
            f"Inspection Date: {notif.inspection_date}\n"
            f"Days Remaining: {days_remaining}\n"
            f"Ref: {notif.notif_id}"
        )
        subject = custom_subject or f"[Amaan] Inspection Scheduled — {notif.site_name} ({notif.inspection_date})"
        body_text = custom_body or plain
        cc_list = custom_cc or []
        for r in recipients:
            send_email(r, subject=subject, body=body_text, html_body=html, cc=cc_list)
        notif.ops_notified_at = _utcnow()
        db.session.commit()
    except Exception as exc:
        logger.warning("Inspection notification email failed: %s", exc)


# ──────────────────────────────────────────────────────────────────
# Page routes
# ──────────────────────────────────────────────────────────────────

@inspection_bp.route('/')
@jwt_required()
def inspection_dashboard():
    """Inspection Form dashboard - HVAC, Civil, Cleaning form cards."""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return redirect('/login')
    if not _has_inspection_access(user):
        return redirect('/dashboard')
    return render_template('inspection_dashboard.html', user=user)


@inspection_bp.route('/notifications')
@jwt_required()
def notifications_page():
    """Civil Defense inspection notification tracker page."""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return redirect('/login')
    if not _has_inspection_access(user) and not _has_notif_write_access(user):
        return redirect('/dashboard')
    return render_template('inspection_notifications.html', user=user)


# ──────────────────────────────────────────────────────────────────
# API routes
# ──────────────────────────────────────────────────────────────────

@inspection_bp.route('/api/notifications', methods=['GET'])
@jwt_required()
def api_list_notifications():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'Not found'}), 404
    if not _has_inspection_access(user) and not _has_notif_write_access(user):
        return jsonify({'error': 'Access denied'}), 403

    status_filter = request.args.get('status')
    q = InspectionNotification.query.order_by(InspectionNotification.inspection_date.asc())
    if status_filter:
        q = q.filter_by(status=status_filter)

    # Auto-update overdue statuses
    today = date.today()
    notifs = q.all()
    changed = False
    for n in notifs:
        if n.status == 'pending' and n.inspection_date and n.inspection_date < today:
            n.status = 'overdue'
            changed = True
    if changed:
        db.session.commit()

    return jsonify({'success': True, 'notifications': [n.to_dict() for n in notifs]})


@inspection_bp.route('/api/notifications', methods=['POST'])
@jwt_required()
def api_create_notification():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'Not found'}), 404
    if not _has_notif_write_access(user):
        return jsonify({'error': 'Access denied'}), 403

    data = request.get_json() or {}
    if not data.get('site_name'):
        return jsonify({'error': 'site_name is required'}), 400
    if not data.get('notification_date') or not data.get('inspection_date'):
        return jsonify({'error': 'notification_date and inspection_date are required'}), 400

    try:
        notif_date = date.fromisoformat(data['notification_date'])
        insp_date = date.fromisoformat(data['inspection_date'])
    except ValueError:
        return jsonify({'error': 'Invalid date format; use YYYY-MM-DD'}), 400

    if insp_date <= notif_date:
        return jsonify({'error': 'Inspection date must be after notification date'}), 400

    notif_id = f"INSP-{uuid.uuid4().hex[:8].upper()}"
    notif = InspectionNotification(
        notif_id=notif_id,
        civil_defense_ref=data.get('civil_defense_ref', ''),
        site_name=data['site_name'],
        notification_date=notif_date,
        inspection_date=insp_date,
        inspection_type=data.get('inspection_type', ''),
        notes=data.get('notes', ''),
        status='pending',
        registered_by_id=user.id,
    )
    db.session.add(notif)
    db.session.commit()

    # Parse custom email recipients from request
    raw_to  = data.get('email_to', '')
    raw_cc  = data.get('email_cc', '')
    custom_to  = [e.strip() for e in raw_to.split(',')  if e.strip()] if raw_to  else None
    custom_cc  = [e.strip() for e in raw_cc.split(',')  if e.strip()] if raw_cc  else None
    custom_subject = data.get('email_subject') or None
    custom_body    = data.get('email_body')    or None

    # Fire email in background thread so request returns immediately
    try:
        from flask import current_app
        import threading
        app = current_app._get_current_object()
        threading.Thread(
            target=_send_inspection_email,
            args=(notif, app),
            kwargs=dict(custom_to=custom_to, custom_cc=custom_cc,
                        custom_subject=custom_subject, custom_body=custom_body),
            daemon=True
        ).start()
    except Exception:
        pass

    return jsonify({'success': True, 'notification': notif.to_dict()}), 201


@inspection_bp.route('/api/notifications/<int:notif_id_int>', methods=['PATCH'])
@jwt_required()
def api_update_notification(notif_id_int):
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'Not found'}), 404
    notif = InspectionNotification.query.get_or_404(notif_id_int)
    data = request.get_json() or {}
    if 'status' in data:
        notif.status = data['status']
    if 'notes' in data:
        notif.notes = data['notes']
    if 'civil_defense_ref' in data:
        notif.civil_defense_ref = data['civil_defense_ref']
    db.session.commit()
    return jsonify({'success': True, 'notification': notif.to_dict()})


@inspection_bp.route('/api/notifications/<int:notif_id_int>', methods=['DELETE'])
@jwt_required()
def api_delete_notification(notif_id_int):
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user or user.role != 'admin':
        return jsonify({'error': 'Admin only'}), 403
    notif = InspectionNotification.query.get_or_404(notif_id_int)
    db.session.delete(notif)
    db.session.commit()
    return jsonify({'success': True})


@inspection_bp.route('/api/notifications/stats', methods=['GET'])
@jwt_required()
def api_notification_stats():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'Not found'}), 404
    today = date.today()
    all_notifs = InspectionNotification.query.all()
    return jsonify({
        'success': True,
        'stats': {
            'total': len(all_notifs),
            'pending': sum(1 for n in all_notifs if n.status == 'pending'),
            'scheduled': sum(1 for n in all_notifs if n.status == 'scheduled'),
            'completed': sum(1 for n in all_notifs if n.status == 'completed'),
            'overdue': sum(1 for n in all_notifs if n.status == 'overdue' or (n.status == 'pending' and n.inspection_date and n.inspection_date < today)),
            'upcoming_7d': sum(1 for n in all_notifs if n.inspection_date and 0 <= (n.inspection_date - today).days <= 7 and n.status not in ('completed', 'cancelled')),
        }
    })
