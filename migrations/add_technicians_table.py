"""
Migration: create technicians table
Run once: python migrations/add_technicians_table.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Injaaz import create_app
from app.models import db

app = create_app()
with app.app_context():
    db.create_all()
    print("✅ technicians table created (if it didn't exist).")
