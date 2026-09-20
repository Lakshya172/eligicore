"""Application-package schemas (ADR-025).

Slice 7A ships the vocabulary of **truthfulness validation**: what a claim is, why a claim was
removed, where it was removed from, and how a finished package reports itself. The package
request and response models arrive with the endpoint in Slice 7B — this module deliberately
contains no request model, because 7A adds no API surface.

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

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

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
