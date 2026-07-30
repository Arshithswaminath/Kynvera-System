"""Add users.access_sales_manager for company-wide sales view.

Revision ID: 20260720_sales_mgr
Revises: 20260720_sales_ops
Create Date: 2026-07-20
"""
from alembic import op
import sqlalchemy as sa


revision = '20260720_sales_mgr'
down_revision = '20260720_sales_ops'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if 'users' not in insp.get_table_names():
        return
    cols = {c['name'] for c in insp.get_columns('users')}
    if 'access_sales_manager' not in cols:
        op.add_column(
            'users',
            sa.Column('access_sales_manager', sa.Boolean(), nullable=True, server_default=sa.false()),
        )
    # Backfill BD ownership from created_by when missing
    if 'bd_projects' in insp.get_table_names():
        bp_cols = {c['name'] for c in insp.get_columns('bd_projects')}
        if 'owner_user_id' in bp_cols and 'created_by' in bp_cols:
            op.execute(sa.text(
                'UPDATE bd_projects SET owner_user_id = created_by '
                'WHERE owner_user_id IS NULL AND created_by IS NOT NULL'
            ))


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if 'users' in insp.get_table_names():
        cols = {c['name'] for c in insp.get_columns('users')}
        if 'access_sales_manager' in cols:
            op.drop_column('users', 'access_sales_manager')
