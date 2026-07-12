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
)

STATUS_HEADERS = tuple(DOC_COLUMN_HEADERS[dt] for dt in HIRING_DOC_TYPES)
ALL_HEADERS = PROFILE_HEADERS + STATUS_HEADERS + ('Comments',)

DOC_STATUS_LABELS = ('Missing', 'Uploaded', 'Attested', 'Verified')
DOC_STATUS_KEYS = frozenset({'missing', 'uploaded', 'attested', 'verified'})

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
    s = normalize_column_name(raw)
    if not s:
        return None, None

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


def _status_label(status: Optional[str]) -> str:
    if not status or status == 'missing':
        return 'Missing'
    return status.replace('_', ' ').title()


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
        'M': 12, 'N': 18, 'O': 12, 'P': 12, 'Q': 12, 'R': 12, 'S': 28,
    }
    for col, width in widths.items():
        ws.column_dimensions[col].width = width

    # Lookups sheet for dropdowns
    ws_look = wb.create_sheet('Lookups')
    ws_look['A1'] = 'Pipeline Status'
    for i, key in enumerate(HIRING_PIPELINE_STATUSES, start=2):
        ws_look.cell(i, 1, HIRING_PIPELINE_LABELS[key])
    ws_look['B1'] = 'Document Status'
    for i, label in enumerate(DOC_STATUS_LABELS, start=2):
        ws_look.cell(i, 2, label)
    ws_look.sheet_state = 'hidden'

    pipe_dv = DataValidation(
        type='list',
        formula1=f'=Lookups!$A$2:$A${1 + len(HIRING_PIPELINE_STATUSES)}',
        allow_blank=True,
    )
    pipe_dv.error = 'Pick a pipeline stage from the list'
    pipe_dv.errorTitle = 'Invalid pipeline'
    ws.add_data_validation(pipe_dv)
    pipe_dv.add('I2:I1000')

    status_dv = DataValidation(
        type='list',
        formula1=f'=Lookups!$B$2:$B${1 + len(DOC_STATUS_LABELS)}',
        allow_blank=True,
    )
    status_dv.error = 'Use Missing, Uploaded, Attested, or Verified'
    status_dv.errorTitle = 'Invalid status'
    ws.add_data_validation(status_dv)
    # Doc columns J–R (9 docs)
    status_dv.add('J2:R1000')

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
            ]
            for dt in HIRING_DOC_TYPES:
                doc = by_type.get(dt)
                values.append(_status_label(doc.status if doc else 'missing'))
            values.append(cand.comments or '')
            for col_idx, val in enumerate(values, start=1):
                ws.cell(row_idx, col_idx, val)
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
            'Uploaded',
            'Missing',
            'Uploaded',
            'Attested',
            'Missing',
            'Missing',
            'Missing',
            'Missing',
            'Missing',
            'Example row — replace or delete before importing',
        ]
        for col_idx, val in enumerate(example, start=1):
            cell = ws.cell(2, col_idx, val)
            cell.fill = example_fill

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
        '• Else if Email matches an existing candidate → update that candidate.',
        '• Else → create a new candidate (Full Name and Role are required).',
        '',
        'Document statuses',
        '• Missing — clears any uploaded file for that slot.',
        '• Uploaded / Attested / Verified — updates status only (no file attached via Excel).',
        '• Blank cell — leave the current status unchanged.',
        '• Attested is for PCC; on other documents it is treated as Uploaded.',
        '',
        'Pipeline statuses',
        *[f'• {HIRING_PIPELINE_LABELS[k]}' for k in HIRING_PIPELINE_STATUSES],
        '',
        'Notes',
        '• Excel does not upload document files — use the candidate detail page for files.',
        '• Comments max 4000 characters.',
        '• Bad rows are reported; other rows still import.',
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

                if cid:
                    candidate = db.session.get(HiringCandidate, cid)
                    if not candidate:
                        raise ValueError(f'Candidate ID {cid} not found')
                elif email:
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
                    seed_documents_fn(candidate)
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

                seed_documents_fn(candidate)
                db.session.flush()

                by_type = {d.doc_type: d for d in (candidate.documents or [])}
                for doc_type, status in docs.items():
                    doc = by_type.get(doc_type)
                    if not doc:
                        doc = HiringDocument(
                            candidate_id=candidate.id,
                            doc_type=doc_type,
                            status='missing',
                        )
                        db.session.add(doc)
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
        'processed': created + updated,
    }
