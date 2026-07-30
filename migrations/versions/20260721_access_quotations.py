"""Add users.access_quotations for sales quotation prepare permission.

Revision ID: 20260721_access_quotes
Revises: 20260721_quote_fmt
Create Date: 2026-07-21
"""
from alembic import op
import sqlalchemy as sa


revision = '20260721_access_quotes'
down_revision = '20260721_quote_fmt'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if 'users' not in insp.get_table_names():
        return
    cols = {c['name'] for c in insp.get_columns('users')}
    if 'access_quotations' not in cols:
        op.add_column(
            'users',
            sa.Column('access_quotations', sa.Boolean(), nullable=True, server_default=sa.false()),
        )


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if 'users' in insp.get_table_names():
        cols = {c['name'] for c in insp.get_columns('users')}
        if 'access_quotations' in cols:
            op.drop_column('users', 'access_quotations')
