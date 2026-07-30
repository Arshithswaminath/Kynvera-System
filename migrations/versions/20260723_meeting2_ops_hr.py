"""Meeting 2: timesheet, attendance, material sets, project_code, leave/insurance.

Revision ID: 20260723_meeting2
Revises: 20260721_signoff_label
Create Date: 2026-07-23
"""
from alembic import op
import sqlalchemy as sa


revision = '20260723_meeting2'
down_revision = '20260721_signoff_label'
branch_labels = None
depends_on = None


def _add_col(insp, table, name, col):
    if table not in insp.get_table_names():
        return
    cols = {c['name'] for c in insp.get_columns(table)}
    if name not in cols:
        op.add_column(table, col)


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    _add_col(insp, 'users', 'access_operations_timesheet',
             sa.Column('access_operations_timesheet', sa.Boolean(), server_default=sa.text('false')))
    _add_col(insp, 'users', 'access_operations_attendance',
             sa.Column('access_operations_attendance', sa.Boolean(), server_default=sa.text('false')))
    _add_col(insp, 'users', 'sick_leave_days', sa.Column('sick_leave_days', sa.Integer(), nullable=True))
    _add_col(insp, 'users', 'insurance_details', sa.Column('insurance_details', sa.String(255), nullable=True))
    _add_col(insp, 'technicians', 'sick_leave_days', sa.Column('sick_leave_days', sa.Integer(), nullable=True))
    _add_col(insp, 'technicians', 'insurance_details', sa.Column('insurance_details', sa.String(255), nullable=True))
    _add_col(insp, 'employees', 'sick_leave_days', sa.Column('sick_leave_days', sa.Integer(), nullable=True))
    _add_col(insp, 'employees', 'insurance_details', sa.Column('insurance_details', sa.String(255), nullable=True))
    _add_col(insp, 'ticket_projects', 'project_code', sa.Column('project_code', sa.String(60), nullable=True))

    tables = set(insp.get_table_names())
    if 'duty_timesheet_entries' not in tables:
        op.create_table(
            'duty_timesheet_entries',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('entry_id', sa.String(50), nullable=False),
            sa.Column('staff_name', sa.String(160), nullable=False),
            sa.Column('employee_id', sa.String(60), nullable=True),
            sa.Column('project_name', sa.String(200), nullable=False),
            sa.Column('project_code', sa.String(60), nullable=True),
            sa.Column('work_date', sa.Date(), nullable=False),
            sa.Column('start_time', sa.String(10), nullable=False),
            sa.Column('end_time', sa.String(10), nullable=False),
            sa.Column('hours', sa.Float(), nullable=False),
            sa.Column('day_type', sa.String(20), nullable=True),
            sa.Column('rate_per_hour', sa.Float(), nullable=True),
            sa.Column('total_amount', sa.Float(), nullable=True),
            sa.Column('remarks', sa.Text(), nullable=True),
            sa.Column('status', sa.String(30)),
            sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
            sa.Column('created_at', sa.DateTime()),
            sa.Column('updated_at', sa.DateTime()),
        )
        op.create_index('ix_duty_timesheet_entries_entry_id', 'duty_timesheet_entries', ['entry_id'], unique=True)

    if 'attendance_import_batches' not in tables:
        op.create_table(
            'attendance_import_batches',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('batch_id', sa.String(50), nullable=False),
            sa.Column('source_filename', sa.String(255), nullable=True),
            sa.Column('period_label', sa.String(80), nullable=True),
            sa.Column('row_count', sa.Integer()),
            sa.Column('matched_count', sa.Integer()),
            sa.Column('imported_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
            sa.Column('created_at', sa.DateTime()),
        )
        op.create_index('ix_attendance_import_batches_batch_id', 'attendance_import_batches', ['batch_id'], unique=True)

    if 'attendance_entries' not in tables:
        op.create_table(
            'attendance_entries',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('batch_id_fk', sa.Integer(), sa.ForeignKey('attendance_import_batches.id', ondelete='SET NULL'), nullable=True),
            sa.Column('technician_id', sa.Integer(), sa.ForeignKey('technicians.id'), nullable=True),
            sa.Column('employee_code', sa.String(60), nullable=True),
            sa.Column('staff_name', sa.String(160), nullable=False),
            sa.Column('project_name', sa.String(200), nullable=True),
            sa.Column('team_size', sa.Integer(), nullable=True),
            sa.Column('work_date', sa.Date(), nullable=False),
            sa.Column('day_status', sa.String(30)),
            sa.Column('start_time', sa.String(10), nullable=True),
            sa.Column('end_time', sa.String(10), nullable=True),
            sa.Column('hours', sa.Float(), nullable=True),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime()),
            sa.Column('updated_at', sa.DateTime()),
        )

    if 'material_sets' not in tables:
        op.create_table(
            'material_sets',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('set_id', sa.String(50), nullable=False),
            sa.Column('name', sa.String(200), nullable=False),
            sa.Column('material_type', sa.String(120), nullable=True),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('is_active', sa.Boolean()),
            sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
            sa.Column('created_at', sa.DateTime()),
            sa.Column('updated_at', sa.DateTime()),
        )
        op.create_index('ix_material_sets_set_id', 'material_sets', ['set_id'], unique=True)

    if 'material_set_items' not in tables:
        op.create_table(
            'material_set_items',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('set_id_fk', sa.Integer(), sa.ForeignKey('material_sets.id', ondelete='CASCADE'), nullable=False),
            sa.Column('material_name', sa.String(200), nullable=False),
            sa.Column('unit', sa.String(40), nullable=True),
            sa.Column('quantity', sa.Float()),
            sa.Column('unit_price', sa.Float()),
            sa.Column('procurement_ref', sa.String(50), nullable=True),
        )

    if 'adhoc_material_requests' not in tables:
        op.create_table(
            'adhoc_material_requests',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('request_id', sa.String(50), nullable=False),
            sa.Column('ticket_id', sa.Integer(), sa.ForeignKey('tickets.id'), nullable=True),
            sa.Column('material_name', sa.String(200), nullable=False),
            sa.Column('quantity', sa.Float()),
            sa.Column('unit', sa.String(40), nullable=True),
            sa.Column('unit_price', sa.Float(), nullable=True),
            sa.Column('reason', sa.Text(), nullable=True),
            sa.Column('status', sa.String(30)),
            sa.Column('requested_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
            sa.Column('om_approved_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
            sa.Column('om_approved_at', sa.DateTime(), nullable=True),
            sa.Column('gm_approved_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
            sa.Column('gm_approved_at', sa.DateTime(), nullable=True),
            sa.Column('decided_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
            sa.Column('decided_at', sa.DateTime(), nullable=True),
            sa.Column('decision_note', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime()),
        )
        op.create_index('ix_adhoc_material_requests_request_id', 'adhoc_material_requests', ['request_id'], unique=True)


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())
    for t in (
        'adhoc_material_requests', 'material_set_items', 'material_sets',
        'attendance_entries', 'attendance_import_batches', 'duty_timesheet_entries',
    ):
        if t in tables:
            op.drop_table(t)
