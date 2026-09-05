"""
Procurement Module Routes
Catalog rate cards, property stock, purchase requests, goods received, issue to tickets.
"""
from datetime import datetime
from io import BytesIO
import os

from flask import Blueprint, render_template, request, jsonify, current_app, send_file, redirect, url_for
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.models import db, User, Ticket, TicketMaterial
from common.datetime_utils import utc_now_naive
from module_procurement.models import (
    TRADE_DEPARTMENTS, GM_APPROVAL_AED,
    ProcCatalogItem, ProcProperty, ProcStock, ProcSupplier,
    ProcPurchaseRequest, ProcPurchaseDocument, ProcMovement, _utcnow,
)
from module_procurement import service as svc
from module_procurement import pr_docs
from module_procurement import page_exports

procurement_bp = Blueprint('procurement_module', __name__, template_folder='templates')


def get_current_user():
    user_id = get_jwt_identity()
    if user_id is None:
        return None
    return db.session.get(User, int(user_id))


def _gate(user, dashboard=False):
    msg = 'Access denied to Procurement module' if dashboard else 'Access denied'
    return svc.deny_if_no_access(user, msg)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@procurement_bp.route('/')
@jwt_required()
def procurement_dashboard():
    user = get_current_user()
    denied = _gate(user, dashboard=True)
    if denied:
        return denied
    svc.migrate_submissions_if_needed()
    return render_template('procurement_dashboard.html', user=user)


@procurement_bp.route('/materials')
@jwt_required()
def materials_list():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    return render_template('procurement_materials.html', user=user)


@procurement_bp.route('/add-material')
@jwt_required()
def add_material_form():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    return render_template('procurement_add_material.html', user=user)


@procurement_bp.route('/properties')
@jwt_required()
def properties_list():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    return render_template('procurement_properties.html', user=user)


@procurement_bp.route('/property/<property_name>')
@jwt_required()
def property_materials(property_name):
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    row = ProcProperty.query.filter(
        db.func.lower(ProcProperty.name) == (property_name or '').strip().lower()
    ).first()
    display_name = svc.display_name_for_proc_property(row) if row else property_name
    theme = svc.property_card_theme(
        (row.name if row else property_name),
        is_shared=bool(row.is_shared) if row else False,
    )
    if row and row.icon:
        theme = {**theme, 'icon': row.icon}
    return render_template(
        'procurement_property_detail.html',
        user=user,
        property_name=property_name,
        property_display_name=display_name or property_name,
        theme=theme,
        property_public_id=row.public_id if row else '',
        icon_choices=svc.property_icon_choices(),
    )


@procurement_bp.route('/catalog/<department>')
@jwt_required()
def catalog_department(department):
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    allowed = list(TRADE_DEPARTMENTS)
    if department not in allowed:
        return redirect('/procurement/')
    dept_meta = {
        'HVAC':       {'color': '#0284c7', 'gradient': 'linear-gradient(135deg,#0ea5e9,#0284c7)', 'desc': 'Compressors, refrigerants, AHUs, filters and air-conditioning spare parts.'},
        'Cleaning':   {'color': '#047857', 'gradient': 'linear-gradient(135deg,#10b981,#047857)', 'desc': 'Mops, buckets, chemicals, trolleys, washroom supplies and cleaning equipment.'},
        'Electrical': {'color': '#d97706', 'gradient': 'linear-gradient(135deg,#f59e0b,#d97706)', 'desc': 'Switches, sockets, breakers, cables, lights, fans and electrical fittings.'},
        'Plumbing':   {'color': '#6d28d9', 'gradient': 'linear-gradient(135deg,#8b5cf6,#6d28d9)', 'desc': 'Mixers, WC sets, basins, pipes, traps, valves and all sanitary fittings.'},
    }
    return render_template(
        'procurement_catalog_department.html',
        user=user,
        department=department,
        meta=dept_meta[department],
    )


@procurement_bp.route('/suppliers')
@jwt_required()
def suppliers_page():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    return render_template('procurement_suppliers.html', user=user)


@procurement_bp.route('/purchase-requests')
@jwt_required()
def purchase_requests_page():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    return render_template('procurement_purchase_requests.html', user=user)


@procurement_bp.route('/purchase-requests/<request_id>')
@jwt_required()
def purchase_request_detail_page(request_id):
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    return render_template('procurement_purchase_request_detail.html', user=user, request_id=request_id)


@procurement_bp.route('/receive/<request_id>')
@jwt_required()
def receive_page(request_id):
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    return redirect(url_for('procurement_module.purchase_request_detail_page', request_id=request_id))


@procurement_bp.route('/email-settings')
@jwt_required()
def email_settings_page():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    return render_template('procurement_email_settings.html', user=user)


@procurement_bp.route('/doc-approve/<token>', methods=['GET', 'POST'])
def doc_approve_page(token):
    doc = pr_docs.find_doc_by_token(token)
    if not doc or not doc.request:
        return render_template(
            'procurement_doc_approve.html',
            ok=False, title='Link expired',
            message='This approval link is invalid or has already been used.',
        ), 400
    pr = doc.request
    if doc.status == 'approved':
        return render_template(
            'procurement_doc_approve.html',
            ok=True, title='Already approved',
            message=f'{pr.public_id} {doc.kind.replace("_", " ")} is already approved.',
        )
    try:
        pr_docs.approve_document(doc, approver='finance:email')
        if pr.requested_by_id and doc.kind == 'quotation' and pr.status == 'approved':
            svc.notify_users(
                [pr.requested_by_id],
                'Purchase request approved',
                f'{pr.public_id} was approved.',
                'proc_pr',
                submission_id=pr.public_id,
            )
        if pr.requested_by_id and doc.kind == 'invoice' and pr.status == 'closed':
            svc.notify_users(
                [pr.requested_by_id],
                'Purchase request closed',
                f'{pr.public_id} is complete. The invoice is stamped.',
                'proc_pr',
                submission_id=pr.public_id,
            )
        db.session.commit()
    except ValueError as e:
        db.session.rollback()
        return render_template(
            'procurement_doc_approve.html',
            ok=False, title='Could not approve',
            message=str(e),
        ), 400
    return render_template(
        'procurement_doc_approve.html',
        ok=True, title='Approved',
        message=f'{pr.public_id} {doc.kind.replace("_", " ")} is approved. A stamped PDF is ready on the request.',
    )


@procurement_bp.route('/log')
@jwt_required()
def usage_log_page():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    return render_template('procurement_log.html', user=user)


@procurement_bp.route('/refill')
@jwt_required()
def refill_page():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    return render_template('procurement_refill.html', user=user)


# ---------------------------------------------------------------------------
# Inventory materials (property stock)
# ---------------------------------------------------------------------------

@procurement_bp.route('/api/materials', methods=['GET'])
@jwt_required()
def get_materials():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    svc.migrate_submissions_if_needed()
    rows = ProcStock.query.order_by(ProcStock.created_at.desc()).all()
    materials = [r.to_material_dict() for r in rows]
    return jsonify({'success': True, 'materials': materials, 'total': len(materials)})


@procurement_bp.route('/api/recent-activity', methods=['GET'])
@jwt_required()
def recent_activity():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    limit = max(1, min(50, request.args.get('limit', 15, type=int)))
    moves = ProcMovement.query.order_by(ProcMovement.created_at.desc()).limit(limit).all()
    return jsonify({'success': True, 'activities': [m.to_activity_dict() for m in moves]})


@procurement_bp.route('/api/dashboard', methods=['GET'])
@jwt_required()
def dashboard_api():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    return jsonify(svc.dashboard_payload(
        request.args.get('range', 'month'),
        request.args.get('break'),
    ))


@procurement_bp.route('/api/usage-log', methods=['GET'])
@jwt_required()
def usage_log_api():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    rows = svc.usage_log_rows(
        movement_type=(request.args.get('type') or '').strip(),
        property_name=request.args.get('property', ''),
        property_id=(request.args.get('property_id') or '').strip(),
        department=request.args.get('department', ''),
        status=request.args.get('status', ''),
        search=request.args.get('q', ''),
        limit=max(1, min(500, request.args.get('limit', 200, type=int))),
    )
    return jsonify({'success': True, 'rows': rows, 'total': len(rows)})


@procurement_bp.route('/api/usage-log/export', methods=['GET'])
@jwt_required()
def usage_log_export():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    rows = svc.usage_log_rows(
        movement_type=(request.args.get('type') or '').strip(),
        property_name=request.args.get('property', ''),
        property_id=(request.args.get('property_id') or '').strip(),
        department=request.args.get('department', ''),
        status=request.args.get('status', ''),
        search=request.args.get('q', ''),
        limit=1000,
    )
    import csv
    output = BytesIO()
    # utf-8-sig so Excel opens AED-friendly CSV
    text = csv.StringIO()
    writer = csv.writer(text)
    for row in svc.usage_log_csv_rows(rows):
        writer.writerow(row)
    output.write(text.getvalue().encode('utf-8-sig'))
    output.seek(0)
    filename = f'procurement_usage_log_{datetime.now().strftime("%Y%m%d")}.csv'
    return send_file(output, mimetype='text/csv', as_attachment=True, download_name=filename)


@procurement_bp.route('/api/export/<kind>', methods=['GET'])
@jwt_required()
def page_export(kind):
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    try:
        data, filename, mime = page_exports.build_export(
            kind, request.args.get('format') or 'xlsx', request.args,
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception:
        current_app.logger.exception('Procurement export failed for %s', kind)
        return jsonify({'error': 'Could not build this export'}), 500
    return send_file(BytesIO(data), mimetype=mime, as_attachment=True, download_name=filename)


@procurement_bp.route('/api/refill', methods=['GET'])
@jwt_required()
def refill_api():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    items = svc.refill_rows()
    return jsonify({'success': True, 'items': items, 'total': len(items)})


@procurement_bp.route('/api/refill/summary', methods=['GET'])
@jwt_required()
def refill_summary_api():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    summary = svc.refill_queue_summary()
    summary['success'] = True
    return jsonify(summary)


@procurement_bp.route('/api/refill/create-pr', methods=['POST'])
@jwt_required()
def refill_create_pr():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    data = request.get_json() or {}
    items = data.get('items') or []
    if not items:
        return jsonify({'error': 'Select at least one item'}), 400
    property_id = (data.get('property_id') or items[0].get('property_id') or '').strip() or None
    lines = []
    for it in items:
        cat = (it.get('catalog_id') or '').strip()
        if not cat:
            continue
        lines.append({
            'catalog_id': cat,
            'qty': it.get('qty') or it.get('suggested_qty') or 1,
            'unit_price': it.get('unit_price'),
        })
    if not lines:
        return jsonify({'error': 'No valid catalog lines'}), 400
    try:
        pr = svc.create_purchase_request(
            user=user,
            property_public_id=property_id,
            supplier_public_id=(data.get('supplier_id') or '').strip() or None,
            notes=data.get('notes') or 'Refill from low-stock queue',
            lines=lines,
            status='submitted',
        )
    except ValueError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400
    db.session.commit()
    return jsonify({'success': True, 'request': pr.to_dict()})


@procurement_bp.route('/api/low-stock', methods=['GET'])
@jwt_required()
def low_stock():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    return jsonify({'success': True, 'items': svc.low_stock_rows()})


@procurement_bp.route('/api/materials', methods=['POST'])
@jwt_required()
def add_material():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    data = request.get_json() or {}
    if not data.get('material_name'):
        return jsonify({'error': 'Material name is required'}), 400
    stock = svc.add_inventory_material(
        user=user,
        material_name=data.get('material_name'),
        property_name=data.get('property', 'Unassigned'),
        category=data.get('category', 'General'),
        description=data.get('description', ''),
        unit=data.get('unit', 'pcs'),
        quantity=float(data.get('quantity', 0) or 0),
        unit_price=float(data.get('unit_price', 0) or 0),
        supplier_name=data.get('supplier', ''),
        notes=data.get('notes', ''),
        distribute=data.get('distribute') or data.get('share_mode') or 'site',
    )
    db.session.commit()
    return jsonify({
        'success': True,
        'submission_id': stock.public_id,
        'message': 'Material added successfully',
    })


@procurement_bp.route('/api/materials/<material_id>', methods=['DELETE'])
@jwt_required()
def delete_material(material_id):
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    stock = ProcStock.query.filter_by(public_id=material_id).first()
    if not stock:
        return jsonify({'error': 'Material not found'}), 404
    db.session.delete(stock)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Material deleted successfully'})


@procurement_bp.route('/api/import-excel', methods=['POST'])
@jwt_required()
def import_excel():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    if not file.filename.endswith(('.xlsx', '.xls')):
        return jsonify({'error': 'Invalid file format. Please upload an Excel file (.xlsx or .xls)'}), 400
    try:
        import pandas as pd
        from common.kynvera_excel_brand import read_import_dataframe

        df = read_import_dataframe(file, preferred_sheets=('Materials',))
        df.columns = df.columns.str.lower().str.strip()
        column_map = {
            'material': 'material_name', 'material name': 'material_name',
            'name': 'material_name', 'item': 'material_name', 'item name': 'material_name',
            'qty': 'quantity', 'qty.': 'quantity', 'price': 'unit_price',
            'unit price': 'unit_price', 'rate': 'unit_price', 'cat': 'category',
            'cat.': 'category', 'desc': 'description', 'desc.': 'description',
            'vendor': 'supplier', 'remarks': 'notes', 'comment': 'notes', 'comments': 'notes',
        }
        df.rename(columns=column_map, inplace=True)
        if 'material_name' not in df.columns:
            return jsonify({
                'error': 'Excel file must have a column named "Material Name", "Material", "Item", or "Name"'
            }), 400

        imported_count = 0
        errors = []

        def safe_float(val, default=0):
            try:
                if pd.isna(val):
                    return default
                return float(val)
            except Exception:
                return default

        for idx, row in df.iterrows():
            try:
                material_name = str(row.get('material_name', '')).strip()
                if not material_name or material_name == 'nan':
                    continue
                svc.add_inventory_material(
                    user=user,
                    material_name=material_name,
                    property_name=str(row.get('property', 'Unassigned')).strip() if not pd.isna(row.get('property')) else 'Unassigned',
                    category=str(row.get('category', 'Imported')).strip() if not pd.isna(row.get('category')) else 'Imported',
                    description=str(row.get('description', '')).strip() if not pd.isna(row.get('description')) else '',
                    unit=str(row.get('unit', 'pcs')).strip() if not pd.isna(row.get('unit')) else 'pcs',
                    quantity=safe_float(row.get('quantity', 0)),
                    unit_price=safe_float(row.get('unit_price', 0)),
                    supplier_name=str(row.get('supplier', '')).strip() if not pd.isna(row.get('supplier')) else '',
                    notes=str(row.get('notes', '')).strip() if not pd.isna(row.get('notes')) else '',
                    imported_from_excel=True,
                )
                imported_count += 1
            except Exception as e:
                errors.append(f'Row {idx + 2}: {str(e)}')
        db.session.commit()
        return jsonify({
            'success': True,
            'imported': imported_count,
            'total_rows': len(df),
            'errors': errors[:10] if errors else [],
            'message': f'Successfully imported {imported_count} materials',
        })
    except ImportError:
        return jsonify({'error': 'Excel import requires pandas and openpyxl. Please contact administrator.'}), 500
    except Exception as e:
        current_app.logger.exception(f'Excel import error: {e}')
        return jsonify({'error': f'Error processing Excel file: {str(e)}'}), 500


@procurement_bp.route('/api/sample-excel', methods=['GET'])
@jwt_required()
def download_sample_excel():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    try:
        from module_procurement.excel_template import build_procurement_sample_bytes
        output = BytesIO(build_procurement_sample_bytes())
        filename = f'procurement_import_sample_{datetime.now().strftime("%Y%m%d")}.xlsx'
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename,
        )
    except ImportError:
        return jsonify({'error': 'Sample Excel requires openpyxl.'}), 500
    except Exception as e:
        current_app.logger.exception(f'Procurement sample Excel error: {e}')
        return jsonify({'error': str(e)}), 500


@procurement_bp.route('/api/export-excel', methods=['GET'])
@jwt_required()
def export_excel():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    try:
        import pandas as pd
        property_name = request.args.get('property', None)
        rows = ProcStock.query.order_by(ProcStock.created_at.desc()).all()
        data = []
        for row in rows:
            m = row.to_material_dict()
            if property_name and m.get('property') != property_name:
                continue
            data.append({
                'ID': m['id'],
                'Material Name': m['material_name'],
                'Property': m['property'],
                'Category': m['category'],
                'Description': m['description'],
                'Unit': m['unit'],
                'Quantity': m['quantity'],
                'Unit Price (AED)': m['unit_price'],
                'Total Price (AED)': m['total_price'],
                'Supplier': m['supplier'],
                'Notes': m['notes'],
                'Added By': m['added_by'],
                'Date Added': row.created_at.strftime('%Y-%m-%d') if row.created_at else '',
            })
        df = pd.DataFrame(data)
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Materials')
        output.seek(0)
        filename = f'procurement_materials_{datetime.now().strftime("%Y%m%d")}.xlsx'
        if property_name:
            filename = f'procurement_{property_name.replace(" ", "_")}_{datetime.now().strftime("%Y%m%d")}.xlsx'
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename,
        )
    except ImportError:
        return jsonify({'error': 'Excel export requires pandas and openpyxl. Please contact administrator.'}), 500
    except Exception as e:
        current_app.logger.exception(f'Excel export error: {e}')
        return jsonify({'error': f'Error exporting to Excel: {str(e)}'}), 500


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------

@procurement_bp.route('/api/properties', methods=['GET'])
@jwt_required()
def get_properties():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    return jsonify({
        'success': True,
        'properties': svc.properties_with_counts(),
        'icons': svc.property_icon_choices(),
    })


@procurement_bp.route('/api/properties', methods=['POST'])
@jwt_required()
def add_property():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    data = request.get_json() or {}
    property_name = (data.get('name') or '').strip()
    if not property_name:
        return jsonify({'error': 'Property name is required'}), 400
    standalone = bool(data.get('standalone'))
    ticket_property_id = data.get('ticket_property_id')
    row = svc.get_or_create_property(
        property_name,
        address=data.get('address', ''),
        description=data.get('description', ''),
        link=False,
    )
    try:
        if ticket_property_id not in (None, ''):
            svc.apply_ticket_property_link(row, ticket_property_id)
        elif not standalone:
            svc.link_ticket_property(row)
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400
    db.session.commit()
    return jsonify({
        'success': True,
        'message': f'Property {row.name} added successfully',
        'id': row.public_id,
        'linked': bool(row.ticket_property_id),
    })


@procurement_bp.route('/api/properties/icon', methods=['POST'])
@jwt_required()
def set_property_icon():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    data = request.get_json() or {}
    try:
        row = svc.set_property_icon(
            icon=data.get('icon'),
            public_id=data.get('id'),
            name=data.get('name'),
            ticket_property_id=data.get('ticket_property_id'),
        )
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400
    db.session.commit()
    return jsonify({
        'success': True,
        'id': row.public_id,
        'icon': row.icon,
        'name': row.name,
    })


@procurement_bp.route('/api/ticket-properties', methods=['GET'])
@jwt_required()
def get_ticket_properties_picker():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    return jsonify({'success': True, 'properties': svc.ticket_properties_for_picker()})


@procurement_bp.route('/api/properties/<public_id>/link', methods=['POST'])
@jwt_required()
def link_property_to_ticket(public_id):
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    row = ProcProperty.query.filter_by(public_id=(public_id or '').strip()).first()
    if not row:
        return jsonify({'error': 'Property not found'}), 404
    data = request.get_json() or {}
    try:
        svc.apply_ticket_property_link(row, data.get('ticket_property_id'))
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400
    db.session.commit()
    return jsonify({
        'success': True,
        'id': row.public_id,
        'linked': True,
        'ticket_property_id': row.ticket_property_id,
    })


@procurement_bp.route('/api/property-materials/<property_name>', methods=['GET'])
@jwt_required()
def get_property_materials(property_name):
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    materials, row = svc.materials_for_property_view(property_name)
    return jsonify({
        'success': True,
        'property': property_name,
        'display_name': svc.display_name_for_proc_property(row) if row else property_name,
        'materials': materials,
        'total': len(materials),
    })


@procurement_bp.route('/api/material-assign-property', methods=['POST'])
@jwt_required()
def assign_material_to_property():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    data = request.get_json() or {}
    material_id = (data.get('material_id') or '').strip()
    property_name = (data.get('property') or '').strip()
    if not material_id or not property_name:
        return jsonify({'error': 'material_id and property are required'}), 400
    stock = ProcStock.query.filter_by(public_id=material_id).first()
    if not stock:
        return jsonify({'error': 'Material not found'}), 404
    dest = svc.get_or_create_property(property_name)
    existing = ProcStock.query.filter_by(
        property_id=dest.id, catalog_item_id=stock.catalog_item_id,
    ).first()
    if existing and existing.id != stock.id:
        existing.qty_on_hand = float(existing.qty_on_hand or 0) + float(stock.qty_on_hand or 0)
        db.session.delete(stock)
        keep_id = existing.public_id
    else:
        stock.property = dest
        keep_id = stock.public_id
    db.session.commit()
    return jsonify({
        'success': True,
        'message': f'Material assigned to {property_name}',
        'id': keep_id,
    })


@procurement_bp.route('/api/stock-elsewhere', methods=['GET'])
@jwt_required()
def stock_elsewhere():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    exclude = (request.args.get('exclude') or '').strip()
    groups = svc.list_stock_elsewhere(exclude)
    return jsonify({'success': True, 'sources': groups, 'total': sum(len(g['materials']) for g in groups)})


@procurement_bp.route('/api/stock-transfer', methods=['POST'])
@jwt_required()
def stock_transfer():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    data = request.get_json() or {}
    stock_id = (data.get('stock_id') or '').strip()
    dest_name = (data.get('to_property') or data.get('property') or '').strip()
    if not stock_id or not dest_name:
        return jsonify({'error': 'stock_id and to_property are required'}), 400
    stock = ProcStock.query.filter_by(public_id=stock_id).first()
    if not stock:
        return jsonify({'error': 'Material not found'}), 404
    dest = svc.get_or_create_property(dest_name)
    try:
        dest_stock = svc.transfer_stock(
            user=user,
            source_stock=stock,
            dest_property=dest,
            qty=data.get('qty') if data.get('qty') is not None else data.get('quantity'),
        )
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400
    db.session.commit()
    return jsonify({
        'success': True,
        'message': 'Stock moved',
        'id': dest_stock.public_id,
        'quantity': float(dest_stock.qty_on_hand or 0),
    })


@procurement_bp.route('/api/stock-share', methods=['POST'])
@jwt_required()
def stock_share():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    data = request.get_json() or {}
    stock_id = (data.get('stock_id') or '').strip()
    if not stock_id:
        return jsonify({'error': 'stock_id is required'}), 400
    stock = ProcStock.query.filter_by(public_id=stock_id).first()
    if not stock:
        return jsonify({'error': 'Material not found'}), 404
    try:
        dest_name = (data.get('to_property') or data.get('property') or '').strip()
        dest = svc.get_or_create_property(dest_name) if dest_name else None
        dest_stock = svc.share_stock(
            user=user,
            source_stock=stock,
            qty=data.get('qty') if data.get('qty') is not None else data.get('quantity'),
            mode=data.get('mode') or 'shared',
            dest_property=dest,
        )
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400
    db.session.commit()
    return jsonify({
        'success': True,
        'message': 'Shared across all sites',
        'id': dest_stock.public_id,
        'quantity': float(dest_stock.qty_on_hand or 0),
    })


@procurement_bp.route('/api/registered-properties', methods=['GET'])
@jwt_required()
def get_registered_properties():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    rows = ProcProperty.query.order_by(ProcProperty.created_at.desc()).all()
    return jsonify({'success': True, 'properties': [r.to_dict() for r in rows]})


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

@procurement_bp.route('/api/catalog/materials', methods=['GET'])
@jwt_required()
def get_catalog_materials():
    user_id = get_jwt_identity()
    user = db.session.get(User, int(user_id)) if user_id is not None else None
    if not user:
        return jsonify({'error': 'User not found'}), 404
    svc.migrate_submissions_if_needed()
    return jsonify(svc.catalog_grouped(
        department=request.args.get('department', ''),
        query_str=request.args.get('q', ''),
    ))


@procurement_bp.route('/api/catalog/materials', methods=['POST'])
@jwt_required()
def create_catalog_material():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    data = request.get_json() or {}
    department = (data.get('department') or '').strip()
    material_name = (data.get('material_name') or data.get('name') or '').strip()
    if department not in TRADE_DEPARTMENTS:
        return jsonify({'error': 'Invalid department'}), 400
    if not material_name:
        return jsonify({'error': 'Material name is required'}), 400
    try:
        unit_price = float(data.get('unit_price') or 0)
        if unit_price < 0:
            return jsonify({'error': 'Unit price cannot be negative'}), 400
    except Exception:
        return jsonify({'error': 'Invalid unit price'}), 400
    public_id = svc.new_public_id('CAT-MAT')
    item = ProcCatalogItem(
        public_id=public_id,
        department=department,
        name=material_name,
        brand=(data.get('brand') or '').strip(),
        uom=(data.get('uom') or 'PCS').strip() or 'PCS',
        unit_price=unit_price,
        min_qty=float(data.get('min_qty') or 0),
        is_rate_card=True,
    )
    db.session.add(item)
    db.session.commit()
    return jsonify({'success': True, 'id': public_id, 'message': 'Catalog material created'})


@procurement_bp.route('/api/catalog/materials/<material_id>', methods=['PUT'])
@jwt_required()
def update_catalog_material(material_id):
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    item = ProcCatalogItem.query.filter_by(public_id=material_id, is_rate_card=True).first()
    if not item:
        return jsonify({'error': 'Catalog material not found'}), 404
    data = request.get_json() or {}
    if 'department' in data:
        dept = (data.get('department') or '').strip()
        if dept and dept not in TRADE_DEPARTMENTS:
            return jsonify({'error': 'Invalid department'}), 400
        if dept:
            item.department = dept
    if 'material_name' in data or 'name' in data:
        name = (data.get('material_name') or data.get('name') or '').strip()
        if not name:
            return jsonify({'error': 'Material name is required'}), 400
        item.name = name
    if 'brand' in data:
        item.brand = (data.get('brand') or '').strip()
    if 'uom' in data:
        item.uom = (data.get('uom') or 'PCS').strip()
    if 'min_qty' in data:
        item.min_qty = float(data.get('min_qty') or 0)
    if 'unit_price' in data:
        try:
            unit_price = float(data.get('unit_price') or 0)
            if unit_price < 0:
                return jsonify({'error': 'Unit price cannot be negative'}), 400
            item.unit_price = unit_price
        except Exception:
            return jsonify({'error': 'Invalid unit price'}), 400
    item.updated_at = utc_now_naive()
    db.session.commit()
    return jsonify({
        'success': True,
        'message': 'Catalog material updated',
        'route_version': 2,
        'material': item.to_catalog_dict(),
    })


@procurement_bp.route('/api/catalog/materials/<material_id>', methods=['DELETE'])
@jwt_required()
def delete_catalog_material(material_id):
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    item = ProcCatalogItem.query.filter_by(public_id=material_id, is_rate_card=True).first()
    if not item:
        return jsonify({'error': 'Catalog material not found'}), 404
    if item.stock_rows.count():
        return jsonify({'error': 'Catalog item has stock and cannot be deleted'}), 400
    db.session.delete(item)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Catalog material deleted'})


# ---------------------------------------------------------------------------
# Suppliers
# ---------------------------------------------------------------------------

@procurement_bp.route('/api/suppliers', methods=['GET'])
@jwt_required()
def list_suppliers():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    rows = ProcSupplier.query.order_by(ProcSupplier.name.asc()).all()
    return jsonify({'success': True, 'suppliers': [s.to_dict() for s in rows]})


@procurement_bp.route('/api/suppliers', methods=['POST'])
@jwt_required()
def create_supplier():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Supplier name is required'}), 400
    row = ProcSupplier(
        public_id=svc.new_public_id('SUP'),
        name=name,
        contact_name=(data.get('contact_name') or '').strip(),
        contact_email=(data.get('contact_email') or '').strip(),
        contact_phone=(data.get('contact_phone') or '').strip(),
        trades=(data.get('trades') or '').strip(),
        notes=(data.get('notes') or '').strip(),
        is_active=True,
    )
    db.session.add(row)
    db.session.commit()
    return jsonify({'success': True, 'supplier': row.to_dict()})


# ---------------------------------------------------------------------------
# Purchase requests
# ---------------------------------------------------------------------------

@procurement_bp.route('/api/purchase-requests', methods=['GET'])
@jwt_required()
def list_purchase_requests():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    status = (request.args.get('status') or '').strip()
    q = ProcPurchaseRequest.query.order_by(ProcPurchaseRequest.created_at.desc())
    if status:
        q = q.filter_by(status=status)
    rows = q.all()
    healed = False
    for pr in rows:
        if pr_docs.close_if_invoice_complete(pr):
            healed = True
    if healed:
        db.session.commit()
    return jsonify({
        'success': True,
        'requests': [r.to_dict(with_lines=False) for r in rows],
        'gm_threshold': GM_APPROVAL_AED,
        'can_approve_procurement': svc.is_procurement_approver(user),
        'can_approve_gm': svc.is_gm_approver(user),
    })


@procurement_bp.route('/api/purchase-requests', methods=['POST'])
@jwt_required()
def create_purchase_request():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    data = request.get_json() or {}
    lines = data.get('lines') or []
    if not lines:
        return jsonify({'error': 'At least one line is required'}), 400
    try:
        pr = svc.create_purchase_request(
            user=user,
            property_public_id=data.get('property_id'),
            supplier_public_id=data.get('supplier_id'),
            notes=data.get('notes') or '',
            lines=lines,
            status='submitted',
        )
    except ValueError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400
    db.session.commit()
    return jsonify({'success': True, 'request': pr.to_dict()})


@procurement_bp.route('/api/purchase-requests/<request_id>', methods=['GET'])
@jwt_required()
def get_purchase_request(request_id):
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    pr = ProcPurchaseRequest.query.filter_by(public_id=request_id).first()
    if not pr:
        return jsonify({'error': 'Request not found'}), 404
    if pr_docs.close_if_invoice_complete(pr):
        db.session.commit()
    return jsonify({
        'success': True,
        'request': pr.to_dict(),
        'documents': pr_docs.documents_payload(pr),
        'can_approve_procurement': svc.is_procurement_approver(user),
        'can_approve_gm': svc.is_gm_approver(user),
        'gm_threshold': GM_APPROVAL_AED,
    })


@procurement_bp.route('/api/purchase-requests/<request_id>/approve', methods=['POST'])
@jwt_required()
def approve_purchase_request(request_id):
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    pr = ProcPurchaseRequest.query.filter_by(public_id=request_id).first()
    if not pr:
        return jsonify({'error': 'Request not found'}), 404
    if pr.status == 'procurement_review':
        if not svc.is_procurement_approver(user):
            return jsonify({'error': 'Only procurement can approve this request'}), 403
        pr.status = 'awaiting_quotation'
        pr_docs.generate_pr_pdf(pr)
    elif pr.status == 'gm_review':
        if not svc.is_gm_approver(user):
            return jsonify({'error': 'Only the general manager or a system administrator can approve this request'}), 403
        data = request.get_json() or {}
        try:
            quote = pr_docs.pick_quotation_for_approval(pr, data.get('quotation_kind'))
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        who = (user.full_name or user.username or 'Approver')
        pr_docs.approve_document(quote, approver=who)
    elif pr.status == 'received':
        if not svc.is_gm_approver(user):
            return jsonify({'error': 'Only the general manager or a system administrator can approve the invoice'}), 403
        inv = ProcPurchaseDocument.query.filter_by(request_id=pr.id, kind='invoice').first()
        if not inv or inv.status != 'pending_approval':
            return jsonify({'error': 'No invoice waiting for approval'}), 400
        who = (user.full_name or user.username or 'Approver')
        pr_docs.approve_document(inv, approver=who)
    else:
        return jsonify({'error': f'Cannot approve from status {pr.status}'}), 400
    if pr.requested_by_id and pr.status == 'approved':
        svc.notify_users(
            [pr.requested_by_id],
            'Purchase request approved',
            f'{pr.public_id} was approved.',
            'proc_pr',
            submission_id=pr.public_id,
        )
    if pr.requested_by_id and pr.status == 'closed':
        svc.notify_users(
            [pr.requested_by_id],
            'Purchase request closed',
            f'{pr.public_id} is complete. The invoice is stamped.',
            'proc_pr',
            submission_id=pr.public_id,
        )
    db.session.commit()
    return jsonify({'success': True, 'request': pr.to_dict(), 'documents': pr_docs.documents_payload(pr)})


@procurement_bp.route('/api/purchase-requests/<request_id>/reject', methods=['POST'])
@jwt_required()
def reject_purchase_request(request_id):
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    pr = ProcPurchaseRequest.query.filter_by(public_id=request_id).first()
    if not pr:
        return jsonify({'error': 'Request not found'}), 404
    if pr.status not in ('procurement_review', 'awaiting_quotation', 'gm_review', 'submitted'):
        return jsonify({'error': f'Cannot reject from status {pr.status}'}), 400
    if pr.status == 'gm_review' and not svc.is_gm_approver(user):
        return jsonify({'error': 'Only the general manager or a system administrator can reject this request'}), 403
    if pr.status != 'gm_review' and not svc.is_procurement_approver(user):
        return jsonify({'error': 'Only procurement can reject this request'}), 403
    data = request.get_json() or {}
    pr.status = 'rejected'
    pr.reject_reason = (data.get('reason') or '').strip()
    if pr.requested_by_id:
        svc.notify_users(
            [pr.requested_by_id],
            'Purchase request rejected',
            f'{pr.public_id}: {pr.reject_reason or "No reason given"}',
            'proc_pr',
            submission_id=pr.public_id,
        )
    db.session.commit()
    return jsonify({'success': True, 'request': pr.to_dict()})


@procurement_bp.route('/api/purchase-requests/<request_id>/order', methods=['POST'])
@jwt_required()
def mark_ordered(request_id):
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    pr = ProcPurchaseRequest.query.filter_by(public_id=request_id).first()
    if not pr:
        return jsonify({'error': 'Request not found'}), 404
    if pr.status != 'approved':
        return jsonify({'error': 'Request must be approved first'}), 400
    if not pr_docs.quotation_is_stamped(pr):
        return jsonify({'error': 'Upload and approve the supplier quotation before marking ordered'}), 400
    pr.status = 'ordered'
    pr.ordered_at = _utcnow()
    db.session.commit()
    return jsonify({'success': True, 'request': pr.to_dict()})


@procurement_bp.route('/api/purchase-requests/<request_id>/receive', methods=['POST'])
@jwt_required()
def receive_purchase_request(request_id):
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    pr = ProcPurchaseRequest.query.filter_by(public_id=request_id).first()
    if not pr:
        return jsonify({'error': 'Request not found'}), 404
    data = request.get_json() or {}
    try:
        receipt = svc.receive_purchase_request(
            pr, user=user,
            line_qtys=data.get('quantities') or None,
            notes=data.get('notes') or '',
        )
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    db.session.commit()
    return jsonify({'success': True, 'receipt': receipt.to_dict(), 'request': pr.to_dict(), 'documents': pr_docs.documents_payload(pr)})


@procurement_bp.route('/api/purchase-requests/<request_id>/send-quotations', methods=['POST'])
@jwt_required()
def send_quotations(request_id):
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    if not svc.is_procurement_approver(user):
        return jsonify({'error': 'Only procurement can send quotations for approval'}), 403
    pr = ProcPurchaseRequest.query.filter_by(public_id=request_id).first()
    if not pr:
        return jsonify({'error': 'Request not found'}), 404
    try:
        pr_docs.send_quotations_for_approval(pr)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    svc.notify_users(
        svc.gm_user_ids(),
        'Quotation ready for approval',
        f'{pr.public_id}: open Purchase requests to approve the quotation and the purchase request.',
        'proc_pr',
        submission_id=pr.public_id,
    )
    db.session.commit()
    return jsonify({
        'success': True,
        'request': pr.to_dict(),
        'documents': pr_docs.documents_payload(pr),
    })


@procurement_bp.route('/api/purchase-requests/<request_id>/documents/<kind>', methods=['POST'])
@jwt_required()
def upload_pr_document(request_id, kind):
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    pr = ProcPurchaseRequest.query.filter_by(public_id=request_id).first()
    if not pr:
        return jsonify({'error': 'Request not found'}), 404
    kind = (kind or '').strip().lower()
    if kind in ('quotation', 'quotation_2', 'quotation_3'):
        kind = 'quotation'
        if pr.status != 'awaiting_quotation':
            return jsonify({'error': 'Quotation can be added after procurement approves, before sending for approval'}), 400
    if kind == 'invoice' and pr.status != 'received':
        return jsonify({'error': 'Invoice can be added after goods are received'}), 400
    upload = request.files.get('file') or request.files.get('document')
    try:
        doc = pr_docs.save_upload(pr, kind, upload, user=user)
        if kind == 'invoice':
            pr_docs.begin_invoice_review(pr, doc)
            if doc.status == 'pending_approval':
                svc.notify_users(
                    svc.gm_user_ids(),
                    'Supplier invoice needs approval',
                    f'{pr.public_id} has an invoice waiting.',
                    'proc_pr',
                    submission_id=pr.public_id,
                )
    except ValueError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400
    db.session.commit()
    return jsonify({
        'success': True,
        'request': pr.to_dict(),
        'documents': pr_docs.documents_payload(pr),
    })


@procurement_bp.route('/api/purchase-requests/<request_id>/documents/<kind>', methods=['GET'])
@jwt_required()
def download_pr_document(request_id, kind):
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    pr = ProcPurchaseRequest.query.filter_by(public_id=request_id).first()
    if not pr:
        return jsonify({'error': 'Request not found'}), 404
    stamped_arg = (request.args.get('stamped') or '').lower()
    want_stamped = stamped_arg in ('1', 'true', 'yes')
    force_original = stamped_arg in ('0', 'false', 'no')
    doc = ProcPurchaseDocument.query.filter_by(request_id=pr.id, kind=kind).first()
    if kind == 'pr_pdf':
        has_stamp = bool(doc and doc.stamped_path and doc.status == 'approved')
        if has_stamp and not force_original:
            want_stamped = True
        elif not want_stamped:
            pr_docs.generate_pr_pdf(pr)
            db.session.commit()
            doc = ProcPurchaseDocument.query.filter_by(request_id=pr.id, kind=kind).first()
    if not doc:
        return jsonify({'error': 'Document not found'}), 404
    path = pr_docs.absolute_file(doc, stamped=want_stamped)
    if not path:
        return jsonify({'error': 'File not found'}), 404
    download_name = doc.original_name or os.path.basename(path)
    if want_stamped:
        download_name = f'{pr.public_id}-{kind}-approved.pdf'
    mime = 'application/pdf' if str(download_name).lower().endswith('.pdf') else None
    if mime is None and str(path).lower().endswith(('.png',)):
        mime = 'image/png'
    elif mime is None and str(path).lower().endswith(('.jpg', '.jpeg')):
        mime = 'image/jpeg'
    return send_file(
        path,
        as_attachment=True,
        download_name=download_name,
        mimetype=mime,
    )


@procurement_bp.route('/api/purchase-requests/<request_id>/documents/<kind>/approve', methods=['POST'])
@jwt_required()
def approve_pr_document(request_id, kind):
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    if not svc.is_gm_approver(user):
        return jsonify({'error': 'Only the general manager or a system administrator can approve this document'}), 403
    pr = ProcPurchaseRequest.query.filter_by(public_id=request_id).first()
    if not pr:
        return jsonify({'error': 'Request not found'}), 404
    doc = ProcPurchaseDocument.query.filter_by(request_id=pr.id, kind=kind).first()
    if not doc or doc.status != 'pending_approval':
        return jsonify({'error': 'Nothing waiting for approval'}), 400
    who = user.full_name or user.username or 'Approver'
    pr_docs.approve_document(doc, approver=who)
    if pr.requested_by_id and kind in ('quotation', 'quotation_2', 'quotation_3') and pr.status == 'approved':
        svc.notify_users(
            [pr.requested_by_id],
            'Purchase request approved',
            f'{pr.public_id} was approved.',
            'proc_pr',
            submission_id=pr.public_id,
        )
    db.session.commit()
    return jsonify({'success': True, 'request': pr.to_dict(), 'documents': pr_docs.documents_payload(pr)})


@procurement_bp.route('/api/email-templates', methods=['GET'])
@jwt_required()
def get_email_templates():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    templates = pr_docs.list_email_templates()
    db.session.commit()
    return jsonify({
        'success': True,
        'templates': templates,
        'placeholders': ['{pr_id}', '{property}', '{total}', '{status}', '{approve_url}', '{supplier}'],
    })


@procurement_bp.route('/api/email-templates', methods=['PUT'])
@jwt_required()
def put_email_templates():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    data = request.get_json() or {}
    items = data.get('templates') or []
    if data.get('event_key'):
        items = [data]
    try:
        for item in items:
            key = (item.get('event_key') or '').strip()
            if item.get('reset'):
                pr_docs.reset_email_template(key)
                continue
            pr_docs.save_email_template(
                key,
                to_emails=item.get('to_emails') if 'to_emails' in item else (item.get('to') or ''),
                cc_emails=item.get('cc_emails') if 'cc_emails' in item else (item.get('cc') or ''),
                subject=item.get('subject') if 'subject' in item else None,
                body=item.get('body') if 'body' in item else None,
                attach_pdf=item.get('attach_pdf') if 'attach_pdf' in item else None,
            )
    except ValueError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400
    db.session.commit()
    return jsonify({'success': True, 'templates': pr_docs.list_email_templates()})


# ---------------------------------------------------------------------------
# Issue / return to tickets
# ---------------------------------------------------------------------------

@procurement_bp.route('/api/open-tickets', methods=['GET'])
@jwt_required()
def open_tickets():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    rows = Ticket.query.filter(
        Ticket.status.in_(('open', 'assigned', 'site_attended', 'work_started', 'on_hold'))
    ).order_by(Ticket.created_at.desc()).limit(50).all()
    return jsonify({
        'success': True,
        'tickets': [{
            'ticket_id': t.ticket_id,
            'title': t.title,
            'status': t.status,
            'property_name': t.property_name or '',
        } for t in rows],
    })


@procurement_bp.route('/api/issue-to-ticket', methods=['POST'])
@jwt_required()
def issue_to_ticket():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    data = request.get_json() or {}
    ticket = Ticket.query.filter_by(ticket_id=(data.get('ticket_id') or '').strip()).first()
    if not ticket:
        return jsonify({'error': 'Ticket not found'}), 404
    try:
        mat = svc.issue_to_ticket(
            user=user,
            property_public_id=data.get('property_id'),
            catalog_public_id=data.get('catalog_id'),
            qty=data.get('qty') or data.get('quantity') or 1,
            ticket=ticket,
            chargeable=bool(data.get('chargeable')),
        )
        if hasattr(ticket, 'total_cost'):
            ticket.total_cost = float(ticket.total_cost or 0) + float(mat.total_price or 0)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    db.session.commit()
    return jsonify({'success': True, 'material': mat.to_dict()})


@procurement_bp.route('/api/return-from-ticket', methods=['POST'])
@jwt_required()
def return_from_ticket():
    user = get_current_user()
    denied = _gate(user)
    if denied:
        return denied
    data = request.get_json() or {}
    mat_id = data.get('ticket_material_id')
    mat = db.session.get(TicketMaterial, int(mat_id)) if mat_id else None
    if not mat:
        return jsonify({'error': 'Ticket material not found'}), 404
    try:
        svc.return_from_ticket(user=user, ticket_material=mat, property_public_id=data.get('property_id'))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    db.session.commit()
    return jsonify({'success': True})
