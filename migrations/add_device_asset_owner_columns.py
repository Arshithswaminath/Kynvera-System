"""
Add asset_owner_name and assignment_date to devices.

Run: python migrations/add_device_asset_owner_columns.py
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
        dialect = engine.dialect.name
        if dialect == 'postgresql':
            stmts = [
                'ALTER TABLE devices ADD COLUMN IF NOT EXISTS asset_owner_name VARCHAR(255)',
                'ALTER TABLE devices ADD COLUMN IF NOT EXISTS assignment_date DATE',
            ]
        else:
            stmts = [
                'ALTER TABLE devices ADD COLUMN asset_owner_name VARCHAR(255)',
                'ALTER TABLE devices ADD COLUMN assignment_date DATE',
            ]

        with engine.connect() as conn:
            for sql in stmts:
                try:
                    conn.execute(db.text(sql))
                    conn.commit()
                except Exception as e:
                    err = str(e).lower()
                    if 'duplicate' in err or 'already exists' in err:
                        print('[SKIP] column may already exist:', sql[:60])
                    else:
                        raise
        print('[OK] devices.asset_owner_name and devices.assignment_date ready')


if __name__ == '__main__':
    migrate_up()
