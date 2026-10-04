"""replace the full derivation key with ACTIVE-only uniqueness

Follows e7b4c0d21a95. Corrects a lifecycle the previous key could not represent. No column
is added, dropped or retyped; no enum changes; no row is read, written or deleted.

WHAT CHANGES
    dropped  UNIQUE (job_id, source_text_digest, requirement_type)
    added    UNIQUE INDEX (job_id, requirement_type) WHERE status = 'ACTIVE'

WHY
    A description that changes from A to B and later back to A must produce a *new* active
    derivation for A while the original A row stays invalidated — invalidation is terminal
    and no derived row is ever deleted. Under the old key the invalidated A row occupied the
    slot the new one needed, so the correct history was unrepresentable and the only ways
    out were deleting history or reviving a withdrawn verification.

    The replacement is also stricter where it matters. The old key permitted two ACTIVE rows
    for one requirement type under two digests; nothing but application code prevented it.

SQLITE IS THE CRITICAL PATH, AND NAIVE BATCH MODE IS UNSAFE HERE
    SQLite cannot drop a named constraint in place, so the table must be rebuilt. Alembic's
    batch mode rebuilds from **reflection** by default, and SQLite reflection does not round
    trip this table's multi-line typed-value CHECK: a naive rebuild was measured dropping
    ``ck_extracted_requirements_value_columns`` silently along with the intended constraint.
    That CHECK is what enforces D12's permanent exclusion of MIN_DEGREE_LEVEL and
    ALLOWED_FIELDS, so losing it would be a real weakening presented as a no-op.

    Both batch operations below therefore pass ``copy_from`` with an authoritative Table
    built in this module. The three ordinary indexes are attached to it so the rebuild
    recreates them rather than discarding them.

LITERAL CONSTANTS, NOT ENUM IMPORTS
    As in e7b4c0d21a95, b3e8d2c61a47 and c4f1a8b92d63: a migration describes the schema as it
    was at this revision, not as the application's enums happen to read later.

PORTABILITY (ADR-009)
    A partial unique index is supported by SQLite (since 3.8.0) and by PostgreSQL, and
    SQLAlchemy emits an identical statement for both. There is no dialect-neutral spelling,
    so the predicate is given for each; a third dialect would receive a **total** unique
    index, which is why the repository's two supported dialects are named explicitly here and
    asserted in the tests.

DOWNGRADE — IT CAN LEGITIMATELY REFUSE
    **The newer schema can represent histories the older one cannot.** After an A to B to A
    cycle the table holds two rows sharing a job, a digest and a requirement type: one
    invalidated, one active. Restoring the old key over those rows is impossible without
    destroying or merging derived history, and this migration will do neither.

    The downgrade therefore runs a **read-only preflight** before any DDL. If any duplicate
    of (job_id, source_text_digest, requirement_type) exists — at any status — it raises and
    stops: the ACTIVE-only index is still in place, the table is untouched, and the database
    remains on this revision. Nothing is deleted, nothing is reactivated, nothing is
    deduplicated. Resolving it is a data decision and belongs to an operator, not to a
    schema migration.

Revision ID: d5c2e9a1f7b4
Revises: e7b4c0d21a95
Create Date: 2026-10-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d5c2e9a1f7b4"
down_revision: Union[str, None] = "e7b4c0d21a95"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "extracted_requirements"

OLD_UNIQUE_CONSTRAINT = "uq_extracted_requirements_job_digest_type"
ACTIVE_UNIQUE_INDEX = "uq_extracted_requirements_one_active"

#: The index predicate, written out because a migration states the schema at this revision.
#: It must match ``ExtractionStatus.ACTIVE``'s stored value exactly; a predicate naming a
#: status that does not occur would create a unique index that constrains nothing.
ACTIVE_PREDICATE = "status = 'ACTIVE'"

#: Literal copies of the enum members as they stand at this revision.
REQUIREMENT_TYPES = (
    "MIN_CGPA",
    "GRAD_YEAR_WINDOW",
    "MAX_BACKLOGS",
    "MIN_DEGREE_LEVEL",
    "ALLOWED_FIELDS",
)
REQUIREMENT_PROVENANCES = ("SOURCE_STATED", "PROSE_DERIVED")
REQUIREMENT_STRENGTHS = ("REQUIRED", "PREFERRED", "CONDITIONAL", "INFORMATIONAL")
GRADE_SCALES = ("SCALE_4", "SCALE_5", "SCALE_10", "PERCENTAGE", "UNKNOWN")
EXTRACTION_STATUSES = ("ACTIVE", "INVALIDATED")

INDEXES = (
    ("ix_extracted_requirements_job_id", "job_id"),
    ("ix_extracted_requirements_source_text_digest", "source_text_digest"),
    ("ix_extracted_requirements_status", "status"),
)

VALUE_COLUMNS_MATCH_TYPE = """
(
    requirement_type = 'MIN_CGPA'
    AND min_cgpa IS NOT NULL AND min_cgpa_scale IS NOT NULL
    AND min_grad_year IS NULL AND max_grad_year IS NULL AND max_backlogs IS NULL
) OR (
    requirement_type = 'GRAD_YEAR_WINDOW'
    AND (min_grad_year IS NOT NULL OR max_grad_year IS NOT NULL)
    AND min_cgpa IS NULL AND min_cgpa_scale IS NULL AND max_backlogs IS NULL
) OR (
    requirement_type = 'MAX_BACKLOGS'
    AND max_backlogs IS NOT NULL
    AND min_cgpa IS NULL AND min_cgpa_scale IS NULL
    AND min_grad_year IS NULL AND max_grad_year IS NULL
)
"""

#: What the downgrade says when the data cannot fit the older schema. Stated as a constant so
#: the refusal is testable by its text rather than by catching a bare exception type.
DUPLICATE_HISTORY_ERROR = (
    f"Cannot downgrade {revision}: {TABLE} holds derived history the previous schema "
    "cannot represent."
)

#: Finds every (job, digest, type) group the restored key would reject. Read-only, and
#: ordinary SQL on both supported engines.
DUPLICATE_SCAN = sa.text(
    f"""
    SELECT COUNT(*) AS groups, COALESCE(SUM(n), 0) AS rows_involved
    FROM (
        SELECT COUNT(*) AS n
        FROM {TABLE}
        GROUP BY job_id, source_text_digest, requirement_type
        HAVING COUNT(*) > 1
    ) AS duplicated
    """
)


def _authoritative_table(*, with_old_unique: bool) -> sa.Table:
    """The table as it exists on one side of this revision, for ``copy_from``.

    Written out rather than reflected, because reflection is exactly what loses the
    multi-line typed-value CHECK on SQLite. ``with_old_unique`` selects which side: the
    upgrade copies from the table that still has the old constraint, the downgrade from the
    table that no longer does.

    The ordinary indexes are attached so a rebuild recreates them. The ACTIVE-only index is
    deliberately absent from both: the upgrade creates it after its rebuild, and the
    downgrade drops it before its own.
    """
    metadata = sa.MetaData()
    args: list[sa.schema.SchemaItem] = [
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("source_text_digest", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "requirement_type",
            sa.Enum(
                *REQUIREMENT_TYPES,
                name="requirementtype",
                native_enum=False,
                length=20,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "provenance",
            sa.Enum(
                *REQUIREMENT_PROVENANCES,
                name="requirementprovenance",
                native_enum=False,
                length=20,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "strength",
            sa.Enum(
                *REQUIREMENT_STRENGTHS,
                name="requirementstrength",
                native_enum=False,
                length=20,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("min_cgpa", sa.Float(), nullable=True),
        sa.Column(
            "min_cgpa_scale",
            sa.Enum(
                *GRADE_SCALES,
                name="gradescale",
                native_enum=False,
                length=20,
                create_constraint=True,
            ),
            nullable=True,
        ),
        sa.Column("min_grad_year", sa.Integer(), nullable=True),
        sa.Column("max_grad_year", sa.Integer(), nullable=True),
        sa.Column("max_backlogs", sa.Integer(), nullable=True),
        sa.Column("evidence_text", sa.Text(), nullable=False),
        sa.Column("extractor", sa.String(length=100), nullable=False),
        sa.Column("extractor_version", sa.String(length=50), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                *EXTRACTION_STATUSES,
                name="extractionstatus",
                native_enum=False,
                length=20,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "provenance = 'PROSE_DERIVED'",
            name="ck_extracted_requirements_provenance_derived",
        ),
        sa.CheckConstraint(
            "strength = 'REQUIRED'",
            name="ck_extracted_requirements_strength_required",
        ),
        sa.CheckConstraint(
            "min_cgpa_scale IS NULL OR min_cgpa_scale <> 'UNKNOWN'",
            name="ck_extracted_requirements_scale_known",
        ),
        sa.CheckConstraint(
            VALUE_COLUMNS_MATCH_TYPE, name="ck_extracted_requirements_value_columns"
        ),
    ]
    if with_old_unique:
        args.append(
            sa.UniqueConstraint(
                "job_id",
                "source_text_digest",
                "requirement_type",
                name=OLD_UNIQUE_CONSTRAINT,
            )
        )
    args.extend(sa.Index(name, column) for name, column in INDEXES)
    return sa.Table(TABLE, metadata, *args)


def upgrade() -> None:
    """Drop the full key, add the ACTIVE-only partial unique index."""
    with op.batch_alter_table(
        TABLE, schema=None, copy_from=_authoritative_table(with_old_unique=True)
    ) as batch_op:
        batch_op.drop_constraint(OLD_UNIQUE_CONSTRAINT, type_="unique")

    # Created outside the rebuild, with the predicate stated for each supported dialect.
    # A dialect matching neither would receive a total unique index; ADR-009 names these two.
    op.create_index(
        ACTIVE_UNIQUE_INDEX,
        TABLE,
        ["job_id", "requirement_type"],
        unique=True,
        sqlite_where=sa.text(ACTIVE_PREDICATE),
        postgresql_where=sa.text(ACTIVE_PREDICATE),
    )


def downgrade() -> None:
    """Restore the full key — but only when the stored history can still fit inside it.

    The preflight runs **first and reads only**. If it finds anything the older key would
    reject, it raises before the partial index is dropped and before the table is touched, so
    a refused downgrade leaves the database exactly as it was, still on this revision.
    """
    bind = op.get_bind()
    groups, rows_involved = bind.execute(DUPLICATE_SCAN).one()

    if groups:
        raise RuntimeError(
            f"{DUPLICATE_HISTORY_ERROR}\n"
            f"  {groups} (job_id, source_text_digest, requirement_type) group(s) hold "
            f"more than one row, {rows_involved} rows in total.\n"
            "  This is valid under the current schema: a description that changed away and "
            "back produces a new active derivation beside the invalidated one.\n"
            "  The previous schema's UNIQUE "
            "(job_id, source_text_digest, requirement_type) cannot hold them, and this "
            "migration will not delete, merge or reactivate derived rows to make room.\n"
            "  Nothing has been changed. To inspect the affected rows:\n"
            f"    SELECT job_id, source_text_digest, requirement_type, COUNT(*) FROM {TABLE}"
            " GROUP BY 1, 2, 3 HAVING COUNT(*) > 1;"
        )

    op.drop_index(ACTIVE_UNIQUE_INDEX, table_name=TABLE)

    with op.batch_alter_table(
        TABLE, schema=None, copy_from=_authoritative_table(with_old_unique=False)
    ) as batch_op:
        batch_op.create_unique_constraint(
            OLD_UNIQUE_CONSTRAINT,
            ["job_id", "source_text_digest", "requirement_type"],
        )
