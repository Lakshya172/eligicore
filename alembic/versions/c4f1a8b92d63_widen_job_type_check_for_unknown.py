"""widen the job_type CHECK constraint to admit UNKNOWN

Follows b3e8d2c61a47. Constraint-only: no column is added, dropped or retyped, and no row
is read or written by the upgrade.

WHY
    ADR-029 adds ``JobType.UNKNOWN``, meaning *the source did not explicitly provide the
    employment type*. The blocker it resolves is concrete: the Greenhouse Job Board API
    publishes no employment-type field, so an adapter could only infer one, fabricate one,
    or fail — all three forbidden by ADR-028 D9.

    ``jobs.job_type`` is already ``VARCHAR(20) NOT NULL``, so ``'UNKNOWN'`` (7 characters)
    needs no type change. The only work is the CHECK constraint that 7c2f1a9b4d30 created
    as ``job_type IN ('INTERNSHIP', 'FULL_TIME')``.

WHY NOT AMEND AN EARLIER MIGRATION
    7c2f1a9b4d30 is merged. Amending it would give already-migrated databases a different
    schema from fresh ones under the same revision id.

NO BACKFILL
    The upgrade is a **strict widening**: every value that satisfied the old predicate
    satisfies the new one. All 40 curated jobs state a real type and keep it. ``UNKNOWN``
    exists for genuinely missing source data arriving later from a live adapter, and no
    existing row is converted to it (ADR-029 D11).

DOWNGRADE REFUSES RATHER THAN GUESSING (ADR-029 D16, OD-3)
    Narrowing the constraint back to two values is only valid if no row holds ``'UNKNOWN'``
    — and the entire purpose of this migration is to put such rows there.

    * **PostgreSQL** validates existing rows on ``ADD CONSTRAINT`` and would raise.
    * **SQLite** recreates the table through batch mode and copies rows into one carrying
      the narrowed CHECK, which either raises or leaves a table contradicting its own
      constraint.

    Neither failure is acceptable as a rollback path, and the two alternatives are worse:
    deleting the rows contradicts ADR-006/ADR-014's "jobs are closed, never deleted", and
    remapping them to a real type is fabrication (ADR-029 D2, D3). So the downgrade
    **counts first and refuses**, before issuing any DDL, leaving every row untouched and
    the schema exactly as it was.

    The error carries **only the count** — never a job id, title, company or any other row
    content (INV-4).

PORTABILITY (ADR-009)
    ``batch_alter_table`` is required for SQLite, which cannot ``ALTER TABLE ... DROP
    CONSTRAINT`` and must recreate the table. On PostgreSQL it falls through to plain
    ``ALTER TABLE ... DROP CONSTRAINT`` / ``ADD CONSTRAINT``.

Revision ID: c4f1a8b92d63
Revises: b3e8d2c61a47
Create Date: 2026-10-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4f1a8b92d63"
down_revision: Union[str, None] = "b3e8d2c61a47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: The constraint name 7c2f1a9b4d30 created. Dropping and recreating it under the same name
#: keeps the schema stable for anything that inspects constraints by name.
CONSTRAINT_NAME = "jobtype"

#: Literal copies, not imports of ``app.schemas.candidate.JobType``. A migration must
#: describe the schema as it was at this revision, not as the enum happens to read later —
#: the same rule b3e8d2c61a47 states for ``DegreeLevel``.
JOB_TYPES_BEFORE = ("INTERNSHIP", "FULL_TIME")
JOB_TYPES_AFTER = ("INTERNSHIP", "FULL_TIME", "UNKNOWN")


def _in_clause(column: str, values: tuple[str, ...]) -> str:
    """Render an IN predicate with quoted literals.

    The values are module-level constants mirroring a Python enum, never user input. Same
    helper shape as 7c2f1a9b4d30, deliberately.
    """
    rendered = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({rendered})"


def _count_unknown_rows() -> int:
    """How many stored jobs hold ``'UNKNOWN'``.

    Read-only, and executed **before** any DDL so a refusal cannot leave a half-rewritten
    table behind.
    """
    result = op.get_bind().execute(
        sa.text("SELECT COUNT(*) FROM jobs WHERE job_type = :value"),
        {"value": "UNKNOWN"},
    )
    return int(result.scalar_one())


def _replace_job_type_check(values: tuple[str, ...]) -> None:
    """Swap the ``jobtype`` CHECK for one admitting exactly ``values``."""
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_constraint(CONSTRAINT_NAME, type_="check")
        batch_op.create_check_constraint(
            CONSTRAINT_NAME, _in_clause("job_type", values)
        )


def upgrade() -> None:
    """Admit ``'UNKNOWN'`` alongside the two known types. No row is read or written."""
    _replace_job_type_check(JOB_TYPES_AFTER)


def downgrade() -> None:
    """Narrow back to the two known types, refusing if any ``UNKNOWN`` row exists.

    Raises:
        RuntimeError: One or more jobs hold ``'UNKNOWN'``. **No DDL has run at that point**
            and no row is modified, so the database is left exactly as it was and the
            operator can resolve the rows and retry. The message carries only a count.
    """
    unknown_rows = _count_unknown_rows()
    if unknown_rows:
        raise RuntimeError(
            f"Refusing to downgrade: {unknown_rows} job(s) have job_type='UNKNOWN', which "
            f"the two-value CHECK constraint this downgrade restores would reject. "
            f"No schema or row was modified. Resolve those rows deliberately before "
            f"retrying — this migration will not delete, convert or reinterpret them "
            f"(ADR-029 D16)."
        )

    _replace_job_type_check(JOB_TYPES_BEFORE)
