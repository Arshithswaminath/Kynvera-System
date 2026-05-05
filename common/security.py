"""
Security utilities: rate limiting, CSRF protection, input sanitization
"""
import os
import re
from functools import wraps
from flask import request, jsonify, current_app
from werkzeug.security import safe_join
import logging

logger = logging.getLogger(__name__)

def sanitize_filename(filename):
    """
    Sanitize filename to prevent path traversal
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename (only alphanumeric, dash, underscore, dot)
    """
    # Remove any path components
    filename = os.path.basename(filename)
    
    # Only allow alphanumeric, dash, underscore, and single dots
    filename = re.sub(r'[^\w\-.]', '_', filename)
    
    # Prevent multiple consecutive dots (../)
    filename = re.sub(r'\.{2,}', '.', filename)
    
    # Ensure it doesn't start with a dot (hidden file)
    filename = filename.lstrip('.')
    
    # Limit length
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[:250] + ext
    
    return filename or 'unnamed_file'

def safe_path_join(base_dir, *paths):
    """
    Safely join paths and ensure result is within base_dir
    
    Args:
        base_dir: Base directory that result must be within
        *paths: Path components to join (can include subdirectories like 'uploads/filename')
        
    Returns:
        Absolute path within base_dir or raises ValueError
    """
    # Join all paths first, then split and sanitize each component
    # This allows paths like 'uploads/filename' to work correctly
    joined = os.path.join(*paths) if paths else ''
    
    # Split into individual components and sanitize each one
    path_parts = joined.replace('\\', '/').split('/')
    sanitized_parts = []
    
    for part in path_parts:
        if part and part not in ('.', '..'):
            # Sanitize each individual part to prevent path traversal
            sanitized = sanitize_filename(part)
            if sanitized and sanitized != '.':
                sanitized_parts.append(sanitized)
    
    # Use werkzeug's safe_join which prevents path traversal
    result = safe_join(base_dir, *sanitized_parts)
    
    if result is None:
        raise ValueError(f"Path traversal detected: {paths}")
    
    # Double-check result is within base_dir
    result_abs = os.path.abspath(result)
    base_abs = os.path.abspath(base_dir)
    
    if not result_abs.startswith(base_abs):
        raise ValueError(f"Path {result} is outside base directory {base_dir}")
    
    return result_abs

def validate_json_request(required_fields=None):
    """
    Decorator to validate JSON requests
    
    Args:
        required_fields: List of required field names
        
    Returns:
        Decorator function
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not request.is_json:
                return jsonify({"error": "Content-Type must be application/json"}), 400
            
            data = request.get_json()
            if data is None:
                return jsonify({"error": "Invalid JSON"}), 400
            
            if required_fields:
                missing = [field for field in required_fields if field not in data]
                if missing:
                    return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400
            
            return f(*args, **kwargs)
        return wrapper
    return decorator

def validate_file_upload(allowed_extensions=None, max_size_mb=None):
    """
    Decorator to validate file uploads
    
    Args:
        allowed_extensions: Set of allowed extensions (e.g., {'png', 'jpg'})
        max_size_mb: Maximum file size in MB (defaults to 10MB from config)
        
    Returns:
        Decorator function
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if 'photo' not in request.files:
                return jsonify({"error": "No file uploaded"}), 400
            
            file = request.files['photo']
            if file.filename == '':
                return jsonify({"error": "Empty filename"}), 400
            
            # Check extension
            if allowed_extensions:
                ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
                if ext not in allowed_extensions:
                    return jsonify({"error": f"File type .{ext} not allowed. Allowed: {', '.join(allowed_extensions)}"}), 400
            
            # Use standardized max size from config if not specified
            if max_size_mb is None:
                from config import MAX_FILE_SIZE_MB
                max_size_mb = MAX_FILE_SIZE_MB
            
            # Check size (if we can)
            file.seek(0, os.SEEK_END)
            size = file.tell()
            file.seek(0)  # Reset to beginning
            
            if size > max_size_mb * 1024 * 1024:
                return jsonify({"error": f"File too large. Maximum size: {max_size_mb}MB"}), 413
            
            return f(*args, **kwargs)
        return wrapper
    return decorator

def log_security_event(event_type, details, request_obj=None):
    """
    Log security-related events
    
    Args:
        event_type: Type of security event (e.g., 'rate_limit_exceeded')
        details: Additional details about the event
        request_obj: Flask request object (optional)
    """
    if request_obj is None:
        request_obj = request
    
    log_data = {
        'event': event_type,
        'details': details,
        'ip': request_obj.remote_addr,
        'user_agent': request_obj.headers.get('User-Agent', 'unknown'),
        'path': request_obj.path,
        'method': request_obj.method
    }
    
    logger.warning(f"SECURITY_EVENT: {log_data}")

def check_cloudinary_configured():
    """
    Check if Cloudinary is properly configured
    
    Returns:
        bool: True if configured, False otherwise
    """
    cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME')
    api_key = os.environ.get('CLOUDINARY_API_KEY')
    api_secret = os.environ.get('CLOUDINARY_API_SECRET')
    
    return all([cloud_name, api_key, api_secret])
