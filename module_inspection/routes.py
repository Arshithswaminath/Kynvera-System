"""
Inspection Form Module - HVAC, Civil, Cleaning forms.
URL prefix: /inspection
"""
from flask import Blueprint, render_template, redirect
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import User

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


@inspection_bp.route('/')
@jwt_required()
def inspection_dashboard():
    """Inspection Form dashboard - HVAC, Civil, Cleaning form cards (like HR module)."""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return redirect('/login')
    if not _has_inspection_access(user):
        return redirect('/dashboard')
    return render_template('inspection_dashboard.html', user=user)
