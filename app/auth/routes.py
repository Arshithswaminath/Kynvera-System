"""
Authentication Routes - JWT-based authentication
"""
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import (
    create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity, get_jwt, get_jti
)
from datetime import datetime, timedelta, timezone
from functools import wraps
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
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
    """Apply Flask-Limiter lazily so blueprint import can happen before limiter init.

    Decorating at import time used to call current_app before create_app() had
    attached the limiter, so login/register permanently skipped the 5/minute cap.
    """
    def decorator(f):
        limited_view = None

        @wraps(f)
        def wrapped(*args, **kwargs):
            nonlocal limited_view
            limiter = get_limiter()
            if limiter is None:
                return f(*args, **kwargs)
            if limited_view is None:
                limited_view = limiter.limit(limit_str)(f)
            return limited_view(*args, **kwargs)

        return wrapped
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
    while User.query.filter_by(username=candidate).first():
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


PASSWORD_RESET_SALT = 'kynvera-password-reset'
PASSWORD_RESET_MAX_AGE = 60 * 60  # 1 hour


def _password_reset_serializer():
    secret = current_app.config.get('JWT_SECRET_KEY') or current_app.config.get('SECRET_KEY')
    return URLSafeTimedSerializer(secret, salt=PASSWORD_RESET_SALT)


def make_password_reset_token(user_id):
    return _password_reset_serializer().dumps({'uid': int(user_id)})


def load_password_reset_token(token, max_age=PASSWORD_RESET_MAX_AGE):
    data = _password_reset_serializer().loads(token, max_age=max_age)
    return int(data['uid'])


def _jwt_payloads_from_request():
    """Best-effort JWT claims from Authorization header and access/refresh cookies.

    Used by logout so we can revoke sessions even when the token is already
    expired or revoked — @jwt_required() would 401 and skip cookie clearing.
    """
    import jwt as pyjwt

    candidates = []
    auth = request.headers.get('Authorization') or ''
    if auth.lower().startswith('bearer '):
        candidates.append(auth.split(' ', 1)[1].strip())
    for cookie_key in (
        current_app.config.get('JWT_ACCESS_COOKIE_NAME', 'access_token_cookie'),
        current_app.config.get('JWT_REFRESH_COOKIE_NAME', 'refresh_token_cookie'),
    ):
        value = request.cookies.get(cookie_key)
        if value:
            candidates.append(value)

    secret = current_app.config.get('JWT_SECRET_KEY')
    algorithm = current_app.config.get('JWT_ALGORITHM', 'HS256')
    payloads = []
    seen = set()
    for raw in candidates:
        if not raw or raw in seen:
            continue
        seen.add(raw)
        try:
            payloads.append(pyjwt.decode(
                raw,
                secret,
                algorithms=[algorithm],
                options={'verify_exp': False, 'verify_aud': False},
            ))
        except Exception:
            continue
    return payloads


@auth_bp.route('/register', methods=['POST'])
@rate_limit_if_available('5 per minute')
def register():
    """Register a new user (self-service wizard — default password assigned server-side)."""
    if not current_app.config.get('ALLOW_PUBLIC_REGISTRATION'):
        return error_response(
            'Public registration is closed. Ask your administrator to create an account.',
            403,
            'REGISTRATION_DISABLED',
        )
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

        # Legacy API support
        legacy_full_name = (data.get('full_name') or '').strip()
        legacy_username = (data.get('username') or '').strip()
        legacy_password = data.get('password')

        if not first_name and legacy_full_name:
            parts = legacy_full_name.split(None, 1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else ''

        if not first_name or not last_name:
            return error_response('First name and last name are required', 400, 'VALIDATION_ERROR')
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

        username = legacy_username or generate_unique_username(email, first_name, last_name)
        if User.query.filter_by(username=username).first():
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

        user = User(
            username=username,
            email=email,
            full_name=full_name,
            role='user',
            phone=phone,
            assigned_project=project_name,
            job_designation=job_designation[:160],
            employment_start_date=employment_start_date,
            password_changed=password_changed,
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        log_audit(user.id, 'register', 'user', str(user.id))
        
        return jsonify({
            'message': 'User registered successfully',
            'user': user.to_client_dict(),
            'default_password': password if not password_changed else None,
            'login_hint': email,
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
        # Do not log the request body — it contains plaintext credentials.
        # Only record the originating IP so failed-login audits stay useful.
        current_app.logger.info(f"Login attempt from {request.remote_addr}")

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
        username_key = username.lower()
        
        # Find user (support login with email or username; case-insensitive)
        user = User.query.filter(
            (db.func.lower(User.username) == username_key)
            | (db.func.lower(User.email) == username_key)
        ).first()
        
        if not user or not user.check_password(password):
            # Log failed attempt
            log_audit(None, 'login_failed', details={'username': username})
            return error_response('Invalid username or password', 401, 'INVALID_CREDENTIALS')
        
        if not user.is_active:
            return error_response('Account is disabled', 403, 'ACCOUNT_DISABLED')

        # MFA challenge — if enabled, require TOTP before issuing tokens
        if getattr(user, 'mfa_enabled', False) and getattr(user, 'mfa_secret', None):
            mfa_code = (data.get('mfa_code') or data.get('otp') or '').strip()
            if not mfa_code:
                return success_response({
                    'mfa_required': True,
                    'message': 'MFA code required',
                    'user_id': user.id,
                }, message='MFA required')
            try:
                import pyotp
                totp = pyotp.TOTP(user.mfa_secret)
                if not totp.verify(mfa_code, valid_window=1):
                    log_audit(user.id, 'mfa_failed', 'user', str(user.id))
                    return error_response('Invalid MFA code', 401, 'INVALID_MFA')
            except ImportError:
                current_app.logger.error('pyotp not installed — MFA check skipped')
            except Exception as exc:
                current_app.logger.error('MFA verify error: %s', exc)
                return error_response('MFA verification failed', 401, 'INVALID_MFA')

        # Admin override: keep plaintext copy for Manage profile when user signs in.
        from common.password_admin import capture_admin_visible_password
        capture_admin_visible_password(user, password)
        
        # Check if password change is required (default admin password)
        password_change_required = not user.password_changed if hasattr(user, 'password_changed') else False
        
        # Update last login
        user.last_login = datetime.now(timezone.utc)
        db.session.commit()

        # Create tokens
        access_token = create_access_token(identity=str(user.id))
        refresh_token = create_refresh_token(identity=str(user.id))

        # Record both the access and refresh JTIs so the blocklist loader can
        # revoke each independently. Tracking the refresh JTI is what lets
        # /logout actually invalidate it — otherwise a stolen refresh token
        # would mint new access tokens until natural expiry (~7 days).
        access_jti = get_jti(access_token)
        refresh_jti = get_jti(refresh_token)
        jwt_access_expires = current_app.config.get('JWT_ACCESS_TOKEN_EXPIRES') or timedelta(hours=1)
        jwt_refresh_expires = current_app.config.get('JWT_REFRESH_TOKEN_EXPIRES') or timedelta(days=7)
        now_utc = datetime.now(timezone.utc)
        db.session.add(Session(user_id=user.id, token_jti=access_jti, expires_at=now_utc + jwt_access_expires))
        db.session.add(Session(user_id=user.id, token_jti=refresh_jti, expires_at=now_utc + jwt_refresh_expires))
        db.session.commit()
        
        # Log successful login
        log_audit(user.id, 'login', 'user', str(user.id))
        
        # Check if password needs to be changed (for default admin)
        requires_password_change = not user.password_changed
        
        # Create response
        response = jsonify({
            'message': 'Login successful',
            'access_token': access_token,
            'refresh_token': refresh_token,
            'user': user.to_client_dict(),
            'requires_password_change': requires_password_change
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
def logout():
    """Logout user and revoke tokens.

    Always 200 and always clears JWT cookies — even if the caller is already
    signed out, the token is expired, or a second /login pageshow races the
    first logout. Requiring a live access JWT left cookies in place on 401
    and let Back/Forward restore the app without credentials.

    When a valid (or expired) token is present, revokes that JTI and every
    other live session row for the user, including the paired refresh token.
    """
    try:
        user_ids = set()
        jtis = set()
        for payload in _jwt_payloads_from_request():
            sub = payload.get('sub')
            jti = payload.get('jti')
            if sub is not None:
                try:
                    user_ids.add(int(sub))
                except (TypeError, ValueError):
                    pass
            if jti:
                jtis.add(jti)

        if jtis:
            Session.query.filter(Session.token_jti.in_(jtis)).update(
                {'is_revoked': True}, synchronize_session=False
            )
        for uid in user_ids:
            Session.query.filter_by(user_id=uid, is_revoked=False).update({'is_revoked': True})
        if jtis or user_ids:
            db.session.commit()
            for uid in user_ids:
                log_audit(uid, 'logout', 'user', str(uid))

        response = jsonify({'message': 'Logout successful'})
        from flask_jwt_extended import unset_jwt_cookies
        unset_jwt_cookies(response)
        # HTTPS browsers honor this and drop cookies + localStorage for the origin.
        response.headers['Clear-Site-Data'] = '"cookies", "storage"'
        return response, 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Logout error: {str(e)}")
        response = jsonify({'message': 'Logout successful'})
        from flask_jwt_extended import unset_jwt_cookies
        unset_jwt_cookies(response)
        return response, 200


@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def get_current_user():
    """Get current user profile"""
    try:
        user_id = get_jwt_identity()
        user = db.session.get(User, int(user_id))
        
        if not user:
            return error_response('User not found', 404, 'USER_NOT_FOUND')
        
        return jsonify({
            'user': user.to_client_dict()
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Get user error: {str(e)}")
        return error_response('Failed to fetch user', 500, 'INTERNAL_ERROR')


@auth_bp.route('/profile', methods=['PUT'])
@jwt_required()
def update_own_profile():
    """Update fields the user manages: full name, employment start date (for dashboard tenure)."""
    try:
        from common.datetime_utils import parse_employment_start_date

        user_id = get_jwt_identity()
        user = db.session.get(User, int(user_id))
        if not user:
            return error_response('User not found', 404, 'USER_NOT_FOUND')

        data = request.get_json(force=True, silent=True) or {}

        if 'full_name' in data:
            fn = data.get('full_name')
            user.full_name = (fn or '').strip() or None

        if 'employment_start_date' in data:
            try:
                user.employment_start_date = parse_employment_start_date(data.get('employment_start_date'))
            except ValueError as ve:
                return error_response(str(ve), 400, 'VALIDATION_ERROR')

        db.session.commit()
        return jsonify({'success': True, 'user': user.to_client_dict()}), 200
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
                from common.utils import normalize_approval_comment
                c = str(default_comment).strip()
                if re.match(r'^Signed\s*(?:&|and)\s*Verified\.?$', c, re.I):
                    user.default_comment = None
                else:
                    user.default_comment = normalize_approval_comment(c) or None

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
        
        # Update password
        user.set_password(data['new_password'])
        user.password_changed = True  # Mark password as changed
        db.session.commit()
        
        # Revoke all existing sessions (force re-login)
        Session.query.filter_by(user_id=user_id, is_revoked=False).update({'is_revoked': True})
        db.session.commit()
        
        # Log password change
        log_audit(user_id, 'change_password', 'user', str(user_id))

        if user.email:
            try:
                from common.email_service import send_password_updated_email
                send_password_updated_email(
                    user.email, user.username, by_admin=False, full_name=user.full_name
                )
            except Exception as email_error:
                current_app.logger.warning('Password updated email failed: %s', email_error)
        
        return jsonify({'message': 'Password changed successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Change password error: {str(e)}")
        return error_response('Password change failed', 500, 'INTERNAL_ERROR')


@auth_bp.route('/forgot-password', methods=['POST'])
@rate_limit_if_available('5 per minute')
def forgot_password():
    """Email a time-limited reset link. Always 200 for valid emails so we do not leak accounts."""
    data = request.get_json(force=True, silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    sent_message = 'If that email is on an account, we have sent a reset link.'

    if not email or not validate_email(email):
        return error_response('A valid email is required', 400, 'VALIDATION_ERROR')

    user = User.query.filter(db.func.lower(User.email) == email).first()
    if user and user.is_active:
        try:
            token = make_password_reset_token(user.id)
            from common.email_service import send_forgot_password_email
            send_forgot_password_email(
                user.email, user.username, token, full_name=user.full_name
            )
            log_audit(user.id, 'forgot_password', 'user', str(user.id))
        except Exception as exc:
            current_app.logger.warning('Forgot-password email failed: %s', exc)
    return jsonify({'message': sent_message, 'success': True}), 200


@auth_bp.route('/reset-password', methods=['POST'])
@rate_limit_if_available('5 per minute')
def reset_password():
    """Set a new password from a forgot-password email token."""
    data = request.get_json(force=True, silent=True) or {}
    token = (data.get('token') or '').strip()
    new_password = data.get('password') or data.get('new_password') or ''

    if not token:
        return error_response('Reset link is missing or invalid', 400, 'INVALID_TOKEN')
    is_valid, message = validate_password(new_password)
    if not is_valid:
        return error_response(message, 400, 'WEAK_PASSWORD')

    try:
        user_id = load_password_reset_token(token)
    except SignatureExpired:
        return error_response('This reset link has expired. Request a new one.', 400, 'TOKEN_EXPIRED')
    except (BadSignature, KeyError, TypeError, ValueError):
        return error_response('Reset link is missing or invalid', 400, 'INVALID_TOKEN')

    user = db.session.get(User, user_id)
    if not user or not user.is_active:
        return error_response('Account not found', 404, 'USER_NOT_FOUND')

    user.set_password(new_password)
    user.password_changed = True
    Session.query.filter_by(user_id=user.id, is_revoked=False).update({'is_revoked': True})
    db.session.commit()
    log_audit(user.id, 'reset_password', 'user', str(user.id))

    if user.email:
        try:
            from common.email_service import send_password_updated_email
            send_password_updated_email(
                user.email, user.username, by_admin=False, full_name=user.full_name
            )
        except Exception as email_error:
            current_app.logger.warning('Password updated email failed: %s', email_error)

    return jsonify({'message': 'Password updated. You can sign in now.', 'success': True}), 200


@auth_bp.route('/mfa/setup', methods=['POST'])
@jwt_required()
def mfa_setup():
    """Begin TOTP MFA enrollment — returns otpauth URI + secret."""
    try:
        import pyotp
    except ImportError:
        return error_response('MFA library not installed (pyotp)', 503, 'MFA_UNAVAILABLE')
    user = db.session.get(User, int(get_jwt_identity()))
    if not user:
        return error_response('User not found', 404, 'USER_NOT_FOUND')
    secret = pyotp.random_base32()
    user.mfa_secret = secret
    user.mfa_enabled = False
    db.session.commit()
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=user.email or user.username, issuer_name='Kynvera')
    log_audit(user.id, 'mfa_setup_started', 'user', str(user.id))
    return success_response({
        'secret': secret,
        'otpauth_uri': uri,
        'mfa_enabled': False,
    }, message='Scan QR / enter secret, then confirm with /mfa/enable')


@auth_bp.route('/mfa/enable', methods=['POST'])
@jwt_required()
def mfa_enable():
    """Confirm MFA with a valid TOTP code."""
    try:
        import pyotp
    except ImportError:
        return error_response('MFA library not installed (pyotp)', 503, 'MFA_UNAVAILABLE')
    user = db.session.get(User, int(get_jwt_identity()))
    if not user or not user.mfa_secret:
        return error_response('Run /mfa/setup first', 400, 'MFA_NOT_SETUP')
    data = request.get_json(silent=True) or {}
    code = (data.get('mfa_code') or data.get('otp') or '').strip()
    if not pyotp.TOTP(user.mfa_secret).verify(code, valid_window=1):
        return error_response('Invalid MFA code', 401, 'INVALID_MFA')
    user.mfa_enabled = True
    db.session.commit()
    log_audit(user.id, 'mfa_enabled', 'user', str(user.id))
    return success_response({'mfa_enabled': True}, message='MFA enabled')


@auth_bp.route('/mfa/disable', methods=['POST'])
@jwt_required()
def mfa_disable():
    user = db.session.get(User, int(get_jwt_identity()))
    if not user:
        return error_response('User not found', 404, 'USER_NOT_FOUND')
    data = request.get_json(silent=True) or {}
    password = data.get('password') or ''
    if not user.check_password(password):
        return error_response('Password required to disable MFA', 401, 'INVALID_PASSWORD')
    user.mfa_enabled = False
    user.mfa_secret = None
    db.session.commit()
    log_audit(user.id, 'mfa_disabled', 'user', str(user.id))
    return success_response({'mfa_enabled': False}, message='MFA disabled')


@auth_bp.route('/mfa/status', methods=['GET'])
@jwt_required()
def mfa_status():
    user = db.session.get(User, int(get_jwt_identity()))
    if not user:
        return error_response('User not found', 404, 'USER_NOT_FOUND')
    return success_response({
        'mfa_enabled': bool(getattr(user, 'mfa_enabled', False)),
        'has_secret': bool(getattr(user, 'mfa_secret', None)),
    })


@auth_bp.route('/push-token', methods=['POST'])
@jwt_required()
def register_push_token():
    """Register FCM/APNs device token for push notifications."""
    from app.models import PushDeviceToken
    user = db.session.get(User, int(get_jwt_identity()))
    if not user:
        return error_response('User not found', 404, 'USER_NOT_FOUND')
    data = request.get_json(silent=True) or {}
    token = (data.get('token') or '').strip()
    platform = (data.get('platform') or 'android').strip().lower()
    if not token:
        return error_response('token required', 400, 'VALIDATION_ERROR')
    row = PushDeviceToken.query.filter_by(token=token).first()
    if row:
        row.user_id = user.id
        row.platform = platform
    else:
        row = PushDeviceToken(user_id=user.id, token=token, platform=platform)
        db.session.add(row)
    db.session.commit()
    return success_response({'registered': True}, message='Push token registered')