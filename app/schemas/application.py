"""Application-package schemas (ADR-025).

Two layers live here, and the split is the point.

**The vocabulary of truthfulness validation** (Slice 7A): what a claim is, why a claim was
removed, where it was removed from, and how a finished package reports itself.

**The package contract** (Slice 7B): the request, the response, and — separately — the three
**projections** that are the privacy boundary. :class:`ApplicationEvidence`, :class:`JobBrief`
and :class:`GenerationLimits` are the *only* shapes an AI provider is given, and
:class:`ApplicationDraft` is the only shape it may return. A provider is never handed a
:class:`~app.schemas.candidate.CandidateProfile`: the excluded fields are not filtered out of
the evidence model, they are **absent from it**, so no future edit can forward one by accident
(D10).

Contract rules, from ADR-025:

* **Remove by default** (D5). A claim that cannot be traced to the supplied profile is removed
  before the response is constructed, and the removal is disclosed. There is no warn-only mode
  and no flag that disables removal, so nothing here is configurable.
* **The knowledge boundary** (D12). A claim in a category the model was never given is
  untraceable *by construction* — a guess that happens to match the profile is still a guess.
  :attr:`ClaimCategory.EXCLUDED_DATA` and
  :attr:`RemovalReason.CLAIM_OUTSIDE_KNOWLEDGE_BOUNDARY` name that case.
* **Nothing is stored** (D13, ADR-011). These are data-in-flight shapes: no model, no table, no
  migration. A ``RemovedClaim`` exists for the length of one response.
* The eligibility ``ReasonCode`` enum is **not** extended (ADR-010). Generated-content vocabulary
  lives here; eligibility vocabulary stays in :mod:`app.schemas.eligibility`.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.schemas.candidate import CandidateProfile, Confidence, DegreeLevel
from app.schemas.eligibility import EvaluationMethod, JobId

#: Maximum length of the disclosed text of one removed unit. Longer text is cut at a word
#: boundary and flagged, so an audit list cannot grow without bound.
MAX_REMOVED_CLAIM_TEXT = 500


class PackageStatus(str, Enum):
    """What survived validation — never what the provider did (ADR-025 § Failure semantics)."""

    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    NOTHING_VERIFIABLE = "NOTHING_VERIFIABLE"


class GenerationOutcome(str, Enum):
    """What the provider did — never what survived validation.

    Kept separate from :class:`PackageStatus` so a package whose content was generated and then
    entirely removed reports ``GENERATED`` with ``NOTHING_VERIFIABLE``: two different facts, and
    collapsing them would hide one of them.
    """

    GENERATED = "GENERATED"
    AI_GENERATION_UNAVAILABLE = "AI_GENERATION_UNAVAILABLE"
    AI_GENERATION_INVALID = "AI_GENERATION_INVALID"
    AI_GENERATION_EMPTY = "AI_GENERATION_EMPTY"


class AnswerOutcome(str, Enum):
    """Per-answer result, so one failed answer never mislabels the whole package."""

    GENERATED = "GENERATED"
    REMOVED_ENTIRELY = "REMOVED_ENTIRELY"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID = "INVALID"
    EMPTY = "EMPTY"
    REQUIRES_EXCLUDED_DATA = "REQUIRES_EXCLUDED_DATA"


class ClaimCategory(str, Enum):
    """The kinds of assertion validation checks.

    The first six are dossier §12.3's own list — *"a skill, project, duration or achievement"* —
    split into the forms a sentence actually takes. ``EXCLUDED_DATA`` is the knowledge boundary:
    a claim about data the provider was never given (ADR-025 D10, D12).
    """

    SKILL = "SKILL"
    PROJECT = "PROJECT"
    EMPLOYMENT = "EMPLOYMENT"
    DURATION = "DURATION"
    CREDENTIAL = "CREDENTIAL"
    QUANTITY = "QUANTITY"
    EXCLUDED_DATA = "EXCLUDED_DATA"


class RemovalReason(str, Enum):
    """Why a unit was removed. Every removal carries one; silence is not an option (D5)."""

    CLAIM_NOT_TRACEABLE = "CLAIM_NOT_TRACEABLE"
    CLAIM_EXCEEDS_PROFILE_VALUE = "CLAIM_EXCEEDS_PROFILE_VALUE"
    CLAIM_OUTSIDE_KNOWLEDGE_BOUNDARY = "CLAIM_OUTSIDE_KNOWLEDGE_BOUNDARY"
    ANSWER_REQUIRES_EXCLUDED_DATA = "ANSWER_REQUIRES_EXCLUDED_DATA"


class RemovalScope(str, Enum):
    """Where a removal happened, so the aggregate list stays filterable back to locality."""

    COVER_LETTER = "COVER_LETTER"
    ANSWER = "ANSWER"


class RemovedClaim(BaseModel):
    """One removed unit, disclosed to the caller.

    ``text`` is the unit **as it stood before removal**, not a rewrite. No character offsets are
    carried: the pre-removal draft is never returned, so an offset would point at nothing.
    """

    model_config = ConfigDict(extra="forbid")

    text: str = Field(
        max_length=MAX_REMOVED_CLAIM_TEXT,
        description="The removed sentence or list item, verbatim, truncated if very long.",
    )
    truncated: bool = Field(
        default=False,
        description="True when `text` was cut at a word boundary to fit the disclosure limit.",
    )
    category: ClaimCategory
    reason: RemovalReason
    scope: RemovalScope
    question_id: str | None = Field(
        default=None,
        max_length=64,
        description="The question this removal belongs to; null for cover-letter scope.",
    )


# ---------------------------------------------------------------------------------------
# Slice 7B — bounds
# ---------------------------------------------------------------------------------------

#: Questions one request may carry (ADR-025 D9). Small on purpose: a package a human must read
#: before sending stops being reviewable long before it stops being generatable.
MAX_QUESTIONS = 5

#: Longest employer question accepted, after stripping.
MAX_QUESTION_TEXT = 500

#: Longest question identifier.
MAX_QUESTION_ID = 64

#: Question ids are opaque client tokens, not free text: restricting the alphabet keeps them safe
#: to echo back in a ``RemovedClaim.question_id``.
QUESTION_ID_PATTERN = r"^[A-Za-z0-9._:-]{1,64}$"

MIN_ANSWER_WORDS = 20
MAX_ANSWER_WORDS = 250
MIN_COVER_LETTER_WORDS = 50
MAX_COVER_LETTER_WORDS = 400

#: Job description characters sent to a provider (D10). Truncation, not rejection: a long posting
#: is normal, and the tail rarely says anything the first paragraphs have not.
MAX_JOB_DESCRIPTION_CHARS = 4000

#: Hard character ceiling on any one piece of generated text. The **word** limits are the
#: contract; this is the structural bound that stops a runaway provider handing the validator an
#: unbounded string. Exceeding it makes the whole draft invalid — a reply this far outside the
#: requested shape is not a near miss.
MAX_DRAFT_TEXT = 20_000

#: Characters no supplied or generated text may carry: C0 controls except tab, line feed and
#: carriage return. Rejected at the boundary exactly as in :mod:`app.schemas.tracker`.
_UNSTORABLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _reject_control_characters(value: str) -> str:
    """Raise if ``value`` carries a control character. The message never echoes it (INV-4)."""
    if _UNSTORABLE.search(value):
        raise ValueError("contains control characters that are not allowed")
    return value


# ---------------------------------------------------------------------------------------
# Slice 7B — request
# ---------------------------------------------------------------------------------------


class ApplicationQuestion(BaseModel):
    """One employer question, **supplied by the client** (D3).

    Never inferred from the job description, the apply link or anywhere else: no dossier data
    model carries employer questions, so any the server invented would be its own.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        min_length=1,
        max_length=MAX_QUESTION_ID,
        pattern=QUESTION_ID_PATTERN,
        description="Client-chosen identifier, unique within the request. Echoed on the answer.",
    )
    text: str = Field(
        min_length=1,
        max_length=MAX_QUESTION_TEXT,
        description="The question as the employer asks it. Stripped; control characters rejected.",
    )
    max_words: int | None = Field(
        default=None,
        ge=MIN_ANSWER_WORDS,
        le=MAX_ANSWER_WORDS,
        description="Word limit for this answer. Omitted: the request-level `answer_max_words`.",
    )

    @field_validator("text", mode="before")
    @classmethod
    def _strip_and_check(cls, value: object) -> object:
        """Strip first, so a whitespace-only question fails the length bound rather than passing."""
        if isinstance(value, str):
            return _reject_control_characters(value.strip())
        return value


class ApplicationPrepareRequest(BaseModel):
    """Request body for ``POST /api/v1/applications/prepare``.

    ``extra="forbid"`` does real work here: it is what rejects a **client-supplied job object**
    (D2) and any ``validate=false``-shaped escape hatch (D5). Neither was forgotten — a caller
    must not be able to describe the job, or weaken removal, at all.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "profile": {
                    "candidate_id": "client-generated-example-id",
                    "skills": ["Python", "FastAPI"],
                    "experience": [
                        {
                            "title": "Backend Engineering Intern",
                            "duration": "Jun 2026 - Aug 2026",
                            "description": "Built internal reporting tooling in Python.",
                        }
                    ],
                    "education": [
                        {
                            "degree": "B.Tech",
                            "level": "BACHELORS",
                            "field_of_study": "Information Technology",
                            "grad_year": 2027,
                        }
                    ],
                },
                "job_id": "00000000-0000-0000-0000-000000000000",
                "questions": [
                    {"id": "q1", "text": "Why do you want this role?", "max_words": 120}
                ],
                "include_cover_letter": True,
            }
        },
    )

    profile: CandidateProfile = Field(
        description="The candidate profile, supplied by the client. Validated against, never stored."
    )
    job_id: JobId = Field(
        description="Exactly one catalogue job id. An unknown id is a 404, not a partial result."
    )
    questions: list[ApplicationQuestion] = Field(
        default_factory=list,
        max_length=MAX_QUESTIONS,
        description="At most five employer questions, each with a unique `id`.",
    )
    include_cover_letter: bool = Field(
        default=True, description="Whether to prepare a cover letter."
    )
    cover_letter_max_words: int = Field(
        default=MAX_COVER_LETTER_WORDS,
        ge=MIN_COVER_LETTER_WORDS,
        le=MAX_COVER_LETTER_WORDS,
        description="Cover-letter word limit. Enforced after generation, never by truncation.",
    )
    answer_max_words: int = Field(
        default=MAX_ANSWER_WORDS,
        ge=MIN_ANSWER_WORDS,
        le=MAX_ANSWER_WORDS,
        description="Default word limit per answer; a question's own `max_words` overrides it.",
    )

    @field_validator("questions")
    @classmethod
    def _unique_question_ids(
        cls, value: list[ApplicationQuestion]
    ) -> list[ApplicationQuestion]:
        """Reject duplicate ids rather than silently answering one question twice.

        Mirrors ``TrackerExportRequest._unique_job_ids``: the id is how an answer and a removal
        are correlated, so two questions sharing one makes the response ambiguous.
        """
        if len({question.id for question in value}) != len(value):
            raise ValueError("question ids must be unique within a request")
        return value

    @model_validator(mode="after")
    def _something_was_requested(self) -> ApplicationPrepareRequest:
        """No cover letter and no questions asks for nothing, and is rejected (ADR-025).

        Rejected at the boundary, so no provider is built and no AI call is made — rather than
        inventing a "nothing requested" package status for an empty package.
        """
        if not self.include_cover_letter and not self.questions:
            raise ValueError(
                "request must ask for a cover letter, at least one question, or both"
            )
        return self


# ---------------------------------------------------------------------------------------
# Slice 7B — the provider boundary (D10)
# ---------------------------------------------------------------------------------------


class EvidenceExperience(BaseModel):
    """One experience record, **without the employer's name** (D10, D12).

    ``company`` is absent by design: a generator that never saw an employer name cannot write a
    sentence claiming one, and the validator removes any sentence that does anyway.
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    duration: str | None = None
    description: str | None = None


class EvidenceProject(BaseModel):
    """One project, re-projected field by field rather than passed as the profile's own object."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None


class EvidenceCertification(BaseModel):
    """One certification — the name only. Issuer and year stay behind (D10)."""

    model_config = ConfigDict(extra="forbid")

    name: str


class EvidenceEducation(BaseModel):
    """One qualification, without institution, grade or scale (D10, D12)."""

    model_config = ConfigDict(extra="forbid")

    degree: str | None = None
    level: DegreeLevel = DegreeLevel.UNKNOWN
    field_of_study: str | None = None
    grad_year: int | None = None


class ApplicationEvidence(BaseModel):
    """Everything about the candidate a provider may see. Nothing else exists here.

    The D10 allow-list expressed as a type. ``candidate_id``, ``name``, ``email``, ``phone``,
    ``location``, ``languages``, ``backlogs``, ``preferences``, ``field_confidence``,
    ``resume_raw_text``, ``experience[].company``, ``education[].institution``,
    ``education[].cgpa``, ``education[].scale``, ``certifications[].issuer`` and
    ``certifications[].year`` have **no field to travel in**.
    """

    model_config = ConfigDict(extra="forbid")

    skills: list[str] = Field(default_factory=list)
    experience: list[EvidenceExperience] = Field(default_factory=list)
    projects: list[EvidenceProject] = Field(default_factory=list)
    certifications: list[EvidenceCertification] = Field(default_factory=list)
    education: list[EvidenceEducation] = Field(default_factory=list)


class JobBrief(BaseModel):
    """The job as a provider sees it — public catalogue data only.

    ``company_name`` comes from the resolved catalogue job and nowhere else: the request cannot
    carry a job object, so a caller cannot name the target company themselves.
    """

    model_config = ConfigDict(extra="forbid")

    job_id: str
    company_name: str
    role_title: str
    description: str = Field(
        default="",
        max_length=MAX_JOB_DESCRIPTION_CHARS,
        description="Normalized posting text, truncated. Untrusted: passed as data, never as instructions.",
    )
    required_skills: list[str] = Field(default_factory=list)


class GenerationLimits(BaseModel):
    """What to write and how long it may be. Sent to the provider *and* enforced afterwards (D9)."""

    model_config = ConfigDict(extra="forbid")

    include_cover_letter: bool = True
    cover_letter_max_words: int = Field(
        default=MAX_COVER_LETTER_WORDS, ge=MIN_COVER_LETTER_WORDS, le=MAX_COVER_LETTER_WORDS
    )
    answer_max_words: int = Field(
        default=MAX_ANSWER_WORDS, ge=MIN_ANSWER_WORDS, le=MAX_ANSWER_WORDS
    )


class DraftAnswer(BaseModel):
    """One answer as the provider returned it. Untrusted input until validated."""

    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(min_length=1, max_length=MAX_QUESTION_ID)
    text: str = Field(max_length=MAX_DRAFT_TEXT)


class ApplicationDraft(BaseModel):
    """Raw provider output.

    **This object never reaches a caller.** It is validated claim by claim and only the sanitized
    result is assembled into an :class:`ApplicationPrepareResponse` (D5).
    """

    model_config = ConfigDict(extra="forbid")

    cover_letter: str | None = Field(default=None, max_length=MAX_DRAFT_TEXT)
    answers: list[DraftAnswer] = Field(default_factory=list, max_length=MAX_QUESTIONS)


# ---------------------------------------------------------------------------------------
# Slice 7B — response
# ---------------------------------------------------------------------------------------


class PreparedAnswer(BaseModel):
    """One answer, after validation.

    ``answer`` is ``null`` whenever nothing survived — removed entirely, never generated,
    invalid, or answerable only from data the provider was never given. ``outcome`` says which.
    """

    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(description="The `id` of the question this answers.")
    answer: str | None = Field(
        description="The sanitized answer, or null when nothing survived validation."
    )
    outcome: AnswerOutcome
    removed_claims: list[RemovedClaim] = Field(
        default_factory=list,
        description=(
            "Removals local to this answer. Every entry also appears in the top-level "
            "`removed_claims` aggregate."
        ),
    )


class ApplicationPrepareResponse(BaseModel):
    """Response from ``POST /api/v1/applications/prepare``.

    A **draft for a human to review**, never a submission (ADR-008, INV-10). Lists are always
    present and may be empty; only scalars are nullable — the convention
    :class:`~app.schemas.matching.RecommendationResponse` already set. Nothing here is stored.
    """

    model_config = ConfigDict(extra="forbid")

    candidate_id: str | None = Field(
        default=None, description="Echoed from the request for client-side correlation."
    )
    job_id: str
    company_name: str = Field(
        description="From the resolved catalogue job, never from the request."
    )
    role_title: str
    status: PackageStatus = Field(description="What survived validation.")
    generation_outcome: GenerationOutcome = Field(description="What the provider did.")
    cover_letter: str | None = Field(
        description="The sanitized letter, or null when none was requested or none survived."
    )
    answers: list[PreparedAnswer] = Field(
        default_factory=list, description="One entry per supplied question, in request order."
    )
    removed_claims: list[RemovedClaim] = Field(
        default_factory=list,
        description=(
            "The authoritative aggregate: every cover-letter removal plus a copy of every "
            "per-answer removal, each tagged with its `scope` and `question_id`."
        ),
    )
    review_required: Literal[True] = Field(
        default=True,
        description=(
            "Always true. The package is prepared for a human to review; nothing is ever "
            "submitted automatically."
        ),
    )
    notice: str = Field(description="The no-submit notice, returned with every package.")
    provider: str = Field(description="AI provider that generated the draft.")
    model: str = Field(
        description="Model identifier, so a package can be traced to what wrote it."
    )
    method: EvaluationMethod = Field(
        default=EvaluationMethod.AI_REASONING,
        description="Always `ai_reasoning`: the prose is generated, the validation is not.",
    )
    confidence: Confidence = Field(
        description="Capped at MEDIUM for generated content; LOW once anything was removed."
    )
    validator_version: str = Field(description="Truthfulness validator rules version.")
    generated_at: AwareDatetime = Field(description="UTC time the package was prepared.")
