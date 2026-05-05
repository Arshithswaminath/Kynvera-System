import os
import uuid
import json
import time
import logging
from functools import wraps
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)


def is_path_safe_for_directory(base_dir, file_path):
    """
    Verify that the resolved file_path is inside base_dir (prevents path traversal).
    
    Args:
        base_dir: Base directory that file_path must be under
        file_path: Path to validate (may contain .. or symlinks)
    
    Returns:
        bool: True if file_path resolves to a path under base_dir, False otherwise
    """
    try:
        base_real = os.path.realpath(os.path.abspath(base_dir))
        path_real = os.path.realpath(os.path.abspath(file_path))
        # Ensure path_real is under base_real (commonpath trick works for containment)
        return os.path.commonpath([base_real, path_real]) == base_real
    except (ValueError, OSError):
        return False

# Try importing fcntl for file locking (Unix only)
try:
    import fcntl
    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False

# Retry decorator for external service calls
def retry_on_failure(max_attempts=3, delay=1.0, backoff=2.0, exceptions=(Exception,)):
    """Retry decorator with exponential backoff"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 0
            current_delay = delay
            last_exception = None
            
            while attempt < max_attempts:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    attempt += 1
                    if attempt >= max_attempts:
                        break
                    logger.warning(f"Attempt {attempt}/{max_attempts} failed for {func.__name__}: {e}. Retrying in {current_delay}s...")
                    time.sleep(current_delay)
                    current_delay *= backoff
            
            logger.error(f"All {max_attempts} attempts failed for {func.__name__}")
            raise last_exception
        return wrapper
    return decorator

def random_id(prefix="job"):
    return f"{prefix}_{uuid.uuid4().hex[:12]}"

def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

def save_uploaded_file(file_storage, uploads_dir):
    """
    Save an incoming werkzeug FileStorage securely.
    Returns saved filename (relative to uploads_dir).
    """
    ensure_dir(uploads_dir)
    filename = secure_filename(file_storage.filename)
    if not filename:
        filename = f"file_{int(time.time())}"
    unique = f"{uuid.uuid4().hex[:8]}"
    base, ext = os.path.splitext(filename)
    final_name = f"{base}_{unique}{ext}"
    path = os.path.join(uploads_dir, final_name)
    file_storage.save(path)
    return final_name

def write_job_state(jobs_dir, job_id, state_dict):
    ensure_dir(jobs_dir)
    job_file = os.path.join(jobs_dir, f"{job_id}.json")
    
    # Use file locking to prevent race conditions (Unix only)
    try:
        with open(job_file, 'w') as f:
            if HAS_FCNTL:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    json.dump(state_dict, f)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            else:
                # Windows fallback - no locking available
                json.dump(state_dict, f)
    except (IOError, OSError) as e:
        logger.error(f"Failed to write job state for {job_id}: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error writing job state for {job_id}: {e}")
        raise

def read_job_state(jobs_dir, job_id):
    job_file = os.path.join(jobs_dir, f"{job_id}.json")
    if not os.path.exists(job_file):
        return None
    with open(job_file, 'r') as f:
        return json.load(f)

def mark_job_started(jobs_dir, job_id, meta=None):
    state = {
        "job_id": job_id,
        "state": "started",
        "progress": 0,
        "results": [],
        "meta": meta or {},
        "created_at": time.time()
    }
    write_job_state(jobs_dir, job_id, state)
    return state

def update_job_progress(jobs_dir, job_id, progress, state='running', results=None):
    s = read_job_state(jobs_dir, job_id) or {}
    s.update({
        "state": state,
        "progress": progress,
    })
    if results is not None:
        s['results'] = results
    write_job_state(jobs_dir, job_id, s)

def mark_job_done(jobs_dir, job_id, results):
    s = read_job_state(jobs_dir, job_id) or {}
    s.update({
        "state": "done",
        "progress": 100,
        "results": results,
        "completed_at": time.time()
    })
    write_job_state(jobs_dir, job_id, s)

# Config-aware wrapper functions for background tasks
def mark_job_started_with_config(job_id, config, meta=None):
    """Wrapper that extracts JOBS_DIR from config dict"""
    jobs_dir = config.get('JOBS_DIR')
    return mark_job_started(jobs_dir, job_id, meta)

def update_job_progress_with_config(job_id, progress, config, state='running', results=None):
    """Wrapper that extracts JOBS_DIR from config dict"""
    jobs_dir = config.get('JOBS_DIR')
    return update_job_progress(jobs_dir, job_id, progress, state, results)

def mark_job_done_with_config(job_id, success, config, results=None, error=None):
    """Wrapper that extracts JOBS_DIR from config dict and handles error state"""
    jobs_dir = config.get('JOBS_DIR')
    if not success:
        result_data = {"error": error or "Unknown error"}
        s = read_job_state(jobs_dir, job_id) or {}
        s.update({
            "state": "failed",
            "progress": 0,
            "results": result_data,
            "completed_at": time.time()
        })
        write_job_state(jobs_dir, job_id, s)
    else:
        # Success case - MUST call mark_job_done with correct signature
        # mark_job_done(jobs_dir, job_id, results_dict)
        if results is None:
            results = {}
        mark_job_done(jobs_dir, job_id, results)  # This sets state="done"

def read_job_state_with_config(job_id, config):
    """Wrapper that extracts JOBS_DIR from config dict"""
    jobs_dir = config.get('JOBS_DIR')
    return read_job_state(jobs_dir, job_id)

# ---------- Cloud Storage Integration ----------

def upload_file_to_cloud(file_storage, folder="uploads"):
    """
    Upload file to Cloudinary and return secure URL.
    Falls back to local storage if Cloudinary is not configured.
    Returns (url, is_cloud) tuple.
    """
    try:
        from app.services.cloudinary_service import init_cloudinary, upload_local_file
        
        if not init_cloudinary():
            logger.warning("Cloudinary not configured, falling back to local storage")
            return None, False
        
        # Save temporarily to upload to Cloudinary
        import tempfile
        temp_dir = tempfile.gettempdir()
        filename = secure_filename(file_storage.filename)
        if not filename:
            filename = f"file_{int(time.time())}"
        unique = f"{uuid.uuid4().hex[:8]}"
        base, ext = os.path.splitext(filename)
        temp_filename = f"{base}_{unique}{ext}"
        temp_path = os.path.join(temp_dir, temp_filename)
        
        file_storage.save(temp_path)
        
        # Upload to Cloudinary
        public_id_prefix = f"{folder}/{base}_{unique}"
        url = upload_local_file(temp_path, public_id_prefix)
        
        # Clean up temp file
        try:
            os.remove(temp_path)
        except (OSError, IOError, PermissionError) as e:
            logger.debug(f"Could not remove temp file {temp_path}: {e}")
        
        if url:
            logger.info(f"✅ Uploaded to Cloudinary: {url}")
            return url, True
        else:
            logger.error("❌ Cloudinary upload failed")
            return None, False
            
    except Exception as e:
        logger.error(f"❌ Cloud upload error: {e}")
        return None, False

def save_uploaded_file_cloud(file_storage, uploads_dir, folder="uploads"):
    """
    Upload file to Cloudinary with retry logic and fallback to local storage.
    
    Args:
        file_storage: werkzeug FileStorage object
        uploads_dir: Local directory for fallback storage
        folder: Cloudinary folder name
        
    Returns:
        dict with 'url', 'public_id', 'is_cloud' keys
        
    Raises:
        Exception if both cloud and local storage fail
    """
    try:
        import cloudinary.uploader
        from .retry_utils import upload_to_cloudinary_with_retry
    except ImportError as ie:
        logger.warning(f"Cloudinary not available: {ie}. Using local storage only.")
        # Fallback to local storage immediately
        temp_filename = save_uploaded_file(file_storage, uploads_dir)
        return {
            "url": f"/generated/uploads/{temp_filename}",
            "public_id": None,
            "is_cloud": False,
            "filename": temp_filename
        }
    
    # Try cloud upload first with retry
    try:
        # Ensure uploads directory exists
        ensure_dir(uploads_dir)
        
        # Save to temp file first to allow retries
        temp_filename = save_uploaded_file(file_storage, uploads_dir)
        temp_path = os.path.join(uploads_dir, temp_filename)
        
        if not os.path.exists(temp_path):
            raise Exception(f"Temporary file not saved: {temp_path}")
        
        logger.info(f"Attempting cloud upload of {temp_filename}")
        
        try:
            result = upload_to_cloudinary_with_retry(
                temp_path,
                folder=folder,
                resource_type="auto"
            )
            
            if not result:
                raise Exception("Cloudinary returned empty result")
            
            cloud_url = result.get("secure_url") or result.get("url")
            if not cloud_url:
                raise Exception("No URL in Cloudinary response")
            
            # Cleanup temp file after successful upload
            try:
                os.remove(temp_path)
                logger.info(f"Removed temp file: {temp_path}")
            except OSError as e:
                logger.warning(f"Could not delete temp file {temp_path}: {e}")
            
            logger.info(f"✅ Cloud upload successful: {cloud_url}")
            return {
                "url": cloud_url,
                "public_id": result.get("public_id"),
                "is_cloud": True,
                "filename": temp_filename
            }
        except Exception as cloud_error:
            logger.error(f"Cloud upload failed after retries: {cloud_error}")
            # Keep local file as fallback
            logger.info(f"Falling back to local storage: {temp_filename}")
            return {
                "url": f"/generated/uploads/{temp_filename}",
                "public_id": None,
                "is_cloud": False,
                "local_path": temp_path,
                "filename": temp_filename
            }
    except Exception as e:
        logger.exception(f"File upload failed completely: {e}")
        # Last resort: try saving directly without cloud
        try:
            fallback_filename = save_uploaded_file(file_storage, uploads_dir)
            logger.warning(f"Using fallback local save: {fallback_filename}")
            return {
                "url": f"/generated/uploads/{fallback_filename}",
                "public_id": None,
                "is_cloud": False,
                "filename": fallback_filename
            }
        except Exception as final_error:
            logger.error(f"Final fallback failed: {final_error}")
            raise Exception(f"Complete file upload failure: {str(e)}")

def upload_base64_to_cloud(base64_string, folder="base64_uploads", prefix=None, uploads_dir=None):
    """
    Upload a base64-encoded image to Cloudinary with retry logic and local fallback.
    
    Args:
        base64_string: Base64 data URI string (e.g., "data:image/png;base64,...")
        folder: Cloudinary folder name (also used as subdirectory for local storage)
        prefix: Optional filename prefix for the uploaded file
        uploads_dir: Local directory for fallback storage (optional)
        
    Returns:
        tuple: (url, is_cloud) where url is either cloudinary_url or local URL
    """
    import io
    import base64 as b64_module
    
    if not base64_string or not isinstance(base64_string, str):
        raise Exception("Invalid base64 string provided")
    
    # Check if it starts with data URI scheme
    if not base64_string.startswith('data:'):
        raise Exception("Base64 string doesn't start with 'data:' - invalid format")
    
    # Try cloud upload first if Cloudinary is available
    try:
        import cloudinary.uploader
        from .retry_utils import upload_to_cloudinary_with_retry
        
        upload_options = {
            "folder": folder,
            "resource_type": "image"
        }
        
        # Add public_id prefix if provided
        if prefix:
            upload_options["public_id"] = f"{prefix}_{random_id('img')}"
        
        result = upload_to_cloudinary_with_retry(
            base64_string,
            **upload_options
        )
        
        cloud_url = result.get("secure_url") or result.get("url")
        if not cloud_url:
            raise Exception("Cloudinary upload succeeded but no URL returned")
        
        logger.info(f"✅ Base64 image uploaded to cloud: {cloud_url}")
        return cloud_url, True
        
    except ImportError:
        # Cloudinary not available - use local fallback
        logger.info("Cloudinary not available, using local storage for base64 image")
    except Exception as e:
        # Cloud upload failed - fall back to local storage
        logger.warning(f"Cloud upload failed for base64 image: {e}. Falling back to local storage.")
    
    # Fallback to local storage
    if not uploads_dir:
        # Try to get uploads directory from config
        try:
            from config import UPLOADS_DIR
            uploads_dir = UPLOADS_DIR
        except ImportError:
            # Fallback: create uploads directory in current directory
            uploads_dir = os.path.join(os.getcwd(), "generated", "uploads")
            ensure_dir(uploads_dir)
    
    try:
        # Parse the data URI
        header, encoded = base64_string.split(',', 1)
        
        # Extract mime type from header (e.g., "data:image/png;base64")
        mime_type = header.split(';')[0].split(':')[1] if ':' in header else 'image/png'
        ext_map = {
            'image/png': '.png',
            'image/jpeg': '.jpg',
            'image/jpg': '.jpg',
            'image/gif': '.gif',
            'image/webp': '.webp'
        }
        ext = ext_map.get(mime_type, '.png')
        
        # Decode base64
        image_data = b64_module.b64decode(encoded)
        
        # Generate filename
        if prefix:
            filename = f"{prefix}_{random_id('img')}{ext}"
        else:
            filename = f"{random_id('img')}{ext}"
        
        # Create subdirectory if needed (mirror Cloudinary folder structure)
        if folder:
            save_dir = os.path.join(uploads_dir, folder)
            ensure_dir(save_dir)
        else:
            save_dir = uploads_dir
        
        # Save file
        file_path = os.path.join(save_dir, filename)
        with open(file_path, 'wb') as f:
            f.write(image_data)
        
        # Generate URL (relative to generated directory)
        from config import GENERATED_DIR, BASE_DIR
        relative_path = os.path.relpath(file_path, GENERATED_DIR)
        # Normalize path separators for URL
        url_path = relative_path.replace('\\', '/')
        local_url = f"/generated/{url_path}"
        
        logger.info(f"✅ Base64 image saved locally: {local_url}")
        return local_url, False
        
    except Exception as e:
        logger.error(f"Failed to save base64 image locally: {e}")
        raise Exception(f"Both cloud and local storage failed: {str(e)}")

def get_image_for_pdf(image_info):
    """
    Get image data (path or BytesIO) for PDF generation.
    Handles both cloud URLs, local paths, and data URIs.
    
    Args:
        image_info: Can be a dict with 'url' or 'path' keys, or a string path
        
    Returns:
        (image_data, is_url) tuple where image_data is path or BytesIO stream
    """
    import io
    import base64
    from .retry_utils import fetch_url_with_retry
    
    # Handle string path (legacy)
    if isinstance(image_info, str):
        # Check if it's a data URI (base64 encoded image)
        if image_info.startswith('data:image'):
            try:
                # Extract base64 data after comma
                header, encoded = image_info.split(',', 1)
                image_data = base64.b64decode(encoded)
                return io.BytesIO(image_data), True
            except Exception as e:
                logger.error(f"Failed to decode data URI: {e}")
                return None, False
        
        # Check if it's a relative URL path like /generated/uploads/...
        if image_info.startswith('/generated/'):
            try:
                from config import GENERATED_DIR
                # Remove /generated/ prefix and convert to local path
                relative_path = image_info.replace('/generated/', '')
                local_path = os.path.join(GENERATED_DIR, relative_path)
                if os.path.exists(local_path):
                    logger.info(f"Found local image at: {local_path}")
                    return local_path, False
            except Exception as e:
                logger.warning(f"Failed to resolve local path for {image_info}: {e}")
        
        # Check if it's a full URL (http/https)
        if image_info.startswith('http://') or image_info.startswith('https://'):
            try:
                response = fetch_url_with_retry(image_info, timeout=10)
                return io.BytesIO(response.content), True
            except Exception as e:
                logger.error(f"Failed to fetch URL {image_info}: {e}")
                return None, False
        
        # Try as direct file path
        if os.path.exists(image_info):
            return image_info, False
        return None, False
    
    # Handle dict with url or path
    if isinstance(image_info, dict):
        # Try url field first - check if it's a data URI
        url = image_info.get('url', '')
        if url and url.startswith('data:image'):
            try:
                # Extract base64 data after comma
                header, encoded = url.split(',', 1)
                image_data = base64.b64decode(encoded)
                return io.BytesIO(image_data), True
            except Exception as e:
                logger.error(f"Failed to decode data URI: {e}")
                return None, False
        
        # Try to resolve relative URL paths like /generated/uploads/...
        if url and url.startswith('/generated/'):
            try:
                from config import GENERATED_DIR
                # Remove /generated/ prefix and convert to local path
                relative_path = url.replace('/generated/', '')
                local_path = os.path.join(GENERATED_DIR, relative_path)
                if os.path.exists(local_path):
                    logger.info(f"Found local image at: {local_path}")
                    return local_path, False
            except Exception as e:
                logger.warning(f"Failed to resolve local path for {url}: {e}")
        
        # Try cloud URL with retry (for full URLs or when is_cloud is True)
        if url and (image_info.get('is_cloud') or url.startswith('http://') or url.startswith('https://')):
            try:
                response = fetch_url_with_retry(url, timeout=10)
                return io.BytesIO(response.content), True
            except Exception as e:
                logger.error(f"Failed to fetch cloud image {url} after retries: {e}")
                # Fall through to try local path
        
        # Try local path
        path = image_info.get('path')
        if path and os.path.exists(path):
            return path, False
    
    return None, False