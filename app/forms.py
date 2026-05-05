# app/forms.py
from flask import Blueprint, request, current_app, jsonify, render_template, abort, url_for
from werkzeug.utils import secure_filename
from sqlalchemy.exc import SQLAlchemyError
import os
import cloudinary
import cloudinary.uploader
import json

from app.models import db, Visit, ReportItem, FileAsset, ReportJob
from app.form_schemas import FORM_SCHEMAS
from app.tasks import enqueue_report_job

bp = Blueprint("forms", __name__, template_folder="../templates", static_folder="../static", url_prefix="/forms")

ALLOWED_EXT = {"png", "jpg", "jpeg", "gif"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB (standardized across all modules)

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

@bp.route("/")
def forms_dashboard():
    # Render a small dashboard listing forms
    forms = [{"name": k, "title": v["title"]} for k, v in FORM_SCHEMAS.items()]
    return render_template("forms_dashboard.html", forms=forms)

@bp.route("/<form_name>")
def render_form(form_name):
    schema = FORM_SCHEMAS.get(form_name)
    if not schema:
        abort(404)
    return render_template("form.html", form_name=form_name, schema=schema)

@bp.route("/<form_name>/submit", methods=["POST"])
def submit_form(form_name):
    schema = FORM_SCHEMAS.get(form_name)
    if not schema:
        abort(404)

    try:
        # Basic required field check
        required = [f["name"] for f in schema["fields"] if f.get("required")]
        for r in required:
            if not request.form.get(r):
                return jsonify({"error": f"Missing required field: {r}"}), 400

        # Create Visit record
        visit = Visit(form_name=form_name,
                      building_name=request.form.get("building_name"),
                      email=request.form.get("email"))
        db.session.add(visit)
        db.session.flush()  # so visit.id is available

        # Save all fields as ReportItems for flexibility (one item per defined field or a single item)
        # We'll store the main notes as a single ReportItem to keep schema flexible.
        notes = request.form.get("notes") or request.form.get("checklist") or request.form.get("notes")
        ri = ReportItem(visit_id=visit.id, title=f"{schema['title']} submission", description=notes or "")
        db.session.add(ri)

        # Upload files if present
        uploaded_files = request.files.getlist("photos")
        if uploaded_files:
            cloudinary.config(
                cloud_name=current_app.config.get("CLOUDINARY_CLOUD_NAME"),
                api_key=current_app.config.get("CLOUDINARY_API_KEY"),
                api_secret=current_app.config.get("CLOUDINARY_API_SECRET"),
            )
            for f in uploaded_files:
                if f.filename == "":
                    continue
                if not allowed_file(f.filename):
                    return jsonify({"error": f"File type not allowed: {f.filename}"}), 400
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(0)
                if size > MAX_FILE_SIZE:
                    return jsonify({"error": f"File too large: {f.filename}"}), 400

                filename = secure_filename(f.filename)
                upload_opts = {"folder": f"injaaz/{form_name}/{visit.id}"}
                # upload from file object directly
                result = cloudinary.uploader.upload(f, **upload_opts)
                asset = FileAsset(visit_id=visit.id,
                                  public_id=result.get("public_id"),
                                  secure_url=result.get("secure_url"),
                                  filename=filename,
                                  size=size)
                db.session.add(asset)

        # Enqueue background job
        job = ReportJob(visit_id=visit.id, status="queued")
        db.session.add(job)
        db.session.commit()

        enqueue_report_job(job.id)

        status_url = url_for("forms.report_status", visit_id=visit.id, _external=True)
        return jsonify({"visit_id": visit.id, "job_id": job.id, "status": "queued", "status_url": status_url}), 202

    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.exception("DB error in submit_form")
        return jsonify({"error": "database error"}), 500
    except Exception as e:
        current_app.logger.exception("Server error in submit_form")
        return jsonify({"error": str(e)}), 500

@bp.route("/report-status")
def report_status():
    visit_id = request.args.get("visit_id", type=int)
    if not visit_id:
        return jsonify({"error": "visit_id required"}), 400
    job = ReportJob.query.filter_by(visit_id=visit_id).order_by(ReportJob.id.desc()).first()
    if not job:
        return jsonify({"status": "not-found"}), 404
    return jsonify({
        "job_id": job.id,
        "status": job.status,
        "pdf_url": job.pdf_url,
        "xlsx_url": job.xlsx_url
    })