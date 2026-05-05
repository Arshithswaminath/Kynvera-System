"""
Map legacy device status values to active | inactive.

Legacy: online, idle -> active; offline, update -> inactive; anything else -> active.

Run: python migrations/migrate_device_status_active_inactive.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Injaaz import create_app
from app.models import db


def migrate_up():
    app = create_app()
    with app.app_context():
        engine = db.engine
        stmts = [
            (
                "UPDATE devices SET status = 'inactive' "
                "WHERE lower(trim(coalesce(status, ''))) IN ('offline', 'update')"
            ),
            (
                "UPDATE devices SET status = 'active' "
                "WHERE lower(trim(coalesce(status, ''))) IN ('online', 'idle')"
            ),
            (
                "UPDATE devices SET status = 'active' "
                "WHERE lower(trim(coalesce(status, ''))) NOT IN ('active', 'inactive')"
            ),
        ]
        with engine.connect() as conn:
            for sql in stmts:
                conn.execute(db.text(sql))
            conn.commit()
        print('[OK] devices.status normalized to active/inactive')


if __name__ == '__main__':
    migrate_up()
