"""Candidate profile endpoints — stateless.

Both endpoints take a profile in the request body, compute a result, and return it. Neither
touches the database. Neither has a session dependency, because there is nothing for them
to read or write (ADR-002).

There is deliberately no ``GET`` or ``PATCH`` on a candidate resource: those would imply a
server-held record, and none exists. Retrieval and update happen against IndexedDB on the
client (ADR-002, ADR-011).
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.schemas.candidate import (
    CandidateNormalizationResponse,
    CandidateProfile,
    CandidateValidationResponse,
)
from app.services import candidate_normalizer

router = APIRouter(prefix="/candidates", tags=["candidates"])


@router.post(
    "/validate",
    response_model=CandidateValidationResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate and normalize a candidate profile payload",
    description=(
        "Validates a candidate profile and returns the canonical profile shape plus any "
        "issues found.\n\n"
        "**Stateless.** The profile is not stored. The client generates `candidate_id`, "
        "owns it, and persists the result locally.\n\n"
        "Gaps are reported as issues rather than rejected: a partially complete profile is "
        "the normal state after resume parsing, and the candidate fills the gaps. Only "
        "structurally invalid payloads are rejected outright, with 422.\n\n"
        "`is_valid` is true when no ERROR-severity issue was found. Warnings do not block."
    ),
)
async def validate_candidate(profile: CandidateProfile) -> CandidateValidationResponse:
    """Validate a candidate profile and report any issues."""
    issues = candidate_normalizer.validate_profile(profile)
    return CandidateValidationResponse(
        candidate_id=profile.candidate_id,
        is_valid=not candidate_normalizer.has_blocking_issues(issues),
        issues=issues,
        profile=profile,
    )


@router.post(
    "/normalize",
    response_model=CandidateNormalizationResponse,
    status_code=status.HTTP_200_OK,
    summary="Normalize a candidate profile for downstream use",
    description=(
        "Canonicalizes skills, cleans up text fields, and produces a scale-independent "
        "view of each education grade.\n\n"
        "**Stateless.** Nothing is stored.\n\n"
        "Semantic meaning is preserved: education entries pass through intact, and a grade "
        "whose scale is unknown stays unknown — `normalized_grades[i].fraction` is null "
        "rather than being computed against an assumed 10-point scale.\n\n"
        "This endpoint performs no eligibility or matching logic."
    ),
)
async def normalize_candidate(profile: CandidateProfile) -> CandidateNormalizationResponse:
    """Normalize a candidate profile."""
    normalized, grades, changes = candidate_normalizer.normalize_profile(profile)
    return CandidateNormalizationResponse(
        candidate_id=profile.candidate_id,
        profile=normalized,
        normalized_grades=grades,
        changes=changes,
    )
