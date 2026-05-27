from flask import Blueprint

site_visit_bp = Blueprint(
    'site_visit_bp',
    __name__,
    template_folder='templates',
    static_folder='static'
)

from . import routes  # noqa: E402,F401