"""
JSON to Database Migration Script
Migrates existing submissions and jobs from JSON files to PostgreSQL
"""
import sys
import os
import json
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Injaaz import create_app
from app.models import db, Submission, Job, File, User
from config import GENERATED_DIR, UPLOADS_DIR, JOBS_DIR


def migrate_submissions():
    """Migrate submission JSON files to database"""
    submissions_dir = os.path.join(GENERATED_DIR, 'submissions')
    
    if not os.path.exists(submissions_dir):
        print("No submissions directory found")
        return 0
    
    count = 0
    errors = 0
    
    for filename in os.listdir(submissions_dir):
        if not filename.endswith('.json'):
            continue
        
        filepath = os.path.join(submissions_dir, filename)
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Extract submission ID from filename (e.g., sub_abc123.json -> sub_abc123)
            submission_id = filename.replace('.json', '')
            
            # Check if already migrated
            if Submission.query.filter_by(submission_id=submission_id).first():
                print(f"Skipping {submission_id} (already migrated)")
                continue
            
            # Determine module type from form_type or other fields
            module_type = data.get('form_type', 'unknown')
            if module_type == 'unknown':
                # Try to infer from data
                if 'hvac' in str(data).lower() or 'mep' in str(data).lower():
                    module_type = 'hvac_mep'
                elif 'civil' in str(data).lower():
                    module_type = 'civil'
                elif 'cleaning' in str(data).lower():
                    module_type = 'cleaning'
            
            # Parse visit date if available
            visit_date = None
            if data.get('visitDate'):
                try:
                    visit_date = datetime.strptime(data['visitDate'], '%Y-%m-%d').date()
                except:
                    pass
            
            # Create submission record
            submission = Submission(
                submission_id=submission_id,
                user_id=None,  # No user association for legacy data
                module_type=module_type,
                site_name=data.get('siteName', data.get('site_name')),
                visit_date=visit_date,
                status='completed',  # Assume old submissions are completed
                form_data=data
            )
            
            db.session.add(submission)
            db.session.flush()  # Get submission.id
            
            # Migrate associated files (photos, signatures)
            migrate_submission_files(submission, data)
            
            count += 1
            print(f"✅ Migrated submission: {submission_id}")
            
        except Exception as e:
            errors += 1
            print(f"❌ Error migrating {filename}: {str(e)}")
    
    db.session.commit()
    return count, errors


def migrate_submission_files(submission, data):
    """Migrate files associated with a submission"""
    # Migrate photos
    photos = data.get('photos', [])
    if isinstance(photos, list):
        for idx, photo in enumerate(photos):
            if isinstance(photo, dict):
                url = photo.get('url')
                if url:
                    file_record = File(
                        file_id=f"photo_{submission.submission_id}_{idx}",
                        submission_id=submission.id,
                        file_type='photo',
                        filename=photo.get('filename', f'photo_{idx}.jpg'),
                        file_path=photo.get('path'),
                        cloud_url=url,
                        is_cloud=photo.get('is_cloud', True),
                        mime_type='image/jpeg'
                    )
                    db.session.add(file_record)
    
    # Migrate signatures
    for sig_key in ['supervisorSignature', 'inspectorSignature', 'contractorSignature']:
        sig_data = data.get(sig_key)
        if isinstance(sig_data, dict):
            url = sig_data.get('url')
            if url:
                file_record = File(
                    file_id=f"sig_{submission.submission_id}_{sig_key}",
                    submission_id=submission.id,
                    file_type='signature',
                    filename=sig_data.get('filename', f'{sig_key}.png'),
                    file_path=sig_data.get('path'),
                    cloud_url=url,
                    is_cloud=sig_data.get('is_cloud', True),
                    mime_type='image/png'
                )
                db.session.add(file_record)


def migrate_jobs():
    """Migrate job JSON files to database"""
    if not os.path.exists(JOBS_DIR):
        print("No jobs directory found")
        return 0
    
    count = 0
    errors = 0
    
    for filename in os.listdir(JOBS_DIR):
        if not filename.endswith('.json'):
            continue
        
        filepath = os.path.join(JOBS_DIR, filename)
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            job_id = filename.replace('.json', '')
            
            # Check if already migrated
            if Job.query.filter_by(job_id=job_id).first():
                print(f"Skipping {job_id} (already migrated)")
                continue
            
            # Find associated submission
            sub_id = data.get('submission_id')
            submission = None
            if sub_id:
                submission = Submission.query.filter_by(submission_id=sub_id).first()
            
            if not submission:
                print(f"Warning: No submission found for job {job_id}, skipping")
                continue
            
            # Parse timestamps
            started_at = None
            completed_at = None
            
            if data.get('started_at'):
                try:
                    started_at = datetime.fromisoformat(data['started_at'])
                except:
                    pass
            
            if data.get('completed_at'):
                try:
                    completed_at = datetime.fromisoformat(data['completed_at'])
                except:
                    pass
            
            # Create job record
            job = Job(
                job_id=job_id,
                submission_id=submission.id,
                status=data.get('state', 'completed'),
                progress=data.get('progress', 100),
                result_data=data.get('result'),
                error_message=data.get('error'),
                started_at=started_at,
                completed_at=completed_at
            )
            
            db.session.add(job)
            count += 1
            print(f"✅ Migrated job: {job_id}")
            
        except Exception as e:
            errors += 1
            print(f"❌ Error migrating {filename}: {str(e)}")
    
    db.session.commit()
    return count, errors


def main():
    """Run migration"""
    app = create_app()
    
    with app.app_context():
        print("=" * 60)
        print("JSON to Database Migration")
        print("=" * 60)
        
        # Ensure tables exist
        print("\nChecking database tables...")
        db.create_all()
        print("✅ Database ready")
        
        # Migrate submissions
        print("\n--- Migrating Submissions ---")
        sub_count, sub_errors = migrate_submissions()
        print(f"\nSubmissions migrated: {sub_count}")
        print(f"Errors: {sub_errors}")
        
        # Migrate jobs
        print("\n--- Migrating Jobs ---")
        job_count, job_errors = migrate_jobs()
        print(f"\nJobs migrated: {job_count}")
        print(f"Errors: {job_errors}")
        
        print("\n" + "=" * 60)
        print("Migration Complete!")
        print(f"Total submissions: {sub_count}")
        print(f"Total jobs: {job_count}")
        print(f"Total errors: {sub_errors + job_errors}")
        print("=" * 60)


if __name__ == '__main__':
    main()
