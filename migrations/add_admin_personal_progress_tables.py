"""
Add admin_personal_projects and admin_personal_progress_steps tables.

Run: python migrations/add_admin_personal_progress_tables.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Injaaz import create_app
from app.models import db, AdminPersonalProject, AdminPersonalProgressStep


def migrate_up():
    app = create_app()
    with app.app_context():
        engine = db.engine
        AdminPersonalProject.__table__.create(bind=engine, checkfirst=True)
        AdminPersonalProgressStep.__table__.create(bind=engine, checkfirst=True)
        print('[OK] admin_personal_projects / admin_personal_progress_steps ready')


if __name__ == '__main__':
    migrate_up()
