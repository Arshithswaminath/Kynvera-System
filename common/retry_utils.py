"""
Retry utilities for external service calls with exponential backoff
"""
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
    after_log
)
import requests
import logging
import cloudinary.uploader

logger = logging.getLogger(__name__)

# Cloudinary upload with retry
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((requests.exceptions.RequestException, cloudinary.exceptions.Error)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    after=after_log(logger, logging.INFO)
)
def upload_to_cloudinary_with_retry(file_obj, **kwargs):
    """
    Upload file to Cloudinary with retry logic
    
    Args:
        file_obj: File object or path to upload
        **kwargs: Additional cloudinary upload options
        
    Returns:
        Cloudinary response dict
        
    Raises:
        Exception after 3 failed attempts
    """
    try:
        # Ensure files are publicly accessible by default
        if 'access_mode' not in kwargs:
            kwargs['access_mode'] = 'public'
        
        result = cloudinary.uploader.upload(file_obj, **kwargs)
        logger.info(f"Successfully uploaded to Cloudinary: {result.get('public_id')}")
        return result
    except Exception as e:
        logger.error(f"Cloudinary upload failed: {str(e)}")
        raise

# HTTP GET with retry
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((
        requests.exceptions.Timeout,
        requests.exceptions.ConnectionError,
        requests.exceptions.HTTPError
    )),
    before_sleep=before_sleep_log(logger, logging.WARNING)
)
def fetch_url_with_retry(url, timeout=10, **kwargs):
    """
    Fetch URL with retry logic
    
    Args:
        url: URL to fetch
        timeout: Request timeout in seconds
        **kwargs: Additional requests options
        
    Returns:
        requests.Response object
        
    Raises:
        Exception after 3 failed attempts
    """
    try:
        response = requests.get(url, timeout=timeout, **kwargs)
        response.raise_for_status()
        logger.debug(f"Successfully fetched: {url}")
        return response
    except requests.exceptions.HTTPError as e:
        if e.response.status_code < 500:
            # Don't retry 4xx errors
            raise
        logger.warning(f"HTTP error fetching {url}: {e}")
        raise
    except Exception as e:
        logger.warning(f"Error fetching {url}: {str(e)}")
        raise

# Generic retry decorator for custom functions
def retry_on_failure(max_attempts=3, exceptions=(Exception,)):
    """
    Decorator to add retry logic to any function
    
    Args:
        max_attempts: Maximum number of retry attempts
        exceptions: Tuple of exceptions to catch and retry
        
    Returns:
        Decorated function with retry logic
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(exceptions),
        before_sleep=before_sleep_log(logger, logging.WARNING)
    )
