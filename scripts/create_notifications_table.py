"""
Create Notifications Table
Run this script to add the notifications table to the database
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.models import db, Notification
from Injaaz import create_app

def create_notifications_table():
    """Create the notifications table if it doesn't exist"""
    app = create_app()
    
    with app.app_context():
        try:
            # Check if notifications table exists
            result = db.session.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='notifications'"
            )).fetchone()
            
            if result:
                print("[OK] Notifications table already exists")
            else:
                # Create the table using SQLAlchemy
                Notification.__table__.create(db.engine)
                print("[OK] Created notifications table")
            
            db.session.commit()
            print("\n[SUCCESS] Database update complete!")
            
        except Exception as e:
            print(f"\n[ERROR] Failed to create table: {e}")
            db.session.rollback()
            return False
    
    return True

if __name__ == '__main__':
    create_notifications_table()
