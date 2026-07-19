"""
Store Module Routes
Handles material lists, quantities, pricing, and Excel imports
"""
import uuid
import json
from datetime import datetime
from io import BytesIO
from flask import Blueprint, render_template, request, jsonify, current_app, send_file, redirect
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import db, User, Submission
from common.form_data_utils import shallow_copy_form_data
from common.datetime_utils import utc_now_naive

store_bp = Blueprint('store_module', __name__, template_folder='templates')

# Store catalog departments — fire & life-safety materials only
CATALOG_DEPARTMENTS = [
    'Fire Alarm',
    'Fire Suppression',
    'Fire Safety',
    'Emergency',
]

CATALOG_DEPT_META = {
    'Fire Alarm': {
        'color': '#d21725',
        'gradient': 'linear-gradient(135deg,#e8323f,#d21725)',
        'desc': 'Control panels, smoke/heat detectors, MCPs, sounders, strobes & alarm cabling.',
        'title': 'Fire Alarm Materials',
        'css_var': 'fire-alarm',
    },
    'Fire Suppression': {
        'color': '#ea580c',
        'gradient': 'linear-gradient(135deg,#f97316,#ea580c)',
        'desc': 'Sprinklers, FM200, CO2, foam, deluge systems, cylinders & valves.',
        'title': 'Fire Suppression Materials',
        'css_var': 'fire-suppression',
    },
    'Fire Safety': {
        'color': '#d97706',
        'gradient': 'linear-gradient(135deg,#f59e0b,#d97706)',
        'desc': 'Extinguishers, hose reels, hydrants, dry risers, cabinets & firefighting pumps.',
        'title': 'Fire Safety Materials',
        'css_var': 'fire-safety',
    },
    'Emergency': {
        'color': '#0369a1',
        'gradient': 'linear-gradient(135deg,#0ea5e9,#0369a1)',
        'desc': 'Emergency lighting, exit signs, PA systems, fire doors & evacuation equipment.',
        'title': 'Emergency & Evacuation Materials',
        'css_var': 'emergency',
    },
}


def get_current_user():
    """Get the current authenticated user"""
    user_id = get_jwt_identity()
    if user_id is None:
        return None
    return db.session.get(User, int(user_id))


@store_bp.route('/')
@jwt_required()
def procurement_dashboard():
    """Store Module Dashboard"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # Check if user has Store access
    if user.role != 'admin' and not getattr(user, 'access_procurement_module', False):
        return jsonify({'error': 'Access denied to Store module'}), 403
    
    return render_template('store_dashboard.html', user=user)


@store_bp.route('/materials')
@jwt_required()
def materials_list():
    """View all materials"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    if user.role != 'admin' and not getattr(user, 'access_procurement_module', False):
        return jsonify({'error': 'Access denied'}), 403
    
    return render_template('store_materials.html', user=user)


@store_bp.route('/add-material')
@jwt_required()
def add_material_form():
    """Add new material form"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    if user.role != 'admin' and not getattr(user, 'access_procurement_module', False):
        return jsonify({'error': 'Access denied'}), 403
    
    return render_template('store_add_material.html', user=user)


@store_bp.route('/api/materials', methods=['GET'])
@jwt_required()
def get_materials():
    """Get all materials from procurement submissions"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    if user.role != 'admin' and not getattr(user, 'access_procurement_module', False):
        return jsonify({'error': 'Access denied'}), 403
    
    # Get all procurement material submissions
    submissions = Submission.query.filter(
        Submission.module_type == 'procurement_material'
    ).order_by(Submission.created_at.desc()).all()
    
    materials = []
    for sub in submissions:
        if sub.form_data:
            material = sub.form_data.copy()
            material['id'] = sub.submission_id
            material['created_at'] = sub.created_at.isoformat() if sub.created_at else None
            materials.append(material)
    
    return jsonify({
        'success': True,
        'materials': materials,
        'total': len(materials)
    })


@store_bp.route('/api/recent-activity', methods=['GET'])
@jwt_required()
def recent_activity():
    """Get recent procurement material submissions for the dashboard activity log."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    if user.role != 'admin' and not getattr(user, 'access_procurement_module', False):
        return jsonify({'error': 'Access denied'}), 403
    limit = max(1, min(50, request.args.get('limit', 15, type=int)))
    submissions = Submission.query.filter(
        Submission.module_type == 'procurement_material'
    ).order_by(Submission.created_at.desc()).limit(limit).all()
    activities = []
    for sub in submissions:
        name = (sub.form_data or {}).get('material_name') or (sub.form_data or {}).get('site_name') or 'Material'
        added_by = (sub.form_data or {}).get('added_by') or ''
        if not added_by and sub.user_id:
            u = User.query.get(sub.user_id)
            added_by = (u.full_name or u.username) if u else 'System'
        if not added_by:
            added_by = 'System Administrator'
        activities.append({
            'material_name': name,
            'submitted_by': added_by,
            'created_at': sub.created_at.isoformat() if sub.created_at else None,
        })
    return jsonify({'success': True, 'activities': activities})


@store_bp.route('/api/materials', methods=['POST'])
@jwt_required()
def add_material():
    """Add a new material to the list"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    if user.role != 'admin' and not getattr(user, 'access_procurement_module', False):
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json()
    
    # Validate required fields
    if not data.get('material_name'):
        return jsonify({'error': 'Material name is required'}), 400
    
    # Generate submission ID
    submission_id = f"PROC-MAT-{uuid.uuid4().hex[:8].upper()}"
    
    # Create submission
    submission = Submission(
        submission_id=submission_id,
        user_id=user.id,
        module_type='procurement_material',
        site_name=data.get('material_name', 'Material'),
        visit_date=datetime.now().date(),
        status='submitted',
        workflow_status='submitted',
        supervisor_id=user.id,
        form_data={
            'material_name': data.get('material_name'),
            'property': data.get('property', 'Unassigned'),
            'category': data.get('category', 'General'),
            'description': data.get('description', ''),
            'unit': data.get('unit', 'pcs'),
            'quantity': float(data.get('quantity', 0)),
            'unit_price': float(data.get('unit_price', 0)),
            'total_price': float(data.get('quantity', 0)) * float(data.get('unit_price', 0)),
            'supplier': data.get('supplier', ''),
            'notes': data.get('notes', ''),
            'added_by': user.full_name or user.username
        }
    )
    
    db.session.add(submission)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'submission_id': submission_id,
        'message': 'Material added successfully'
    })


@store_bp.route('/api/materials/<material_id>', methods=['DELETE'])
@jwt_required()
def delete_material(material_id):
    """Delete a material from the list"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    if user.role != 'admin' and not getattr(user, 'access_procurement_module', False):
        return jsonify({'error': 'Access denied'}), 403
    
    submission = Submission.query.filter_by(submission_id=material_id).first()
    if not submission:
        return jsonify({'error': 'Material not found'}), 404
    
    db.session.delete(submission)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Material deleted successfully'
    })


@store_bp.route('/api/import-excel', methods=['POST'])
@jwt_required()
def import_excel():
    """Import materials from Excel file"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    if user.role != 'admin' and not getattr(user, 'access_procurement_module', False):
        return jsonify({'error': 'Access denied'}), 403
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not file.filename.endswith(('.xlsx', '.xls')):
        return jsonify({'error': 'Invalid file format. Please upload an Excel file (.xlsx or .xls)'}), 400
    
    try:
        import pandas as pd
        
        # Read Excel file
        df = pd.read_excel(file)
        
        # Normalize column names (lowercase, strip whitespace)
        df.columns = df.columns.str.lower().str.strip()
        
        # Map common column name variations
        column_map = {
            'material': 'material_name',
            'material name': 'material_name',
            'name': 'material_name',
            'item': 'material_name',
            'item name': 'material_name',
            'qty': 'quantity',
            'qty.': 'quantity',
            'price': 'unit_price',
            'unit price': 'unit_price',
            'rate': 'unit_price',
            'cat': 'category',
            'cat.': 'category',
            'desc': 'description',
            'desc.': 'description',
            'vendor': 'supplier',
            'remarks': 'notes',
            'comment': 'notes',
            'comments': 'notes'
        }
        
        df.rename(columns=column_map, inplace=True)
        
        # Ensure required columns exist
        if 'material_name' not in df.columns:
            return jsonify({
                'error': 'Excel file must have a column named "Material Name", "Material", "Item", or "Name"'
            }), 400
        
        imported_count = 0
        errors = []
        
        for idx, row in df.iterrows():
            try:
                material_name = str(row.get('material_name', '')).strip()
                if not material_name or material_name == 'nan':
                    continue
                
                # Generate submission ID
                submission_id = f"PROC-MAT-{uuid.uuid4().hex[:8].upper()}"
                
                # Parse numeric values safely
                def safe_float(val, default=0):
                    try:
                        if pd.isna(val):
                            return default
                        return float(val)
                    except:
                        return default
                
                quantity = safe_float(row.get('quantity', 0))
                unit_price = safe_float(row.get('unit_price', 0))
                
                # Create submission
                submission = Submission(
                    submission_id=submission_id,
                    user_id=user.id,
                    module_type='procurement_material',
                    site_name=material_name[:255],
                    visit_date=datetime.now().date(),
                    status='submitted',
                    workflow_status='submitted',
                    supervisor_id=user.id,
                    form_data={
                        'material_name': material_name,
                        'category': str(row.get('category', 'Imported')).strip() if not pd.isna(row.get('category')) else 'Imported',
                        'description': str(row.get('description', '')).strip() if not pd.isna(row.get('description')) else '',
                        'unit': str(row.get('unit', 'pcs')).strip() if not pd.isna(row.get('unit')) else 'pcs',
                        'quantity': quantity,
                        'unit_price': unit_price,
                        'total_price': quantity * unit_price,
                        'supplier': str(row.get('supplier', '')).strip() if not pd.isna(row.get('supplier')) else '',
                        'notes': str(row.get('notes', '')).strip() if not pd.isna(row.get('notes')) else '',
                        'added_by': user.full_name or user.username,
                        'imported_from_excel': True
                    }
                )
                
                db.session.add(submission)
                imported_count += 1
                
            except Exception as e:
                errors.append(f"Row {idx + 2}: {str(e)}")
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'imported': imported_count,
            'total_rows': len(df),
            'errors': errors[:10] if errors else [],  # Return first 10 errors
            'message': f'Successfully imported {imported_count} materials'
        })
        
    except ImportError:
        return jsonify({
            'error': 'Excel import requires pandas and openpyxl. Please contact administrator.'
        }), 500
    except Exception as e:
        current_app.logger.exception(f"Excel import error: {e}")
        return jsonify({
            'error': f'Error processing Excel file: {str(e)}'
        }), 500


@store_bp.route('/api/sample-excel', methods=['GET'])
@jwt_required()
def download_sample_excel():
    """Download a sample Excel file for procurement material import."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    if user.role != 'admin' and not getattr(user, 'access_procurement_module', False):
        return jsonify({'error': 'Access denied'}), 403
    try:
        import pandas as pd
        rows = [
            {'Material Name': 'Addressable Smoke Detector', 'Category': 'Fire Alarm', 'Description': 'Optical smoke detector, addressable', 'Unit': 'pcs', 'Quantity': 50, 'Unit Price': 185.00, 'Supplier': 'FireTech UAE', 'Notes': 'Civil Defence approved'},
            {'Material Name': 'Manual Call Point', 'Category': 'Fire Alarm', 'Description': 'Break-glass MCP with resettable element', 'Unit': 'pcs', 'Quantity': 30, 'Unit Price': 95.00, 'Supplier': 'FireTech UAE', 'Notes': ''},
            {'Material Name': 'Sprinkler Head 68°C', 'Category': 'Fire Suppression', 'Description': 'Pendant sprinkler, standard response', 'Unit': 'pcs', 'Quantity': 100, 'Unit Price': 28.00, 'Supplier': 'SafeFlow Systems', 'Notes': ''},
            {'Material Name': 'ABC Fire Extinguisher 6kg', 'Category': 'Fire Safety', 'Description': 'Dry powder portable extinguisher', 'Unit': 'pcs', 'Quantity': 40, 'Unit Price': 120.00, 'Supplier': 'Gulf Fire Safety', 'Notes': 'Annual service due'},
            {'Material Name': 'Emergency Exit Sign LED', 'Category': 'Emergency', 'Description': 'Maintained LED exit sign, 3hr battery', 'Unit': 'pcs', 'Quantity': 25, 'Unit Price': 145.00, 'Supplier': 'SafeExit Lighting', 'Notes': ''},
            {'Material Name': 'Fire Hose Reel 30m', 'Category': 'Fire Safety', 'Description': 'Swing-type hose reel with nozzle', 'Unit': 'pcs', 'Quantity': 12, 'Unit Price': 850.00, 'Supplier': 'Gulf Fire Safety', 'Notes': ''},
            {'Material Name': 'Fire Alarm Cable 2-Core 1.5mm', 'Category': 'Fire Alarm', 'Description': 'Fire-resistant alarm cable, red sheath', 'Unit': 'm', 'Quantity': 500, 'Unit Price': 4.50, 'Supplier': 'CablePro', 'Notes': 'Bulk drum'},
        ]
        df = pd.DataFrame(rows)
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Materials')
        output.seek(0)
        filename = f'procurement_import_sample_{datetime.now().strftime("%Y%m%d")}.xlsx'
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    except ImportError:
        return jsonify({'error': 'Sample Excel requires pandas and openpyxl.'}), 500
    except Exception as e:
        current_app.logger.exception(f"Store sample Excel error: {e}")
        return jsonify({'error': str(e)}), 500


@store_bp.route('/api/export-excel', methods=['GET'])
@jwt_required()
def export_excel():
    """Export materials list to Excel"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    if user.role != 'admin' and not getattr(user, 'access_procurement_module', False):
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        import pandas as pd
        from io import BytesIO
        from flask import send_file
        
        # Get property filter if provided
        property_name = request.args.get('property', None)
        
        # Get all materials
        query = Submission.query.filter(Submission.module_type == 'procurement_material')
        
        if property_name:
            # Filter by property - need to check form_data
            submissions = query.order_by(Submission.created_at.desc()).all()
            submissions = [s for s in submissions if s.form_data and s.form_data.get('property') == property_name]
        else:
            submissions = query.order_by(Submission.created_at.desc()).all()
        
        data = []
        for sub in submissions:
            if sub.form_data:
                data.append({
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
                    'Date Added': sub.created_at.strftime('%Y-%m-%d') if sub.created_at else ''
                })
        
        df = pd.DataFrame(data)
        
        # Create Excel file in memory
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
            download_name=filename
        )
        
    except ImportError:
        return jsonify({
            'error': 'Excel export requires pandas and openpyxl. Please contact administrator.'
        }), 500
    except Exception as e:
        current_app.logger.exception(f"Excel export error: {e}")
        return jsonify({
            'error': f'Error exporting to Excel: {str(e)}'
        }), 500


# ============================================
# PROPERTY-WISE MATERIALS ROUTES
# ============================================

@store_bp.route('/properties')
@jwt_required()
def properties_list():
    """View materials organized by property"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    if user.role != 'admin' and not getattr(user, 'access_procurement_module', False):
        return jsonify({'error': 'Access denied'}), 403
    
    return render_template('store_properties.html', user=user)


@store_bp.route('/property/<property_name>')
@jwt_required()
def property_materials(property_name):
    """View materials for a specific property"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    if user.role != 'admin' and not getattr(user, 'access_procurement_module', False):
        return jsonify({'error': 'Access denied'}), 403
    
    return render_template('store_property_detail.html', user=user, property_name=property_name)


@store_bp.route('/api/properties', methods=['GET'])
@jwt_required()
def get_properties():
    """Get all properties with material counts"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    if user.role != 'admin' and not getattr(user, 'access_procurement_module', False):
        return jsonify({'error': 'Access denied'}), 403
    
    # Get all materials and group by property
    submissions = Submission.query.filter(
        Submission.module_type == 'procurement_material'
    ).all()
    
    properties = {}
    for sub in submissions:
        if sub.form_data:
            prop = sub.form_data.get('property', 'Unassigned')
            if prop not in properties:
                properties[prop] = {
                    'name': prop,
                    'materials_count': 0,
                    'total_quantity': 0,
                    'total_value': 0
                }
            properties[prop]['materials_count'] += 1
            properties[prop]['total_quantity'] += float(sub.form_data.get('quantity', 0))
            properties[prop]['total_value'] += float(sub.form_data.get('total_price', 0))
    
    return jsonify({
        'success': True,
        'properties': list(properties.values())
    })


@store_bp.route('/api/properties', methods=['POST'])
@jwt_required()
def add_property():
    """Add a new property"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    if user.role != 'admin' and not getattr(user, 'access_procurement_module', False):
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json()
    property_name = data.get('name', '').strip()
    
    if not property_name:
        return jsonify({'error': 'Property name is required'}), 400
    
    # Store property in a simple submission record
    submission_id = f"PROC-PROP-{uuid.uuid4().hex[:8].upper()}"
    submission = Submission(
        submission_id=submission_id,
        user_id=user.id,
        module_type='procurement_property',
        site_name=property_name,
        visit_date=datetime.now().date(),
        status='active',
        workflow_status='active',
        supervisor_id=user.id,
        form_data={
            'property_name': property_name,
            'address': data.get('address', ''),
            'description': data.get('description', ''),
            'created_by': user.full_name or user.username,
            'created_at': datetime.now().isoformat()
        }
    )
    
    db.session.add(submission)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'Property "{property_name}" created successfully'
    })


@store_bp.route('/api/property-materials/<property_name>', methods=['GET'])
@jwt_required()
def get_property_materials(property_name):
    """Get materials for a specific property"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    if user.role != 'admin' and not getattr(user, 'access_procurement_module', False):
        return jsonify({'error': 'Access denied'}), 403
    
    # Get materials for this property
    submissions = Submission.query.filter(
        Submission.module_type == 'procurement_material'
    ).order_by(Submission.created_at.desc()).all()
    
    materials = []
    for sub in submissions:
        if sub.form_data and sub.form_data.get('property') == property_name:
            material = sub.form_data.copy()
            material['id'] = sub.submission_id
            material['created_at'] = sub.created_at.isoformat() if sub.created_at else None
            materials.append(material)
    
    return jsonify({
        'success': True,
        'property': property_name,
        'materials': materials,
        'total': len(materials)
    })


@store_bp.route('/api/material-assign-property', methods=['POST'])
@jwt_required()
def assign_material_to_property():
    """Assign a material to a property"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    if user.role != 'admin' and not getattr(user, 'access_procurement_module', False):
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json()
    material_id = data.get('material_id')
    property_name = data.get('property')
    
    if not material_id or not property_name:
        return jsonify({'error': 'Material ID and property name are required'}), 400
    
    submission = Submission.query.filter_by(submission_id=material_id).first()
    if not submission:
        return jsonify({'error': 'Material not found'}), 404
    
    # Update the property field (shallow copy so JSON column is marked dirty in SQLAlchemy)
    form_data = shallow_copy_form_data(submission)
    form_data['property'] = property_name
    submission.form_data = form_data
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'Material assigned to {property_name}'
    })


@store_bp.route('/catalog/<path:department>')
@jwt_required()
def catalog_department(department):
    """Show catalog materials for a fire / life-safety department."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    if department not in CATALOG_DEPARTMENTS:
        return redirect('/store/')
    return render_template(
        'store_catalog_department.html',
        user=user,
        department=department,
        meta=CATALOG_DEPT_META[department],
    )


@store_bp.route('/api/catalog/materials', methods=['GET'])
@jwt_required()
def get_catalog_materials():
    """
    Return the materials catalog grouped by department.
    Accessible to any authenticated user (inspection form users need this).
    Optional query params:
      ?department=Fire Alarm|Fire Suppression|Fire Safety|Emergency
      ?q=search term
    """
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    department = request.args.get('department', '').strip()
    query_str = request.args.get('q', '').strip().lower()

    submissions = Submission.query.filter_by(module_type='catalog_material').all()

    result = {}
    for sub in submissions:
        fd = sub.form_data or {}
        dept = fd.get('department', 'General')
        if department and dept != department:
            continue
        name = fd.get('material_name', '')
        if query_str and query_str not in name.lower() and query_str not in fd.get('brand', '').lower():
            continue

        if dept not in result:
            result[dept] = []
        try:
            unit_price = float(fd.get('unit_price') or 0)
        except Exception:
            unit_price = 0.0
        result[dept].append({
            'id': sub.submission_id,
            'name': name,
            'brand': fd.get('brand', ''),
            'uom': fd.get('uom', 'PCS'),
            'unit_price': unit_price,
        })

    # Sort each department's items alphabetically by name
    for dept in result:
        result[dept].sort(key=lambda x: x['name'])

    departments = sorted(result.keys())
    return jsonify({
        'success': True,
        'departments': departments,
        'materials': result,
        'total': sum(len(v) for v in result.values()),
    })


@store_bp.route('/api/catalog/materials', methods=['POST'])
@jwt_required()
def create_catalog_material():
    """Create a new catalog material (department catalog)."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    if user.role != 'admin' and not getattr(user, 'access_procurement_module', False):
        return jsonify({'error': 'Access denied'}), 403

    data = request.get_json() or {}
    department = (data.get('department') or '').strip()
    material_name = (data.get('material_name') or data.get('name') or '').strip()
    brand = (data.get('brand') or '').strip()
    uom = (data.get('uom') or 'PCS').strip()
    unit_price_raw = data.get('unit_price', 0)

    if department not in CATALOG_DEPARTMENTS:
        return jsonify({'error': 'Invalid department'}), 400
    if not material_name:
        return jsonify({'error': 'Material name is required'}), 400

    try:
        unit_price = float(unit_price_raw or 0)
        if unit_price < 0:
            return jsonify({'error': 'Unit price cannot be negative'}), 400
    except Exception:
        return jsonify({'error': 'Invalid unit price'}), 400

    submission_id = f"CAT-MAT-{uuid.uuid4().hex[:8].upper()}"
    submission = Submission(
        submission_id=submission_id,
        user_id=user.id,
        module_type='catalog_material',
        site_name=material_name,
        visit_date=datetime.now().date(),
        status='submitted',
        workflow_status='submitted',
        supervisor_id=user.id,
        form_data={
            'department': department,
            'material_name': material_name,
            'brand': brand,
            'uom': uom,
            'unit_price': unit_price,
        }
    )
    db.session.add(submission)
    db.session.commit()

    return jsonify({'success': True, 'id': submission_id, 'message': 'Catalog material created'})


@store_bp.route('/api/catalog/materials/<material_id>', methods=['PUT'])
@jwt_required()
def update_catalog_material(material_id):
    """Update an existing catalog material."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    if user.role != 'admin' and not getattr(user, 'access_procurement_module', False):
        return jsonify({'error': 'Access denied'}), 403

    submission = Submission.query.filter_by(submission_id=material_id, module_type='catalog_material').first()
    if not submission:
        return jsonify({'error': 'Catalog material not found'}), 404

    data = request.get_json() or {}
    # Make a copy so SQLAlchemy reliably detects JSON changes
    fd = dict(submission.form_data or {})

    # Department is fixed by where the user is editing from, but keep validation if sent.
    if 'department' in data:
        dept = (data.get('department') or '').strip()
        if dept and dept not in CATALOG_DEPARTMENTS:
            return jsonify({'error': 'Invalid department'}), 400
        if dept:
            fd['department'] = dept

    if 'material_name' in data or 'name' in data:
        name = (data.get('material_name') or data.get('name') or '').strip()
        if not name:
            return jsonify({'error': 'Material name is required'}), 400
        fd['material_name'] = name
        submission.site_name = name

    if 'brand' in data:
        fd['brand'] = (data.get('brand') or '').strip()

    if 'uom' in data:
        fd['uom'] = (data.get('uom') or 'PCS').strip()

    if 'unit_price' in data:
        try:
            unit_price = float(data.get('unit_price') or 0)
            if unit_price < 0:
                return jsonify({'error': 'Unit price cannot be negative'}), 400
            fd['unit_price'] = unit_price
        except Exception:
            return jsonify({'error': 'Invalid unit price'}), 400

    new_site_name = fd.get('material_name') or submission.site_name

    # Persist via direct UPDATE to avoid any ORM JSON mutation edge cases.
    Submission.query.filter_by(id=submission.id).update(
        {
            Submission.form_data: fd,
            Submission.site_name: new_site_name,
            Submission.updated_at: utc_now_naive(),
        },
        synchronize_session=False
    )
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Catalog material updated',
        'route_version': 2,
        'material': {
            'id': submission.submission_id,
            'name': fd.get('material_name', ''),
            'brand': fd.get('brand', ''),
            'uom': fd.get('uom', 'PCS'),
            'unit_price': float(fd.get('unit_price') or 0),
        }
    })


@store_bp.route('/api/catalog/materials/<material_id>', methods=['DELETE'])
@jwt_required()
def delete_catalog_material(material_id):
    """Delete a catalog material by its submission_id."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    if user.role != 'admin' and not getattr(user, 'access_procurement_module', False):
        return jsonify({'error': 'Access denied'}), 403

    submission = Submission.query.filter_by(
        submission_id=material_id, module_type='catalog_material'
    ).first()
    if not submission:
        return jsonify({'error': 'Catalog material not found'}), 404

    db.session.delete(submission)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Catalog material deleted'})


@store_bp.route('/api/registered-properties', methods=['GET'])
@jwt_required()
def get_registered_properties():
    """Get list of registered properties"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    if user.role != 'admin' and not getattr(user, 'access_procurement_module', False):
        return jsonify({'error': 'Access denied'}), 403
    
    # Get registered properties
    submissions = Submission.query.filter(
        Submission.module_type == 'procurement_property'
    ).order_by(Submission.created_at.desc()).all()
    
    properties = []
    for sub in submissions:
        if sub.form_data:
            properties.append({
                'id': sub.submission_id,
                'name': sub.form_data.get('property_name', sub.site_name),
                'address': sub.form_data.get('address', ''),
                'description': sub.form_data.get('description', ''),
                'created_at': sub.created_at.isoformat() if sub.created_at else None
            })
    
    return jsonify({
        'success': True,
        'properties': properties
    })


# ============================================
# PUBLIC CATALOG API — accessible to ticketing users
# ============================================

@store_bp.route('/api/catalog', methods=['GET'])
@jwt_required()
def catalog_for_tickets():
    """Return the material catalog to any authenticated user (used by ticketing material picker).
    No full procurement access required — just a valid login."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not found'}), 404

    search = (request.args.get('q') or '').strip().lower()
    category = (request.args.get('category') or '').strip()
    limit = min(200, max(1, request.args.get('limit', 100, type=int)))

    submissions = Submission.query.filter(
        Submission.module_type == 'procurement_material'
    ).order_by(Submission.site_name.asc()).all()

    items = []
    seen = set()
    for sub in submissions:
        if not sub.form_data:
            continue
        name = sub.form_data.get('material_name', '') or ''
        cat  = sub.form_data.get('category', '') or ''
        if search and search not in name.lower() and search not in cat.lower():
            continue
        if category and category.lower() not in cat.lower():
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append({
            'id': sub.submission_id,
            'name': name,
            'category': cat,
            'unit': sub.form_data.get('unit', 'pcs'),
            'unit_price': float(sub.form_data.get('unit_price', 0)),
            'supplier': sub.form_data.get('supplier', ''),
            'description': sub.form_data.get('description', ''),
        })
        if len(items) >= limit:
            break

    # Also collect categories for the filter dropdown
    all_cats = sorted(set(
        (s.form_data or {}).get('category', '')
        for s in Submission.query.filter(Submission.module_type == 'procurement_material').all()
        if (s.form_data or {}).get('category')
    ))

    return jsonify({'success': True, 'materials': items, 'categories': all_cats, 'total': len(items)})


@store_bp.route('/api/catalog', methods=['POST'])
@jwt_required()
def add_to_catalog():
    """Add a custom material from the ticketing material picker and save it to the catalog.
    Any authenticated user can add custom items — they are auto-saved for future reuse."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not found'}), 404

    data = request.get_json() or {}
    name = (data.get('name') or data.get('material_name') or '').strip()
    if not name:
        return jsonify({'error': 'name is required'}), 400

    # Check for duplicate
    existing = Submission.query.filter(
        Submission.module_type == 'procurement_material',
        Submission.site_name == name,
    ).first()
    if existing:
        return jsonify({'success': True, 'id': existing.submission_id, 'existing': True})

    submission_id = f"PROC-MAT-{uuid.uuid4().hex[:8].upper()}"
    sub = Submission(
        submission_id=submission_id,
        user_id=user.id,
        module_type='procurement_material',
        site_name=name,
        visit_date=datetime.now().date(),
        status='submitted',
        workflow_status='submitted',
        supervisor_id=user.id,
        form_data={
            'material_name': name,
            'category': data.get('category', 'Custom'),
            'unit': data.get('unit', 'pcs'),
            'unit_price': float(data.get('unit_price', 0)),
            'quantity': 0,
            'total_price': 0,
            'supplier': data.get('supplier', ''),
            'description': data.get('description', ''),
            'added_by': user.full_name or user.username,
            'source': 'ticket_picker',
        },
    )
    db.session.add(sub)
    db.session.commit()
    return jsonify({'success': True, 'id': submission_id, 'existing': False}), 201

