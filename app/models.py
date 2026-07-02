"""
Database Models for Injaaz App
SQLAlchemy ORM models for PostgreSQL/SQLite
"""
import json
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from sqlalchemy import JSON

from common.datetime_utils import naive_utc_isoformat_z

db = SQLAlchemy()
bcrypt = Bcrypt()


def _utcnow():
    """Naive UTC datetime for SQLAlchemy column defaults (timezone-unaware columns)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(db.Model):
    """User accounts with role-based access"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120))
    role = db.Column(db.String(20), default='user')  # 'admin', 'user'
    designation = db.Column(db.String(30), default=None)  # 'supervisor', 'operations_manager', 'business_development', 'procurement', 'general_manager'
    is_active = db.Column(db.Boolean, default=True)
    password_changed = db.Column(db.Boolean, default=False)  # Track if password was changed from default
    default_signature = db.Column(db.Text, default=None)  # Base64 data URL for default signature
    default_comment = db.Column(db.Text, default=None)  # Default comment for approvals
    # Module access permissions (admin has access to all by default)
    access_hvac = db.Column(db.Boolean, default=False)  # HVAC&MEP form access
    access_civil = db.Column(db.Boolean, default=False)  # Civil works form access
    access_cleaning = db.Column(db.Boolean, default=False)  # Cleaning form access
    access_hr = db.Column(db.Boolean, default=False)  # HR module access
    access_procurement_module = db.Column(db.Boolean, default=False)  # Procurement module access
    access_business_development = db.Column(db.Boolean, default=False)  # BD email + inspection BD reviewer (when no conflicting designation)
    access_report_generation = db.Column(db.Boolean, default=False)  # MMR / Report Generation hub
    access_submitted_forms = db.Column(db.Boolean, default=False)  # "My submitted forms" workflow hub
    access_ticketing = db.Column(db.Boolean, default=False)  # Ticketing / Work Order module
    access_operations = db.Column(db.Boolean, default=False)  # Operations module (Over Time + Trading Invoices)
    access_operations_manage = db.Column(db.Boolean, default=False)  # Operations: full access (create/edit) vs view-only
    created_at = db.Column(db.DateTime, default=_utcnow)
    last_login = db.Column(db.DateTime)
    # First day with the company (for tenure on dashboard); editable in Profile / admin Manage profile
    employment_start_date = db.Column(db.Date, nullable=True)
    # HR / org fields (distinct from workflow `designation`; set by admin, visible on profile)
    job_designation = db.Column(db.String(160), nullable=True)
    # Project the user is assigned to (collected at self-registration)
    assigned_project = db.Column(db.String(160), nullable=True)
    # Mobile number (collected at self-registration)
    phone = db.Column(db.String(40), nullable=True)
    annual_leave_days = db.Column(db.Integer, nullable=True)
    other_leave_days = db.Column(db.Integer, nullable=True)
    reporting_manager_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Relationships
    submissions = db.relationship('Submission', foreign_keys='Submission.user_id', backref='user', lazy='dynamic')
    supervised_submissions = db.relationship('Submission', foreign_keys='Submission.supervisor_id', backref='supervisor', lazy='dynamic')
    ops_manager_submissions = db.relationship('Submission', foreign_keys='Submission.operations_manager_id', backref='operations_manager', lazy='dynamic')
    business_dev_submissions = db.relationship('Submission', foreign_keys='Submission.business_dev_id', backref='business_dev', lazy='dynamic')
    procurement_submissions = db.relationship('Submission', foreign_keys='Submission.procurement_id', backref='procurement_user', lazy='dynamic')
    general_manager_submissions = db.relationship('Submission', foreign_keys='Submission.general_manager_id', backref='general_manager', lazy='dynamic')
    # Legacy
    managed_submissions = db.relationship('Submission', foreign_keys='Submission.manager_id', backref='manager', lazy='dynamic')
    audit_logs = db.relationship('AuditLog', backref='user', lazy='dynamic')
    sessions = db.relationship('Session', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    reporting_manager = db.relationship(
        'User',
        foreign_keys=[reporting_manager_id],
        remote_side=[id],
    )

    def set_password(self, password):
        """Hash and set password"""
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
    
    def check_password(self, password):
        """Verify password against hash"""
        return bcrypt.check_password_hash(self.password_hash, password)
    
    def has_module_access(self, module):
        """Check if user has access to a specific module"""
        if self.role == 'admin':
            return True  # Admins have access to all modules
        module_map = {
            'hvac_mep': self.access_hvac,
            'civil': self.access_civil,
            'cleaning': self.access_cleaning,
            'hr': getattr(self, 'access_hr', False),
            'procurement_module': getattr(self, 'access_procurement_module', False),
            'business_development': self.is_bd_inspection_reviewer(),
            'mmr': bool(getattr(self, 'access_report_generation', False)),
            'submitted_forms': bool(getattr(self, 'access_submitted_forms', False)),
            'ticketing': bool(getattr(self, 'access_ticketing', False)),
            'operations': bool(getattr(self, 'access_operations', False)),
        }
        return module_map.get(module, False)

    def is_bd_inspection_reviewer(self):
        """BD reviewer lanes on inspection forms and BD email (designation BD, or access flag if not a conflicting primary role)."""
        if self.role == 'admin':
            return False
        d = (self.designation or '').strip().lower()
        if d == 'business_development':
            return True
        if not bool(getattr(self, 'access_business_development', False)):
            return False
        priority = {
            'supervisor', 'operations_manager', 'procurement', 'general_manager',
            'hr_manager', 'hr',
        }
        return d not in priority
    
    def to_dict(self, include_sensitive=False):
        """Convert to dictionary"""
        data = {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'full_name': self.full_name,
            'role': self.role,
            'is_active': self.is_active,
            'access_hvac': self.access_hvac if self.role != 'admin' else True,
            'access_civil': self.access_civil if self.role != 'admin' else True,
            'access_cleaning': self.access_cleaning if self.role != 'admin' else True,
            'access_hr': getattr(self, 'access_hr', False) if self.role != 'admin' else True,
            'access_procurement_module': getattr(self, 'access_procurement_module', False) if self.role != 'admin' else True,
            'access_business_development': getattr(self, 'access_business_development', False) if self.role != 'admin' else True,
            'access_report_generation': getattr(self, 'access_report_generation', False) if self.role != 'admin' else True,
            'access_submitted_forms': getattr(self, 'access_submitted_forms', False) if self.role != 'admin' else True,
            'access_ticketing': getattr(self, 'access_ticketing', False) if self.role != 'admin' else True,
            'access_operations': getattr(self, 'access_operations', False) if self.role != 'admin' else True,
            'access_operations_manage': getattr(self, 'access_operations_manage', False) if self.role != 'admin' else True,
            'password_changed': self.password_changed if hasattr(self, 'password_changed') else True,
            'designation': self.designation if hasattr(self, 'designation') else None,
            'default_signature': self.default_signature if hasattr(self, 'default_signature') else None,
            'default_comment': self.default_comment if hasattr(self, 'default_comment') else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'employment_start_date': self.employment_start_date.isoformat() if getattr(self, 'employment_start_date', None) else None,
            'job_designation': getattr(self, 'job_designation', None),
            'assigned_project': getattr(self, 'assigned_project', None),
            'phone': getattr(self, 'phone', None),
            'annual_leave_days': getattr(self, 'annual_leave_days', None),
            'other_leave_days': getattr(self, 'other_leave_days', None),
            'reporting_manager_id': getattr(self, 'reporting_manager_id', None),
        }
        mgr = getattr(self, 'reporting_manager', None)
        if mgr:
            data['reporting_manager'] = {
                'id': mgr.id,
                'username': mgr.username,
                'email': mgr.email,
                'full_name': mgr.full_name,
            }
        else:
            data['reporting_manager'] = None
        return data
    
    def to_client_dict(self):
        """Session/API user payload including DocHub access (stored in dochub_access, not on User)."""
        data = self.to_dict()
        if self.role == 'admin':
            data['can_access_dochub'] = True
        else:
            row = DocHubAccess.query.filter_by(user_id=self.id).first()
            data['can_access_dochub'] = row.can_access if row else True
        return data
    
    def __repr__(self):
        return f'<User {self.username}>'


class Submission(db.Model):
    """Form submissions from all modules"""
    __tablename__ = 'submissions'
    
    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    doc_number = db.Column(db.String(20), nullable=True, index=True)  # Human-facing series number, e.g. 'HR-0001', 'INSP-0042'
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    module_type = db.Column(db.String(20), nullable=False, index=True)  # 'hvac_mep', 'civil', 'cleaning'
    site_name = db.Column(db.String(255))
    visit_date = db.Column(db.Date)
    status = db.Column(db.String(20), default='draft', index=True)  # 'draft', 'submitted', 'processing', 'completed'
    workflow_status = db.Column(db.String(40), default='submitted', index=True)  # 'submitted', 'operations_manager_review', 'operations_manager_approved', 'bd_procurement_review', 'bd_approved', 'procurement_approved', 'general_manager_review', 'general_manager_approved', 'completed', 'rejected'
    
    # Workflow participants
    supervisor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # Original submitter
    operations_manager_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    business_dev_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    procurement_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    general_manager_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # Legacy fields (kept for backwards compatibility, deprecated)
    manager_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # Deprecated - use operations_manager_id
    supervisor_notified_at = db.Column(db.DateTime, nullable=True)  # Deprecated
    supervisor_reviewed_at = db.Column(db.DateTime, nullable=True)  # Deprecated
    manager_notified_at = db.Column(db.DateTime, nullable=True)  # Deprecated
    manager_reviewed_at = db.Column(db.DateTime, nullable=True)  # Deprecated
    
    # New workflow timestamps
    operations_manager_notified_at = db.Column(db.DateTime, nullable=True)
    operations_manager_approved_at = db.Column(db.DateTime, nullable=True)
    business_dev_notified_at = db.Column(db.DateTime, nullable=True)
    business_dev_approved_at = db.Column(db.DateTime, nullable=True)
    procurement_notified_at = db.Column(db.DateTime, nullable=True)
    procurement_approved_at = db.Column(db.DateTime, nullable=True)
    general_manager_notified_at = db.Column(db.DateTime, nullable=True)
    general_manager_approved_at = db.Column(db.DateTime, nullable=True)
    
    # Approval comments and signatures
    operations_manager_comments = db.Column(db.Text, nullable=True)
    business_dev_comments = db.Column(db.Text, nullable=True)
    procurement_comments = db.Column(db.Text, nullable=True)
    general_manager_comments = db.Column(db.Text, nullable=True)
    
    # Rejection tracking
    rejection_stage = db.Column(db.String(40), nullable=True)  # Which stage rejected
    rejection_reason = db.Column(db.Text, nullable=True)
    rejected_at = db.Column(db.DateTime, nullable=True)
    rejected_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    form_data = db.Column(JSON, nullable=False)  # All form fields as JSON
    created_at = db.Column(db.DateTime, default=_utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    # Relationships
    jobs = db.relationship('Job', backref='submission', lazy='dynamic', cascade='all, delete-orphan')
    files = db.relationship('File', backref='submission', lazy='dynamic', cascade='all, delete-orphan')
    
    def to_dict(self, include_form_data=True, include_latest_job=True):
        """Convert to dictionary.
        For list/history endpoints use include_form_data=False, include_latest_job=False to avoid
        huge JSON payloads and N+1 Job queries.
        """
        latest_job = None
        if include_latest_job:
            try:
                if hasattr(self, 'jobs'):
                    completed_jobs = [j for j in self.jobs if hasattr(j, 'status') and j.status == 'completed']
                    if completed_jobs:
                        latest_job = max(completed_jobs, key=lambda j: j.completed_at if (hasattr(j, 'completed_at') and j.completed_at) else datetime.min)
            except Exception:
                pass

        data = {
            'id': self.id,
            'submission_id': self.submission_id,
            'user_id': self.user_id,
            'module_type': self.module_type,
            'module': self.module_type,  # Alias for frontend compatibility
            'site_name': self.site_name,
            'visit_date': self.visit_date.isoformat() if self.visit_date else None,
            'status': self.status,
            'workflow_status': getattr(self, 'workflow_status', 'submitted'),
            'supervisor_id': getattr(self, 'supervisor_id', None),
            'operations_manager_id': getattr(self, 'operations_manager_id', None),
            'business_dev_id': getattr(self, 'business_dev_id', None),
            'procurement_id': getattr(self, 'procurement_id', None),
            'general_manager_id': getattr(self, 'general_manager_id', None),
            'manager_id': getattr(self, 'manager_id', None),
            'rejection_reason': getattr(self, 'rejection_reason', None),
            'rejected_at': naive_utc_isoformat_z(getattr(self, 'rejected_at', None)) if hasattr(self, 'rejected_at') and getattr(self, 'rejected_at', None) else None,
            'supervisor_notified_at': naive_utc_isoformat_z(getattr(self, 'supervisor_notified_at', None)) if hasattr(self, 'supervisor_notified_at') and getattr(self, 'supervisor_notified_at', None) else None,
            'supervisor_reviewed_at': naive_utc_isoformat_z(getattr(self, 'supervisor_reviewed_at', None)) if hasattr(self, 'supervisor_reviewed_at') and getattr(self, 'supervisor_reviewed_at', None) else None,
            'manager_notified_at': naive_utc_isoformat_z(getattr(self, 'manager_notified_at', None)) if hasattr(self, 'manager_notified_at') and getattr(self, 'manager_notified_at', None) else None,
            'manager_reviewed_at': naive_utc_isoformat_z(getattr(self, 'manager_reviewed_at', None)) if hasattr(self, 'manager_reviewed_at') and getattr(self, 'manager_reviewed_at', None) else None,
            'operations_manager_approved_at': naive_utc_isoformat_z(getattr(self, 'operations_manager_approved_at', None)) if hasattr(self, 'operations_manager_approved_at') and getattr(self, 'operations_manager_approved_at', None) else None,
            'business_dev_approved_at': naive_utc_isoformat_z(getattr(self, 'business_dev_approved_at', None)) if hasattr(self, 'business_dev_approved_at') and getattr(self, 'business_dev_approved_at', None) else None,
            'procurement_approved_at': naive_utc_isoformat_z(getattr(self, 'procurement_approved_at', None)) if hasattr(self, 'procurement_approved_at') and getattr(self, 'procurement_approved_at', None) else None,
            'general_manager_approved_at': naive_utc_isoformat_z(getattr(self, 'general_manager_approved_at', None)) if hasattr(self, 'general_manager_approved_at') and getattr(self, 'general_manager_approved_at', None) else None,
            'created_at': naive_utc_isoformat_z(self.created_at) if self.created_at else None,
            'updated_at': naive_utc_isoformat_z(self.updated_at) if self.updated_at else None,
            'latest_job_id': latest_job.job_id if latest_job else None  # Latest completed job for downloads
        }
        if include_form_data:
            data['form_data'] = self.form_data
        if include_latest_job:
            pass  # latest_job_id already set above
        else:
            data['latest_job_id'] = None
        return data
    
    def __repr__(self):
        return f'<Submission {self.submission_id} - {self.module_type}>'


class Job(db.Model):
    """Background jobs for report generation"""
    __tablename__ = 'jobs'
    
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    submission_id = db.Column(db.Integer, db.ForeignKey('submissions.id', ondelete='CASCADE'), nullable=False)
    status = db.Column(db.String(20), default='pending', index=True)  # 'pending', 'processing', 'completed', 'failed'
    progress = db.Column(db.Integer, default=0)  # 0-100
    result_data = db.Column(JSON)  # URLs for Excel/PDF, error messages
    error_message = db.Column(db.Text)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=_utcnow)
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'job_id': self.job_id,
            'submission_id': self.submission_id,
            'status': self.status,
            'progress': self.progress,
            'result_data': self.result_data,
            'error_message': self.error_message,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    def __repr__(self):
        return f'<Job {self.job_id} - {self.status}>'


class File(db.Model):
    """Uploaded files (photos, signatures, reports)"""
    __tablename__ = 'files'
    
    id = db.Column(db.Integer, primary_key=True)
    file_id = db.Column(db.String(50), unique=True, nullable=False)
    submission_id = db.Column(db.Integer, db.ForeignKey('submissions.id', ondelete='CASCADE'), nullable=False)
    file_type = db.Column(db.String(20), index=True)  # 'photo', 'signature', 'report_pdf', 'report_excel'
    filename = db.Column(db.String(255))
    file_path = db.Column(db.String(500))  # Local path or NULL if cloud-only
    cloud_url = db.Column(db.String(500))  # Cloudinary URL
    is_cloud = db.Column(db.Boolean, default=True)
    file_size = db.Column(db.Integer)  # In bytes
    mime_type = db.Column(db.String(100))
    uploaded_at = db.Column(db.DateTime, default=_utcnow)
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'file_id': self.file_id,
            'submission_id': self.submission_id,
            'file_type': self.file_type,
            'filename': self.filename,
            'file_path': self.file_path,
            'cloud_url': self.cloud_url,
            'is_cloud': self.is_cloud,
            'file_size': self.file_size,
            'mime_type': self.mime_type,
            'uploaded_at': self.uploaded_at.isoformat() if self.uploaded_at else None
        }
    
    def __repr__(self):
        return f'<File {self.filename} - {self.file_type}>'


class AuditLog(db.Model):
    """Audit trail for security and compliance"""
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    action = db.Column(db.String(50), nullable=False, index=True)  # 'login', 'logout', 'create_submission', etc.
    resource_type = db.Column(db.String(50))  # 'submission', 'job', 'user'
    resource_id = db.Column(db.String(100))
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.Text)
    details = db.Column(JSON)
    created_at = db.Column(db.DateTime, default=_utcnow, index=True)
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'action': self.action,
            'resource_type': self.resource_type,
            'resource_id': self.resource_id,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'details': self.details,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    def __repr__(self):
        return f'<AuditLog {self.action} - User {self.user_id}>'


class Session(db.Model):
    """JWT session management for token revocation"""
    __tablename__ = 'sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    token_jti = db.Column(db.String(100), unique=True, nullable=False, index=True)  # JWT ID
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    is_revoked = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=_utcnow)
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'token_jti': self.token_jti,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'is_revoked': self.is_revoked,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    def __repr__(self):
        return f'<Session {self.token_jti[:8]}... - User {self.user_id}>'


class Device(db.Model):
    """Registered devices for admin management"""
    __tablename__ = 'devices'

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(50), unique=True, nullable=False, index=True)  # e.g. DEV-0001
    name = db.Column(db.String(255), nullable=False)
    device_type = db.Column(db.String(30), default='Laptop')  # Laptop, Desktop, Mobile, Server, Tablet
    os = db.Column(db.String(80), default='Windows 11')  # macOS, Windows 11, iOS, Ubuntu, etc.
    status = db.Column(db.String(20), default='online', index=True)  # online, offline, update
    health = db.Column(db.Integer, default=100)  # 0-100
    assigned_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    serial_or_asset_tag = db.Column(db.String(100), nullable=True)
    last_active_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)
    company = db.Column(db.String(255), nullable=True, index=True)  # client/company this device belongs to
    asset_owner_name = db.Column(db.String(255), nullable=True)  # free-text assignee, no User account link
    device_comment = db.Column(db.Text, nullable=True)  # admin notes / specs
    assignment_date = db.Column(db.Date, nullable=True)

    assigned_user = db.relationship('User', backref='devices', foreign_keys=[assigned_user_id])

    def to_dict(self):
        last = 'Never'
        if self.last_active_at:
            delta = datetime.now(timezone.utc).replace(tzinfo=None) - self.last_active_at
            if delta.days > 0:
                last = f'{delta.days}d ago'
            elif delta.seconds >= 3600:
                last = f'{delta.seconds // 3600}h ago'
            elif delta.seconds >= 60:
                last = f'{delta.seconds // 60}m ago'
            else:
                last = 'Just now'
        return {
            'id': self.id,
            'device_id': self.device_id,
            'name': self.name,
            'device_type': self.device_type,
            'os': self.os,
            'status': self.status,
            'health': self.health,
            'assigned_user_id': self.assigned_user_id,
            'assigned_user': self.assigned_user.email.split('@')[0] if self.assigned_user else None,
            'assigned_user_email': self.assigned_user.email if self.assigned_user else None,
            'serial_or_asset_tag': self.serial_or_asset_tag,
            'last_active': last,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'company': self.company,
            'asset_owner_name': self.asset_owner_name,
            'device_comment': self.device_comment,
            'assignment_date': self.assignment_date.isoformat() if self.assignment_date else None
        }

    def __repr__(self):
        return f'<Device {self.device_id} - {self.name}>'


class BDProject(db.Model):
    """Business development projects/deals"""
    __tablename__ = 'bd_projects'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, index=True)
    company = db.Column(db.String(255), nullable=False, index=True)
    stage = db.Column(db.String(30), default='prospecting', index=True)  # prospecting, qualifying, proposal, negotiation, closing
    status = db.Column(db.String(20), default='active', index=True)  # active, prospect, proposal, won, lost
    priority = db.Column(db.String(10), default='med')  # high, med, low
    value_amount = db.Column(db.Float, default=0.0)
    progress = db.Column(db.Integer, default=0)
    owner = db.Column(db.String(120), nullable=True)
    next_action = db.Column(db.String(255), nullable=True)
    expected_close_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    primary_contact_name = db.Column(db.String(120), nullable=True)
    primary_contact_email = db.Column(db.String(255), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    def to_dict(self):
        value_amount = float(self.value_amount or 0)
        return {
            'id': self.id,
            'name': self.name,
            'co': self.company,
            'company': self.company,
            'icon': '🏢',
            'bg': '#e8f5ee',
            'stage': self.stage,
            'status': self.status,
            'priority': self.priority,
            'valueAmount': value_amount,
            'value': f'${value_amount:,.0f}',
            'progress': max(0, min(100, int(self.progress or 0))),
            'owner': self.owner or 'Unassigned',
            'next': self.next_action or 'No action',
            'nextDate': self.expected_close_date.isoformat() if self.expected_close_date else '',
            'expectedCloseDate': self.expected_close_date.isoformat() if self.expected_close_date else None,
            'notes': self.notes,
            'primaryContactName': self.primary_contact_name,
            'primaryContactEmail': self.primary_contact_email,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
            'updatedAt': self.updated_at.isoformat() if self.updated_at else None
        }

    def __repr__(self):
        return f'<BDProject {self.id} - {self.name}>'


class BDFollowUp(db.Model):
    """Business development follow-up tasks"""
    __tablename__ = 'bd_followups'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    company = db.Column(db.String(255), nullable=True, index=True)
    followup_type = db.Column(db.String(20), default='call')  # call, email, meeting, note
    due_at = db.Column(db.DateTime, nullable=True, index=True)
    status = db.Column(db.String(20), default='open', index=True)  # open, done
    details = db.Column(db.Text, nullable=True)
    project_id = db.Column(db.Integer, db.ForeignKey('bd_projects.id'), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    project = db.relationship('BDProject', backref=db.backref('followups', lazy='dynamic'))

    def to_dict(self):
        icon_map = {'call': '📞', 'email': '📧', 'meeting': '🤝', 'note': '📝'}
        return {
            'id': self.id,
            'icon': icon_map.get(self.followup_type, '📝'),
            'title': self.title,
            'co': self.company or (self.project.company if self.project else ''),
            'date': self.due_at.isoformat() if self.due_at else '',
            'type': self.followup_type,
            'status': self.status,
            'details': self.details,
            'projectId': self.project_id,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
            'updatedAt': self.updated_at.isoformat() if self.updated_at else None
        }

    def __repr__(self):
        return f'<BDFollowUp {self.id} - {self.title}>'


class BDContact(db.Model):
    """Business development contacts"""
    __tablename__ = 'bd_contacts'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, index=True)
    title = db.Column(db.String(120), nullable=True)
    company = db.Column(db.String(255), nullable=True, index=True)
    email = db.Column(db.String(255), nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    tags = db.Column(JSON, default=list)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    def to_dict(self):
        safe_name = (self.name or '').strip()
        initials = ''.join([part[0] for part in safe_name.split() if part])[:2].upper() or 'NA'
        return {
            'id': self.id,
            'initials': initials,
            'name': self.name,
            'title': self.title or 'Contact',
            'co': self.company or '',
            'company': self.company or '',
            'email': self.email,
            'phone': self.phone,
            'tags': self.tags if isinstance(self.tags, list) else [],
            'createdAt': self.created_at.isoformat() if self.created_at else None,
            'updatedAt': self.updated_at.isoformat() if self.updated_at else None
        }

    def __repr__(self):
        return f'<BDContact {self.id} - {self.name}>'


class BDActivity(db.Model):
    """Business development activity timeline"""
    __tablename__ = 'bd_activities'

    id = db.Column(db.Integer, primary_key=True)
    icon = db.Column(db.String(10), default='📝')
    bg = db.Column(db.String(20), default='#e8f5ee')
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    badge = db.Column(db.String(120), nullable=True)
    event_time = db.Column(db.DateTime, default=_utcnow, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow, index=True)

    def to_dict(self):
        return {
            'id': self.id,
            'icon': self.icon or '📝',
            'bg': self.bg or '#e8f5ee',
            'title': self.title,
            'desc': self.description or '',
            'badge': self.badge or '',
            'time': self.event_time.isoformat() if self.event_time else None,
            'createdAt': self.created_at.isoformat() if self.created_at else None
        }

    def __repr__(self):
        return f'<BDActivity {self.id} - {self.title}>'


class AdminPersonalProject(db.Model):
    """Admin-only personal work tracking: current initiatives and metadata."""
    __tablename__ = 'admin_personal_projects'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False, index=True)
    summary = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='active', index=True)  # planning, active, on_hold, done, archived
    priority = db.Column(db.String(10), default='med')  # low, med, high
    category = db.Column(db.String(80), nullable=True, index=True)
    start_date = db.Column(db.Date, nullable=True)
    target_date = db.Column(db.Date, nullable=True)
    link_url = db.Column(db.String(500), nullable=True)
    tags = db.Column(JSON, default=list)
    notes = db.Column(db.Text, nullable=True)
    is_current_focus = db.Column(db.Boolean, default=False, index=True)
    sort_order = db.Column(db.Integer, default=0, index=True)
    created_at = db.Column(db.DateTime, default=_utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    user = db.relationship('User', backref=db.backref('admin_personal_projects', lazy='dynamic'))
    steps = db.relationship(
        'AdminPersonalProgressStep',
        backref='project',
        lazy='dynamic',
        cascade='all, delete-orphan',
        order_by='AdminPersonalProgressStep.sort_order',
    )

    def to_dict(self, include_steps=True):
        tags = self.tags if isinstance(self.tags, list) else []
        out = {
            'id': self.id,
            'title': self.title,
            'summary': self.summary or '',
            'status': self.status or 'active',
            'priority': self.priority or 'med',
            'category': self.category or '',
            'startDate': self.start_date.isoformat() if self.start_date else None,
            'targetDate': self.target_date.isoformat() if self.target_date else None,
            'linkUrl': self.link_url or '',
            'tags': tags,
            'notes': self.notes or '',
            'isCurrentFocus': bool(self.is_current_focus),
            'sortOrder': int(self.sort_order or 0),
            'createdAt': self.created_at.isoformat() if self.created_at else None,
            'updatedAt': self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_steps:
            step_rows = self.steps.order_by(AdminPersonalProgressStep.sort_order.asc()).all()
            out['steps'] = [s.to_dict() for s in step_rows]
            done = sum(1 for s in step_rows if (s.status or '') == 'done')
            total = len(step_rows)
            out['progressPercent'] = int(round(100 * done / total)) if total else 0
            out['stepsDone'] = done
            out['stepsTotal'] = total
        return out

    def __repr__(self):
        return f'<AdminPersonalProject {self.id} - {self.title}>'


class AdminPersonalProgressStep(db.Model):
    """Checklist-style steps for a personal admin project."""
    __tablename__ = 'admin_personal_progress_steps'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('admin_personal_projects.id'), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='pending', index=True)  # pending, in_progress, done, blocked, skipped
    sort_order = db.Column(db.Integer, default=0, index=True)
    due_date = db.Column(db.Date, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description or '',
            'status': self.status or 'pending',
            'sortOrder': int(self.sort_order or 0),
            'dueDate': self.due_date.isoformat() if self.due_date else None,
            'completedAt': self.completed_at.isoformat() + 'Z' if self.completed_at else None,
            'notes': self.notes or '',
        }

    def __repr__(self):
        return f'<AdminPersonalProgressStep {self.id} - {self.title}>'


class DocHubDocument(db.Model):
    """Document metadata for DocHub. Supports both file uploads and editable content docs."""
    __tablename__ = 'dochub_documents'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=True)  # null for content-only docs
    stored_path = db.Column(db.String(500), nullable=True)  # null for content-only docs
    file_type = db.Column(db.String(20), nullable=True, index=True)  # PDF, DOCX, etc.; null for content
    doc_type = db.Column(db.String(20), default='content', index=True)  # 'content' | 'upload'
    content = db.Column(db.Text, nullable=True)  # HTML content for editable docs
    # JSON array: [{ "url": "/api/docs/inline/…", "filename": "…", "feed_document_id": 123 }, …]
    reference_attachments = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(50), default='Internal', index=True)  # onboarding, contracts, policies, manuals, reports, Internal, etc.
    status = db.Column(db.String(20), default='draft', index=True)  # draft, review, published, archived
    size_bytes = db.Column(db.Integer, default=0)
    is_starred = db.Column(db.Boolean, default=False)
    # True when this row mirrors an inline-stored file (editor reference); deleting the row does not delete the file.
    inline_asset = db.Column(db.Boolean, default=False)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow, index=True)

    author = db.relationship('User', backref=db.backref('dochub_documents', lazy='dynamic'))

    def to_dict(self):
        author_name = 'Unknown'
        if self.author:
            author_name = self.author.full_name or self.author.username or 'Unknown'

        size_mb = (self.size_bytes or 0) / (1024 * 1024)
        if size_mb >= 1:
            size_label = f"{size_mb:.1f} MB"
        elif self.size_bytes:
            size_kb = (self.size_bytes or 0) / 1024
            size_label = f"{max(1, int(round(size_kb)))} KB"
        else:
            size_label = '—'

        date_label = self.updated_at.strftime('%b %d, %Y') if self.updated_at else ''

        d = {
            'id': self.id,
            'name': self.title,
            'filename': self.filename or '',
            'path': self.stored_path or '',
            'type': self.file_type or '',
            'doc_type': self.doc_type or 'content',
            'tag': self.category,
            'status': self.status,
            'author': author_name,
            'author_id': self.author_id,
            'date': date_label,
            'dateTs': int(self.updated_at.timestamp()) if self.updated_at else 0,
            'size': size_label,
            'sizeB': int(self.size_bytes or 0),
            'starred': bool(self.is_starred),
            'inline_asset': bool(getattr(self, 'inline_asset', False)),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
        if self.doc_type == 'content':
            d['content'] = self.content or ''
            refs = []
            raw = getattr(self, 'reference_attachments', None)
            if raw:
                try:
                    parsed = json.loads(raw)
                    refs = parsed if isinstance(parsed, list) else []
                except (json.JSONDecodeError, TypeError):
                    refs = []
            d['reference_attachments'] = refs
        return d

    def __repr__(self):
        return f'<DocHubDocument {self.id} - {self.title}>'


class DocHubAccess(db.Model):
    """Per-user access control for DocHub."""
    __tablename__ = 'dochub_access'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False, index=True)
    can_access = db.Column(db.Boolean, default=True)
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow, index=True)

    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('dochub_access_entry', uselist=False))

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'can_access': bool(self.can_access),
            'updated_by': self.updated_by,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    def __repr__(self):
        return f'<DocHubAccess user={self.user_id} access={self.can_access}>'


class EmailAutomation(db.Model):
    """A user-created recurring email automation (free-form email on a schedule)."""
    __tablename__ = 'email_automation'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    enabled = db.Column(db.Boolean, default=True)

    # recipients (comma-separated @injaaz.ae addresses)
    to_emails = db.Column(db.Text, default='')
    cc_emails = db.Column(db.Text, default='')

    # content
    subject = db.Column(db.String(300), default='')
    body = db.Column(db.Text, default='')  # plain text; rendered to simple HTML on send

    # schedule — daily | weekly | monthly | quarterly | interval
    schedule_type = db.Column(db.String(20), default='daily')
    hour = db.Column(db.Integer, default=10)   # Dubai tz
    minute = db.Column(db.Integer, default=0)
    weekday = db.Column(db.Integer, default=0)        # 0=Mon (weekly)
    day_of_month = db.Column(db.Integer, default=1)   # monthly | quarterly
    quarter_start_month = db.Column(db.Integer, default=1)  # quarterly anchor (1 => 1,4,7,10)
    interval_unit = db.Column(db.String(10), default='days')  # interval: days | weeks | months
    interval_n = db.Column(db.Integer, default=1)

    # runtime status
    last_run_at = db.Column(db.DateTime)
    last_run_status = db.Column(db.String(20))   # success | failed
    last_run_detail = db.Column(db.Text)

    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    attachments = db.relationship(
        'EmailAutomationAttachment', backref='automation',
        cascade='all, delete-orphan', lazy='selectin',
    )
    run_logs = db.relationship(
        'EmailAutomationRunLog', backref='automation',
        cascade='all, delete-orphan', lazy='dynamic',
        order_by='EmailAutomationRunLog.run_at.desc()',
    )
    creator = db.relationship('User', foreign_keys=[created_by])

    def schedule_summary(self):
        """Human-readable one-line schedule description."""
        t = f"{self.hour:02d}:{self.minute:02d}"
        st = self.schedule_type
        if st == 'daily':
            return f"Daily at {t}"
        if st == 'weekly':
            days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
            wd = days[self.weekday] if 0 <= (self.weekday or 0) < 7 else '?'
            return f"Weekly on {wd} at {t}"
        if st == 'monthly':
            return f"Monthly on day {self.day_of_month} at {t}"
        if st == 'quarterly':
            return f"Quarterly (from month {self.quarter_start_month}) on day {self.day_of_month} at {t}"
        if st == 'interval':
            return f"Every {self.interval_n} {self.interval_unit} at {t}"
        return st or 'Unknown'

    def to_dict(self, include_body=False):
        d = {
            'id': self.id,
            'name': self.name,
            'enabled': bool(self.enabled),
            'to_emails': self.to_emails or '',
            'cc_emails': self.cc_emails or '',
            'subject': self.subject or '',
            'schedule_type': self.schedule_type,
            'hour': self.hour,
            'minute': self.minute,
            'weekday': self.weekday,
            'day_of_month': self.day_of_month,
            'quarter_start_month': self.quarter_start_month,
            'interval_unit': self.interval_unit,
            'interval_n': self.interval_n,
            'schedule_summary': self.schedule_summary(),
            'last_run_at': self.last_run_at.isoformat() if self.last_run_at else None,
            'last_run_status': self.last_run_status,
            'last_run_detail': self.last_run_detail,
            'recipient_count': len([e for e in (self.to_emails or '').split(',') if e.strip()]),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'created_by': self.created_by,
            'created_by_name': (self.creator.full_name or self.creator.username) if self.creator else None,
            'attachments': [
                {'id': a.id, 'filename': a.filename, 'mime_type': a.mime_type}
                for a in self.attachments
            ],
        }
        if include_body:
            d['body'] = self.body or ''
        return d

    def __repr__(self):
        return f'<EmailAutomation id={self.id} name={self.name!r}>'


class EmailAutomationAttachment(db.Model):
    """A file attachment stored in the DB for an email automation."""
    __tablename__ = 'email_automation_attachment'

    id = db.Column(db.Integer, primary_key=True)
    automation_id = db.Column(
        db.Integer, db.ForeignKey('email_automation.id'), nullable=False, index=True,
    )
    filename = db.Column(db.String(255), nullable=False)
    mime_type = db.Column(db.String(120))
    content = db.Column(db.LargeBinary, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow)

    def __repr__(self):
        return f'<EmailAutomationAttachment id={self.id} file={self.filename!r}>'


class EmailAutomationRunLog(db.Model):
    """One row per email-automation execution (scheduled or manual)."""
    __tablename__ = 'email_automation_run_log'

    id = db.Column(db.Integer, primary_key=True)
    automation_id = db.Column(
        db.Integer, db.ForeignKey('email_automation.id'), nullable=False, index=True,
    )
    run_at = db.Column(db.DateTime, default=_utcnow, index=True)
    status = db.Column(db.String(20))    # success | failed
    trigger = db.Column(db.String(20))   # scheduled | manual
    detail = db.Column(db.Text)
    recipient_count = db.Column(db.Integer, default=0)
    attachment_count = db.Column(db.Integer, default=0)
    duration_ms = db.Column(db.Integer)

    def to_dict(self):
        return {
            'id': self.id,
            'automation_id': self.automation_id,
            'run_at': self.run_at.isoformat() if self.run_at else None,
            'status': self.status,
            'trigger': self.trigger,
            'detail': self.detail,
            'recipient_count': self.recipient_count or 0,
            'attachment_count': self.attachment_count or 0,
            'duration_ms': self.duration_ms,
        }

    def __repr__(self):
        return f'<EmailAutomationRunLog id={self.id} automation={self.automation_id} status={self.status}>'


class NotificationConfig(db.Model):
    """Single-row JSON settings for workflow notification recipients."""
    __tablename__ = 'notification_config'

    id = db.Column(db.Integer, primary_key=True)
    config_json = db.Column(JSON, nullable=False)

    def __repr__(self):
        return f'<NotificationConfig id={self.id}>'


class EmailAutomationDefaults(db.Model):
    """Single-row default To/CC recipients for new email automations."""
    __tablename__ = 'email_automation_defaults'

    id = db.Column(db.Integer, primary_key=True)
    to_emails = db.Column(db.Text, default='')   # comma-separated @injaaz.ae
    cc_emails = db.Column(db.Text, default='')

    def to_dict(self):
        return {'to_emails': self.to_emails or '', 'cc_emails': self.cc_emails or ''}

    def __repr__(self):
        return f'<EmailAutomationDefaults id={self.id}>'


class TicketProject(db.Model):
    """Projects managed in ticketing settings"""
    __tablename__ = 'ticket_projects'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    client_name = db.Column(db.String(160), nullable=True)
    description = db.Column(db.Text, nullable=True)
    supervisor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    bd_project_id = db.Column(db.Integer, db.ForeignKey('bd_projects.id', ondelete='SET NULL'), nullable=True, index=True)
    project_end_date = db.Column(db.Date, nullable=True)
    renewal_date = db.Column(db.Date, nullable=True)
    project_value = db.Column(db.Float, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=_utcnow)

    properties = db.relationship('TicketProperty', backref='project',
                                 lazy='dynamic', cascade='all, delete-orphan',
                                 order_by='TicketProperty.name')
    supervisor_user = db.relationship(
        'User', foreign_keys=[supervisor_id],
        backref=db.backref('ticket_projects_supervised', lazy='dynamic'),
    )
    bd_project = db.relationship('BDProject', foreign_keys=[bd_project_id])

    def to_dict(self, *, with_property_count=False):
        sup = self.supervisor_user
        bp = self.bd_project
        d = {
            'id': self.id, 'name': self.name,
            'client_name': self.client_name, 'description': self.description,
            'supervisor_id': self.supervisor_id,
            'supervisor_name': sup.full_name if sup else None,
            'bd_project_id': self.bd_project_id,
            'bd_project_label': (
                f'{bp.name} — {bp.company}' if bp else None
            ),
            'project_end_date': self.project_end_date.isoformat() if self.project_end_date else None,
            'renewal_date': self.renewal_date.isoformat() if self.renewal_date else None,
            'project_value': float(self.project_value) if self.project_value is not None else None,
            'is_active': self.is_active, 'sort_order': self.sort_order,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        if with_property_count:
            d['properties_count'] = self.properties.filter_by(is_active=True).count()
        return d

    def __repr__(self):
        return f'<TicketProject {self.name}>'


class TicketProperty(db.Model):
    """Location: Property level (belongs to a project)"""
    __tablename__ = 'ticket_properties'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('ticket_projects.id', ondelete='CASCADE'), nullable=True)
    name = db.Column(db.String(160), nullable=False)
    is_active = db.Column(db.Boolean, default=True)

    zones = db.relationship('TicketZone', backref='property',
                            lazy='dynamic', cascade='all, delete-orphan',
                            order_by='TicketZone.name')

    def to_dict(self, with_zones=False):
        d = {'id': self.id, 'name': self.name, 'project_id': self.project_id}
        if with_zones:
            d['zones'] = [z.to_dict(with_sub_zones=True) for z in self.zones]
        return d


class TicketZone(db.Model):
    """Location: Zone level"""
    __tablename__ = 'ticket_zones'

    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('ticket_properties.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(160), nullable=False)
    is_active = db.Column(db.Boolean, default=True)

    sub_zones = db.relationship('TicketSubZone', backref='zone',
                                lazy='dynamic', cascade='all, delete-orphan',
                                order_by='TicketSubZone.name')

    def to_dict(self, with_sub_zones=False):
        d = {'id': self.id, 'name': self.name, 'property_id': self.property_id}
        if with_sub_zones:
            d['sub_zones'] = [s.to_dict(with_units=True) for s in self.sub_zones]
        return d


class TicketSubZone(db.Model):
    """Location: Sub-zone level"""
    __tablename__ = 'ticket_sub_zones'

    id = db.Column(db.Integer, primary_key=True)
    zone_id = db.Column(db.Integer, db.ForeignKey('ticket_zones.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(160), nullable=False)
    is_active = db.Column(db.Boolean, default=True)

    base_units = db.relationship('TicketBaseUnit', backref='sub_zone',
                                 lazy='dynamic', cascade='all, delete-orphan',
                                 order_by='TicketBaseUnit.name')

    def to_dict(self, with_units=False):
        d = {'id': self.id, 'name': self.name, 'zone_id': self.zone_id}
        if with_units:
            d['base_units'] = [u.to_dict() for u in self.base_units]
        return d


class TicketBaseUnit(db.Model):
    """Location: Base unit (apartment, room, office, etc.)"""
    __tablename__ = 'ticket_base_units'

    id = db.Column(db.Integer, primary_key=True)
    sub_zone_id = db.Column(db.Integer, db.ForeignKey('ticket_sub_zones.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(160), nullable=False)
    is_active = db.Column(db.Boolean, default=True)

    def to_dict(self):
        return {'id': self.id, 'name': self.name, 'sub_zone_id': self.sub_zone_id}


class TicketTitleTemplate(db.Model):
    """Predefined title templates for quick ticket creation"""
    __tablename__ = 'ticket_title_templates'

    id = db.Column(db.Integer, primary_key=True)
    service_group = db.Column(db.String(120), nullable=True)   # if None → applies to all
    category = db.Column(db.String(120), nullable=True)
    fault_type = db.Column(db.String(120), nullable=True)
    title = db.Column(db.String(255), nullable=False)
    description_template = db.Column(db.Text, nullable=True)   # auto-fill for work description
    is_active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=_utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'service_group': self.service_group,
            'category': self.category,
            'fault_type': self.fault_type,
            'title': self.title,
            'description_template': self.description_template,
            'is_active': self.is_active,
        }

    def __repr__(self):
        return f'<TicketTitleTemplate "{self.title}">'


class TicketSupervisorTeam(db.Model):
    """Maps supervisors to their technician team members for ticket assignment."""
    __tablename__ = 'ticket_supervisor_teams'

    id = db.Column(db.Integer, primary_key=True)
    supervisor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    technician_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=_utcnow)

    __table_args__ = (
        db.UniqueConstraint('supervisor_id', 'technician_id', name='uq_sup_tech_member'),
    )

    sup_user  = db.relationship('User', foreign_keys=[supervisor_id],
                                backref=db.backref('supervisor_team_entries', lazy='dynamic'))
    tech_user = db.relationship('User', foreign_keys=[technician_id],
                                backref=db.backref('technician_team_entries', lazy='dynamic'))

    def to_dict(self):
        return {
            'id': self.id,
            'supervisor_id': self.supervisor_id,
            'technician_id': self.technician_id,
            'technician_name': self.tech_user.full_name if self.tech_user else None,
            'technician_username': self.tech_user.username if self.tech_user else None,
            'is_active': self.is_active,
        }

    def __repr__(self):
        return f'<TicketSupervisorTeam sup={self.supervisor_id} tech={self.technician_id}>'


class Ticket(db.Model):
    """Work order / complaint tickets"""
    __tablename__ = 'tickets'

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.String(50), unique=True, nullable=False, index=True)  # TKT-XXXXXXXX

    # Reporter & assignment
    reporter_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Supervisor workflow
    supervisor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    technician_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Classification
    project = db.Column(db.String(160), nullable=False)
    service_group = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(120), nullable=False)
    fault_type = db.Column(db.String(120), nullable=False)
    priority = db.Column(db.String(20), nullable=False, default='medium')  # low, medium, high, critical

    # Description
    title = db.Column(db.String(255), nullable=False)
    work_description = db.Column(db.Text, nullable=False)

    # Location
    property_name = db.Column(db.String(160), nullable=True)
    zone = db.Column(db.String(120), nullable=True)
    sub_zone = db.Column(db.String(120), nullable=True)
    base_unit = db.Column(db.String(120), nullable=True)

    # Financial
    is_chargeable = db.Column(db.Boolean, default=False)
    projected_cost = db.Column(db.Float, nullable=True)
    total_cost = db.Column(db.Float, nullable=True)

    # Pricing with overhead + markup (supervisor sets these before closing)
    overhead_pct = db.Column(db.Float, default=10.0)      # always 10 %; stored for audit
    markup_pct = db.Column(db.Float, nullable=True)        # 0 / 10 / 20 / 30
    actual_price = db.Column(db.Float, nullable=True)      # (mp + mat) * (1 + overhead/100)
    selling_price = db.Column(db.Float, nullable=True)     # actual_price * (1 + markup/100)

    # Narrative fields
    service_report_notes = db.Column(db.Text, nullable=True)          # supervisor's service-report narrative
    technician_resolution_notes = db.Column(db.Text, nullable=True)   # technician's completion notes
    supervisor_verification_notes = db.Column(db.Text, nullable=True) # supervisor's verification remarks

    # Status: open → pending_supervisor → in_progress → pending_parts → pending_verification → closed
    status = db.Column(db.String(30), default='open', index=True)

    # Closing info
    close_notes = db.Column(db.Text, nullable=True)
    close_signature = db.Column(db.Text, nullable=True)   # base64 data-URL
    close_signed_by = db.Column(db.String(160), nullable=True)
    close_signed_role = db.Column(db.String(120), nullable=True)

    # Client sign-off (digital signature from the client upon completion)
    client_signature = db.Column(db.Text, nullable=True)       # base64 data-URL
    client_signed_by = db.Column(db.String(160), nullable=True)
    client_signed_at = db.Column(db.DateTime, nullable=True)
    client_mobile = db.Column(db.String(40), nullable=True)

    # Technician ID (for Service Report footer)
    technician_id_no = db.Column(db.String(80), nullable=True)

    # Amaan Service Report template fields
    service_report_no = db.Column(db.Integer, nullable=True, unique=True)  # auto SRN
    service_report_data = db.Column(db.Text, nullable=True)                # JSON blob

    # Finance approval gate: required when profit margin < 15%
    gm_approval_required = db.Column(db.Boolean, default=False)
    gm_approved_at = db.Column(db.DateTime, nullable=True)
    gm_approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    gm_approval_notes = db.Column(db.Text, nullable=True)
    # GM rejection (sends back to supervisor for re-verification)
    gm_rejected_at = db.Column(db.DateTime, nullable=True)
    gm_rejection_notes = db.Column(db.Text, nullable=True)
    # Finance confirmation (finance team confirms invoice created, ticket fully closes)
    finance_confirmed_at = db.Column(db.DateTime, nullable=True)
    finance_confirmed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    finance_invoice_ref = db.Column(db.String(80), nullable=True)
    # Linked finance contract
    finance_contract_id = db.Column(db.Integer, db.ForeignKey('finance_contracts.id'), nullable=True)

    # Origin: Civil Defense (CD) inspection notification this ticket was converted from
    source_inspection_notif_id = db.Column(db.Integer, db.ForeignKey('inspection_notifications.id'), nullable=True, index=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=_utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)
    closed_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    reporter = db.relationship('User', foreign_keys=[reporter_id],
                               backref=db.backref('reported_tickets', lazy='dynamic'))
    assigned_to = db.relationship('User', foreign_keys=[assigned_to_id],
                                  backref=db.backref('assigned_tickets', lazy='dynamic'))
    supervisor = db.relationship('User', foreign_keys=[supervisor_id],
                                 backref=db.backref('supervised_tickets', lazy='dynamic'))
    technician = db.relationship('User', foreign_keys=[technician_id],
                                 backref=db.backref('technician_tickets', lazy='dynamic'))
    gm_approved_by = db.relationship('User', foreign_keys=[gm_approved_by_id],
                                     backref=db.backref('gm_approved_tickets', lazy='dynamic'))
    finance_confirmed_by = db.relationship('User', foreign_keys=[finance_confirmed_by_id],
                                           backref=db.backref('finance_confirmed_tickets', lazy='dynamic'))
    finance_contract = db.relationship('FinanceContract', foreign_keys=[finance_contract_id],
                                       backref=db.backref('tickets', lazy='dynamic'))
    source_inspection_notif = db.relationship('InspectionNotification', foreign_keys=[source_inspection_notif_id],
                                              backref=db.backref('converted_tickets', lazy='dynamic'))
    notes = db.relationship('TicketNote', backref='ticket',
                            lazy='dynamic', cascade='all, delete-orphan',
                            order_by='TicketNote.created_at')
    images = db.relationship('TicketImage', backref='ticket',
                             lazy='dynamic', cascade='all, delete-orphan')
    materials = db.relationship('TicketMaterial', backref='ticket',
                                lazy='dynamic', cascade='all, delete-orphan')
    manpower = db.relationship('TicketManpower', backref='ticket',
                               lazy='dynamic', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'ticket_id': self.ticket_id,
            'title': self.title,
            'project': self.project,
            'service_group': self.service_group,
            'category': self.category,
            'fault_type': self.fault_type,
            'priority': self.priority,
            'status': self.status,
            'work_description': self.work_description,
            'property_name': self.property_name,
            'zone': self.zone,
            'sub_zone': self.sub_zone,
            'base_unit': self.base_unit,
            'is_chargeable': self.is_chargeable,
            'projected_cost': self.projected_cost,
            'total_cost': self.total_cost,
            'overhead_pct': self.overhead_pct,
            'markup_pct': self.markup_pct,
            'actual_price': self.actual_price,
            'selling_price': self.selling_price,
            'reporter_id': self.reporter_id,
            'reporter_name': self.reporter.full_name if self.reporter else None,
            'assigned_to_id': self.assigned_to_id,
            'assigned_to_name': self.assigned_to.full_name if self.assigned_to else None,
            'supervisor_id': self.supervisor_id,
            'supervisor_name': self.supervisor.full_name if self.supervisor else None,
            'technician_id': self.technician_id,
            'technician_name': self.technician.full_name if self.technician else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'closed_at': self.closed_at.isoformat() if self.closed_at else None,
            'source_inspection_notif_id': self.source_inspection_notif_id,
            'source_cd_ref': (self.source_inspection_notif.civil_defense_ref or self.source_inspection_notif.notif_id)
                             if self.source_inspection_notif else None,
        }

    def __repr__(self):
        return f'<Ticket {self.ticket_id} [{self.status}]>'


class TicketNote(db.Model):
    """Live notes / activity on a ticket"""
    __tablename__ = 'ticket_notes'

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    note_type = db.Column(db.String(30), default='note')  # note, status_change, assignment, image
    created_at = db.Column(db.DateTime, default=_utcnow, index=True)

    author = db.relationship('User', backref=db.backref('ticket_notes', lazy='dynamic'))

    def to_dict(self):
        return {
            'id': self.id,
            'ticket_id': self.ticket_id,
            'content': self.content,
            'note_type': self.note_type,
            'author_name': self.author.full_name if self.author else 'Unknown',
            'author_id': self.user_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f'<TicketNote {self.id} ticket={self.ticket_id}>'


class TicketImage(db.Model):
    """Photos / images attached to a ticket"""
    __tablename__ = 'ticket_images'

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id', ondelete='CASCADE'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(512), nullable=False)
    cloud_url = db.Column(db.String(512), nullable=True)
    caption = db.Column(db.String(255), nullable=True)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=_utcnow)

    uploader = db.relationship('User', backref=db.backref('ticket_images', lazy='dynamic'))

    def url(self):
        return self.cloud_url or f'/tickets/images/{self.id}'

    def to_dict(self):
        return {
            'id': self.id,
            'filename': self.filename,
            'url': self.url(),
            'caption': self.caption,
            'uploaded_by': self.uploader.full_name if self.uploader else None,
            'uploaded_at': self.uploaded_at.isoformat() if self.uploaded_at else None,
        }

    def __repr__(self):
        return f'<TicketImage {self.id} ticket={self.ticket_id}>'


class TicketMaterial(db.Model):
    """Materials consumed / used on a ticket (work order)"""
    __tablename__ = 'ticket_materials'

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id', ondelete='CASCADE'), nullable=False)
    material_name = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Float, default=1.0)
    unit = db.Column(db.String(50), nullable=True)
    unit_price = db.Column(db.Float, default=0.0)
    total_price = db.Column(db.Float, default=0.0)
    from_procurement = db.Column(db.Boolean, default=False)  # sourced from procurement catalog
    procurement_ref = db.Column(db.String(80), nullable=True)  # submission_id of catalog item
    notes = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'material_name': self.material_name,
            'quantity': self.quantity,
            'unit': self.unit,
            'unit_price': self.unit_price,
            'total_price': self.total_price,
            'from_procurement': self.from_procurement,
            'notes': self.notes,
        }

    def __repr__(self):
        return f'<TicketMaterial {self.id} "{self.material_name}">'


class TicketManpower(db.Model):
    """Manpower hours logged on a ticket"""
    __tablename__ = 'ticket_manpower'

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id', ondelete='CASCADE'), nullable=False)
    worker_name = db.Column(db.String(160), nullable=False)
    worker_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    hours = db.Column(db.Float, nullable=False)  # 0.25=15min, 0.5=30min, 0.75=45min, 1, 2, 3+
    rate_per_hour = db.Column(db.Float, nullable=True)
    total_cost = db.Column(db.Float, nullable=True)
    work_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, nullable=True)

    worker_user = db.relationship('User', backref=db.backref('ticket_manpower_entries', lazy='dynamic'))

    def to_dict(self):
        return {
            'id': self.id,
            'worker_name': self.worker_name,
            'hours': self.hours,
            'rate_per_hour': self.rate_per_hour,
            'total_cost': self.total_cost,
            'work_date': self.work_date.isoformat() if self.work_date else None,
            'notes': self.notes,
        }

    def __repr__(self):
        return f'<TicketManpower {self.id} {self.worker_name} {self.hours}h>'


class Notification(db.Model):
    """User notifications for workflow updates"""
    __tablename__ = 'notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(50), default='info')  # 'info', 'success', 'warning', 'error', 'hr_approved', 'hr_rejected'
    submission_id = db.Column(db.String(50), nullable=True)  # Reference to related submission
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=_utcnow, index=True)
    
    # Relationship
    user = db.relationship('User', backref=db.backref('notifications', lazy='dynamic', cascade='all, delete-orphan'))
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'title': self.title,
            'message': self.message,
            'notification_type': self.notification_type,
            'submission_id': self.submission_id,
            'is_read': self.is_read,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    def __repr__(self):
        return f'<Notification {self.id} - User {self.user_id}>'


class Technician(db.Model):
    """Field technicians managed separately from system Users (no login required)."""
    __tablename__ = 'technicians'

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.String(40), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(160), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=True, index=True)
    password_hash = db.Column(db.String(255), nullable=True)
    admin_visible_password = db.Column(db.String(255), nullable=True)  # plaintext for admin reference
    designation = db.Column(db.String(160), nullable=True)
    department = db.Column(db.String(120), nullable=True)
    specialization = db.Column(db.String(120), nullable=True)
    phone = db.Column(db.String(40), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    salary = db.Column(db.Float, nullable=True)
    joining_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), default='active', index=True)  # active, inactive, on_leave
    notes = db.Column(db.Text, nullable=True)
    # HR profile (mirrors User HR fields)
    job_title = db.Column(db.String(160), nullable=True)
    annual_leave_days = db.Column(db.Integer, nullable=True)
    other_leave_days = db.Column(db.Integer, nullable=True)

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
    # Optional link to supervisor user account (for roster reporting; ticketing team uses TicketSupervisorTeam).
    supervisor_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    supervisor_user = db.relationship(
        'User',
        foreign_keys=[supervisor_user_id],
        backref=db.backref('hr_roster_technicians', lazy='dynamic'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'employee_id': self.employee_id,
            'full_name': self.full_name,
            'username': self.username,
            'admin_visible_password': self.admin_visible_password,
            'designation': self.designation,
            'department': self.department,
            'specialization': self.specialization,
            'phone': self.phone,
            'email': self.email,
            'salary': self.salary,
            'joining_date': self.joining_date.isoformat() if self.joining_date else None,
            'status': self.status,
            'notes': self.notes,
            'job_title': self.job_title,
            'annual_leave_days': self.annual_leave_days,
            'other_leave_days': self.other_leave_days,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'supervisor_user_id': self.supervisor_user_id,
            'supervisor_name': self.supervisor_user.full_name if self.supervisor_user else None,
            'supervisor_username': self.supervisor_user.username if self.supervisor_user else None,
        }

    def __repr__(self):
        return f'<Technician {self.employee_id} — {self.full_name}>'


class InspectionNotification(db.Model):
    """Civil Defense / regulatory inspection notifications registered by Sales."""
    __tablename__ = 'inspection_notifications'

    id = db.Column(db.Integer, primary_key=True)
    notif_id = db.Column(db.String(50), unique=True, nullable=False, index=True)  # INSP-NOTIF-XXXXXXXX
    civil_defense_ref = db.Column(db.String(120), nullable=True)   # reference from the portal
    site_name = db.Column(db.String(255), nullable=False)
    notification_date = db.Column(db.Date, nullable=False)          # date received from portal
    inspection_date = db.Column(db.Date, nullable=False)            # scheduled inspection date
    inspection_type = db.Column(db.String(80), nullable=True)       # Fire Safety / Civil / Electrical…
    notes = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(30), default='pending', index=True)  # pending, scheduled, completed, closed, overdue
    registered_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    ops_notified_at = db.Column(db.DateTime, nullable=True)
    # Inspection outcome (recorded after the inspection happens)
    outcome = db.Column(db.String(10), nullable=True)               # None (not inspected) / pass / fail
    rectify_by = db.Column(db.String(20), nullable=True)           # amaan / civil_defense (only when outcome=fail)
    outcome_notes = db.Column(db.Text, nullable=True)              # failure findings / basis for the ST
    outcome_recorded_at = db.Column(db.DateTime, nullable=True)
    outcome_recorded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    reinspection_count = db.Column(db.Integer, default=0)          # increments each CD-side restart
    created_at = db.Column(db.DateTime, default=_utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    registered_by = db.relationship('User', foreign_keys=[registered_by_id],
                                    backref=db.backref('registered_inspection_notifs', lazy='dynamic'))
    outcome_recorded_by = db.relationship('User', foreign_keys=[outcome_recorded_by_id])

    @property
    def can_convert(self):
        """True when this failed inspection is Amaan's to rectify, so an ST may be created."""
        return self.outcome == 'fail' and self.rectify_by == 'amaan'

    def days_notice(self):
        """Days between notification date and inspection date."""
        if self.notification_date and self.inspection_date:
            return (self.inspection_date - self.notification_date).days
        return None

    def days_remaining(self):
        """Days from today until inspection date (negative = overdue)."""
        from datetime import date
        if self.inspection_date:
            return (self.inspection_date - date.today()).days
        return None

    def to_dict(self):
        return {
            'id': self.id,
            'notif_id': self.notif_id,
            'civil_defense_ref': self.civil_defense_ref,
            'site_name': self.site_name,
            'notification_date': self.notification_date.isoformat() if self.notification_date else None,
            'inspection_date': self.inspection_date.isoformat() if self.inspection_date else None,
            'inspection_type': self.inspection_type,
            'notes': self.notes,
            'status': self.status,
            'outcome': self.outcome,
            'rectify_by': self.rectify_by,
            'outcome_notes': self.outcome_notes,
            'outcome_recorded_at': self.outcome_recorded_at.isoformat() if self.outcome_recorded_at else None,
            'outcome_recorded_by_name': self.outcome_recorded_by.full_name if self.outcome_recorded_by else None,
            'reinspection_count': self.reinspection_count or 0,
            'can_convert': self.can_convert,
            'days_notice': self.days_notice(),
            'days_remaining': self.days_remaining(),
            'registered_by_id': self.registered_by_id,
            'registered_by_name': self.registered_by.full_name if self.registered_by else None,
            'ops_notified_at': self.ops_notified_at.isoformat() if self.ops_notified_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f'<InspectionNotification {self.notif_id} [{self.status}]>'


class FinanceContract(db.Model):
    """AMC / service contracts tracked by the Finance module."""
    __tablename__ = 'finance_contracts'

    id = db.Column(db.Integer, primary_key=True)
    contract_id = db.Column(db.String(50), unique=True, nullable=False, index=True)  # FIN-CON-XXXXXXXX
    client_name = db.Column(db.String(255), nullable=False)
    property_name = db.Column(db.String(255), nullable=True)
    contract_type = db.Column(db.String(40), nullable=False)  # quarterly, semi_annual, annual, monthly
    service_type = db.Column(db.String(120), nullable=True)   # HVAC AMC, Civil, Cleaning…
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    contract_value = db.Column(db.Float, nullable=True)       # total contract value (AED)
    billing_day = db.Column(db.Integer, default=29)           # day of month for invoice generation
    status = db.Column(db.String(30), default='active', index=True)  # active, expired, cancelled
    notes = db.Column(db.Text, nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    created_by = db.relationship('User', foreign_keys=[created_by_id],
                                 backref=db.backref('finance_contracts', lazy='dynamic'))

    def to_dict(self):
        return {
            'id': self.id,
            'contract_id': self.contract_id,
            'client_name': self.client_name,
            'property_name': self.property_name,
            'contract_type': self.contract_type,
            'service_type': self.service_type,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'contract_value': self.contract_value,
            'billing_day': self.billing_day,
            'status': self.status,
            'notes': self.notes,
            'created_by_id': self.created_by_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f'<FinanceContract {self.contract_id} {self.client_name}>'


class FinanceMonthlyReport(db.Model):
    """Snapshot of completed jobs generated for Finance billing."""
    __tablename__ = 'finance_monthly_reports'

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    period_label = db.Column(db.String(40), nullable=False)   # e.g. "May 2026"
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)
    total_jobs = db.Column(db.Integer, default=0)
    total_value = db.Column(db.Float, default=0.0)
    report_data = db.Column(JSON, nullable=True)              # serialised job list
    generated_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    sent_to_finance_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)

    generated_by = db.relationship('User', foreign_keys=[generated_by_id],
                                   backref=db.backref('generated_finance_reports', lazy='dynamic'))

    def to_dict(self):
        return {
            'id': self.id,
            'report_id': self.report_id,
            'period_label': self.period_label,
            'period_start': self.period_start.isoformat() if self.period_start else None,
            'period_end': self.period_end.isoformat() if self.period_end else None,
            'total_jobs': self.total_jobs,
            'total_value': self.total_value,
            'generated_by_id': self.generated_by_id,
            'sent_to_finance_at': self.sent_to_finance_at.isoformat() if self.sent_to_finance_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f'<FinanceMonthlyReport {self.report_id}>'


# ---------------------------------------------------------------------------
# Operations module: Over Time records + Trading Invoices (with Client master)
# ---------------------------------------------------------------------------

class OvertimeRecord(db.Model):
    """A single staff overtime entry (manual or Excel import).

    Staff are stored as free text (name + employee id) rather than a strict FK
    so any staff member can be recorded and bulk-imported from Excel.
    """
    __tablename__ = 'overtime_records'

    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.String(50), unique=True, nullable=False, index=True)  # OT-XXXXXXXX
    staff_name = db.Column(db.String(160), nullable=False)
    employee_id = db.Column(db.String(60), nullable=True)
    department = db.Column(db.String(120), nullable=True)
    date = db.Column(db.Date, nullable=False)
    hours = db.Column(db.Float, nullable=False, default=0.0)
    rate_per_hour = db.Column(db.Float, nullable=True)
    total_amount = db.Column(db.Float, nullable=True)  # hours * rate_per_hour when rate present
    reason = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(30), default='recorded')  # recorded / approved / paid
    imported_from_excel = db.Column(db.Boolean, default=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    created_by = db.relationship('User', foreign_keys=[created_by_id],
                                 backref=db.backref('overtime_records', lazy='dynamic'))

    def to_dict(self):
        return {
            'id': self.id,
            'record_id': self.record_id,
            'staff_name': self.staff_name,
            'employee_id': self.employee_id,
            'department': self.department,
            'date': self.date.isoformat() if self.date else None,
            'hours': self.hours,
            'rate_per_hour': self.rate_per_hour,
            'total_amount': self.total_amount,
            'reason': self.reason,
            'status': self.status,
            'imported_from_excel': self.imported_from_excel,
            'created_by_id': self.created_by_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f'<OvertimeRecord {self.record_id} {self.staff_name}>'


class Client(db.Model):
    """Customer master for trading invoices (sourced materials sold to clients)."""
    __tablename__ = 'clients'

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.String(50), unique=True, nullable=False, index=True)  # CLI-XXXXXXXX
    client_name = db.Column(db.String(200), nullable=False)
    contact_person = db.Column(db.String(160), nullable=True)
    email = db.Column(db.String(160), nullable=True)
    phone = db.Column(db.String(60), nullable=True)
    billing_address = db.Column(db.Text, nullable=True)
    city = db.Column(db.String(120), nullable=True)
    country = db.Column(db.String(120), nullable=True)
    tax_id = db.Column(db.String(80), nullable=True)
    status = db.Column(db.String(30), default='active')  # active / inactive
    notes = db.Column(db.Text, nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    created_by = db.relationship('User', foreign_keys=[created_by_id],
                                 backref=db.backref('clients', lazy='dynamic'))

    def to_dict(self):
        return {
            'id': self.id,
            'client_id': self.client_id,
            'client_name': self.client_name,
            'contact_person': self.contact_person,
            'email': self.email,
            'phone': self.phone,
            'billing_address': self.billing_address,
            'city': self.city,
            'country': self.country,
            'tax_id': self.tax_id,
            'status': self.status,
            'notes': self.notes,
            'created_by_id': self.created_by_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f'<Client {self.client_id} {self.client_name}>'


class TradingInvoice(db.Model):
    """Invoice header for materials sourced and sold to a client."""
    __tablename__ = 'trading_invoices'

    id = db.Column(db.Integer, primary_key=True)
    invoice_no = db.Column(db.String(50), unique=True, nullable=False, index=True)  # TRD-INV-XXXXXXXX
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    invoice_date = db.Column(db.Date, nullable=False, default=lambda: _utcnow().date())
    due_date = db.Column(db.Date, nullable=True)
    subtotal = db.Column(db.Float, default=0.0)
    tax_pct = db.Column(db.Float, default=0.0)
    tax_amount = db.Column(db.Float, default=0.0)
    grand_total = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(30), default='draft')  # draft / issued / paid
    notes = db.Column(db.Text, nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    client = db.relationship('Client', foreign_keys=[client_id],
                             backref=db.backref('trading_invoices', lazy='dynamic'))
    created_by = db.relationship('User', foreign_keys=[created_by_id],
                                 backref=db.backref('trading_invoices', lazy='dynamic'))
    items = db.relationship('TradingInvoiceItem', backref='invoice',
                            cascade='all, delete-orphan', lazy='select',
                            order_by='TradingInvoiceItem.id')

    def to_dict(self, include_items=True):
        data = {
            'id': self.id,
            'invoice_no': self.invoice_no,
            'client_id': self.client_id,
            'client_name': self.client.client_name if self.client else None,
            'invoice_date': self.invoice_date.isoformat() if self.invoice_date else None,
            'due_date': self.due_date.isoformat() if self.due_date else None,
            'subtotal': self.subtotal,
            'tax_pct': self.tax_pct,
            'tax_amount': self.tax_amount,
            'grand_total': self.grand_total,
            'status': self.status,
            'notes': self.notes,
            'created_by_id': self.created_by_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_items:
            data['items'] = [it.to_dict() for it in self.items]
            data['client'] = self.client.to_dict() if self.client else None
        return data

    def __repr__(self):
        return f'<TradingInvoice {self.invoice_no}>'


class TradingInvoiceItem(db.Model):
    """A line item (material) on a trading invoice."""
    __tablename__ = 'trading_invoice_items'

    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('trading_invoices.id', ondelete='CASCADE'),
                           nullable=False, index=True)
    material_name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    quantity = db.Column(db.Float, default=0.0)
    unit = db.Column(db.String(40), nullable=True)
    unit_price = db.Column(db.Float, default=0.0)
    total_price = db.Column(db.Float, default=0.0)

    def to_dict(self):
        return {
            'id': self.id,
            'invoice_id': self.invoice_id,
            'material_name': self.material_name,
            'description': self.description,
            'quantity': self.quantity,
            'unit': self.unit,
            'unit_price': self.unit_price,
            'total_price': self.total_price,
        }

    def __repr__(self):
        return f'<TradingInvoiceItem {self.material_name}>'
