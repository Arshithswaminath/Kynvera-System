"""
Check that an admin user exists. Create or reset only when DEFAULT_ADMIN_PASSWORD is set.

Usage:
  DEFAULT_ADMIN_PASSWORD='...' python scripts/fix_admin_user.py
  FORCE_ADMIN_RESET=1 DEFAULT_ADMIN_PASSWORD='...' python scripts/fix_admin_user.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Injaaz import create_app
from app.models import db, User
from common.password_admin import require_env_password

DEFAULT_ADMIN_USERNAME = 'Kynvera'


def fix_admin_user():
    app = create_app()

    with app.app_context():
        try:
            db.engine.connect()
            print("[OK] Database connection successful!")
        except Exception as e:
            print(f"[ERROR] Database connection failed: {e}")
            return False

        try:
            password = require_env_password('DEFAULT_ADMIN_PASSWORD')
        except RuntimeError as exc:
            print(f"[ERROR] {exc}")
            return False

        force_reset = os.environ.get('FORCE_ADMIN_RESET', '').lower() in ('1', 'true', 'yes')
        admin = (
            User.query.filter_by(username=DEFAULT_ADMIN_USERNAME).first()
            or User.query.filter_by(username='admin').first()
        )

        if not admin:
            print("\n[INFO] Admin user does not exist. Creating...")
            admin = User(
                username=DEFAULT_ADMIN_USERNAME,
                email='admin@injaaz.com',
                full_name='System Administrator',
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
                print("[OK] Admin user created.")
            except Exception as e:
                db.session.rollback()
                print(f"[ERROR] Failed to create admin user: {e}")
                return False
        else:
            print(f"\n[OK] Admin user exists: {admin.username}")
            if not force_reset:
                print("[INFO] Password left unchanged. Set FORCE_ADMIN_RESET=1 to apply DEFAULT_ADMIN_PASSWORD.")
                return True
            admin.username = DEFAULT_ADMIN_USERNAME
            admin.set_password(password)
            admin.is_active = True
            admin.password_changed = False
            db.session.commit()
            print("[OK] Admin password reset from DEFAULT_ADMIN_PASSWORD.")

        print(f"Username: {DEFAULT_ADMIN_USERNAME}")
        print("Password: (from DEFAULT_ADMIN_PASSWORD)")
        return True


if __name__ == '__main__':
    try:
        success = fix_admin_user()
        if not success:
            sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        sys.exit(1)
