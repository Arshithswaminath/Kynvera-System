"""HR leave-balance helpers (attendance lives under Operations)."""
from __future__ import annotations

from flask_jwt_extended import jwt_required, get_jwt_identity

from app.models import db, User
from common.error_responses import success_response, error_response


def register_attendance_routes(bp):
    """Kept for leave balances used by HR leave application form."""

    @bp.route('/api/leave-balances/me', methods=['GET'])
    @jwt_required()
    def api_my_leave_balances():
        user = db.session.get(User, get_jwt_identity())
        if not user:
            return error_response('User not found', status_code=404, error_code='NOT_FOUND')
        annual = getattr(user, 'annual_leave_days', None)
        sick = getattr(user, 'sick_leave_days', None)
        if sick is None:
            sick = getattr(user, 'other_leave_days', None)
        return success_response({
            'annual_leave_days': annual,
            'sick_leave_days': sick,
            'other_leave_days': getattr(user, 'other_leave_days', None),
            'display': {
                'annual': f'{annual} days left' if annual is not None else 'Not set',
                'sick': f'{sick} days left' if sick is not None else 'Not set',
            },
        })
