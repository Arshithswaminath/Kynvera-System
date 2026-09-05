"""Local Files storage: folders, items, save-from-module builders."""

from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime
from io import BytesIO
from typing import Optional, Tuple

from flask import current_app
from sqlalchemy.orm import joinedload
from werkzeug.utils import secure_filename

from app.models import (
    FilesFolder,
    FilesItem,
    LeaveEmployee,
    LeaveLog,
    LeavePlan,
    db,
)
from common.datetime_utils import utc_now_naive
from module_files.catalog import (
    DEFAULT_FOLDER_TREE,
    get_excel_template,
    get_module_catalog,
    list_excel_templates_for_user,
    user_can_see_excel_template,
)

logger = logging.getLogger(__name__)

XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
PDF_MIME = 'application/pdf'


def _files_root() -> str:
    gen = current_app.config.get('GENERATED_DIR') or os.path.join(current_app.root_path, 'generated')
    root = os.path.join(gen, 'files')
    os.makedirs(root, exist_ok=True)
    return root


def ensure_default_folders(created_by: Optional[int] = None) -> dict:
    """Create HR / Leave / Manpower folder tree if missing. Returns path_key → folder."""
    by_key = {f.path_key: f for f in FilesFolder.query.filter(FilesFolder.path_key.isnot(None)).all()}
    now = utc_now_naive()
    for spec in DEFAULT_FOLDER_TREE:
        key = spec['path_key']
        if key in by_key:
            continue
        parent_id = None
        parent_key = spec.get('parent_key')
        if parent_key:
            parent = by_key.get(parent_key)
            if not parent:
                # Parent should already exist from earlier loop order
                parent = FilesFolder.query.filter_by(path_key=parent_key).first()
            parent_id = parent.id if parent else None
        folder = FilesFolder(
            name=spec['name'],
            parent_id=parent_id,
            path_key=key,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        db.session.add(folder)
        db.session.flush()
        by_key[key] = folder
    db.session.commit()
    try:
        ensure_brand_kit(created_by=created_by, folders=by_key)
    except Exception:
        logger.exception('Could not seed Kynvera brand assets into Files')
    return by_key


BRAND_KIT_SOURCE_KIND = 'brand-kit-2.0'
BRAND_ASSET_SOURCE_KIND = 'brand-asset'


def _remove_seeded_brand_kit_pdf() -> None:
    """Drop previously seeded brand-kit PDFs from Files. The PDF stays in the repo."""
    rows = FilesItem.query.filter_by(source_kind=BRAND_KIT_SOURCE_KIND).all()
    for item in rows:
        try:
            delete_item(item.id)
        except Exception:
            logger.exception('Could not remove seeded brand kit PDF (item %s)', item.id)


def ensure_brand_kit(created_by: Optional[int] = None, folders: Optional[dict] = None) -> list:
    """Place logo files into Files → Branding (idempotent).

    The brand kit PDF is kept in the codebase (`static/brand/`) and is not
    shown in the Files app.
    """
    from common.kynvera_brand import existing_logos

    _remove_seeded_brand_kit_pdf()

    folder = (folders or {}).get('branding')
    if folder is None:
        folder = FilesFolder.query.filter_by(path_key='branding').first()
    if folder is None:
        return []

    seeded = []
    for logo in existing_logos():
        already = (
            FilesItem.query.filter_by(folder_id=folder.id, filename=logo.files_filename)
            .first()
        )
        if already:
            continue
        with open(logo.abs_path, 'rb') as fh:
            data = fh.read()
        seeded.append(
            save_bytes_to_folder(
                folder=folder,
                data=data,
                display_name=logo.label,
                filename=logo.files_filename,
                mime_type='image/png',
                source_module='branding',
                source_kind=BRAND_ASSET_SOURCE_KIND,
                created_by=created_by,
            )
        )
    return seeded


def get_folder_by_path_key(path_key: str, created_by: Optional[int] = None) -> FilesFolder:
    ensure_default_folders(created_by=created_by)
    folder = FilesFolder.query.filter_by(path_key=path_key).first()
    if not folder:
        raise ValueError(f'Folder not found for path_key={path_key}')
    return folder


def build_tree() -> dict:
    ensure_default_folders()
    folders = FilesFolder.query.order_by(FilesFolder.name.asc()).all()
    items = (
        FilesItem.query.options(joinedload(FilesItem.folder))
        .order_by(FilesItem.updated_at.desc())
        .all()
    )
    return {
        'folders': [f.to_dict() for f in folders],
        'items': [i.to_dict() for i in items],
    }


def _safe_store_name(filename: str) -> str:
    base = secure_filename(filename) or 'file.bin'
    return f'{uuid.uuid4().hex[:12]}_{base}'


def save_bytes_to_folder(
    *,
    folder: FilesFolder,
    data: bytes,
    display_name: str,
    filename: str,
    mime_type: str,
    source_module: Optional[str],
    source_kind: Optional[str],
    created_by: Optional[int],
) -> FilesItem:
    folder_dir = os.path.join(_files_root(), str(folder.id))
    os.makedirs(folder_dir, exist_ok=True)
    store_name = _safe_store_name(filename)
    abs_path = os.path.join(folder_dir, store_name)
    with open(abs_path, 'wb') as fh:
        fh.write(data)

    # Store path relative to GENERATED_DIR for portability
    gen = current_app.config.get('GENERATED_DIR') or ''
    stored = abs_path
    if gen and abs_path.startswith(gen):
        stored = os.path.relpath(abs_path, gen)

    now = utc_now_naive()
    item = FilesItem(
        folder_id=folder.id,
        name=display_name,
        filename=filename,
        mime_type=mime_type,
        size_bytes=len(data),
        stored_path=stored,
        source_module=source_module,
        source_kind=source_kind,
        sync_status='local',
        created_by=created_by,
        created_at=now,
        updated_at=now,
    )
    db.session.add(item)
    db.session.commit()
    return item


def resolve_item_abs_path(item: FilesItem) -> str:
    path = item.stored_path or ''
    if os.path.isabs(path) and os.path.isfile(path):
        return path
    gen = current_app.config.get('GENERATED_DIR') or ''
    candidate = os.path.join(gen, path) if gen else path
    if os.path.isfile(candidate):
        return candidate
    # Fallback: under files root
    alt = os.path.join(_files_root(), path)
    if os.path.isfile(alt):
        return alt
    raise FileNotFoundError(f'File missing on disk: {item.filename}')


def create_folder(name: str, parent_id: Optional[int], created_by: Optional[int]) -> FilesFolder:
    name = (name or '').strip()
    if not name:
        raise ValueError('Folder name is required')
    if parent_id is not None:
        parent = db.session.get(FilesFolder, parent_id)
        if not parent:
            raise ValueError('Parent folder not found')
    now = utc_now_naive()
    folder = FilesFolder(
        name=name,
        parent_id=parent_id,
        path_key=None,
        created_by=created_by,
        created_at=now,
        updated_at=now,
    )
    db.session.add(folder)
    db.session.commit()
    return folder


def rename_folder(folder_id: int, name: str) -> FilesFolder:
    name = (name or '').strip()
    if not name:
        raise ValueError('Folder name is required')
    folder = db.session.get(FilesFolder, folder_id)
    if not folder:
        raise ValueError('Folder not found')
    folder.name = name
    folder.updated_at = utc_now_naive()
    db.session.commit()
    return folder


def rename_item(item_id: int, name: str) -> FilesItem:
    name = (name or '').strip()
    if not name:
        raise ValueError('Name is required')
    item = db.session.get(FilesItem, item_id)
    if not item:
        raise ValueError('File not found')
    item.name = name
    # Keep extension on filename if present
    _, ext = os.path.splitext(item.filename or '')
    safe = re.sub(r'[^\w.\- ()]+', '_', name).strip() or item.filename
    if ext and not safe.lower().endswith(ext.lower()):
        safe = f'{safe}{ext}'
    item.filename = safe
    item.updated_at = utc_now_naive()
    if item.sync_status == 'synced':
        item.sync_status = 'local'  # needs re-sync after rename
    db.session.commit()
    return item


def _collect_folder_ids(folder_id: int) -> list[int]:
    """Return folder_id and all descendant folder ids (depth-first)."""
    ids = [folder_id]
    kids = FilesFolder.query.filter_by(parent_id=folder_id).all()
    for kid in kids:
        ids.extend(_collect_folder_ids(kid.id))
    return ids


def delete_item(item_id: int) -> dict:
    """Delete a file from DB + local disk. Returns drive_file_id if present for Drive cleanup."""
    item = db.session.get(FilesItem, item_id)
    if not item:
        raise ValueError('File not found')
    drive_file_id = item.drive_file_id
    disk_path = None
    try:
        disk_path = resolve_item_abs_path(item)
    except FileNotFoundError:
        disk_path = None

    # Remove Drive copy first while we still have a clear intent + id
    drive_removed = None
    if drive_file_id:
        try:
            from module_files import drive_service as _drive
            drive_removed = bool(_drive.delete_on_drive_item(drive_file_id))
        except Exception:
            logger.exception('Drive delete during item delete failed for %s', item_id)
            drive_removed = False

    db.session.delete(item)
    db.session.commit()
    if disk_path and os.path.isfile(disk_path):
        try:
            os.remove(disk_path)
        except OSError:
            logger.exception('Could not remove local file %s', disk_path)
    return {
        'id': item_id,
        'drive_file_id': drive_file_id,
        'drive_removed': drive_removed,
    }


def delete_folder(folder_id: int) -> dict:
    """Delete folder + descendants + items. Blocks seeded catalog folders (path_key set)."""
    folder = db.session.get(FilesFolder, folder_id)
    if not folder:
        raise ValueError('Folder not found')
    if folder.path_key:
        raise ValueError('System folders cannot be deleted. You can rename them instead.')

    folder_ids = _collect_folder_ids(folder_id)
    items = FilesItem.query.filter(FilesItem.folder_id.in_(folder_ids)).all()
    drive_file_ids = [i.drive_file_id for i in items if i.drive_file_id]
    # Parent-first; Drive helper reverses to deepest-first
    drive_folder_ids = []
    for fid in folder_ids:
        f = db.session.get(FilesFolder, fid)
        if f and f.drive_folder_id:
            drive_folder_ids.append(f.drive_folder_id)

    # Remove Drive copies first (before local rows disappear)
    drive_stats = {'drive_deleted': [], 'drive_failed': []}
    if drive_file_ids or drive_folder_ids:
        try:
            from module_files import drive_service as _drive
            drive_stats = _drive.delete_on_drive_ids(
                file_ids=drive_file_ids,
                folder_ids=drive_folder_ids,
            ) or drive_stats
        except Exception:
            logger.exception('Drive delete during folder delete failed for %s', folder_id)

    # Remove local files
    for item in items:
        try:
            path = resolve_item_abs_path(item)
            if os.path.isfile(path):
                os.remove(path)
        except (FileNotFoundError, OSError):
            pass

    for item in items:
        db.session.delete(item)

    for fid in reversed(folder_ids):
        f = db.session.get(FilesFolder, fid)
        if f:
            db.session.delete(f)
    db.session.commit()

    return {
        'id': folder_id,
        'deleted_folder_ids': folder_ids,
        'drive_file_ids': drive_file_ids,
        'drive_folder_ids': drive_folder_ids,
        'drive_stats': drive_stats,
    }


def save_upload(
    *,
    folder_id: int,
    file_storage,
    created_by: Optional[int],
) -> FilesItem:
    folder = db.session.get(FilesFolder, folder_id)
    if not folder:
        raise ValueError('Folder not found')
    raw_name = file_storage.filename or 'upload.bin'
    filename = secure_filename(raw_name) or 'upload.bin'
    data = file_storage.read()
    if not data:
        raise ValueError('Empty file')
    mime = file_storage.mimetype or 'application/octet-stream'
    return save_bytes_to_folder(
        folder=folder,
        data=data,
        display_name=filename,
        filename=filename,
        mime_type=mime,
        source_module='upload',
        source_kind='upload',
        created_by=created_by,
    )


def _build_manpower_bytes(kind: str) -> Tuple[bytes, str, str]:
    from module_hr.manpower_excel import (
        build_manpower_export_bytes,
        build_manpower_template_bytes,
    )

    stamp = datetime.utcnow().strftime('%Y%m%d_%H%M')
    if kind == 'template':
        data = build_manpower_template_bytes()
        filename = f'manpower_template_{stamp}.xlsx'
        display = f'Manpower template ({stamp})'
    elif kind == 'export':
        data = build_manpower_export_bytes()
        filename = f'manpower_export_{stamp}.xlsx'
        display = f'Manpower export ({stamp})'
    else:
        raise ValueError('Invalid kind for manpower')
    return data, filename, display


def _build_leave_bytes(kind: str) -> Tuple[bytes, str, str]:
    from app.models import LEAVE_TRACKER_YEAR
    from module_hr.leave_excel import (
        build_leave_log_template_bytes,
        build_leave_workbook,
    )

    stamp = datetime.utcnow().strftime('%Y%m%d_%H%M')
    if kind == 'template':
        buf = build_leave_log_template_bytes()
        data = buf.getvalue() if isinstance(buf, BytesIO) else bytes(buf)
        filename = f'leave_log_template_{LEAVE_TRACKER_YEAR}_{stamp}.xlsx'
        display = f'Leave log template ({stamp})'
    elif kind == 'export':
        from module_hr.leave_tracker import LEAVE_WINDOW_END, LEAVE_WINDOW_START

        employees = (
            LeaveEmployee.query.filter_by(active=True)
            .options(joinedload(LeaveEmployee.usage))
            .order_by(LeaveEmployee.company.asc(), LeaveEmployee.full_name.asc())
            .all()
        )
        plans = (
            LeavePlan.query.options(joinedload(LeavePlan.employee))
            .filter(
                LeavePlan.start_date <= LEAVE_WINDOW_END,
                LeavePlan.end_date >= LEAVE_WINDOW_START,
            )
            .order_by(LeavePlan.start_date.asc())
            .all()
        )
        logs = (
            LeaveLog.query.options(joinedload(LeaveLog.employee))
            .filter(
                LeaveLog.leave_date >= LEAVE_WINDOW_START,
                LeaveLog.leave_date <= LEAVE_WINDOW_END,
            )
            .order_by(LeaveLog.leave_date.asc(), LeaveLog.id.asc())
            .all()
        )
        buf = build_leave_workbook(employees, plans, logs)
        data = buf.getvalue() if isinstance(buf, BytesIO) else bytes(buf)
        filename = f'leave_tracker_{LEAVE_TRACKER_YEAR}_{stamp}.xlsx'
        display = f'Leave export ({stamp})'
    else:
        raise ValueError('Invalid kind for leave')
    return data, filename, display


def _build_hiring_bytes(kind: str) -> Tuple[bytes, str, str]:
    from app.models import HiringCandidate
    from module_hr.hiring_excel import build_hiring_template_bytes

    stamp = datetime.utcnow().strftime('%Y%m%d_%H%M')
    if kind == 'template':
        data = build_hiring_template_bytes()
        filename = f'hiring_tracker_template_{stamp}.xlsx'
        display = f'Hiring template ({stamp})'
    elif kind == 'export':
        candidates = HiringCandidate.query.order_by(HiringCandidate.updated_at.desc()).all()
        data = build_hiring_template_bytes(candidates=candidates)
        filename = f'hiring_tracker_export_{stamp}.xlsx'
        display = f'Hiring export ({stamp})'
    else:
        raise ValueError('Invalid kind for hiring')
    return data, filename, display


def _build_procurement_bytes(kind: str) -> Tuple[bytes, str, str]:
    import pandas as pd
    from app.models import Submission

    stamp = datetime.utcnow().strftime('%Y%m%d_%H%M')
    if kind == 'template':
        from module_procurement.excel_template import build_procurement_sample_bytes

        return (
            build_procurement_sample_bytes(),
            f'procurement_import_sample_{stamp}.xlsx',
            f'Procurement sample ({stamp})',
        )
    if kind == 'export':
        submissions = (
            Submission.query.filter(Submission.module_type == 'procurement_material')
            .order_by(Submission.created_at.desc())
            .all()
        )
        data_rows = []
        for sub in submissions:
            if sub.form_data:
                data_rows.append({
                    'ID': sub.submission_id,
                    'Material Name': sub.form_data.get('material_name', ''),
                    'Property': sub.form_data.get('property', 'Unassigned'),
                    'Category': sub.form_data.get('category', ''),
                    'Description': sub.form_data.get('description', ''),
                    'Unit': sub.form_data.get('unit', ''),
                    'Quantity': sub.form_data.get('quantity', 0),
                    'Unit Price (AED)': sub.form_data.get('unit_price', 0),
                    'Total Price (AED)': sub.form_data.get('total_price', 0),
                    'Supplier': sub.form_data.get('supplier', ''),
                    'Notes': sub.form_data.get('notes', ''),
                    'Added By': sub.form_data.get('added_by', ''),
                    'Date Added': sub.created_at.strftime('%Y-%m-%d') if sub.created_at else '',
                })
        df = pd.DataFrame(data_rows)
        filename = f'procurement_materials_{stamp}.xlsx'
        display = f'Procurement export ({stamp})'
    else:
        raise ValueError('Invalid kind for procurement')

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Materials')
    return output.getvalue(), filename, display


def _build_qhsi_bytes(kind: str) -> Tuple[bytes, str, str]:
    from module_qhsi.excel_import import build_import_template_bytes

    stamp = datetime.utcnow().strftime('%Y%m%d_%H%M')
    if kind == 'template':
        data = build_import_template_bytes()
        if isinstance(data, BytesIO):
            data = data.getvalue()
        filename = f'qhsi_staff_compliance_template_{stamp}.xlsx'
        display = f'QHSE staff template ({stamp})'
        return data, filename, display
    if kind != 'export':
        raise ValueError('Invalid kind for qhsi')

    import pandas as pd
    from app.models import Submission

    subs = (
        Submission.query.filter(Submission.module_type == 'qhsi_staff_compliance')
        .order_by(Submission.created_at.desc())
        .all()
    )
    columns = [
        'Employee Name', 'Employee ID', 'Project', 'Record Date',
        'Department', 'Supervisor', 'Item', 'Condition', 'Comments',
    ]
    rows = []
    for sub in subs:
        fd = sub.form_data or {}
        kit = fd.get('kit_items') or []
        base = {
            'Employee Name': fd.get('employee_name') or '',
            'Employee ID': fd.get('employee_id') or '',
            'Project': fd.get('project_name') or sub.site_name or '',
            'Record Date': fd.get('record_date') or '',
            'Department': fd.get('department') or '',
            'Supervisor': fd.get('supervisor_name') or '',
        }
        if not kit:
            rows.append({**base, 'Item': '', 'Condition': '', 'Comments': fd.get('notes') or ''})
            continue
        for item in kit:
            if not isinstance(item, dict):
                continue
            rows.append({
                **base,
                'Item': item.get('type') or item.get('item') or item.get('name') or '',
                'Condition': item.get('condition') or '',
                'Comments': item.get('comments') or '',
            })
    df = pd.DataFrame(rows, columns=columns)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Staff Compliance')
    filename = f'qhsi_staff_compliance_export_{stamp}.xlsx'
    display = f'QHSE staff export ({stamp})'
    return output.getvalue(), filename, display


def _build_mmr_bytes(kind: str) -> Tuple[bytes, str, str]:
    import os
    from flask import current_app

    if kind != 'export':
        raise ValueError('Invalid kind for mmr')
    gen = current_app.config.get('GENERATED_DIR') or ''
    path = os.path.join(gen, 'mmr_latest.xlsx')
    if not os.path.isfile(path):
        raise ValueError('No MMR file uploaded yet. Upload a CAFM Excel in Report Generation first.')
    from module_mmr.mmr_service import generate_report_excel, parse_excel

    stamp = datetime.utcnow().strftime('%Y%m%d_%H%M')
    df = parse_excel(path)
    data = generate_report_excel(df)
    filename = f'mmr_report_{stamp}.xlsx'
    display = f'MMR report ({stamp})'
    return data, filename, display


def _build_devices_bytes(kind: str) -> Tuple[bytes, str, str]:
    import pandas as pd

    stamp = datetime.utcnow().strftime('%Y%m%d_%H%M')
    if kind == 'template':
        from app.admin.excel_templates import build_devices_sample_bytes

        return (
            build_devices_sample_bytes(),
            f'device_import_sample_{stamp}.xlsx',
            f'Device sample ({stamp})',
        )
    if kind == 'export':
        from app.models import Device

        devices = Device.query.order_by(Device.name.asc()).all()
        rows = []
        for d in devices:
            email = ''
            if d.assigned_user and d.assigned_user.email:
                email = d.assigned_user.email
            rows.append({
                'Device ID': d.device_id or '',
                'Device Name': d.name or '',
                'Device Type': d.device_type or '',
                'OS': d.os or '',
                'Status': d.status or '',
                'Health': d.health if d.health is not None else '',
                'Assigned User Email': email,
                'Serial / Asset Tag': d.serial_or_asset_tag or '',
            })
        df = pd.DataFrame(rows, columns=[
            'Device ID', 'Device Name', 'Device Type', 'OS', 'Status',
            'Health', 'Assigned User Email', 'Serial / Asset Tag',
        ])
        filename = f'devices_export_{stamp}.xlsx'
        display = f'Devices export ({stamp})'
    else:
        raise ValueError('Invalid kind for devices')
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Devices')
    return output.getvalue(), filename, display


def _build_dochub_bytes(kind: str) -> Tuple[bytes, str, str]:
    import pandas as pd
    from sqlalchemy import or_

    from app.models import DocHubDocument

    if kind != 'export':
        raise ValueError('Invalid kind for dochub')
    stamp = datetime.utcnow().strftime('%Y%m%d_%H%M')
    docs = (
        DocHubDocument.query.filter(
            or_(DocHubDocument.inline_asset.is_(False), DocHubDocument.inline_asset.is_(None))
        )
        .order_by(DocHubDocument.updated_at.desc())
        .all()
    )
    columns = [
        'Title', 'Category', 'Status', 'Type', 'File type', 'Author',
        'Starred', 'Updated', 'Created', 'Size (bytes)',
    ]
    rows = []
    for d in docs:
        author = ''
        if d.author:
            author = d.author.full_name or d.author.username or ''
        rows.append({
            'Title': d.title or '',
            'Category': d.category or '',
            'Status': d.status or '',
            'Type': d.doc_type or '',
            'File type': d.file_type or '',
            'Author': author,
            'Starred': 'Yes' if d.is_starred else 'No',
            'Updated': d.updated_at.strftime('%Y-%m-%d %H:%M') if d.updated_at else '',
            'Created': d.created_at.strftime('%Y-%m-%d %H:%M') if d.created_at else '',
            'Size (bytes)': int(d.size_bytes or 0),
        })
    df = pd.DataFrame(rows, columns=columns)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Documents')
    filename = f'dochub_library_{stamp}.xlsx'
    display = f'DocHub library ({stamp})'
    return output.getvalue(), filename, display


def _is_remote_url(path: str) -> bool:
    return bool(path) and (path.startswith('http://') or path.startswith('https://'))


def _read_dochub_document(doc_id: int) -> Tuple[bytes, str, str, str]:
    """Return (bytes, filename, display_name, mime) for one DocHub document."""
    import mimetypes
    import urllib.request

    from app.models import DocHubDocument

    doc = DocHubDocument.query.get(doc_id)
    if not doc or bool(getattr(doc, 'inline_asset', False)):
        raise ValueError('Document not found')

    title = (doc.title or f'Document {doc.id}').strip()
    if (doc.doc_type or 'content') == 'content':
        html = doc.content or ''
        safe = secure_filename(title) or f'document_{doc.id}'
        filename = f'{safe}.html'
        data = (
            f'<!DOCTYPE html><html><head><meta charset="utf-8"><title>{title}</title></head>'
            f'<body>{html}</body></html>'
        ).encode('utf-8')
        return data, filename, title, 'text/html; charset=utf-8'

    filename = (doc.filename or '').strip() or f'document_{doc.id}'
    path = (doc.stored_path or '').strip()
    data = b''
    if _is_remote_url(path):
        req = urllib.request.Request(path, headers={'User-Agent': 'Injaaz-Files/1.0'})
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
    else:
        candidates = [path]
        gen = current_app.config.get('GENERATED_DIR') or ''
        if path and gen and not os.path.isabs(path):
            candidates.append(os.path.join(gen, path))
        for candidate in candidates:
            if candidate and os.path.isfile(candidate):
                with open(candidate, 'rb') as fh:
                    data = fh.read()
                break
        if not data:
            raise ValueError(f'File for “{title}” is missing on disk')

    mime = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
    return data, filename, title, mime


def _build_locations_bytes(kind: str) -> Tuple[bytes, str, str]:
    from module_ticketing.location_excel import build_location_workbook

    if kind not in ('locations', 'template'):
        raise ValueError('Invalid kind for ticketing locations')
    stamp = datetime.utcnow().strftime('%Y%m%d_%H%M')
    buf = build_location_workbook()
    data = buf.getvalue() if isinstance(buf, BytesIO) else bytes(buf)
    filename = f'location_template_{stamp}.xlsx'
    display = f'Location template ({stamp})'
    return data, filename, display


def _build_technicians_bytes(kind: str) -> Tuple[bytes, str, str]:
    if kind == 'export':
        return _build_technicians_export_bytes()
    if kind != 'template':
        raise ValueError('Invalid kind for technicians')
    from app.admin.excel_templates import build_technicians_template_bytes

    stamp = datetime.utcnow().strftime('%Y%m%d_%H%M')
    return (
        build_technicians_template_bytes(),
        f'technicians_import_template_{stamp}.xlsx',
        f'Technicians template ({stamp})',
    )


def _build_technicians_export_bytes() -> Tuple[bytes, str, str]:
    import pandas as pd

    from app.models import Technician

    stamp = datetime.utcnow().strftime('%Y%m%d_%H%M')
    techs = Technician.query.order_by(Technician.full_name.asc()).all()
    rows = []
    for t in techs:
        rows.append({
            'Employee ID': t.employee_id or '',
            'Full Name': t.full_name or '',
            'Designation': t.designation or '',
            'Department': t.department or '',
            'Specialization': t.specialization or '',
            'Phone': t.phone or '',
            'Email': t.email or '',
            'Salary': t.salary if t.salary is not None else '',
            'Joining Date': t.joining_date.isoformat() if t.joining_date else '',
            'Status': t.status or '',
            'Supervisor User ID': t.supervisor_user_id if t.supervisor_user_id is not None else '',
            'Notes': t.notes or '',
        })
    df = pd.DataFrame(rows, columns=[
        'Employee ID', 'Full Name', 'Designation', 'Department',
        'Specialization', 'Phone', 'Email', 'Salary', 'Joining Date',
        'Status', 'Supervisor User ID', 'Notes',
    ])
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Technicians')
    filename = f'technicians_export_{stamp}.xlsx'
    display = f'Technicians export ({stamp})'
    return output.getvalue(), filename, display


def _parse_ticket_kind(kind: str) -> Tuple[int, str]:
    parts = (kind or '').split(':')
    if len(parts) != 3 or parts[0] != 'ticket' or parts[2] not in ('report', 'invoice'):
        raise ValueError('Invalid ticket save kind')
    try:
        return int(parts[1]), parts[2]
    except (TypeError, ValueError):
        raise ValueError('Invalid ticket id') from None


def _build_closed_ticket_pdf(kind: str, created_by: Optional[int]) -> Tuple[bytes, str, str]:
    """Regenerate a closed work order service report or invoice PDF."""
    from app.models import Ticket, TicketNote, User
    from module_ticketing.routes import _can_user_view_ticket

    ticket_pk, artifact = _parse_ticket_kind(kind)
    ticket = db.session.get(Ticket, ticket_pk)
    if not ticket:
        raise ValueError('Ticket not found')
    if (ticket.status or '') != 'closed':
        raise ValueError('Only closed work orders can be saved')
    user = db.session.get(User, created_by) if created_by else None
    if user is not None and not _can_user_view_ticket(user, ticket):
        raise ValueError('You cannot save this work order')

    materials = ticket.materials.all()
    manpower_entries = ticket.manpower.all()
    buf = BytesIO()
    code = ticket.ticket_id or f'ticket-{ticket.id}'

    if artifact == 'report':
        from module_ticketing.ticket_pdf_builder import build_ticket_pdf
        from module_ticketing.routes import _ticket_location_map_payload
        notes = ticket.notes.order_by(TicketNote.created_at.asc()).all()
        images = ticket.images.all()
        build_ticket_pdf(
            ticket, notes, images, materials, manpower_entries, buf,
            location_map=_ticket_location_map_payload(ticket),
        )
        filename = f'{code}_report.pdf'
        display = f'{code} — Service report'
    else:
        if ticket.selling_price is None:
            from module_ticketing.routes import _recalc_total_cost
            _recalc_total_cost(ticket)
            db.session.commit()
        from module_ticketing.ticket_invoice_builder import build_invoice_pdf
        build_invoice_pdf(ticket, materials, manpower_entries, buf)
        filename = f'{code}_invoice.pdf'
        display = f'{code} — Invoice'

    return buf.getvalue(), filename, display


def save_from_module(module: str, kind: str, created_by: Optional[int]) -> Tuple[FilesItem, str]:
    """Build Excel via existing helpers and store in Files. Returns (item, folder_label)."""
    mod = (module or '').strip().lower()
    kind = (kind or '').strip().lower()
    catalog = get_module_catalog(mod)
    if not catalog:
        raise ValueError(f'Unsupported module: {module}')

    # DocHub: copy a specific library document into Files
    if mod == 'dochub' and kind.startswith('doc:'):
        try:
            doc_id = int(kind.split(':', 1)[1])
        except (TypeError, ValueError):
            raise ValueError('Invalid DocHub document id') from None
        data, filename, display, mime = _read_dochub_document(doc_id)
        folder = get_folder_by_path_key(catalog['folder_path_key'], created_by=created_by)
        item = save_bytes_to_folder(
            folder=folder,
            data=data,
            display_name=display,
            filename=filename,
            mime_type=mime,
            source_module=mod,
            source_kind=kind,
            created_by=created_by,
        )
        return item, catalog.get('folder_label') or folder.name

    # Service Tickets: regenerate closed-ticket PDFs into Files
    if mod == 'ticketing' and kind.startswith('ticket:'):
        data, filename, display = _build_closed_ticket_pdf(kind, created_by)
        folder = get_folder_by_path_key(catalog['folder_path_key'], created_by=created_by)
        item = save_bytes_to_folder(
            folder=folder,
            data=data,
            display_name=display,
            filename=filename,
            mime_type=PDF_MIME,
            source_module=mod,
            source_kind=kind,
            created_by=created_by,
        )
        return item, catalog.get('folder_label') or folder.name

    # Ticketing location hierarchy blank template
    if mod == 'ticketing' and kind == 'locations':
        data, filename, display = _build_locations_bytes('locations')
        folder = get_folder_by_path_key(catalog['folder_path_key'], created_by=created_by)
        item = save_bytes_to_folder(
            folder=folder,
            data=data,
            display_name=display,
            filename=filename,
            mime_type=XLSX_MIME,
            source_module=mod,
            source_kind=kind,
            created_by=created_by,
        )
        return item, catalog.get('folder_label') or folder.name

    kinds = {o['kind'] for o in catalog['options']}
    if kind not in kinds:
        raise ValueError(f'Unsupported kind for {mod}: {kind}')

    builders = {
        'manpower': _build_manpower_bytes,
        'leave': _build_leave_bytes,
        'hiring': _build_hiring_bytes,
        'procurement': _build_procurement_bytes,
        'qhsi': _build_qhsi_bytes,
        'mmr': _build_mmr_bytes,
        'devices': _build_devices_bytes,
        'technicians': _build_technicians_bytes,
        'dochub': _build_dochub_bytes,
        'ticketing': _build_locations_bytes,
    }
    builder = builders.get(mod)
    if not builder:
        raise ValueError(f'Unsupported module: {module}')
    data, filename, display = builder(kind)

    folder = get_folder_by_path_key(catalog['folder_path_key'], created_by=created_by)
    item = save_bytes_to_folder(
        folder=folder,
        data=data,
        display_name=display,
        filename=filename,
        mime_type=XLSX_MIME,
        source_module=mod,
        source_kind=kind,
        created_by=created_by,
    )
    folder_label = catalog.get('folder_label') or folder.name
    return item, folder_label


def save_from_module_many(module: str, kinds: list, created_by: Optional[int]) -> dict:
    """Save each kind independently. One failure does not block the rest."""
    seen = set()
    items = []
    failed = []
    folder_label = ''
    catalog = get_module_catalog((module or '').strip().lower())
    if catalog:
        folder_label = catalog.get('folder_label') or ''
    for raw in kinds or []:
        kind = str(raw or '').strip().lower()
        if not kind or kind in seen:
            continue
        seen.add(kind)
        try:
            item, folder_label = save_from_module(module, kind, created_by=created_by)
            items.append(item)
        except Exception as exc:
            logger.exception('save-from-module kind=%s failed', kind)
            failed.append({'kind': kind, 'error': str(exc)})
    return {
        'items': items,
        'saved': len(items),
        'failed': failed,
        'folder_label': folder_label,
    }


def count_unsynced_items() -> int:
    """Files that exist locally but are not synced to Drive (local or error)."""
    return (
        FilesItem.query.filter(FilesItem.sync_status.in_(['local', 'error']))
        .count()
    )


def build_excel_template_bytes(template_id: str) -> Tuple[bytes, str, str]:
    """Generate a library template with a stable download filename.

    Returns (data, stable_filename, display_name).
    """
    entry = get_excel_template(template_id)
    if not entry:
        raise ValueError(f'Unknown template: {template_id}')

    mod = entry['module']
    kind = entry['kind']
    stable = entry['filename']
    display = entry['label']

    builders = {
        'manpower': _build_manpower_bytes,
        'leave': _build_leave_bytes,
        'hiring': _build_hiring_bytes,
        'procurement': _build_procurement_bytes,
        'qhsi': _build_qhsi_bytes,
        'devices': _build_devices_bytes,
        'technicians': _build_technicians_bytes,
        'ticketing': _build_locations_bytes,
    }
    builder = builders.get(mod)
    if not builder:
        raise ValueError(f'No builder for module: {mod}')
    data, _ts_name, _ts_display = builder(kind)
    return data, stable, display


def upsert_bytes_to_folder(
    *,
    folder: FilesFolder,
    data: bytes,
    display_name: str,
    filename: str,
    mime_type: str,
    source_module: Optional[str],
    source_kind: Optional[str],
    created_by: Optional[int],
) -> FilesItem:
    """Save bytes; if a file with the same filename already exists in the folder, replace it."""
    existing = (
        FilesItem.query.filter_by(folder_id=folder.id, filename=filename)
        .order_by(FilesItem.id.desc())
        .first()
    )
    if existing:
        # Replace disk bytes and reset sync so Drive push updates the same logical file
        try:
            old_path = resolve_item_abs_path(existing)
            if os.path.isfile(old_path):
                os.remove(old_path)
        except FileNotFoundError:
            pass
        except OSError:
            logger.warning('Could not remove old template file for %s', filename, exc_info=True)

        folder_dir = os.path.join(_files_root(), str(folder.id))
        os.makedirs(folder_dir, exist_ok=True)
        store_name = _safe_store_name(filename)
        abs_path = os.path.join(folder_dir, store_name)
        with open(abs_path, 'wb') as fh:
            fh.write(data)

        gen = current_app.config.get('GENERATED_DIR') or ''
        stored = abs_path
        if gen and abs_path.startswith(gen):
            stored = os.path.relpath(abs_path, gen)

        now = utc_now_naive()
        existing.name = display_name
        existing.filename = filename
        existing.mime_type = mime_type
        existing.size_bytes = len(data)
        existing.stored_path = stored
        existing.source_module = source_module
        existing.source_kind = source_kind
        existing.sync_status = 'local'
        existing.sync_error = None
        # Keep drive_file_id so sync_item can update the same Drive file if present
        existing.updated_at = now
        if created_by is not None:
            existing.created_by = created_by
        db.session.commit()
        return existing

    return save_bytes_to_folder(
        folder=folder,
        data=data,
        display_name=display_name,
        filename=filename,
        mime_type=mime_type,
        source_module=source_module,
        source_kind=source_kind,
        created_by=created_by,
    )


def push_excel_templates_to_drive(template_ids: list, created_by: Optional[int], user=None) -> dict:
    """Generate templates with stable names, upsert into module folders, sync each to Drive."""
    from module_files import drive_service

    if not template_ids:
        raise ValueError('Select at least one template')

    seen = set()
    items = []
    failed = []
    synced = []

    for raw in template_ids:
        tid = str(raw or '').strip().lower()
        if not tid or tid in seen:
            continue
        seen.add(tid)
        entry = get_excel_template(tid)
        if not entry:
            failed.append({'id': tid, 'error': 'Unknown template'})
            continue
        if user is not None and not user_can_see_excel_template(user, entry):
            failed.append({'id': tid, 'error': 'Access denied'})
            continue
        try:
            data, filename, display = build_excel_template_bytes(tid)
            catalog = get_module_catalog(entry['module'])
            if not catalog:
                raise ValueError(f'No folder catalog for {entry["module"]}')
            folder = get_folder_by_path_key(catalog['folder_path_key'], created_by=created_by)
            item = upsert_bytes_to_folder(
                folder=folder,
                data=data,
                display_name=display,
                filename=filename,
                mime_type=XLSX_MIME,
                source_module=entry['module'],
                source_kind=entry['kind'],
                created_by=created_by,
            )
            items.append(item)
            try:
                drive_service.sync_item(item.id)
                synced.append(item.id)
            except Exception as sync_exc:
                logger.exception('push template sync failed id=%s', tid)
                failed.append({'id': tid, 'error': f'Saved locally but Drive sync failed: {sync_exc}'})
        except Exception as exc:
            logger.exception('push template failed id=%s', tid)
            failed.append({'id': tid, 'error': str(exc)})

    return {
        'items': items,
        'saved': len(items),
        'synced': synced,
        'failed': failed,
    }


def build_templates_zip(template_ids: list, user=None) -> Tuple[bytes, str]:
    """Zip one or more Excel templates. Empty ids = all allowed for user."""
    import zipfile

    from module_files.catalog import EXCEL_TEMPLATES

    if user is not None:
        allowed = list_excel_templates_for_user(user)
    else:
        allowed = [{'id': e['id']} for e in EXCEL_TEMPLATES]
    allowed_ids = {t['id'] for t in allowed}
    ids = [str(x or '').strip().lower() for x in (template_ids or []) if str(x or '').strip()]
    if not ids:
        ids = [e['id'] for e in EXCEL_TEMPLATES if e['id'] in allowed_ids]
    else:
        ids = [i for i in ids if i in allowed_ids]
    if not ids:
        raise ValueError('No templates to download')

    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        used_names = set()
        for tid in ids:
            data, filename, _display = build_excel_template_bytes(tid)
            name = filename
            if name in used_names:
                stem, ext = os.path.splitext(filename)
                name = f'{stem}_{tid}{ext}'
            used_names.add(name)
            zf.writestr(name, data)
    stamp = datetime.utcnow().strftime('%Y%m%d')
    return buf.getvalue(), f'excel_templates_{stamp}.zip'
