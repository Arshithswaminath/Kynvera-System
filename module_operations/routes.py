"""
Operations Module — Over Time records + Trading Invoices (with Client master).
URL prefix: /operations

v1 is simple CRUD (no approval workflow):
  - Over Time: manual add / list / edit / delete + Excel import + downloadable template.
  - Clients: customer master CRUD (used by trading invoices).
  - Trading Invoices: header + line items, server-computed totals, branded PDF.
"""
import uuid
import logging
from io import BytesIO
from datetime import datetime, date

from flask import (
    Blueprint, render_template, redirect, request, send_file, current_app,
)
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.models import (
    db, User, OvertimeRecord, Client, TradingInvoice, TradingInvoiceItem,
)
from common.error_responses import success_response, error_response

logger = logging.getLogger(__name__)

operations_bp = Blueprint('operations_bp', __name__, url_prefix='/operations',
                          template_folder='templates')


# ── Access control ───────────────────────────────────────────────────────────

def _has_operations_access(user):
    if not user:
        return False
    if user.role == 'admin':
        return True
    return bool(getattr(user, 'access_operations', False))


def _can_manage_invoices(user):
    """Who may create/edit/delete trading invoices (vs. view-only).

    Admins always have full access. Everyone else needs Operations access AND
    the per-user "full access" flag set by an admin; otherwise they are view-only."""
    if not user:
        return False
    if user.role == 'admin':
        return True
    return bool(getattr(user, 'access_operations', False)) and bool(getattr(user, 'access_operations_manage', False))


def _current_user():
    return User.query.get(get_jwt_identity())


# ── Helpers ──────────────────────────────────────────────────────────────────

def _gen_id(prefix):
    return f'{prefix}-' + uuid.uuid4().hex[:8].upper()


def _to_float(value, default=None):
    if value is None or value == '':
        return default
    try:
        return float(str(value).replace(',', '').strip())
    except (ValueError, TypeError):
        return default


def _parse_date(value):
    """Parse a date from ISO, DD/MM/YYYY, or a datetime/date object."""
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%m/%d/%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    # Last resort: ISO with time component
    try:
        return datetime.fromisoformat(s).date()
    except ValueError:
        return None


# ── Hub ──────────────────────────────────────────────────────────────────────

@operations_bp.route('/')
@jwt_required()
def operations_dashboard():
    user = _current_user()
    if not _has_operations_access(user):
        return redirect('/dashboard')
    return render_template('operations_dashboard.html', user=user)


# ── Over Time pages ──────────────────────────────────────────────────────────

@operations_bp.route('/overtime')
@jwt_required()
def overtime_page():
    user = _current_user()
    if not _has_operations_access(user):
        return redirect('/dashboard')
    return render_template('overtime.html', user=user)


@operations_bp.route('/api/overtime', methods=['GET'])
@jwt_required()
def api_list_overtime():
    user = _current_user()
    if not _has_operations_access(user):
        return error_response('Access denied', status_code=403, error_code='ACCESS_DENIED')
    records = OvertimeRecord.query.order_by(OvertimeRecord.date.desc(),
                                            OvertimeRecord.id.desc()).all()
    return success_response({'records': [r.to_dict() for r in records]})


@operations_bp.route('/api/overtime', methods=['POST'])
@jwt_required()
def api_create_overtime():
    user = _current_user()
    if not _has_operations_access(user):
        return error_response('Access denied', status_code=403, error_code='ACCESS_DENIED')
    data = request.get_json(silent=True) or {}

    staff_name = (data.get('staff_name') or '').strip()
    ot_date = _parse_date(data.get('date'))
    hours = _to_float(data.get('hours'))
    if not staff_name:
        return error_response('Staff name is required', status_code=400, error_code='VALIDATION_ERROR')
    if not ot_date:
        return error_response('A valid date is required', status_code=400, error_code='VALIDATION_ERROR')
    if hours is None:
        return error_response('Hours is required', status_code=400, error_code='VALIDATION_ERROR')

    rate = _to_float(data.get('rate_per_hour'))
    rec = OvertimeRecord(
        record_id=_gen_id('OT'),
        staff_name=staff_name,
        employee_id=(data.get('employee_id') or '').strip() or None,
        department=(data.get('department') or '').strip() or None,
        date=ot_date,
        hours=hours,
        rate_per_hour=rate,
        total_amount=round(hours * rate, 2) if rate is not None else None,
        reason=(data.get('reason') or '').strip() or None,
        status=(data.get('status') or 'recorded').strip() or 'recorded',
        created_by_id=user.id,
    )
    db.session.add(rec)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error('create_overtime: %s', e, exc_info=True)
        return error_response('Database error', status_code=500, error_code='DATABASE_ERROR')
    return success_response({'record': rec.to_dict()}, message='Overtime record created.', status_code=201)


@operations_bp.route('/api/overtime/<int:rec_id>', methods=['PUT'])
@jwt_required()
def api_update_overtime(rec_id):
    user = _current_user()
    if not _has_operations_access(user):
        return error_response('Access denied', status_code=403, error_code='ACCESS_DENIED')
    rec = OvertimeRecord.query.get(rec_id)
    if not rec:
        return error_response('Record not found', status_code=404, error_code='NOT_FOUND')
    data = request.get_json(silent=True) or {}

    if 'staff_name' in data:
        name = (data.get('staff_name') or '').strip()
        if not name:
            return error_response('Staff name cannot be empty', status_code=400, error_code='VALIDATION_ERROR')
        rec.staff_name = name
    if 'employee_id' in data:
        rec.employee_id = (data.get('employee_id') or '').strip() or None
    if 'department' in data:
        rec.department = (data.get('department') or '').strip() or None
    if 'date' in data:
        d = _parse_date(data.get('date'))
        if not d:
            return error_response('Invalid date', status_code=400, error_code='VALIDATION_ERROR')
        rec.date = d
    if 'hours' in data:
        h = _to_float(data.get('hours'))
        if h is None:
            return error_response('Invalid hours', status_code=400, error_code='VALIDATION_ERROR')
        rec.hours = h
    if 'rate_per_hour' in data:
        rec.rate_per_hour = _to_float(data.get('rate_per_hour'))
    if 'reason' in data:
        rec.reason = (data.get('reason') or '').strip() or None
    if 'status' in data:
        rec.status = (data.get('status') or 'recorded').strip() or 'recorded'

    rec.total_amount = round(rec.hours * rec.rate_per_hour, 2) if rec.rate_per_hour is not None else None
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error('update_overtime: %s', e, exc_info=True)
        return error_response('Database error', status_code=500, error_code='DATABASE_ERROR')
    return success_response({'record': rec.to_dict()}, message='Overtime record updated.')


@operations_bp.route('/api/overtime/<int:rec_id>', methods=['DELETE'])
@jwt_required()
def api_delete_overtime(rec_id):
    user = _current_user()
    if not _has_operations_access(user):
        return error_response('Access denied', status_code=403, error_code='ACCESS_DENIED')
    rec = OvertimeRecord.query.get(rec_id)
    if not rec:
        return error_response('Record not found', status_code=404, error_code='NOT_FOUND')
    db.session.delete(rec)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error('delete_overtime: %s', e, exc_info=True)
        return error_response('Database error', status_code=500, error_code='DATABASE_ERROR')
    return success_response(message='Overtime record deleted.')


@operations_bp.route('/api/overtime/import-excel', methods=['POST'])
@jwt_required()
def api_import_overtime_excel():
    user = _current_user()
    if not _has_operations_access(user):
        return error_response('Access denied', status_code=403, error_code='ACCESS_DENIED')
    try:
        import openpyxl
    except ImportError:
        return error_response('openpyxl is required for Excel import (pip install openpyxl)',
                              status_code=500, error_code='DEPENDENCY_ERROR')

    if 'file' not in request.files:
        return error_response('No file uploaded', status_code=400, error_code='VALIDATION_ERROR')
    f = request.files['file']
    if not f.filename:
        return error_response('No file selected', status_code=400, error_code='VALIDATION_ERROR')

    try:
        wb = openpyxl.load_workbook(BytesIO(f.read()), read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
    except Exception as e:
        return error_response(f'Could not read Excel file: {e}', status_code=400, error_code='PARSE_ERROR')

    if not rows:
        return error_response('Excel file is empty', status_code=400, error_code='VALIDATION_ERROR')

    header_row = [str(c or '').strip().lower().replace(' ', '_') for c in rows[0]]
    COL = {h: i for i, h in enumerate(header_row)}

    def _get(row, key, alt=None):
        idx = COL.get(key, COL.get(alt))
        if idx is None:
            return None
        v = row[idx] if idx < len(row) else None
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

    created, skipped, errors = 0, 0, []
    for row_num, row in enumerate(rows[1:], start=2):
        if all(c is None or str(c).strip() == '' for c in row):
            continue
        staff_name = _get(row, 'staff_name', 'name')
        raw_date = _get(row, 'date')
        raw_hours = _get(row, 'hours')
        if not staff_name:
            errors.append(f'Row {row_num}: staff name is required — skipped')
            continue
        ot_date = _parse_date(raw_date)
        if not ot_date:
            errors.append(f'Row {row_num}: invalid/missing date — skipped')
            continue
        hours = _to_float(raw_hours)
        if hours is None:
            errors.append(f'Row {row_num}: invalid/missing hours — skipped')
            continue
        rate = _to_float(_get(row, 'rate_per_hour', 'rate'))
        rec = OvertimeRecord(
            record_id=_gen_id('OT'),
            staff_name=staff_name,
            employee_id=_get(row, 'employee_id', 'emp_id'),
            department=_get(row, 'department'),
            date=ot_date,
            hours=hours,
            rate_per_hour=rate,
            total_amount=round(hours * rate, 2) if rate is not None else None,
            reason=_get(row, 'reason', 'notes'),
            status='recorded',
            imported_from_excel=True,
            created_by_id=user.id,
        )
        db.session.add(rec)
        created += 1

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error('import_overtime_excel commit: %s', e, exc_info=True)
        return error_response('Database error during import', status_code=500, error_code='DATABASE_ERROR')

    return success_response(
        {'created': created, 'skipped': skipped, 'errors': errors},
        message=f'{created} overtime record(s) imported.',
    )


@operations_bp.route('/api/overtime/export', methods=['GET'])
@jwt_required()
def api_export_overtime_excel():
    user = _current_user()
    if not _has_operations_access(user):
        return error_response('Access denied', status_code=403, error_code='ACCESS_DENIED')
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    except ImportError:
        return error_response('openpyxl is required (pip install openpyxl)',
                              status_code=500, error_code='DEPENDENCY_ERROR')

    records = OvertimeRecord.query.order_by(OvertimeRecord.date.desc(),
                                            OvertimeRecord.id.desc()).all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Overtime'

    headers = ['Staff Name', 'Employee ID', 'Department', 'Date',
               'Hours', 'Rate Per Hour', 'Total Amount', 'Status', 'Reason']
    header_fill = PatternFill('solid', fgColor='a8121e')
    header_font = Font(bold=True, color='FFFFFF', size=11)
    header_align = Alignment(horizontal='center', vertical='center', wrap_text=True)
    thin = Side(style='thin', color='AAAAAA')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    for col_idx, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = border

    col_widths = [26, 16, 22, 14, 10, 14, 14, 14, 36]
    for i, w in enumerate(col_widths, start=1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w
    ws.row_dimensions[1].height = 26

    row_fill = PatternFill('solid', fgColor='FFF5F5')
    data_font = Font(size=10)
    data_align = Alignment(vertical='center')

    for row_num, rec in enumerate(records, start=2):
        row_data = [
            rec.staff_name,
            rec.employee_id or '',
            rec.department or '',
            str(rec.date) if rec.date else '',
            rec.hours,
            rec.rate_per_hour,
            rec.total_amount,
            rec.status or '',
            rec.reason or '',
        ]
        for col_idx, val in enumerate(row_data, start=1):
            cell = ws.cell(row=row_num, column=col_idx, value=val)
            cell.font = data_font
            cell.alignment = data_align
            cell.border = border
            if row_num % 2 == 0:
                cell.fill = row_fill

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    today = date.today().strftime('%Y-%m-%d')
    return send_file(
        buf,
        as_attachment=True,
        download_name=f'overtime_export_{today}.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


@operations_bp.route('/api/overtime/template', methods=['GET'])
@jwt_required()
def api_overtime_template():
    user = _current_user()
    if not _has_operations_access(user):
        return redirect('/dashboard')
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    except ImportError:
        return error_response('openpyxl is required (pip install openpyxl)',
                              status_code=500, error_code='DEPENDENCY_ERROR')

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Overtime'

    headers = ['Staff Name', 'Employee ID', 'Department', 'Date',
               'Hours', 'Rate Per Hour', 'Reason']
    header_fill = PatternFill('solid', fgColor='a8121e')
    header_font = Font(bold=True, color='FFFFFF', size=11)
    header_align = Alignment(horizontal='center', vertical='center', wrap_text=True)
    thin = Side(style='thin', color='AAAAAA')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    for col_idx, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = border

    col_widths = [26, 16, 22, 14, 10, 14, 36]
    for i, w in enumerate(col_widths, start=1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w
    ws.row_dimensions[1].height = 26

    example = ['John Smith', 'EMP-001', 'MEP', '2026-06-01', '3', '25', 'Emergency AC repair']
    note_fill = PatternFill('solid', fgColor='FDECEE')
    note_font = Font(color='5A1118', size=10, italic=True)
    for col_idx, v in enumerate(example, start=1):
        cell = ws.cell(row=2, column=col_idx, value=v)
        cell.fill = note_fill
        cell.font = note_font
        cell.alignment = Alignment(vertical='center')
        cell.border = border

    ws2 = wb.create_sheet('Instructions')
    ws2['A1'] = 'Overtime Import — Instructions'
    ws2['A1'].font = Font(bold=True, size=13, color='a8121e')
    notes = [
        ('Staff Name', 'Required. Full name of the staff member.'),
        ('Employee ID', 'Optional. Staff/employee identifier (free text).'),
        ('Department', 'Optional. Team/department (e.g. MEP, Civil, Cleaning).'),
        ('Date', 'Required. Format: YYYY-MM-DD or DD/MM/YYYY.'),
        ('Hours', 'Required. Overtime hours worked — numbers only.'),
        ('Rate Per Hour', 'Optional. Hourly rate — numbers only. Total = Hours × Rate.'),
        ('Reason', 'Optional. Reason / notes for the overtime.'),
    ]
    for row_i, (col, desc) in enumerate(notes, start=3):
        ws2.cell(row=row_i, column=1, value=col).font = Font(bold=True)
        ws2.cell(row=row_i, column=2, value=desc)
    ws2.column_dimensions['A'].width = 18
    ws2.column_dimensions['B'].width = 64

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name='overtime_import_template.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


# ── Catalog materials (for invoice line-item search) ─────────────────────────

@operations_bp.route('/api/catalog-materials', methods=['GET'])
@jwt_required()
def api_catalog_materials():
    """Proxy the procurement catalog for operations users (who may lack procurement access)."""
    user = _current_user()
    if not _has_operations_access(user):
        return error_response('Access denied', status_code=403, error_code='ACCESS_DENIED')
    from app.models import Submission
    q = (request.args.get('q') or '').strip().lower()
    subs = Submission.query.filter_by(module_type='catalog_material').all()
    results = []
    for sub in subs:
        fd = sub.form_data or {}
        name = fd.get('material_name', '')
        if q and q not in name.lower() and q not in (fd.get('brand') or '').lower():
            continue
        try:
            unit_price = float(fd.get('unit_price') or 0)
        except Exception:
            unit_price = 0.0
        results.append({
            'name': name,
            'brand': fd.get('brand', ''),
            'uom': fd.get('uom', 'PCS'),
            'unit_price': unit_price,
        })
    results.sort(key=lambda x: x['name'])
    limit = 40 if q else 50
    return success_response({'materials': results[:limit]})


# ── Clients ──────────────────────────────────────────────────────────────────

@operations_bp.route('/clients')
@jwt_required()
def clients_page():
    user = _current_user()
    if not _has_operations_access(user):
        return redirect('/dashboard')
    return render_template('clients.html', user=user)


@operations_bp.route('/api/clients', methods=['GET'])
@jwt_required()
def api_list_clients():
    user = _current_user()
    if not _has_operations_access(user):
        return error_response('Access denied', status_code=403, error_code='ACCESS_DENIED')
    clients = Client.query.order_by(Client.client_name.asc()).all()
    return success_response({'clients': [c.to_dict() for c in clients]})


@operations_bp.route('/api/clients', methods=['POST'])
@jwt_required()
def api_create_client():
    user = _current_user()
    if not _has_operations_access(user):
        return error_response('Access denied', status_code=403, error_code='ACCESS_DENIED')
    data = request.get_json(silent=True) or {}
    name = (data.get('client_name') or '').strip()
    if not name:
        return error_response('Client name is required', status_code=400, error_code='VALIDATION_ERROR')
    c = Client(
        client_id=_gen_id('CLI'),
        client_name=name,
        contact_person=(data.get('contact_person') or '').strip() or None,
        email=(data.get('email') or '').strip() or None,
        phone=(data.get('phone') or '').strip() or None,
        billing_address=(data.get('billing_address') or '').strip() or None,
        city=(data.get('city') or '').strip() or None,
        country=(data.get('country') or '').strip() or None,
        tax_id=(data.get('tax_id') or '').strip() or None,
        status=(data.get('status') or 'active').strip() or 'active',
        notes=(data.get('notes') or '').strip() or None,
        created_by_id=user.id,
    )
    db.session.add(c)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error('create_client: %s', e, exc_info=True)
        return error_response('Database error', status_code=500, error_code='DATABASE_ERROR')
    return success_response({'client': c.to_dict()}, message='Client created.', status_code=201)


@operations_bp.route('/api/clients/<int:client_id>', methods=['PUT'])
@jwt_required()
def api_update_client(client_id):
    user = _current_user()
    if not _has_operations_access(user):
        return error_response('Access denied', status_code=403, error_code='ACCESS_DENIED')
    c = Client.query.get(client_id)
    if not c:
        return error_response('Client not found', status_code=404, error_code='NOT_FOUND')
    data = request.get_json(silent=True) or {}
    if 'client_name' in data:
        name = (data.get('client_name') or '').strip()
        if not name:
            return error_response('Client name cannot be empty', status_code=400, error_code='VALIDATION_ERROR')
        c.client_name = name
    for field in ('contact_person', 'email', 'phone', 'billing_address',
                  'city', 'country', 'tax_id', 'notes'):
        if field in data:
            setattr(c, field, (data.get(field) or '').strip() or None)
    if 'status' in data:
        c.status = (data.get('status') or 'active').strip() or 'active'
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error('update_client: %s', e, exc_info=True)
        return error_response('Database error', status_code=500, error_code='DATABASE_ERROR')
    return success_response({'client': c.to_dict()}, message='Client updated.')


@operations_bp.route('/api/clients/<int:client_id>', methods=['DELETE'])
@jwt_required()
def api_delete_client(client_id):
    user = _current_user()
    if not _has_operations_access(user):
        return error_response('Access denied', status_code=403, error_code='ACCESS_DENIED')
    c = Client.query.get(client_id)
    if not c:
        return error_response('Client not found', status_code=404, error_code='NOT_FOUND')
    if c.trading_invoices.count() > 0:
        return error_response('Cannot delete a client with existing invoices.',
                              status_code=400, error_code='VALIDATION_ERROR')
    db.session.delete(c)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error('delete_client: %s', e, exc_info=True)
        return error_response('Database error', status_code=500, error_code='DATABASE_ERROR')
    return success_response(message='Client deleted.')


# ── Trading Invoices ─────────────────────────────────────────────────────────

def _recompute_totals(invoice, tax_pct):
    subtotal = round(sum((it.total_price or 0.0) for it in invoice.items), 2)
    tax_pct = _to_float(tax_pct, 0.0) or 0.0
    tax_amount = round(subtotal * tax_pct / 100.0, 2)
    invoice.subtotal = subtotal
    invoice.tax_pct = tax_pct
    invoice.tax_amount = tax_amount
    invoice.grand_total = round(subtotal + tax_amount, 2)


def _build_items(invoice, items_data):
    """Replace invoice.items from a list of dicts; returns error string or None."""
    invoice.items.clear()
    for idx, raw in enumerate(items_data or [], start=1):
        material = (raw.get('material_name') or '').strip()
        if not material:
            continue
        qty = _to_float(raw.get('quantity'), 0.0) or 0.0
        unit_price = _to_float(raw.get('unit_price'), 0.0) or 0.0
        invoice.items.append(TradingInvoiceItem(
            material_name=material,
            description=(raw.get('description') or '').strip() or None,
            quantity=qty,
            unit=(raw.get('unit') or '').strip() or None,
            unit_price=unit_price,
            total_price=round(qty * unit_price, 2),
        ))
    if not invoice.items:
        return 'At least one line item with a material name is required.'
    return None


@operations_bp.route('/invoices')
@jwt_required()
def invoices_page():
    user = _current_user()
    if not _has_operations_access(user):
        return redirect('/dashboard')
    return render_template('trading_invoices.html', user=user, can_manage=_can_manage_invoices(user))


@operations_bp.route('/invoices/<invoice_no>')
@jwt_required()
def invoice_detail_page(invoice_no):
    user = _current_user()
    if not _has_operations_access(user):
        return redirect('/dashboard')
    invoice = TradingInvoice.query.filter_by(invoice_no=invoice_no).first()
    if not invoice:
        return redirect('/operations/invoices')
    return render_template('trading_invoice_detail.html', user=user, invoice=invoice,
                           can_manage=_can_manage_invoices(user))


@operations_bp.route('/api/invoices', methods=['GET'])
@jwt_required()
def api_list_invoices():
    user = _current_user()
    if not _has_operations_access(user):
        return error_response('Access denied', status_code=403, error_code='ACCESS_DENIED')
    invoices = TradingInvoice.query.order_by(TradingInvoice.created_at.desc()).all()
    return success_response({'invoices': [inv.to_dict(include_items=False) for inv in invoices]})


@operations_bp.route('/api/invoices/<int:invoice_id>', methods=['GET'])
@jwt_required()
def api_get_invoice(invoice_id):
    user = _current_user()
    if not _has_operations_access(user):
        return error_response('Access denied', status_code=403, error_code='ACCESS_DENIED')
    inv = TradingInvoice.query.get(invoice_id)
    if not inv:
        return error_response('Invoice not found', status_code=404, error_code='NOT_FOUND')
    return success_response({'invoice': inv.to_dict()})


@operations_bp.route('/api/invoices', methods=['POST'])
@jwt_required()
def api_create_invoice():
    user = _current_user()
    if not _can_manage_invoices(user):
        return error_response('Access denied', status_code=403, error_code='ACCESS_DENIED')
    data = request.get_json(silent=True) or {}

    client_id = data.get('client_id')
    client = Client.query.get(client_id) if client_id else None
    if not client:
        return error_response('A valid client is required', status_code=400, error_code='VALIDATION_ERROR')

    inv = TradingInvoice(
        invoice_no=_gen_id('TRD-INV'),
        client_id=client.id,
        invoice_date=_parse_date(data.get('invoice_date')) or date.today(),
        due_date=_parse_date(data.get('due_date')),
        status=(data.get('status') or 'draft').strip() or 'draft',
        notes=(data.get('notes') or '').strip() or None,
        created_by_id=user.id,
    )
    err = _build_items(inv, data.get('items'))
    if err:
        return error_response(err, status_code=400, error_code='VALIDATION_ERROR')
    _recompute_totals(inv, data.get('tax_pct'))

    db.session.add(inv)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error('create_invoice: %s', e, exc_info=True)
        return error_response('Database error', status_code=500, error_code='DATABASE_ERROR')
    return success_response({'invoice': inv.to_dict()}, message='Trading invoice created.', status_code=201)


@operations_bp.route('/api/invoices/<int:invoice_id>', methods=['PUT'])
@jwt_required()
def api_update_invoice(invoice_id):
    user = _current_user()
    if not _can_manage_invoices(user):
        return error_response('Access denied', status_code=403, error_code='ACCESS_DENIED')
    inv = TradingInvoice.query.get(invoice_id)
    if not inv:
        return error_response('Invoice not found', status_code=404, error_code='NOT_FOUND')
    data = request.get_json(silent=True) or {}

    if 'client_id' in data:
        client = Client.query.get(data.get('client_id'))
        if not client:
            return error_response('A valid client is required', status_code=400, error_code='VALIDATION_ERROR')
        inv.client_id = client.id
    if 'invoice_date' in data:
        d = _parse_date(data.get('invoice_date'))
        if d:
            inv.invoice_date = d
    if 'due_date' in data:
        inv.due_date = _parse_date(data.get('due_date'))
    if 'status' in data:
        inv.status = (data.get('status') or 'draft').strip() or 'draft'
    if 'notes' in data:
        inv.notes = (data.get('notes') or '').strip() or None
    if 'items' in data:
        err = _build_items(inv, data.get('items'))
        if err:
            return error_response(err, status_code=400, error_code='VALIDATION_ERROR')
    # tax_pct may change independently of items; fall back to existing value
    _recompute_totals(inv, data.get('tax_pct', inv.tax_pct))

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error('update_invoice: %s', e, exc_info=True)
        return error_response('Database error', status_code=500, error_code='DATABASE_ERROR')
    return success_response({'invoice': inv.to_dict()}, message='Trading invoice updated.')


@operations_bp.route('/api/invoices/<int:invoice_id>', methods=['DELETE'])
@jwt_required()
def api_delete_invoice(invoice_id):
    user = _current_user()
    if not _can_manage_invoices(user):
        return error_response('Access denied', status_code=403, error_code='ACCESS_DENIED')
    inv = TradingInvoice.query.get(invoice_id)
    if not inv:
        return error_response('Invoice not found', status_code=404, error_code='NOT_FOUND')
    db.session.delete(inv)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error('delete_invoice: %s', e, exc_info=True)
        return error_response('Database error', status_code=500, error_code='DATABASE_ERROR')
    return success_response(message='Trading invoice deleted.')


@operations_bp.route('/invoices/<invoice_no>/pdf', methods=['GET'])
@jwt_required()
def invoice_pdf(invoice_no):
    user = _current_user()
    if not _has_operations_access(user):
        return redirect('/dashboard')
    inv = TradingInvoice.query.filter_by(invoice_no=invoice_no).first()
    if not inv:
        return error_response('Invoice not found', status_code=404, error_code='NOT_FOUND')

    try:
        from module_operations.trading_invoice_builder import build_trading_invoice_pdf
    except Exception as e:
        logger.error('trading_invoice_builder import: %s', e, exc_info=True)
        return error_response('PDF generator unavailable', status_code=500, error_code='DEPENDENCY_ERROR')

    buf = BytesIO()
    try:
        build_trading_invoice_pdf(inv, inv.client, list(inv.items), buf)
    except Exception as e:
        logger.error('build_trading_invoice_pdf: %s', e, exc_info=True)
        return error_response('Could not generate PDF', status_code=500, error_code='PDF_ERROR')
    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name=f'{inv.invoice_no}.pdf',
        mimetype='application/pdf',
    )
