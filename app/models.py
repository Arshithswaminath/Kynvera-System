"""
Database Models for Injaaz App
SQLAlchemy ORM models for PostgreSQL/SQLite
"""
import json
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from sqlalchemy import JSON

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
    created_at = db.Column(db.DateTime, default=_utcnow)
    last_login = db.Column(db.DateTime)
    
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
            'procurement_module': getattr(self, 'access_procurement_module', False)
        }
        return module_map.get(module, False)
    
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
            'password_changed': self.password_changed if hasattr(self, 'password_changed') else True,
            'designation': self.designation if hasattr(self, 'designation') else None,
            'default_signature': self.default_signature if hasattr(self, 'default_signature') else None,
            'default_comment': self.default_comment if hasattr(self, 'default_comment') else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }
        return data
    
    def __repr__(self):
        return f'<User {self.username}>'


class Submission(db.Model):
    """Form submissions from all modules"""
    __tablename__ = 'submissions'
    
    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
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
            'rejected_at': getattr(self, 'rejected_at', None).isoformat() if hasattr(self, 'rejected_at') and getattr(self, 'rejected_at', None) else None,
            'supervisor_notified_at': getattr(self, 'supervisor_notified_at', None).isoformat() if hasattr(self, 'supervisor_notified_at') and getattr(self, 'supervisor_notified_at', None) else None,
            'supervisor_reviewed_at': getattr(self, 'supervisor_reviewed_at', None).isoformat() if hasattr(self, 'supervisor_reviewed_at') and getattr(self, 'supervisor_reviewed_at', None) else None,
            'manager_notified_at': getattr(self, 'manager_notified_at', None).isoformat() if hasattr(self, 'manager_notified_at') and getattr(self, 'manager_notified_at', None) else None,
            'manager_reviewed_at': getattr(self, 'manager_reviewed_at', None).isoformat() if hasattr(self, 'manager_reviewed_at') and getattr(self, 'manager_reviewed_at', None) else None,
            'operations_manager_approved_at': getattr(self, 'operations_manager_approved_at', None).isoformat() if hasattr(self, 'operations_manager_approved_at') and getattr(self, 'operations_manager_approved_at', None) else None,
            'business_dev_approved_at': getattr(self, 'business_dev_approved_at', None).isoformat() if hasattr(self, 'business_dev_approved_at') and getattr(self, 'business_dev_approved_at', None) else None,
            'procurement_approved_at': getattr(self, 'procurement_approved_at', None).isoformat() if hasattr(self, 'procurement_approved_at') and getattr(self, 'procurement_approved_at', None) else None,
            'general_manager_approved_at': getattr(self, 'general_manager_approved_at', None).isoformat() if hasattr(self, 'general_manager_approved_at') and getattr(self, 'general_manager_approved_at', None) else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
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
    status = db.Column(db.String(20), default='idle', index=True)  # online, offline, idle, update
    health = db.Column(db.Integer, default=100)  # 0-100
    assigned_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    serial_or_asset_tag = db.Column(db.String(100), nullable=True)
    last_active_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

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
            'serial_or_asset_tag': self.serial_or_asset_tag,
            'last_active': last,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
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


class MmrChargeableConfig(db.Model):
    """Single-row JSON settings for MMR chargeable rules (admin-editable)."""
    __tablename__ = 'mmr_chargeable_config'

    id = db.Column(db.Integer, primary_key=True)
    config_json = db.Column(JSON, nullable=False)

    def __repr__(self):
        return f'<MmrChargeableConfig id={self.id}>'


class NotificationConfig(db.Model):
    """Single-row JSON settings for workflow notification recipients."""
    __tablename__ = 'notification_config'

    id = db.Column(db.Integer, primary_key=True)
    config_json = db.Column(JSON, nullable=False)

    def __repr__(self):
        return f'<NotificationConfig id={self.id}>'


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
