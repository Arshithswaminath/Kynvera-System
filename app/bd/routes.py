from flask import Blueprint, jsonify, render_template, request, redirect, url_for, current_app, send_file
import os
import mimetypes
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import (
    User, Submission, Job, File,
    EmailAutomation, EmailRecipientGroup, db,
)
from common.email_service import send_email, is_email_configured
from module_files import service as files_service
from app.bd import email_automation as ea

bd_bp = Blueprint('bd_bp', __name__, url_prefix='/bd')


def _is_bd_user(user):
    return ea.is_bd_user(user)


def _current_user():
    uid = get_jwt_identity()
    try:
        uid = int(uid)
    except (TypeError, ValueError):
        return None
    return db.session.get(User, uid)


def _parse_emails(value):
    return ea.parse_emails(value)


def _parse_submission_ids(value):
    return ea.parse_submission_ids(value)


def _parse_file_item_ids(value):
    return ea.parse_file_item_ids(value)


def _collect_files_item_attachments(file_item_ids):
    return ea.collect_files_item_attachments(file_item_ids)


def _collect_submission_attachments(submission):
    return ea.collect_submission_attachments(submission)


def _require_bd_user():
    user = _current_user()
    if not _is_bd_user(user):
        return None, (jsonify({'success': False, 'error': 'Access denied'}), 403)
    return user, None


def _automation_or_error(auto_id, user, need_edit=False, need_run=False):
    auto = db.session.get(EmailAutomation, auto_id)
    if not auto:
        return None, (jsonify({'success': False, 'error': 'Automation not found'}), 404)
    if need_edit and not ea.can_edit_automation(user, auto):
        return None, (jsonify({'success': False, 'error': 'Access denied'}), 403)
    if need_run and not ea.can_run_automation(user, auto):
        return None, (jsonify({'success': False, 'error': 'Access denied'}), 403)
    if not ea.can_view_automation(user, auto):
        return None, (jsonify({'success': False, 'error': 'Access denied'}), 403)
    return auto, None


def _serialize_auto_for(user, auto):
    data = ea.serialize_automation(auto)
    data['can_edit'] = ea.can_edit_automation(user, auto)
    data['can_run'] = ea.can_run_automation(user, auto)
    return data


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
    user = _current_user()
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
    user, err = _require_bd_user()
    if err:
        return err

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
    user, err = _require_bd_user()
    if err:
        return err

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


@bd_bp.route('/email-module/cloud-files', methods=['GET'])
@jwt_required()
def list_email_cloud_files():
    """List Files-module items BD users can attach to outbound email."""
    user, err = _require_bd_user()
    if err:
        return err

    try:
        tree = files_service.build_tree()
    except Exception:
        current_app.logger.exception('Failed to load Files tree for BD email')
        return jsonify({'success': False, 'error': 'Unable to load cloud files'}), 500

    folders = tree.get('folders') or []
    folder_by_id = {f['id']: f for f in folders if isinstance(f, dict) and f.get('id') is not None}

    def folder_path(folder_id):
        parts = []
        seen = set()
        cur = folder_id
        while cur is not None and cur not in seen:
            seen.add(cur)
            folder = folder_by_id.get(cur)
            if not folder:
                break
            parts.append(folder.get('name') or 'Folder')
            cur = folder.get('parent_id')
        return ' / '.join(reversed(parts)) if parts else 'Files'

    items = []
    for item in (tree.get('items') or []):
        if not isinstance(item, dict) or item.get('id') is None:
            continue
        items.append({
            'id': item.get('id'),
            'name': item.get('name') or item.get('filename') or 'File',
            'filename': item.get('filename') or item.get('name') or 'file',
            'mime_type': item.get('mime_type') or '',
            'size_label': item.get('size_label') or '—',
            'folder_id': item.get('folder_id'),
            'folder_path': folder_path(item.get('folder_id')),
            'sync_status': item.get('sync_status') or 'local',
            'source_module': item.get('source_module') or '',
        })

    folder_rows = []
    for folder in folders:
        if not isinstance(folder, dict) or folder.get('id') is None:
            continue
        folder_rows.append({
            'id': folder.get('id'),
            'name': folder.get('name') or 'Folder',
            'parent_id': folder.get('parent_id'),
            'path_key': folder.get('path_key') or '',
            'folder_path': folder_path(folder.get('id')),
        })

    return jsonify({'success': True, 'folders': folder_rows, 'items': items}), 200


@bd_bp.route('/email-module/send', methods=['POST'])
@jwt_required()
def send_email_to_gm():
    user, err = _require_bd_user()
    if err:
        return err

    payload = request.get_json(silent=True) or request.form.to_dict()
    to_value = payload.get('to') or ''
    cc_value = payload.get('cc') or ''
    subject = (payload.get('subject') or '').strip()
    message = (payload.get('message') or '').strip()
    submission_ids = _parse_submission_ids(payload.get('submission_ids'))
    file_item_ids = _parse_file_item_ids(payload.get('file_item_ids'))

    if not subject:
        return jsonify({'success': False, 'error': 'Subject is required'}), 400
    if not message:
        return jsonify({'success': False, 'error': 'Message is required'}), 400

    recipients = _parse_emails(to_value)
    if not recipients:
        return jsonify({'success': False, 'error': 'At least one To recipient is required'}), 400

    cc_list = _parse_emails(cc_value)

    if not is_email_configured():
        return jsonify({'success': False, 'error': 'Email is not configured'}), 400

    attachments = []
    missing_documents = []
    submission_attachments_found = False
    if submission_ids:
        for submission_id in submission_ids:
            q = Submission.query.filter_by(submission_id=submission_id)
            if user.role != 'admin':
                q = q.filter_by(business_dev_id=user.id)
            submission = q.first()
            if not submission:
                continue
            submission_attachments, found_documents = _collect_submission_attachments(submission)
            attachments.extend(submission_attachments)
            if found_documents:
                submission_attachments_found = True
            else:
                missing_documents.append(submission.submission_id)

    cloud_attachments, missing_cloud = _collect_files_item_attachments(file_item_ids)
    if missing_cloud:
        return jsonify({
            'success': False,
            'error': 'Some cloud files could not be attached: ' + ', '.join(missing_cloud[:8])
        }), 400
    attachments.extend(cloud_attachments)

    if submission_ids and not submission_attachments_found and not cloud_attachments:
        return jsonify({'success': False, 'error': 'No PDF/Excel documents found for the selected submissions'}), 400

    signature = f"\n\nSent by: {user.full_name or user.username}\nInjaaz Team"
    body = f"{message}{signature}"
    html_body = (
        "<html><body>"
        f"<p>{message.replace(chr(10), '<br>')}</p>"
        f"<p><strong>Sent by:</strong> {user.full_name or user.username}<br>Injaaz Team</p>"
        "</body></html>"
    )

    related_bits = list(submission_ids)
    if file_item_ids:
        related_bits.append('files:' + ','.join(str(i) for i in file_item_ids))

    sent = send_email(
        recipients,
        subject,
        body,
        html_body=html_body,
        cc=cc_list or None,
        attachments=attachments or None,
        source='bd_email',
        sent_by_user_id=user.id,
        related_id=','.join(related_bits) if related_bits else None,
    )

    if sent:
        current_app.logger.info(f"BD email sent by user {user.id} to {recipients}")
        if missing_documents:
            return jsonify({
                'success': True,
                'message': 'Email sent, but some submissions have no documents',
                'missing_documents': missing_documents
            }), 200
        return jsonify({'success': True, 'message': 'Email sent successfully'}), 200
    return jsonify({'success': False, 'error': 'Failed to send email'}), 500


@bd_bp.route('/email-module/groups', methods=['GET'])
@jwt_required()
def list_email_groups():
    user, err = _require_bd_user()
    if err:
        return err
    scope = request.args.get('scope')
    groups = ea.visible_groups_query(user, scope=scope).all()
    items = []
    for group in groups:
        data = ea.serialize_group(group)
        data['can_edit'] = ea.can_edit_group(user, group)
        items.append(data)
    return jsonify({'success': True, 'items': items}), 200


@bd_bp.route('/email-module/groups', methods=['POST'])
@jwt_required()
def create_email_group():
    user, err = _require_bd_user()
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    name = (payload.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'Group name is required'}), 400
    emails = ea.emails_to_text(payload.get('emails'))
    if not emails:
        return jsonify({'success': False, 'error': 'At least one email is required'}), 400
    group = EmailRecipientGroup(
        name=name[:120],
        emails=emails,
        scope=ea.parse_scope(payload.get('scope')),
        owner_id=user.id,
    )
    db.session.add(group)
    db.session.commit()
    data = ea.serialize_group(group)
    data['can_edit'] = True
    return jsonify({'success': True, 'item': data}), 201


@bd_bp.route('/email-module/groups/<int:group_id>', methods=['PATCH'])
@jwt_required()
def update_email_group(group_id):
    user, err = _require_bd_user()
    if err:
        return err
    group = db.session.get(EmailRecipientGroup, group_id)
    if not group:
        return jsonify({'success': False, 'error': 'Group not found'}), 404
    if not ea.can_edit_group(user, group):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    payload = request.get_json(silent=True) or {}
    if 'name' in payload:
        name = (payload.get('name') or '').strip()
        if not name:
            return jsonify({'success': False, 'error': 'Group name is required'}), 400
        group.name = name[:120]
    if 'emails' in payload:
        emails = ea.emails_to_text(payload.get('emails'))
        if not emails:
            return jsonify({'success': False, 'error': 'At least one email is required'}), 400
        group.emails = emails
    if 'scope' in payload:
        group.scope = ea.parse_scope(payload.get('scope'), default=group.scope)
    db.session.commit()
    data = ea.serialize_group(group)
    data['can_edit'] = True
    return jsonify({'success': True, 'item': data}), 200


@bd_bp.route('/email-module/groups/<int:group_id>', methods=['DELETE'])
@jwt_required()
def delete_email_group(group_id):
    user, err = _require_bd_user()
    if err:
        return err
    group = db.session.get(EmailRecipientGroup, group_id)
    if not group:
        return jsonify({'success': False, 'error': 'Group not found'}), 404
    if not ea.can_edit_group(user, group):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    db.session.delete(group)
    db.session.commit()
    return jsonify({'success': True}), 200


@bd_bp.route('/email-module/automations', methods=['GET'])
@jwt_required()
def list_email_automations():
    user, err = _require_bd_user()
    if err:
        return err
    scope = request.args.get('scope')
    rows = ea.visible_automations_query(user, scope=scope).all()
    return jsonify({
        'success': True,
        'items': [_serialize_auto_for(user, row) for row in rows],
    }), 200


@bd_bp.route('/email-module/automations', methods=['POST'])
@jwt_required()
def create_email_automation():
    user, err = _require_bd_user()
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    auto = EmailAutomation(owner_id=user.id, name='Untitled', scope=ea.SCOPE_PERSONAL)
    try:
        ea.apply_automation_fields(auto, payload, creating=True)
        db.session.add(auto)
        db.session.flush()
        if 'attachments' in payload:
            ea.replace_attachments(auto, ea.parse_attachment_payload(payload.get('attachments')))
        db.session.commit()
    except ea.AutomationError as exc:
        db.session.rollback()
        return jsonify({'success': False, 'error': exc.message}), exc.status
    return jsonify({'success': True, 'item': _serialize_auto_for(user, auto)}), 201


@bd_bp.route('/email-module/automations/<int:auto_id>', methods=['GET'])
@jwt_required()
def get_email_automation(auto_id):
    user, err = _require_bd_user()
    if err:
        return err
    auto, err = _automation_or_error(auto_id, user)
    if err:
        return err
    return jsonify({'success': True, 'item': _serialize_auto_for(user, auto)}), 200


@bd_bp.route('/email-module/automations/<int:auto_id>', methods=['PATCH'])
@jwt_required()
def update_email_automation(auto_id):
    user, err = _require_bd_user()
    if err:
        return err
    auto, err = _automation_or_error(auto_id, user, need_edit=True)
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    try:
        ea.apply_automation_fields(auto, payload, creating=False)
        if 'attachments' in payload:
            ea.replace_attachments(auto, ea.parse_attachment_payload(payload.get('attachments')))
        db.session.commit()
    except ea.AutomationError as exc:
        db.session.rollback()
        return jsonify({'success': False, 'error': exc.message}), exc.status
    return jsonify({'success': True, 'item': _serialize_auto_for(user, auto)}), 200


@bd_bp.route('/email-module/automations/<int:auto_id>', methods=['DELETE'])
@jwt_required()
def delete_email_automation(auto_id):
    user, err = _require_bd_user()
    if err:
        return err
    auto, err = _automation_or_error(auto_id, user, need_edit=True)
    if err:
        return err
    db.session.delete(auto)
    db.session.commit()
    return jsonify({'success': True}), 200


@bd_bp.route('/email-module/automations/<int:auto_id>/run', methods=['POST'])
@jwt_required()
def run_email_automation(auto_id):
    user, err = _require_bd_user()
    if err:
        return err
    auto, err = _automation_or_error(auto_id, user, need_run=True)
    if err:
        return err
    try:
        result = ea.run_automation(auto, user=user, trigger='manual')
    except ea.AutomationError as exc:
        return jsonify({'success': False, 'error': exc.message, 'skipped': exc.skipped}), exc.status
    return jsonify(result), 200


@bd_bp.route('/email-module/automations/<int:auto_id>/history', methods=['GET'])
@jwt_required()
def email_automation_history(auto_id):
    user, err = _require_bd_user()
    if err:
        return err
    auto, err = _automation_or_error(auto_id, user)
    if err:
        return err
    try:
        limit = int(request.args.get('limit') or 20)
    except (TypeError, ValueError):
        limit = 20
    return jsonify({'success': True, 'items': ea.list_run_history(auto, limit=limit)}), 200


@bd_bp.route('/email-module/automations/<int:auto_id>/attachments/upload', methods=['POST'])
@jwt_required()
def upload_email_automation_attachment(auto_id):
    user, err = _require_bd_user()
    if err:
        return err
    auto, err = _automation_or_error(auto_id, user, need_edit=True)
    if err:
        return err
    file_storage = request.files.get('file')
    if not file_storage or not file_storage.filename:
        return jsonify({'success': False, 'error': 'Choose a file to upload'}), 400
    require_new = str(request.form.get('require_new') or '').strip().lower() in ('1', 'true', 'yes', 'on')
    try:
        item, folder = ea.save_upload_for_automation(file_storage, created_by=user.id)
        slot = ea.append_linked_file_slot(auto, item.id, require_new=require_new)
    except Exception as exc:
        current_app.logger.exception('Failed to upload automation attachment')
        return jsonify({'success': False, 'error': str(exc) or 'Upload failed'}), 400
    data = _serialize_auto_for(user, auto)
    return jsonify({
        'success': True,
        'item': data,
        'files_item': item.to_dict(),
        'folder_id': folder.id,
        'slot': ea.serialize_attachment(slot),
    }), 201
