"""The evidence verifier for extracted job requirements (ADR-030 D6).

Pure functions. No FastAPI, no database, no AI provider, no HTTP, no I/O (INV-7). Nothing
here imports :class:`~app.schemas.candidate.CandidateProfile` or any other candidate type,
and **this module logs nothing at all** — not a count, not an outcome, and certainly not a
description, an evidence string or a rejection reason (INV-4, ADR-030 D24). A caller that
wants operational counts logs them itself, from numbers it already holds.

**The verifier is the authority; the extractor produces a proposal** (ADR-030 D6). A regular
expression locates a number; it does not establish that the number is a CGPA requirement
rather than *"7.5 years of experience"*. Every proposal — deterministic or model-produced —
passes the same eight conditions and carries the same ``PROSE_DERIVED`` provenance with the
same capped authority (D3, D12).

The eight conditions, and where each lives:

===  ==================================================================  =====================
 #   Condition (ADR-030 D6)                                              Implemented by
===  ==================================================================  =====================
 1   The source text explicitly contains the requirement                 :func:`_check_value_in_evidence`
 2   The extractor identifies a requirement value                        :func:`_check_value_structure`
 3   Supporting evidence text is returned with it                        :func:`_check_evidence_present`
 4   That evidence exists in the pinned normalized source text           :func:`_check_evidence_located`
 5   A deterministic verifier confirms value and type are supported      :func:`_check_evidence_supports_value`
 6   The semantic requirement type is one the engine recognises          :func:`_check_requirement_type`
 7   Strength established as ``REQUIRED`` from an explicit marker        :func:`_check_strength`
 8   No contradicting text in the contradiction window invalidates it    :func:`_check_contradiction_window`
===  ==================================================================  =====================

Any condition failing means the proposal **does not become a requirement**. It is discarded
— not downgraded, not retried with a lower bar, not surfaced as a weaker constraint. The
job's criterion simply stays absent, which is the pre-existing behaviour and is never a
failure for the candidate (ADR-003: absence of evidence is not evidence of ineligibility).

**Scanning is not extraction.** The per-type scanners below read a *short, bounded* string —
an evidence fragment, or a window around it — and they can only ever **refuse** a proposal or
confirm one that was handed to them. They never search a description for criteria and never
originate a value. Prose extraction is a separate module under ADR-030 D11 and is not part of
this one.

**The pinned normalized text** is ``jobs.description`` as stored, after
:func:`~app.services.job_normalizer.collapse_whitespace` (ADR-030 D9). Evidence is located in
that string and nowhere else: a verifier that located evidence in the raw fetched payload
would pass on text the system does not hold. Character offsets are computed here and
deliberately never returned — an offset is valid only against one exact string, and evidence
text is what survives (D9, D18).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from app.schemas.candidate import GradeScale
from app.schemas.eligibility import RequirementType
from app.schemas.extraction import (
    PHASE_1_REQUIREMENT_TYPES,
    CollectionVerification,
    DerivedValue,
    ExtractionProposal,
    GradYearWindowValue,
    MaxBacklogsValue,
    MinCgpaValue,
    RequirementProvenance,
    RequirementStrength,
    VerificationFailure,
    VerificationOutcome,
    VerifiedDerivedRequirement,
)
from app.services.job_normalizer import collapse_whitespace

#: Characters scanned either side of the evidence span for text that invalidates a proposal
#: (ADR-030 D9). "Nearby" is a character window rather than a sentence or paragraph because
#: ``collapse_whitespace`` destroys paragraph structure — ``\n\n`` becomes a single space —
#: and sentence splitting over collapsed HTML is unreliable.
#:
#: 300 is the ADR's default and is wide enough for both canonical cases: *"CGPA 7.5
#: preferred, 7.0 required"* (~30 characters apart) and a cutoff followed a sentence or two
#: later by *"This requirement is waived for ..."*. One constant, shared by every requirement
#: type, so "nearby" cannot come to mean different things for different criteria.
CONTRADICTION_WINDOW = 300

#: Earliest and latest graduation years a proposal may state, matching
#: :class:`~app.schemas.job.RawJob`'s own bounds so a derived window cannot express something
#: a source-stated one could not.
MIN_YEAR = 1950
MAX_YEAR = 2100


# ---------------------------------------------------------------------------------------
# Strength recognition (ADR-030 D10, D10a)
# ---------------------------------------------------------------------------------------

#: Explicit strength markers, by the strength each one states. Recognition only: every entry
#: is a phrase that must be **present in the evidence**. Nothing here reads context, emphasis,
#: position or recurrence, because each of those is inference wearing recognition's clothes
#: (ADR-030 D10a).
#:
#: ``maximum`` and its synonyms sit with ``minimum`` deliberately. An upper bound stated as
#: *"maximum 2 backlogs"* is exactly as explicit as a lower bound stated as *"minimum CGPA
#: 7.5"*, and D10a's worked table admits the latter; treating them differently would make the
#: rule depend on which direction a criterion happens to point.
_STRENGTH_MARKERS: dict[RequirementStrength, tuple[str, ...]] = {
    RequirementStrength.REQUIRED: (
        r"\brequired\b",
        r"\brequirements?\b",
        r"\bmandatory\b",
        r"\bcompulsory\b",
        r"\bessential\b",
        r"\bmust\s+(?:have|be|possess|hold|maintain)\b",
        r"\bminimum\b",
        r"\bmin\.",
        r"\bmaximum\b",
        r"\bmax\.",
        r"\bat\s+least\b",
        r"\bat\s+most\b",
        r"\bno\s+less\s+than\b",
        r"\bnot?\s+more\s+than\b",
        r"\bstrictly\b",
    ),
    RequirementStrength.PREFERRED: (
        r"\bpreferred\b",
        r"\bpreferably\b",
        r"\bpreference\b",
        r"\bdesirable\b",
        r"\bdesired\b",
        r"\bnice\s+to\s+have\b",
        r"\bgood\s+to\s+have\b",
        r"\ba\s+plus\b",
        r"\ban?\s+advantage\b",
        r"\bideally\b",
        r"\bbonus\b",
    ),
    RequirementStrength.CONDITIONAL: (
        r"\bwaiv(?:e|ed|er|ers)\b",
        r"\brelax(?:ed|ation)?\b",
        r"\bsubject\s+to\b",
        r"\bcase[\s-]by[\s-]case\b",
        r"\bat\s+the\s+discretion\b",
        r"\bunless\b",
        r"\bexcept(?:ion|ions)?\b",
        r"\bif\s+applicable\b",
        r"\bwherever\s+applicable\b",
    ),
    RequirementStrength.INFORMATIONAL: (
        r"\btypically\b",
        r"\bgenerally\b",
        r"\busually\b",
        r"\bindicative\b",
        r"\bfor\s+reference\b",
        r"\bfor\s+information\b",
        r"\bnote\s+that\b",
    ),
}

_COMPILED_MARKERS: dict[RequirementStrength, tuple[re.Pattern[str], ...]] = {
    strength: tuple(re.compile(p, re.IGNORECASE) for p in patterns)
    for strength, patterns in _STRENGTH_MARKERS.items()
}


class StrengthRecognition(str, Enum):
    """The outcome of reading strength off an evidence string.

    ``NOT_ESTABLISHED`` and ``AMBIGUOUS`` are distinct results, not two names for failure.
    The first means the text states no strength at all — the commonest shape in real prose,
    and the most tempting to promote. The second means it states more than one, which is a
    conflict rather than a silence. Both refuse the proposal; reporting them separately keeps
    the two tests independent.
    """

    ESTABLISHED = "ESTABLISHED"
    NOT_ESTABLISHED = "NOT_ESTABLISHED"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True)
class RecognisedStrength:
    """What :func:`recognise_strength` read. ``strength`` is set only when exactly one was."""

    recognition: StrengthRecognition
    strength: RequirementStrength | None


def recognise_strength(evidence_text: str) -> RecognisedStrength:
    """Read an explicit strength marker out of evidence text, or report that there is none.

    Exactly one marker class present is a recognition. Two or more is ``AMBIGUOUS`` — *"CGPA
    7.5 may be waived"* carries both a ``REQUIRED``-class and a ``CONDITIONAL``-class marker,
    and a strength that cannot be read off the text safely has not been established. None at
    all is ``NOT_ESTABLISHED``: a bare *"CGPA 7.5"* says what the number is, never whether it
    gates anything, and condition 7 refuses it exactly as it refuses *"preferred"*.

    **An unestablished strength is not a weak ``REQUIRED``; it is the absence of a strength**
    (ADR-030 D10a).
    """
    matched = {
        strength
        for strength, patterns in _COMPILED_MARKERS.items()
        if any(pattern.search(evidence_text) for pattern in patterns)
    }
    if not matched:
        return RecognisedStrength(StrengthRecognition.NOT_ESTABLISHED, None)
    if len(matched) > 1:
        return RecognisedStrength(StrengthRecognition.AMBIGUOUS, None)
    return RecognisedStrength(StrengthRecognition.ESTABLISHED, matched.pop())


# ---------------------------------------------------------------------------------------
# Value scanners — confirmation only, never origination
# ---------------------------------------------------------------------------------------

_NUMBER = re.compile(r"\d{1,3}(?:\.\d{1,2})?")
_YEAR = re.compile(r"\b(\d{4})\b")

#: Words that, following a number, mean it is not a grade. *"7.5 years of experience"* is the
#: canonical false positive ADR-030 D6 condition 5 exists to refuse, and the reason a
#: deterministic extraction is not self-evidently correct (D12).
_UNIT_AFTER_NUMBER = re.compile(
    r"\s*\+?\s*(?:years?|yrs?|months?|mos?|weeks?|days?|hours?|hrs?|semesters?"
    r"|lpa|lakhs?|crores?|cr|k\b|usd|inr|eur|gbp)\b",
    re.IGNORECASE,
)

#: A number is only a grade when the text says so. ``score`` is deliberately absent: "score
#: 80% on the assessment" is not an eligibility cutoff.
_GRADE_KEYWORD = re.compile(
    r"c\.?\s?g\.?\s?p\.?\s?a|\bgpa\b|\baggregate\b|\bpercentage\b|\bmarks\b|\bgrade\b",
    re.IGNORECASE,
)

#: ``7.5/10``, ``7.5 out of 10``, ``7.5 on a 10 point scale``.
_SCALE_SUFFIX = re.compile(
    r"\s*(?:/|out\s+of|on\s+an?)\s*(\d{1,3})\b(?:[\s-]*point)?(?:\s*scale)?", re.IGNORECASE
)
_PERCENT_SUFFIX = re.compile(r"\s*(?:%|percent(?:age)?\b)", re.IGNORECASE)

_SCALE_BY_MAXIMUM: dict[int, GradeScale] = {
    4: GradeScale.SCALE_4,
    5: GradeScale.SCALE_5,
    10: GradeScale.SCALE_10,
    100: GradeScale.PERCENTAGE,
}

#: How far before a number the scanner will look for a keyword establishing what it is. Short
#: on purpose — a keyword two clauses away is context, and context is not recognition.
_KEYWORD_LOOKBEHIND = 60
_KEYWORD_LOOKAHEAD = 20


def _cgpa_values(text: str) -> set[tuple[float, GradeScale]]:
    """Every ``(grade, scale)`` pair the text actually states.

    A pair is produced only when the number carries **both** a grade keyword nearby and an
    explicit scale. A grade with no stated scale is not a usable requirement
    (``standards/eligibility.md`` §4, ADR-030 D11), so it is not produced at all rather than
    produced with a guessed one.
    """
    found: set[tuple[float, GradeScale]] = set()
    for match in _NUMBER.finditer(text):
        tail = text[match.end() : match.end() + _KEYWORD_LOOKBEHIND]
        if _UNIT_AFTER_NUMBER.match(tail):
            continue

        scale: GradeScale | None = None
        suffix = _SCALE_SUFFIX.match(tail)
        if suffix is not None:
            scale = _SCALE_BY_MAXIMUM.get(int(suffix.group(1)))
        elif _PERCENT_SUFFIX.match(tail):
            scale = GradeScale.PERCENTAGE
        if scale is None:
            continue

        head = text[max(0, match.start() - _KEYWORD_LOOKBEHIND) : match.start()]
        if not _GRADE_KEYWORD.search(head) and not _GRADE_KEYWORD.search(
            tail[:_KEYWORD_LOOKAHEAD]
        ):
            continue

        found.add((float(match.group()), scale))
    return found


#: Words that make a four-digit number a graduation year rather than a number. Without one of
#: these the scanner produces nothing: a bare ``2026`` is a number, and treating every
#: four-digit token as a year is how a salary band becomes an eligibility window.
_GRAD_CONTEXT = re.compile(
    r"graduat|passing\s*out|pass[\s-]?out|\bbatch\b|class\s+of|year\s+of\s+pass",
    re.IGNORECASE,
)
_YEAR_LOWER_BOUND = re.compile(r"\s*(?:or\s+later|onwards?|and\s+(?:after|later)|or\s+after)\b", re.IGNORECASE)
_YEAR_UPPER_BOUND = re.compile(r"\s*(?:or\s+earlier|and\s+(?:before|earlier)|or\s+before|and\s+prior)\b", re.IGNORECASE)
_YEAR_RANGE = re.compile(r"\s*(?:-|–|—|to|and)\s*(\d{4})\b", re.IGNORECASE)


def _grad_year_windows(text: str) -> set[tuple[int | None, int | None]]:
    """Every ``(min_year, max_year)`` window the text actually states.

    A bare year in graduation context is an exact window — *"2026 batch"* means 2026 and
    nothing else. ``or later`` and ``or earlier`` open one end; an explicit range states both.
    """
    found: set[tuple[int | None, int | None]] = set()
    #: Positions already consumed as the upper end of an explicit range. ``2025-2026`` states
    #: one window, not also an exact 2026 — and without this the range would look like two
    #: competing windows and condition 8 would refuse the very text it came from.
    consumed: set[int] = set()

    for match in _YEAR.finditer(text):
        year = int(match.group(1))
        if match.start() in consumed or not MIN_YEAR <= year <= MAX_YEAR:
            continue

        head = text[max(0, match.start() - _KEYWORD_LOOKBEHIND) : match.start()]
        tail = text[match.end() : match.end() + _KEYWORD_LOOKBEHIND]
        if not _GRAD_CONTEXT.search(head) and not _GRAD_CONTEXT.search(tail):
            continue

        span = _YEAR_RANGE.match(tail)
        if span is not None:
            other = int(span.group(1))
            if MIN_YEAR <= other <= MAX_YEAR and other >= year:
                found.add((year, other))
                consumed.add(match.end() + span.start(1))
                continue
        if _YEAR_LOWER_BOUND.match(tail):
            found.add((year, None))
        elif _YEAR_UPPER_BOUND.match(tail):
            found.add((None, year))
        else:
            found.add((year, year))
    return found


#: Bounded, explicitly recognisable backlog wording, and nothing beyond it (ADR-030 D11).
#: A ``backlog`` with no quantifier frame produces nothing, which is what keeps *"product
#: backlog"* and *"a backlog of support tickets"* out.
_BACKLOG_ZERO = re.compile(
    r"\b(?:no|zero|nil|without\s+(?:any\s+)?)\s+(?:active\s+|current\s+|standing\s+|live\s+|pending\s+)?backlogs?\b",
    re.IGNORECASE,
)
_BACKLOG_BOUNDED = re.compile(
    r"\b(?:maximum|max\.?|at\s+most|not?\s+more\s+than|up\s*to|upto)\s+(?:of\s+)?(\d{1,2})"
    r"\s+(?:active\s+|current\s+|standing\s+|live\s+|pending\s+)?backlogs?\b",
    re.IGNORECASE,
)
_BACKLOG_TRAILING = re.compile(
    r"\b(\d{1,2})\s+(?:active\s+|current\s+|standing\s+|live\s+|pending\s+)?backlogs?"
    r"\s+(?:or\s+fewer|or\s+less|maximum|at\s+most|allowed|permitted)\b",
    re.IGNORECASE,
)


def _backlog_counts(text: str) -> set[int]:
    """Every backlog limit the text actually states, via a bounded stock frame only."""
    found: set[int] = {0} if _BACKLOG_ZERO.search(text) else set()
    for pattern in (_BACKLOG_BOUNDED, _BACKLOG_TRAILING):
        found.update(int(match.group(1)) for match in pattern.finditer(text))
    return found


def _stated_values(requirement_type: RequirementType, text: str) -> set[object]:
    """Dispatch to the scanner for one requirement type, as a comparable set."""
    if requirement_type is RequirementType.MIN_CGPA:
        return set(_cgpa_values(text))
    if requirement_type is RequirementType.GRAD_YEAR_WINDOW:
        return set(_grad_year_windows(text))
    if requirement_type is RequirementType.MAX_BACKLOGS:
        return set(_backlog_counts(text))
    return set()


def _value_key(value: DerivedValue) -> object:
    """The comparable form of a typed value, matching what the scanners produce."""
    if isinstance(value, MinCgpaValue):
        return (float(value.min_cgpa), value.min_cgpa_scale)
    if isinstance(value, GradYearWindowValue):
        return (value.min_grad_year, value.max_grad_year)
    return value.max_backlogs


def _value_is_stated_in(value: DerivedValue, evidence: str) -> bool:
    """Whether the evidence explicitly states this value, in digits or in words.

    A cheap, mostly-literal check that the evidence is about this value at all; condition 5
    is the semantic one. It is not purely literal because **a value can be stated without a
    digit**: *"no active backlogs"* states a limit of zero as explicitly as *"maximum 0
    backlogs"* does, and demanding the character ``0`` would refuse the commonest backlog
    phrasing in real postings for a reason that has nothing to do with evidence.
    """
    if isinstance(value, MinCgpaValue):
        return f"{value.min_cgpa:g}" in evidence
    if isinstance(value, GradYearWindowValue):
        bounds = [b for b in (value.min_grad_year, value.max_grad_year) if b is not None]
        return bool(bounds) and all(str(bound) in evidence for bound in bounds)
    if value.max_backlogs == 0 and _BACKLOG_ZERO.search(evidence):
        return True
    return str(value.max_backlogs) in evidence


# ---------------------------------------------------------------------------------------
# Contradiction detection (ADR-030 D9) — deterministic and pattern-based, never a model
# ---------------------------------------------------------------------------------------

#: Text that qualifies or withdraws a criterion. Asking a model whether its own extraction is
#: contradicted would reintroduce exactly the authority ADR-030 removes, so this is patterns
#: and nothing else.
_CONTRADICTION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bwaiv(?:e|ed|er|ers|ing)\b",
        r"\brelax(?:ed|ation)?\b",
        r"\bexempt(?:ion|ed)?\b",
        r"\bnot\s+applicable\b",
        r"\bno\s+longer\s+appl",
        r"\bat\s+the\s+discretion\b",
        r"\bcase[\s-]by[\s-]case\b",
        r"\bsubject\s+to\s+(?:approval|review|change)\b",
        r"\bexcept(?:ion|ions)?\b",
    )
)


def contradiction_window(
    pinned_text: str, start: int, end: int, window: int = CONTRADICTION_WINDOW
) -> str:
    """The symmetric character window around an evidence span, clamped to the text bounds."""
    return pinned_text[max(0, start - window) : min(len(pinned_text), end + window)]


def _window_invalidates(
    requirement_type: RequirementType,
    value: DerivedValue,
    window_text: str,
) -> bool:
    """True when something in the window qualifies the proposal or competes with it.

    Two independent ways a window invalidates a proposal:

    * **Qualifying language** — a waiver, relaxation or discretion clause anywhere in it.
    * **A competing value of the same type** — *"CGPA 7.5 preferred, 7.0 required"* is
      ADR-030 D8's worked case, and the reason this check exists separately from the strength
      gate: condition 7 refuses the 7.5 proposal on its marker, and condition 8 refuses it
      again, independently, because *"7.0 required"* sits beside it.

    The competing-value test is deliberately symmetric and therefore conservative: a proposal
    is refused whenever the window states a *different* value of its own type, in either
    direction. A job with no CGPA requirement is honest; a job with the wrong one tells a
    qualified candidate not to apply.
    """
    if any(pattern.search(window_text) for pattern in _CONTRADICTION_PATTERNS):
        return True
    competing = _stated_values(requirement_type, window_text)
    return any(other != _value_key(value) for other in competing)


# ---------------------------------------------------------------------------------------
# The eight conditions
# ---------------------------------------------------------------------------------------


def _check_evidence_present(evidence: str) -> VerificationFailure | None:
    """Condition 3 — supporting evidence text is returned with the proposal."""
    return None if evidence else VerificationFailure.EVIDENCE_EMPTY


def _check_evidence_located(pinned_text: str, evidence: str) -> list[tuple[int, int]]:
    """Condition 4 — locate the evidence in the pinned normalized text.

    Exact and case-sensitive. The extractor read this string out of the pinned text, so an
    exact occurrence must exist; a case-insensitive or fuzzy fallback would admit evidence the
    extractor altered, and the whole point of condition 4 is that the system can still see the
    sentence it relied on.

    Every occurrence is returned, because condition 8 scans the window around each of them.
    """
    if not evidence:
        return []
    spans: list[tuple[int, int]] = []
    index = pinned_text.find(evidence)
    while index != -1:
        spans.append((index, index + len(evidence)))
        index = pinned_text.find(evidence, index + 1)
    return spans


def _check_value_in_evidence(value: DerivedValue, evidence: str) -> VerificationFailure | None:
    """Condition 1 — the evidence explicitly states the proposed value."""
    if _value_is_stated_in(value, evidence):
        return None
    return VerificationFailure.VALUE_NOT_IN_EVIDENCE


def _check_value_structure(value: DerivedValue) -> VerificationFailure | None:
    """Condition 2 — the proposal carries a structurally usable requirement value.

    Proposals are permissive by construction, so this is where a nonsense value is caught: a
    grade with no scale or above its own scale's maximum, a window with no bound or an
    inverted one, a negative backlog count. Each would otherwise reach the engine and be
    reported as an invalid job requirement, which is a worse outcome than never adopting it.
    """
    if isinstance(value, MinCgpaValue):
        if value.min_cgpa_scale is GradeScale.UNKNOWN:
            return VerificationFailure.MALFORMED_VALUE
        maximum = value.min_cgpa_scale.maximum
        if maximum is None or not 0 < value.min_cgpa <= maximum:
            return VerificationFailure.MALFORMED_VALUE
        return None

    if isinstance(value, GradYearWindowValue):
        low, high = value.min_grad_year, value.max_grad_year
        if low is None and high is None:
            return VerificationFailure.MALFORMED_VALUE
        if any(bound is not None and not MIN_YEAR <= bound <= MAX_YEAR for bound in (low, high)):
            return VerificationFailure.MALFORMED_VALUE
        if low is not None and high is not None and low > high:
            return VerificationFailure.MALFORMED_VALUE
        return None

    if value.max_backlogs < 0:
        return VerificationFailure.MALFORMED_VALUE
    return None


def _check_evidence_supports_value(
    requirement_type: RequirementType, value: DerivedValue, evidence: str
) -> VerificationFailure | None:
    """Condition 5 — re-read the evidence and require it to state exactly this value.

    **The verifier does not trust the extractor's reading.** It runs the type's own scanner
    over the evidence alone and checks that the proposed value is among what that text
    actually states. This is what refuses a faithful-looking ``min_cgpa = 7.5`` whose evidence
    is *"7.5 years of experience"*: the scanner finds no grade there at all.
    """
    if _value_key(value) in _stated_values(requirement_type, evidence):
        return None
    return VerificationFailure.VALUE_NOT_SUPPORTED_BY_EVIDENCE


def _check_requirement_type(proposal: ExtractionProposal) -> list[VerificationFailure]:
    """Condition 6 — the type is recognised, and the typed value agrees with it.

    Two distinct ways this fails. A proposal for ``ALLOWED_FIELDS`` names a real ADR-018 type
    that ADR-030 D12 excludes from extraction permanently. A proposal labelled ``MIN_CGPA``
    carrying a backlog value is an extractor bug. Collapsing the two into one code would hide
    the second behind the first.
    """
    failures: list[VerificationFailure] = []
    if proposal.requirement_type not in PHASE_1_REQUIREMENT_TYPES:
        failures.append(VerificationFailure.UNRECOGNISED_REQUIREMENT_TYPE)
    if proposal.value.requirement_type is not proposal.requirement_type:
        failures.append(VerificationFailure.REQUIREMENT_TYPE_MISMATCH)
    return failures


def _check_strength(proposal: ExtractionProposal, evidence: str) -> VerificationFailure | None:
    """Condition 7 — strength established as ``REQUIRED`` from an explicit marker.

    A reported strength may **lower** trust and never raise it (ADR-030 D7, D10a): an
    extractor that itself says ``PREFERRED`` is taken at its word and refused, but one that
    says ``REQUIRED`` proves nothing — recognition from the evidence decides, every time.
    """
    if (
        proposal.reported_strength is not None
        and proposal.reported_strength is not RequirementStrength.REQUIRED
    ):
        return VerificationFailure.STRENGTH_NOT_REQUIRED

    recognised = recognise_strength(evidence)
    if recognised.recognition is StrengthRecognition.AMBIGUOUS:
        return VerificationFailure.STRENGTH_AMBIGUOUS
    if recognised.recognition is StrengthRecognition.NOT_ESTABLISHED:
        return VerificationFailure.STRENGTH_NOT_ESTABLISHED
    if recognised.strength is not RequirementStrength.REQUIRED:
        return VerificationFailure.STRENGTH_NOT_REQUIRED
    return None


def _check_contradiction_window(
    proposal: ExtractionProposal,
    pinned_text: str,
    spans: Sequence[tuple[int, int]],
    window: int,
) -> VerificationFailure | None:
    """Condition 8 — nothing within the window invalidates the proposal.

    Checked around **every** occurrence of the evidence. A qualifying clause beside any of
    them is a qualifying clause, and picking one occurrence would make the result depend on
    which copy the extractor happened to point at.
    """
    for start, end in spans:
        text = contradiction_window(pinned_text, start, end, window)
        if _window_invalidates(proposal.requirement_type, proposal.value, text):
            return VerificationFailure.CONTRADICTED_IN_WINDOW
    return None


# ---------------------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------------------


def verify_proposal(
    proposal: ExtractionProposal,
    pinned_text: str,
    *,
    window: int = CONTRADICTION_WINDOW,
) -> VerificationOutcome:
    """Decide whether one proposal becomes a verified derived requirement.

    Args:
        proposal: What an extractor claims to have read. Untrusted.
        pinned_text: ``jobs.description`` **as stored** — the post-``collapse_whitespace``
            string, not the raw fetched payload (ADR-030 D9).
        window: Characters scanned either side of the evidence for condition 8.

    Returns:
        A :class:`~app.schemas.extraction.VerificationOutcome` carrying either the verified
        requirement or **every** condition that refused it.

    Nothing about a candidate reaches this function, and nothing it reads is logged.
    """
    evidence = collapse_whitespace(proposal.evidence_text)
    failures: list[VerificationFailure] = []

    if proposal.provenance is not RequirementProvenance.PROSE_DERIVED:
        # A source-stated requirement lives in a `jobs` column by definition (ADR-030 D1) and
        # has no extraction path. A proposal claiming one is refused rather than relabelled.
        failures.append(VerificationFailure.PROVENANCE_NOT_DERIVED)

    failures.extend(_check_requirement_type(proposal))

    structure_failure = _check_value_structure(proposal.value)
    if structure_failure is not None:
        failures.append(structure_failure)

    evidence_failure = _check_evidence_present(evidence)
    if evidence_failure is not None:
        failures.append(evidence_failure)

    spans = _check_evidence_located(pinned_text, evidence)
    if evidence and not spans:
        failures.append(VerificationFailure.EVIDENCE_NOT_IN_SOURCE)

    if evidence:
        token_failure = _check_value_in_evidence(proposal.value, evidence)
        if token_failure is not None:
            failures.append(token_failure)

        # Condition 5 is only meaningful for a type the value actually matches; a mismatched
        # pair has already failed condition 6 and would fail here for the wrong reason.
        if proposal.value.requirement_type is proposal.requirement_type:
            support_failure = _check_evidence_supports_value(
                proposal.requirement_type, proposal.value, evidence
            )
            if support_failure is not None:
                failures.append(support_failure)

        strength_failure = _check_strength(proposal, evidence)
        if strength_failure is not None:
            failures.append(strength_failure)

    if spans:
        window_failure = _check_contradiction_window(proposal, pinned_text, spans, window)
        if window_failure is not None:
            failures.append(window_failure)

    if failures:
        # Deduplicated and ordered so the outcome is deterministic, which matters because a
        # test asserts on it and a human reads it.
        ordered = tuple(sorted({failure for failure in failures}, key=lambda f: f.value))
        return VerificationOutcome(verified=False, failures=ordered)

    return VerificationOutcome(
        verified=True,
        requirement=VerifiedDerivedRequirement(
            requirement_type=proposal.requirement_type,
            value=proposal.value,
            evidence_text=evidence,
            extractor=proposal.extractor,
            extractor_version=proposal.extractor_version,
            provider=proposal.provider,
            model=proposal.model,
        ),
    )


def verify_proposals(
    proposals: Sequence[ExtractionProposal],
    pinned_text: str,
    *,
    window: int = CONTRADICTION_WINDOW,
) -> CollectionVerification:
    """Verify every proposal read from one description, then resolve competition between them.

    Two proposals of the same requirement type stating **different** values are both
    discarded: *"if both proposals arrive, or the strength reading is ambiguous or
    contradictory, neither is promoted"* (ADR-030 D8). The system never picks a winner and
    never "corrects" one value to another — it either receives a single well-evidenced value
    or has no requirement of that type for the job.

    Identical duplicates are not competition. Two extractors reading the same sentence, or one
    extractor emitting the same value twice, agree; the value is promoted once.

    **R-COLLISION is deliberately not applied here.** Whether a verified requirement is
    suppressed because the source states the same type structurally is an evaluation-boundary
    decision (ADR-030 D20a), and it needs the job's own columns, which this module must never
    see. Verified is not the same as effective.
    """
    outcomes = [verify_proposal(proposal, pinned_text, window=window) for proposal in proposals]

    by_type: dict[RequirementType, set[object]] = {}
    for outcome in outcomes:
        if outcome.requirement is not None:
            requirement = outcome.requirement
            by_type.setdefault(requirement.requirement_type, set()).add(
                _value_key(requirement.value)
            )
    competing = {kind for kind, values in by_type.items() if len(values) > 1}

    resolved: list[VerificationOutcome] = []
    verified: list[VerifiedDerivedRequirement] = []
    promoted: set[tuple[RequirementType, object]] = set()
    for outcome in outcomes:
        requirement = outcome.requirement
        if requirement is None:
            resolved.append(outcome)
            continue
        if requirement.requirement_type in competing:
            resolved.append(
                VerificationOutcome(
                    verified=False, failures=(VerificationFailure.COMPETING_PROPOSALS,)
                )
            )
            continue
        resolved.append(outcome)
        key = (requirement.requirement_type, _value_key(requirement.value))
        if key not in promoted:
            promoted.add(key)
            verified.append(requirement)

    return CollectionVerification(verified=tuple(verified), outcomes=tuple(resolved))
