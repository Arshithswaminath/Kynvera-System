"""HR Hiring Document Tracker: hiring_candidates + hiring_documents.

Revision ID: 20260729_hiring
Revises: 20260723_meeting2
Create Date: 2026-07-29
"""
from alembic import op
import sqlalchemy as sa


revision = '20260729_hiring'
down_revision = '20260723_meeting2'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if 'hiring_candidates' not in tables:
        op.create_table(
            'hiring_candidates',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('full_name', sa.String(200), nullable=False),
            sa.Column('role', sa.String(120), nullable=True),
            sa.Column('department', sa.String(120), nullable=True),
            sa.Column('phone', sa.String(40), nullable=True),
            sa.Column('email', sa.String(120), nullable=True),
            sa.Column('replacement_name', sa.String(200), nullable=True),
            sa.Column('replacement_employee_id', sa.String(80), nullable=True),
            sa.Column('comments', sa.Text(), nullable=True),
            sa.Column('pipeline_status', sa.String(40), nullable=True),
            sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
        )
        op.create_index('ix_hiring_candidates_full_name', 'hiring_candidates', ['full_name'])
        op.create_index('ix_hiring_candidates_pipeline_status', 'hiring_candidates', ['pipeline_status'])
        op.create_index('ix_hiring_candidates_created_at', 'hiring_candidates', ['created_at'])
        op.create_index('ix_hiring_candidates_updated_at', 'hiring_candidates', ['updated_at'])

    tables = set(sa.inspect(bind).get_table_names())
    if 'hiring_documents' not in tables:
        op.create_table(
            'hiring_documents',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column(
                'candidate_id',
                sa.Integer(),
                sa.ForeignKey('hiring_candidates.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column('doc_type', sa.String(40), nullable=False),
            sa.Column('filename', sa.String(255), nullable=True),
            sa.Column('file_path', sa.String(500), nullable=True),
            sa.Column('cloud_url', sa.String(500), nullable=True),
            sa.Column('mime_type', sa.String(100), nullable=True),
            sa.Column('file_size', sa.Integer(), nullable=True),
            sa.Column('status', sa.String(20), nullable=True),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('uploaded_at', sa.DateTime(), nullable=True),
            sa.Column('uploaded_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
            sa.UniqueConstraint('candidate_id', 'doc_type', name='uq_hiring_candidate_doc_type'),
        )
        op.create_index('ix_hiring_documents_candidate_id', 'hiring_documents', ['candidate_id'])
        op.create_index('ix_hiring_documents_doc_type', 'hiring_documents', ['doc_type'])
        op.create_index('ix_hiring_documents_status', 'hiring_documents', ['status'])

    # Existing installs: add notes if table already created without it
    tables = set(sa.inspect(bind).get_table_names())
    if 'hiring_documents' in tables:
        cols = {c['name'] for c in sa.inspect(bind).get_columns('hiring_documents')}
        if 'notes' not in cols:
            op.add_column('hiring_documents', sa.Column('notes', sa.Text(), nullable=True))


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())
    if 'hiring_documents' in tables:
        op.drop_table('hiring_documents')
    if 'hiring_candidates' in tables:
        op.drop_table('hiring_candidates')
