"""create the extracted_requirements operational table

Follows c4f1a8b92d63. Additive: one new table, no existing table is read, written or
altered, and no row anywhere is touched.

WHAT THIS CREATES
    extracted_requirements  verified prose-derived job requirements (ADR-030 D16-D19)

WHAT THIS DELIBERATELY DOES NOT CREATE
    No candidate, application or evaluation table, and no candidate column anywhere. This
    table records what a JOB POSTING says. Extraction runs at ingestion time from job text
    alone and never sees a candidate (ADR-030 D21, D24; INV-1, ADR-011).

WHY A SEPARATE TABLE RATHER THAN COLUMNS ON jobs (ADR-030 D16)
    Two hazards in the merged code make this mandatory rather than stylistic.

    ``jobs.requirements`` participates in ``compute_content_hash``. A derived value written
    there changes the hash, so the job presents as changed on the next ingestion, which
    triggers re-extraction, which changes the hash again — a self-sustaining loop.

    ``_apply_updates`` copies every source-owned requirement column from the adapter on
    every run, and a live adapter supplies ``None`` for all of them, so a derived value
    written into ``min_cgpa`` or any sibling is erased on the next ingestion. That hazard is
    the broader of the two: it applies to the typed columns as well as to ``requirements``.

WHY source_text_digest RATHER THAN content_hash AS THE STALENESS KEY
    ``compute_content_hash`` canonicalizes the description before hashing — lowercasing and
    stripping punctuation — so two descriptions differing only in punctuation or case hash
    identically while storing differently. A derived row keyed on ``content_hash`` alone
    could look current while its evidence no longer occurs in the stored text.
    ``source_text_digest`` is SHA-256 over ``jobs.description`` exactly as stored, and
    ``content_hash`` is kept beside it as correlation only.

FOREIGN KEY, AND WHAT DOES NOT DEPEND ON IT
    ``job_id`` references ``jobs.id`` with ``ON DELETE CASCADE``. This is the project's first
    foreign key. It is correct and enforced on PostgreSQL; **SQLite does not enforce foreign
    keys without** ``PRAGMA foreign_keys=ON``, which this project does not set and which this
    migration deliberately does not introduce — turning it on globally is its own decision.
    Nothing depends on the cascade: jobs are closed, never deleted (ADR-006, ADR-014), so no
    path exercises it today.

CONSTRAINTS THAT ENCODE DECISIONS RATHER THAN TYPES
    provenance = 'PROSE_DERIVED'   a source-stated requirement lives in a jobs column by
                                   definition (D1) and has no extraction path
    strength   = 'REQUIRED'        only REQUIRED satisfies D6 condition 7; a PREFERRED or
                                   CONDITIONAL statement gating eligibility becomes a
                                   constraint violation rather than a code defect (D10)
    scale <> 'UNKNOWN'             a grade with no scale is comparable to nothing
    value columns match type       exactly one branch per Phase 1 requirement type, and
                                   **exhaustive by omission**: MIN_DEGREE_LEVEL and
                                   ALLOWED_FIELDS are real RequirementType members that the
                                   column's own enum check admits, so without this they
                                   could be stored. D12 excludes both permanently.

LITERAL CONSTANTS, NOT ENUM IMPORTS
    The enum members below are written out rather than imported from
    ``app.schemas`` / ``app.models``. A migration must describe the schema as it was at this
    revision, not as the enum happens to read later — the same rule b3e8d2c61a47 states for
    ``DegreeLevel`` and c4f1a8b92d63 for ``JobType``.

PORTABILITY (ADR-009)
    ``native_enum=False`` so every enum is VARCHAR plus a CHECK on both engines rather than
    a PostgreSQL native type SQLite cannot express. Index creation runs inside
    ``batch_alter_table``, which SQLite requires, exactly as 54a85d64881e does.

DOWNGRADE
    Drops the indexes and then the table, and nothing else. The table is created empty by
    this revision and holds only derived data that can be recomputed from the job text, so
    there is nothing to preserve and no refusal to make — unlike c4f1a8b92d63, whose
    downgrade would have had to destroy or reinterpret real source data.

Revision ID: e7b4c0d21a95
Revises: c4f1a8b92d63
Create Date: 2026-10-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e7b4c0d21a95"
down_revision: Union[str, None] = "c4f1a8b92d63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "extracted_requirements"

#: Literal copies of the enum members as they stand at this revision. See the module
#: docstring on why these are not imported.
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

#: One branch per Phase 1 requirement type. Each names the columns that must be populated
#: and requires every unrelated typed column to stay NULL.
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


def upgrade() -> None:
    """Create the table, its constraints and its indexes. No existing object is touched."""
    op.create_table(
        TABLE,
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
        sa.UniqueConstraint(
            "job_id",
            "source_text_digest",
            "requirement_type",
            name="uq_extracted_requirements_job_digest_type",
        ),
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
    )

    with op.batch_alter_table(TABLE, schema=None) as batch_op:
        for name, column in INDEXES:
            batch_op.create_index(name, [column], unique=False)


def downgrade() -> None:
    """Drop the indexes and the table. Nothing else this revision did needs undoing."""
    with op.batch_alter_table(TABLE, schema=None) as batch_op:
        for name, _ in reversed(INDEXES):
            batch_op.drop_index(name)

    op.drop_table(TABLE)
