"""Tracker export schemas (ADR-023).

The request carries the client's own application-tracking rows. They are rendered into a
workbook and returned; **nothing is stored** (ADR-001, ADR-002, ADR-011, INV-1). There is no
candidate field: no candidate identity can reach the workbook.

Contract rules, from ADR-023:

* The client supplies complete rows. The server never looks a job up, recalculates a verdict or a
  score, or corrects a row — it renders what it is given.
* ``match_score`` is nullable, and null is not zero (C-24, ADR-020, ADR-022).
* ``ApplicationStatus`` holds exactly the five states of dossier §10.1. It is a data contract for
  data in flight, never a stored status.
"""

from __future__ import annotations

import re
from datetime import date
from enum import Enum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.eligibility import EligibilityState, JobId, RequirementResult
from app.schemas.job import JobStatusSchema

#: Maximum number of tracker rows in one export (A-31). Bounds the work and the file size.
MAX_TRACKER_ROWS = 500

#: Maximum requirement-breakdown entries per row. A job states at most one requirement of each of
#: the five types; the headroom tolerates a client that merges several evaluations.
MAX_REQUIREMENTS_PER_ROW = 20

#: Maximum length of any text inside a supplied requirement breakdown.
MAX_REQUIREMENT_TEXT = 1000

#: Characters a worksheet cannot store: C0 controls except tab, line feed and carriage return.
#: Rejected at the boundary so they surface as a 422, not a 500 from the workbook writer.
_UNSTORABLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _check_storable(value: str | None) -> str | None:
    """Reject text a worksheet cannot hold. The message never contains the value (INV-4)."""
    if value is not None and _UNSTORABLE.search(value):
        raise ValueError("contains control characters that cannot be stored in a worksheet")
    return value


class ApplicationStatus(str, Enum):
    """Where the candidate is with an application — dossier §10.1, exactly.

    Written by the client, on the client (ADR-002). The server only renders it. Add members,
    never rename or remove them (ADR-010).
    """

    NOT_APPLIED = "NOT_APPLIED"
    APPLIED = "APPLIED"
    INTERVIEW = "INTERVIEW"
    REJECTED = "REJECTED"
    OFFER = "OFFER"


class TrackerRecord(BaseModel):
    """One tracker row, as the client holds it."""

    model_config = ConfigDict(extra="forbid")

    job_id: JobId = Field(description="Catalogue job id. Unique within one export.")
    company_name: str = Field(max_length=200)
    role_title: str = Field(max_length=200)
    apply_link: str | None = Field(
        default=None,
        max_length=2048,
        description="Written as plain text. Never turned into a clickable hyperlink.",
    )
    deadline: date | None = Field(default=None, description="Written as an Excel date.")
    job_status: JobStatusSchema | None = None
    eligibility_state: EligibilityState | None = None
    match_score: float | None = Field(
        default=None,
        ge=0,
        le=100,
        allow_inf_nan=False,
        description=(
            "Relevance score 0–100 as returned by `/recommendations`. Null is not zero: a null "
            "score is written as an empty cell."
        ),
    )
    reason: str | None = Field(
        default=None,
        max_length=1000,
        description="Human-readable explanation — typically the recommendation explanation.",
    )
    application_status: ApplicationStatus = ApplicationStatus.NOT_APPLIED
    evaluated_at: AwareDatetime | None = Field(
        default=None,
        description=(
            "When the verdict was computed, with a time zone. Written in UTC; a time without a "
            "zone is rejected rather than guessed."
        ),
    )
    notes: str | None = Field(
        default=None,
        max_length=1000,
        description="The candidate's own notes. Written to the workbook; never logged.",
    )
    requirement_breakdown: list[RequirementResult] | None = Field(
        default=None,
        max_length=MAX_REQUIREMENTS_PER_ROW,
        description="Optional. When present, each entry becomes a row of the Requirements sheet.",
    )

    @field_validator("job_id", "company_name", "role_title", "apply_link", "reason", "notes")
    @classmethod
    def _storable(cls, value: str | None) -> str | None:
        return _check_storable(value)

    @field_validator("requirement_breakdown")
    @classmethod
    def _bounded_breakdown(
        cls, value: list[RequirementResult] | None
    ) -> list[RequirementResult] | None:
        """Bound and check the text of a reused :class:`RequirementResult`.

        The eligibility schema leaves these strings unbounded because the server writes them;
        here the client does, so they are bounded at this boundary instead.
        """
        for entry in value or []:
            for text in (entry.requirement, entry.candidate_value, entry.note):
                if text is not None and len(text) > MAX_REQUIREMENT_TEXT:
                    raise ValueError(
                        f"requirement text must be at most {MAX_REQUIREMENT_TEXT} characters"
                    )
                _check_storable(text)
        return value


class TrackerExportRequest(BaseModel):
    """Request body for ``POST /api/v1/applications/export``."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "records": [
                    {
                        "job_id": "example-job-1",
                        "company_name": "Example Co",
                        "role_title": "Software Engineering Intern",
                        "apply_link": "https://example.com/careers/1",
                        "deadline": "2026-11-15",
                        "job_status": "ACTIVE",
                        "eligibility_state": "ELIGIBLE",
                        "match_score": 73.2,
                        "reason": "Eligible. Meets all stated requirements.",
                        "application_status": "APPLIED",
                        "evaluated_at": "2026-09-19T10:00:00Z",
                        "notes": "Referral requested.",
                    },
                    {
                        "job_id": "example-job-2",
                        "company_name": "Sample Labs",
                        "role_title": "Data Analyst Intern",
                        "eligibility_state": "NOT_ELIGIBLE",
                        "match_score": None,
                        "reason": "Not eligible: minimum CGPA not met.",
                    },
                ]
            }
        },
    )

    records: list[TrackerRecord] = Field(
        min_length=1,
        max_length=MAX_TRACKER_ROWS,
        description=(
            f"1 to {MAX_TRACKER_ROWS} rows, written in this order. Each `job_id` may appear once."
        ),
    )

    @model_validator(mode="after")
    def _unique_job_ids(self) -> TrackerExportRequest:
        """Reject a repeated ``job_id`` rather than silently dropping one of the rows."""
        seen: set[str] = set()
        for record in self.records:
            if record.job_id in seen:
                raise ValueError("each job_id may appear only once")
            seen.add(record.job_id)
        return self
