import cloudinary
import cloudinary.uploader
import os
import re
import time
import logging

logger = logging.getLogger(__name__)

def init_cloudinary():
    cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME', '')
    api_key = os.environ.get('CLOUDINARY_API_KEY', '')
    api_secret = os.environ.get('CLOUDINARY_API_SECRET', '')
    if not cloud_name or not api_key or not api_secret:
        logger.error(f"Cloudinary credentials missing: cloud_name={bool(cloud_name)}, api_key={bool(api_key)}, api_secret={bool(api_secret)}")
        return False
    cloudinary.config(
        cloud_name=cloud_name,
        api_key=api_key,
        api_secret=api_secret,
        secure=True
    )
    logger.info(f"Cloudinary configured: {cloud_name}")
    return True

def upload_base64_signature(data_uri, public_id_prefix):
    if not data_uri:
        logger.error("No data_uri provided")
        return None
    if not init_cloudinary():
        logger.error("Cloudinary initialization failed")
        return None
    try:
        logger.info(f"Attempting Cloudinary upload for {public_id_prefix}")
        res = cloudinary.uploader.upload(
            file=data_uri,
            folder="signatures",
            public_id=f"{public_id_prefix}_{int(time.time())}",
            access_mode='public'  # Make publicly accessible
        )
        url = res.get('secure_url')
        logger.info(f"Cloudinary upload success: {url}")
        return url
    except Exception as e:
        logger.error(f"Cloudinary signature upload failed: {str(e)}", exc_info=True)
        return None

def upload_local_file(path, public_id_prefix):
    if not init_cloudinary():
        logger.error("Cloudinary initialization failed")
        return None
    try:
        # Extract original filename for download
        original_filename = os.path.basename(path)
        
        # Use 'raw' for Excel and PDF to force download (raw files download automatically)
        file_ext = os.path.splitext(path)[1].lower()
        resource_type = 'raw' if file_ext in ['.pdf', '.xlsx', '.xls'] else 'auto'
        
        logger.info(f"Attempting Cloudinary file upload: {path} (resource_type={resource_type})")
        res = cloudinary.uploader.upload(
            path, 
            folder="injaaz_reports", 
            public_id=public_id_prefix, 
            resource_type=resource_type,
            access_mode='public'  # Make publicly accessible
        )
        url = res.get('secure_url')
        
        # Don't add ?attachment=true to URLs - let the download route handle it
        # The attachment parameter can cause issues with Cloudinary access
        logger.info(f"Cloudinary file upload success: {url}")
        return url
    except Exception as e:
        logger.error(f"Cloudinary file upload failed: {str(e)}", exc_info=True)
        return None


def upload_dochub_file(local_path, public_id_prefix):
    """
    Store a DocHub library file on Cloudinary; return secure_url or None.
    Used when DOCHUB_USE_CLOUDINARY=true so files survive ephemeral server disks (e.g. Render).
    """
    if not local_path or not os.path.isfile(local_path):
        return None
    if not init_cloudinary():
        return None
    try:
        ext = os.path.splitext(local_path)[1].lower()
        resource_type = (
            "raw"
            if ext
            in (
                ".pdf",
                ".docx",
                ".doc",
                ".xlsx",
                ".xls",
                ".pptx",
                ".ppt",
                ".zip",
                ".md",
            )
            else "auto"
        )
        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", public_id_prefix)[:180]
        res = cloudinary.uploader.upload(
            local_path,
            folder="dochub",
            public_id=safe_id,
            resource_type=resource_type,
            access_mode="public",
        )
        url = res.get("secure_url")
        if url:
            logger.info("DocHub Cloudinary upload success: %s", url[:80])
        return url
    except Exception as e:
        logger.error("DocHub Cloudinary upload failed: %s", e, exc_info=True)
        return None