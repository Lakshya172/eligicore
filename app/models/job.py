"""The job catalogue — operational data.

Field shape follows dossier §10.2. This table holds public job postings, not personal data:
nothing here is about a candidate, and no column may correlate a job to a user (INV-1).

Two deliberate departures from a naive reading of §10.2, both recorded:

* ``status`` is the dossier's four-state enum, and ``is_active`` is derived from it rather
  than stored (ADR-014). A boolean would collapse EXPIRED, CLOSED and UNKNOWN into one
  state and lose the distinction permanently.
* ``location`` exists even though §10.2's field table omits it, because the same section's
  deduplication spec lists "Normalized location" among the canonicalization inputs. It is
  required to implement the dossier's own hashing rule (contradiction C-7).

``description`` holds the **normalized** posting text. The adapter's raw upstream payload is
never stored — an approved Week 3 decision, and the reason the column is text rather than a
JSON blob.
"""

from __future__ import annotations

import enum
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import (
    Date,
    DateTime,
    Enum as SAEnum,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.database import Base
from app.schemas.candidate import JobType


class JobStatus(str, enum.Enum):
    """Lifecycle state of a posting (dossier §10.2).

    Four states, not a boolean, because *why* a job is closed is information worth keeping:

    * ``ACTIVE`` — open and accepting applications
    * ``EXPIRED`` — the stated deadline has passed
    * ``CLOSED`` — no longer offered; an authoritative source stopped listing it
    * ``UNKNOWN`` — no basis to say. Carries the same absence-of-evidence semantics as
      INV-3: not knowing is a state, not a failure.
    """

    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"


def _utcnow() -> datetime:
    """Timezone-aware UTC now.

    A local naive timestamp is a portability bug waiting for deployment: development is on
    one machine's clock and production is on another's.
    """
    return datetime.now(timezone.utc)


class Job(Base):
    """One job posting in the catalogue."""

    __tablename__ = "jobs"
    __table_args__ = (
        # The exact-match fast path from dossier §10.2, when a source provides stable ids.
        # NULLs compare as distinct in both SQLite and PostgreSQL, so sources without ids
        # are simply not covered by this constraint — which is the intended behaviour.
        UniqueConstraint("source", "source_job_id", name="uq_jobs_source_source_job_id"),
        Index("ix_jobs_content_hash", "content_hash"),
        Index("ix_jobs_status", "status"),
        Index("ix_jobs_source", "source"),
        Index("ix_jobs_job_type", "job_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # --- posting -----------------------------------------------------------------------
    company_name: Mapped[str] = mapped_column(String(300), nullable=False)
    role_title: Mapped[str] = mapped_column(String(300), nullable=False)
    job_type: Mapped[JobType] = mapped_column(
        SAEnum(JobType, native_enum=False, length=20), nullable=False
    )
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # --- eligibility criteria ----------------------------------------------------------
    # Structured, but NOT evaluated here. Week 4 owns eligibility; Week 3 only stores what
    # a posting states.
    requirements: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    min_cgpa: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: Grading scale for ``min_cgpa``. A cutoff without its scale is as meaningless as a
    #: candidate grade without one (standards/eligibility.md §4). Stored as a plain string
    #: so Week 4 owns the comparison semantics rather than Week 3 pre-empting them.
    min_cgpa_scale: Mapped[str | None] = mapped_column(String(20), nullable=True)
    allowed_fields: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    max_backlogs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_grad_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_grad_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    required_skills: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    # --- application ------------------------------------------------------------------
    apply_link: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)

    # --- provenance and dedup ---------------------------------------------------------
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    source_job_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # --- freshness --------------------------------------------------------------------
    status: Mapped[JobStatus] = mapped_column(
        SAEnum(JobStatus, native_enum=False, length=20),
        nullable=False,
        default=JobStatus.ACTIVE,
    )
    last_verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    @property
    def is_active(self) -> bool:
        """True when the posting is open.

        Derived, not stored (ADR-014). ``status`` is the truth; this is the convenience
        every caller actually wants to filter on.
        """
        return self.status is JobStatus.ACTIVE

    def __repr__(self) -> str:
        # Job postings are public data, so a readable repr leaks nothing. It still shows
        # only identifiers rather than free text.
        return f"<Job id={self.id!r} source={self.source!r} status={self.status.value}>"
