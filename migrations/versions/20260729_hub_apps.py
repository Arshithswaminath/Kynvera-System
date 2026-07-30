"""Add users.access_fire_app and users.access_municipality_app for Kynvera Hub.

Revision ID: 20260729_hub_apps
Revises: 20260729_hiring
Create Date: 2026-07-29
"""
from alembic import op
import sqlalchemy as sa


revision = '20260729_hub_apps'
down_revision = '20260729_hiring'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if 'users' not in insp.get_table_names():
        return
    cols = {c['name'] for c in insp.get_columns('users')}
    if 'access_fire_app' not in cols:
        op.add_column(
            'users',
            sa.Column('access_fire_app', sa.Boolean(), nullable=True, server_default=sa.false()),
        )
    if 'access_municipality_app' not in cols:
        op.add_column(
            'users',
            sa.Column('access_municipality_app', sa.Boolean(), nullable=True, server_default=sa.false()),
        )


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if 'users' not in insp.get_table_names():
        return
    cols = {c['name'] for c in insp.get_columns('users')}
    if 'access_municipality_app' in cols:
        op.drop_column('users', 'access_municipality_app')
    if 'access_fire_app' in cols:
        op.drop_column('users', 'access_fire_app')
