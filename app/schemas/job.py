"""Job schemas.

Three layers, kept separate on purpose:

* :class:`RawJob` — what an **adapter** returns. Source-agnostic and permissive, because a
  future source will not hand over clean data.
* :class:`NormalizedJob` — the canonical shape after normalization, ready to persist.
* :class:`JobRead` / :class:`JobListResponse` — the **public API** contract.

A source changing its output shape therefore cannot change the API contract, and the API
contract can evolve without rewriting every adapter.

Job postings are public data. Nothing here is personal data, and no field may correlate a
job to a candidate (INV-1).
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

# Reused rather than redefined. A second JobType with the same members would drift from
# this one the first time either changed.
from app.schemas.candidate import JobType


class JobStatusSchema(str, Enum):
    """API-facing mirror of :class:`app.models.job.JobStatus`.

    Duplicated deliberately: the model enum is a storage concern and the schema enum is a
    published contract (ADR-010 — enum values are part of the contract). Coupling them
    would mean a storage refactor could silently break every consumer. A test asserts the
    two stay in step.
    """

    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"


# ---------------------------------------------------------------------------------------
# Adapter contract
# ---------------------------------------------------------------------------------------


class RawJob(BaseModel):
    """One job as an adapter reports it, before normalization.

    Permissive by design. Only what identifies a posting is required; everything else is
    optional, because a real source will omit fields and rejecting the whole record for a
    missing deadline would throw away a usable job.

    ``extra="forbid"`` still applies: an adapter inventing a field is a bug in the adapter,
    and silently dropping it would hide that.
    """

    model_config = ConfigDict(extra="forbid")

    company_name: str = Field(min_length=1, max_length=300)
    role_title: str = Field(min_length=1, max_length=300)
    job_type: JobType

    location: str | None = Field(default=None, max_length=300)
    description: str = Field(default="", max_length=50_000)

    requirements: dict[str, object] = Field(default_factory=dict)
    min_cgpa: float | None = Field(default=None, ge=0)
    min_cgpa_scale: str | None = Field(
        default=None,
        max_length=20,
        description=(
            "Grading scale for `min_cgpa`. Left as stated by the source and never inferred "
            "— a cutoff without its scale is not comparable to anything."
        ),
    )
    allowed_fields: list[str] = Field(default_factory=list)
    max_backlogs: int | None = Field(default=None, ge=0)
    min_grad_year: int | None = Field(default=None, ge=1950, le=2100)
    max_grad_year: int | None = Field(default=None, ge=1950, le=2100)
    required_skills: list[str] = Field(default_factory=list)

    apply_link: str | None = Field(default=None, max_length=2000)
    deadline: date | None = None

    source_job_id: str | None = Field(
        default=None,
        max_length=200,
        description=(
            "The source's own stable identifier, when it has one. Enables exact-match "
            "deduplication; absence falls back to content hashing."
        ),
    )


class NormalizedJob(BaseModel):
    """A job after normalization, with its canonical content hash computed."""

    model_config = ConfigDict(extra="forbid")

    company_name: str
    role_title: str
    job_type: JobType
    location: str | None
    description: str

    requirements: dict[str, object]
    min_cgpa: float | None
    min_cgpa_scale: str | None
    allowed_fields: list[str]
    max_backlogs: int | None
    min_grad_year: int | None
    max_grad_year: int | None
    required_skills: list[str]

    apply_link: str | None
    deadline: date | None

    source: str
    source_job_id: str | None
    content_hash: str


# ---------------------------------------------------------------------------------------
# Public API contract
# ---------------------------------------------------------------------------------------


class JobRead(BaseModel):
    """A job as returned by the API."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: str
    company_name: str
    role_title: str
    job_type: JobType
    location: str | None
    description: str

    requirements: dict[str, object]
    min_cgpa: float | None
    min_cgpa_scale: str | None = Field(
        default=None,
        description=(
            "Grading scale for `min_cgpa`, as stated by the source. Null means the source "
            "did not state one — it is not assumed, and a comparison against it is not "
            "possible without one."
        ),
    )
    allowed_fields: list[str]
    max_backlogs: int | None
    min_grad_year: int | None
    max_grad_year: int | None
    required_skills: list[str]

    apply_link: str | None
    deadline: date | None

    source: str
    source_job_id: str | None
    status: JobStatusSchema
    is_active: bool = Field(
        description="Derived: true when `status` is ACTIVE. `status` is the stored truth."
    )
    last_verified_at: datetime


class JobListResponse(BaseModel):
    """A page of jobs.

    Bounded by construction — `standards/api_design.md` §6 requires list responses to be
    paginated rather than returning an unbounded catalogue.
    """

    model_config = ConfigDict(extra="forbid")

    items: list[JobRead]
    total: int = Field(ge=0, description="Total matching the filters, ignoring pagination.")
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


# ---------------------------------------------------------------------------------------
# Ingestion reporting
# ---------------------------------------------------------------------------------------


class IngestionOutcome(BaseModel):
    """What one adapter's ingestion run did.

    Counts and identifiers only. Returned to a caller and stored in `ingestion_state`;
    contains nothing personal, so it is safe to log.
    """

    model_config = ConfigDict(extra="forbid")

    source: str
    jobs_seen: int = Field(ge=0)
    jobs_created: int = Field(ge=0)
    jobs_updated: int = Field(ge=0)
    jobs_unchanged: int = Field(ge=0)
    jobs_deactivated: int = Field(ge=0)
    duplicates_collapsed: int = Field(
        default=0,
        ge=0,
        description="Records that resolved to a job already seen in this same run.",
    )
