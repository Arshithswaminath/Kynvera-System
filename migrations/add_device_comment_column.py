"""
Add device_comment (admin notes) column to devices table.

Run: python migrations/add_device_comment_column.py
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
            sql = 'ALTER TABLE devices ADD COLUMN IF NOT EXISTS device_comment TEXT'
        else:
            sql = 'ALTER TABLE devices ADD COLUMN device_comment TEXT'

        with engine.connect() as conn:
            try:
                conn.execute(db.text(sql))
                conn.commit()
                print('[OK] devices.device_comment column ready')
            except Exception as e:
                err = str(e).lower()
                if 'duplicate' in err or 'already exists' in err or 'column device_comment of relation' in err:
                    print('[SKIP] device_comment already present')
                else:
                    raise


if __name__ == '__main__':
    migrate_up()
