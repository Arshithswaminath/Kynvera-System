"""
Database initialization script
Creates all tables and adds default admin user
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Injaaz import create_app
from app.models import db, User
from common.bootstrap_security import resolve_bootstrap_admin_password

def init_database():
    """Initialize database and create tables"""
    import time
    
    app = create_app()
    
    with app.app_context():
        # Retry logic for Render database connection
        max_retries = 5
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                print(f"Attempting to connect to database (attempt {attempt + 1}/{max_retries})...")
                # Test connection first
                db.engine.connect()
                print("✅ Database connection successful!")
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"⚠️  Connection failed: {e}. Retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    print(f"❌ Failed to connect after {max_retries} attempts: {e}")
                    raise
        
        print("Creating database tables...")
        db.create_all()
        print("✅ Database tables created successfully!")
        
        # Check if admin user exists
        admin = (
            User.query.filter_by(username='Kynvera').first()
            or User.query.filter_by(username='admin').first()
        )
        
        if not admin:
            print("\nCreating default admin user...")
            try:
                password, generated = resolve_bootstrap_admin_password(
                    app.config.get('FLASK_ENV', 'development')
                )
            except RuntimeError as exc:
                print(f"❌ {exc}")
                raise
            admin = User(
                username=os.environ.get('DEFAULT_ADMIN_USERNAME', 'Kynvera'),
                email=os.environ.get('DEFAULT_ADMIN_EMAIL', 'admin@injaaz.com'),
                full_name=os.environ.get('DEFAULT_ADMIN_FULL_NAME', 'System Administrator'),
                role='admin',
                is_active=True,
                password_changed=False,
            )
            admin.set_password(password)
            
            db.session.add(admin)
            db.session.commit()
            
            print("✅ Default admin user created!")
            print(f"   Username: {admin.username}")
            if generated:
                print("   Password: (generated — see CRITICAL log line above; change after first login)")
            else:
                print("   Password: (from DEFAULT_ADMIN_PASSWORD; change after first login)")
        else:
            print("\nℹ️  Admin user already exists, skipping creation")
        
        print("\n✅ Database initialization complete!")
        print("\nYou can now run the application with: python Injaaz.py")

if __name__ == '__main__':
    init_database()
