"""
Create device_handovers table for asset handover audit log.

Run: python migrations/create_device_handovers_table.py
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
                """
                CREATE TABLE IF NOT EXISTS device_handovers (
                    id SERIAL PRIMARY KEY,
                    device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
                    handover_at TIMESTAMP NOT NULL,
                    from_person_name VARCHAR(255) NOT NULL,
                    from_person_email VARCHAR(255),
                    from_person_phone VARCHAR(80),
                    to_person_name VARCHAR(255) NOT NULL,
                    to_person_email VARCHAR(255),
                    to_person_phone VARCHAR(80),
                    condition_rating VARCHAR(20) NOT NULL,
                    condition_detail TEXT,
                    accessories_included TEXT,
                    defects_reported TEXT,
                    notes TEXT,
                    recorded_by_user_id INTEGER REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """,
                'CREATE INDEX IF NOT EXISTS ix_device_handovers_device_id ON device_handovers(device_id)',
                'CREATE INDEX IF NOT EXISTS ix_device_handovers_handover_at ON device_handovers(handover_at)',
            ]
        else:
            stmts = [
                """
                CREATE TABLE IF NOT EXISTS device_handovers (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    device_id INTEGER NOT NULL,
                    handover_at DATETIME NOT NULL,
                    from_person_name VARCHAR(255) NOT NULL,
                    from_person_email VARCHAR(255),
                    from_person_phone VARCHAR(80),
                    to_person_name VARCHAR(255) NOT NULL,
                    to_person_email VARCHAR(255),
                    to_person_phone VARCHAR(80),
                    condition_rating VARCHAR(20) NOT NULL,
                    condition_detail TEXT,
                    accessories_included TEXT,
                    defects_reported TEXT,
                    notes TEXT,
                    recorded_by_user_id INTEGER,
                    created_at DATETIME,
                    FOREIGN KEY(device_id) REFERENCES devices(id) ON DELETE CASCADE,
                    FOREIGN KEY(recorded_by_user_id) REFERENCES users(id)
                )
                """,
                'CREATE INDEX IF NOT EXISTS ix_device_handovers_device_id ON device_handovers(device_id)',
                'CREATE INDEX IF NOT EXISTS ix_device_handovers_handover_at ON device_handovers(handover_at)',
            ]

        with engine.connect() as conn:
            for raw in stmts:
                stmt = ' '.join(raw.split())
                try:
                    conn.execute(db.text(stmt))
                    conn.commit()
                except Exception as e:
                    err = str(e).lower()
                    if 'already exists' in err or 'duplicate' in err:
                        print('[SKIP]', stmt[:70])
                    else:
                        raise
        print('[OK] device_handovers table ready')


if __name__ == '__main__':
    migrate_up()
