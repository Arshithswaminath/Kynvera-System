"""Add Excel-aligned quotation fields (ref, discount, sections, signatures).

Revision ID: 20260721_quote_fmt
Revises: 20260720_desig_sales
Create Date: 2026-07-21
"""
from alembic import op
import sqlalchemy as sa


revision = '20260721_quote_fmt'
down_revision = '20260720_desig_sales'
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
    cols = [
        sa.Column('ref_no', sa.String(length=80), nullable=True),
        sa.Column('kind_attn', sa.String(length=160), nullable=True),
        sa.Column('client_tel', sa.String(length=60), nullable=True),
        sa.Column('subject', sa.String(length=500), nullable=True),
        sa.Column('project_name', sa.String(length=255), nullable=True),
        sa.Column('intro_text', sa.Text(), nullable=True),
        sa.Column('discount_amount', sa.Float(), nullable=True),
        sa.Column('amount_in_words', sa.String(length=400), nullable=True),
        sa.Column('notes_text', sa.Text(), nullable=True),
        sa.Column('exclusions_text', sa.Text(), nullable=True),
        sa.Column('terms_text', sa.Text(), nullable=True),
        sa.Column('signatory_name', sa.String(length=160), nullable=True),
        sa.Column('signatory_email', sa.String(length=255), nullable=True),
        sa.Column('signatory_phone', sa.String(length=60), nullable=True),
        sa.Column('prepared_signature', sa.Text(), nullable=True),
    ]
    for col in cols:
        _add_col('quotations', col)
    try:
        op.create_index('ix_quotations_ref_no', 'quotations', ['ref_no'], unique=False)
    except Exception:
        pass


def downgrade():
    for name in (
        'ref_no', 'kind_attn', 'client_tel', 'subject', 'project_name', 'intro_text',
        'discount_amount', 'amount_in_words', 'notes_text', 'exclusions_text',
        'terms_text', 'signatory_name', 'signatory_email', 'signatory_phone',
        'prepared_signature',
    ):
        if _has_column('quotations', name):
            op.drop_column('quotations', name)
