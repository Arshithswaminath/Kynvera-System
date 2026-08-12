"""
Hiring Document Tracker — Excel template, export, and status import.
"""
from __future__ import annotations

import logging
import re
from io import BytesIO, StringIO
from typing import Any, Optional

from app.models import (
    HIRING_DOC_LABELS,
    HIRING_DOC_TYPES,
    HIRING_PIPELINE_DEFAULT,
    HIRING_PIPELINE_LABELS,
    HIRING_PIPELINE_STATUSES,
    HIRING_PIPELINE_STEPS,
    HiringCandidate,
    HiringDocument,
    db,
)
from common.datetime_utils import utc_now_naive

logger = logging.getLogger(__name__)

# Short column headers for the wide template (readable + fit dropdowns)
DOC_COLUMN_HEADERS = {
    'passport': 'Passport',
    'emirates_id': 'Emirates ID',
    'photograph': 'Photograph',
    'pcc': 'PCC',
    'education_certificate': 'Education Certificate',
    'offer_letter': 'Offer Letter',
    'insurance': 'Insurance',
    'e_visa': 'E-Visa',
    'contract': 'Contract',
}

PROFILE_HEADERS = (
    'Candidate ID',
    'Full Name',
    'Role',
    'Department',
    'Phone',
    'Email',
    'Replacement Name',
    'Replacement Employee ID',
    'Pipeline Status',
    'Vacancy ID',
)

STATUS_HEADERS = tuple(DOC_COLUMN_HEADERS[dt] for dt in HIRING_DOC_TYPES)
ALL_HEADERS = PROFILE_HEADERS + STATUS_HEADERS + ('Comments',)

DOC_STATUS_TICK = '✓'
DOC_STATUS_CROSS = '✗'
DOC_STATUS_LABELS = (DOC_STATUS_CROSS, DOC_STATUS_TICK)
DOC_STATUS_KEYS = frozenset({'missing', 'uploaded', 'attested', 'verified'})

# Symbols / glyphs Excel may store for tick / cross
_TICK_GLYPHS = frozenset({
    '✓', '✔', '√', '☑', '✅', '☑️',
})
_CROSS_GLYPHS = frozenset({
    '✗', '✘', '✕', '×', '❌', '☒',
})

FIELD_ALIASES = {
    'candidate_id': ('candidate id', 'id', 'hiring id', 'candidate'),
    'full_name': ('full name', 'name', 'candidate name'),
    'role': ('role', 'position', 'job title', 'role position'),
    'department': ('department', 'dept'),
    'phone': ('phone', 'mobile', 'telephone', 'contact'),
    'email': ('email', 'e mail', 'email address'),
    'replacement_name': ('replacement name', 'replacing', 'replacement'),
    'replacement_employee_id': (
        'replacement employee id', 'replacement emp id', 'replacement id',
        'replacing employee id',
    ),
    'pipeline_status': ('pipeline status', 'pipeline', 'stage', 'hiring stage'),
    'vacancy_id': ('vacancy id', 'manpower vacancy id', 'vacancy', 'project vacancy id'),
    'comments': ('comments', 'comment', 'notes', 'remarks'),
}

DOC_ALIASES = {
    'passport': ('passport', 'passport copy'),
    'emirates_id': ('emirates id', 'emirates id copy', 'eid'),
    'photograph': ('photograph', 'photo', 'photograph white background'),
    'pcc': ('pcc', 'pcc attested', 'police clearance'),
    'education_certificate': ('education certificate', 'education', 'certificate'),
    'offer_letter': ('offer letter', 'offer'),
    'insurance': ('insurance', 'insurance paper'),
    'e_visa': ('e visa', 'evisa', 'visa'),
    'contract': ('contract', 'employment contract'),
}


def normalize_column_name(value) -> str:
    raw = str(value or '').strip().lower()
    cleaned = ''.join(ch if ch.isalnum() else ' ' for ch in raw)
    return ' '.join(cleaned.split())


def _cell_str(value) -> str:
    if value is None:
        return ''
    if isinstance(value, float) and str(value) == 'nan':
        return ''
    s = str(value).strip()
    if s.lower() in ('nan', 'nat', 'none', '-'):
        return ''
    # pandas may give "12.0" for integer IDs
    if re.fullmatch(r'\d+\.0', s):
        return s[:-2]
    return s


def _build_header_map(columns) -> dict:
    """Map normalized header → canonical field or doc_type key."""
    alias_lookup = {}
    for field, aliases in FIELD_ALIASES.items():
        for a in aliases:
            alias_lookup[a] = ('field', field)
    for doc_type, aliases in DOC_ALIASES.items():
        for a in aliases:
            alias_lookup[a] = ('doc', doc_type)
        alias_lookup[normalize_column_name(DOC_COLUMN_HEADERS[doc_type])] = ('doc', doc_type)
        alias_lookup[normalize_column_name(HIRING_DOC_LABELS.get(doc_type, doc_type))] = ('doc', doc_type)

    mapping = {}
    for col in columns:
        n = normalize_column_name(col)
        if not n:
            continue
        if n in alias_lookup:
            mapping[n] = alias_lookup[n]
            continue
        # fuzzy: exact key match
        for field, aliases in FIELD_ALIASES.items():
            if n == field.replace('_', ' ') or n in aliases:
                mapping[n] = ('field', field)
                break
    return mapping


def _normalize_doc_status(raw: str, doc_type: str) -> tuple[Optional[str], Optional[str]]:
    """Return (status_key, error). Blank → (None, None) meaning leave unchanged."""
    raw_s = _cell_str(raw)
    if not raw_s:
        return None, None

    # Tick / cross symbols (normalize_column_name would strip these)
    if raw_s in _TICK_GLYPHS or raw_s.lower() in ('tick', 'check', 'checked', 'yes', 'y'):
        status = 'attested' if doc_type == 'pcc' else 'uploaded'
        return status, None
    if raw_s in _CROSS_GLYPHS or raw_s.lower() in ('cross', 'unchecked', 'no', 'n'):
        return 'missing', None

    s = normalize_column_name(raw_s)
    if not s:
        return None, f'Invalid status "{raw}" for {DOC_COLUMN_HEADERS.get(doc_type, doc_type)}'

    aliases = {
        'missing': 'missing',
        'not started': 'missing',
        'none': 'missing',
        'n a': 'missing',
        'na': 'missing',
        'uploaded': 'uploaded',
        'upload': 'uploaded',
        'received': 'uploaded',
        'done': 'uploaded',
        'complete': 'uploaded',
        'completed': 'uploaded',
        'attested': 'attested',
        'attest': 'attested',
        'verified': 'verified',
        'verify': 'verified',
    }
    status = aliases.get(s)
    if not status:
        return None, f'Invalid status "{raw}" for {DOC_COLUMN_HEADERS.get(doc_type, doc_type)}'

    if status == 'attested' and doc_type != 'pcc':
        # Attested only applies to PCC; treat as uploaded for other docs
        status = 'uploaded'
    return status, None


def _normalize_pipeline(raw: str) -> tuple[Optional[str], Optional[str]]:
    s = _cell_str(raw)
    if not s:
        return None, None
    key = s.strip().lower().replace(' ', '_').replace('-', '_')
    if key in ('onhold',):
        key = 'on_hold'
    if key in ('candidateemployee', 'candidate_as_employee', 'file_closed', 'fileclosed', 'closed'):
        key = 'candidate_employee'
    if key in HIRING_PIPELINE_STATUSES:
        return key, None
    label_map = {normalize_column_name(v): k for k, v in HIRING_PIPELINE_LABELS.items()}
    n = normalize_column_name(s)
    if n in label_map:
        return label_map[n], None
    # partial label match
    for k, label in HIRING_PIPELINE_LABELS.items():
        if normalize_column_name(label) == n or n in normalize_column_name(label):
            return k, None
    return None, f'Invalid pipeline status "{raw}"'


def _status_label(status: Optional[str], has_file: bool = False) -> str:
    """Excel display: ✓ = submitted, ✗ = missing."""
    if not status or status == 'missing':
        return DOC_STATUS_CROSS
    if status in ('uploaded', 'attested', 'verified'):
        return DOC_STATUS_TICK
    return DOC_STATUS_CROSS


def _pipeline_label(key: Optional[str]) -> str:
    k = key or HIRING_PIPELINE_DEFAULT
    return HIRING_PIPELINE_LABELS.get(k, k)


def build_hiring_template_bytes(candidates: Optional[list] = None) -> bytes:
    """Blank template (with example row) or prefilled export of candidates."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    ws = wb.active
    ws.title = 'Candidates'

    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill('solid', fgColor='125435')
    example_fill = PatternFill('solid', fgColor='F3F4F6')

    for col_idx, header in enumerate(ALL_HEADERS, start=1):
        cell = ws.cell(1, col_idx, header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(wrap_text=True, vertical='center')

    ws.freeze_panes = 'A2'
    ws.row_dimensions[1].height = 32

    widths = {
        'A': 12, 'B': 22, 'C': 18, 'D': 14, 'E': 14, 'F': 24,
        'G': 18, 'H': 18, 'I': 28, 'J': 12, 'K': 12, 'L': 12,
        'M': 12, 'N': 12, 'O': 18, 'P': 12, 'Q': 12, 'R': 12, 'S': 12, 'T': 28,
    }
    for col, width in widths.items():
        ws.column_dimensions[col].width = width

    if candidates:
        for row_idx, cand in enumerate(candidates, start=2):
            by_type = {d.doc_type: d for d in (cand.documents or [])}
            values = [
                cand.id,
                cand.full_name or '',
                cand.role or '',
                cand.department or '',
                cand.phone or '',
                cand.email or '',
                cand.replacement_name or '',
                cand.replacement_employee_id or '',
                _pipeline_label(cand.normalized_pipeline_status()),
                getattr(cand, 'assigned_vacancy', None).id if getattr(cand, 'assigned_vacancy', None) else '',
            ]
            for dt in HIRING_DOC_TYPES:
                doc = by_type.get(dt)
                if doc:
                    values.append(_status_label(doc.status, has_file=doc.has_file()))
                else:
                    values.append(_status_label('missing'))
            values.append(cand.comments or '')
            for col_idx, val in enumerate(values, start=1):
                cell = ws.cell(row_idx, col_idx, val)
                # Center tick/cross in document columns (K–S = 11–19 after Vacancy ID)
                if 11 <= col_idx <= 19:
                    cell.alignment = Alignment(horizontal='center', vertical='center')
        data_end_row = 1 + len(candidates)
    else:
        # Example row so HR sees the shape
        example = [
            '',
            'Sara Ahmed',
            'Product Designer',
            'Operations',
            '+971500000000',
            'sara.ahmed@example.com',
            'Ali Hassan',
            'EMP-01234',
            HIRING_PIPELINE_LABELS['gathering_documents'],
            '',  # Vacancy ID
            DOC_STATUS_TICK,
            DOC_STATUS_CROSS,
            DOC_STATUS_TICK,
            DOC_STATUS_TICK,
            DOC_STATUS_CROSS,
            DOC_STATUS_CROSS,
            DOC_STATUS_CROSS,
            DOC_STATUS_CROSS,
            DOC_STATUS_CROSS,
            'Example row — replace or delete before importing',
        ]
        for col_idx, val in enumerate(example, start=1):
            cell = ws.cell(2, col_idx, val)
            cell.fill = example_fill
            if 11 <= col_idx <= 19:
                cell.alignment = Alignment(horizontal='center', vertical='center')
        data_end_row = 2

    # Dropdowns: use inline lists (not a hidden sheet). Hidden-sheet refs often
    # only work on the first data row in Excel for Mac / some Excel builds.
    # showDropDown=False is required — Excel treats True as "hide arrow".
    max_dv_row = max(data_end_row + 200, 1000)
    # Stages first, then On hold as a process pause (not a linear stage).
    pipe_list = ','.join(
        HIRING_PIPELINE_LABELS[k] for k in (HIRING_PIPELINE_STEPS + ('on_hold',))
    )
    status_list = ','.join(DOC_STATUS_LABELS)

    pipe_dv = DataValidation(
        type='list',
        formula1=f'"{pipe_list}"',
        allow_blank=True,
        showDropDown=False,
        showErrorMessage=True,
    )
    pipe_dv.error = 'Pick a pipeline stage from the list'
    pipe_dv.errorTitle = 'Invalid pipeline'
    pipe_dv.add(f'I2:I{max_dv_row}')
    ws.add_data_validation(pipe_dv)

    status_dv = DataValidation(
        type='list',
        formula1=f'"{status_list}"',
        allow_blank=True,
        showDropDown=False,
        showErrorMessage=True,
    )
    status_dv.error = f'Use {DOC_STATUS_CROSS} (missing) or {DOC_STATUS_TICK} (submitted)'
    status_dv.errorTitle = 'Invalid status'
    # Doc columns J–R (9 docs)
    status_dv.add(f'K2:S{max_dv_row}')
    ws.add_data_validation(status_dv)

    # Instructions
    ws2 = wb.create_sheet('Instructions')
    lines = [
        'Hiring Document Tracker — Excel import',
        '',
        'How to use',
        '1. Download this template (or Export current candidates).',
        '2. Fill one row per candidate. Use the dropdowns for Pipeline Status and each document column.',
        '3. Upload the file via Import Excel on the Hiring dashboard.',
        '',
        'Matching rules (upsert)',
        '• If Candidate ID is set and exists → update that candidate.',
        '• If Candidate ID is set but not found (e.g. export from another environment) → fall through below.',
        '• Else if Email matches an existing candidate → update that candidate.',
        '• Else → create a new candidate (Full Name and Role are required).',
        '• Vacancy ID is optional: if the vacancy is missing on this server, the candidate still imports.',
        '',
        'Document statuses',
        f'• {DOC_STATUS_CROSS} — missing / not submitted (clears any uploaded file for that slot).',
        f'• {DOC_STATUS_TICK} — submitted / on file (checklist complete; for PCC this marks attested).',
        '• Blank cell — leave the current status unchanged.',
        '• Older files that still say Missing / Uploaded / Received / Attested / Verified are still accepted on import.',
        '',
        'Pipeline stages (in order)',
        *[f'• {HIRING_PIPELINE_LABELS[k]}' for k in HIRING_PIPELINE_STEPS],
        f'• {HIRING_PIPELINE_LABELS["on_hold"]} — pauses the whole process (not a stage)',
        '',
        'Notes',
        '• Excel does not upload document files — use the candidate detail page for files.',
        '• Comments max 4000 characters.',
        '• Bad rows are reported; other rows still import.',
        '• Dropdowns apply to Pipeline Status and document columns through row '
        f'{max_dv_row}. Re-download the template if an older file is missing them.',
    ]
    for i, line in enumerate(lines, start=1):
        ws2.cell(i, 1, line)
        if i == 1:
            ws2.cell(i, 1).font = Font(bold=True, size=14, color='125435')
    ws2.column_dimensions['A'].width = 90

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def read_hiring_dataframe(file_storage):
    """Return pandas DataFrame from uploaded .xlsx / .xls / .csv."""
    import pandas as pd

    filename = (file_storage.filename or '').lower()
    if not filename.endswith(('.xlsx', '.xls', '.csv')):
        raise ValueError('Upload .xlsx, .xls, or .csv')

    if filename.endswith('.csv'):
        return pd.read_csv(file_storage)

    if filename.endswith('.xlsx'):
        # Prefer Candidates sheet when present
        try:
            return pd.read_excel(file_storage, sheet_name='Candidates')
        except ValueError:
            file_storage.stream.seek(0)
            return pd.read_excel(file_storage)

    try:
        file_storage.stream.seek(0)
        return pd.read_excel(file_storage, engine='xlrd')
    except Exception:
        file_storage.stream.seek(0)
        html_text = file_storage.stream.read().decode('utf-8', errors='ignore')
        tables = pd.read_html(StringIO(html_text))
        if not tables:
            raise ValueError('Could not read any table from the file')
        return max(tables, key=lambda t: t.shape[0])


def parse_hiring_workbook(file_storage) -> list[dict[str, Any]]:
    """Parse spreadsheet into normalized row dicts."""
    import pandas as pd

    df = read_hiring_dataframe(file_storage)
    if df is None or df.empty:
        raise ValueError('Spreadsheet has no data rows')

    # Drop fully empty rows
    df = df.dropna(how='all')
    if df.empty:
        raise ValueError('Spreadsheet has no data rows')

    col_map = {}
    header_map = _build_header_map(df.columns)
    for col in df.columns:
        n = normalize_column_name(col)
        if n in header_map:
            col_map[col] = header_map[n]

    if not any(v == ('field', 'full_name') for v in col_map.values()):
        raise ValueError('Missing required column: Full Name')

    rows = []
    for idx, series in df.iterrows():
        excel_row = int(idx) + 2  # header is row 1; pandas 0-based
        fields: dict[str, Any] = {}
        docs: dict[str, Optional[str]] = {}
        row_errors = []

        for col, kind_key in col_map.items():
            kind, key = kind_key
            raw = _cell_str(series.get(col))
            if kind == 'field':
                if key == 'pipeline_status':
                    pipe, err = _normalize_pipeline(raw)
                    if err:
                        row_errors.append(err)
                    elif pipe is not None:
                        fields['pipeline_status'] = pipe
                elif key == 'candidate_id':
                    if raw:
                        try:
                            fields['candidate_id'] = int(float(raw))
                        except (TypeError, ValueError):
                            row_errors.append(f'Invalid Candidate ID "{raw}"')
                elif raw:
                    fields[key] = raw
            else:
                status, err = _normalize_doc_status(raw, key)
                if err:
                    row_errors.append(err)
                elif status is not None:
                    docs[key] = status

        # Skip blank example-ish empty name rows
        name = (fields.get('full_name') or '').strip()
        if not name and not fields.get('candidate_id') and not fields.get('email'):
            continue

        comments = (fields.get('comments') or '')
        if 'example row' in comments.lower() and not fields.get('candidate_id'):
            continue

        rows.append({
            'excel_row': excel_row,
            'fields': fields,
            'docs': docs,
            'errors': row_errors,
        })

    if not rows:
        raise ValueError('No candidate rows found')
    return rows


def apply_hiring_import(rows: list[dict], user, seed_documents_fn, clear_document_file_fn) -> dict:
    """
    Upsert candidates and apply document statuses.
    seed_documents_fn / clear_document_file_fn come from hiring_documents to avoid circular imports.
    """
    created = 0
    updated = 0
    skipped = 0
    errors: list[dict] = []
    warnings: list[dict] = []

    # Prefetch email → candidate for matching
    email_index: dict[str, HiringCandidate] = {}
    for c in HiringCandidate.query.filter(HiringCandidate.email.isnot(None)).all():
        em = (c.email or '').strip().lower()
        if em and em not in email_index:
            email_index[em] = c

    for row in rows:
        excel_row = row.get('excel_row')
        fields = dict(row.get('fields') or {})
        docs = dict(row.get('docs') or {})
        row_errors = list(row.get('errors') or [])

        if row_errors:
            errors.append({'row': excel_row, 'error': '; '.join(row_errors)})
            skipped += 1
            continue

        comments_val = (fields.get('comments') or '').strip()
        if comments_val and len(comments_val) > 4000:
            errors.append({'row': excel_row, 'error': 'Comments must be 4000 characters or fewer'})
            skipped += 1
            continue

        try:
            with db.session.begin_nested():
                candidate = None
                is_create = False
                cid = fields.get('candidate_id')
                email = (fields.get('email') or '').strip()

                # Prefer ID when it exists on this DB; otherwise fall through
                # (common when re-importing an export from another environment).
                if cid:
                    candidate = db.session.get(HiringCandidate, cid)
                if not candidate and email:
                    candidate = email_index.get(email.lower())

                if not candidate:
                    name = (fields.get('full_name') or '').strip()
                    role = (fields.get('role') or '').strip()
                    if not name:
                        raise ValueError('Full Name is required to create a candidate')
                    if not role:
                        raise ValueError('Role is required to create a candidate')
                    candidate = HiringCandidate(
                        full_name=name,
                        role=role,
                        department=(fields.get('department') or '').strip() or None,
                        phone=(fields.get('phone') or '').strip() or None,
                        email=email or None,
                        replacement_name=(fields.get('replacement_name') or '').strip() or None,
                        replacement_employee_id=(fields.get('replacement_employee_id') or '').strip() or None,
                        comments=comments_val or None,
                        pipeline_status=fields.get('pipeline_status') or HIRING_PIPELINE_DEFAULT,
                        created_by=user.id if user else None,
                    )
                    db.session.add(candidate)
                    db.session.flush()
                    is_create = True
                    if email:
                        email_index[email.lower()] = candidate
                else:
                    if fields.get('full_name'):
                        candidate.full_name = fields['full_name'].strip()
                    role_val = (fields.get('role') or '').strip()
                    if role_val:
                        candidate.role = role_val
                    for key in (
                        'department', 'phone', 'email', 'replacement_name',
                        'replacement_employee_id', 'comments',
                    ):
                        if key in fields:
                            val = (fields.get(key) or '').strip()
                            setattr(candidate, key, val or None)
                    if fields.get('pipeline_status'):
                        candidate.pipeline_status = fields['pipeline_status']

                # Seed once after create/update. Relationship-backed seed keeps
                # candidate.documents current so we never re-insert the same slot.
                seed_documents_fn(candidate)
                db.session.flush()

                by_type = {d.doc_type: d for d in (candidate.documents or [])}
                for doc_type, status in docs.items():
                    doc = by_type.get(doc_type)
                    if not doc:
                        doc = HiringDocument(
                            doc_type=doc_type,
                            status='missing',
                        )
                        candidate.documents.append(doc)
                        db.session.flush()
                        by_type[doc_type] = doc

                    if status == 'missing':
                        clear_document_file_fn(doc)
                    else:
                        doc.status = status

                candidate.updated_at = utc_now_naive()
                if is_create:
                    created += 1
                else:
                    updated += 1

                # Optional Vacancy ID → assign to manpower vacancy (soft-fail so a
                # stale vacancy from another env does not block candidate import).
                vac_raw = (fields.get('vacancy_id') or '').strip()
                if vac_raw:
                    try:
                        vac_id = int(float(vac_raw)) if '.' in vac_raw else int(vac_raw)
                    except (TypeError, ValueError):
                        vac_id = None
                        warnings.append({
                            'row': excel_row,
                            'error': f'Invalid Vacancy ID "{vac_raw}" — candidate imported without vacancy link',
                        })
                    if vac_id:
                        from module_hr.staffing_link import assign_candidate_to_vacancy
                        _, _, assign_err = assign_candidate_to_vacancy(
                            candidate.id, vac_id, allow_reassign=True,
                        )
                        if assign_err:
                            warnings.append({
                                'row': excel_row,
                                'error': f'{assign_err} — candidate imported without vacancy link',
                            })
        except Exception as e:
            logger.warning('Hiring Excel row %s skipped: %s', excel_row, e)
            errors.append({'row': excel_row, 'error': str(e)})
            skipped += 1

    try:
        db.session.commit()
    except Exception as e:
        logger.exception('Hiring Excel import commit failed')
        db.session.rollback()
        raise ValueError(f'Import failed to save: {e}') from e

    return {
        'created': created,
        'updated': updated,
        'skipped': skipped,
        'errors': errors,
        'warnings': warnings,
        'processed': created + updated,
    }
