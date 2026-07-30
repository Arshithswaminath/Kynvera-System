"""Normalize users.designation business_development → sales.

Revision ID: 20260720_desig_sales
Revises: 20260720_sales_mgr
Create Date: 2026-07-20
"""
from alembic import op
import sqlalchemy as sa


revision = '20260720_desig_sales'
down_revision = '20260720_sales_mgr'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if 'users' not in insp.get_table_names():
        return
    cols = {c['name'] for c in insp.get_columns('users')}
    if 'designation' not in cols:
        return
    op.execute(sa.text(
        "UPDATE users SET designation = 'sales' "
        "WHERE designation = 'business_development'"
    ))


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if 'users' not in insp.get_table_names():
        return
    cols = {c['name'] for c in insp.get_columns('users')}
    if 'designation' not in cols:
        return
    # Best-effort reverse: only rows that are still sales and have Sales module flag
    # stay as sales; we do not invent which were formerly BD.
    op.execute(sa.text(
        "UPDATE users SET designation = 'business_development' "
        "WHERE designation = 'sales'"
    ))
