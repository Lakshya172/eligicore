"""Candidate profile schemas.

The candidate profile is a **stateless request payload**. It is validated, normalized and
returned; it is never persisted server-side (ADR-001, ADR-002, ADR-011, INV-1).

Field shape follows the dossier §10.1 candidate object store. Two dossier fields are
deliberately absent: ``created_at`` and ``updated_at`` are client-store metadata owned by
IndexedDB, not by an API that holds no record.

**Design stance — the profile is permissive.** Almost every field is optional, because the
dossier's workflow (§7 steps 2–3) has a resume parsed into a partial profile which the
candidate then completes. Structural problems (wrong types, impossible values) are rejected
by Pydantic; *gaps* are reported as issues by ``/validate`` rather than rejected. Making
fields required here would turn "we don't know yet" into "invalid", which is exactly the
mistake INV-3 exists to prevent.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# ---------------------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------------------


class GradeScale(str, Enum):
    """The grading system a CGPA or grade is expressed on.

    A grade without its scale is meaningless: ``8.2`` on :attr:`SCALE_10` and ``3.6`` on
    :attr:`SCALE_4` are not comparable, and neither is comparable to a percentage.

    :attr:`UNKNOWN` is a first-class value, not an error. When the scale is absent it stays
    UNKNOWN — it is never guessed and never defaulted to a 10-point scale
    (``standards/eligibility.md`` §4). Downstream eligibility evaluation treats an unknown
    scale as ``UNKNOWN``, never as a failure (INV-3).
    """

    SCALE_4 = "SCALE_4"
    SCALE_5 = "SCALE_5"
    SCALE_10 = "SCALE_10"
    PERCENTAGE = "PERCENTAGE"
    UNKNOWN = "UNKNOWN"

    @property
    def maximum(self) -> float | None:
        """The maximum attainable value on this scale, or None when unknown."""
        return _SCALE_MAXIMA.get(self)


_SCALE_MAXIMA: dict[GradeScale, float] = {
    GradeScale.SCALE_4: 4.0,
    GradeScale.SCALE_5: 5.0,
    GradeScale.SCALE_10: 10.0,
    GradeScale.PERCENTAGE: 100.0,
}


class DegreeLevel(str, Enum):
    """Level of a qualification, kept universal rather than country-specific."""

    HIGH_SCHOOL = "HIGH_SCHOOL"
    DIPLOMA = "DIPLOMA"
    BACHELORS = "BACHELORS"
    MASTERS = "MASTERS"
    DOCTORATE = "DOCTORATE"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class JobType(str, Enum):
    """Job types the candidate is interested in (dossier §10.2 ``job_type``)."""

    INTERNSHIP = "INTERNSHIP"
    FULL_TIME = "FULL_TIME"


class WorkMode(str, Enum):
    """Preferred working arrangement."""

    REMOTE = "REMOTE"
    ONSITE = "ONSITE"
    HYBRID = "HYBRID"
    ANY = "ANY"


class Confidence(str, Enum):
    """How much the system trusts a determination — not how good the news is.

    Independent of eligibility, per ADR-003. Used here for per-field parsing confidence
    (dossier §10.1 ``field_confidence``); reused by the eligibility engine in Week 4.
    """

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


# ---------------------------------------------------------------------------------------
# Shared field types
# ---------------------------------------------------------------------------------------

ShortText = Annotated[str, Field(min_length=1, max_length=200)]
LongText = Annotated[str, Field(min_length=1, max_length=5000)]

# Graduation years are bounded to catch parse errors (a resume yielding year 20255) while
# staying wide enough to accept past qualifications and future expected completion.
GraduationYear = Annotated[int, Field(ge=1950, le=2100)]


# ---------------------------------------------------------------------------------------
# Profile components
# ---------------------------------------------------------------------------------------


class EducationEntry(BaseModel):
    """One qualification.

    Education is a list rather than flat columns because candidates hold multiple
    qualifications and education systems differ (dossier §10.1 design note). Keeping
    ``cgpa`` and ``scale`` together on the same entry is what makes cross-system
    comparison possible later.
    """

    model_config = ConfigDict(extra="forbid")

    degree: ShortText = Field(description="Qualification name, e.g. 'B.Tech', 'BSc'.")
    level: DegreeLevel = Field(
        default=DegreeLevel.UNKNOWN,
        description="Degree level. UNKNOWN when it cannot be determined; never guessed.",
    )
    field_of_study: ShortText | None = Field(
        default=None, description="Branch or major, e.g. 'Information Technology'."
    )
    institution: ShortText | None = None
    grad_year: GraduationYear | None = Field(
        default=None, description="Graduation year, actual or expected."
    )
    cgpa: float | None = Field(
        default=None,
        ge=0,
        description="Grade value. Meaningless without `scale` — always read them together.",
    )
    scale: GradeScale = Field(
        default=GradeScale.UNKNOWN,
        description=(
            "Grading system for `cgpa`. Defaults to UNKNOWN when absent and is never "
            "inferred. UNKNOWN is a valid state, not an error."
        ),
    )

    @property
    def has_known_scale(self) -> bool:
        """True when a grade is present *and* its scale is known."""
        return self.cgpa is not None and self.scale is not GradeScale.UNKNOWN

    @field_validator("cgpa")
    @classmethod
    def _reject_non_finite(cls, value: float | None) -> float | None:
        """Reject NaN and infinity, which pass ``ge=0`` but poison every comparison."""
        if value is not None and value != value:  # NaN
            raise ValueError("cgpa must be a finite number")
        if value in (float("inf"), float("-inf")):
            raise ValueError("cgpa must be a finite number")
        return value

    @field_validator("scale", mode="before")
    @classmethod
    def _scale_never_none(cls, value: object) -> object:
        """Treat an explicit ``null`` scale as UNKNOWN.

        Must run in ``before`` mode: an ``after`` validator never sees ``None``, because
        enum coercion rejects it first. Semantically ``"scale": null`` and an omitted
        ``scale`` say the same thing — the scale is not known — and both must land on
        UNKNOWN rather than a 422 (``standards/eligibility.md`` §3).
        """
        return GradeScale.UNKNOWN if value is None else value


class ExperienceEntry(BaseModel):
    """One work experience record (dossier §10.1)."""

    model_config = ConfigDict(extra="forbid")

    title: ShortText
    company: ShortText | None = None
    duration: ShortText | None = Field(
        default=None,
        description="Free text as it appeared, e.g. 'Jun 2025 - Aug 2025'. Not parsed here.",
    )
    description: LongText | None = None


class ProjectEntry(BaseModel):
    """One project (dossier §10.1 supporting profile data)."""

    model_config = ConfigDict(extra="forbid")

    name: ShortText
    description: LongText | None = None


class CertificationEntry(BaseModel):
    """One certification (dossier §10.1 supporting profile data)."""

    model_config = ConfigDict(extra="forbid")

    name: ShortText
    issuer: ShortText | None = None
    year: GraduationYear | None = None


class CandidatePreferences(BaseModel):
    """Search preferences (dossier §10.1: location, job type, remote/onsite)."""

    model_config = ConfigDict(extra="forbid")

    locations: list[ShortText] = Field(default_factory=list)
    job_types: list[JobType] = Field(default_factory=list)
    work_mode: WorkMode = WorkMode.ANY


# ---------------------------------------------------------------------------------------
# The profile
# ---------------------------------------------------------------------------------------


class CandidateProfile(BaseModel):
    """A complete candidate profile, as sent by the client on every request.

    This is never stored server-side. ``candidate_id`` is a **client-generated correlation
    identifier**, not a server lookup key (ADR-002).
    """

    model_config = ConfigDict(extra="forbid")

    candidate_id: str | None = Field(
        default=None,
        max_length=100,
        description=(
            "Client-generated stable identifier used to correlate operations across "
            "requests. NOT a pointer to any server-side record — none exists."
        ),
    )

    name: ShortText | None = None
    email: EmailStr | None = None
    phone: ShortText | None = None
    location: ShortText | None = None

    education: list[EducationEntry] = Field(default_factory=list)
    experience: list[ExperienceEntry] = Field(default_factory=list)
    skills: list[ShortText] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)
    certifications: list[CertificationEntry] = Field(default_factory=list)
    languages: list[ShortText] = Field(default_factory=list)

    backlogs: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Active backlog count. None means UNKNOWN, which is NOT the same as zero — "
            "defaulting an unknown to 0 would silently invent a passing value (INV-3)."
        ),
    )

    preferences: CandidatePreferences = Field(default_factory=CandidatePreferences)

    resume_raw_text: str | None = Field(
        default=None,
        max_length=100_000,
        description="Raw resume text, retained by the CLIENT for re-parsing. Never logged.",
    )
    field_confidence: dict[str, Confidence] = Field(
        default_factory=dict,
        description="Per-field parsing confidence, keyed by field name.",
    )


# ---------------------------------------------------------------------------------------
# Validation reporting
# ---------------------------------------------------------------------------------------


class IssueSeverity(str, Enum):
    """How much a reported issue matters.

    ERROR means the profile cannot be used as-is. WARNING means it is usable but a later
    stage will be unable to reach a confident answer. INFO is advisory.
    """

    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class ValidationIssue(BaseModel):
    """A single finding about a profile.

    Carries a machine-readable ``code`` and a dotted ``field`` path. It deliberately does
    **not** carry the offending value — echoing candidate data back would leak PII into
    client logs and error trackers (INV-4).
    """

    model_config = ConfigDict(extra="forbid")

    field: str = Field(description="Dotted path, e.g. 'education[0].scale'.")
    code: str = Field(description="Stable machine-readable code, e.g. 'MISSING_SCALE'.")
    message: str = Field(description="Human-readable explanation. Contains no field value.")
    severity: IssueSeverity


class CandidateValidationResponse(BaseModel):
    """Response from ``POST /api/v1/candidates/validate``.

    Returns the canonical profile shape plus any issues found (dossier §11).
    """

    model_config = ConfigDict(extra="forbid")

    candidate_id: str | None = Field(
        default=None, description="Echoed back from the request for client correlation."
    )
    is_valid: bool = Field(
        description="True when no ERROR-severity issues were found. Warnings do not block."
    )
    issues: list[ValidationIssue] = Field(default_factory=list)
    profile: CandidateProfile = Field(
        description="The profile in canonical shape. Not stored — returned for the client."
    )


class CandidateNormalizationResponse(BaseModel):
    """Response from ``POST /api/v1/candidates/normalize``."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str | None = None
    profile: CandidateProfile = Field(description="The normalized profile.")
    normalized_grades: list[NormalizedGrade] = Field(
        default_factory=list,
        description=(
            "Scale-normalized view of each education entry, positionally aligned with "
            "`profile.education`. Entries with an unknown scale carry a null fraction — "
            "they are not guessed."
        ),
    )
    changes: list[str] = Field(
        default_factory=list,
        description=(
            "Human-readable summary of what normalization changed, by field path. Contains "
            "no candidate values."
        ),
    )


class NormalizedGrade(BaseModel):
    """A grade expressed as a scale-independent fraction, when that is possible at all.

    ``fraction`` is ``cgpa / scale_maximum`` — so 8.2/10 and 3.28/4 both yield 0.82, which
    is what makes cross-system comparison possible in Week 4.

    When the scale is UNKNOWN, ``fraction`` is ``None``. That is the whole point: an
    unknown scale stays unknown rather than being silently treated as a 10-point scale
    (``standards/eligibility.md`` §4). Week 4 maps a null fraction to ``UNKNOWN``, never to
    a failure (INV-3).
    """

    model_config = ConfigDict(extra="forbid")

    education_index: int = Field(ge=0)
    cgpa: float | None = None
    scale: GradeScale
    fraction: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="cgpa / scale maximum. None when the grade or its scale is unknown.",
    )


CandidateNormalizationResponse.model_rebuild()
