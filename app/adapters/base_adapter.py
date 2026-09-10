"""The job source adapter interface.

Every source implements this. Nothing downstream knows which source produced a job beyond
its ``source`` string (ADR-005, INV-6).

Deliberately narrow: fetch, and declare whether you are authoritative. A wider interface
would leak the shape of whichever source was implemented first, and the entire point of the
boundary is that the hardest unsolved problem in this domain — legally and technically sound
job data acquisition — can be solved later without touching anything downstream.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas.job import RawJob


class AdapterError(Exception):
    """An adapter could not fetch its jobs.

    Adapters translate their own failures into this, so ingestion never sees an httpx
    error, a JSON decode error, or a file-not-found from a specific source implementation.

    **Messages must be sanitized.** A future live source's error body could quote the
    content it was fetching, and error text ends up in `ingestion_state.last_error`.
    """


class JobSourceAdapter(ABC):
    """Abstract interface for a source of job postings."""

    #: Stable identifier for this source, stored on every job it supplies. Changing it
    #: orphans that source's existing rows, so treat it as permanent.
    source_name: str = "base"

    #: Whether this source is the complete authority on the jobs it supplies.
    #:
    #: True means a job vanishing from a fetch is genuine evidence the posting is gone, and
    #: ingestion may close it. The curated dataset is authoritative: it is a single file
    #: listing every job it knows about.
    #:
    #: False means a fetch returns a partial view — a page, a filtered query, a rate-limited
    #: window — and absence proves nothing. Ingestion leaves unseen jobs untouched.
    #:
    #: **Defaulting to False is deliberate.** A new adapter author who does not think about
    #: this gets the safe behaviour. Closing the entire catalogue because a paginated API
    #: returned page one would be a data-loss bug, and this default is what prevents it
    #: being written by accident.
    is_authoritative: bool = False

    @abstractmethod
    async def fetch(self) -> list[RawJob]:
        """Fetch the current set of jobs from this source.

        Returns jobs in the source-agnostic :class:`~app.schemas.job.RawJob` shape.
        Normalization, hashing and deduplication happen downstream — an adapter's only job
        is to translate its source into the common shape.

        Returns:
            Every job this source currently offers. An authoritative source must return its
            complete set, because ingestion treats omission as closure.

        Raises:
            AdapterError: The source could not be read. Message must carry no raw payload.
        """
