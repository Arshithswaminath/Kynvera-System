"""Baseline revision — schema already exists via models / legacy inline DDL.

Revision ID: 20260720_baseline
Revises:
Create Date: 2026-07-20

Stamp existing databases with: flask db stamp head
Then enable FLASK_SKIP_INLINE_DDL=1 and add real migrations for new changes.
"""
from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401

revision = '20260720_baseline'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # No-op baseline: current production schema is the source of truth.
    pass


def downgrade():
    pass
