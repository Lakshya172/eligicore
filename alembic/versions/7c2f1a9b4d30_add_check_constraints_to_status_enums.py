"""add CHECK constraints to status enums

Follows 54a85d64881e, which created the tables with plain VARCHAR status columns.

WHY THIS IS A SEPARATE MIGRATION
    SQLAlchemy 2.0 defaults ``create_constraint=False``, so ``Enum(native_enum=False)``
    emits a bare VARCHAR. Verified directly against the database created by
    54a85d64881e: ``status='NOT_A_STATE'`` was accepted without complaint.

    That made the canonical four-state job status (ADR-014) a convention rather than a
    guarantee. A future write path storing an invalid value would not surface until read
    time, by which point the catalogue is already wrong.

    The obvious fix is to amend 54a85d64881e in place. That is wrong now that it has been
    merged: any database that already ran it is stamped at that revision and would never
    receive the constraints, while a fresh database would silently get a different schema
    from the same revision id. Two databases claiming the same revision with different
    schemas is exactly the failure Alembic exists to prevent.

    A separate migration is correct for both cases — a fresh database runs both, an
    already-migrated one runs this alone, and both end up identical.

PORTABILITY (ADR-009)
    ``batch_alter_table`` is required for SQLite, which cannot ADD CONSTRAINT and must
    recreate the table instead. On PostgreSQL, batch mode falls through to a plain
    ALTER TABLE ... ADD CONSTRAINT.

Revision ID: 7c2f1a9b4d30
Revises: 54a85d64881e
Create Date: 2026-09-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "7c2f1a9b4d30"
down_revision: Union[str, None] = "54a85d64881e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JOB_STATUSES = ("ACTIVE", "EXPIRED", "CLOSED", "UNKNOWN")
JOB_TYPES = ("INTERNSHIP", "FULL_TIME")
INGESTION_STATUSES = ("SUCCESS", "PARTIAL", "FAILED")


def _in_clause(column: str, values: tuple[str, ...]) -> str:
    """Render an IN predicate with quoted literals.

    The values are module-level constants mirroring Python enums, never user input.
    """
    rendered = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({rendered})"


def upgrade() -> None:
    """Constrain the enum columns to their declared members."""
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.create_check_constraint("jobstatus", _in_clause("status", JOB_STATUSES))
        batch_op.create_check_constraint("jobtype", _in_clause("job_type", JOB_TYPES))

    with op.batch_alter_table("ingestion_state", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "ingestionstatus", _in_clause("last_status", INGESTION_STATUSES)
        )


def downgrade() -> None:
    """Drop the CHECK constraints, returning the columns to plain VARCHAR."""
    with op.batch_alter_table("ingestion_state", schema=None) as batch_op:
        batch_op.drop_constraint("ingestionstatus", type_="check")

    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_constraint("jobtype", type_="check")
        batch_op.drop_constraint("jobstatus", type_="check")
