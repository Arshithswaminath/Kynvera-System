"""
Quick script to create a default admin user
Usage: python scripts/create_default_admin.py
       python scripts/create_default_admin.py --reset-existing
"""
import argparse
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.models import db, User
from Injaaz import create_app
from common.bootstrap_security import resolve_bootstrap_admin_password


def create_default_admin(reset_existing: bool = False):
    """Create a default admin user. Password must come from DEFAULT_ADMIN_PASSWORD (or generated in non-prod)."""
    app = create_app()

    with app.app_context():
        # Default admin credentials. The password MUST be supplied via the
        # DEFAULT_ADMIN_PASSWORD environment variable in production. We refuse
        # to fall back to a well-known string so a fresh deploy cannot be taken
        # over with a public default.
        username = os.environ.get("DEFAULT_ADMIN_USERNAME", "Kynvera")
        email = os.environ.get("DEFAULT_ADMIN_EMAIL", "admin@injaaz.com")
        full_name = os.environ.get("DEFAULT_ADMIN_FULL_NAME", "System Administrator")
        try:
            password, generated = resolve_bootstrap_admin_password(
                app.config.get('FLASK_ENV', 'development')
            )
        except RuntimeError as exc:
            print(f"[ERROR] {exc}")
            return False

        # Check if admin already exists (new or legacy username)
        existing = (
            User.query.filter_by(username=username).first()
            or User.query.filter_by(username='admin').first()
        )
        if existing:
            if not reset_existing:
                print(f"[INFO] Admin user '{existing.username}' already exists — leaving credentials unchanged.")
                print("       Pass --reset-existing to rotate the password (requires DEFAULT_ADMIN_PASSWORD in production).")
                return True
            if generated:
                print("[ERROR] Refusing to reset an existing admin with a generated password. Set DEFAULT_ADMIN_PASSWORD.")
                return False
            print(f"[INFO] Admin user '{existing.username}' already exists — resetting password from DEFAULT_ADMIN_PASSWORD.")
            existing.username = username
            existing.set_password(password)
            existing.is_active = True
            existing.password_changed = False
            existing.access_hvac = True
            existing.access_civil = True
            existing.access_cleaning = True
            db.session.commit()
            print("=" * 60)
            print("[SUCCESS] Admin Password Reset!")
            print("=" * 60)
            print(f"Username: {username}")
            print(f"Email: {existing.email}")
            print("Password: (from DEFAULT_ADMIN_PASSWORD)")
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
            password_changed=False,
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
            if generated:
                print("Password: (generated — see application logs / CRITICAL line above)")
            else:
                print("Password: (from DEFAULT_ADMIN_PASSWORD)")
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
    parser = argparse.ArgumentParser(description='Create the default admin user')
    parser.add_argument(
        '--reset-existing',
        action='store_true',
        help='Rotate password for an existing admin (never uses a generated password)',
    )
    args = parser.parse_args()
    create_default_admin(reset_existing=args.reset_existing)
