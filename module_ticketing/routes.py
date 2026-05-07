"""
Ticketing Module Routes
A complete work-order / complaint ticketing system: register, classify,
locate (property/zone/sub-zone/base-unit), price (manpower + materials),
attach photos / live notes, capture closing signatures, generate PDF
report, and notify Admin / Assignee / GM / Requester on closure.
"""
import os
import io
import base64
import uuid
import logging
from datetime import datetime
from flask import (
    Blueprint, render_template, request, jsonify, current_app,
    send_file, abort, redirect, url_for
)
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import or_, desc

from app.models import (
    db, User, BDProject, Submission, Notification,
    Ticket, TicketNote, TicketImage, TicketLabor, TicketMaterial,
)

logger = logging.getLogger(__name__)

ticketing_bp = Blueprint(
    'ticketing', __name__,
    url_prefix='/ticketing',
    template_folder='templates'
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PRIORITIES = ['low', 'medium', 'high', 'critical']
STATUSES = ['open', 'in_progress', 'on_hold', 'closed', 'cancelled']
LABOR_DURATIONS = [15, 30, 45, 60, 120, 180]   # 180 means "3h+"
SERVICE_GROUPS = [
    'HVAC', 'MEP', 'Civil', 'Cleaning', 'IT',
    'Maintenance', 'Security', 'Other'
]


def get_current_user():
    user_id = get_jwt_identity()
    if user_id is None:
        return None
    return db.session.get(User, int(user_id))


def _next_ticket_no():
    last = db.session.query(Ticket).order_by(Ticket.id.desc()).first()
    seq = (last.id + 1) if last else 1
    return f'TC-{seq:06d}'


def _recalc_costs(ticket):
    labor_minutes = 0
    labor_cost = 0.0
    for entry in ticket.labor_entries:
        labor_minutes += int(entry.duration_minutes or 0)
        rate = float(entry.hourly_rate or 0)
        cost = float(entry.cost or 0) or (rate * (entry.duration_minutes or 0) / 60.0)
        entry.cost = round(cost, 2)
        labor_cost += entry.cost
    material_cost = 0.0
    for m in ticket.material_entries:
        cost = float(m.cost or 0) or (float(m.unit_price or 0) * float(m.quantity or 0))
        m.cost = round(cost, 2)
        material_cost += m.cost
    ticket.labor_minutes_total = labor_minutes
    ticket.labor_cost_total = round(labor_cost, 2)
    ticket.material_cost_total = round(material_cost, 2)


def _serialize_user(u):
    if not u:
        return None
    return {
        'id': u.id,
        'username': u.username,
        'full_name': u.full_name or u.username,
        'email': u.email,
        'designation': getattr(u, 'designation', None),
    }


def _save_data_url_image(data_url, ticket_no):
    """Persist a base64 data URL as a file under uploads/tickets/<ticket_no>/."""
    if not data_url or ',' not in data_url:
        return None
    try:
        header, b64 = data_url.split(',', 1)
        ext = 'png'
        if 'image/jpeg' in header:
            ext = 'jpg'
        elif 'image/webp' in header:
            ext = 'webp'
        raw = base64.b64decode(b64)
    except Exception:
        return None
    upload_root = current_app.config.get('UPLOADS_DIR') or \
                  os.path.join(current_app.root_path, 'generated', 'uploads')
    out_dir = os.path.join(upload_root, 'tickets', ticket_no)
    os.makedirs(out_dir, exist_ok=True)
    fname = f'{uuid.uuid4().hex}.{ext}'
    fpath = os.path.join(out_dir, fname)
    with open(fpath, 'wb') as f:
        f.write(raw)
    rel = os.path.relpath(fpath, upload_root)
    return rel.replace('\\', '/')


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@ticketing_bp.route('/')
@jwt_required()
def dashboard():
    user = get_current_user()
    if not user:
        return redirect(url_for('login_page'))
    return render_template('ticketing_dashboard.html', user=user)


@ticketing_bp.route('/new')
@jwt_required()
def new_ticket_page():
    user = get_current_user()
    if not user:
        return redirect(url_for('login_page'))
    return render_template('ticketing_new.html', user=user)


@ticketing_bp.route('/<int:ticket_id>')
@jwt_required()
def ticket_detail_page(ticket_id):
    user = get_current_user()
    if not user:
        return redirect(url_for('login_page'))
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket:
        abort(404)
    return render_template('ticketing_detail.html', user=user, ticket=ticket)


# ---------------------------------------------------------------------------
# Reference data (for selects)
# ---------------------------------------------------------------------------

@ticketing_bp.route('/api/reference')
@jwt_required()
def reference_data():
    """Lookups for the ticket form: team members, projects, materials."""
    users = User.query.filter_by(is_active=True).order_by(User.full_name).all()
    projects = BDProject.query.order_by(BDProject.name).all()

    # Materials from procurement module submissions
    materials = []
    proc_subs = Submission.query.filter(
        Submission.module_type == 'procurement_material'
    ).order_by(Submission.created_at.desc()).limit(500).all()
    for s in proc_subs:
        fd = s.form_data or {}
        materials.append({
            'ref': s.submission_id,
            'name': fd.get('material_name') or fd.get('site_name') or 'Material',
            'unit': fd.get('unit') or fd.get('uom') or '',
            'unit_price': float(fd.get('unit_price') or fd.get('price') or 0),
        })

    return jsonify({
        'priorities': PRIORITIES,
        'statuses': STATUSES,
        'service_groups': SERVICE_GROUPS,
        'labor_durations': LABOR_DURATIONS,
        'team': [_serialize_user(u) for u in users],
        'projects': [
            {'id': p.id, 'name': p.name, 'company': p.company}
            for p in projects
        ],
        'materials': materials,
    })


# ---------------------------------------------------------------------------
# CRUD API
# ---------------------------------------------------------------------------

@ticketing_bp.route('/api/tickets', methods=['GET'])
@jwt_required()
def list_tickets():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'unauthorized'}), 401

    q = Ticket.query
    status = request.args.get('status')
    priority = request.args.get('priority')
    project_id = request.args.get('project_id', type=int)
    assignee = request.args.get('assignee_id', type=int)
    search = request.args.get('q', '').strip()

    if status:
        q = q.filter(Ticket.status == status)
    if priority:
        q = q.filter(Ticket.priority == priority)
    if project_id:
        q = q.filter(Ticket.project_id == project_id)
    if assignee:
        q = q.filter(Ticket.assigned_to_id == assignee)
    if search:
        like = f'%{search}%'
        q = q.filter(or_(
            Ticket.title.ilike(like),
            Ticket.ticket_no.ilike(like),
            Ticket.description.ilike(like),
            Ticket.fault_type.ilike(like),
        ))

    tickets = q.order_by(desc(Ticket.created_at)).limit(500).all()
    summary = {
        'total': len(tickets),
        'open': sum(1 for t in tickets if t.status == 'open'),
        'in_progress': sum(1 for t in tickets if t.status == 'in_progress'),
        'closed': sum(1 for t in tickets if t.status == 'closed'),
        'critical': sum(1 for t in tickets if t.priority == 'critical'),
    }
    return jsonify({
        'tickets': [t.to_dict() for t in tickets],
        'summary': summary,
    })


@ticketing_bp.route('/api/tickets', methods=['POST'])
@jwt_required()
def create_ticket():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'unauthorized'}), 401
    data = request.get_json(silent=True) or {}

    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({'error': 'title is required'}), 400

    priority = data.get('priority') or 'medium'
    if priority not in PRIORITIES:
        priority = 'medium'

    project = None
    if data.get('project_id'):
        project = db.session.get(BDProject, int(data['project_id']))

    reporter = None
    if data.get('reporter_id'):
        reporter = db.session.get(User, int(data['reporter_id']))

    assignee = None
    if data.get('assigned_to_id'):
        assignee = db.session.get(User, int(data['assigned_to_id']))

    ticket = Ticket(
        ticket_no=_next_ticket_no(),
        project_id=project.id if project else None,
        project_name=project.name if project else (data.get('project_name') or None),
        reporter_id=reporter.id if reporter else None,
        reporter_name=(reporter.full_name if reporter else data.get('reporter_name')) or None,
        reporter_contact=data.get('reporter_contact'),
        service_group=data.get('service_group'),
        category=data.get('category'),
        fault_type=data.get('fault_type'),
        priority=priority,
        title=title,
        description=data.get('description'),
        loc_property=data.get('loc_property'),
        loc_zone=data.get('loc_zone'),
        loc_sub_zone=data.get('loc_sub_zone'),
        loc_base_unit=data.get('loc_base_unit'),
        chargeable=bool(data.get('chargeable')),
        assigned_to_id=assignee.id if assignee else None,
        projected_price=float(data.get('projected_price') or 0),
        status='open',
        created_by_id=user.id,
    )
    db.session.add(ticket)
    db.session.commit()

    # Notify the assignee
    if assignee:
        db.session.add(Notification(
            user_id=assignee.id,
            title=f'New ticket {ticket.ticket_no} assigned',
            message=f'{ticket.title} (priority: {ticket.priority})',
            notification_type='info',
            submission_id=ticket.ticket_no,
        ))
        db.session.commit()

    return jsonify({'ticket': ticket.to_dict(include_children=True)}), 201


@ticketing_bp.route('/api/tickets/<int:ticket_id>', methods=['GET'])
@jwt_required()
def get_ticket(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket:
        return jsonify({'error': 'not found'}), 404
    return jsonify({'ticket': ticket.to_dict(include_children=True)})


@ticketing_bp.route('/api/tickets/<int:ticket_id>', methods=['PATCH'])
@jwt_required()
def update_ticket(ticket_id):
    user = get_current_user()
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket:
        return jsonify({'error': 'not found'}), 404
    data = request.get_json(silent=True) or {}

    editable = [
        'title', 'description', 'service_group', 'category', 'fault_type',
        'priority', 'loc_property', 'loc_zone', 'loc_sub_zone', 'loc_base_unit',
        'reporter_name', 'reporter_contact', 'project_name',
    ]
    for f in editable:
        if f in data:
            setattr(ticket, f, data[f])

    if 'priority' in data and data['priority'] not in PRIORITIES:
        ticket.priority = 'medium'
    if 'status' in data and data['status'] in STATUSES:
        ticket.status = data['status']
    if 'chargeable' in data:
        ticket.chargeable = bool(data['chargeable'])
    if 'projected_price' in data:
        ticket.projected_price = float(data['projected_price'] or 0)
    if 'assigned_to_id' in data:
        ticket.assigned_to_id = int(data['assigned_to_id']) if data['assigned_to_id'] else None
    if 'project_id' in data:
        ticket.project_id = int(data['project_id']) if data['project_id'] else None
        if ticket.project_id:
            p = db.session.get(BDProject, ticket.project_id)
            if p:
                ticket.project_name = p.name

    db.session.commit()
    return jsonify({'ticket': ticket.to_dict(include_children=True)})


@ticketing_bp.route('/api/tickets/<int:ticket_id>', methods=['DELETE'])
@jwt_required()
def delete_ticket(ticket_id):
    user = get_current_user()
    if not user or user.role != 'admin':
        return jsonify({'error': 'admin only'}), 403
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket:
        return jsonify({'error': 'not found'}), 404
    db.session.delete(ticket)
    db.session.commit()
    return jsonify({'success': True})


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------

@ticketing_bp.route('/api/tickets/<int:ticket_id>/notes', methods=['POST'])
@jwt_required()
def add_note(ticket_id):
    user = get_current_user()
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket:
        return jsonify({'error': 'not found'}), 404
    data = request.get_json(silent=True) or {}
    body = (data.get('body') or '').strip()
    if not body:
        return jsonify({'error': 'body is required'}), 400
    note = TicketNote(
        ticket_id=ticket.id,
        author_id=user.id if user else None,
        author_name=user.full_name if user else None,
        body=body,
    )
    db.session.add(note)
    db.session.commit()
    return jsonify({'note': note.to_dict()}), 201


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

@ticketing_bp.route('/api/tickets/<int:ticket_id>/images', methods=['POST'])
@jwt_required()
def add_image(ticket_id):
    user = get_current_user()
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket:
        return jsonify({'error': 'not found'}), 404

    saved = []
    if request.files:
        upload_root = current_app.config.get('UPLOADS_DIR') or \
                      os.path.join(current_app.root_path, 'generated', 'uploads')
        out_dir = os.path.join(upload_root, 'tickets', ticket.ticket_no)
        os.makedirs(out_dir, exist_ok=True)
        for f in request.files.getlist('files'):
            if not f or not f.filename:
                continue
            ext = os.path.splitext(f.filename)[1].lower() or '.png'
            fname = f'{uuid.uuid4().hex}{ext}'
            fpath = os.path.join(out_dir, fname)
            f.save(fpath)
            rel = os.path.relpath(fpath, upload_root).replace('\\', '/')
            img = TicketImage(
                ticket_id=ticket.id, file_path=rel,
                caption=request.form.get('caption'),
                uploaded_by_id=user.id if user else None,
            )
            db.session.add(img)
            saved.append(img)
    else:
        data = request.get_json(silent=True) or {}
        rel = _save_data_url_image(data.get('data_url'), ticket.ticket_no)
        if rel:
            img = TicketImage(
                ticket_id=ticket.id, file_path=rel,
                caption=data.get('caption'),
                uploaded_by_id=user.id if user else None,
            )
            db.session.add(img)
            saved.append(img)

    db.session.commit()
    return jsonify({'images': [i.to_dict() for i in saved]}), 201


@ticketing_bp.route('/uploads/<path:rel>')
@jwt_required()
def serve_upload(rel):
    upload_root = current_app.config.get('UPLOADS_DIR') or \
                  os.path.join(current_app.root_path, 'generated', 'uploads')
    full = os.path.join(upload_root, rel)
    if not os.path.isfile(full):
        abort(404)
    return send_file(full)


# ---------------------------------------------------------------------------
# Labor & materials
# ---------------------------------------------------------------------------

@ticketing_bp.route('/api/tickets/<int:ticket_id>/labor', methods=['POST'])
@jwt_required()
def add_labor(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket:
        return jsonify({'error': 'not found'}), 404
    data = request.get_json(silent=True) or {}
    duration = int(data.get('duration_minutes') or 0)
    if duration not in LABOR_DURATIONS:
        return jsonify({'error': f'duration must be one of {LABOR_DURATIONS}'}), 400
    rate = float(data.get('hourly_rate') or 0)
    cost = round(rate * duration / 60.0, 2)
    entry = TicketLabor(
        ticket_id=ticket.id,
        worker_name=data.get('worker_name'),
        duration_minutes=duration,
        hourly_rate=rate,
        cost=cost,
        notes=data.get('notes'),
    )
    db.session.add(entry)
    _recalc_costs(ticket)
    db.session.commit()
    return jsonify({'labor': entry.to_dict(), 'ticket': ticket.to_dict()}), 201


@ticketing_bp.route('/api/tickets/<int:ticket_id>/labor/<int:entry_id>', methods=['DELETE'])
@jwt_required()
def delete_labor(ticket_id, entry_id):
    entry = db.session.get(TicketLabor, entry_id)
    if not entry or entry.ticket_id != ticket_id:
        return jsonify({'error': 'not found'}), 404
    ticket = entry.ticket
    db.session.delete(entry)
    db.session.flush()
    _recalc_costs(ticket)
    db.session.commit()
    return jsonify({'ticket': ticket.to_dict()})


@ticketing_bp.route('/api/tickets/<int:ticket_id>/materials', methods=['POST'])
@jwt_required()
def add_material(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket:
        return jsonify({'error': 'not found'}), 404
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'name required'}), 400
    qty = float(data.get('quantity') or 1)
    price = float(data.get('unit_price') or 0)
    entry = TicketMaterial(
        ticket_id=ticket.id,
        procurement_ref=data.get('procurement_ref'),
        name=name,
        unit=data.get('unit'),
        quantity=qty,
        unit_price=price,
        cost=round(qty * price, 2),
        is_new=bool(data.get('is_new')),
    )
    db.session.add(entry)
    _recalc_costs(ticket)
    db.session.commit()
    return jsonify({'material': entry.to_dict(), 'ticket': ticket.to_dict()}), 201


@ticketing_bp.route('/api/tickets/<int:ticket_id>/materials/<int:entry_id>', methods=['DELETE'])
@jwt_required()
def delete_material(ticket_id, entry_id):
    entry = db.session.get(TicketMaterial, entry_id)
    if not entry or entry.ticket_id != ticket_id:
        return jsonify({'error': 'not found'}), 404
    ticket = entry.ticket
    db.session.delete(entry)
    db.session.flush()
    _recalc_costs(ticket)
    db.session.commit()
    return jsonify({'ticket': ticket.to_dict()})


# ---------------------------------------------------------------------------
# Close ticket: capture signatures, generate PDF, send notifications
# ---------------------------------------------------------------------------

@ticketing_bp.route('/api/tickets/<int:ticket_id>/close', methods=['POST'])
@jwt_required()
def close_ticket(ticket_id):
    user = get_current_user()
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket:
        return jsonify({'error': 'not found'}), 404
    if ticket.status == 'closed':
        return jsonify({'error': 'ticket already closed'}), 400

    data = request.get_json(silent=True) or {}
    summary = (data.get('summary') or '').strip()
    requester_sig = data.get('requester_signature')
    technician_sig = data.get('technician_signature')

    if not requester_sig or not technician_sig:
        return jsonify({'error': 'requester and technician signatures are required'}), 400

    ticket.closure_summary = summary
    ticket.requester_signature = requester_sig
    ticket.technician_signature = technician_sig
    ticket.closed_at = datetime.utcnow()
    ticket.closed_by_id = user.id if user else None
    ticket.status = 'closed'
    _recalc_costs(ticket)
    db.session.commit()

    # Generate PDF report
    pdf_rel = None
    try:
        from .pdf_service import build_ticket_pdf
        gen_dir = current_app.config.get('GENERATED_DIR') or \
                  os.path.join(current_app.root_path, 'generated')
        out_dir = os.path.join(gen_dir, 'tickets')
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f'{ticket.ticket_no}.pdf')
        build_ticket_pdf(ticket, out_path)
        ticket.pdf_path = os.path.relpath(out_path, gen_dir).replace('\\', '/')
        db.session.commit()
        pdf_rel = ticket.pdf_path
    except Exception as e:
        logger.exception('Ticket PDF generation failed: %s', e)

    # Notify (admin, assignee, GM, requester)
    try:
        _notify_close(ticket, pdf_path=os.path.join(
            current_app.config.get('GENERATED_DIR') or
            os.path.join(current_app.root_path, 'generated'),
            pdf_rel
        ) if pdf_rel else None)
    except Exception as e:
        logger.exception('Ticket close notifications failed: %s', e)

    return jsonify({'ticket': ticket.to_dict(include_children=True)})


def _notify_close(ticket, pdf_path=None):
    """Send in-app + email notifications when a ticket is closed."""
    recipients = set()

    # In-app notification + email recipient: assignee
    if ticket.assignee:
        db.session.add(Notification(
            user_id=ticket.assignee.id,
            title=f'Ticket {ticket.ticket_no} closed',
            message=ticket.title, notification_type='success',
            submission_id=ticket.ticket_no,
        ))
        if ticket.assignee.email:
            recipients.add(ticket.assignee.email)

    # Requester
    if ticket.reporter and ticket.reporter.email:
        recipients.add(ticket.reporter.email)
        db.session.add(Notification(
            user_id=ticket.reporter.id,
            title=f'Your ticket {ticket.ticket_no} has been closed',
            message=ticket.closure_summary or ticket.title,
            notification_type='success',
            submission_id=ticket.ticket_no,
        ))

    # Admins
    admins = User.query.filter_by(role='admin', is_active=True).all()
    for a in admins:
        if a.email:
            recipients.add(a.email)

    # GM
    gms = User.query.filter_by(designation='general_manager', is_active=True).all()
    for g in gms:
        if g.email:
            recipients.add(g.email)
        db.session.add(Notification(
            user_id=g.id,
            title=f'Ticket {ticket.ticket_no} closed',
            message=ticket.title, notification_type='info',
            submission_id=ticket.ticket_no,
        ))

    db.session.commit()

    if not recipients:
        return

    try:
        from common.email_service import send_email, is_email_configured
    except Exception:
        return
    if not is_email_configured():
        logger.info('Email not configured; skipping ticket close email')
        return

    subject = f'[Injaaz] Ticket {ticket.ticket_no} closed - {ticket.title}'
    body_lines = [
        f'Ticket: {ticket.ticket_no}',
        f'Title:  {ticket.title}',
        f'Project: {ticket.project_name or "-"}',
        f'Priority: {ticket.priority}',
        f'Service group: {ticket.service_group or "-"}',
        f'Category / Fault: {(ticket.category or "-")} / {(ticket.fault_type or "-")}',
        f'Location: {ticket.loc_property or "-"} / {ticket.loc_zone or "-"} / '
        f'{ticket.loc_sub_zone or "-"} / {ticket.loc_base_unit or "-"}',
        f'Chargeable: {"Yes" if ticket.chargeable else "No"}',
        f'Manpower: {ticket.labor_minutes_total} min ({ticket.labor_cost_total:.2f})',
        f'Materials: {ticket.material_cost_total:.2f}',
        f'Projected price: {ticket.projected_price:.2f}',
        f'Total cost: {(ticket.labor_cost_total or 0) + (ticket.material_cost_total or 0):.2f}',
        '',
        'Closure summary:',
        ticket.closure_summary or '(none)',
    ]
    body = '\n'.join(body_lines)
    attachments = []
    if pdf_path and os.path.isfile(pdf_path):
        attachments.append(pdf_path)
    try:
        send_email(list(recipients), subject, body, attachments=attachments or None)
    except Exception as e:
        logger.exception('send_email failed for ticket %s: %s', ticket.ticket_no, e)


# ---------------------------------------------------------------------------
# PDF download
# ---------------------------------------------------------------------------

@ticketing_bp.route('/api/tickets/<int:ticket_id>/pdf')
@jwt_required()
def download_pdf(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket:
        abort(404)
    gen_dir = current_app.config.get('GENERATED_DIR') or \
              os.path.join(current_app.root_path, 'generated')
    out_dir = os.path.join(gen_dir, 'tickets')
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f'{ticket.ticket_no}.pdf')
    if not os.path.isfile(out_path):
        try:
            from .pdf_service import build_ticket_pdf
            build_ticket_pdf(ticket, out_path)
        except Exception as e:
            logger.exception('PDF build failed: %s', e)
            return jsonify({'error': 'pdf generation failed'}), 500
    return send_file(out_path, as_attachment=True,
                     download_name=f'{ticket.ticket_no}.pdf')
