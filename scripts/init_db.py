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
        admin = User.query.filter_by(username='admin').first()
        
        if not admin:
            print("\nCreating default admin user...")
            admin = User(
                username='admin',
                email='admin@injaaz.com',
                full_name='System Administrator',
                role='admin',
                is_active=True
            )
            admin.set_password('Admin@123')  # Change this immediately!
            
            db.session.add(admin)
            db.session.commit()
            
            print("✅ Default admin user created!")
            print("   Username: admin")
            print("   Password: Admin@123")
            print("   ⚠️  IMPORTANT: Change this password immediately after first login!")
        else:
            print("\nℹ️  Admin user already exists, skipping creation")
        
        print("\n✅ Database initialization complete!")
        print("\nYou can now run the application with: python Injaaz.py")

if __name__ == '__main__':
    init_database()
