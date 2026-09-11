"""
Create a default admin user.

The password MUST be supplied via DEFAULT_ADMIN_PASSWORD. This script never
falls back to a well-known string.

Usage:
  DEFAULT_ADMIN_PASSWORD='...' python scripts/create_default_admin.py
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.models import db, User
from Injaaz import create_app
from common.password_admin import require_env_password


def create_default_admin():
    app = create_app()

    with app.app_context():
        username = os.environ.get("DEFAULT_ADMIN_USERNAME", "Kynvera")
        email = os.environ.get("DEFAULT_ADMIN_EMAIL", "admin@injaaz.com")
        try:
            password = require_env_password("DEFAULT_ADMIN_PASSWORD")
        except RuntimeError as exc:
            print(f"[ERROR] {exc}")
            return False
        full_name = os.environ.get("DEFAULT_ADMIN_FULL_NAME", "System Administrator")
        force_reset = os.environ.get("FORCE_ADMIN_RESET", "").lower() in ("1", "true", "yes")

        existing = (
            User.query.filter_by(username=username).first()
            or User.query.filter_by(username='admin').first()
        )
        if existing:
            if not force_reset:
                print(f"[INFO] Admin user '{existing.username}' already exists. Not resetting password.")
                print("       Set FORCE_ADMIN_RESET=1 to overwrite the password from DEFAULT_ADMIN_PASSWORD.")
                return True
            existing.username = username
            existing.set_password(password)
            existing.is_active = True
            existing.password_changed = False
            existing.access_hvac = True
            existing.access_civil = True
            existing.access_cleaning = True
            db.session.commit()
            print("[SUCCESS] Admin password reset from DEFAULT_ADMIN_PASSWORD.")
            print(f"Username: {username}")
            return True

        existing_email = User.query.filter_by(email=email).first()
        if existing_email:
            email = f"admin{User.query.count() + 1}@injaaz.com"

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
            print("[SUCCESS] Default admin user created.")
            print(f"Username: {username}")
            print(f"Email: {email}")
            print("Password: (from DEFAULT_ADMIN_PASSWORD — change it after first sign-in)")
            return True
        except Exception as e:
            db.session.rollback()
            print(f"[ERROR] Error creating admin user: {str(e)}")
            return False


if __name__ == '__main__':
    ok = create_default_admin()
    sys.exit(0 if ok else 1)
