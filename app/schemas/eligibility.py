"""Eligibility evaluation schemas.

The request carries a candidate profile that is **never stored** (ADR-001, ADR-002, INV-1).
The response is computed, returned, and persisted by the client — not by the server.

Contract rules, from ADR-006, ADR-017 and ``standards/eligibility.md`` §6:

* Every verdict carries a per-requirement breakdown and a human-readable summary (INV-8).
* Every breakdown entry carries a machine-readable ``reason_code`` and a ``note``.
* There is deliberately **no top-level confidence**. Confidence belongs to individual
  determinations; a single number beside a verdict reads as "how good is my result",
  which is exactly the conflation ADR-003 forbids.
* There is deliberately **no match score**. Eligibility is not matching (C-11, Week 5).
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.candidate import CandidateProfile, Confidence
from app.schemas.job import JobStatusSchema

#: Maximum number of job ids in one check (ruling A-4). Bounds the work, and — once the AI
#: stage exists — the number of paid calls one request can cause.
MAX_JOB_IDS = 50


class EligibilityState(str, Enum):
    """Final verdict for one candidate-job pair. Exactly five states (ADR-017).

    * ``ELIGIBLE`` — every stated requirement passed deterministically, or the job states
      no structured requirement at all
    * ``LIKELY_ELIGIBLE`` — every stated requirement passed, at least one via AI reasoning
    * ``NEEDS_REVIEW`` — something is unresolved: an unverifiable requirement, or an AI
      assessment that failed or said "not related"
    * ``UNKNOWN`` — nothing could be verified
    * ``NOT_ELIGIBLE`` — at least one verified deterministic hard requirement failed
    """

    ELIGIBLE = "ELIGIBLE"
    LIKELY_ELIGIBLE = "LIKELY_ELIGIBLE"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    UNKNOWN = "UNKNOWN"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"


class RequirementType(str, Enum):
    """The structured requirements the engine evaluates (ADR-018).

    Skills, location, job type and experience are absent on purpose: they are matching or
    preference concerns (Week 5), or have no field on either side to compare.
    """

    MIN_CGPA = "MIN_CGPA"
    GRAD_YEAR_WINDOW = "GRAD_YEAR_WINDOW"
    MAX_BACKLOGS = "MAX_BACKLOGS"
    MIN_DEGREE_LEVEL = "MIN_DEGREE_LEVEL"
    ALLOWED_FIELDS = "ALLOWED_FIELDS"


class RequirementStatus(str, Enum):
    """Outcome of one requirement. ``UNKNOWN`` is a result, not an error (INV-3)."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class EvaluationMethod(str, Enum):
    """Which stage produced a breakdown entry.

    Lowercase values are the dossier's own (§11 sample, ADR-006). This field is how a
    reader audits ADR-003 from the output alone.
    """

    DETERMINISTIC = "deterministic"
    AI_REASONING = "ai_reasoning"


class ReasonCode(str, Enum):
    """Stable, machine-readable reason for a breakdown entry.

    Part of the published contract (ADR-010): add members, never rename or remove them.
    """

    # --- PASS ----------------------------------------------------------------------------
    MEETS_MINIMUM = "MEETS_MINIMUM"
    WITHIN_WINDOW = "WITHIN_WINDOW"
    WITHIN_LIMIT = "WITHIN_LIMIT"
    MEETS_LEVEL = "MEETS_LEVEL"
    EXACT_FIELD_MATCH = "EXACT_FIELD_MATCH"

    # --- FAIL (verified) -----------------------------------------------------------------
    BELOW_MINIMUM = "BELOW_MINIMUM"
    BEFORE_WINDOW = "BEFORE_WINDOW"
    AFTER_WINDOW = "AFTER_WINDOW"
    EXCEEDS_LIMIT = "EXCEEDS_LIMIT"
    BELOW_LEVEL = "BELOW_LEVEL"

    # --- UNKNOWN: candidate side ---------------------------------------------------------
    MISSING_CANDIDATE_VALUE = "MISSING_CANDIDATE_VALUE"
    CANDIDATE_SCALE_UNKNOWN = "CANDIDATE_SCALE_UNKNOWN"
    CANDIDATE_VALUE_EXCEEDS_SCALE = "CANDIDATE_VALUE_EXCEEDS_SCALE"
    CANDIDATE_LEVEL_UNKNOWN = "CANDIDATE_LEVEL_UNKNOWN"
    NO_QUALIFICATION = "NO_QUALIFICATION"
    QUALIFICATION_NOT_DETERMINABLE = "QUALIFICATION_NOT_DETERMINABLE"

    # --- UNKNOWN: job side ---------------------------------------------------------------
    JOB_SCALE_MISSING = "JOB_SCALE_MISSING"
    JOB_SCALE_INVALID = "JOB_SCALE_INVALID"
    JOB_VALUE_EXCEEDS_SCALE = "JOB_VALUE_EXCEEDS_SCALE"
    INVALID_JOB_REQUIREMENT = "INVALID_JOB_REQUIREMENT"

    # --- UNKNOWN: comparison -------------------------------------------------------------
    SCALE_MISMATCH = "SCALE_MISMATCH"
    FIELD_NOT_EXACT_MATCH = "FIELD_NOT_EXACT_MATCH"
    SKIPPED_AFTER_HARD_FAILURE = "SKIPPED_AFTER_HARD_FAILURE"

    # --- AI field-relatedness stage (ADR-019) --------------------------------------------
    AI_FIELD_RELATED = "AI_FIELD_RELATED"
    AI_FIELD_NOT_RELATED = "AI_FIELD_NOT_RELATED"
    AI_ASSESSMENT_INCONCLUSIVE = "AI_ASSESSMENT_INCONCLUSIVE"
    AI_ASSESSMENT_UNAVAILABLE = "AI_ASSESSMENT_UNAVAILABLE"


class FieldRelatedness(str, Enum):
    """An AI provider's judgement on whether a field of study falls within permitted fields.

    ``UNCERTAIN`` is a legitimate answer and the conservative default (ADR-019).
    """

    RELATED = "RELATED"
    NOT_RELATED = "NOT_RELATED"
    UNCERTAIN = "UNCERTAIN"


class FieldRelatednessAssessment(BaseModel):
    """The validated result of ``AIProvider.assess_field_relatedness``.

    Provider output is untrusted input (``standards/ai.md`` §4): a reply is only usable once
    it validates against this model, and anything else is reported as an invalid response.
    Never persisted and never logged.
    """

    model_config = ConfigDict(extra="forbid")

    result: FieldRelatedness
    confidence: Confidence = Field(
        description="The provider's own confidence. The engine caps it and never raises it."
    )
    reason: str = Field(
        min_length=1,
        max_length=500,
        description="Short explanation of the judgement, returned to the caller as a note.",
    )


class RequirementResult(BaseModel):
    """One requirement's evaluation."""

    model_config = ConfigDict(extra="forbid")

    requirement_type: RequirementType
    requirement: str = Field(
        description="The requirement as the job states it, e.g. 'Minimum CGPA 7.0 (SCALE_10)'."
    )
    candidate_value: str | None = Field(
        default=None,
        description=(
            "The candidate value the requirement was compared against, as supplied in the "
            "request. Null when the profile does not provide one. Returned to the caller "
            "only — never logged."
        ),
    )
    status: RequirementStatus
    confidence: Confidence = Field(
        description=(
            "How much the system trusts this determination — not how good the news is. "
            "Deterministic PASS and FAIL are HIGH; UNKNOWN is LOW."
        )
    )
    method: EvaluationMethod
    reason_code: ReasonCode
    note: str = Field(min_length=1, description="Human-readable explanation of the result.")


class JobEligibility(BaseModel):
    """The verdict for one job."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    company_name: str
    role_title: str
    job_status: JobStatusSchema = Field(
        description=(
            "The posting's catalogue status. Informational: a closed job is still evaluated, "
            "and its status does not affect the verdict."
        )
    )
    apply_link: str | None
    deadline: date | None

    eligibility_state: EligibilityState
    requirement_breakdown: list[RequirementResult] = Field(
        description="One entry per structured requirement the job states."
    )
    summary: str = Field(
        min_length=1,
        description="Human-readable reason for the verdict. Contains no candidate values.",
    )


JobId = Annotated[str, Field(min_length=1, max_length=100)]


class EligibilityCheckRequest(BaseModel):
    """Request body for ``POST /api/v1/eligibility/check``."""

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
                    "backlogs": 0,
                },
                "job_ids": ["00000000-0000-0000-0000-000000000000"],
            }
        },
    )

    profile: CandidateProfile = Field(
        description="The candidate profile, supplied by the client. Evaluated, never stored."
    )
    job_ids: list[JobId] = Field(
        min_length=1,
        max_length=MAX_JOB_IDS,
        description=(
            f"Catalogue job ids to evaluate against, 1 to {MAX_JOB_IDS}. Duplicates are "
            "removed, keeping first-seen order."
        ),
    )

    @field_validator("job_ids")
    @classmethod
    def _dedupe_preserving_order(cls, value: list[str]) -> list[str]:
        """Drop repeated ids so a job is evaluated and reported once."""
        return list(dict.fromkeys(value))


class EligibilityCheckResponse(BaseModel):
    """Response from ``POST /api/v1/eligibility/check``.

    Computed for the client to persist locally. The server keeps no copy.
    """

    model_config = ConfigDict(extra="forbid")

    candidate_id: str | None = Field(
        default=None, description="Echoed from the request for client-side correlation."
    )
    engine_version: str = Field(
        description=(
            "Version of the eligibility rules that produced these verdicts. A client holding "
            "stored results can re-evaluate when this changes."
        )
    )
    evaluated_at: datetime = Field(description="UTC time of evaluation.")
    results: list[JobEligibility] = Field(
        description="One verdict per found job, in request order."
    )
    not_found_job_ids: list[str] = Field(
        default_factory=list,
        description="Requested ids with no job in the catalogue, in request order.",
    )
