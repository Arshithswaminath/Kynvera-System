"""
Configuration validation utilities
"""
import os
import logging

logger = logging.getLogger(__name__)


def validate_config(app):
    """
    Validate critical configuration values at startup
    
    Args:
        app: Flask application instance
    
    Returns:
        tuple: (is_valid, errors_list)
    """
    errors = []
    warnings = []
    
    flask_env = app.config.get('FLASK_ENV', 'development')
    
    # Critical validations (fail fast in production)
    if flask_env == 'production':
        # Secret keys
        secret_key = app.config.get('SECRET_KEY')
        if not secret_key or secret_key in ['dev-secret', 'dev-secret-change-in-production', 'change-me', 'change-me-in-production']:
            errors.append("SECRET_KEY not set or using default value in production")
        elif len(secret_key) < 32:
            errors.append(f"SECRET_KEY too short (min 32 characters, got {len(secret_key)})")
        
        jwt_secret_key = app.config.get('JWT_SECRET_KEY')
        if not jwt_secret_key or jwt_secret_key in ['change-me', 'change-me-jwt-secret']:
            errors.append("JWT_SECRET_KEY not set or using default value in production")
        
        # Database URL - REQUIRED in production
        db_url = app.config.get('SQLALCHEMY_DATABASE_URI') or app.config.get('DATABASE_URL')
        if not db_url:
            errors.append("DATABASE_URL not configured - required in production")
        elif 'sqlite' in db_url.lower():
            errors.append("SQLite is not allowed in production - use PostgreSQL (set DATABASE_URL)")
        
        # Cloudinary - REQUIRED in production for file storage
        if not app.config.get('CLOUDINARY_CLOUD_NAME'):
            errors.append("CLOUDINARY_CLOUD_NAME not configured - required in production for cloud file storage")
        if not app.config.get('CLOUDINARY_API_KEY'):
            errors.append("CLOUDINARY_API_KEY not configured - required in production")
        if not app.config.get('CLOUDINARY_API_SECRET'):
            errors.append("CLOUDINARY_API_SECRET not configured - required in production")
        
        # CORS settings (if applicable)
        if app.config.get('CORS_ORIGINS') == '*':
            warnings.append("CORS allows all origins in production - security risk")
        
        # Debug mode
        if app.config.get('DEBUG', False):
            errors.append("DEBUG mode is enabled in production - security risk")
    
    # Warning validations (inform but don't fail)
    if not app.config.get('REDIS_URL') and flask_env == 'production':
        warnings.append("REDIS_URL not configured - rate limiting and background jobs may not work optimally")

    base_url = (app.config.get('APP_BASE_URL') or os.environ.get('APP_BASE_URL') or '').strip()
    if flask_env == 'production':
        if not base_url:
            warnings.append("APP_BASE_URL not set - email links and absolute file URLs may be wrong")
        elif 'localhost' in base_url or '127.0.0.1' in base_url:
            warnings.append("APP_BASE_URL still points to localhost - set to your public HTTPS URL for production")
    
    # Log warnings
    for warning in warnings:
        logger.warning(f"Configuration warning: {warning}")
    
    # Log errors
    for error in errors:
        logger.error(f"Configuration error: {error}")
    
    return len(errors) == 0, errors

