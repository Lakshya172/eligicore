"""create jobs and ingestion_state operational tables

The first migration in this project. It creates the entire server-side schema.

WHAT THIS CREATES
    jobs             the job catalogue (dossier §10.2)
    ingestion_state  one row per source, current state only (ADR-015)

WHAT THIS DELIBERATELY DOES NOT CREATE
    No candidates, applications or evaluations table. No table holding profiles,
    resumes, results or application records. Candidate data is in-flight only
    (INV-1, ADR-011). The dossier §8.2 folder listing that suggests otherwise is
    stale.

PORTABILITY (ADR-009 — SQLite in development, PostgreSQL in production)
    Enums use native_enum=False with create_constraint=True, so they are VARCHAR plus a
    CHECK constraint on both engines rather than a PostgreSQL native type that SQLite
    cannot express. create_constraint is NOT the SQLAlchemy 2.0 default: without it the
    column is a bare VARCHAR and the database accepts any string, which would make the
    four-state job status (ADR-014) a convention rather than a guarantee.
    Index creation runs inside batch_alter_table, which SQLite requires.
    JSON columns map to JSON on PostgreSQL and TEXT on SQLite via SQLAlchemy.

    The unique constraint on (source, source_job_id) permits many NULL source_job_id
    rows: both engines treat NULLs as distinct in a unique constraint. That is
    intended — it is the exact-match fast path for sources that publish stable ids,
    and sources without ids fall through to content_hash matching.

Revision ID: 54a85d64881e
Revises:
Create Date: 2026-09-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '54a85d64881e'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the operational tables."""
    op.create_table('ingestion_state',
    sa.Column('source', sa.String(length=100), nullable=False),
    sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_status', sa.Enum('SUCCESS', 'PARTIAL', 'FAILED', name='ingestionstatus', native_enum=False, length=20, create_constraint=True), nullable=False),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('jobs_seen', sa.Integer(), nullable=False),
    sa.Column('jobs_created', sa.Integer(), nullable=False),
    sa.Column('jobs_updated', sa.Integer(), nullable=False),
    sa.Column('jobs_unchanged', sa.Integer(), nullable=False),
    sa.Column('jobs_deactivated', sa.Integer(), nullable=False),
    sa.Column('cursor', sa.String(length=500), nullable=True),
    sa.PrimaryKeyConstraint('source')
    )
    op.create_table('jobs',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('company_name', sa.String(length=300), nullable=False),
    sa.Column('role_title', sa.String(length=300), nullable=False),
    sa.Column('job_type', sa.Enum('INTERNSHIP', 'FULL_TIME', name='jobtype', native_enum=False, length=20, create_constraint=True), nullable=False),
    sa.Column('location', sa.String(length=300), nullable=True),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('requirements', sa.JSON(), nullable=False),
    sa.Column('min_cgpa', sa.Float(), nullable=True),
    sa.Column('min_cgpa_scale', sa.String(length=20), nullable=True),
    sa.Column('allowed_fields', sa.JSON(), nullable=False),
    sa.Column('max_backlogs', sa.Integer(), nullable=True),
    sa.Column('min_grad_year', sa.Integer(), nullable=True),
    sa.Column('max_grad_year', sa.Integer(), nullable=True),
    sa.Column('required_skills', sa.JSON(), nullable=False),
    sa.Column('apply_link', sa.String(length=2000), nullable=True),
    sa.Column('deadline', sa.Date(), nullable=True),
    sa.Column('source', sa.String(length=100), nullable=False),
    sa.Column('source_job_id', sa.String(length=200), nullable=True),
    sa.Column('content_hash', sa.String(length=64), nullable=False),
    sa.Column('status', sa.Enum('ACTIVE', 'EXPIRED', 'CLOSED', 'UNKNOWN', name='jobstatus', native_enum=False, length=20, create_constraint=True), nullable=False),
    sa.Column('last_verified_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source', 'source_job_id', name='uq_jobs_source_source_job_id')
    )
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.create_index('ix_jobs_content_hash', ['content_hash'], unique=False)
        batch_op.create_index('ix_jobs_job_type', ['job_type'], unique=False)
        batch_op.create_index('ix_jobs_source', ['source'], unique=False)
        batch_op.create_index('ix_jobs_status', ['status'], unique=False)



def downgrade() -> None:
    """Drop the operational tables. No data migration needed — no personal data here."""
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.drop_index('ix_jobs_status')
        batch_op.drop_index('ix_jobs_source')
        batch_op.drop_index('ix_jobs_job_type')
        batch_op.drop_index('ix_jobs_content_hash')

    op.drop_table('jobs')
    op.drop_table('ingestion_state')
