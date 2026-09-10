"""Resume extraction schemas.

Two distinct layers, deliberately not merged:

* :class:`ResumeExtraction` — the shape the **AI provider** must return. Provider output is
  untrusted input and is validated against this before it reaches any service
  (``standards/ai.md`` §4). Every field is optional, because a resume genuinely may not
  contain it and an absent field must stay absent rather than being invented.
* :class:`ResumeParseResponse` — what the **API** returns: a canonical
  :class:`~app.schemas.candidate.CandidateProfile` plus per-field confidence, issues, and
  safe extraction metadata.

Keeping them separate means a change to a provider's output shape cannot silently change
the public API contract.

Nothing here is persisted. The client receives the parsed profile and stores it locally
(ADR-001, ADR-002).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.candidate import (
    CandidateProfile,
    Confidence,
    DegreeLevel,
    GradeScale,
    ValidationIssue,
)

# ---------------------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------------------


class SourceFormat(str, Enum):
    """Document format a resume was supplied in."""

    PDF = "PDF"
    DOCX = "DOCX"


class ResumeParseStatus(str, Enum):
    """Outcome of a parse, as a product-level statement rather than an HTTP code.

    ``NEEDS_REVIEW`` is a real, useful outcome — not a failure. It means text was extracted
    but the structured result cannot be trusted without a human looking at it, which is
    exactly what the dossier's workflow expects the candidate to do at §7 step 3.
    """

    PARSED = "PARSED"
    PARTIAL = "PARTIAL"
    NEEDS_REVIEW = "NEEDS_REVIEW"


# ---------------------------------------------------------------------------------------
# AI extraction contract — what a provider must return
# ---------------------------------------------------------------------------------------


class ExtractedEducation(BaseModel):
    """One education record as reported by the extraction model.

    ``scale`` defaults to UNKNOWN. A model that reports a grade without a scale must not
    have one inferred for it — 8.2 out of 10 and 8.2 out of 4 are different facts
    (``standards/eligibility.md`` §4).
    """

    model_config = ConfigDict(extra="ignore")

    degree: str | None = None
    level: DegreeLevel = DegreeLevel.UNKNOWN
    field_of_study: str | None = None
    institution: str | None = None
    grad_year: int | None = None
    cgpa: float | None = None
    scale: GradeScale = GradeScale.UNKNOWN


class ExtractedExperience(BaseModel):
    """One experience record as reported by the extraction model."""

    model_config = ConfigDict(extra="ignore")

    title: str | None = None
    company: str | None = None
    duration: str | None = None
    description: str | None = None


class ExtractedProject(BaseModel):
    """One project as reported by the extraction model."""

    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    description: str | None = None


class ExtractedCertification(BaseModel):
    """One certification as reported by the extraction model."""

    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    issuer: str | None = None
    year: int | None = None


class ResumeExtraction(BaseModel):
    """The validated structured result of an AI extraction.

    ``extra="ignore"`` rather than ``"forbid"``: a model that volunteers an extra key should
    not fail the whole extraction. Unknown keys are dropped, which is safer than either
    trusting them or rejecting the response.

    Every field is optional. **An absent field means the resume did not clearly state it**,
    and it stays absent — the parser does not fill gaps, and neither may the model
    (dossier §6: "It does not fabricate anything").
    """

    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None

    education: list[ExtractedEducation] = Field(default_factory=list)
    experience: list[ExtractedExperience] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    projects: list[ExtractedProject] = Field(default_factory=list)
    certifications: list[ExtractedCertification] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)

    backlogs: int | None = Field(
        default=None,
        description=(
            "Active backlog count. None means the resume did not state one — which is NOT "
            "the same as zero, and must never be coerced into zero (INV-3)."
        ),
    )

    field_confidence: dict[str, Confidence] = Field(
        default_factory=dict,
        description=(
            "The model's own per-field confidence. Advisory only: the parser applies "
            "deterministic rules on top, and a deterministic rule always wins."
        ),
    )


# ---------------------------------------------------------------------------------------
# API response
# ---------------------------------------------------------------------------------------


class ExtractionMetadata(BaseModel):
    """Safe operational metadata about how a parse was performed.

    Everything here is technical and non-identifying — format, sizes, provider, model,
    timing. **No candidate data appears in this model**, so it is safe to log (INV-4).
    """

    model_config = ConfigDict(extra="forbid")

    source_format: SourceFormat
    characters_extracted: int = Field(
        ge=0, description="Length of extracted text. A count, never the text itself."
    )
    provider: str = Field(description="AI provider name, e.g. 'mock' or 'gemini'.")
    model: str = Field(description="Model identifier used for extraction.")
    duration_ms: float = Field(ge=0)


class ResumeParseResponse(BaseModel):
    """Response from ``POST /api/v1/resumes/parse``.

    Returns the parsed profile with per-field confidence, plus anything the client should
    ask the candidate to check (dossier §11, §7 step 3).

    **The uploaded file is gone by the time this is returned** — deleted after processing
    whether it succeeded or failed (INV-11). The client persists both the file and this
    result locally; the backend keeps neither.
    """

    model_config = ConfigDict(extra="forbid")

    candidate_id: str | None = Field(
        default=None,
        description="Echoed from the request if supplied. Client-generated correlation id.",
    )
    status: ResumeParseStatus
    profile: CandidateProfile = Field(
        description="Parsed profile in canonical shape. Not stored server-side."
    )
    field_confidence: dict[str, Confidence] = Field(
        default_factory=dict,
        description=(
            "Per-field confidence, keyed by dotted field path. Describes how much the "
            "system trusts its own extraction — it says nothing about eligibility."
        ),
    )
    issues: list[ValidationIssue] = Field(
        default_factory=list,
        description=(
            "Gaps, uncertainties and untraceable claims. Field paths and reasons only — "
            "never the offending value."
        ),
    )
    metadata: ExtractionMetadata
