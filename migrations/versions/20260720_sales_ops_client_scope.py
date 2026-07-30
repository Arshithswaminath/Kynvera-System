"""Sales ownership, ticket SLA/payment, quotations, reminder log.

Revision ID: 20260720_sales_ops
Revises: 20260720_baseline
Create Date: 2026-07-20
"""
from alembic import op
import sqlalchemy as sa


revision = '20260720_sales_ops'
down_revision = '20260720_baseline'
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return column in {c['name'] for c in insp.get_columns(table)}


def _add_col(table: str, column: sa.Column):
    if not _has_column(table, column.name):
        op.add_column(table, column)


def upgrade():
    _add_col('bd_projects', sa.Column('owner_user_id', sa.Integer(), nullable=True))
    try:
        op.create_index('ix_bd_projects_owner_user_id', 'bd_projects', ['owner_user_id'], unique=False)
    except Exception:
        pass

    for col, typ in [
        ('sla_due_at', sa.DateTime()),
        ('sla_breached_at', sa.DateTime()),
        ('payment_status', sa.String(length=20)),
        ('payment_due_date', sa.Date()),
        ('paid_at', sa.DateTime()),
        ('paid_by_id', sa.Integer()),
    ]:
        _add_col('tickets', sa.Column(col, typ, nullable=True))
    try:
        op.create_index('ix_tickets_sla_due_at', 'tickets', ['sla_due_at'], unique=False)
    except Exception:
        pass

    for col, typ in [
        ('owner_user_id', sa.Integer()),
        ('paid_at', sa.DateTime()),
    ]:
        _add_col('trading_invoices', sa.Column(col, typ, nullable=True))
    try:
        op.create_index('ix_trading_invoices_owner_user_id', 'trading_invoices', ['owner_user_id'], unique=False)
    except Exception:
        pass

    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if 'reminder_dispatch_logs' not in tables:
        op.create_table(
            'reminder_dispatch_logs',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('entity_type', sa.String(length=40), nullable=False),
            sa.Column('entity_id', sa.Integer(), nullable=False),
            sa.Column('milestone', sa.String(length=60), nullable=False),
            sa.Column('recipients', sa.Text(), nullable=True),
            sa.Column('sent_at', sa.DateTime(), nullable=True),
            sa.UniqueConstraint('entity_type', 'entity_id', 'milestone', name='uq_reminder_dispatch'),
        )
        op.create_index('ix_reminder_dispatch_logs_entity_type', 'reminder_dispatch_logs', ['entity_type'])
        op.create_index('ix_reminder_dispatch_logs_entity_id', 'reminder_dispatch_logs', ['entity_id'])

    if 'quotations' not in tables:
        op.create_table(
            'quotations',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('quote_no', sa.String(length=50), nullable=False),
            sa.Column('bd_project_id', sa.Integer(), nullable=True),
            sa.Column('client_id', sa.Integer(), nullable=True),
            sa.Column('company_name', sa.String(length=255), nullable=False),
            sa.Column('contact_name', sa.String(length=160), nullable=True),
            sa.Column('contact_email', sa.String(length=255), nullable=True),
            sa.Column('quote_date', sa.Date(), nullable=False),
            sa.Column('valid_until', sa.Date(), nullable=True),
            sa.Column('status', sa.String(length=30), nullable=True),
            sa.Column('subtotal', sa.Float(), nullable=True),
            sa.Column('tax_pct', sa.Float(), nullable=True),
            sa.Column('tax_amount', sa.Float(), nullable=True),
            sa.Column('grand_total', sa.Float(), nullable=True),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('submitted_at', sa.DateTime(), nullable=True),
            sa.Column('approved_at', sa.DateTime(), nullable=True),
            sa.Column('approved_by_id', sa.Integer(), nullable=True),
            sa.Column('approval_signature', sa.Text(), nullable=True),
            sa.Column('approval_notes', sa.Text(), nullable=True),
            sa.Column('rejected_at', sa.DateTime(), nullable=True),
            sa.Column('rejection_notes', sa.Text(), nullable=True),
            sa.Column('trading_invoice_id', sa.Integer(), nullable=True),
            sa.Column('lpo_filename', sa.String(length=255), nullable=True),
            sa.Column('lpo_path', sa.String(length=512), nullable=True),
            sa.Column('lpo_cloud_url', sa.String(length=512), nullable=True),
            sa.Column('owner_user_id', sa.Integer(), nullable=True),
            sa.Column('created_by_id', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.UniqueConstraint('quote_no'),
        )
        op.create_index('ix_quotations_quote_no', 'quotations', ['quote_no'])
        op.create_index('ix_quotations_bd_project_id', 'quotations', ['bd_project_id'])
        op.create_index('ix_quotations_status', 'quotations', ['status'])

    if 'quotation_items' not in tables:
        op.create_table(
            'quotation_items',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('quotation_id', sa.Integer(), nullable=False),
            sa.Column('description', sa.String(length=255), nullable=False),
            sa.Column('details', sa.Text(), nullable=True),
            sa.Column('quantity', sa.Float(), nullable=True),
            sa.Column('unit', sa.String(length=40), nullable=True),
            sa.Column('unit_price', sa.Float(), nullable=True),
            sa.Column('total_price', sa.Float(), nullable=True),
        )
        op.create_index('ix_quotation_items_quotation_id', 'quotation_items', ['quotation_id'])

    if 'quotation_attachments' not in tables:
        op.create_table(
            'quotation_attachments',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('quotation_id', sa.Integer(), nullable=False),
            sa.Column('filename', sa.String(length=255), nullable=False),
            sa.Column('file_path', sa.String(length=512), nullable=True),
            sa.Column('cloud_url', sa.String(length=512), nullable=True),
            sa.Column('uploaded_by_id', sa.Integer(), nullable=True),
            sa.Column('uploaded_at', sa.DateTime(), nullable=True),
        )
        op.create_index('ix_quotation_attachments_quotation_id', 'quotation_attachments', ['quotation_id'])


def downgrade():
    for table in ('quotation_attachments', 'quotation_items', 'quotations', 'reminder_dispatch_logs'):
        try:
            op.drop_table(table)
        except Exception:
            pass
