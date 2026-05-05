"""
Middleware for JWT token validation and session checking
"""
from flask import jsonify, current_app
from flask_jwt_extended import verify_jwt_in_request, get_jwt
from functools import wraps
from app.models import Session, User
from common.jwt_session import sync_access_session_row


def token_required(fn=None, *, locations=None):
    """
    Verify JWT + Session row + active user.
    Use locations=['headers'] for SPA JSON/multipart routes so the Authorization Bearer is the
    only access JWT considered (avoids stale access_token_cookie vs fresh localStorage token).
    Default locations=None uses app JWT_TOKEN_LOCATION (headers + cookies).
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            try:
                verify_jwt_in_request(locations=locations)

                jwt_data = get_jwt()
                jti = jwt_data.get('jti')

                session = Session.query.filter_by(token_jti=jti).first()
                if session is None:
                    session = sync_access_session_row(jti, jwt_data)
                if not session or session.is_revoked:
                    return jsonify({'success': False, 'error': 'Token has been revoked'}), 401

                from flask_jwt_extended import get_jwt_identity
                user_id = get_jwt_identity()
                try:
                    uid = int(user_id)
                except (TypeError, ValueError):
                    uid = user_id
                user = User.query.get(uid)

                if not user or not user.is_active:
                    return jsonify({'success': False, 'error': 'User is inactive'}), 403

                return f(*args, **kwargs)

            except Exception as e:
                current_app.logger.error(f"Token validation error: {str(e)}")
                return jsonify({'error': 'Unauthorized'}), 401

        return wrapper

    if fn is not None:
        return decorator(fn)
    return decorator


def admin_required(fn):
    """Decorator to check if user has admin role"""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            verify_jwt_in_request()
            
            from flask_jwt_extended import get_jwt_identity
            user_id = get_jwt_identity()
            
            if not user_id:
                current_app.logger.warning("Admin check failed: No user ID in token")
                return jsonify({'error': 'Unauthorized'}), 401
            
            user = User.query.get(user_id)
            
            if not user:
                current_app.logger.warning(f"Admin check failed: User {user_id} not found")
                return jsonify({'error': 'User not found'}), 404
            
            if not user.is_active:
                current_app.logger.warning(f"Admin check failed: User {user_id} is inactive")
                return jsonify({'error': 'User account is inactive'}), 403
            
            if user.role != 'admin':
                current_app.logger.warning(f"Admin check failed: User {user_id} has role '{user.role}', not 'admin'")
                return jsonify({'error': 'Admin access required'}), 403
            
            return fn(*args, **kwargs)
            
        except Exception as e:
            import traceback
            current_app.logger.error(f"Admin check error: {str(e)}")
            current_app.logger.error(traceback.format_exc())
            return jsonify({'error': 'Unauthorized', 'details': str(e) if current_app.debug else None}), 401
    
    return wrapper


def inspector_required(fn):
    """Decorator to check if user has inspector or admin role"""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            verify_jwt_in_request()
            
            from flask_jwt_extended import get_jwt_identity
            user_id = get_jwt_identity()
            user = User.query.get(user_id)
            
            if not user or user.role not in ['inspector', 'admin']:
                return jsonify({'error': 'Inspector access required'}), 403
            
            return fn(*args, **kwargs)
            
        except Exception as e:
            current_app.logger.error(f"Inspector check error: {str(e)}")
            return jsonify({'error': 'Unauthorized'}), 401
    
    return wrapper


def module_access_required(module):
    """Decorator factory to check if user has access to a specific module"""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                verify_jwt_in_request()
                
                from flask_jwt_extended import get_jwt_identity
                user_id = get_jwt_identity()
                user = User.query.get(user_id)
                
                if not user or not user.is_active:
                    return jsonify({'error': 'User is inactive'}), 403
                
                if not user.has_module_access(module):
                    return jsonify({
                        'error': f'Access denied to {module} module',
                        'module': module
                    }), 403
                
                return fn(*args, **kwargs)
                
            except Exception as e:
                current_app.logger.error(f"Module access check error: {str(e)}")
                return jsonify({'error': 'Unauthorized'}), 401
        
        return wrapper
    return decorator