"""
Migration: create hiring_offer_letters (Offer Letters / LOI register).
Also ensures not_accepted exists for stepwise candidate outcome.
Run: python migrations/add_hiring_offer_letters.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Injaaz import create_app
from app.models import db

app = create_app()
with app.app_context():
    db.create_all()
    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    if 'hiring_offer_letters' not in tables:
        print('WARN: hiring_offer_letters was not created.')
        raise SystemExit(1)
    cols = {c['name'] for c in inspector.get_columns('hiring_offer_letters')}
    if 'not_accepted' not in cols:
        with db.engine.begin() as conn:
            conn.execute(text(
                'ALTER TABLE hiring_offer_letters '
                'ADD COLUMN not_accepted BOOLEAN DEFAULT FALSE NOT NULL'
            ))
        print('OK: added not_accepted column.')
    print('OK: hiring_offer_letters exists.')

