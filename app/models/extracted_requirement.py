"""Verified prose-derived job requirements — operational data (ADR-030 D16-D19).

╔══════════════════════════════════════════════════════════════════════════════════════╗
║  This table records what a JOB POSTING says, never anything about a PERSON.          ║
║                                                                                       ║
║  It must never gain a ``candidate_id``, a profile, resume text, an evaluation, an    ║
║  application record or a match score. Extraction runs at ingestion time, from job    ║
║  text alone, and never sees a candidate (ADR-030 D21, D24; INV-1, ADR-011).          ║
║  ``evidence_text`` is a fragment of the public posting and nothing else.             ║
╚══════════════════════════════════════════════════════════════════════════════════════╝

A row here is a requirement the employer stated **in prose** and that passed all eight
conditions of ADR-030 D6. Two properties make it safe to keep it in its own table rather
than in ``jobs``, and both were found by inspection at the design gate (D16):

* ``jobs.requirements`` participates in ``compute_content_hash``. A derived value written
  there changes the hash, so the job presents as changed on the next ingestion, which
  triggers re-extraction, which changes the hash again — a self-sustaining loop.
* ``_apply_updates`` copies every source-owned requirement column from the adapter on every
  run, and a live adapter supplies ``None`` for all of them. A derived value written into
  ``min_cgpa`` or any sibling is **erased** on the next ingestion.

Nothing in this module is read by the eligibility engine. Supplying derived requirements to
evaluation is a separate decision (D20) with its own implementation; so is extracting them
(D11) and orchestrating that at ingestion time (D21). This is storage, and only storage.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.schemas.candidate import GradeScale
from app.schemas.eligibility import RequirementType
from app.schemas.extraction import RequirementProvenance, RequirementStrength


class ExtractionStatus(str, enum.Enum):
    """Whether a stored derivation still applies. Exactly two states, and no more.

    ``SUPERSEDED`` is deliberately absent. The unique constraint keys a row to one exact
    pinned text, so re-extracting the same text updates that row in place and a changed text
    writes a new row under a new digest — there is never a second live row for one
    ``(job, requirement type)`` pair to supersede. Adding the member would require widening
    the unique key, which would in turn permit two ``ACTIVE`` rows for one requirement type:
    exactly the ambiguity the key exists to prevent.
    """

    #: Current for the pinned description named by ``source_text_digest``.
    ACTIVE = "ACTIVE"

    #: No longer describes the job's current pinned text, or withdrawn by an operator.
    #: **Terminal.** Nothing in this module moves a row back (see :meth:`invalidate`).
    INVALIDATED = "INVALIDATED"


def _utcnow() -> datetime:
    """Timezone-aware UTC now, as for every other operational model."""
    return datetime.now(timezone.utc)


#: Exactly one branch per Phase 1 requirement type, each naming the columns that must be
#: populated and requiring every unrelated typed column to stay ``NULL`` (ADR-030 D11).
#:
#: The disjunction is **exhaustive by omission**, and that is the point: ``MIN_DEGREE_LEVEL``
#: and ``ALLOWED_FIELDS`` are real :class:`~app.schemas.eligibility.RequirementType` members
#: that the column's own enum check admits, so without this they could be stored. D12
#: excludes degree-level mapping and field ontology from extraction permanently, and a row
#: for either satisfies no branch here and is rejected by the database rather than by a
#: convention someone has to remember.
_VALUE_COLUMNS_MATCH_TYPE = """
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


class ExtractedRequirement(Base):
    """One verified derived requirement, for one job, derived from one exact description."""

    __tablename__ = "extracted_requirements"
    __table_args__ = (
        # At most one derivation per requirement type per exact pinned text. Re-extracting
        # the same text updates in place; a changed description produces a new digest and
        # therefore a new row, so invalidation is a join rather than bookkeeping (D19).
        UniqueConstraint(
            "job_id",
            "source_text_digest",
            "requirement_type",
            name="uq_extracted_requirements_job_digest_type",
        ),
        # A source-stated requirement lives in a ``jobs`` column by definition (D1) and has
        # no extraction path. Nothing here may claim one.
        CheckConstraint(
            "provenance = 'PROSE_DERIVED'",
            name="ck_extracted_requirements_provenance_derived",
        ),
        # Only ``REQUIRED`` satisfies D6 condition 7, and only a verified requirement is
        # stored at all. A `PREFERRED` or `CONDITIONAL` statement gating eligibility is thus
        # a constraint violation rather than a code defect (D10, OD-5).
        CheckConstraint(
            "strength = 'REQUIRED'", name="ck_extracted_requirements_strength_required"
        ),
        # A grade whose scale is unknown is not comparable to anything, so the verifier never
        # produces one. Storing the rule keeps it true of rows written by any future path.
        CheckConstraint(
            "min_cgpa_scale IS NULL OR min_cgpa_scale <> 'UNKNOWN'",
            name="ck_extracted_requirements_scale_known",
        ),
        CheckConstraint(
            _VALUE_COLUMNS_MATCH_TYPE, name="ck_extracted_requirements_value_columns"
        ),
        Index("ix_extracted_requirements_job_id", "job_id"),
        Index("ix_extracted_requirements_source_text_digest", "source_text_digest"),
        Index("ix_extracted_requirements_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # --- what it was derived from ------------------------------------------------------
    #: The job this was read out of. ``ON DELETE CASCADE`` is declared for correctness on
    #: PostgreSQL; **nothing depends on it.** SQLite does not enforce foreign keys without
    #: ``PRAGMA foreign_keys=ON``, which this project does not set, and jobs are closed
    #: rather than deleted (ADR-006, ADR-014), so no path exercises the cascade today.
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    #: SHA-256 of ``jobs.description`` **as stored** — the pinned normalized text (D9).
    #:
    #: This is the staleness key, and it is deliberately not ``content_hash``.
    #: ``compute_content_hash`` canonicalizes the description before hashing it, lowercasing
    #: and stripping punctuation, so two descriptions differing only in punctuation or case
    #: hash identically while storing differently. A row keyed on ``content_hash`` alone
    #: could therefore look current while its evidence no longer occurs in the text.
    source_text_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    #: The job's ``content_hash`` at derivation time. Correlation and churn only — it is
    #: never the staleness key, and this table is never an input to the hash itself (D17).
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # --- the requirement ---------------------------------------------------------------
    requirement_type: Mapped[RequirementType] = mapped_column(
        SAEnum(RequirementType, native_enum=False, length=20, create_constraint=True),
        nullable=False,
    )
    #: Always ``PROSE_DERIVED``, enforced by check. Stored rather than implied because D1 is
    #: a two-class rule, and a column a reader must infer is a column a later writer guesses.
    provenance: Mapped[RequirementProvenance] = mapped_column(
        SAEnum(RequirementProvenance, native_enum=False, length=20, create_constraint=True),
        nullable=False,
        default=RequirementProvenance.PROSE_DERIVED,
    )
    #: Always ``REQUIRED``, enforced by check. Non-``REQUIRED`` observations are discarded by
    #: the verifier and are not retained anywhere — retention is not promotion, and Phase 1
    #: does neither (D10).
    strength: Mapped[RequirementStrength] = mapped_column(
        SAEnum(RequirementStrength, native_enum=False, length=20, create_constraint=True),
        nullable=False,
        default=RequirementStrength.REQUIRED,
    )

    # --- typed values: exactly the three Phase 1 criteria (D11) -------------------------
    min_cgpa: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_cgpa_scale: Mapped[GradeScale | None] = mapped_column(
        SAEnum(GradeScale, native_enum=False, length=20, create_constraint=True),
        nullable=True,
    )
    min_grad_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_grad_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_backlogs: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # --- provenance of the derivation (D18) ---------------------------------------------
    #: The verified supporting text, verbatim from the pinned description.
    #:
    #: **No character offsets, deliberately.** An offset is valid only against one exact
    #: normalized string, and a re-normalization or a source edit invalidates it silently.
    #: Evidence text is what is kept (D9, OD-3).
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    extractor: Mapped[str] = mapped_column(String(100), nullable=False)
    #: Separate from ``extractor`` so a stale derivation is detectable by comparison rather
    #: than by parsing a name (D22's version-triggered re-extraction).
    extractor_version: Mapped[str] = mapped_column(String(50), nullable=False)
    #: Null on the Phase 1 deterministic path, which uses no provider and no model.
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    # --- lifecycle ----------------------------------------------------------------------
    status: Mapped[ExtractionStatus] = mapped_column(
        SAEnum(ExtractionStatus, native_enum=False, length=20, create_constraint=True),
        nullable=False,
        default=ExtractionStatus.ACTIVE,
    )
    invalidated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    @property
    def is_active(self) -> bool:
        """True when this derivation still applies.

        Derived, not stored, following ADR-014's rule for ``jobs``: ``status`` is the truth,
        and *why* a row stopped applying is worth keeping rather than collapsing into a
        boolean. Every read path should filter on this **and** on the digest matching the
        job's current description; either alone would be enough, and both together mean a
        bug in one does not surface a stale requirement.
        """
        return self.status is ExtractionStatus.ACTIVE

    def invalidate(self, at: datetime | None = None) -> None:
        """Mark this derivation as no longer applying. **The only transition there is.**

        There is deliberately no counterpart. ``INVALIDATED`` is terminal: a description that
        changes and then changes back produces a *new* row under the recomputed digest, with
        its own evidence and its own extractor version, rather than resurrecting a record of
        a verification that was performed against text the system no longer holds.

        A database CHECK cannot express a transition rule — it sees one row, not the row it
        replaced — and a trigger would be neither portable nor in scope. The guarantee here
        is therefore structural in the model rather than in the schema: no code path sets
        ``status`` back to ``ACTIVE``, and re-running is calling ``invalidate`` again.
        """
        self.status = ExtractionStatus.INVALIDATED
        self.invalidated_at = at or _utcnow()

    def __repr__(self) -> str:
        # Identifiers and the type only. ``evidence_text`` is public job prose rather than
        # personal data, but ADR-030 D24 keeps extraction content out of logs as a standing
        # rule, and a repr is one `logger.info("%s", row)` away from being a log line.
        return (
            f"<ExtractedRequirement id={self.id!r} job_id={self.job_id!r} "
            f"type={self.requirement_type.value} status={self.status.value}>"
        )
