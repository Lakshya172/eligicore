"""Eligibility endpoint.

HTTP concerns only (INV-7): validate the request, load the requested jobs from the public
catalogue, call the engine, return its result. Every rule lives in
:mod:`app.services.eligibility_engine`.

**Stateless** (ADR-002). The profile arrives in the body and leaves in nothing but the
response. The database is read — the job catalogue is public operational data — and never
written. There is deliberately no ``GET`` eligibility route: it would imply a stored result.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.job import Job
from app.schemas.eligibility import (
    MAX_JOB_IDS,
    EligibilityCheckRequest,
    EligibilityCheckResponse,
)
from app.schemas.job import JobRead
from app.services.eligibility_engine import check_eligibility

router = APIRouter(prefix="/eligibility", tags=["eligibility"])


@router.post(
    "/check",
    response_model=EligibilityCheckResponse,
    status_code=status.HTTP_200_OK,
    summary="Check a candidate's eligibility for catalogue jobs",
    description=(
        "Evaluates the supplied profile against each requested job's **stated structured "
        "eligibility requirements**: minimum CGPA, graduation year window, backlog limit, "
        "minimum qualification level and permitted fields of study.\n\n"
        "**This is eligibility, not matching.** No score, ranking or skill overlap is "
        "computed.\n\n"
        "Each requirement is `PASS`, `FAIL` or `UNKNOWN`. Missing or invalid data is "
        "`UNKNOWN` — never a failure. Grades are compared only on the same grading scale.\n\n"
        "Verdicts, in precedence order: any verified deterministic failure → `NOT_ELIGIBLE`; "
        "nothing verifiable → `UNKNOWN`; anything unresolved → `NEEDS_REVIEW`; all passed → "
        "`ELIGIBLE` (or `LIKELY_ELIGIBLE` once AI reasoning contributed).\n\n"
        f"Up to {MAX_JOB_IDS} job ids per request; duplicates are removed. Unknown ids are "
        "listed in `not_found_job_ids` rather than failing the request. Closed jobs are "
        "still evaluated and report their status.\n\n"
        "**Nothing is stored.** Persist the response on the client."
    ),
    responses={422: {"description": "Invalid request. Submitted values are not echoed."}},
)
async def check(
    request: EligibilityCheckRequest,
    db: Annotated[Session, Depends(get_db)],
) -> EligibilityCheckResponse:
    """Load the requested jobs and delegate evaluation to the engine."""
    jobs = db.execute(select(Job).where(Job.id.in_(request.job_ids))).scalars().all()
    jobs_by_id = {job.id: JobRead.model_validate(job) for job in jobs}
    return check_eligibility(request.profile, request.job_ids, jobs_by_id)
