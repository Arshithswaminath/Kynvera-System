from flask import Blueprint, jsonify, render_template, request, redirect, url_for, current_app, send_file
import os
import mimetypes
from urllib.parse import urlparse
from urllib.request import urlopen
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import User, Submission, Job, File
from common.email_service import send_email

bd_bp = Blueprint('bd_bp', __name__, url_prefix='/bd')


def _is_bd_user(user):
    return user and (user.designation == 'business_development')


def _parse_emails(value):
    if not value:
        return []
    if isinstance(value, list):
        return [v.strip() for v in value if v and str(v).strip()]
    raw = str(value)
    parts = [p.strip() for p in raw.replace(';', ',').split(',')]
    return [p for p in parts if p]


def _parse_submission_ids(value):
    if not value:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if v and str(v).strip()]
    raw = str(value)
    parts = [p.strip() for p in raw.replace(';', ',').split(',')]
    return [p for p in parts if p]


def _download_attachment(url, fallback_name):
    if url and url.startswith('/generated/'):
        base_dir = current_app.config.get(
            "GENERATED_DIR",
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "generated")
        )
        rel_path = url.lstrip('/')
        if rel_path.startswith('generated/'):
            rel_path = rel_path.replace('generated/', '', 1)
        local_path = os.path.join(base_dir, rel_path)
        if os.path.exists(local_path):
            with open(local_path, "rb") as fh:
                data = fh.read()
            mime_type = mimetypes.guess_type(local_path)[0] or "application/octet-stream"
            return {"content": data, "filename": os.path.basename(local_path), "mime_type": mime_type}

    if url and url.startswith('/'):
        base_url = current_app.config.get("APP_BASE_URL") or request.url_root.rstrip('/')
        url = f"{base_url}{url}"

    parsed = urlparse(url)
    filename = os.path.basename(parsed.path) or fallback_name
    with urlopen(url) as response:
        data = response.read()
    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return {"content": data, "filename": filename, "mime_type": mime_type}


def _collect_submission_attachments(submission):
    attachments = []
    found_documents = False

    report_files = File.query.filter_by(
        submission_id=submission.id
    ).filter(
        File.file_type.in_(['report_excel', 'report_pdf'])
    ).all()

    for file in report_files:
        if file.file_path and os.path.exists(file.file_path):
            attachments.append(file.file_path)
            found_documents = True
            continue
        if file.cloud_url:
            try:
                fallback = f"{submission.submission_id}-{file.file_type}.pdf"
                if file.file_type == 'report_excel':
                    fallback = f"{submission.submission_id}.xlsx"
                attachments.append(_download_attachment(file.cloud_url, fallback))
                found_documents = True
            except Exception:
                current_app.logger.exception("Failed to download report %s", file.cloud_url)

    if found_documents:
        return attachments, True

    job = Job.query.filter_by(
        submission_id=submission.id,
        status='completed'
    ).order_by(Job.completed_at.desc()).first()
    if job and job.result_data:
        pdf_url = job.result_data.get('pdf_url') or job.result_data.get('pdf')
        excel_url = job.result_data.get('excel_url') or job.result_data.get('excel')
        try:
            if pdf_url:
                attachments.append(_download_attachment(pdf_url, f"{submission.submission_id}.pdf"))
                found_documents = True
            if excel_url:
                attachments.append(_download_attachment(excel_url, f"{submission.submission_id}.xlsx"))
                found_documents = True
        except Exception:
            current_app.logger.exception("Failed to download job result files")

    return attachments, found_documents


def _get_report_urls(submission):
    pdf_url = None
    excel_url = None

    report_files = File.query.filter_by(
        submission_id=submission.id
    ).filter(
        File.file_type.in_(['report_excel', 'report_pdf'])
    ).all()

    for file in report_files:
        if file.file_type == 'report_pdf':
            if file.cloud_url:
                pdf_url = file.cloud_url
            elif file.file_path and os.path.exists(file.file_path):
                pdf_url = url_for('bd_bp.download_attachment', submission_id=submission.submission_id, file_type='report_pdf')
        if file.file_type == 'report_excel':
            if file.cloud_url:
                excel_url = file.cloud_url
            elif file.file_path and os.path.exists(file.file_path):
                excel_url = url_for('bd_bp.download_attachment', submission_id=submission.submission_id, file_type='report_excel')

    if not pdf_url or not excel_url:
        job = Job.query.filter_by(
            submission_id=submission.id,
            status='completed'
        ).order_by(Job.completed_at.desc()).first()
        if job and job.result_data:
            pdf_url = pdf_url or job.result_data.get('pdf_url') or job.result_data.get('pdf')
            excel_url = excel_url or job.result_data.get('excel_url') or job.result_data.get('excel')

    return pdf_url, excel_url


def _get_gm_emails():
    gms = User.query.filter(
        User.is_active == True,
        User.designation == 'general_manager'
    ).all()
    return [u.email for u in gms if u and u.email]


def _get_role_emails(designation):
    users = User.query.filter(
        User.is_active == True,
        User.designation == designation
    ).all()
    return [u.email for u in users if u and u.email]


@bd_bp.route('/email-module', methods=['GET'])
@jwt_required()
def email_module():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not _is_bd_user(user):
        return redirect('/dashboard')

    gm_emails = _get_gm_emails()
    bd_emails = _get_role_emails('business_development')
    po_emails = _get_role_emails('procurement')
    om_emails = _get_role_emails('operations_manager')
    supervisor_emails = _get_role_emails('supervisor')
    submissions = Submission.query.filter(
        Submission.business_dev_id == user.id,
        Submission.business_dev_approved_at.isnot(None)
    ).order_by(Submission.business_dev_approved_at.desc()).limit(100).all()
    return render_template(
        'bd_email_module.html',
        gm_emails=gm_emails,
        submissions=submissions,
        bd_emails=bd_emails,
        po_emails=po_emails,
        om_emails=om_emails,
        supervisor_emails=supervisor_emails
    )


@bd_bp.route('/email-module/attachments', methods=['GET'])
@jwt_required()
def list_email_attachments():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not _is_bd_user(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    submission_ids = _parse_submission_ids(request.args.get('ids'))
    if not submission_ids:
        return jsonify({'success': True, 'items': []}), 200

    items = []
    for submission_id in submission_ids:
        submission = Submission.query.filter_by(
            submission_id=submission_id,
            business_dev_id=user.id
        ).first()
        if not submission:
            continue
        pdf_url, excel_url = _get_report_urls(submission)
        items.append({
            'submission_id': submission.submission_id,
            'pdf_url': pdf_url,
            'excel_url': excel_url
        })

    return jsonify({'success': True, 'items': items}), 200


@bd_bp.route('/email-module/attachment/<submission_id>/<file_type>', methods=['GET'])
@jwt_required()
def download_attachment(submission_id, file_type):
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not _is_bd_user(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    if file_type not in ['report_pdf', 'report_excel']:
        return jsonify({'success': False, 'error': 'Invalid attachment type'}), 400

    submission = Submission.query.filter_by(
        submission_id=submission_id,
        business_dev_id=user.id
    ).first()
    if not submission:
        return jsonify({'success': False, 'error': 'Submission not found'}), 404

    file = File.query.filter_by(
        submission_id=submission.id,
        file_type=file_type
    ).first()
    if not file or not file.file_path or not os.path.exists(file.file_path):
        return jsonify({'success': False, 'error': 'File not available'}), 404

    mime_type = mimetypes.guess_type(file.file_path)[0] or 'application/octet-stream'
    return send_file(file.file_path, mimetype=mime_type, as_attachment=False)


@bd_bp.route('/email-module/send', methods=['POST'])
@jwt_required()
def send_email_to_gm():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not _is_bd_user(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    payload = request.get_json(silent=True) or request.form.to_dict()
    to_value = payload.get('to') or ''
    cc_value = payload.get('cc') or ''
    subject = (payload.get('subject') or '').strip()
    message = (payload.get('message') or '').strip()
    submission_ids = _parse_submission_ids(payload.get('submission_ids'))

    if not subject:
        return jsonify({'success': False, 'error': 'Subject is required'}), 400
    if not message:
        return jsonify({'success': False, 'error': 'Message is required'}), 400

    recipients = _parse_emails(to_value)
    if not recipients:
        recipients = _get_gm_emails()

    if not recipients:
        return jsonify({'success': False, 'error': 'No General Manager email found'}), 400

    cc_list = _parse_emails(cc_value)

    mail_server = current_app.config.get('MAIL_SERVER')
    mail_port = current_app.config.get('MAIL_PORT')
    if not mail_server or not mail_port:
        return jsonify({'success': False, 'error': 'Email server is not configured'}), 400

    attachments = []
    missing_documents = []
    if submission_ids:
        for submission_id in submission_ids:
            submission = Submission.query.filter_by(
                submission_id=submission_id,
                business_dev_id=user.id
            ).first()
            if not submission:
                continue
            submission_attachments, found_documents = _collect_submission_attachments(submission)
            attachments.extend(submission_attachments)
            if not found_documents:
                missing_documents.append(submission.submission_id)

    if submission_ids and not attachments:
        return jsonify({'success': False, 'error': 'No PDF/Excel documents found for the selected submissions'}), 400

    signature = f"\n\nSent by: {user.full_name or user.username}\nInjaaz Team"
    body = f"{message}{signature}"
    html_body = (
        "<html><body>"
        f"<p>{message.replace(chr(10), '<br>')}</p>"
        f"<p><strong>Sent by:</strong> {user.full_name or user.username}<br>Injaaz Team</p>"
        "</body></html>"
    )

    sent = send_email(
        recipients,
        subject,
        body,
        html_body=html_body,
        cc=cc_list or None,
        attachments=attachments or None
    )

    if sent:
        current_app.logger.info(f"BD email sent by user {user_id} to {recipients}")
        if missing_documents:
            return jsonify({
                'success': True,
                'message': 'Email sent, but some submissions have no documents',
                'missing_documents': missing_documents
            }), 200
        return jsonify({'success': True, 'message': 'Email sent to General Manager'}), 200
    return jsonify({'success': False, 'error': 'Failed to send email'}), 500
