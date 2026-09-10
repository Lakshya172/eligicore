"""Adapter ingestion state — one row per source.

Current state only: no run log, no hash ledger (ADR-015). The row is overwritten each run,
so the table cannot grow without new sources being added and needs no retention policy.

╔══════════════════════════════════════════════════════════════════════════════════════╗
║  This table records what the SYSTEM did, never what a PERSON did.                     ║
║                                                                                       ║
║  It must never gain a ``candidate_id``, profile data, resume content, an evaluation,  ║
║  a match score, or any per-user view of the catalogue. Job ingestion runs             ║
║  independently of any candidate (dossier §7 step 4), so a user identifier here would  ║
║  be a defect rather than a convenience (INV-1, ADR-012).                              ║
╚══════════════════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum as SAEnum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class IngestionStatus(str, enum.Enum):
    """Outcome of a source's most recent ingestion run."""

    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


def _utcnow() -> datetime:
    """Timezone-aware UTC now."""
    return datetime.now(timezone.utc)


class IngestionState(Base):
    """The most recent ingestion outcome for one source.

    ``source`` is the primary key, which is what makes "one row per source" structural
    rather than a convention someone has to remember.
    """

    __tablename__ = "ingestion_state"

    source: Mapped[str] = mapped_column(String(100), primary_key=True)

    last_run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    #: Distinct from ``last_run_at`` so a run of repeated failures does not look fresh.
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_status: Mapped[IngestionStatus] = mapped_column(
        SAEnum(IngestionStatus, native_enum=False, length=20), nullable=False
    )
    #: Sanitized failure summary — a category, never a raw provider or source payload.
    #: A future live source's error body could quote the content it was fetching.
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- last run outcome --------------------------------------------------------------
    jobs_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    jobs_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    jobs_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    jobs_unchanged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    jobs_deactivated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    #: High-water mark or page token for sources that need one to resume. Unused by the
    #: curated adapter, which fetches its whole dataset every run.
    cursor: Mapped[str | None] = mapped_column(String(500), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<IngestionState source={self.source!r} "
            f"status={self.last_status.value} seen={self.jobs_seen}>"
        )
