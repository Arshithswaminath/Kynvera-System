# app/tasks.py
import os
import cloudinary
import cloudinary.uploader
from rq import Queue
from redis import Redis
from app.models import db, Visit, ReportJob, FileAsset
from io import BytesIO
from reportlab.pdfgen import canvas
import pandas as pd

redis_url = os.environ.get("REDIS_URL")
redis_conn = Redis.from_url(redis_url) if redis_url else Redis()
q = Queue(connection=redis_conn)

def enqueue_report_job(job_id):
    q.enqueue(process_report_job, job_id)

def process_report_job(job_id):
    # Lazily import create_app to get context
    from app import create_app
    app = create_app()
    with app.app_context():
        job = ReportJob.query.get(job_id)
        if not job:
            return
        try:
            job.status = "processing"
            db.session.commit()

            visit = Visit.query.get(job.visit_id)
            assets = FileAsset.query.filter_by(visit_id=visit.id).all()

            # Generate PDF
            pdf_buffer = BytesIO()
            p = canvas.Canvas(pdf_buffer)
            p.setFont("Helvetica", 12)
            p.drawString(40, 800, f"Report for Visit {visit.id} - {visit.form_name}")
            p.drawString(40, 780, f"Building: {visit.building_name}")
            p.drawString(40, 760, f"Email: {visit.email}")
            y = 730
            for a in assets:
                p.drawString(40, y, f"{a.filename} - {a.secure_url}")
                y -= 16
                if y < 60:
                    p.showPage()
                    y = 800
            p.showPage()
            p.save()
            pdf_buffer.seek(0)

            # Generate XLSX via pandas
            rows = []
            for a in assets:
                rows.append({"filename": a.filename, "url": a.secure_url, "size": a.size})
            df = pd.DataFrame(rows)
            xlsx_buffer = BytesIO()
            with pd.ExcelWriter(xlsx_buffer, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="assets")
            xlsx_buffer.seek(0)

            # Upload artifacts to Cloudinary (as raw files)
            cloudinary.config(
                cloud_name=app.config.get("CLOUDINARY_CLOUD_NAME"),
                api_key=app.config.get("CLOUDINARY_API_KEY"),
                api_secret=app.config.get("CLOUDINARY_API_SECRET"),
            )
            folder = f"injaaz/reports/{job.id}"

            pdf_res = cloudinary.uploader.upload_large(
                pdf_buffer,
                resource_type="raw",
                folder=folder,
                public_id=f"report_{job.id}.pdf"
            )
            xlsx_res = cloudinary.uploader.upload_large(
                xlsx_buffer,
                resource_type="raw",
                folder=folder,
                public_id=f"report_{job.id}.xlsx"
            )

            job.pdf_url = pdf_res.get("secure_url")
            job.xlsx_url = xlsx_res.get("secure_url")
            job.status = "done"
            db.session.commit()

        except Exception as exc:
            job.status = "failed"
            db.session.commit()
            app.logger.exception("Error processing report job %s", job_id)
            raise