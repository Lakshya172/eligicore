"""Eligibility endpoint.

HTTP concerns only (INV-7): validate the request, load the requested jobs from the public
catalogue, call the eligibility service, return its result. Every rule lives in
:mod:`app.services.eligibility_engine`; the AI ambiguity stage lives in
:mod:`app.services.eligibility_ai` and receives a lazily built AI service, so a request that
needs no AI never constructs a provider (ADR-019).

**Stateless** (ADR-002). The profile arrives in the body and leaves in nothing but the
response. The database is read — the job catalogue is public operational data — and never
written. There is deliberately no ``GET`` eligibility route: it would imply a stored result.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.ai_service import AIService, get_lazy_ai_service
from app.database import get_db
from app.models.job import Job
from app.schemas.eligibility import (
    MAX_JOB_IDS,
    EligibilityCheckRequest,
    EligibilityCheckResponse,
)
from app.schemas.job import JobRead
from app.services.eligibility_ai import check_eligibility_with_ai

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
        "**AI is used for one thing only:** when a field of study is present but not an exact "
        "match for a permitted field, and no deterministic requirement failed, an AI provider "
        "judges whether the fields are related. Only the field of study and the permitted "
        "fields are sent. Such entries carry `method: ai_reasoning` and at most MEDIUM "
        "confidence. An AI judgement can make a verdict `LIKELY_ELIGIBLE` or `NEEDS_REVIEW`, "
        "never `NOT_ELIGIBLE`; if the AI is unavailable the entry is `UNKNOWN`.\n\n"
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
    ai_service: Annotated[AIService, Depends(get_lazy_ai_service)],
) -> EligibilityCheckResponse:
    """Load the requested jobs and delegate evaluation to the eligibility service."""
    jobs = db.execute(select(Job).where(Job.id.in_(request.job_ids))).scalars().all()
    jobs_by_id = {job.id: JobRead.model_validate(job) for job in jobs}
    return await check_eligibility_with_ai(
        request.profile, request.job_ids, jobs_by_id, ai_service
    )
