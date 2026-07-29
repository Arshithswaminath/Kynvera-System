"""
Migration: create fm_assets + ticket_triage_logs tables and add Ticket.asset_id / sla_hours.
Run once: python migrations/add_fm_assets.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Injaaz import create_app
from app.models import db

app = create_app()
with app.app_context():
    db.create_all()

    # Additive columns on tickets (SQLite / Postgres safe)
    conn = db.engine.raw_connection()
    cursor = conn.cursor()
    dialect = db.engine.dialect.name

    def existing_columns(table):
        if dialect == 'sqlite':
            cursor.execute(f'PRAGMA table_info({table})')
            return {row[1] for row in cursor.fetchall()}
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = %s",
            (table,),
        )
        return {row[0] for row in cursor.fetchall()}

    cols = existing_columns('tickets')
    additions = [
        ('asset_id', 'INTEGER'),
        ('sla_hours', 'INTEGER'),
    ]
    for name, col_type in additions:
        if name not in cols:
            try:
                cursor.execute(f'ALTER TABLE tickets ADD COLUMN {name} {col_type}')
                print(f'Added tickets.{name}')
            except Exception as exc:
                print(f'Could not add tickets.{name}: {exc}')
    conn.commit()
    conn.close()
    print('OK: fm_assets / ticket_triage_logs created (if missing); ticket columns ensured.')
