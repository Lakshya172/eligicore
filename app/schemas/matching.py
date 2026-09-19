"""Recommendation schemas — eligibility and matching, side by side, never combined.

The request carries a candidate profile that is **never stored** (ADR-001, ADR-002, INV-1). The
response is computed, returned, and persisted by the client.

Contract rules, from ADR-006, ADR-020 and ADR-022:

* Each item embeds the Week 4 :class:`JobEligibility` **unchanged** — the recommendation layer
  groups jobs by it and never rewrites it.
* ``match_score`` is TF-IDF cosine similarity × 100 (ADR-020). It is **not** an eligibility
  score, and there is deliberately no combined or overall score.
* Groups, not one list: jobs a candidate can apply for are ranked; jobs needing review are ranked
  separately; ineligible and closed jobs stay retrievable with their reasons but are not ranked.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.candidate import CandidateProfile
from app.schemas.eligibility import JobEligibility, JobId

#: Maximum number of jobs one recommendation request evaluates — both the explicit ``job_ids``
#: limit and the cap on the default scope. Deliberately its own constant, equal to but not
#: coupled to the eligibility limit (ADR-022).
MAX_RECOMMENDATION_JOBS = 50


class MatchScoreBasis(str, Enum):
    """Why ``match_score`` has a value, or why it is null.

    The first three mirror the matching engine's ``ScoreBasis``. ``WITHHELD_NOT_ELIGIBLE`` is
    the recommendation layer's: a job the candidate is not eligible for is not scored for
    recommendation purposes, so no similarity number competes with the eligibility verdict.
    """

    SCORED = "SCORED"
    NO_CANDIDATE_TERMS = "NO_CANDIDATE_TERMS"
    NO_JOB_TERMS = "NO_JOB_TERMS"
    WITHHELD_NOT_ELIGIBLE = "WITHHELD_NOT_ELIGIBLE"


class MatchTermKind(str, Enum):
    """Which namespace a shared term came from (ADR-020 §2)."""

    SKILL = "skill"
    TEXT = "text"


class SharedTerm(BaseModel):
    """A term both the profile and the job contain, and its share of the cosine."""

    model_config = ConfigDict(extra="forbid")

    term: str = Field(
        description="A job skill's display name, or a literal word from the job's text."
    )
    kind: MatchTermKind
    contribution: float = Field(
        ge=0, description="candidate weight × job weight for this term."
    )


class RecommendationMatch(BaseModel):
    """Relevance evidence for one job. Never an eligibility judgement."""

    model_config = ConfigDict(extra="forbid")

    match_score: float | None = Field(
        ge=0,
        le=100,
        description=(
            "TF-IDF cosine similarity between the profile's skills and experience and the job, "
            "× 100, one decimal. Null when there was nothing to compare or the job is not "
            "eligible — see `score_basis`. Null is not zero. Not an eligibility score."
        ),
    )
    score_basis: MatchScoreBasis
    matched_required_skills: list[str] = Field(
        description="The job's required skills the profile lists, as the job names them."
    )
    missing_required_skills: list[str] = Field(
        description="The job's required skills the profile does not list."
    )
    required_skill_count: int = Field(
        ge=0, description="Distinct required skills. Zero means the job lists none."
    )
    top_terms: list[SharedTerm] = Field(
        description="Up to five shared terms that contributed most to the score."
    )


class RecommendationItem(BaseModel):
    """One job: its unchanged eligibility verdict, its match evidence, and an explanation."""

    model_config = ConfigDict(extra="forbid")

    rank: int | None = Field(
        ge=1,
        description=(
            "1-based position within `ranked` or `needs_review`. Null in `not_eligible` and "
            "`not_open`, which are not ranked."
        ),
    )
    eligibility: JobEligibility = Field(
        description="The Week 4 eligibility result for this job, exactly as `/eligibility/check` returns it."
    )
    match: RecommendationMatch
    explanation: str = Field(
        min_length=1,
        description=(
            "The eligibility summary and the match evidence, composed deterministically. "
            "Contains no candidate values beyond job-side names and shared terms."
        ),
    )


class RecommendationRequest(BaseModel):
    """Request body for ``POST /api/v1/recommendations``."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "profile": {
                    "candidate_id": "client-generated-example-id",
                    "education": [
                        {
                            "degree": "B.Tech",
                            "level": "BACHELORS",
                            "field_of_study": "Information Technology",
                            "grad_year": 2027,
                            "cgpa": 8.2,
                            "scale": "SCALE_10",
                        }
                    ],
                    "skills": ["Python", "SQL"],
                    "experience": [
                        {
                            "title": "Data Engineering Intern",
                            "description": "Built ingestion pipelines and internal APIs.",
                        }
                    ],
                    "backlogs": 0,
                }
            }
        },
    )

    profile: CandidateProfile = Field(
        description="The candidate profile, supplied by the client. Evaluated, never stored."
    )
    job_ids: list[JobId] | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_RECOMMENDATION_JOBS,
        description=(
            f"Optional catalogue job ids, 1 to {MAX_RECOMMENDATION_JOBS}; duplicates removed "
            "keeping first-seen order. Any status may be requested. Omitted: the ACTIVE and "
            f"UNKNOWN jobs, at most {MAX_RECOMMENDATION_JOBS}."
        ),
    )

    @field_validator("job_ids")
    @classmethod
    def _dedupe_preserving_order(cls, value: list[str] | None) -> list[str] | None:
        """Drop repeated ids so a job is evaluated and reported once."""
        return None if value is None else list(dict.fromkeys(value))


class RecommendationResponse(BaseModel):
    """Response from ``POST /api/v1/recommendations``.

    Every found job appears in exactly one of the four groups. Computed for the client to
    persist locally; the server keeps no copy.
    """

    model_config = ConfigDict(extra="forbid")

    candidate_id: str | None = Field(
        default=None, description="Echoed from the request for client-side correlation."
    )
    engine_version: str = Field(description="Eligibility rules version (Week 4).")
    matching_version: str = Field(description="Matching algorithm version (ADR-020).")
    evaluated_at: datetime = Field(description="UTC time of evaluation.")
    corpus_size: int = Field(
        ge=0, description="Catalogue jobs the TF-IDF weights were computed from."
    )
    corpus_fingerprint: str = Field(
        description=(
            "SHA-256 identifying that corpus. A stored score computed under a different "
            "fingerprint may differ. Derived from job data only."
        )
    )
    jobs_considered: int = Field(ge=0, description="Found jobs evaluated in this response.")
    jobs_not_considered: int = Field(
        ge=0,
        description=(
            f"Default scope only: ACTIVE/UNKNOWN jobs beyond the first "
            f"{MAX_RECOMMENDATION_JOBS} (newest `last_verified_at` first, then id) that were "
            "not evaluated. Zero when `job_ids` is supplied."
        ),
    )
    ranked: list[RecommendationItem] = Field(
        description="ELIGIBLE and LIKELY_ELIGIBLE open jobs, by match score (nulls last), then id."
    )
    needs_review: list[RecommendationItem] = Field(
        description="NEEDS_REVIEW and UNKNOWN open jobs, flagged separately, same ordering."
    )
    not_eligible: list[RecommendationItem] = Field(
        description="NOT_ELIGIBLE open jobs with their reasons. Not ranked; ordered by id."
    )
    not_open: list[RecommendationItem] = Field(
        description=(
            "Requested jobs whose status is CLOSED or EXPIRED, whatever their eligibility. "
            "Not ranked; ordered by id."
        )
    )
    not_found_job_ids: list[str] = Field(
        default_factory=list,
        description="Requested ids with no job in the catalogue, in request order.",
    )
