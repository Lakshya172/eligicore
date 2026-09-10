"""Job catalogue endpoints.

Read-only. Ingestion is a service, not an endpoint, in Week 3 — see the note below.

Job postings are public data, so unlike every other router in this project these endpoints
handle no personal data at all. They still take no candidate parameter and return no
per-candidate view: eligibility and matching are Weeks 4 and 5, and putting a candidate
filter here would be those engines leaking into ingestion.

HTTP concerns only. Querying lives in this module because it is data access rather than
business logic; anything that *decides* something about a job belongs in a service (INV-7).

**Deliberately absent: `POST /api/v1/jobs/ingest`.** The dossier §11 lists it, but the
approved Week 3 API scope names only these two reads. Ingestion is implemented and tested as
a service (`app.services.job_ingestion`); exposing a trigger endpoint is deferred rather than
dropped, and is recorded as a known limitation.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.job import Job, JobStatus
from app.schemas.candidate import JobType
from app.schemas.job import JobListResponse, JobRead

router = APIRouter(prefix="/jobs", tags=["jobs"])

#: Hard ceiling on page size. A caller asking for everything still gets a bounded response
#: (`standards/api_design.md` §6).
MAX_LIMIT = 100


def _to_read(job: Job) -> JobRead:
    """Shape a stored job into the API contract.

    ``is_active`` is derived from ``status`` rather than stored (ADR-014), so it is set
    here rather than coming from the ORM attributes directly.
    """
    return JobRead(
        id=job.id,
        company_name=job.company_name,
        role_title=job.role_title,
        job_type=job.job_type,
        location=job.location,
        description=job.description,
        requirements=job.requirements,
        min_cgpa=job.min_cgpa,
        min_cgpa_scale=job.min_cgpa_scale,
        allowed_fields=job.allowed_fields,
        max_backlogs=job.max_backlogs,
        min_grad_year=job.min_grad_year,
        max_grad_year=job.max_grad_year,
        required_skills=job.required_skills,
        apply_link=job.apply_link,
        deadline=job.deadline,
        source=job.source,
        source_job_id=job.source_job_id,
        status=job.status.value,  # type: ignore[arg-type]
        is_active=job.is_active,
        last_verified_at=job.last_verified_at,
    )


@router.get(
    "",
    response_model=JobListResponse,
    status_code=status.HTTP_200_OK,
    summary="List jobs in the catalogue",
    description=(
        "Returns a page of job postings.\n\n"
        "**Filters are deliberately minimal** — only what Weeks 4 and 5 need. `is_active` "
        "keeps eligibility evaluation off dead postings, `job_type` matches the candidate "
        "preference the profile already carries, and `source` exists for operational "
        "inspection of one adapter's output. Nothing else has a caller yet.\n\n"
        "`is_active` is a two-state filter defaulting to true, so the common case does not "
        "have to remember to exclude closed postings — evaluating eligibility against a "
        "dead job wastes the candidate's attention. Pass `is_active=false` for closed and "
        "expired postings.\n\n"
        "There is deliberately no 'return everything' option: nothing in the current scope "
        "needs one, and a caller who wants both sets can make both calls.\n\n"
        "This endpoint performs no eligibility or matching logic and takes no candidate "
        "parameter."
    ),
)
async def list_jobs(
    db: Annotated[Session, Depends(get_db)],
    is_active: Annotated[
        bool | None,
        Query(description="Filter by active status. Defaults to active jobs only."),
    ] = True,
    job_type: Annotated[
        JobType | None, Query(description="Filter by internship or full-time.")
    ] = None,
    source: Annotated[
        str | None, Query(max_length=100, description="Filter by adapter source name.")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JobListResponse:
    """List jobs with the minimal filter set."""
    filters = []
    if is_active is True:
        filters.append(Job.status == JobStatus.ACTIVE)
    elif is_active is False:
        filters.append(Job.status != JobStatus.ACTIVE)
    if job_type is not None:
        filters.append(Job.job_type == job_type)
    if source is not None:
        filters.append(Job.source == source)

    total = db.execute(
        select(func.count()).select_from(Job).where(*filters)
    ).scalar_one()

    jobs = (
        db.execute(
            select(Job)
            .where(*filters)
            # Deterministic ordering. Without a tiebreaker, two jobs sharing a timestamp
            # can swap between pages and a client paginating would see one twice and miss
            # another entirely.
            .order_by(Job.last_verified_at.desc(), Job.id.asc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )

    return JobListResponse(
        items=[_to_read(job) for job in jobs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{job_id}",
    response_model=JobRead,
    status_code=status.HTTP_200_OK,
    summary="Get one job by id",
    description=(
        "Returns a single job posting.\n\n"
        "Closed and expired jobs remain retrievable — a posting is never deleted, so a "
        "stored reference to it stays resolvable and its `status` explains why it is no "
        "longer open."
    ),
    responses={404: {"description": "No job with that id."}},
)
async def get_job(job_id: str, db: Annotated[Session, Depends(get_db)]) -> JobRead:
    """Fetch one job."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found."
        )
    return _to_read(job)
