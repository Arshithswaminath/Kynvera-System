"""
Script to create HR and Procurement user accounts
Run with: python scripts/create_hr_procurement_users.py
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Injaaz import create_app
from app.models import db, User
from sqlalchemy import text

def create_users():
    app = create_app()
    
    with app.app_context():
        # First, ensure the new columns exist
        try:
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            columns = [col['name'] for col in inspector.get_columns('users')]
            
            if 'access_hr' not in columns:
                print("Adding access_hr column...")
                with db.engine.begin() as conn:
                    conn.execute(text("ALTER TABLE users ADD COLUMN access_hr BOOLEAN DEFAULT 0"))
                print("[OK] Added access_hr column")
            
            if 'access_procurement_module' not in columns:
                print("Adding access_procurement_module column...")
                with db.engine.begin() as conn:
                    conn.execute(text("ALTER TABLE users ADD COLUMN access_procurement_module BOOLEAN DEFAULT 0"))
                print("[OK] Added access_procurement_module column")
        except Exception as e:
            print(f"Note: Column check/add: {e}")
        
        # Create HR user
        hr_user = User.query.filter_by(username='hr_manager').first()
        if not hr_user:
            print("Creating HR Manager user...")
            hr_user = User(
                username='hr_manager',
                email='hr@injaaz.ae',
                full_name='HR Manager',
                role='user',
                designation='hr_manager',
                is_active=True,
                access_hvac=False,
                access_civil=False,
                access_cleaning=False,
            )
            # Set HR access
            hr_user.access_hr = True
            hr_user.access_procurement_module = False
            hr_user.set_password('HRInjaaz@2026')
            hr_user.password_changed = False
            db.session.add(hr_user)
            db.session.commit()
            print("[OK] HR Manager user created")
            print("   Username: hr_manager")
            print("   Password: HRInjaaz@2026")
        else:
            # Update existing user to have HR access
            hr_user.access_hr = True
            db.session.commit()
            print("[OK] HR Manager user already exists - updated access")
            print("   Username: hr_manager")
        
        # Create Procurement user
        proc_user = User.query.filter_by(username='procurement_manager').first()
        if not proc_user:
            print("\nCreating Procurement Manager user...")
            proc_user = User(
                username='procurement_manager',
                email='procurement@injaaz.ae',
                full_name='Procurement Manager',
                role='user',
                designation='procurement',
                is_active=True,
                access_hvac=False,
                access_civil=False,
                access_cleaning=False,
            )
            # Set Procurement access
            proc_user.access_hr = False
            proc_user.access_procurement_module = True
            proc_user.set_password('ProcInjaaz@2026')
            proc_user.password_changed = False
            db.session.add(proc_user)
            db.session.commit()
            print("[OK] Procurement Manager user created")
            print("   Username: procurement_manager")
            print("   Password: ProcInjaaz@2026")
        else:
            # Update existing user to have procurement access
            proc_user.access_procurement_module = True
            db.session.commit()
            print("[OK] Procurement Manager user already exists - updated access")
            print("   Username: procurement_manager")
        
        print("\n" + "="*50)
        print("USER ACCOUNTS CREATED:")
        print("="*50)
        print("\nHR MODULE:")
        print("   Username: hr_manager")
        print("   Password: HRInjaaz@2026")
        print("\nPROCUREMENT MODULE:")
        print("   Username: procurement_manager")
        print("   Password: ProcInjaaz@2026")
        print("\nPlease change these passwords after first login!")
        print("="*50)

if __name__ == '__main__':
    create_users()
