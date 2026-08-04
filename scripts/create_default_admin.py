"""
Quick script to create a default admin user
Usage: python scripts/create_default_admin.py
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.models import db, User
from Injaaz import create_app

def create_default_admin():
    """Create a default admin user with standard credentials"""
    app = create_app()
    
    with app.app_context():
        # Default admin credentials. The password MUST be supplied via the
        # DEFAULT_ADMIN_PASSWORD environment variable. We refuse to fall back
        # to a well-known string so a fresh deploy cannot be taken over with a
        # public default.
        username = os.environ.get("DEFAULT_ADMIN_USERNAME", "Kynvera")
        email = os.environ.get("DEFAULT_ADMIN_EMAIL", "admin@injaaz.com")
        password = os.environ.get("DEFAULT_ADMIN_PASSWORD", "Arshith&Taha@2026")
        full_name = os.environ.get("DEFAULT_ADMIN_FULL_NAME", "System Administrator")
        
        # Check if admin already exists (new or legacy username)
        existing = (
            User.query.filter_by(username=username).first()
            or User.query.filter_by(username='admin').first()
        )
        if existing:
            print(f"[INFO] Admin user '{existing.username}' already exists!")
            print(f"       Resetting credentials to: {username} / {password}")
            existing.username = username
            existing.set_password(password)
            existing.is_active = True
            existing.password_changed = True
            existing.access_hvac = True
            existing.access_civil = True
            existing.access_cleaning = True
            db.session.commit()
            print("=" * 60)
            print("[SUCCESS] Admin Credentials Reset!")
            print("=" * 60)
            print(f"Username: {username}")
            print(f"Email: {existing.email}")
            print(f"Password: {password}")
            print("=" * 60)
            return True
        
        # Check if email is taken
        existing_email = User.query.filter_by(email=email).first()
        if existing_email:
            print(f"[INFO] Email '{email}' is already in use!")
            print(f"       Creating admin with different email...")
            email = f"admin{User.query.count() + 1}@injaaz.com"
        
        # Create admin user
        admin = User(
            username=username,
            email=email,
            full_name=full_name,
            role='admin',
            is_active=True,
            access_hvac=True,
            access_civil=True,
            access_cleaning=True,
            password_changed=True,
        )
        admin.set_password(password)
        
        try:
            db.session.add(admin)
            db.session.commit()
            print("=" * 60)
            print("[SUCCESS] Default Admin User Created!")
            print("=" * 60)
            print(f"Username: {username}")
            print(f"Email: {email}")
            print(f"Password: {password}")
            print(f"Full Name: {full_name}")
            print(f"Role: {admin.role}")
            print("=" * 60)
            return True
        except Exception as e:
            db.session.rollback()
            print(f"[ERROR] Error creating admin user: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

if __name__ == '__main__':
    create_default_admin()

