"""add min_degree_level to jobs

Follows 7c2f1a9b4d30. Additive only: one nullable column plus its CHECK constraint.

WHY
    Dossier §12.1 and §17 name degree level as a deterministic hard constraint, but the
    §10.2 ``jobs`` table had no field for a job to state one (contradiction C-10). Ruled in
    ADR-018: a typed, nullable column using the existing ``DegreeLevel`` members.

    Nullable because absence carries meaning — a posting that states no level has no degree
    requirement. Existing rows need no backfill: NULL is exactly what they state.

WHY NOT AMEND AN EARLIER MIGRATION
    54a85d64881e and 7c2f1a9b4d30 are merged. Amending either would give already-migrated
    databases a different schema from fresh ones under the same revision id (memory D-21).

CHECK CONSTRAINT
    Declared explicitly, as 7c2f1a9b4d30 does for the other enums. SQLAlchemy 2.0 defaults
    ``create_constraint=False`` and ``alembic check`` does not detect CHECK constraints, so
    the model and this migration must both state it or the column silently accepts any
    string (memory D-20).

PORTABILITY (ADR-009)
    ``batch_alter_table`` for SQLite, which cannot ADD CONSTRAINT; on PostgreSQL it falls
    through to plain ALTER TABLE statements.

Revision ID: b3e8d2c61a47
Revises: 7c2f1a9b4d30
Create Date: 2026-09-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b3e8d2c61a47"
down_revision: Union[str, None] = "7c2f1a9b4d30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: Mirrors ``app.schemas.candidate.DegreeLevel``. A literal copy, not an import: a migration
#: must describe the schema as it was at this revision, not as the enum reads later.
DEGREE_LEVELS = (
    "HIGH_SCHOOL",
    "DIPLOMA",
    "BACHELORS",
    "MASTERS",
    "DOCTORATE",
    "OTHER",
    "UNKNOWN",
)


def upgrade() -> None:
    """Add the nullable degree-level requirement column, constrained to DegreeLevel."""
    rendered = ", ".join(f"'{value}'" for value in DEGREE_LEVELS)
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "min_degree_level",
                sa.Enum(
                    *DEGREE_LEVELS,
                    name="degreelevel",
                    native_enum=False,
                    length=20,
                ),
                nullable=True,
            )
        )
        batch_op.create_check_constraint(
            "degreelevel", f"min_degree_level IN ({rendered})"
        )


def downgrade() -> None:
    """Drop the constraint, then the column."""
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_constraint("degreelevel", type_="check")
        batch_op.drop_column("min_degree_level")
