"""Job requirement extraction schemas (ADR-030).

The contract between an **extractor**, which proposes, and the **verifier**, which decides.
Nothing here is about a candidate: a job description is public source text, and no field in
this module may carry a profile, an identifier, a grade or any other personal data
(INV-1, ADR-030 D24). The signature is the boundary, as it is for every AI provider
operation (ADR-030 D13).

Three layers, kept separate on purpose and mirroring the job schemas' own split:

* :class:`ExtractionProposal` — what an **extractor** returns. Permissive by design, exactly
  as :class:`~app.schemas.job.RawJob` is permissive: an extractor states what it read, and
  the verifier decides whether that survives. A proposal is **not** a requirement.
* :class:`VerificationOutcome` — what the verifier says about one proposal, including every
  reason it was refused.
* :class:`VerifiedDerivedRequirement` — a proposal that passed **all eight** conditions of
  ADR-030 D6. This is the only shape that may ever reach evaluation or persistence.

**Permissiveness is deliberate.** Field constraints here are types, not rules: a CGPA of
``-1`` and a graduation year of ``9999`` are both constructible, and both are refused by
:mod:`app.services.requirement_verifier`. Enforcing the rules at construction would make the
verifier's own rejection paths unreachable, and ADR-030 D6 is explicit that *"the verifier is
the authority. The extractor — regex or model — produces a proposal."*

Two fields are **advisory and never authority**: ``reported_strength`` and
``reported_confidence``. They may cause a proposal to be refused sooner; they can never cause
one to be accepted (ADR-030 D7, D7a, D10a). Strength that gates eligibility is established by
the verifier from an explicit marker in the evidence, never read off the proposal.

Persistence fields — job id, pinned-text digest, row status, extraction timestamp — are
deliberately **absent**. They belong to the storage decision (ADR-030 D16-D19) and its own
implementation, not to the verification contract.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.candidate import Confidence, GradeScale
from app.schemas.eligibility import RequirementProvenance, RequirementType


class RequirementStrength(str, Enum):
    """How firmly a posting states a criterion (ADR-030 D10).

    ``REQUIRED`` is the **only** strength that satisfies D6 condition 7 and the only one that
    may participate in evaluation. The other three are disclosure or observation, never a
    gate: *"Students from CS/IT or related backgrounds preferred"* must never become an
    authoritative exclusion.
    """

    REQUIRED = "REQUIRED"
    PREFERRED = "PREFERRED"
    CONDITIONAL = "CONDITIONAL"
    INFORMATIONAL = "INFORMATIONAL"


# ---------------------------------------------------------------------------------------
# Typed requirement values — the Phase 1 scope, and nothing beyond it (ADR-030 D11)
# ---------------------------------------------------------------------------------------


class MinCgpaValue(BaseModel):
    """A minimum grade **and its scale**.

    The scale is part of the value, not an optional extra. ADR-030 D11 scopes Phase 1 to
    "CGPA **and its scale**", and a cutoff with no scale is not comparable to anything
    (``standards/eligibility.md`` §4) — the engine would only ever report it as
    ``JOB_SCALE_MISSING``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    requirement_type: Literal[RequirementType.MIN_CGPA] = RequirementType.MIN_CGPA
    min_cgpa: float
    min_cgpa_scale: GradeScale


class GradYearWindowValue(BaseModel):
    """A graduation-year bound, either end or both. Inclusive, as the engine reads them."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    requirement_type: Literal[RequirementType.GRAD_YEAR_WINDOW] = (
        RequirementType.GRAD_YEAR_WINDOW
    )
    min_grad_year: int | None = None
    max_grad_year: int | None = None


class MaxBacklogsValue(BaseModel):
    """A maximum permitted count of active backlogs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    requirement_type: Literal[RequirementType.MAX_BACKLOGS] = RequirementType.MAX_BACKLOGS
    max_backlogs: int


#: The three Phase 1 value shapes, discriminated by their own requirement type. A fourth
#: shape is a new ADR, not a new class: ADR-030 D12 excludes field ontology, degree-level
#: mapping, required skills and deadlines explicitly and permanently.
DerivedValue = Annotated[
    MinCgpaValue | GradYearWindowValue | MaxBacklogsValue,
    Field(discriminator="requirement_type"),
]

#: Requirement types a Phase 1 proposal may carry. A strict subset of ADR-018's five:
#: ``MIN_DEGREE_LEVEL`` and ``ALLOWED_FIELDS`` are excluded by ADR-030 D12 and are refused
#: by the verifier rather than silently ignored.
PHASE_1_REQUIREMENT_TYPES: frozenset[RequirementType] = frozenset(
    {
        RequirementType.MIN_CGPA,
        RequirementType.GRAD_YEAR_WINDOW,
        RequirementType.MAX_BACKLOGS,
    }
)


# ---------------------------------------------------------------------------------------
# The extractor's output
# ---------------------------------------------------------------------------------------


class ExtractionProposal(BaseModel):
    """One criterion an extractor claims to have read out of a job description.

    A proposal asserts nothing. It is an input to verification, and ADR-030 D6 discards it
    whole if any of the eight conditions fails — never downgraded, never retried with a lower
    bar, never surfaced as a weaker constraint.

    ``requirement_type`` is stated **separately** from ``value.requirement_type`` on purpose.
    An extractor that labels a proposal one thing and fills in another has made exactly the
    kind of mistake the verifier exists to catch, and collapsing the two fields would make
    that mistake unrepresentable rather than detectable.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    requirement_type: RequirementType = Field(
        description="The semantic type the extractor claims. Checked against `value`."
    )
    value: DerivedValue = Field(
        description="The typed criterion. Structural validity is the verifier's decision."
    )
    evidence_text: str = Field(
        description=(
            "The supporting text, **verbatim from the pinned normalized description** "
            "(ADR-030 D9). Character offsets are deliberately absent: an offset is valid "
            "only against one exact string, and a re-normalization or a source edit "
            "invalidates it silently. Evidence text is what is kept (D9, D18)."
        )
    )
    provenance: RequirementProvenance = Field(
        default=RequirementProvenance.PROSE_DERIVED,
        description=(
            "Always `PROSE_DERIVED` for anything read from a description. A proposal "
            "claiming `SOURCE_STATED` is refused: a source-stated requirement lives in a "
            "`jobs` column by definition (ADR-030 D1) and has no extraction path."
        ),
    )
    extractor: str = Field(
        min_length=1,
        max_length=100,
        description="Which extractor produced this, e.g. `deterministic.cgpa`.",
    )
    extractor_version: str = Field(
        min_length=1,
        max_length=50,
        description=(
            "Version of that extractor. Makes a stale extraction detectable from stored "
            "provenance rather than by bookkeeping (ADR-030 D18, D22)."
        ),
    )
    provider: str | None = Field(
        default=None,
        max_length=50,
        description="AI provider name where one was involved. Null for a deterministic extractor.",
    )
    model: str | None = Field(
        default=None,
        max_length=100,
        description="Model identifier where applicable. Null for a deterministic extractor.",
    )
    reported_strength: RequirementStrength | None = Field(
        default=None,
        description=(
            "**Advisory only.** What the extractor thinks the strength is. It may lower "
            "trust — a reported `PREFERRED` is refused early — and may never raise it. "
            "Condition 7 is satisfied only by the verifier recognising an explicit marker "
            "in `evidence_text` (ADR-030 D10a)."
        ),
    )
    reported_confidence: Confidence | None = Field(
        default=None,
        description=(
            "**Advisory only, and never evidence** (ADR-030 D7). A low confidence may cause "
            "a proposal to be discarded; a high one substitutes for nothing and is not an "
            "input to any of the eight conditions. A confidence score is a model's opinion "
            "of its own output, and admitting it as evidence would make the verifier a "
            "rubber stamp wearing a verifier's name."
        ),
    )


# ---------------------------------------------------------------------------------------
# The verifier's output
# ---------------------------------------------------------------------------------------


class VerificationFailure(str, Enum):
    """Why a proposal was refused. One member per distinct way a D6 condition can fail.

    Stable and machine-readable, following the ``ReasonCode`` convention (ADR-010): add
    members, never rename or remove them. Codes are deliberately fine-grained so that
    removing any single verifier check turns a specific, named test red.
    """

    # --- condition 3: supporting evidence text is returned -------------------------------
    EVIDENCE_EMPTY = "EVIDENCE_EMPTY"

    # --- condition 4: the evidence exists in the pinned normalized source text ------------
    EVIDENCE_NOT_IN_SOURCE = "EVIDENCE_NOT_IN_SOURCE"

    # --- condition 1: the source text explicitly contains the requirement ----------------
    VALUE_NOT_IN_EVIDENCE = "VALUE_NOT_IN_EVIDENCE"

    # --- condition 2: the extractor identifies a structurally valid requirement value ----
    MALFORMED_VALUE = "MALFORMED_VALUE"

    # --- condition 5: the value and type are supported by that evidence ------------------
    VALUE_NOT_SUPPORTED_BY_EVIDENCE = "VALUE_NOT_SUPPORTED_BY_EVIDENCE"

    # --- condition 6: the semantic requirement type is one the engine recognises ---------
    UNRECOGNISED_REQUIREMENT_TYPE = "UNRECOGNISED_REQUIREMENT_TYPE"
    REQUIREMENT_TYPE_MISMATCH = "REQUIREMENT_TYPE_MISMATCH"

    # --- condition 7: strength established as REQUIRED from an explicit marker -----------
    STRENGTH_NOT_ESTABLISHED = "STRENGTH_NOT_ESTABLISHED"
    STRENGTH_NOT_REQUIRED = "STRENGTH_NOT_REQUIRED"
    STRENGTH_AMBIGUOUS = "STRENGTH_AMBIGUOUS"

    # --- condition 8: nothing in the contradiction window invalidates the proposal -------
    CONTRADICTED_IN_WINDOW = "CONTRADICTED_IN_WINDOW"

    # --- provenance (ADR-030 D1) ---------------------------------------------------------
    PROVENANCE_NOT_DERIVED = "PROVENANCE_NOT_DERIVED"

    # --- collection-level (ADR-030 D8) ---------------------------------------------------
    COMPETING_PROPOSALS = "COMPETING_PROPOSALS"


class VerifiedDerivedRequirement(BaseModel):
    """A proposal that passed every one of ADR-030 D6's eight conditions.

    The two literal fields are the point of this class: a verified derived requirement is
    **always** ``PROSE_DERIVED`` and **always** ``REQUIRED``. Neither is a default that a
    caller may override — they are the type, so "a `PREFERRED` requirement gated eligibility"
    is unrepresentable rather than merely forbidden.

    **Being verified is not the same as being evaluated.** A verified requirement may still be
    suppressed by R-COLLISION when the source states the same requirement type structurally
    (ADR-030 D20a). That decision belongs to the evaluation boundary and is deliberately not
    made here.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    requirement_type: RequirementType
    value: DerivedValue
    provenance: Literal[RequirementProvenance.PROSE_DERIVED] = (
        RequirementProvenance.PROSE_DERIVED
    )
    strength: Literal[RequirementStrength.REQUIRED] = RequirementStrength.REQUIRED
    evidence_text: str = Field(min_length=1)
    extractor: str
    extractor_version: str
    provider: str | None = None
    model: str | None = None


class VerificationOutcome(BaseModel):
    """The verifier's decision about one proposal.

    ``failures`` reports **every** condition that failed, not merely the first. A candidate
    who fails eligibility learns every verified reason (ADR-017, ruling C-13); an extractor
    author deserves the same, and a single-reason result would hide a proposal that is wrong
    in three ways behind the one that happened to be checked first.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    verified: bool
    failures: tuple[VerificationFailure, ...] = ()
    requirement: VerifiedDerivedRequirement | None = None

    @model_validator(mode="after")
    def _outcome_is_coherent(self) -> VerificationOutcome:
        """A verified outcome carries a requirement and no failures, and the reverse.

        An outcome reporting both a requirement and a failure would be a verifier bug that
        silently promotes a refused proposal, so it is made unconstructible.
        """
        if self.verified and (self.requirement is None or self.failures):
            raise ValueError("a verified outcome carries a requirement and no failures")
        if not self.verified and self.requirement is not None:
            raise ValueError("an unverified outcome carries no requirement")
        if not self.verified and not self.failures:
            raise ValueError("an unverified outcome states at least one failure")
        return self


class CollectionVerification(BaseModel):
    """The result of verifying every proposal read from one job description.

    ``outcomes`` is positional — one entry per input proposal, in input order — so a caller
    can report why any individual proposal was refused. ``verified`` holds only what survived
    both individual verification and the competing-proposal rule (ADR-030 D8).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    verified: tuple[VerifiedDerivedRequirement, ...] = ()
    outcomes: tuple[VerificationOutcome, ...] = ()
