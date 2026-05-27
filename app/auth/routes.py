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
    """Register a new user"""
    try:
        data = request.get_json(force=True, silent=True)
        
        if not data:
            return error_response('Invalid JSON or missing request body', 400, 'INVALID_REQUEST')
        
        # Validate required fields
        required_fields = ['username', 'email', 'password', 'full_name']
        for field in required_fields:
            if not data.get(field):
                return error_response(f'{field} is required', 400, 'VALIDATION_ERROR')
        
        username = data['username'].strip()
        email = data['email'].strip().lower()
        password = data['password']
        full_name = data['full_name'].strip()
        
        # Validate email format
        if not validate_email(email):
            return error_response('Invalid email format', 400, 'VALIDATION_ERROR')
        
        # Validate password strength
        is_valid, message = validate_password(password)
        if not is_valid:
            return error_response(message, 400, 'WEAK_PASSWORD')
        
        # Check if user already exists
        if User.query.filter_by(username=username).first():
            return error_response('Username already exists', 409, 'DUPLICATE_USERNAME')
        
        if User.query.filter_by(email=email).first():
            return error_response('Email already registered', 409, 'DUPLICATE_EMAIL')
        
        # Create new user
        user = User(
            username=username,
            email=email,
            full_name=full_name,
            role='user'  # Default role
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        # Log registration
        log_audit(user.id, 'register', 'user', str(user.id))
        
        return jsonify({
            'message': 'User registered successfully',
            'user': user.to_client_dict()
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
@jwt_required()
def logout():
    """Logout user and revoke tokens.

    Revokes the current access JTI explicitly AND every other live session row
    for this user — that covers the paired refresh token. A user who logs out
    in one tab will be signed out on every tab the same browser had open;
    that's the intended security behaviour.
    """
    try:
        user_id = get_jwt_identity()
        jti = get_jwt()['jti']

        Session.query.filter_by(token_jti=jti).update({'is_revoked': True})
        Session.query.filter_by(user_id=int(user_id), is_revoked=False).update({'is_revoked': True})
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
        
        return jsonify({'message': 'Password changed successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Change password error: {str(e)}")
        return error_response('Password change failed', 500, 'INTERNAL_ERROR')