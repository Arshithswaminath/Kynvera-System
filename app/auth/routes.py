"""
Authentication Routes - JWT-based authentication
"""
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import (
    create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity, get_jwt, get_jti
)
from datetime import datetime, timedelta, timezone
from app.models import db, User, Session, AuditLog
from sqlalchemy.exc import IntegrityError
from common.error_responses import error_response, success_response
import re

auth_bp = Blueprint('auth_bp', __name__, url_prefix='/api/auth')


def get_limiter():
    """Get rate limiter from current app"""
    try:
        return current_app.limiter
    except (AttributeError, RuntimeError):
        return None


def rate_limit_if_available(limit_str):
    """Decorator to apply rate limiting if limiter is available"""
    def decorator(f):
        limiter = get_limiter()
        if limiter:
            return limiter.limit(limit_str)(f)
        return f
    return decorator


def validate_email(email):
    """Basic email validation"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_password(password):
    """Password strength validation (min 8 chars, 1 upper, 1 lower, 1 digit)"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r'\d', password):
        return False, "Password must contain at least one digit"
    return True, "Password is strong"


def validate_phone(phone):
    """Basic mobile number validation (digits, spaces, + - ( ) allowed)."""
    cleaned = re.sub(r'[\s\-().+]', '', phone or '')
    if len(cleaned) < 7 or len(cleaned) > 15:
        return False
    return cleaned.isdigit()


def generate_unique_username(email, first_name='', last_name=''):
    """Derive a unique username from email or name."""
    local = (email or '').split('@')[0].lower()
    base = re.sub(r'[^a-z0-9._-]', '', local)
    if not base:
        combined = f"{first_name}{last_name}".lower()
        base = re.sub(r'[^a-z0-9._-]', '', combined) or 'user'
    base = base[:72]
    candidate = base
    suffix = 1
    while User.query.filter(db.func.lower(User.username) == candidate.lower()).first():
        suffix += 1
        candidate = f"{base[:70]}{suffix}"
    return candidate


def log_audit(user_id, action, resource_type=None, resource_id=None, details=None):
    """Create audit log entry"""
    try:
        log = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
            details=details
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        current_app.logger.error(f"Failed to create audit log: {str(e)}")


@auth_bp.route('/register', methods=['POST'])
@rate_limit_if_available('5 per minute')
def register():
    """Register a new user (self-service wizard — default password assigned server-side)."""
    try:
        from common.datetime_utils import parse_employment_start_date
        from common.password_admin import get_default_registration_password

        data = request.get_json(force=True, silent=True)

        if not data:
            return error_response('Invalid JSON or missing request body', 400, 'INVALID_REQUEST')

        first_name = (data.get('first_name') or '').strip()
        last_name = (data.get('last_name') or '').strip()
        email = (data.get('email') or '').strip().lower()
        phone = (data.get('mobile_number') or data.get('phone') or '').strip()
        project_name = (data.get('project_name') or data.get('assigned_project') or '').strip()
        job_designation = (data.get('job_designation') or data.get('designation') or '').strip()
        employment_start_date_raw = data.get('employment_start_date') or data.get('join_date')

        # Legacy API support (username/password/full_name)
        legacy_full_name = (data.get('full_name') or '').strip()
        legacy_username = (data.get('username') or '').strip()
        legacy_password = data.get('password')

        if not first_name and legacy_full_name:
            parts = legacy_full_name.split(None, 1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else ''

        if not first_name:
            return error_response('First name is required', 400, 'VALIDATION_ERROR')
        if not email:
            return error_response('Email is required', 400, 'VALIDATION_ERROR')
        if not phone:
            return error_response('Mobile number is required', 400, 'VALIDATION_ERROR')
        if not project_name:
            return error_response('Project name is required', 400, 'VALIDATION_ERROR')
        if not job_designation:
            return error_response('Designation is required', 400, 'VALIDATION_ERROR')
        if not employment_start_date_raw:
            return error_response('Join date is required', 400, 'VALIDATION_ERROR')

        if not validate_email(email):
            return error_response('Invalid email format', 400, 'VALIDATION_ERROR')
        if not validate_phone(phone):
            return error_response('Invalid mobile number', 400, 'VALIDATION_ERROR')

        try:
            employment_start_date = parse_employment_start_date(employment_start_date_raw)
        except ValueError as ve:
            return error_response(str(ve), 400, 'VALIDATION_ERROR')

        if User.query.filter_by(email=email).first():
            return error_response('Email already registered', 409, 'DUPLICATE_EMAIL')

        if legacy_username:
            username, username_error = _normalize_username(legacy_username)
            if username_error:
                return error_response(username_error, 400, 'VALIDATION_ERROR')
        else:
            username = generate_unique_username(email, first_name, last_name)
        if User.query.filter(db.func.lower(User.username) == username.lower()).first():
            return error_response('Username already exists', 409, 'DUPLICATE_USERNAME')

        if legacy_password:
            password = legacy_password
            is_valid, message = validate_password(password)
            if not is_valid:
                return error_response(message, 400, 'WEAK_PASSWORD')
            password_changed = True
        else:
            password = get_default_registration_password()
            password_changed = False

        full_name = f"{first_name} {last_name}".strip()

        from common.password_policy import assign_user_password

        # Create new user
        user = User(
            username=username,
            email=email,
            full_name=full_name,
            role='user',  # Default role
            phone=phone,
            assigned_project=project_name,
            job_designation=job_designation[:160],
            employment_start_date=employment_start_date,
        )
        assign_user_password(user, password, is_temp=not password_changed)

        db.session.add(user)
        db.session.commit()

        # Log registration
        log_audit(user.id, 'register', 'user', str(user.id))

        email_sent = False
        try:
            from common.email_service import send_welcome_email
            email_sent = bool(send_welcome_email(
                user_email=user.email,
                username=user.username,
                temp_password=password,
                full_name=user.full_name,
            ))
        except Exception as email_error:
            current_app.logger.warning(f"Failed to send welcome email: {email_error}")

        return jsonify({
            'message': 'User registered successfully',
            'user': user.to_client_dict(),
            'default_password': password if not password_changed else None,
            'login_hint': email,
            'email_sent': email_sent,
        }), 201

    except IntegrityError:
        db.session.rollback()
        return error_response('User already exists', 409, 'DUPLICATE_USER')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Registration error: {str(e)}")
        return error_response('Registration failed', 500, 'INTERNAL_ERROR')


@auth_bp.route('/login', methods=['POST'])
@rate_limit_if_available('5 per minute')
def login():
    """Authenticate user and return JWT tokens"""
    try:
        # Debug logging
        current_app.logger.info(f"Login attempt - Content-Type: {request.content_type}")
        current_app.logger.info(f"Request data: {request.get_data(as_text=True)[:200]}")
        
        data = request.get_json(force=True, silent=True)
        
        if not data:
            current_app.logger.error("Failed to parse JSON from request")
            return error_response('Invalid JSON or missing request body', 400, 'INVALID_REQUEST')
        
        # Validate required fields
        if not data.get('username') or not data.get('password'):
            current_app.logger.warning(f"Missing credentials - username: {bool(data.get('username'))}, password: {bool(data.get('password'))}")
            return error_response('Username and password are required', 400, 'VALIDATION_ERROR')
        
        username = data['username'].strip()
        password = data['password']
        login_key = username.lower()
        
        # Username / email: case-insensitive (Arshith, arshith, ARSHITH all work)
        user = User.query.filter(
            (db.func.lower(User.username) == login_key)
            | (db.func.lower(User.email) == login_key)
        ).first()

        if not user:
            # Full name is not unique — match case-insensitively, then resolve by password
            name_matches = User.query.filter(
                db.func.lower(User.full_name) == login_key
            ).all()
            if len(name_matches) == 1:
                user = name_matches[0]
            elif len(name_matches) > 1:
                user = next((u for u in name_matches if u.check_password(password)), None)
        
        if not user or not user.check_password(password):
            # Log failed attempt
            log_audit(None, 'login_failed', details={'username': username})
            return error_response('Invalid username or password', 401, 'INVALID_CREDENTIALS')
        
        if not user.is_active:
            return error_response('Account is disabled', 403, 'ACCOUNT_DISABLED')

        from common.password_policy import (
            password_policy_flags,
            should_lock_for_password_age,
        )

        # Password age lock (day 66+): block login until admin unlocks
        if getattr(user, 'password_locked', False) or should_lock_for_password_age(user):
            if not getattr(user, 'password_locked', False):
                user.password_locked = True
                db.session.commit()
            return error_response(
                'Account locked because the password expired. Please contact an administrator to unlock.',
                403,
                'PASSWORD_EXPIRED_LOCKED',
            )
        
        # Check if password change is required (default admin password)
        password_change_required = not user.password_changed if hasattr(user, 'password_changed') else False
        
        # Update last login
        user.last_login = datetime.now(timezone.utc)
        db.session.commit()

        # Create tokens
        access_token = create_access_token(identity=str(user.id))
        refresh_token = create_refresh_token(identity=str(user.id))

        # Store session for token revocation — use get_jti instead of decode_token
        # because decode_token key names vary across flask-jwt-extended versions.
        access_jti = get_jti(access_token)
        jwt_expires = current_app.config.get('JWT_ACCESS_TOKEN_EXPIRES') or timedelta(hours=1)
        access_exp = datetime.now(timezone.utc) + jwt_expires
        
        session = Session(
            user_id=user.id,
            token_jti=access_jti,
            expires_at=access_exp
        )
        db.session.add(session)
        db.session.commit()
        
        # Log successful login
        log_audit(user.id, 'login', 'user', str(user.id))
        
        # Check if password needs to be changed (for default admin)
        requires_password_change = not user.password_changed
        flags = password_policy_flags(user)
        
        # Create response
        response = jsonify({
            'message': 'Login successful',
            'access_token': access_token,
            'refresh_token': refresh_token,
            'user': user.to_client_dict(),
            'requires_password_change': requires_password_change,
            'password_expiry_warning': flags['password_expiry_warning'],
            'password_days_remaining': flags['password_days_remaining'],
            'temp_password_reminder': flags['temp_password_reminder'],
        })
        
        # Set JWT tokens in cookies for HTML link access
        from flask_jwt_extended import set_access_cookies, set_refresh_cookies
        set_access_cookies(response, access_token)
        set_refresh_cookies(response, refresh_token)
        
        return response, 200
        
    except Exception as e:
        current_app.logger.error(f"Login error: {str(e)}", exc_info=True)
        # Provide more helpful error message for database schema issues
        error_msg = 'Login failed'
        error_code = 'INTERNAL_ERROR'
        if 'does not exist' in str(e) or 'UndefinedColumn' in str(e):
            error_msg = 'Database schema error - please contact administrator'
            error_code = 'DATABASE_ERROR'
            current_app.logger.error("Database schema appears to be out of date. Migration may be needed.")
        return error_response(error_msg, 500, error_code, str(e) if current_app.debug else None)


@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """Refresh access token using refresh token"""
    try:
        user_id = get_jwt_identity()
        user = db.session.get(User, int(user_id))
        
        if not user or not user.is_active:
            return error_response('User not found or inactive', 404, 'USER_NOT_FOUND')
        
        # Create new access token
        access_token = create_access_token(identity=user_id)

        # Store new session
        access_jti = get_jti(access_token)
        jwt_expires = current_app.config.get('JWT_ACCESS_TOKEN_EXPIRES') or timedelta(hours=1)
        access_exp = datetime.now(timezone.utc) + jwt_expires
        
        session = Session(
            user_id=int(user_id),
            token_jti=access_jti,
            expires_at=access_exp
        )
        db.session.add(session)
        db.session.commit()
        
        # Keep httpOnly access cookie in sync with JSON token. Stale cookie + fresh Bearer in
        # localStorage can confuse JWT resolution on multipart/API requests (DocHub upload 401 loop).
        from flask_jwt_extended import set_access_cookies
        response = jsonify({'access_token': access_token})
        set_access_cookies(response, access_token)
        return response, 200
        
    except Exception as e:
        current_app.logger.error(f"Token refresh error: {str(e)}")
        return error_response('Token refresh failed', 500, 'INTERNAL_ERROR')


@auth_bp.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    """Logout user and revoke token"""
    try:
        user_id = get_jwt_identity()
        jti = get_jwt()['jti']
        
        # Revoke current session
        session = Session.query.filter_by(token_jti=jti).first()
        if session:
            session.is_revoked = True
            db.session.commit()
        
        # Log logout
        log_audit(int(user_id), 'logout', 'user', user_id)
        
        # Create response and unset cookies
        response = jsonify({'message': 'Logout successful'})
        from flask_jwt_extended import unset_jwt_cookies
        unset_jwt_cookies(response)
        
        return response, 200
        
    except Exception as e:
        current_app.logger.error(f"Logout error: {str(e)}")
        return error_response('Logout failed', 500, 'INTERNAL_ERROR')


@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def get_current_user():
    """Get current user profile"""
    try:
        from common.password_policy import password_policy_flags

        user_id = get_jwt_identity()
        user = db.session.get(User, int(user_id))
        
        if not user:
            return error_response('User not found', 404, 'USER_NOT_FOUND')

        flags = password_policy_flags(user)
        return jsonify({
            'user': user.to_client_dict(),
            'requires_password_change': not bool(getattr(user, 'password_changed', True)),
            'password_expiry_warning': flags['password_expiry_warning'],
            'password_days_remaining': flags['password_days_remaining'],
            'temp_password_reminder': flags['temp_password_reminder'],
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Get user error: {str(e)}")
        return error_response('Failed to fetch user', 500, 'INTERNAL_ERROR')


def _normalize_username(raw):
    """Validate and normalize a self-service username change."""
    username = (raw or '').strip().lower()
    if not username:
        return None, 'Username is required'
    if len(username) < 3:
        return None, 'Username must be at least 3 characters'
    if len(username) > 80:
        return None, 'Username must be 80 characters or fewer'
    if not re.fullmatch(r'[a-z0-9._-]+', username):
        return None, 'Username can only use letters, numbers, dots, underscores, and hyphens'
    if username.startswith('.') or username.endswith('.'):
        return None, 'Username cannot start or end with a dot'
    return username, None


@auth_bp.route('/profile', methods=['PUT'])
@jwt_required()
def update_own_profile():
    """Update fields the user manages: username, full name, employment start date."""
    try:
        from common.datetime_utils import parse_employment_start_date

        user_id = get_jwt_identity()
        user = db.session.get(User, int(user_id))
        if not user:
            return error_response('User not found', 404, 'USER_NOT_FOUND')

        data = request.get_json(force=True, silent=True) or {}
        old_username = user.username
        username_changed = False

        if 'username' in data:
            new_username, username_error = _normalize_username(data.get('username'))
            if username_error:
                return error_response(username_error, 400, 'VALIDATION_ERROR')
            if new_username != (user.username or '').lower():
                taken = User.query.filter(
                    db.func.lower(User.username) == new_username,
                    User.id != user.id,
                ).first()
                if taken:
                    return error_response('That username is already taken', 409, 'DUPLICATE_USERNAME')
                user.username = new_username
                username_changed = True

        if 'full_name' in data:
            fn = data.get('full_name')
            user.full_name = (fn or '').strip() or None

        if 'employment_start_date' in data:
            try:
                user.employment_start_date = parse_employment_start_date(data.get('employment_start_date'))
            except ValueError as ve:
                return error_response(str(ve), 400, 'VALIDATION_ERROR')

        db.session.commit()

        email_sent = False
        if username_changed:
            log_audit(
                user.id,
                'username_changed',
                'user',
                str(user.id),
                details={'old_username': old_username, 'new_username': user.username},
            )
            try:
                from common.email_service import send_username_changed_email
                email_sent = bool(send_username_changed_email(
                    user_email=user.email,
                    old_username=old_username,
                    new_username=user.username,
                    full_name=user.full_name,
                ))
            except Exception as email_error:
                current_app.logger.warning(
                    'Failed to send username-change email: %s', email_error
                )

        return jsonify({
            'success': True,
            'user': user.to_client_dict(),
            'username_changed': username_changed,
            'email_sent': email_sent,
        }), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Update profile error: {str(e)}")
        return error_response('Failed to update profile', 500, 'INTERNAL_ERROR')


@auth_bp.route('/signature-default', methods=['POST'])
@jwt_required()
def update_signature_default():
    """Update user's default signature and comment"""
    try:
        user_id = get_jwt_identity()
        user = db.session.get(User, int(user_id))
        if not user:
            return error_response('User not found', 404, 'USER_NOT_FOUND')

        data = request.get_json() or {}
        signature_data = data.get('signature_data_url')
        default_comment = data.get('default_comment')
        remove_default = bool(data.get('remove_default'))

        storage = 'cloudinary'
        if remove_default:
            user.default_signature = None
            user.default_comment = None
        else:
            if signature_data:
                from app.services.cloudinary_service import upload_base64_signature
                signature_url = upload_base64_signature(signature_data, f"user_{user.id}")
                if not signature_url:
                    if current_app.config.get('FLASK_ENV', 'development') == 'development':
                        storage = 'inline'
                        user.default_signature = signature_data
                    else:
                        return error_response('Failed to upload signature. Check Cloudinary configuration.', 500, 'UPLOAD_ERROR')
                else:
                    user.default_signature = signature_url
            if default_comment is not None:
                user.default_comment = default_comment

        db.session.commit()

        return jsonify({
            'message': 'Default signature updated',
            'default_signature': user.default_signature,
            'default_comment': user.default_comment,
            'storage': storage
        }), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Update signature default error: {str(e)}")
        return error_response('Failed to update default signature', 500, 'INTERNAL_ERROR')


@auth_bp.route('/change-password', methods=['POST'])
@jwt_required()
def change_password():
    """Change user password"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        
        if not data.get('current_password') or not data.get('new_password'):
            return error_response('Current and new passwords are required', 400, 'VALIDATION_ERROR')
        
        user = db.session.get(User, int(user_id))
        if not user:
            return error_response('User not found', 404, 'USER_NOT_FOUND')
        
        # Verify current password
        if not user.check_password(data['current_password']):
            return error_response('Current password is incorrect', 401, 'INVALID_PASSWORD')
        
        # Validate new password
        is_valid, message = validate_password(data['new_password'])
        if not is_valid:
            return error_response(message, 400, 'WEAK_PASSWORD')
        
        from common.password_policy import assign_user_password

        # Update password — clears admin-visible temp and restarts 65-day clock
        assign_user_password(user, data['new_password'], is_temp=False)
        db.session.commit()
        
        # Revoke all existing sessions (force re-login)
        Session.query.filter_by(user_id=user_id, is_revoked=False).update({'is_revoked': True})
        db.session.commit()
        
        # Log password change
        log_audit(user_id, 'change_password', 'user', str(user_id))
        
        return jsonify({'message': 'Password changed successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Change password error: {str(e)}")
        return error_response('Password change failed', 500, 'INTERNAL_ERROR')


@auth_bp.route('/forgot-password/request-otp', methods=['POST'])
@rate_limit_if_available('5 per minute')
def forgot_password_request_otp():
    """Send a password-reset OTP to the account email (does not reveal whether the account exists)."""
    from common.email_otp import (
        PURPOSE_PASSWORD_RESET,
        EmailOtpError,
        mask_email,
        request_otp,
        resolve_user_for_password_reset,
    )

    try:
        data = request.get_json(silent=True) or {}
        identifier = (data.get('username') or data.get('email') or data.get('identifier') or '').strip()
        if not identifier:
            return error_response(
                'Username or email is required',
                status_code=400,
                error_code='VALIDATION_ERROR',
            )

        generic = {
            'sent': True,
            'message': (
                'If an account matches that username or email, a verification code has been sent.'
            ),
        }
        user = resolve_user_for_password_reset(identifier)
        if not user:
            # Same shape as a successful send to avoid account enumeration
            return success_response(generic)

        try:
            result = request_otp(user, PURPOSE_PASSWORD_RESET, ip=request.remote_addr)
        except EmailOtpError as e:
            if e.error_code in ('EMAIL_NOT_CONFIGURED', 'EMAIL_SEND_FAILED', 'RATE_LIMITED', 'NO_EMAIL'):
                return error_response(e.message, status_code=e.status_code, error_code=e.error_code)
            # Soft-fail other cases with generic success
            return success_response(generic)

        log_audit(user.id, 'password_reset_otp_sent', 'user', str(user.id), {
            'masked_email': result.get('masked_email'),
        })
        return success_response({
            'sent': True,
            'masked_email': result.get('masked_email') or mask_email(user.email),
            'expires_in': result.get('expires_in'),
            'message': 'If an account matches that username or email, a verification code has been sent.',
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'forgot_password_request_otp: {e}', exc_info=True)
        return error_response('Failed to process request', status_code=500, error_code='INTERNAL_ERROR')


@auth_bp.route('/forgot-password/verify-otp', methods=['POST'])
@rate_limit_if_available('10 per minute')
def forgot_password_verify_otp():
    """Verify password-reset OTP and return a short-lived reset grant."""
    from common.email_otp import (
        PURPOSE_PASSWORD_RESET,
        EmailOtpError,
        resolve_user_for_password_reset,
        verify_otp,
    )

    try:
        data = request.get_json(silent=True) or {}
        identifier = (data.get('username') or data.get('email') or data.get('identifier') or '').strip()
        code = data.get('code') or ''
        user = resolve_user_for_password_reset(identifier)
        if not user:
            return error_response(
                'Incorrect or expired code.',
                status_code=403,
                error_code='OTP_INVALID',
            )
        result = verify_otp(user, PURPOSE_PASSWORD_RESET, code)
        log_audit(user.id, 'password_reset_otp_verified', 'user', str(user.id))
        return success_response(result, message='Code verified')
    except EmailOtpError as e:
        return error_response(e.message, status_code=e.status_code, error_code=e.error_code)
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'forgot_password_verify_otp: {e}', exc_info=True)
        return error_response('Failed to verify code', status_code=500, error_code='INTERNAL_ERROR')


@auth_bp.route('/forgot-password/reset', methods=['POST'])
@rate_limit_if_available('5 per minute')
def forgot_password_reset():
    """Set a new password using a verified reset grant token."""
    from common.email_otp import PURPOSE_PASSWORD_RESET, verify_reset_grant
    from common.password_policy import assign_user_password

    try:
        data = request.get_json(silent=True) or {}
        reset_token = (data.get('reset_token') or '').strip()
        new_password = data.get('new_password') or ''
        confirm_password = data.get('confirm_password')
        if confirm_password is not None and new_password != confirm_password:
            return error_response(
                'Password confirmation does not match',
                status_code=400,
                error_code='VALIDATION_ERROR',
            )

        is_valid, message = validate_password(new_password)
        if not is_valid:
            return error_response(message, status_code=400, error_code='WEAK_PASSWORD')

        secret = current_app.config.get('SECRET_KEY') or current_app.config.get('JWT_SECRET_KEY')
        if not secret:
            return error_response('Server misconfigured', status_code=500, error_code='CONFIG_ERROR')

        user_id = verify_reset_grant(secret, reset_token, PURPOSE_PASSWORD_RESET)
        if user_id is None:
            return error_response(
                'Reset session expired. Request a new verification code.',
                status_code=403,
                error_code='RESET_TOKEN_INVALID',
            )

        user = db.session.get(User, int(user_id))
        if not user or not getattr(user, 'is_active', True):
            return error_response('User not found', status_code=404, error_code='NOT_FOUND')

        assign_user_password(user, new_password, is_temp=False)
        # Clear age lock if present so they can sign in immediately
        if hasattr(user, 'password_locked'):
            user.password_locked = False
        db.session.commit()

        Session.query.filter_by(user_id=user.id, is_revoked=False).update({'is_revoked': True})
        db.session.commit()

        log_audit(user.id, 'password_reset_via_otp', 'user', str(user.id))
        return success_response({
            'username': user.username,
        }, message='Password updated. You can sign in now.')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'forgot_password_reset: {e}', exc_info=True)
        return error_response('Failed to reset password', status_code=500, error_code='INTERNAL_ERROR')