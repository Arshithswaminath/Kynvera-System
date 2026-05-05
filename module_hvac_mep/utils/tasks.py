import os
import json
import time
import logging

from common.datetime_utils import utc_now_naive

logger = logging.getLogger(__name__)

from .excel_writer import create_report_workbook
from .pdf_generator import generate_visit_pdf
from .email_sender import send_outlook_email
from .state import save_report_state

def _external_generated_url(filename):
    base = os.environ.get('APP_BASE_URL', 'http://127.0.0.1:5000')
    return f"{base.rstrip('/')}/hvac-mep/generated/{filename}"

def generate_and_send_report(report_id, visit_info, final_items, generated_dir):
    try:
        # 1) Excel
        excel_path, excel_filename = create_report_workbook(generated_dir, visit_info, final_items)
        # 2) PDF
        pdf_path, pdf_filename = generate_visit_pdf(visit_info, final_items, generated_dir, upload_to_cloudinary=False)
        # 3) Build URLs
        excel_url = _external_generated_url(excel_filename) if excel_filename else None
        pdf_url = _external_generated_url(pdf_filename) if pdf_filename else None
        # 4) Save final status (here using tempfile or redis via save_report_state)
        final_status = {
            "status": "done",
            "excel_url": excel_url,
            "pdf_url": pdf_url,
            "completed_at": utc_now_naive().isoformat()
        }
        save_report_state(report_id, {"visit_info": visit_info, "report_items": final_items, "final_status": final_status})
        # 5) Send email (dummy)
        try:
            send_outlook_email(f"HVAC Report: {visit_info.get('building_name','Unknown')}", "Report generated", [excel_path, pdf_path], visit_info.get('email'))
        except Exception:
            logger.exception("Email send failed")
    except Exception:
        logger.exception("Report generation failed")