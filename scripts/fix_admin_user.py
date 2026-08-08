"""
Fix/Reset Admin User Script

Creates the admin user if missing, or resets its password when explicitly requested.
Never falls back to a well-known hardcoded password.

Usage:
  DEFAULT_ADMIN_PASSWORD='...' python scripts/fix_admin_user.py
  DEFAULT_ADMIN_PASSWORD='...' python scripts/fix_admin_user.py --reset
"""
import argparse
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Injaaz import create_app
from app.models import db, User
from common.bootstrap_security import resolve_bootstrap_admin_password

DEFAULT_ADMIN_USERNAME = os.environ.get('DEFAULT_ADMIN_USERNAME', 'Kynvera')


def fix_admin_user(reset: bool = False):
    """Check and optionally fix admin user"""
    app = create_app()

    with app.app_context():
        try:
            # Test database connection
            db.engine.connect()
            print("[OK] Database connection successful!")
        except Exception as e:
            print(f"[ERROR] Database connection failed: {e}")
            return False

        try:
            password, generated = resolve_bootstrap_admin_password(
                app.config.get('FLASK_ENV', 'development')
            )
        except RuntimeError as exc:
            print(f"[ERROR] {exc}")
            return False

        # Check if admin user exists (new or legacy username)
        admin = (
            User.query.filter_by(username=DEFAULT_ADMIN_USERNAME).first()
            or User.query.filter_by(username='admin').first()
        )

        if not admin:
            print("\n[WARNING] Admin user does not exist!")
            print("Creating admin user...")

            admin = User(
                username=DEFAULT_ADMIN_USERNAME,
                email=os.environ.get('DEFAULT_ADMIN_EMAIL', 'admin@injaaz.com'),
                full_name=os.environ.get('DEFAULT_ADMIN_FULL_NAME', 'System Administrator'),
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

            if not reset:
                print("\n[INFO] Leaving credentials unchanged. Pass --reset to rotate the password.")
                return True

            if generated:
                print("[ERROR] Refusing to reset an existing admin with a generated password. Set DEFAULT_ADMIN_PASSWORD.")
                return False

            print(f"\n[INFO] Resetting credentials for '{DEFAULT_ADMIN_USERNAME}' from DEFAULT_ADMIN_PASSWORD...")
            admin.username = DEFAULT_ADMIN_USERNAME
            admin.set_password(password)
            admin.is_active = True
            admin.password_changed = False
            admin.access_hvac = True
            admin.access_civil = True
            admin.access_cleaning = True

            try:
                db.session.commit()
                print("[OK] Credentials reset successfully!")
            except Exception as e:
                db.session.rollback()
                print(f"[ERROR] Failed to reset credentials: {e}")
                return False

        # Verify the password works
        print("\n[INFO] Verifying password...")
        if admin.check_password(password):
            print("[OK] Password verification successful!")
        else:
            print("[ERROR] Password verification failed!")
            return False

        print("\n" + "=" * 60)
        print("[SUCCESS] Admin User Setup Complete!")
        print("=" * 60)
        print(f"Username: {DEFAULT_ADMIN_USERNAME}")
        if generated:
            print("Password: (generated — see CRITICAL log output)")
        else:
            print("Password: (from DEFAULT_ADMIN_PASSWORD)")
        print(f"Email: {admin.email}")
        print("=" * 60)

        return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Create or reset the default admin user')
    parser.add_argument('--reset', action='store_true', help='Reset password for an existing admin')
    args = parser.parse_args()
    try:
        success = fix_admin_user(reset=args.reset)
        if not success:
            print("\n[ERROR] Failed to fix admin user. Check the errors above.")
            sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
