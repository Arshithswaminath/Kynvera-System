"""
Database Migration: Add New Workflow Fields
Adds support for new 5-stage approval workflow

Run this migration:
    python migrations/add_new_workflow_fields.py
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Injaaz import create_app
from app.models import db
import logging

logger = logging.getLogger(__name__)

def migrate_up():
    """Add new workflow columns to submissions table"""
    app = create_app()
    
    with app.app_context():
        try:
            # Get database engine
            engine = db.engine
            
            # List of columns to add
            columns_to_add = [
                "ALTER TABLE submissions ADD COLUMN operations_manager_id INTEGER",
                "ALTER TABLE submissions ADD COLUMN business_dev_id INTEGER",
                "ALTER TABLE submissions ADD COLUMN procurement_id INTEGER",
                "ALTER TABLE submissions ADD COLUMN general_manager_id INTEGER",
                "ALTER TABLE submissions ADD COLUMN operations_manager_notified_at TIMESTAMP",
                "ALTER TABLE submissions ADD COLUMN operations_manager_approved_at TIMESTAMP",
                "ALTER TABLE submissions ADD COLUMN business_dev_notified_at TIMESTAMP",
                "ALTER TABLE submissions ADD COLUMN business_dev_approved_at TIMESTAMP",
                "ALTER TABLE submissions ADD COLUMN procurement_notified_at TIMESTAMP",
                "ALTER TABLE submissions ADD COLUMN procurement_approved_at TIMESTAMP",
                "ALTER TABLE submissions ADD COLUMN general_manager_notified_at TIMESTAMP",
                "ALTER TABLE submissions ADD COLUMN general_manager_approved_at TIMESTAMP",
                "ALTER TABLE submissions ADD COLUMN operations_manager_comments TEXT",
                "ALTER TABLE submissions ADD COLUMN business_dev_comments TEXT",
                "ALTER TABLE submissions ADD COLUMN procurement_comments TEXT",
                "ALTER TABLE submissions ADD COLUMN general_manager_comments TEXT",
                "ALTER TABLE submissions ADD COLUMN rejection_stage VARCHAR(40)",
                "ALTER TABLE submissions ADD COLUMN rejection_reason TEXT",
                "ALTER TABLE submissions ADD COLUMN rejected_at TIMESTAMP",
                "ALTER TABLE submissions ADD COLUMN rejected_by_id INTEGER",
            ]
            
            # Add columns one by one
            with engine.connect() as conn:
                for sql in columns_to_add:
                    try:
                        conn.execute(db.text(sql))
                        conn.commit()
                        col_name = sql.split('ADD COLUMN ')[1].split(' ')[0]
                        print(f"[OK] Added column: {col_name}")
                    except Exception as col_error:
                        # Column might already exist
                        if 'duplicate column' in str(col_error).lower() or 'already exists' in str(col_error).lower():
                            col_name = sql.split('ADD COLUMN ')[1].split(' ')[0]
                            print(f"[SKIP] Column already exists: {col_name}")
                        else:
                            print(f"[ERROR] Failed to add column: {col_error}")
                            raise
            
            print("\n[SUCCESS] Migration completed successfully!")
            print("\nNext steps:")
            print("1. Update user designations via admin panel or SQL")
            print("2. Restart the application")
            print("3. Test the new workflow system")
            
        except Exception as e:
            print(f"\n[FAILED] Migration failed: {e}")
            raise

def migrate_down():
    """Remove new workflow columns (rollback)"""
    app = create_app()
    
    with app.app_context():
        try:
            print("\n[WARNING] This will remove all new workflow columns!")
            print("Press Ctrl+C to cancel, or wait 5 seconds to continue...")
            
            import time
            time.sleep(5)
            
            engine = db.engine
            
            columns_to_remove = [
                "operations_manager_id",
                "business_dev_id",
                "procurement_id",
                "general_manager_id",
                "operations_manager_notified_at",
                "operations_manager_approved_at",
                "business_dev_notified_at",
                "business_dev_approved_at",
                "procurement_notified_at",
                "procurement_approved_at",
                "general_manager_notified_at",
                "general_manager_approved_at",
                "operations_manager_comments",
                "business_dev_comments",
                "procurement_comments",
                "general_manager_comments",
                "rejection_stage",
                "rejection_reason",
                "rejected_at",
                "rejected_by_id",
            ]
            
            # For SQLite, we need to recreate the table without these columns
            # This is a simplified rollback - in production, use proper migrations
            print("[INFO] Rollback not fully implemented for SQLite")
            print("[INFO] Please restore from database backup if needed")
            
        except KeyboardInterrupt:
            print("\n[CANCELLED] Rollback cancelled by user")
        except Exception as e:
            print(f"\n[FAILED] Rollback failed: {e}")
            raise

if __name__ == '__main__':
    import sys
    
    print("=" * 60)
    print("Database Migration: New 5-Stage Workflow System")
    print("=" * 60)
    print()
    
    if len(sys.argv) > 1 and sys.argv[1] == 'down':
        print("Running ROLLBACK migration...")
        print()
        migrate_down()
    else:
        print("Running UP migration...")
        print()
        migrate_up()
