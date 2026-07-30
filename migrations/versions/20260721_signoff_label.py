"""Add quotations.signoff_label for editable Thanks & Regards line.

Revision ID: 20260721_signoff_label
Revises: 20260721_access_quotes
Create Date: 2026-07-21
"""
from alembic import op
import sqlalchemy as sa


revision = '20260721_signoff_label'
down_revision = '20260721_access_quotes'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if 'quotations' not in insp.get_table_names():
        return
    cols = {c['name'] for c in insp.get_columns('quotations')}
    if 'signoff_label' not in cols:
        op.add_column(
            'quotations',
            sa.Column('signoff_label', sa.String(length=120), nullable=True),
        )


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if 'quotations' in insp.get_table_names():
        cols = {c['name'] for c in insp.get_columns('quotations')}
        if 'signoff_label' in cols:
            op.drop_column('quotations', 'signoff_label')
