"""
Migration: add notes column to hiring_documents (offer-letter comment, etc.).
Run: python migrations/add_hiring_document_notes.py
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

    doc_cols = cols('hiring_documents')
    if 'notes' not in doc_cols:
        try:
            cursor.execute('ALTER TABLE hiring_documents ADD COLUMN notes TEXT')
            print('Added hiring_documents.notes')
        except Exception as exc:
            print(f'Skip hiring_documents.notes: {exc}')
    else:
        print('hiring_documents.notes already exists')

    conn.commit()
    conn.close()
    print('OK: hiring_documents.notes ensured.')
