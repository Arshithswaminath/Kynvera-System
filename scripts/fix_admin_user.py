"""
Fix/Reset Admin User Script
This script checks if admin user exists and resets credentials to Kynvera / Arshith&Taha@2026
Usage: python scripts/fix_admin_user.py
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Injaaz import create_app
from app.models import db, User

ADMIN_USERNAME = 'Kynvera'
ADMIN_PASSWORD = 'Arshith&Taha@2026'

def fix_admin_user():
    """Check and fix admin user"""
    app = create_app()
    
    with app.app_context():
        try:
            # Test database connection
            db.engine.connect()
            print("[OK] Database connection successful!")
        except Exception as e:
            print(f"[ERROR] Database connection failed: {e}")
            return False
        
        # Check if admin user exists
        admin = (
            User.query.filter_by(role='admin').first()
            or User.query.filter_by(username=ADMIN_USERNAME).first()
            or User.query.filter_by(username='admin').first()
        )
        
        if not admin:
            print("\n[WARNING] Admin user does not exist!")
            print("Creating admin user...")
            
            admin = User(
                username=ADMIN_USERNAME,
                email='admin@injaaz.com',
                full_name='System Administrator',
                role='admin',
                is_active=True,
                access_hvac=True,
                access_civil=True,
                access_cleaning=True,
                password_changed=True,
                admin_visible_password=ADMIN_PASSWORD,
            )
            admin.set_password(ADMIN_PASSWORD)
            
            try:
                db.session.add(admin)
                db.session.commit()
                print("[OK] Admin user created successfully!")
            except Exception as e:
                db.session.rollback()
                print(f"[ERROR] Failed to create admin user: {e}")
                return False
        else:
            print("\n[OK] Admin user exists!")
            print(f"   Username: {admin.username}")
            print(f"   Email: {admin.email}")
            print(f"   Role: {admin.role}")
            print(f"   Is Active: {admin.is_active}")
            
            print(f"\n[INFO] Updating credentials to '{ADMIN_USERNAME}'...")
            admin.username = ADMIN_USERNAME
            admin.set_password(ADMIN_PASSWORD)
            admin.is_active = True
            admin.password_changed = True
            admin.admin_visible_password = ADMIN_PASSWORD
            admin.password_locked = False
            admin.access_hvac = True
            admin.access_civil = True
            admin.access_cleaning = True
            
            try:
                db.session.commit()
                print("[OK] Credentials updated successfully!")
            except Exception as e:
                db.session.rollback()
                print(f"[ERROR] Failed to update credentials: {e}")
                return False
        
        # Verify the password works
        print("\n[INFO] Verifying password...")
        if admin.check_password(ADMIN_PASSWORD):
            print("[OK] Password verification successful!")
        else:
            print("[ERROR] Password verification failed!")
            return False
        
        print("\n" + "=" * 60)
        print("[SUCCESS] Admin User Setup Complete!")
        print("=" * 60)
        print(f"Username: {ADMIN_USERNAME}")
        print(f"Password: {ADMIN_PASSWORD}")
        print(f"Email: {admin.email}")
        print("=" * 60)
        
        return True

if __name__ == '__main__':
    try:
        success = fix_admin_user()
        if not success:
            print("\n[ERROR] Failed to fix admin user. Check the errors above.")
            sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
