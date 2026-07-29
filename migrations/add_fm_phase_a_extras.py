"""
Migration: FM Phase A+ extras — lat/lng, predictions, floor plans, webhooks, API keys, MFA, push.
Run: python migrations/add_fm_phase_a_extras.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Injaaz import create_app
from app.models import db

app = create_app()
with app.app_context():
    db.create_all()
    conn = db.engine.raw_connection()
    cursor = conn.cursor()
    dialect = db.engine.dialect.name

    def cols(table):
        if dialect == 'sqlite':
            cursor.execute(f'PRAGMA table_info({table})')
            return {row[1] for row in cursor.fetchall()}
        cursor.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
            (table,),
        )
        return {row[0] for row in cursor.fetchall()}

    asset_cols = cols('fm_assets')
    for name, typ in [('latitude', 'REAL'), ('longitude', 'REAL')]:
        if name not in asset_cols:
            try:
                cursor.execute(f'ALTER TABLE fm_assets ADD COLUMN {name} {typ}')
                print(f'Added fm_assets.{name}')
            except Exception as exc:
                print(f'Skip fm_assets.{name}: {exc}')

    user_cols = cols('users')
    for name, typ in [
        ('mfa_enabled', 'BOOLEAN DEFAULT 0'),
        ('mfa_secret', 'VARCHAR(64)'),
    ]:
        if name not in user_cols:
            try:
                cursor.execute(f'ALTER TABLE users ADD COLUMN {name} {typ}')
                print(f'Added users.{name}')
            except Exception as exc:
                print(f'Skip users.{name}: {exc}')

    conn.commit()
    conn.close()
    print('OK: FM extras tables/columns ensured.')
