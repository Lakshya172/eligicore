"""Recommendations endpoint.

HTTP concerns only (INV-7): validate the request, load the job catalogue, call the
recommendation service, return its result. Scope, grouping, ranking and explanations live in
:mod:`app.services.recommendations`; eligibility and matching live in their own services.

**Stateless** (ADR-002). The profile arrives in the body and leaves in nothing but the response.
The catalogue — public operational data — is read in one query and never written. There is
deliberately no ``GET``: it would imply a stored result.

``/api/v1/matching/score`` is not implemented.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.ai_service import AIService, get_lazy_ai_service
from app.database import get_db
from app.models.job import Job
from app.schemas.job import JobRead
from app.schemas.matching import (
    MAX_RECOMMENDATION_JOBS,
    RecommendationRequest,
    RecommendationResponse,
)
from app.services.recommendations import recommend

router = APIRouter(tags=["recommendations"])


@router.post(
    "/recommendations",
    response_model=RecommendationResponse,
    status_code=status.HTTP_200_OK,
    summary="Recommend catalogue jobs, grouped by eligibility and ordered by relevance",
    description=(
        "Evaluates the supplied profile's **eligibility** for catalogue jobs (the same verdicts "
        "as `POST /eligibility/check`) and scores how **relevant** each job is to the "
        "profile's skills and experience. The two are reported side by side and never "
        "combined into one number.\n\n"
        "**Groups.** Every job found appears in exactly one:\n"
        "- `ranked` — `ELIGIBLE` and `LIKELY_ELIGIBLE`, ordered by `match_score`\n"
        "- `needs_review` — `NEEDS_REVIEW` and `UNKNOWN`, ordered the same way\n"
        "- `not_eligible` — `NOT_ELIGIBLE`, with the reasons; not ranked and not scored\n"
        "- `not_open` — requested jobs whose status is `CLOSED` or `EXPIRED`, whatever their "
        "eligibility; not ranked\n\n"
        "A high `match_score` never moves a job into a different group.\n\n"
        "**`match_score`** is TF-IDF cosine similarity × 100, one decimal, computed against the "
        "whole catalogue. It is null when there is nothing to compare (see `score_basis`) — "
        "null is not zero. It is not an eligibility score. Ordering: score descending, nulls "
        "last, then job id.\n\n"
        f"**Scope.** With `job_ids` (1 to {MAX_RECOMMENDATION_JOBS}, duplicates removed), "
        "exactly those jobs, any status; unknown ids are listed in `not_found_job_ids`. "
        f"Without them, the ACTIVE and UNKNOWN jobs — at most {MAX_RECOMMENDATION_JOBS}, "
        "newest first, with any remainder counted in `jobs_not_considered`. Status is never "
        "inferred from a deadline.\n\n"
        "Eligibility may consult the AI provider for an ambiguous field of study, exactly as "
        "`/eligibility/check` does. Matching and explanations use no AI.\n\n"
        "**Nothing is stored.** Persist the response on the client."
    ),
    responses={422: {"description": "Invalid request. Submitted values are not echoed."}},
)
async def recommendations(
    request: RecommendationRequest,
    db: Annotated[Session, Depends(get_db)],
    ai_service: Annotated[AIService, Depends(get_lazy_ai_service)],
) -> RecommendationResponse:
    """Load the catalogue and delegate to the recommendation service."""
    # One query. Ordered by id so the corpus — and its fingerprint — does not depend on when
    # jobs were last verified.
    jobs = db.execute(select(Job).order_by(Job.id.asc())).scalars().all()
    catalogue = [JobRead.model_validate(job) for job in jobs]
    return await recommend(request.profile, request.job_ids, catalogue, ai_service)
