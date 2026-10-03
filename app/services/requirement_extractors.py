"""Deterministic requirement extractors (ADR-030 D11, sequencing step 5).

Pure functions. No FastAPI, no database, no AI provider, no HTTP, no filesystem, no
subprocess, no configuration and **no logging at all** — not a count, not a match, and
certainly not a description or an evidence string (INV-4, ADR-030 D24). Nothing here
imports :class:`~app.schemas.candidate.CandidateProfile` or any other candidate type, and
no function takes a candidate, a profile, an identifier or a resume: **the only input is
job-description text**, which is public source material.

**This module produces proposals. It verifies nothing.** ADR-030 D6 is explicit that *"the
verifier is the authority. The extractor — regex or model — produces a proposal."* Every
value read here is a :class:`~app.schemas.extraction.ExtractionProposal` carrying
``PROSE_DERIVED`` provenance, and it becomes a requirement only if
:func:`~app.services.requirement_verifier.verify_proposal` passes it through all eight
conditions. There is no path from this module to a
:class:`~app.schemas.extraction.VerifiedDerivedRequirement`.

Phase 1 scope is three criteria and nothing beyond them (D11): a minimum grade **with its
scale**, a graduation-year window, and a backlog limit. Field and branch ontology, degree
mapping, skills and deadlines are excluded permanently by D12, and nothing here infers,
stems, expands an abbreviation or consults a synonym table.

Why the pattern layer resembles the verifier's
---------------------------------------------

The verifier's own scanners are private and documented as *confirmation only* — they read a
short evidence fragment and can only refuse a value or confirm one handed to them. This
module does the opposite: it **originates** values by searching a whole description. The two
are deliberately separate implementations, and this module imports none of the verifier's
scanning internals.

The recognised *grammar*, though, is necessarily the same. "What counts as a stated CGPA with
a scale" is fixed by the verifier's contract, so a broader grammar here would only produce
proposals that condition 5 refuses, and a narrower one would be arbitrary. The patterns below
therefore track that grammar on purpose, and a test asserts the alignment directly rather
than leaving it to inspection.

**This does not make condition 5 a formality.** For a Phase 1 proposal condition 5 no longer
guards value *recognition* — it guards **evidence-span selection**, which is the genuinely
new judgement in this module and the one D8 warns about: *"No confidence value distinguishes
'I read this sentence correctly' from 'I read the correct sentence'."* An extractor that
quotes the wrong clause, or trims a clause past its scale, states a value its own evidence
does not support, and condition 5 is what catches it. Conditions 7 and 8 remain fully
load-bearing for the same reason.

Strength
--------

Strength is read with the verifier's public :func:`recognise_strength`, which is the
repository's single definition of an explicit marker (D10a). Reimplementing the marker tables
here would risk the extractor reporting one strength while the verifier reads another, and
would buy no independence: ``reported_strength`` is **advisory** and can only ever lower
trust, never raise it (D7, D10a).

A proposal whose strength is not ``REQUIRED`` is still **emitted**, carrying what was
recognised. That is the *disclosed / observed* class of D10 — the verifier refuses it on
condition 7, which is where that decision belongs. Suppressing it here would move condition 7
into the extractor and hide the commonest real shape, a bare *"CGPA 7.5/10"*, behind silence
instead of a named failure. What is **not** emitted is a value the text does not explicitly
state: a grade with no scale, a year with no graduation context, a backlog count with no
quantifier frame. Conservative absence is correct, and a missing requirement is never a
failure for a candidate (ADR-003).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence

from app.schemas.candidate import Confidence, GradeScale
from app.schemas.eligibility import RequirementType
from app.schemas.extraction import (
    DerivedValue,
    ExtractionProposal,
    GradYearWindowValue,
    MaxBacklogsValue,
    MinCgpaValue,
    RequirementProvenance,
)
from app.services.job_normalizer import collapse_whitespace
from app.services.requirement_verifier import MAX_YEAR, MIN_YEAR, recognise_strength

#: Extractor identities, in the ``deterministic.<field>`` form the proposal schema documents.
#: Stored with every verified requirement (ADR-030 D18) so a reader can tell which extractor
#: produced a row without consulting anything else.
CGPA_EXTRACTOR = "deterministic.cgpa"
GRAD_YEAR_EXTRACTOR = "deterministic.grad_year"
BACKLOG_EXTRACTOR = "deterministic.backlogs"

#: Version of the pattern set below, following ``MATCHING_VERSION`` / ``VALIDATOR_VERSION``.
#: **Bump this whenever a pattern changes what is recognised.** D22 makes re-extraction after
#: a version change an explicit operation rather than a silent one, and that only works if the
#: stored version actually moves.
EXTRACTOR_VERSION = "1"

#: The longest evidence this module will quote. A statement longer than this is not a
#: quotable sentence, and evidence is persisted and read by humans (D18). The verifier reads
#: at most 60 characters either side of a value when recognising it, so 300 leaves a wide
#: margin for the marker and the scale while keeping a stored row legible.
MAX_EVIDENCE_CHARS = 300

#: How far before a value this module looks for the word establishing what the value is, and
#: how far after. Deliberately identical to the verifier's own reach: a keyword further away
#: than this is context, and context is not recognition.
_KEYWORD_LOOKBEHIND = 60
_KEYWORD_LOOKAHEAD = 20


# ---------------------------------------------------------------------------------------
# Clause segmentation — choosing what to quote
# ---------------------------------------------------------------------------------------

#: Where one statement ends and the next begins, in **pinned normalized text**.
#:
#: Three kinds of boundary, and no fourth. A sentence terminator, recognised orthographically
#: as a ``.``/``!``/``?`` that follows a letter or digit and precedes a capital — never by
#: consulting a list of abbreviations, which D12's anti-ontology rule rules out and which
#: would be a dictionary in all but name. Clause punctuation, which in a job posting separates
#: list items as reliably as a full stop does. And surviving HTML markup: ``collapse_whitespace``
#: destroys paragraph structure but leaves tags as literal characters (D9), so ``</li><li>`` is
#: the only remaining trace of where a bulleted requirement ended.
#:
#: The capital-letter lookahead is what keeps *"min. 7.5/10"* and *"max. 2 backlogs"* whole.
#: Both are explicit ``REQUIRED`` markers; splitting them off the value they qualify would
#: silently cost the statement its strength.
_CLAUSE_BOUNDARY = re.compile(
    r"(?<=[A-Za-z0-9\)\]])[.!?]\s+(?=[A-Z])"  # sentence end, orthographic
    r"|\s*[;|•·▪●]\s*"  # clause and list punctuation
    r"|<[^<>]{0,60}>"  # surviving markup
)


def _clauses(pinned_text: str) -> list[str]:
    """Split pinned text into the statements this module is willing to quote.

    Boundaries are dropped rather than kept, so every clause returned is a verbatim substring
    of ``pinned_text`` — which is what condition 4 requires of the evidence built from it.
    """
    return [part for part in _CLAUSE_BOUNDARY.split(pinned_text) if part and part.strip()]


def _evidence(clause: str, start: int, end: int) -> str:
    """The quotable evidence for a value occupying ``clause[start:end]``.

    Normally the whole clause: it is the smallest unit the posting itself delimited, and it
    carries the strength marker that condition 7 needs. A clause longer than
    :data:`MAX_EVIDENCE_CHARS` is narrowed to a symmetric span around the value and then
    pulled back to whitespace, so the result stays a verbatim substring and still reads as
    text rather than as a fragment cut mid-word.

    Narrowing can cost a proposal its marker or its scale, and that is deliberate: the
    verifier refuses it on condition 7 or condition 5 rather than this module guessing at
    what the removed text said.
    """
    # Re-base the span onto the stripped clause before measuring anything against it.
    lead = len(clause) - len(clause.lstrip())
    clause = clause.strip()
    start, end = start - lead, end - lead

    if len(clause) <= MAX_EVIDENCE_CHARS:
        return clause
    if end - start >= MAX_EVIDENCE_CHARS:
        return clause[start:end]

    spare = MAX_EVIDENCE_CHARS - (end - start)
    low = max(0, start - spare // 2)
    high = min(len(clause), low + MAX_EVIDENCE_CHARS)
    low = max(0, high - MAX_EVIDENCE_CHARS)

    # Pull both edges in to whitespace so the quote never begins or ends mid-word. The
    # search bounds stop at the value's own span, so narrowing can never eat the value.
    if low > 0:
        cut = clause.find(" ", low, start)
        if cut != -1:
            low = cut + 1
    if high < len(clause):
        cut = clause.rfind(" ", end, high)
        if cut != -1:
            high = cut
    return clause[low:high].strip()


# ---------------------------------------------------------------------------------------
# Field 1 — a minimum grade and its scale
# ---------------------------------------------------------------------------------------

#: What makes a number a grade rather than a number. ``score`` is absent on purpose: *"score
#: 80% on the assessment"* is not an eligibility cutoff.
_GRADE_KEYWORD = re.compile(
    r"c\.?\s?g\.?\s?p\.?\s?a|\bgpa\b|\baggregate\b|\bpercentage\b|\bmarks\b|\bgrade\b",
    re.IGNORECASE,
)

#: A grade **immediately followed by its scale**: ``7.5/10``, ``8.2 out of 10``, ``7.5 on a
#: 10 point scale``, ``60%``, ``60 percent``. The adjacency is not a simplification — a scale
#: stated further away belongs to some other number as readily as to this one.
_GRADE_WITH_SCALE = re.compile(
    r"(?P<grade>\d{1,3}(?:\.\d{1,2})?)"
    r"(?:"
    r"\s*(?:/|out\s+of|on\s+an?)\s*(?P<maximum>\d{1,3})\b(?:[\s-]*point)?(?:\s*scale)?"
    r"|(?P<percent>\s*(?:%|percent(?:age)?\b))"
    r")",
    re.IGNORECASE,
)

#: Scale by its maximum, derived from :class:`~app.schemas.candidate.GradeScale` rather than
#: written out again. ``UNKNOWN`` has no maximum and so cannot appear here, which is the
#: property that stops an unscaled grade from acquiring a scale by accident.
_SCALE_BY_MAXIMUM: dict[int, GradeScale] = {
    int(scale.maximum): scale for scale in GradeScale if scale.maximum is not None
}


def _cgpa_in(clause: str) -> list[tuple[MinCgpaValue, int, int]]:
    """Every grade-with-scale the clause states, with the span of the stated grade."""
    found: list[tuple[MinCgpaValue, int, int]] = []
    for match in _GRADE_WITH_SCALE.finditer(clause):
        if match.group("percent") is not None:
            scale: GradeScale | None = GradeScale.PERCENTAGE
        else:
            scale = _SCALE_BY_MAXIMUM.get(int(match.group("maximum")))
        if scale is None:
            # A scale the system has no definition for — `7.5/7` — is not a scale it can
            # compare against, and guessing the nearest one is how a cutoff becomes wrong.
            continue

        start, end = match.start("grade"), match.end("grade")
        head = clause[max(0, start - _KEYWORD_LOOKBEHIND) : start]
        tail = clause[end : end + _KEYWORD_LOOKBEHIND]
        if not _GRADE_KEYWORD.search(head) and not _GRADE_KEYWORD.search(
            tail[:_KEYWORD_LOOKAHEAD]
        ):
            # The number carries a scale but nothing says it is a grade. This is what keeps
            # *"7.5 years of experience"*, a salary band and a duration out, and it is the
            # canonical false positive D6 condition 5 exists to refuse.
            continue

        found.append(
            (
                MinCgpaValue(min_cgpa=float(match.group("grade")), min_cgpa_scale=scale),
                start,
                match.end(),
            )
        )
    return found


# ---------------------------------------------------------------------------------------
# Field 2 — a graduation-year window
# ---------------------------------------------------------------------------------------

#: Words that make a four-digit number a graduation year. Without one of these nothing is
#: produced: a bare ``2026`` is a number, and reading every four-digit token as a year is how
#: a salary band becomes an eligibility window.
_GRAD_CONTEXT = re.compile(
    r"graduat|passing\s*out|pass[\s-]?out|\bbatch\b|class\s+of|year\s+of\s+pass",
    re.IGNORECASE,
)
_YEAR = re.compile(r"\b(\d{4})\b")
_YEAR_RANGE = re.compile(r"\s*(?:-|–|—|to|and)\s*(\d{4})\b", re.IGNORECASE)
_YEAR_LOWER_BOUND = re.compile(
    r"\s*(?:or\s+later|onwards?|and\s+(?:after|later)|or\s+after)\b", re.IGNORECASE
)
_YEAR_UPPER_BOUND = re.compile(
    r"\s*(?:or\s+earlier|and\s+(?:before|earlier)|or\s+before|and\s+prior)\b", re.IGNORECASE
)

#: Shapes in which a four-digit number is part of something else. These are orthographic
#: guards on the characters touching the number, not a vocabulary: a year wedged between a
#: day and a month is a date, and one hanging off a letter prefix is a requisition code.
#: Both can sit in the same clause as genuine graduation wording — *"Apply by 2025-03-01 if
#: graduating in 2026"* — where the context test alone would admit them and manufacture a
#: competing window out of a deadline.
_DATE_BEFORE = re.compile(r"\d{1,2}\s*[-/]\s*$")
_DATE_AFTER = re.compile(r"^\s*[-/]\s*\d{1,2}(?!\d)")
_CODE_BEFORE = re.compile(r"[A-Za-z]{2,}\s*[-/]\s*$")
_CODE_AFTER = re.compile(r"^\s*[-/]\s*[A-Za-z]")


def _grad_years_in(clause: str) -> list[tuple[GradYearWindowValue, int, int]]:
    """Every graduation window the clause states, with the span of its opening year."""
    found: list[tuple[GradYearWindowValue, int, int]] = []
    #: Positions already read as the closing year of an explicit range. ``2025-2026`` states
    #: one window, not also an exact 2026 — and emitting both would make a single posting
    #: compete with itself and lose the requirement it plainly states.
    consumed: set[int] = set()

    for match in _YEAR.finditer(clause):
        year = int(match.group(1))
        if match.start() in consumed or not MIN_YEAR <= year <= MAX_YEAR:
            continue

        head = clause[max(0, match.start() - _KEYWORD_LOOKBEHIND) : match.start()]
        tail = clause[match.end() : match.end() + _KEYWORD_LOOKBEHIND]
        if not _GRAD_CONTEXT.search(head) and not _GRAD_CONTEXT.search(tail):
            continue
        if _DATE_BEFORE.search(head) or _CODE_BEFORE.search(head):
            continue
        if _DATE_AFTER.match(tail) or _CODE_AFTER.match(tail):
            continue

        span = _YEAR_RANGE.match(tail)
        if span is not None:
            other = int(span.group(1))
            if MIN_YEAR <= other <= MAX_YEAR and other >= year:
                closing = match.end() + span.start(1)
                consumed.add(closing)
                found.append(
                    (
                        GradYearWindowValue(min_grad_year=year, max_grad_year=other),
                        match.start(),
                        closing + len(span.group(1)),
                    )
                )
                continue

        bound = _YEAR_LOWER_BOUND.match(tail)
        if bound is not None:
            value = GradYearWindowValue(min_grad_year=year, max_grad_year=None)
        else:
            bound = _YEAR_UPPER_BOUND.match(tail)
            if bound is not None:
                value = GradYearWindowValue(min_grad_year=None, max_grad_year=year)
            else:
                value = GradYearWindowValue(min_grad_year=year, max_grad_year=year)
        end = match.end() + (bound.end() if bound is not None else 0)
        found.append((value, match.start(), end))
    return found


# ---------------------------------------------------------------------------------------
# Field 3 — a backlog limit
# ---------------------------------------------------------------------------------------

#: Adjectives a posting puts between the count and the word. Optional, and never required:
#: *"maximum 2 backlogs"* and *"maximum 2 active backlogs"* state the same limit.
_BACKLOG_QUALIFIER = r"(?:active\s+|current\s+|standing\s+|live\s+|pending\s+)?"

#: A limit of zero, stated in words. *"no active backlogs"* is the commonest real phrasing and
#: states its limit as explicitly as *"maximum 0 backlogs"* would.
#:
#: ``without`` is **not** listed, although the verifier's corresponding pattern appears to
#: list it. In that pattern the alternative is followed by a mandatory ``\s+`` that the
#: alternative has already consumed, so it can only ever fire on a double space — which
#: ``collapse_whitespace`` guarantees pinned text never contains. Recognising *"without
#: backlogs"* here would produce a proposal the verifier then refuses on condition 5, so this
#: module matches the behaviour that exists rather than the behaviour the pattern reads like.
#: The verifier defect is recorded for its own review; it is not fixed from here.
_BACKLOG_ZERO = re.compile(
    rf"\b(?:no|zero|nil)\s+{_BACKLOG_QUALIFIER}backlogs?\b", re.IGNORECASE
)

#: *"maximum 2 backlogs"* — the quantifier leads. A bare ``backlog`` with no quantifier frame
#: produces nothing at all, which is what keeps *"product backlog"* and *"a backlog of support
#: tickets"* out without needing to know what either phrase means.
_BACKLOG_LEADING = re.compile(
    rf"\b(?:maximum|max\.?|at\s+most|not?\s+more\s+than|up\s*to|upto)\s+(?:of\s+)?"
    rf"(\d{{1,2}})\s+{_BACKLOG_QUALIFIER}backlogs?\b",
    re.IGNORECASE,
)

#: *"2 backlogs or fewer"* — the quantifier trails. Both word orders occur in real postings.
_BACKLOG_TRAILING = re.compile(
    rf"\b(\d{{1,2}})\s+{_BACKLOG_QUALIFIER}backlogs?\s+"
    rf"(?:or\s+fewer|or\s+less|maximum|at\s+most|allowed|permitted)\b",
    re.IGNORECASE,
)


def _backlogs_in(clause: str) -> list[tuple[MaxBacklogsValue, int, int]]:
    """Every backlog limit the clause states, with the span of the phrase stating it."""
    found: list[tuple[MaxBacklogsValue, int, int]] = [
        (MaxBacklogsValue(max_backlogs=0), match.start(), match.end())
        for match in _BACKLOG_ZERO.finditer(clause)
    ]
    for pattern in (_BACKLOG_LEADING, _BACKLOG_TRAILING):
        found.extend(
            (
                MaxBacklogsValue(max_backlogs=int(match.group(1))),
                match.start(),
                match.end(),
            )
            for match in pattern.finditer(clause)
        )
    return found


# ---------------------------------------------------------------------------------------
# Proposal assembly
# ---------------------------------------------------------------------------------------


def _proposal(
    value: DerivedValue, evidence: str, extractor: str
) -> ExtractionProposal:
    """Wrap one read value as a proposal. Nothing here decides whether it is a requirement.

    ``reported_strength`` is whatever :func:`recognise_strength` read from this evidence, and
    ``None`` when it read nothing or read a conflict. Either way the verifier re-reads the
    evidence itself and distinguishes *"no marker"* from *"two markers"* in its own failure
    codes; reporting ``None`` for both can only lower trust, never raise it.

    ``reported_confidence`` is ``MEDIUM`` for every deterministic result, following D7a's cap
    on prose-derived confidence. It is descriptive and inert — the verifier reads no
    confidence at any point, by design (D7).
    """
    return ExtractionProposal(
        requirement_type=value.requirement_type,
        value=value,
        evidence_text=evidence,
        provenance=RequirementProvenance.PROSE_DERIVED,
        extractor=extractor,
        extractor_version=EXTRACTOR_VERSION,
        provider=None,
        model=None,
        reported_strength=recognise_strength(evidence).strength,
        reported_confidence=Confidence.MEDIUM,
    )


#: What every per-field scanner above looks like: pinned clause in, each value it states out,
#: paired with the span of the text stating it. The span never leaves this module — it chooses
#: what to quote and is then discarded, because an offset is valid against one exact string
#: and is never authoritative provenance (ADR-030 D9, OD-3).
_ClauseScanner = Callable[[str], Sequence[tuple[DerivedValue, int, int]]]


def _extract(
    description: str,
    scan: _ClauseScanner,
    extractor: str,
) -> tuple[ExtractionProposal, ...]:
    """Run one clause scanner over a whole description and assemble its proposals.

    The description is pinned with ``collapse_whitespace`` first — the repository's single
    normalization for this, and the exact form ``jobs.description`` is stored in (D9). It is
    idempotent, so a caller passing the already-stored string gets the same result as one
    passing a raw payload, and evidence quoted from it is locatable in the stored text.

    Identical readings of the same statement collapse to one proposal. Two *different* values
    never collapse: they are emitted separately and left to compete, because choosing between
    them is precisely what D8 forbids this module from doing.
    """
    pinned = collapse_whitespace(description)
    proposals: list[ExtractionProposal] = []
    seen: set[tuple[object, str]] = set()
    for clause in _clauses(pinned):
        for value, start, end in scan(clause):
            evidence = _evidence(clause, start, end)
            key = (value, evidence)
            if key in seen:
                continue
            seen.add(key)
            proposals.append(_proposal(value, evidence, extractor))
    return tuple(proposals)


def extract_min_cgpa(description: str) -> tuple[ExtractionProposal, ...]:
    """Propose every minimum grade the description states **with an explicit scale**.

    A grade with no stated scale produces nothing. It is not a usable requirement
    (``standards/eligibility.md`` §4, ADR-030 D11) — the engine could only ever report it as
    ``JOB_SCALE_MISSING`` — and supplying the missing scale would be the guess ADR-018 and
    ADR-030 both forbid.
    """
    return _extract(description, _cgpa_in, CGPA_EXTRACTOR)


def extract_grad_year_window(description: str) -> tuple[ExtractionProposal, ...]:
    """Propose every graduation window the description states in explicit graduation wording.

    A bare year produces nothing, and neither does a year that is part of a date or a
    requisition code. An open-ended *"2026 or later"* becomes a lower bound, *"or earlier"* an
    upper one, and an explicit range both.
    """
    return _extract(description, _grad_years_in, GRAD_YEAR_EXTRACTOR)


def extract_max_backlogs(description: str) -> tuple[ExtractionProposal, ...]:
    """Propose every backlog limit the description states in an explicit quantifier frame.

    A mention of backlogs with no frame produces nothing — not a limit of zero, not a limit at
    all. *"Backlogs will be considered on a case-by-case basis"* says something about backlogs
    and states no limit whatever.
    """
    return _extract(description, _backlogs_in, BACKLOG_EXTRACTOR)


def extract_requirements(description: str) -> tuple[ExtractionProposal, ...]:
    """Propose every Phase 1 requirement the description states, in field order.

    The whole deterministic surface of ADR-030 D11. The result is ordered — CGPA, then
    graduation year, then backlogs, each in the order the description states them — so the
    output is reproducible for a given input, which is what makes it testable and what makes a
    stored extraction comparable with a later one.

    Pass the result to :func:`~app.services.requirement_verifier.verify_proposals`, which
    applies all eight conditions and then D8's competing-proposal rule across the collection.
    """
    return (
        *extract_min_cgpa(description),
        *extract_grad_year_window(description),
        *extract_max_backlogs(description),
    )


__all__ = [
    "BACKLOG_EXTRACTOR",
    "CGPA_EXTRACTOR",
    "EXTRACTOR_VERSION",
    "GRAD_YEAR_EXTRACTOR",
    "MAX_EVIDENCE_CHARS",
    "extract_grad_year_window",
    "extract_max_backlogs",
    "extract_min_cgpa",
    "extract_requirements",
]
