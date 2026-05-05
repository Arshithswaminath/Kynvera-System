"""
Standardized error response helpers for API routes
"""
from flask import jsonify
from functools import wraps
import traceback
import logging

logger = logging.getLogger(__name__)


def error_response(message, status_code=400, error_code=None, details=None):
    """
    Create a standardized error response
    
    Args:
        message: Human-readable error message
        status_code: HTTP status code (default: 400)
        error_code: Machine-readable error code (optional)
        details: Additional error details (optional)
    
    Returns:
        JSON response tuple (response, status_code)
    """
    response = {
        'success': False,
        'error': message
    }
    
    if error_code:
        response['error_code'] = error_code
    
    if details:
        response['details'] = details
    
    return jsonify(response), status_code


def success_response(data=None, message=None, status_code=200):
    """
    Create a standardized success response
    
    Args:
        data: Response data (optional)
        message: Success message (optional)
        status_code: HTTP status code (default: 200)
    
    Returns:
        JSON response tuple (response, status_code)
    """
    response = {'success': True}
    
    if message:
        response['message'] = message
    
    if data is not None:
        if isinstance(data, dict):
            response.update(data)
        else:
            response['data'] = data
    
    return jsonify(response), status_code


def handle_exceptions(f):
    """
    Decorator to handle exceptions and return standardized error responses
    
    Usage:
        @handle_exceptions
        def my_route():
            # your code here
            return success_response(data={'key': 'value'})
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ValueError as e:
            logger.warning(f"Value error in {f.__name__}: {str(e)}")
            return error_response(str(e), status_code=400, error_code='VALIDATION_ERROR')
        except PermissionError as e:
            logger.warning(f"Permission error in {f.__name__}: {str(e)}")
            return error_response(str(e), status_code=403, error_code='PERMISSION_DENIED')
        except FileNotFoundError as e:
            logger.warning(f"File not found in {f.__name__}: {str(e)}")
            return error_response('Resource not found', status_code=404, error_code='NOT_FOUND')
        except Exception as e:
            logger.error(f"Unexpected error in {f.__name__}: {str(e)}")
            logger.error(traceback.format_exc())
            return error_response(
                'An unexpected error occurred',
                status_code=500,
                error_code='INTERNAL_ERROR',
                details={'message': str(e)} if logger.isEnabledFor(logging.DEBUG) else None
            )
    return wrapper

