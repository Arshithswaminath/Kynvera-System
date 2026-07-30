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
    designation = db.Column(db.String(30), default=None)  # 'supervisor', 'operations_manager', 'sales', 'procurement', 'general_manager', …
    is_active = db.Column(db.Boolean, default=True)
    password_changed = db.Column(db.Boolean, default=False)  # Track if password was changed from default
    # Admin-only plaintext of current temp password (cleared after user changes it)
    admin_visible_password = db.Column(db.String(255), nullable=True)
    password_changed_at = db.Column(db.DateTime, nullable=True)  # Last password set/change (65-day clock)
    password_locked = db.Column(db.Boolean, default=False)  # Locked after password age > 65 days
    # Hashed PIN to unlock editing of protected admin accounts (Users & Teams)
    admin_protect_pin_hash = db.Column(db.String(255), nullable=True)
    default_signature = db.Column(db.Text, default=None)  # Base64 data URL for default signature
    default_comment = db.Column(db.Text, default=None)  # Default comment for approvals
    # Module access permissions (admin has access to all by default)
    access_hvac = db.Column(db.Boolean, default=False)  # Fire Systems inspection access
    access_civil = db.Column(db.Boolean, default=False)  # Legacy (unused — civil module removed)
    access_cleaning = db.Column(db.Boolean, default=False)  # Legacy (unused — cleaning module removed)
    access_hr = db.Column(db.Boolean, default=False)  # HR module access
    access_procurement_module = db.Column(db.Boolean, default=False)  # Procurement module access
    access_business_development = db.Column(db.Boolean, default=False)  # Sales module (own pipeline) + BD inspection reviewer
    access_sales_manager = db.Column(db.Boolean, default=False)  # Sales: view all salespeople's pipelines
    access_quotations = db.Column(db.Boolean, default=False)  # Sales: create/edit/submit quotations
    access_report_generation = db.Column(db.Boolean, default=False)  # MMR / Report Generation hub
    access_submitted_forms = db.Column(db.Boolean, default=False)  # "My submitted forms" workflow hub
    access_ticketing = db.Column(db.Boolean, default=False)  # Ticketing / Work Order module
    access_operations = db.Column(db.Boolean, default=False)  # Operations hub (any sub-module)
    access_operations_manage = db.Column(db.Boolean, default=False)  # Operations: full access (create/edit) vs view-only
    access_operations_overtime = db.Column(db.Boolean, default=False)
    access_operations_timesheet = db.Column(db.Boolean, default=False)
    access_operations_attendance = db.Column(db.Boolean, default=False)
    access_operations_invoices = db.Column(db.Boolean, default=False)
    access_operations_clients = db.Column(db.Boolean, default=False)
    access_operations_cheques = db.Column(db.Boolean, default=False)
    access_finance = db.Column(db.Boolean, default=False)  # Finance & Invoicing module
    # Kynvera Hub portal: which product apps this user may launch
    access_fire_app = db.Column(db.Boolean, default=False)  # Fire System Application (external)
    access_municipality_app = db.Column(db.Boolean, default=False)  # Municipality Application (external)
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
    sick_leave_days = db.Column(db.Integer, nullable=True)
    insurance_details = db.Column(db.String(255), nullable=True)
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

    def set_admin_protect_pin(self, pin):
        """Hash and store the admin protect PIN."""
        self.admin_protect_pin_hash = bcrypt.generate_password_hash(pin).decode('utf-8')

    def check_admin_protect_pin(self, pin):
        """Verify protect PIN against hash. False if no PIN configured."""
        stored = getattr(self, 'admin_protect_pin_hash', None)
        if not stored or not pin:
            return False
        return bcrypt.check_password_hash(stored, pin)

    def password_age_days(self):
        from common.password_policy import password_age_days
        return password_age_days(self)

    def should_warn_password_expiry(self):
        from common.password_policy import should_warn_password_expiry
        return should_warn_password_expiry(self)

    def should_lock_for_password_age(self):
        from common.password_policy import should_lock_for_password_age
        return should_lock_for_password_age(self)

    def should_remind_temp_password(self):
        from common.password_policy import should_remind_temp_password
        return should_remind_temp_password(self)
    
    def has_module_access(self, module):
        """Check if user has access to a specific module"""
        if self.role == 'admin':
            return True  # Admins have access to all modules
        module_map = {
            'hvac_mep': self.access_hvac,
            'hr': getattr(self, 'access_hr', False),
            'procurement_module': getattr(self, 'access_procurement_module', False),
            'business_development': self.is_bd_inspection_reviewer(),
            'mmr': bool(getattr(self, 'access_report_generation', False)),
            'submitted_forms': bool(getattr(self, 'access_submitted_forms', False)),
            'ticketing': bool(getattr(self, 'access_ticketing', False)),
            'operations': bool(getattr(self, 'access_operations', False)) or self.has_any_operations_submodule(),
            'operations_overtime': bool(getattr(self, 'access_operations_overtime', False)),
            'operations_timesheet': bool(getattr(self, 'access_operations_timesheet', False)),
            'operations_attendance': bool(getattr(self, 'access_operations_attendance', False)),
            'operations_invoices': bool(getattr(self, 'access_operations_invoices', False)),
            'operations_clients': bool(getattr(self, 'access_operations_clients', False)),
            'operations_cheques': bool(getattr(self, 'access_operations_cheques', False)),
            'finance': bool(getattr(self, 'access_finance', False)),
            'fire_app': bool(getattr(self, 'access_fire_app', False)),
            'municipality_app': bool(getattr(self, 'access_municipality_app', False)),
        }
        return module_map.get(module, False)

    def has_any_operations_submodule(self):
        return any((
            bool(getattr(self, 'access_operations_overtime', False)),
            bool(getattr(self, 'access_operations_timesheet', False)),
            bool(getattr(self, 'access_operations_attendance', False)),
            bool(getattr(self, 'access_operations_invoices', False)),
            bool(getattr(self, 'access_operations_clients', False)),
            bool(getattr(self, 'access_operations_cheques', False)),
        ))

    def has_operations_submodule(self, sub):
        """sub: overtime | timesheet | attendance | invoices | clients | cheques"""
        if self.role == 'admin':
            return True
        key = {
            'overtime': 'access_operations_overtime',
            'timesheet': 'access_operations_timesheet',
            'attendance': 'access_operations_attendance',
            'invoices': 'access_operations_invoices',
            'clients': 'access_operations_clients',
            'cheques': 'access_operations_cheques',
        }.get(sub)
        if not key:
            return False
        if bool(getattr(self, key, False)):
            return True
        # Legacy: hub on, no per-sub flags set yet → all subs allowed
        if bool(getattr(self, 'access_operations', False)) and not self.has_any_operations_submodule():
            return True
        return False

    def is_bd_inspection_reviewer(self):
        """BD reviewer lanes on inspection forms and BD email (Sales designation, or access flag if not a conflicting primary role)."""
        if self.role == 'admin':
            return False
        d = (self.designation or '').strip().lower()
        # Sales designation owns the former business_development inspection lane
        if d in ('sales', 'business_development'):
            return True
        if not bool(getattr(self, 'access_business_development', False)):
            return False
        priority = {
            'supervisor', 'operations_manager', 'procurement', 'general_manager',
            'hr_manager', 'hr',
        }
        return d not in priority
    
    def to_dict(self, include_sensitive=False):
        """Convert to dictionary.

        The admin-visible plaintext password is only included when
        ``include_sensitive=True`` (single-user reveal / post-action responses).
        Bulk list endpoints call this without the flag so every user's password
        is never shipped to the browser in one response.
        """
        from common.password_policy import password_policy_flags

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
            'access_sales_manager': getattr(self, 'access_sales_manager', False) if self.role != 'admin' else True,
            'access_quotations': getattr(self, 'access_quotations', False) if self.role != 'admin' else True,
            'access_report_generation': getattr(self, 'access_report_generation', False) if self.role != 'admin' else True,
            'access_submitted_forms': getattr(self, 'access_submitted_forms', False) if self.role != 'admin' else True,
            'access_ticketing': getattr(self, 'access_ticketing', False) if self.role != 'admin' else True,
            'access_operations': getattr(self, 'access_operations', False) if self.role != 'admin' else True,
            'access_operations_manage': getattr(self, 'access_operations_manage', False) if self.role != 'admin' else True,
            'access_operations_overtime': getattr(self, 'access_operations_overtime', False) if self.role != 'admin' else True,
            'access_operations_timesheet': getattr(self, 'access_operations_timesheet', False) if self.role != 'admin' else True,
            'access_operations_attendance': getattr(self, 'access_operations_attendance', False) if self.role != 'admin' else True,
            'access_operations_invoices': getattr(self, 'access_operations_invoices', False) if self.role != 'admin' else True,
            'access_operations_clients': getattr(self, 'access_operations_clients', False) if self.role != 'admin' else True,
            'access_operations_cheques': getattr(self, 'access_operations_cheques', False) if self.role != 'admin' else True,
            'access_finance': getattr(self, 'access_finance', False) if self.role != 'admin' else True,
            'access_fire_app': getattr(self, 'access_fire_app', False) if self.role != 'admin' else True,
            'access_municipality_app': getattr(self, 'access_municipality_app', False) if self.role != 'admin' else True,
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
            'sick_leave_days': getattr(self, 'sick_leave_days', None),
            'insurance_details': getattr(self, 'insurance_details', None),
            'reporting_manager_id': getattr(self, 'reporting_manager_id', None),
        }
        data.update(password_policy_flags(self))
        if include_sensitive:
            data['admin_visible_password'] = getattr(self, 'admin_visible_password', None)
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
        data.pop('admin_visible_password', None)
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


class EmailOtp(db.Model):
    """One-time codes emailed for protect-PIN reset and password reset."""
    __tablename__ = 'email_otps'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    purpose = db.Column(db.String(40), nullable=False, index=True)  # protect_pin_reset | password_reset
    code_hash = db.Column(db.String(255), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    attempts = db.Column(db.Integer, default=0, nullable=False)
    consumed_at = db.Column(db.DateTime, nullable=True)
    request_ip = db.Column(db.String(45), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow, index=True)

    user = db.relationship('User', backref=db.backref('email_otps', lazy='dynamic', cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<EmailOtp {self.purpose} user={self.user_id}>'


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
    status = db.Column(db.String(20), default='active', index=True)  # active, prospect, proposal, won, lost, under_renewal
    priority = db.Column(db.String(10), default='med')  # high, med, low
    value_amount = db.Column(db.Float, default=0.0)
    progress = db.Column(db.Integer, default=0)
    owner = db.Column(db.String(120), nullable=True)  # display name (legacy / denormalized)
    owner_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    next_action = db.Column(db.String(255), nullable=True)
    expected_close_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    primary_contact_name = db.Column(db.String(120), nullable=True)
    primary_contact_email = db.Column(db.String(255), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    owner_user = db.relationship('User', foreign_keys=[owner_user_id],
                                 backref=db.backref('owned_bd_projects', lazy='dynamic'))

    def to_dict(self):
        value_amount = float(self.value_amount or 0)
        owner_name = None
        if self.owner_user:
            owner_name = self.owner_user.full_name or self.owner_user.username
        owner_name = owner_name or self.owner or 'Unassigned'
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
            'owner': owner_name,
            'ownerUserId': self.owner_user_id,
            'owner_user_id': self.owner_user_id,
            'next': self.next_action or 'No action',
            'nextDate': self.expected_close_date.isoformat() if self.expected_close_date else '',
            'expectedCloseDate': self.expected_close_date.isoformat() if self.expected_close_date else None,
            'notes': self.notes,
            'primaryContactName': self.primary_contact_name,
            'primaryContactEmail': self.primary_contact_email,
            'createdBy': self.created_by,
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
    stars = db.relationship('DocHubStar', back_populates='document', cascade='all, delete-orphan', lazy='dynamic')

    def is_starred_by(self, user_id):
        if not user_id:
            return False
        return DocHubStar.query.filter_by(user_id=user_id, document_id=self.id).first() is not None

    def to_dict(self, user_id=None, starred=None):
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

        if starred is not None:
            is_starred_for_user = bool(starred)
        elif user_id is not None:
            is_starred_for_user = self.is_starred_by(user_id)
        else:
            is_starred_for_user = False

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
            'starred': is_starred_for_user,
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


class DocHubStar(db.Model):
    """Per-user starred documents in DocHub."""
    __tablename__ = 'dochub_stars'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'document_id', name='uq_dochub_star_user_document'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    document_id = db.Column(db.Integer, db.ForeignKey('dochub_documents.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=_utcnow, index=True)

    user = db.relationship('User', backref=db.backref('dochub_stars', lazy='dynamic'))
    document = db.relationship('DocHubDocument', back_populates='stars')

    def __repr__(self):
        return f'<DocHubStar user={self.user_id} doc={self.document_id}>'


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


class KnowledgeBaseEntry(db.Model):
    """Admin-managed knowledge records that feed the Amaan assistant brain."""
    __tablename__ = 'knowledge_base_entries'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False, index=True)
    content = db.Column(db.Text, nullable=True)  # typed text and/or extracted document text
    keywords = db.Column(db.Text, nullable=True)  # comma-separated search boosters
    category = db.Column(db.String(50), default='General', index=True)
    answer_link = db.Column(db.String(500), nullable=True)  # optional deep link the assistant surfaces
    source_type = db.Column(db.String(20), default='text', index=True)  # 'text' | 'upload' | 'link'
    file_name = db.Column(db.String(255), nullable=True)
    stored_path = db.Column(db.String(500), nullable=True)
    file_type = db.Column(db.String(20), nullable=True)  # PDF, DOCX, TXT, MD
    source_url = db.Column(db.String(1000), nullable=True)  # original URL for 'link' records
    fetched_at = db.Column(db.DateTime, nullable=True)  # when the link was last fetched
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow, index=True)

    author = db.relationship('User', foreign_keys=[created_by], backref=db.backref('knowledge_entries', lazy='dynamic'))

    def excerpt(self, length=200):
        text = (self.content or '').strip()
        if len(text) <= length:
            return text
        return text[:length].rsplit(' ', 1)[0] + '…'

    def keyword_list(self):
        if not self.keywords:
            return []
        return [k.strip() for k in self.keywords.split(',') if k.strip()]

    def to_dict(self, include_content=True):
        author_name = None
        if self.author:
            author_name = self.author.full_name or self.author.username
        data = {
            'id': self.id,
            'title': self.title,
            'keywords': self.keyword_list(),
            'category': self.category or 'General',
            'answer_link': self.answer_link or '',
            'source_type': self.source_type or 'text',
            'file_name': self.file_name,
            'file_type': self.file_type,
            'source_url': self.source_url or '',
            'fetched_at': self.fetched_at.isoformat() if self.fetched_at else None,
            'is_active': bool(self.is_active),
            'created_by': self.created_by,
            'author_name': author_name,
            'excerpt': self.excerpt(),
            'content_length': len(self.content or ''),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_content:
            data['content'] = self.content or ''
        return data

    def __repr__(self):
        return f'<KnowledgeBaseEntry {self.id} - {self.title}>'


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
    project_code = db.Column(db.String(60), nullable=True, index=True)
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

    def to_dict(self, *, with_property_count=False, include_value=True):
        sup = self.supervisor_user
        bp = self.bd_project
        d = {
            'id': self.id, 'name': self.name,
            'project_code': getattr(self, 'project_code', None),
            'client_name': self.client_name, 'description': self.description,
            'supervisor_id': self.supervisor_id,
            'supervisor_name': sup.full_name if sup else None,
            'bd_project_id': self.bd_project_id,
            'bd_project_label': (
                f'{bp.name} — {bp.company}' if bp else None
            ),
            'project_end_date': self.project_end_date.isoformat() if self.project_end_date else None,
            'renewal_date': self.renewal_date.isoformat() if self.renewal_date else None,
            'is_active': self.is_active, 'sort_order': self.sort_order,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        if include_value:
            d['project_value'] = float(self.project_value) if self.project_value is not None else None
        else:
            d['project_value'] = None
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

    # Priority SLA (P1=high 24h, P2=medium 72h, P3=low 168h; critical=4h)
    sla_due_at = db.Column(db.DateTime, nullable=True, index=True)
    sla_breached_at = db.Column(db.DateTime, nullable=True)

    # Payment tracking after finance confirm (chargeable jobs)
    payment_status = db.Column(db.String(20), default='n_a')  # n_a / unpaid / paid
    payment_due_date = db.Column(db.Date, nullable=True)
    paid_at = db.Column(db.DateTime, nullable=True)
    paid_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

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
    paid_by = db.relationship('User', foreign_keys=[paid_by_id],
                              backref=db.backref('paid_tickets', lazy='dynamic'))
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
        from common.sla import sla_state_for_ticket
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
            'finance_invoice_ref': self.finance_invoice_ref,
            'finance_confirmed_at': self.finance_confirmed_at.isoformat() if self.finance_confirmed_at else None,
            'payment_status': self.payment_status or 'n_a',
            'payment_due_date': self.payment_due_date.isoformat() if self.payment_due_date else None,
            'paid_at': self.paid_at.isoformat() if self.paid_at else None,
            'sla_due_at': self.sla_due_at.isoformat() if self.sla_due_at else None,
            'sla_breached_at': self.sla_breached_at.isoformat() if self.sla_breached_at else None,
            'sla_state': sla_state_for_ticket(self),
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
    sick_leave_days = db.Column(db.Integer, nullable=True)
    insurance_details = db.Column(db.String(255), nullable=True)

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
            'sick_leave_days': getattr(self, 'sick_leave_days', None),
            'insurance_details': getattr(self, 'insurance_details', None),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'supervisor_user_id': self.supervisor_user_id,
            'supervisor_name': self.supervisor_user.full_name if self.supervisor_user else None,
            'supervisor_username': self.supervisor_user.username if self.supervisor_user else None,
        }

    def __repr__(self):
        return f'<Technician {self.employee_id} — {self.full_name}>'


class Employee(db.Model):
    """HR employment directory — may exist before an application User login is created."""
    __tablename__ = 'employees'

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.String(40), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(160), nullable=False)
    email = db.Column(db.String(120), nullable=True, index=True)
    phone = db.Column(db.String(40), nullable=True)
    job_title = db.Column(db.String(160), nullable=True)
    department = db.Column(db.String(120), nullable=True)
    designation = db.Column(db.String(160), nullable=True)
    joining_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), default='active', index=True)  # active, inactive, on_leave
    annual_leave_days = db.Column(db.Integer, nullable=True)
    other_leave_days = db.Column(db.Integer, nullable=True)
    sick_leave_days = db.Column(db.Integer, nullable=True)
    insurance_details = db.Column(db.String(255), nullable=True)
    salary = db.Column(db.Float, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, unique=True, index=True)
    reporting_manager_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    user = db.relationship(
        'User',
        foreign_keys=[user_id],
        backref=db.backref('employee_profile', uselist=False),
    )
    reporting_manager = db.relationship(
        'User',
        foreign_keys=[reporting_manager_user_id],
    )

    def to_dict(self):
        return {
            'id': self.id,
            'employee_id': self.employee_id,
            'full_name': self.full_name,
            'email': self.email,
            'phone': self.phone,
            'job_title': self.job_title,
            'department': self.department,
            'designation': self.designation,
            'joining_date': self.joining_date.isoformat() if self.joining_date else None,
            'status': self.status or 'active',
            'annual_leave_days': self.annual_leave_days,
            'other_leave_days': self.other_leave_days,
            'sick_leave_days': getattr(self, 'sick_leave_days', None),
            'insurance_details': getattr(self, 'insurance_details', None),
            'salary': self.salary,
            'notes': self.notes,
            'user_id': self.user_id,
            'has_app_account': bool(self.user_id),
            'reporting_manager_user_id': self.reporting_manager_user_id,
            'reporting_manager_name': (
                (self.reporting_manager.full_name or self.reporting_manager.username)
                if self.reporting_manager else None
            ),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f'<Employee {self.employee_id} — {self.full_name}>'


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
    contract_id = db.Column(db.String(50), unique=True, nullable=False, index=True)  # FC-XXXXX
    # client_name stores the project name (legacy column name kept for compatibility)
    client_name = db.Column(db.String(255), nullable=False)
    property_name = db.Column(db.String(255), nullable=True)  # property / location
    account_handler = db.Column(db.String(255), nullable=True)  # Injaaz staff handling the account
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
            'project_name': self.client_name,
            'property_name': self.property_name,
            'account_handler': self.account_handler or '',
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


class FinanceSettings(db.Model):
    """Single-row JSON settings for Finance & Invoicing billing rules."""
    __tablename__ = 'finance_settings'

    id = db.Column(db.Integer, primary_key=True)
    config_json = db.Column(JSON, nullable=False)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)
    updated_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    updated_by = db.relationship('User', foreign_keys=[updated_by_id])

    DEFAULT_CONFIG = {
        'margin_threshold': 15.0,
        'invoice_email_to': '',
        'invoice_email_cc': '',
        'erp_ref_prefix': 'INV',
        'require_erp_ref': False,
        'report_recipients': '',
        'default_billing_day': 29,
        'default_contract_type': 'monthly',
    }

    def __repr__(self):
        return f'<FinanceSettings id={self.id}>'


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


class OvertimeSettings(db.Model):
    """Single-row JSON settings for overtime weekday/weekend rates."""
    __tablename__ = 'overtime_settings'

    id = db.Column(db.Integer, primary_key=True)
    config_json = db.Column(JSON, nullable=False)

    DEFAULT_CONFIG = {
        'weekday_rate': 10.0,
        'weekend_rate': 15.0,
        # Python date.weekday(): Mon=0 … Sun=6 — UAE weekend Fri+Sat
        'weekend_days': [4, 5],
    }

    def __repr__(self):
        return f'<OvertimeSettings id={self.id}>'


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
    owner_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    paid_at = db.Column(db.DateTime, nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    client = db.relationship('Client', foreign_keys=[client_id],
                             backref=db.backref('trading_invoices', lazy='dynamic'))
    owner_user = db.relationship('User', foreign_keys=[owner_user_id],
                                 backref=db.backref('owned_trading_invoices', lazy='dynamic'))
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
            'owner_user_id': self.owner_user_id,
            'owner_name': (
                (self.owner_user.full_name or self.owner_user.username)
                if self.owner_user else None
            ),
            'paid_at': self.paid_at.isoformat() if self.paid_at else None,
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


# ── Cheque Preparation (Operations) ──────────────────────────────────────────

CHEQUE_STATUSES = ['requested', 'verified', 'approved', 'prepared',
                   'submitted', 'cleared', 'rejected', 'cancelled']


class ChequeRequest(db.Model):
    """Cheque preparation / request form header (Operations module)."""
    __tablename__ = 'cheque_requests'

    id = db.Column(db.Integer, primary_key=True)
    reference_no = db.Column(db.String(50), unique=True, nullable=False, index=True)  # CHQ-XXXXXXXX
    office = db.Column(db.String(160), nullable=True)
    department = db.Column(db.String(120), default='Finance')
    status = db.Column(db.String(30), default='requested', index=True)
    remarks = db.Column(db.Text, nullable=True)
    attached_documents = db.Column(db.Text, nullable=True)  # one document name per line
    total_amount = db.Column(db.Float, default=0.0)

    requested_by_name = db.Column(db.String(160), nullable=True)
    requested_date = db.Column(db.Date, nullable=True)
    requested_signature = db.Column(db.Text, nullable=True)  # base64 data-URL
    verified_by_name = db.Column(db.String(160), nullable=True)
    verified_date = db.Column(db.Date, nullable=True)
    verified_signature = db.Column(db.Text, nullable=True)  # base64 data-URL
    approved_by_name = db.Column(db.String(160), nullable=True)
    approved_date = db.Column(db.Date, nullable=True)
    approved_signature = db.Column(db.Text, nullable=True)  # base64 data-URL

    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    created_by = db.relationship('User', foreign_keys=[created_by_id],
                                 backref=db.backref('cheque_requests', lazy='dynamic'))
    items = db.relationship('ChequeRequestItem', backref='cheque_request',
                            cascade='all, delete-orphan', lazy='select',
                            order_by='ChequeRequestItem.sn')
    status_logs = db.relationship('ChequeStatusLog', backref='cheque_request',
                                  cascade='all, delete-orphan', lazy='select',
                                  order_by='ChequeStatusLog.created_at')

    def to_dict(self, include_items=True, include_logs=False, include_signatures=True):
        data = {
            'id': self.id,
            'reference_no': self.reference_no,
            'office': self.office,
            'department': self.department,
            'status': self.status,
            'remarks': self.remarks,
            'attached_documents': self.attached_documents,
            'total_amount': self.total_amount,
            'requested_by_name': self.requested_by_name,
            'requested_date': self.requested_date.isoformat() if self.requested_date else None,
            'verified_by_name': self.verified_by_name,
            'verified_date': self.verified_date.isoformat() if self.verified_date else None,
            'approved_by_name': self.approved_by_name,
            'approved_date': self.approved_date.isoformat() if self.approved_date else None,
            'has_requested_signature': bool(self.requested_signature),
            'has_verified_signature': bool(self.verified_signature),
            'has_approved_signature': bool(self.approved_signature),
            'created_by_id': self.created_by_id,
            'created_by_name': self.created_by.full_name if self.created_by else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'item_count': len(self.items),
        }
        if include_signatures:
            data['requested_signature'] = self.requested_signature
            data['verified_signature'] = self.verified_signature
            data['approved_signature'] = self.approved_signature
        if include_items:
            data['items'] = [it.to_dict() for it in self.items]
        if include_logs:
            data['status_logs'] = [lg.to_dict() for lg in self.status_logs]
        return data

    def __repr__(self):
        return f'<ChequeRequest {self.reference_no} {self.status}>'


class ChequeRequestItem(db.Model):
    """A supplier line on a cheque request (SN / Supplier / Amount / Date / Remarks)."""
    __tablename__ = 'cheque_request_items'

    id = db.Column(db.Integer, primary_key=True)
    cheque_request_id = db.Column(db.Integer,
                                  db.ForeignKey('cheque_requests.id', ondelete='CASCADE'),
                                  nullable=False, index=True)
    sn = db.Column(db.Integer, default=1)
    supplier = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, default=0.0)
    cheque_date = db.Column(db.Date, nullable=True)
    remarks = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'cheque_request_id': self.cheque_request_id,
            'sn': self.sn,
            'supplier': self.supplier,
            'amount': self.amount,
            'cheque_date': self.cheque_date.isoformat() if self.cheque_date else None,
            'remarks': self.remarks,
        }

    def __repr__(self):
        return f'<ChequeRequestItem {self.supplier} {self.amount}>'


class ChequeStatusLog(db.Model):
    """Audit trail of cheque request status changes."""
    __tablename__ = 'cheque_status_logs'

    id = db.Column(db.Integer, primary_key=True)
    cheque_request_id = db.Column(db.Integer,
                                  db.ForeignKey('cheque_requests.id', ondelete='CASCADE'),
                                  nullable=False, index=True)
    from_status = db.Column(db.String(30), nullable=True)
    to_status = db.Column(db.String(30), nullable=False)
    changed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    note = db.Column(db.Text, nullable=True)
    email_sent = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=_utcnow)

    changed_by = db.relationship('User', foreign_keys=[changed_by_id])

    def to_dict(self):
        return {
            'id': self.id,
            'cheque_request_id': self.cheque_request_id,
            'from_status': self.from_status,
            'to_status': self.to_status,
            'changed_by_id': self.changed_by_id,
            'changed_by_name': self.changed_by.full_name if self.changed_by else None,
            'note': self.note,
            'email_sent': bool(self.email_sent),
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f'<ChequeStatusLog {self.cheque_request_id} -> {self.to_status}>'


class ChequeNotificationConfig(db.Model):
    """Per-status To/CC recipients for cheque status-change emails (admin-managed)."""
    __tablename__ = 'cheque_notification_config'

    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(30), unique=True, nullable=False)
    to_emails = db.Column(db.Text, default='')  # comma-separated
    cc_emails = db.Column(db.Text, default='')

    def to_dict(self):
        return {
            'status': self.status,
            'to_emails': self.to_emails or '',
            'cc_emails': self.cc_emails or '',
        }

    def __repr__(self):
        return f'<ChequeNotificationConfig {self.status}>'


class ReminderDispatchLog(db.Model):
    """Idempotent log for scheduled reminder / escalation emails."""
    __tablename__ = 'reminder_dispatch_logs'
    __table_args__ = (
        db.UniqueConstraint('entity_type', 'entity_id', 'milestone', name='uq_reminder_dispatch'),
    )

    id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.String(40), nullable=False, index=True)  # finance_contract, ticket, trading_invoice, ticket_project
    entity_id = db.Column(db.Integer, nullable=False, index=True)
    milestone = db.Column(db.String(60), nullable=False)  # amc_45d, amc_10d, sla_breach, payment_d25, paid_confirm
    recipients = db.Column(db.Text, nullable=True)
    sent_at = db.Column(db.DateTime, default=_utcnow, index=True)

    def __repr__(self):
        return f'<ReminderDispatchLog {self.entity_type}:{self.entity_id}:{self.milestone}>'


# Defaults matching client "New Quotation Format.xls"
QUOTATION_DEFAULT_INTRO = (
    'With reference to our site visit, we are pleased to quote for the following:'
)
QUOTATION_DEFAULT_NOTES = (
    'VAT Excluded in the quote\n'
    'Prices may change at any time and new prices will be applicable on this quotation '
    'unless the client confirmation granted and the advance payment received'
)
QUOTATION_DEFAULT_EXCLUSIONS = (
    'Any Civil work will be excluded and it will be the client scope.\n'
    'Any civil defense fees, Drawing approval/ Weqayah Fees will be borne by the client.\n'
    'Any additional requirement or variation required by the Ajman Civil Defence Authority '
    'will be quoted separately at additional cost borne by the client.'
)
QUOTATION_DEFAULT_TERMS = (
    'Validity : 10 Days\n'
    'Delivery : as per the exstock availability at the time of approval and advance payment clearance\n'
    'Payment :50% advance, 50% after completion\n'
    'Please confirm your acceptance to enable us proceed further assuring you of our best services at all times.'
)
QUOTATION_DEFAULT_SIGNATORY_NAME = 'Eng. Mahmoud Tannera'
QUOTATION_DEFAULT_SIGNATORY_EMAIL = 'mahmoud@amaanajh.com'
QUOTATION_DEFAULT_SIGNATORY_PHONE = '050-7408670'
QUOTATION_DEFAULT_SIGNOFF_LABEL = 'Thanks & Regards'


class Quotation(db.Model):
    """Sales quotation / proposal linked to a BD deal."""
    __tablename__ = 'quotations'

    id = db.Column(db.Integer, primary_key=True)
    quote_no = db.Column(db.String(50), unique=True, nullable=False, index=True)  # QT-XXXXXXXX
    ref_no = db.Column(db.String(80), nullable=True, index=True)  # Client-facing ASQ/…
    bd_project_id = db.Column(db.Integer, db.ForeignKey('bd_projects.id', ondelete='SET NULL'), nullable=True, index=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='SET NULL'), nullable=True, index=True)
    company_name = db.Column(db.String(255), nullable=False)
    contact_name = db.Column(db.String(160), nullable=True)
    contact_email = db.Column(db.String(255), nullable=True)
    kind_attn = db.Column(db.String(160), nullable=True)
    client_tel = db.Column(db.String(60), nullable=True)
    subject = db.Column(db.String(500), nullable=True)
    project_name = db.Column(db.String(255), nullable=True)
    intro_text = db.Column(db.Text, nullable=True)
    quote_date = db.Column(db.Date, nullable=False, default=lambda: _utcnow().date())
    valid_until = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(30), default='draft', index=True)  # draft / sent / pending_approval / approved / rejected / cancelled / accepted / expired
    subtotal = db.Column(db.Float, default=0.0)
    discount_amount = db.Column(db.Float, default=0.0)
    tax_pct = db.Column(db.Float, default=5.0)
    tax_amount = db.Column(db.Float, default=0.0)
    grand_total = db.Column(db.Float, default=0.0)
    amount_in_words = db.Column(db.String(400), nullable=True)
    notes = db.Column(db.Text, nullable=True)  # legacy free-form
    notes_text = db.Column(db.Text, nullable=True)
    exclusions_text = db.Column(db.Text, nullable=True)
    terms_text = db.Column(db.Text, nullable=True)
    signatory_name = db.Column(db.String(160), nullable=True)
    signatory_email = db.Column(db.String(255), nullable=True)
    signatory_phone = db.Column(db.String(60), nullable=True)
    signoff_label = db.Column(db.String(120), nullable=True)  # e.g. Thanks & Regards
    prepared_signature = db.Column(db.Text, nullable=True)
    # Approval / e-sign
    submitted_at = db.Column(db.DateTime, nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    approval_signature = db.Column(db.Text, nullable=True)
    approval_notes = db.Column(db.Text, nullable=True)
    rejected_at = db.Column(db.DateTime, nullable=True)
    rejection_notes = db.Column(db.Text, nullable=True)
    # Post-approval
    trading_invoice_id = db.Column(db.Integer, db.ForeignKey('trading_invoices.id', ondelete='SET NULL'), nullable=True)
    lpo_filename = db.Column(db.String(255), nullable=True)
    lpo_path = db.Column(db.String(512), nullable=True)
    lpo_cloud_url = db.Column(db.String(512), nullable=True)
    owner_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    bd_project = db.relationship('BDProject', foreign_keys=[bd_project_id],
                                 backref=db.backref('quotations', lazy='dynamic'))
    client = db.relationship('Client', foreign_keys=[client_id],
                             backref=db.backref('quotations', lazy='dynamic'))
    approved_by = db.relationship('User', foreign_keys=[approved_by_id])
    owner_user = db.relationship('User', foreign_keys=[owner_user_id],
                                 backref=db.backref('owned_quotations', lazy='dynamic'))
    created_by = db.relationship('User', foreign_keys=[created_by_id],
                                 backref=db.backref('created_quotations', lazy='dynamic'))
    trading_invoice = db.relationship('TradingInvoice', foreign_keys=[trading_invoice_id])
    items = db.relationship('QuotationItem', backref='quotation',
                            cascade='all, delete-orphan', lazy='select',
                            order_by='QuotationItem.id')
    attachments = db.relationship('QuotationAttachment', backref='quotation',
                                  cascade='all, delete-orphan', lazy='select',
                                  order_by='QuotationAttachment.id')

    def to_dict(self, include_items=True):
        data = {
            'id': self.id,
            'quote_no': self.quote_no,
            'ref_no': self.ref_no or self.quote_no,
            'bd_project_id': self.bd_project_id,
            'bd_project_name': self.bd_project.name if self.bd_project else None,
            'client_id': self.client_id,
            'company_name': self.company_name,
            'contact_name': self.contact_name,
            'contact_email': self.contact_email,
            'kind_attn': self.kind_attn,
            'client_tel': self.client_tel,
            'subject': self.subject,
            'project_name': self.project_name,
            'intro_text': self.intro_text or QUOTATION_DEFAULT_INTRO,
            'quote_date': self.quote_date.isoformat() if self.quote_date else None,
            'valid_until': self.valid_until.isoformat() if self.valid_until else None,
            'status': self.status,
            'subtotal': self.subtotal,
            'discount_amount': self.discount_amount or 0.0,
            'tax_pct': self.tax_pct,
            'tax_amount': self.tax_amount,
            'grand_total': self.grand_total,
            'amount_in_words': self.amount_in_words,
            'notes': self.notes,
            'notes_text': self.notes_text or QUOTATION_DEFAULT_NOTES,
            'exclusions_text': self.exclusions_text or QUOTATION_DEFAULT_EXCLUSIONS,
            'terms_text': self.terms_text or QUOTATION_DEFAULT_TERMS,
            'signatory_name': self.signatory_name or QUOTATION_DEFAULT_SIGNATORY_NAME,
            'signatory_email': self.signatory_email or QUOTATION_DEFAULT_SIGNATORY_EMAIL,
            'signatory_phone': self.signatory_phone or QUOTATION_DEFAULT_SIGNATORY_PHONE,
            'signoff_label': self.signoff_label or QUOTATION_DEFAULT_SIGNOFF_LABEL,
            'prepared_signature': self.prepared_signature,
            'has_prepared_signature': bool(self.prepared_signature),
            'submitted_at': self.submitted_at.isoformat() if self.submitted_at else None,
            'approved_at': self.approved_at.isoformat() if self.approved_at else None,
            'approved_by_id': self.approved_by_id,
            'approved_by_name': (
                (self.approved_by.full_name or self.approved_by.username)
                if self.approved_by else None
            ),
            'has_approval_signature': bool(self.approval_signature),
            'rejection_notes': self.rejection_notes,
            'trading_invoice_id': self.trading_invoice_id,
            'lpo_filename': self.lpo_filename,
            'lpo_url': self.lpo_cloud_url or (
                f'/api/admin/bd/quotations/{self.id}/lpo' if self.lpo_path else None
            ),
            'owner_user_id': self.owner_user_id,
            'created_by_id': self.created_by_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_items:
            data['items'] = [it.to_dict() for it in self.items]
            data['attachments'] = [a.to_dict() for a in self.attachments]
        return data

    def __repr__(self):
        return f'<Quotation {self.quote_no}>'


class QuotationItem(db.Model):
    __tablename__ = 'quotation_items'

    id = db.Column(db.Integer, primary_key=True)
    quotation_id = db.Column(db.Integer, db.ForeignKey('quotations.id', ondelete='CASCADE'),
                             nullable=False, index=True)
    description = db.Column(db.String(255), nullable=False)
    details = db.Column(db.Text, nullable=True)
    quantity = db.Column(db.Float, default=1.0)
    unit = db.Column(db.String(40), nullable=True)
    unit_price = db.Column(db.Float, default=0.0)
    total_price = db.Column(db.Float, default=0.0)

    def to_dict(self):
        return {
            'id': self.id,
            'quotation_id': self.quotation_id,
            'description': self.description,
            'details': self.details,
            'quantity': self.quantity,
            'unit': self.unit,
            'unit_price': self.unit_price,
            'total_price': self.total_price,
        }

    def __repr__(self):
        return f'<QuotationItem {self.id} {self.description}>'


class QuotationAttachment(db.Model):
    """Supporting documents attached to a quotation (besides LPO on header)."""
    __tablename__ = 'quotation_attachments'

    id = db.Column(db.Integer, primary_key=True)
    quotation_id = db.Column(db.Integer, db.ForeignKey('quotations.id', ondelete='CASCADE'),
                             nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(512), nullable=True)
    cloud_url = db.Column(db.String(512), nullable=True)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=_utcnow)

    uploaded_by = db.relationship('User', foreign_keys=[uploaded_by_id])

    def to_dict(self):
        return {
            'id': self.id,
            'quotation_id': self.quotation_id,
            'filename': self.filename,
            'url': self.cloud_url or (
                f'/api/admin/bd/quotations/{self.quotation_id}/attachments/{self.id}'
                if self.file_path else None
            ),
            'uploaded_at': self.uploaded_at.isoformat() if self.uploaded_at else None,
        }

    def __repr__(self):
        return f'<QuotationAttachment {self.id} {self.filename}>'


# ---------------------------------------------------------------------------
# Meeting 2: Duty/Timesheet, Attendance, Store Material Sets, Ad-hoc approvals
# ---------------------------------------------------------------------------

ATTENDANCE_DAY_STATUSES = (
    'present', 'off_day', 'emergency_leave', 'sick_leave', 'half_day',
)


class DutyTimesheetEntry(db.Model):
    """Operations duty/timesheet — hours from start/end; rate/cost Finance-only."""
    __tablename__ = 'duty_timesheet_entries'

    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    staff_name = db.Column(db.String(160), nullable=False)
    employee_id = db.Column(db.String(60), nullable=True)
    project_name = db.Column(db.String(200), nullable=False)
    project_code = db.Column(db.String(60), nullable=True)
    work_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.String(10), nullable=False)
    end_time = db.Column(db.String(10), nullable=False)
    hours = db.Column(db.Float, nullable=False, default=0.0)
    day_type = db.Column(db.String(20), nullable=True)
    rate_per_hour = db.Column(db.Float, nullable=True)
    total_amount = db.Column(db.Float, nullable=True)
    remarks = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(30), default='submitted')
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    created_by = db.relationship(
        'User', foreign_keys=[created_by_id],
        backref=db.backref('duty_timesheet_entries', lazy='dynamic'),
    )

    def to_dict(self, include_rates=False):
        d = {
            'id': self.id,
            'entry_id': self.entry_id,
            'staff_name': self.staff_name,
            'employee_id': self.employee_id,
            'project_name': self.project_name,
            'project_code': self.project_code,
            'work_date': self.work_date.isoformat() if self.work_date else None,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'hours': self.hours,
            'day_type': self.day_type,
            'remarks': self.remarks,
            'status': self.status,
            'created_by_id': self.created_by_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_rates:
            d['rate_per_hour'] = self.rate_per_hour
            d['total_amount'] = self.total_amount
        return d


class AttendanceImportBatch(db.Model):
    __tablename__ = 'attendance_import_batches'

    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    source_filename = db.Column(db.String(255), nullable=True)
    period_label = db.Column(db.String(80), nullable=True)
    row_count = db.Column(db.Integer, default=0)
    matched_count = db.Column(db.Integer, default=0)
    imported_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)

    imported_by = db.relationship('User', foreign_keys=[imported_by_id])
    entries = db.relationship(
        'AttendanceEntry', backref='batch', lazy='dynamic',
        cascade='all, delete-orphan',
    )

    def to_dict(self):
        return {
            'id': self.id,
            'batch_id': self.batch_id,
            'source_filename': self.source_filename,
            'period_label': self.period_label,
            'row_count': self.row_count,
            'matched_count': self.matched_count,
            'imported_by_id': self.imported_by_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class AttendanceEntry(db.Model):
    __tablename__ = 'attendance_entries'

    id = db.Column(db.Integer, primary_key=True)
    batch_id_fk = db.Column(db.Integer, db.ForeignKey('attendance_import_batches.id', ondelete='SET NULL'),
                            nullable=True, index=True)
    technician_id = db.Column(db.Integer, db.ForeignKey('technicians.id'), nullable=True, index=True)
    employee_code = db.Column(db.String(60), nullable=True, index=True)
    staff_name = db.Column(db.String(160), nullable=False)
    project_name = db.Column(db.String(200), nullable=True)
    team_size = db.Column(db.Integer, nullable=True)
    work_date = db.Column(db.Date, nullable=False, index=True)
    day_status = db.Column(db.String(30), default='present')
    start_time = db.Column(db.String(10), nullable=True)
    end_time = db.Column(db.String(10), nullable=True)
    hours = db.Column(db.Float, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    technician = db.relationship('Technician', foreign_keys=[technician_id])

    def to_dict(self):
        return {
            'id': self.id,
            'batch_id': self.batch.batch_id if self.batch else None,
            'technician_id': self.technician_id,
            'employee_code': self.employee_code,
            'staff_name': self.staff_name,
            'project_name': self.project_name,
            'team_size': self.team_size,
            'work_date': self.work_date.isoformat() if self.work_date else None,
            'day_status': self.day_status,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'hours': self.hours,
            'notes': self.notes,
        }


class MaterialSet(db.Model):
    __tablename__ = 'material_sets'

    id = db.Column(db.Integer, primary_key=True)
    set_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    material_type = db.Column(db.String(120), nullable=True)
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    created_by = db.relationship('User', foreign_keys=[created_by_id])
    items = db.relationship(
        'MaterialSetItem', backref='material_set',
        cascade='all, delete-orphan', lazy='select',
        order_by='MaterialSetItem.id',
    )

    def to_dict(self, include_prices=True, include_items=True):
        d = {
            'id': self.id,
            'set_id': self.set_id,
            'name': self.name,
            'material_type': self.material_type,
            'description': self.description,
            'is_active': self.is_active,
            'item_count': len(self.items) if self.items is not None else 0,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        if include_items:
            d['items'] = [it.to_dict(include_prices=include_prices) for it in self.items]
        return d


class MaterialSetItem(db.Model):
    __tablename__ = 'material_set_items'

    id = db.Column(db.Integer, primary_key=True)
    set_id_fk = db.Column(db.Integer, db.ForeignKey('material_sets.id', ondelete='CASCADE'),
                          nullable=False, index=True)
    material_name = db.Column(db.String(200), nullable=False)
    unit = db.Column(db.String(40), nullable=True)
    quantity = db.Column(db.Float, default=1.0)
    unit_price = db.Column(db.Float, default=0.0)
    procurement_ref = db.Column(db.String(50), nullable=True)

    def to_dict(self, include_prices=True):
        d = {
            'id': self.id,
            'material_name': self.material_name,
            'unit': self.unit,
            'quantity': self.quantity,
            'procurement_ref': self.procurement_ref,
        }
        if include_prices:
            d['unit_price'] = self.unit_price
            d['line_total'] = round(float(self.quantity or 0) * float(self.unit_price or 0), 2)
        return d


class AdHocMaterialRequest(db.Model):
    """Mid-job ad-hoc material — OM then GM must approve before ticket attach/price."""
    __tablename__ = 'adhoc_material_requests'

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id'), nullable=True, index=True)
    material_name = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Float, default=1.0)
    unit = db.Column(db.String(40), nullable=True)
    unit_price = db.Column(db.Float, nullable=True)
    reason = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(30), default='pending', index=True)  # pending|om_approved|approved|rejected
    requested_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    om_approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    om_approved_at = db.Column(db.DateTime, nullable=True)
    gm_approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    gm_approved_at = db.Column(db.DateTime, nullable=True)
    decided_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    decided_at = db.Column(db.DateTime, nullable=True)
    decision_note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)

    def to_dict(self, include_prices=True):
        d = {
            'id': self.id,
            'request_id': self.request_id,
            'ticket_id': self.ticket_id,
            'material_name': self.material_name,
            'quantity': self.quantity,
            'unit': self.unit,
            'reason': self.reason,
            'status': self.status,
            'requested_by_id': self.requested_by_id,
            'om_approved_by_id': self.om_approved_by_id,
            'om_approved_at': self.om_approved_at.isoformat() if self.om_approved_at else None,
            'gm_approved_by_id': self.gm_approved_by_id,
            'gm_approved_at': self.gm_approved_at.isoformat() if self.gm_approved_at else None,
            'decided_by_id': self.decided_by_id,
            'decided_at': self.decided_at.isoformat() if self.decided_at else None,
            'decision_note': self.decision_note,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        if include_prices:
            d['unit_price'] = self.unit_price
        return d



# ── Hiring Document Tracker (HR module) ──────────────────────────────────────

# Phase 1 — collected first (candidate identity / clearance)
HIRING_PHASE1_DOC_TYPES = (
    'passport',
    'emirates_id',
    'photograph',
    'pcc',
    'education_certificate',
)

# Phase 2 — unlocked only after Phase 1 is complete
HIRING_PHASE2_DOC_TYPES = (
    'offer_letter',
    'insurance',
    'e_visa',
    'contract',
)

HIRING_DOC_TYPES = HIRING_PHASE1_DOC_TYPES + HIRING_PHASE2_DOC_TYPES

HIRING_DOC_PHASE = {
    **{dt: 1 for dt in HIRING_PHASE1_DOC_TYPES},
    **{dt: 2 for dt in HIRING_PHASE2_DOC_TYPES},
}

HIRING_DOC_LABELS = {
    'passport': 'Passport Copy (Colour)',
    'emirates_id': 'Emirates ID Copy (Colour)',
    'photograph': 'Photograph (White Background, PDF)',
    'pcc': 'PCC — Attested',
    'education_certificate': 'Education Certificate (PDF)',
    'offer_letter': 'Offer Letter (Department Signed)',
    'insurance': 'Insurance Paper',
    'e_visa': 'E-Visa',
    'contract': 'Employment Contract',
}

HIRING_DOC_ALLOWED_EXT = {
    'passport': {'pdf', 'jpg', 'jpeg', 'png'},
    'emirates_id': {'pdf', 'jpg', 'jpeg', 'png'},
    'photograph': {'pdf'},
    'pcc': {'pdf'},
    'education_certificate': {'pdf'},
    'offer_letter': {'pdf'},
    'insurance': {'pdf', 'jpg', 'jpeg', 'png'},
    'e_visa': {'pdf', 'jpg', 'jpeg', 'png'},
    'contract': {'pdf'},
}

# Docs that unlock only after pipeline reaches visa_process_started
HIRING_VISA_GATED_DOC_TYPES = frozenset({'insurance', 'e_visa', 'contract'})

# Linear hiring stages only — on_hold is a process-wide pause, not a step.
HIRING_PIPELINE_STEPS = (
    'interview_completed',
    'gathering_documents',
    'preparing_offer_letter',
    'offer_letter_prepared',
    'offer_letter_signed',
    'md_signed_offer_received',
    'visa_process_started',
    'candidate_employee',
)

# Valid stored values = real steps + on_hold pause state
HIRING_PIPELINE_STATUSES = HIRING_PIPELINE_STEPS + ('on_hold',)

HIRING_PIPELINE_LABELS = {
    'interview_completed': 'Interview completed',
    'gathering_documents': 'Gathering documents',
    'preparing_offer_letter': 'Preparing offer letter',
    'offer_letter_prepared': 'Offer letter prepared',
    'offer_letter_signed': 'Offer letter signed',
    'md_signed_offer_received': 'Signed offer letter from MD received',
    'visa_process_started': 'Visa process started',
    'candidate_employee': 'Candidate employee',
    'on_hold': 'On hold',
}

HIRING_PIPELINE_DEFAULT = 'interview_completed'


class HiringCandidate(db.Model):
    """Candidate / new-hire tracked for onboarding document collection."""
    __tablename__ = 'hiring_candidates'

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(200), nullable=False, index=True)
    role = db.Column(db.String(120))  # position / job title
    department = db.Column(db.String(120))
    phone = db.Column(db.String(40))
    email = db.Column(db.String(120))
    replacement_name = db.Column(db.String(200))
    replacement_employee_id = db.Column(db.String(80))
    comments = db.Column(db.Text)
    pipeline_status = db.Column(
        db.String(40),
        default=HIRING_PIPELINE_DEFAULT,
        index=True,
    )
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow, index=True)

    creator = db.relationship('User', foreign_keys=[created_by],
                              backref=db.backref('hiring_candidates_created', lazy='dynamic'))
    documents = db.relationship(
        'HiringDocument',
        back_populates='candidate',
        cascade='all, delete-orphan',
        lazy='joined',
    )

    @staticmethod
    def doc_is_complete(doc) -> bool:
        """Whether a document counts as done for progress."""
        if not doc:
            return False
        if doc.doc_type == 'pcc':
            return doc.status in ('attested', 'verified')
        return doc.status in ('uploaded', 'attested', 'verified')

    def _docs_by_type(self):
        return {d.doc_type: d for d in (self.documents or [])}

    def phase_progress(self, doc_types):
        by_type = self._docs_by_type()
        total = len(doc_types)
        completed = sum(1 for dt in doc_types if self.doc_is_complete(by_type.get(dt)))
        return completed, total

    def phase1_complete(self) -> bool:
        completed, total = self.phase_progress(HIRING_PHASE1_DOC_TYPES)
        return completed >= total

    def normalized_pipeline_status(self) -> str:
        status = (self.pipeline_status or HIRING_PIPELINE_DEFAULT).strip()
        if status not in HIRING_PIPELINE_STATUSES:
            return HIRING_PIPELINE_DEFAULT
        return status

    def is_on_hold(self) -> bool:
        """True when the whole hiring process is paused (not a linear stage)."""
        return self.normalized_pipeline_status() == 'on_hold'

    def pipeline_index(self) -> int:
        """Index within HIRING_PIPELINE_STEPS; -1 while process is on hold."""
        status = self.normalized_pipeline_status()
        if status == 'on_hold':
            return -1
        try:
            return HIRING_PIPELINE_STEPS.index(status)
        except ValueError:
            return 0

    def visa_docs_unlocked(self) -> bool:
        """Insurance, e-visa, and contract unlock at visa_process_started (not while on hold)."""
        if self.is_on_hold():
            return False
        visa_idx = HIRING_PIPELINE_STEPS.index('visa_process_started')
        return self.pipeline_index() >= visa_idx

    def file_closed(self) -> bool:
        """True when hiring file is closed (candidate employee final stage)."""
        return self.normalized_pipeline_status() == 'candidate_employee'

    def pipeline_steps(self):
        """Linear stage chips only — excludes on_hold (process pause)."""
        current = self.normalized_pipeline_status()
        on_hold = current == 'on_hold'
        current_idx = self.pipeline_index()
        steps = []
        for i, key in enumerate(HIRING_PIPELINE_STEPS):
            steps.append({
                'key': key,
                'label': HIRING_PIPELINE_LABELS.get(key, key),
                'done': (not on_hold) and current_idx > i,
                'current': (not on_hold) and key == current,
            })
        return steps

    def progress(self):
        """Overall progress across both phases (all 9 documents)."""
        p1_done, p1_total = self.phase_progress(HIRING_PHASE1_DOC_TYPES)
        p2_done, p2_total = self.phase_progress(HIRING_PHASE2_DOC_TYPES)
        completed = p1_done + p2_done
        total = p1_total + p2_total

        if completed <= 0:
            status = 'not_started'
        elif completed >= total:
            status = 'complete'
        else:
            status = 'in_progress'
        return completed, total, status

    def initials(self) -> str:
        parts = (self.full_name or '').strip().split()
        if not parts:
            return '?'
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()

    def _placeholder_doc(self, dt):
        return {
            'id': None,
            'candidate_id': self.id,
            'doc_type': dt,
            'label': HIRING_DOC_LABELS.get(dt, dt),
            'phase': HIRING_DOC_PHASE.get(dt, 1),
            'status': 'missing',
            'filename': None,
            'mime_type': None,
            'file_size': None,
            'uploaded_at': None,
            'uploaded_by': None,
            'has_file': False,
            'is_complete': False,
            'file_url': None,
            'notes': '',
            'allowed_extensions': sorted(HIRING_DOC_ALLOWED_EXT.get(dt, set())),
        }

    def to_dict(self, include_documents=True):
        completed, total, status = self.progress()
        p1_done, p1_total = self.phase_progress(HIRING_PHASE1_DOC_TYPES)
        p2_done, p2_total = self.phase_progress(HIRING_PHASE2_DOC_TYPES)
        pipeline = self.normalized_pipeline_status()
        visa_unlocked = self.visa_docs_unlocked()
        d = {
            'id': self.id,
            'full_name': self.full_name,
            'role': self.role or '',
            'department': self.department or '',
            'phone': self.phone or '',
            'email': self.email or '',
            'replacement_name': self.replacement_name or '',
            'replacement_employee_id': self.replacement_employee_id or '',
            'comments': self.comments or '',
            'initials': self.initials(),
            'completed': completed,
            'total': total,
            'progress_label': f'{completed}/{total}',
            'status': status,
            'pipeline_status': pipeline,
            'pipeline_label': HIRING_PIPELINE_LABELS.get(pipeline, pipeline),
            'pipeline_steps': self.pipeline_steps(),
            'is_on_hold': pipeline == 'on_hold',
            'file_closed': pipeline == 'candidate_employee',
            'visa_docs_unlocked': visa_unlocked,
            'phase1_completed': p1_done,
            'phase1_total': p1_total,
            'phase2_completed': p2_done,
            'phase2_total': p2_total,
            'phase2_unlocked': True,
            'created_by': self.created_by,
            'created_at': naive_utc_isoformat_z(self.created_at) if self.created_at else None,
            'updated_at': naive_utc_isoformat_z(self.updated_at) if self.updated_at else None,
        }
        if include_documents:
            by_type = self._docs_by_type()
            docs = []
            for dt in HIRING_DOC_TYPES:
                doc = by_type.get(dt)
                if doc:
                    item = doc.to_dict()
                else:
                    item = self._placeholder_doc(dt)
                item['upload_locked'] = (
                    dt in HIRING_VISA_GATED_DOC_TYPES and not visa_unlocked
                )
                docs.append(item)
            d['documents'] = docs
            d['phase1_documents'] = [x for x in docs if x.get('phase') == 1]
            d['phase2_documents'] = [x for x in docs if x.get('phase') == 2]
        return d

    def __repr__(self):
        return f'<HiringCandidate {self.id} {self.full_name}>'


class HiringDocument(db.Model):
    """One onboarding document slot for a hiring candidate."""
    __tablename__ = 'hiring_documents'

    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(
        db.Integer,
        db.ForeignKey('hiring_candidates.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    doc_type = db.Column(db.String(40), nullable=False, index=True)
    filename = db.Column(db.String(255))
    file_path = db.Column(db.String(500))
    cloud_url = db.Column(db.String(500))
    mime_type = db.Column(db.String(100))
    file_size = db.Column(db.Integer)
    status = db.Column(db.String(20), default='missing', index=True)  # missing|uploaded|attested|verified
    notes = db.Column(db.Text)  # optional per-doc note (UI currently for offer letter)
    uploaded_at = db.Column(db.DateTime)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    __table_args__ = (
        db.UniqueConstraint('candidate_id', 'doc_type', name='uq_hiring_candidate_doc_type'),
    )

    candidate = db.relationship('HiringCandidate', back_populates='documents')
    uploader = db.relationship('User', foreign_keys=[uploaded_by],
                               backref=db.backref('hiring_documents_uploaded', lazy='dynamic'))

    def has_file(self) -> bool:
        return bool(self.cloud_url or self.file_path)

    def file_url(self):
        if self.id and self.has_file():
            return f'/hr/api/hiring/documents/{self.id}/file'
        return None

    def to_dict(self):
        return {
            'id': self.id,
            'candidate_id': self.candidate_id,
            'doc_type': self.doc_type,
            'label': HIRING_DOC_LABELS.get(self.doc_type, self.doc_type),
            'phase': HIRING_DOC_PHASE.get(self.doc_type, 1),
            'filename': self.filename,
            'mime_type': self.mime_type,
            'file_size': self.file_size,
            'status': self.status or 'missing',
            'uploaded_at': self.uploaded_at.isoformat() if self.uploaded_at else None,
            'uploaded_by': self.uploaded_by,
            'uploader_name': (
                self.uploader.full_name or self.uploader.username
                if self.uploader else None
            ),
            'has_file': self.has_file(),
            'is_complete': HiringCandidate.doc_is_complete(self),
            'file_url': self.file_url(),
            'notes': self.notes or '',
            'allowed_extensions': sorted(HIRING_DOC_ALLOWED_EXT.get(self.doc_type, set())),
        }

    def __repr__(self):
        return f'<HiringDocument {self.id} {self.doc_type} cand={self.candidate_id}>'

