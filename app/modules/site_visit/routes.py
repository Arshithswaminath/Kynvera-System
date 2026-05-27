import os
import json
import time
import tempfile
import traceback
from datetime import datetime
from flask import current_app, jsonify, request, url_for, send_from_directory, render_template
from . import site_visit_bp
from app.extensions import get_redis_conn, get_rq_queue
from app.services.cloudinary_service import upload_base64_signature
from app.services.excel_service import create_report_workbook
from app.tasks.generate_report import generate_and_send_report

# location for generated artifacts
GENERATED_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'generated'))

def _temp_path(report_id):
    return os.path.join(tempfile.gettempdir(), f"{report_id}.json")

def _save_state(report_id, data):
    os.makedirs(os.path.dirname(_temp_path(report_id)), exist_ok=True)
    with open(_temp_path(report_id), 'w', encoding='utf-8') as f:
        json.dump(data, f)

def _load_state(report_id):
    p = _temp_path(report_id)
    if not os.path.exists(p):
        return None
    with open(p, 'r', encoding='utf-8') as f:
        data = json.load(f)
    # keep same removal behavior as legacy: remove after reading
    try:
        os.remove(p)
    except Exception:
        current_app.logger.debug("Could not remove temp state file: %s", p)
    return data

@site_visit_bp.route('/form')
def form():
    # Render a simple form that will be replaced later by your real UI
    return render_template('site_visit_form.html')

@site_visit_bp.route('/api/submit/metadata', methods=['POST'])
def submit_metadata():
    try:
        data = request.get_json() or {}
        visit_info = data.get('visit_info', {})
        processed_items = data.get('report_items', [])
        signatures = data.get('signatures', {})

        report_id = f"report-{int(time.time())}"

        tech_sig = signatures.get('tech_signature')
        opman_sig = signatures.get('opMan_signature')

        tech_sig_url = None
        opman_sig_url = None

        # Try server-side signature upload if Cloudinary keys exist
        try:
            tech_sig_url = upload_base64_signature(tech_sig, f"{report_id}_tech") if tech_sig else None
            opman_sig_url = upload_base64_signature(opman_sig, f"{report_id}_opman") if opman_sig else None
        except Exception:
            current_app.logger.exception("Signature upload failed (non-fatal).")

        visit_info['tech_signature_url'] = tech_sig_url
        visit_info['opMan_signature_url'] = opman_sig_url

        _save_state(report_id, {
            'visit_info': visit_info,
            'report_items': processed_items,
            'photo_urls': []
        })

        cloud_name = current_app.config.get('CLOUDINARY_CLOUD_NAME', '')
        upload_preset = current_app.config.get('CLOUDINARY_UPLOAD_PRESET')

        return jsonify({
            "status": "success",
            "visit_id": report_id,
            "cloudinary_cloud_name": cloud_name,
            "cloudinary_upload_preset": upload_preset,
        })
    except Exception:
        current_app.logger.exception("ERROR (Metadata): %s", traceback.format_exc())
        return jsonify({"error": "Failed to process metadata"}), 500

@site_visit_bp.route('/api/submit/update-photos', methods=['POST'])
def update_photos():
    report_id = request.args.get('visit_id')
    if not report_id:
        return jsonify({"error": "Missing visit_id"}), 400
    record = _load_state(report_id)
    if not record:
        return jsonify({"error": "Report record not found"}), 500
    try:
        data = request.get_json() or {}
        photo_urls = data.get('photo_urls', [])
        record['photo_urls'] = photo_urls
        _save_state(report_id, record)
        return jsonify({"status": "success"})
    except Exception:
        current_app.logger.exception("ERROR (Update Photos): %s", traceback.format_exc())
        return jsonify({"error": "Failed to update photo URLs"}), 500

@site_visit_bp.route('/api/submit/finalize', methods=['GET'])
def finalize_report():
    report_id = request.args.get('visit_id')
    if not report_id:
        return jsonify({"error": "Missing visit_id"}), 400
    record = _load_state(report_id)
    if not record:
        return jsonify({"error": "Report not found"}), 500
    try:
        visit_info = record.get('visit_info', {})
        final_items = record.get('report_items', [])
        final_photo_urls = record.get('photo_urls', [])

        # Create generated dir
        os.makedirs(GENERATED_DIR, exist_ok=True)

        # Create Excel synchronously (quick)
        excel_path, excel_filename = create_report_workbook(GENERATED_DIR, visit_info, final_items)

        # Attempt to enqueue via RQ; fall back to in-process thread if Redis not configured
        q = get_rq_queue()
        if q is None:
            # Fallback: run in a thread (non-blocking)
            import threading
            threading.Thread(target=generate_and_send_report, args=(report_id, visit_info, final_items, GENERATED_DIR), daemon=True).start()
            return jsonify({"status": "accepted", "visit_id": report_id, "job_id": None, "status_url": url_for('site_visit_bp.report_status', visit_id=report_id, _external=True)}), 202

        job = q.enqueue(generate_and_send_report, report_id, visit_info, final_items, GENERATED_DIR)
        # store initial status in redis if possible
        conn = get_redis_conn()
        if conn is not None:
            conn.set(f"report:{report_id}", json.dumps({"status": "pending", "job_id": job.get_id()}))
        return jsonify({"status": "accepted", "visit_id": report_id, "job_id": job.get_id(), "status_url": url_for('site_visit_bp.report_status', visit_id=report_id, _external=True)}), 202
    except Exception:
        current_app.logger.exception("ERROR (Finalize): %s", traceback.format_exc())
        return jsonify({"status": "error", "error": "Internal server error"}), 500

@site_visit_bp.route('/api/report-status', methods=['GET'])
def report_status():
    visit_id = request.args.get('visit_id')
    if not visit_id:
        return jsonify({"error": "Missing visit_id"}), 400

    conn = get_redis_conn()
    if conn:
        try:
            data = conn.get(f"report:{visit_id}")
            if not data:
                return jsonify({"status": "unknown", "message": "No record found"}), 404
            return jsonify({"status": "ok", "report": json.loads(data)})
        except Exception:
            current_app.logger.exception("Error reading status from Redis")
            # fallthrough to file fallback

    # file fallback: check generated/<report_id>.status.json
    status_path = os.path.join(GENERATED_DIR, f"{visit_id}.status.json")
    if os.path.exists(status_path):
        with open(status_path, 'r', encoding='utf-8') as f:
            return jsonify({"status": "ok", "report": json.load(f)})
    return jsonify({"status": "unknown", "message": "No record found"}), 404

@site_visit_bp.route('/generated/<path:filename>')
def download_generated(filename):
    return send_from_directory(GENERATED_DIR, filename, as_attachment=True)