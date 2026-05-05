"""
Script to create an admin user
Usage: python scripts/create_admin.py
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.models import db, User
from Injaaz import create_app

def create_admin_user(username, email, password, full_name=None):
    """Create an admin user"""
    app = create_app()
    
    with app.app_context():
        # Check if admin already exists
        existing = User.query.filter_by(username=username).first()
        if existing:
            print(f"[ERROR] User '{username}' already exists!")
            return False
        
        # Check if email is taken
        existing_email = User.query.filter_by(email=email).first()
        if existing_email:
            print(f"[ERROR] Email '{email}' is already in use!")
            return False
        
        # Create admin user
        admin = User(
            username=username,
            email=email,
            full_name=full_name or username,
            role='admin',
            is_active=True,
            access_hvac=True,  # Admins have all access
            access_civil=True,
            access_cleaning=True
        )
        admin.set_password(password)
        
        try:
            db.session.add(admin)
            db.session.commit()
            print(f"[OK] Admin user '{username}' created successfully!")
            print(f"   Email: {email}")
            print(f"   Full Name: {admin.full_name}")
            print(f"   Role: {admin.role}")
            print(f"\n[WARNING] Please save these credentials securely!")
            return True
        except Exception as e:
            db.session.rollback()
            print(f"[ERROR] Error creating admin user: {str(e)}")
            return False

if __name__ == '__main__':
    import getpass
    
    print("=" * 60)
    print("Create Admin User")
    print("=" * 60)
    print()
    
    username = input("Enter username: ").strip()
    if not username:
        print("[ERROR] Username cannot be empty!")
        sys.exit(1)
    
    email = input("Enter email: ").strip()
    if not email or '@' not in email:
        print("[ERROR] Invalid email address!")
        sys.exit(1)
    
    full_name = input("Enter full name (optional): ").strip() or None
    
    password = getpass.getpass("Enter password: ").strip()
    if len(password) < 8:
        print("[ERROR] Password must be at least 8 characters long!")
        sys.exit(1)
    
    confirm_password = getpass.getpass("Confirm password: ").strip()
    if password != confirm_password:
        print("[ERROR] Passwords do not match!")
        sys.exit(1)
    
    print()
    create_admin_user(username, email, password, full_name)

