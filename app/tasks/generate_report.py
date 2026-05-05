import os
import json
import logging
from app.services.excel_service import create_report_workbook
from common.datetime_utils import utc_now_naive
from app.services.cloudinary_service import upload_local_file, init_cloudinary
from app.services.email_service import send_outlook_email
from app.services.pdf_service import generate_visit_pdf

logger = logging.getLogger(__name__)

def _write_status_file(generated_dir, report_id, status_obj):
    try:
        os.makedirs(generated_dir, exist_ok=True)
        status_path = os.path.join(generated_dir, f"{report_id}.status.json")
        with open(status_path, 'w', encoding='utf-8') as sf:
            json.dump(status_obj, sf)
    except Exception:
        logger.exception("Failed to write status file for %s", report_id)

def generate_and_send_report(report_id, visit_info, final_items, generated_dir, remove_local_files=False):
    status_key = f"report:{report_id}"
    try:
        status = {"status": "processing", "started_at": utc_now_naive().isoformat(), "progress": 0}
        _write_status_file(generated_dir, report_id, status)

        # Excel
        excel_path, excel_filename = create_report_workbook(generated_dir, visit_info, final_items)

        # PDF generation - use the new PDF service
        try:
            pdf_path, pdf_filename = generate_visit_pdf(visit_info, final_items, generated_dir, report_id=report_id)
            logger.info("PDF generated: %s", pdf_path)
        except Exception as e:
            logger.exception("PDF generation failed: %s", e)
            status = {"status": "failed", "error": f"PDF generation failed: {e}"}
            _write_status_file(generated_dir, report_id, status)
            return

        # Attempt Cloudinary upload if configured
        excel_url = None
        pdf_url = None
        uploaded_to_cloudinary = False
        if init_cloudinary():
            try:
                if excel_path and os.path.exists(excel_path):
                    excel_url = upload_local_file(excel_path, f"{report_id}_excel")
                if pdf_path and os.path.exists(pdf_path):
                    pdf_url = upload_local_file(pdf_path, f"{report_id}_pdf")
                uploaded_to_cloudinary = bool(excel_url or pdf_url)
                logger.info("Uploaded to Cloudinary: excel=%s pdf=%s", bool(excel_url), bool(pdf_url))
            except Exception:
                logger.exception("Failed uploading to Cloudinary")

        # Fallback to local URLs served by Flask
        if not excel_url:
            excel_url = f"/site-visit/generated/{excel_filename}"
        if not pdf_url:
            pdf_url = f"/site-visit/generated/{pdf_filename}"

        final_status = {
            "status": "done",
            "excel_url": excel_url,
            "pdf_url": pdf_url,
            "uploaded_to_cloudinary": uploaded_to_cloudinary,
            "finished_at": utc_now_naive().isoformat()
        }
        _write_status_file(generated_dir, report_id, final_status)

        # Send email (best-effort)
        try:
            send_outlook_email(f"Report {report_id}", "Your report is ready", [excel_path, pdf_path], visit_info.get("email"))
        except Exception:
            logger.exception("Failed to send email")
        
        # Optionally remove local files after upload
        if remove_local_files:
            for p in [excel_path, pdf_path]:
                try:
                    if p and os.path.exists(p):
                        os.remove(p)
                except Exception:
                    logger.exception("Failed to remove local file: %s", p)

    except Exception:
        logger.exception("Unhandled error in generate_and_send_report")
        _write_status_file(generated_dir, report_id, {"status": "failed", "error": "internal"})