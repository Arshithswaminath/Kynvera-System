"""
Device Management pages — FM Executive shell at /admin/devices.
JSON APIs stay on /api/admin/devices.
"""
import logging

from flask import Blueprint, render_template, redirect, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.models import User, Device
from module_devices.service import (
    compute_compliance,
    compute_device_kpis,
    compute_overview,
    ensure_device_columns,
)

logger = logging.getLogger(__name__)

devices_bp = Blueprint(
    'devices_bp',
    __name__,
    url_prefix='/admin/devices',
    template_folder='templates',
)


@devices_bp.record_once
def _on_register(state):
    ensure_device_columns(state.app)


def _current_user():
    uid = get_jwt_identity()
    return User.query.get(uid) if uid else None


def _require_admin():
    user = _current_user()
    if not user or not user.is_active or user.role != 'admin':
        return None
    return user


def _period_from_request():
    period = (request.args.get('range') or 'week').strip().lower()
    if period not in ('week', 'month', 'all'):
        return 'week'
    return period


def _overview_from_request():
    return compute_overview(
        _period_from_request(),
        year=request.args.get('year'),
        month=request.args.get('month'),
    )


@devices_bp.route('/', strict_slashes=False)
@jwt_required()
def devices_dashboard():
    user = _require_admin()
    if not user:
        return redirect('/dashboard')
    overview = _overview_from_request()
    return render_template(
        'devices_dashboard.html',
        user=user,
        kpis=overview['kpis'],
        overview=overview,
        can_write=True,
        active_page='devices',
    )


@devices_bp.route('/all')
@jwt_required()
def devices_list_page():
    user = _require_admin()
    if not user:
        return redirect('/dashboard')
    return render_template(
        'devices_list.html',
        user=user,
        can_write=True,
        active_page='devices',
    )


@devices_bp.route('/analytics')
@jwt_required()
def devices_analytics():
    user = _require_admin()
    if not user:
        return redirect('/dashboard')
    overview = _overview_from_request()
    return render_template(
        'devices_analytics.html',
        user=user,
        kpis=overview['kpis'],
        overview=overview,
        can_write=True,
        active_page='devices',
    )


@devices_bp.route('/map')
@jwt_required()
def devices_map_page():
    user = _require_admin()
    if not user:
        return redirect('/dashboard')
    return render_template(
        'devices_map.html',
        user=user,
        can_write=True,
        active_page='devices',
    )


@devices_bp.route('/compliance')
@jwt_required()
def devices_compliance():
    user = _require_admin()
    if not user:
        return redirect('/dashboard')
    return render_template(
        'devices_compliance.html',
        user=user,
        compliance=compute_compliance(),
        kpis=compute_device_kpis(),
        can_write=True,
        active_page='devices',
    )


@devices_bp.route('/audit')
@jwt_required()
def devices_audit():
    user = _require_admin()
    if not user:
        return redirect('/dashboard')
    return render_template(
        'devices_audit.html',
        user=user,
        can_write=True,
        active_page='devices',
    )


@devices_bp.route('/new')
@jwt_required()
def devices_new_page():
    user = _require_admin()
    if not user:
        return redirect('/dashboard')
    return render_template(
        'devices_form.html',
        user=user,
        device=None,
        mode='create',
        can_write=True,
        active_page='devices',
    )


@devices_bp.route('/<int:device_pk>')
@jwt_required()
def devices_detail_page(device_pk):
    user = _require_admin()
    if not user:
        return redirect('/dashboard')
    device = Device.query.get_or_404(device_pk)
    return render_template(
        'devices_detail.html',
        user=user,
        device=device,
        can_write=True,
        active_page='devices',
    )


@devices_bp.route('/<int:device_pk>/edit')
@jwt_required()
def devices_edit_page(device_pk):
    user = _require_admin()
    if not user:
        return redirect('/dashboard')
    device = Device.query.get_or_404(device_pk)
    return render_template(
        'devices_form.html',
        user=user,
        device=device,
        mode='edit',
        can_write=True,
        active_page='devices',
    )
