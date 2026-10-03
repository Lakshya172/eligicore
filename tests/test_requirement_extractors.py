"""Deterministic requirement extractor tests (ADR-030 D11).

The extractor is the only thing in the pipeline that *originates* a claim about a job, so
these tests are written around two questions: does it read what the posting actually says,
and does it stay silent when the posting says nothing safe? A false negative costs a job its
criterion, which ADR-003 treats as ordinary. A false positive tells a qualified candidate not
to apply, which the system must never do on its own authority.

**Every fixture here is public job prose.** No candidate, no profile, no personal data — the
extractor has no parameter for any of it, and these tests assert that too.

The final section runs extractor output through the **unmodified** verifier, because the two
only mean anything together: an extractor whose proposals never verify is a no-op, and one
whose proposals always verify has absorbed the authority ADR-030 D6 puts somewhere else.
"""

from __future__ import annotations

import ast
import inspect
import pathlib

import pytest

from app.schemas.candidate import Confidence, GradeScale
from app.schemas.eligibility import RequirementType
from app.schemas.extraction import (
    PHASE_1_REQUIREMENT_TYPES,
    ExtractionProposal,
    GradYearWindowValue,
    MaxBacklogsValue,
    MinCgpaValue,
    RequirementProvenance,
    RequirementStrength,
    VerificationFailure,
)
from app.services import requirement_extractors
from app.services.job_normalizer import collapse_whitespace
from app.services.requirement_extractors import (
    BACKLOG_EXTRACTOR,
    CGPA_EXTRACTOR,
    EXTRACTOR_VERSION,
    GRAD_YEAR_EXTRACTOR,
    MAX_EVIDENCE_CHARS,
    extract_grad_year_window,
    extract_max_backlogs,
    extract_min_cgpa,
    extract_requirements,
)
from app.services.requirement_verifier import (
    MAX_YEAR,
    MIN_YEAR,
    StrengthRecognition,
    recognise_strength,
    verify_proposal,
    verify_proposals,
)

MODULE = pathlib.Path(requirement_extractors.__file__)

PUBLIC_EXTRACTORS = (
    extract_min_cgpa,
    extract_grad_year_window,
    extract_max_backlogs,
    extract_requirements,
)


# ---------------------------------------------------------------------------------------
# Helpers — every test asks one of three questions about a string
# ---------------------------------------------------------------------------------------


def cgpa_values(text: str) -> list[tuple[float, GradeScale]]:
    """The ``(grade, scale)`` pairs the extractor reads, in order."""
    return [
        (p.value.min_cgpa, p.value.min_cgpa_scale)
        for p in extract_min_cgpa(text)
        if isinstance(p.value, MinCgpaValue)
    ]


def grad_windows(text: str) -> list[tuple[int | None, int | None]]:
    """The ``(min_year, max_year)`` windows the extractor reads, in order."""
    return [
        (p.value.min_grad_year, p.value.max_grad_year)
        for p in extract_grad_year_window(text)
        if isinstance(p.value, GradYearWindowValue)
    ]


def backlog_limits(text: str) -> list[int]:
    """The backlog limits the extractor reads, in order."""
    return [
        p.value.max_backlogs
        for p in extract_max_backlogs(text)
        if isinstance(p.value, MaxBacklogsValue)
    ]


def verified_of(text: str) -> tuple[object, ...]:
    """What survives the whole pipeline — extract, then verify against the pinned text."""
    pinned = collapse_whitespace(text)
    return verify_proposals(extract_requirements(text), pinned).verified


def failures_of(text: str) -> list[set[VerificationFailure]]:
    """Per-proposal failure sets, for asserting *why* something was refused."""
    pinned = collapse_whitespace(text)
    result = verify_proposals(extract_requirements(text), pinned)
    return [set(outcome.failures) for outcome in result.outcomes]


#: Prose that mentions no criterion at all, used to pad a clause past the evidence cap.
FILLER = (
    "we build data platforms and developer tooling for engineering teams across the region "
)


# ---------------------------------------------------------------------------------------
# Purity and privacy — asserted on the module, not promised in a docstring
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "forbidden",
    [
        "fastapi",
        "sqlalchemy",
        "httpx",
        "requests",
        "logging",
        "os",
        "sys",
        "subprocess",
        "pathlib",
        "socket",
        "urllib",
        "google",
        "openai",
        "anthropic",
        "app.database",
        "app.models",
        "app.config",
        "app.ai",
        "app.adapters",
        "app.routers",
    ],
)
def test_extractor_imports_no_framework_database_provider_or_logger(forbidden: str) -> None:
    """The extractor is pure parsing. Anything on this list would make it something else.

    Parsed from the real import statements rather than searched for as text, so a module
    named in a docstring or a comment cannot pass or fail this by accident.
    """
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    offenders = {
        name
        for name in imported
        if name == forbidden or name.startswith(f"{forbidden}.")
    }
    assert not offenders, f"{MODULE.name} imports {sorted(offenders)}"


@pytest.mark.parametrize(
    "forbidden",
    ["CandidateProfile", "ResumeExtraction", "EligibilityResult", "ExtractedRequirement"],
)
def test_extractor_imports_no_candidate_or_persistence_type(forbidden: str) -> None:
    """No candidate type and no ORM model. The extractor reads public job prose only."""
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert forbidden not in imported


def test_extractor_defines_no_logger() -> None:
    """INV-4. A description is third-party text and an evidence string quotes it verbatim."""
    source = MODULE.read_text(encoding="utf-8")
    for marker in ("getLogger", "logger", "logging.", "print("):
        assert marker not in source, f"{MODULE.name} contains {marker!r}"


@pytest.mark.parametrize("function", PUBLIC_EXTRACTORS, ids=lambda f: f.__name__)
def test_extractor_takes_job_text_and_nothing_else(function: object) -> None:
    """The signature is the privacy boundary (ADR-030 D13, D24).

    One parameter, a string, named for what it is. There is no candidate argument to pass
    even by mistake, and no keyword a caller could smuggle a profile through.
    """
    signature = inspect.signature(function)  # type: ignore[arg-type]
    assert list(signature.parameters) == ["description"]
    parameter = signature.parameters["description"]
    assert parameter.annotation == "str"
    assert parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD


def test_extractor_never_produces_a_verified_requirement() -> None:
    """There is no path from this module to a verified requirement (ADR-030 D6).

    The extractor proposes; the verifier decides. A ``VerifiedDerivedRequirement`` constructed
    anywhere in here would be the authority bypass D6 exists to prevent, so the name must not
    appear in the module at all.
    """
    source = MODULE.read_text(encoding="utf-8")
    assert "VerifiedDerivedRequirement(" not in source
    assert "VerificationOutcome(" not in source
    assert "verified=" not in source


# ---------------------------------------------------------------------------------------
# Module contract
# ---------------------------------------------------------------------------------------


def test_extractor_identities_follow_the_documented_form() -> None:
    """``deterministic.<field>``, which is the example the proposal schema itself gives."""
    assert CGPA_EXTRACTOR == "deterministic.cgpa"
    assert GRAD_YEAR_EXTRACTOR == "deterministic.grad_year"
    assert BACKLOG_EXTRACTOR == "deterministic.backlogs"
    assert len({CGPA_EXTRACTOR, GRAD_YEAR_EXTRACTOR, BACKLOG_EXTRACTOR}) == 3


def test_extractor_version_is_populated_and_within_the_schema_bound() -> None:
    """D22 makes a version change an explicit re-extraction trigger, so it must be real."""
    assert EXTRACTOR_VERSION
    assert 1 <= len(EXTRACTOR_VERSION) <= 50


def test_the_evidence_cap_is_pinned_to_a_literal() -> None:
    """Asserted against a number, not against the constant.

    Every other test measures evidence with ``MAX_EVIDENCE_CHARS`` itself, which keeps them
    readable but means none of them would notice the cap being raised. This one would.
    """
    assert MAX_EVIDENCE_CHARS == 300


def test_extracted_types_are_exactly_the_phase_1_three() -> None:
    """D11 and D12. A fourth field is a new ADR, never a new branch in this module."""
    produced = {
        proposal.requirement_type
        for text in (
            "Minimum CGPA 7.5/10 required.",
            "Graduation year 2026 required.",
            "Maximum 2 backlogs permitted.",
        )
        for proposal in extract_requirements(text)
    }
    assert produced == set(PHASE_1_REQUIREMENT_TYPES)


def test_empty_and_blank_descriptions_produce_nothing() -> None:
    for text in ("", "   ", "\n\n\t"):
        assert extract_requirements(text) == ()


# ---------------------------------------------------------------------------------------
# Field 1 — CGPA and its scale
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Minimum CGPA 7.5/10 required.", (7.5, GradeScale.SCALE_10)),
        ("Minimum CGPA 8.2 out of 10 required.", (8.2, GradeScale.SCALE_10)),
        ("CGPA of 7.5 on a 10 point scale is required.", (7.5, GradeScale.SCALE_10)),
        ("Minimum GPA 3.5/4 required.", (3.5, GradeScale.SCALE_4)),
        ("Minimum CGPA 4.2/5 required.", (4.2, GradeScale.SCALE_5)),
        ("Minimum aggregate 60% required.", (60.0, GradeScale.PERCENTAGE)),
        ("Minimum aggregate 60 percent required.", (60.0, GradeScale.PERCENTAGE)),
        ("Minimum percentage 60% required.", (60.0, GradeScale.PERCENTAGE)),
        ("Minimum marks 75% required.", (75.0, GradeScale.PERCENTAGE)),
        ("Minimum grade 8/10 required.", (8.0, GradeScale.SCALE_10)),
        ("7.5/10 CGPA required.", (7.5, GradeScale.SCALE_10)),
    ],
)
def test_supported_cgpa_forms_are_read_with_their_scale(
    text: str, expected: tuple[float, GradeScale]
) -> None:
    """Every phrasing the verifier's contract recognises, read as a grade and a scale."""
    assert cgpa_values(text) == [expected]


def test_a_cgpa_without_a_scale_produces_no_proposal() -> None:
    """A cutoff with no scale is comparable to nothing (``standards/eligibility.md`` §4).

    The engine could only ever report it as ``JOB_SCALE_MISSING``, and supplying the missing
    scale would be the guess ADR-018 and ADR-030 both forbid. So nothing is produced — not a
    proposal carrying ``UNKNOWN``, which would merely move the guess downstream.
    """
    assert cgpa_values("Minimum CGPA 7.5 required.") == []
    assert cgpa_values("A CGPA of at least 8 is mandatory.") == []


def test_a_scale_the_system_cannot_compare_against_produces_no_proposal() -> None:
    """``7.5/7`` states a scale, but not one :class:`GradeScale` defines."""
    assert cgpa_values("Minimum CGPA 7.5/7 required.") == []
    assert cgpa_values("Minimum CGPA 3.1/3 required.") == []


def test_unknown_is_never_produced_as_a_scale() -> None:
    """The one scale with no maximum must be unreachable from extraction."""
    corpus = " ".join(
        [
            "Minimum CGPA 7.5/10 required.",
            "Minimum CGPA 7.5 required.",
            "Minimum aggregate 60% required.",
            "Minimum CGPA 7.5/7 required.",
        ]
    )
    scales = {value.min_cgpa_scale for value in (p.value for p in extract_min_cgpa(corpus))}
    assert GradeScale.UNKNOWN not in scales


@pytest.mark.parametrize(
    "text",
    [
        "The role requires 7.5 years of experience.",
        "Minimum 7.5 years of experience required.",
        "Compensation is 18 LPA to 24 LPA.",
        "The contract runs for 6 months.",
        "Requisition REQ-2026-ABC is open.",
        "Posted 2026-01-15, applications close 2026-03-01.",
        "Call 98765 43210 for details.",
        "Team of 12 engineers, 3 designers.",
        # The other half of the pair: a number that *does* carry a scale, and still is not
        # a grade. Without the keyword guard every one of these becomes a CGPA cutoff.
        "Rated 9/10 by our own employees.",
        "Satisfaction score 80% last quarter.",
        "Completed 8 out of 10 sprints on time.",
        "Uptime 99% last year.",
        "We ship 4 out of 5 releases on schedule.",
    ],
)
def test_numbers_that_are_not_grades_produce_no_cgpa_proposal(text: str) -> None:
    """The canonical false positive of D6 condition 5, refused before it is ever proposed.

    Two guards are needed and both are load-bearing. The **mandatory scale** refuses
    *"7.5 years of experience"*, which has the number and the sentence shape of a cutoff and
    none of its meaning. The **grade keyword** refuses *"rated 9/10"* and *"score 80%"*,
    which carry a perfectly good scale and are not about grades at all — and ``score`` is
    deliberately absent from the keyword set for exactly that reason.
    """
    assert cgpa_values(text) == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Minimum CGPA 10/10 required.", [(10.0, GradeScale.SCALE_10)]),
        ("Minimum aggregate 100% required.", [(100.0, GradeScale.PERCENTAGE)]),
        ("Minimum CGPA 0/10 required.", [(0.0, GradeScale.SCALE_10)]),
        ("Minimum CGPA 10.5/10 required.", [(10.5, GradeScale.SCALE_10)]),
    ],
)
def test_boundary_grades_are_read_and_left_for_the_verifier_to_judge(
    text: str, expected: list[tuple[float, GradeScale]]
) -> None:
    """The extractor reads what the text says; structural validity is condition 2's job.

    ``0/10`` and ``10.5/10`` are both stated by their sentences and both refused by
    :func:`verify_proposal`. Filtering them here would make condition 2 unreachable for
    deterministic input and hide a genuinely malformed posting behind silence.
    """
    assert cgpa_values(text) == expected


@pytest.mark.parametrize("text", ["Minimum CGPA 0/10 required.", "Minimum CGPA 10.5/10 required."])
def test_structurally_invalid_grades_are_refused_by_the_verifier(text: str) -> None:
    assert verified_of(text) == ()
    assert VerificationFailure.MALFORMED_VALUE in failures_of(text)[0]


def test_two_competing_cgpa_values_are_both_proposed_and_neither_promoted() -> None:
    """ADR-030 D8's worked case, end to end through the real verifier.

    The extractor proposes both. It does not choose, does not prefer the first, and does not
    correct 7.5 to 7.0 — *"the system never picks a winner"*. Condition 7 refuses the
    preferred clause on its marker and condition 8 refuses both independently, because each
    sits inside the other's contradiction window.
    """
    text = "Minimum CGPA 7.0/10 required. CGPA 7.5/10 preferred."
    assert cgpa_values(text) == [(7.0, GradeScale.SCALE_10), (7.5, GradeScale.SCALE_10)]
    assert verified_of(text) == ()

    required_clause, preferred_clause = failures_of(text)
    assert VerificationFailure.CONTRADICTED_IN_WINDOW in required_clause
    assert VerificationFailure.STRENGTH_NOT_REQUIRED in preferred_clause


def test_two_competing_values_in_one_clause_are_both_proposed() -> None:
    """One sentence stating two cutoffs is still two readings, and still no winner."""
    text = "CGPA 7.5/10 preferred, 7.0/10 required."
    assert cgpa_values(text) == [(7.5, GradeScale.SCALE_10), (7.0, GradeScale.SCALE_10)]
    assert verified_of(text) == ()


def test_the_same_value_stated_twice_is_proposed_once_per_statement() -> None:
    """Identical readings of the same clause collapse; separate statements do not.

    Two clauses saying the same thing are two pieces of evidence, and condition 8 applies to
    each separately — collapsing them would silently drop a window that might have been
    qualified.
    """
    assert len(extract_min_cgpa("Minimum CGPA 7.5/10 or 7.5/10 required.")) == 1
    assert len(extract_min_cgpa("Minimum CGPA 7.5/10 required. Minimum CGPA 7.5/10.")) == 2


# ---------------------------------------------------------------------------------------
# Field 2 — graduation year
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Candidates graduating 2026 are required to apply.", (2026, 2026)),
        ("Graduation year 2026 required.", (2026, 2026)),
        ("Passing out 2026 required.", (2026, 2026)),
        ("Pass-out 2026 required.", (2026, 2026)),
        ("Class of 2026 required.", (2026, 2026)),
        ("Batch of 2026 required.", (2026, 2026)),
        ("Year of passing 2026 required.", (2026, 2026)),
        ("2025-2026 batch required.", (2025, 2026)),
        ("2025–2026 batch required.", (2025, 2026)),
        ("Year of passing 2025 to 2026 required.", (2025, 2026)),
        ("Graduating 2026 or later required.", (2026, None)),
        ("Graduation 2024 onwards required.", (2024, None)),
        ("Graduating 2026 or earlier required.", (None, 2026)),
        ("Graduating 2026 and prior required.", (None, 2026)),
    ],
)
def test_supported_graduation_forms_are_read_with_the_right_bounds(
    text: str, expected: tuple[int | None, int | None]
) -> None:
    """An exact year, an explicit range, and each open end. Min/max semantics preserved."""
    assert grad_windows(text) == [expected]


def test_a_stated_range_is_one_window_and_not_also_an_exact_year() -> None:
    """``2025-2026`` states one window.

    Reading the closing year a second time as an exact window would make the posting compete
    with itself, and condition 8 would then refuse the very requirement it plainly states.
    """
    assert grad_windows("2025-2026 batch required.") == [(2025, 2026)]
    assert len(extract_grad_year_window("2025-2026 batch required.")) == 1
    assert len(verified_of("2025-2026 batch required.")) == 1


@pytest.mark.parametrize(
    "text",
    [
        "2026",
        "We shipped 2026 features last quarter.",
        "The office opened in 2019 and moved in 2021.",
        "Posted 2026-01-15. Apply now.",
        "Applications close 2026-03-01.",
        "Requisition REQ-2026-ABC is open.",
        "Order reference 2026/4471 refers.",
        "Call 2026 555 0199 for details.",
        "Compensation is 2026 USD per week.",
    ],
)
def test_a_year_without_graduation_context_produces_nothing(text: str) -> None:
    """A bare four-digit number is a number.

    Reading every one as a year is how a salary band becomes an eligibility window, and the
    system has no way to tell a candidate it guessed.
    """
    assert grad_windows(text) == []


def test_a_deadline_sharing_a_clause_with_graduation_wording_is_not_a_year() -> None:
    """The guard the verifier does not need and an extractor does.

    *"Apply by 2025-03-01 if graduating in 2026"* puts a date inside the graduation context
    window. Without the date guard the extractor would read 2025 as a second window, the two
    would compete, and a posting that states exactly one graduation year would end up with
    none at all.
    """
    text = "Apply by 2025-03-01 if graduating in 2026."
    assert grad_windows(text) == [(2026, 2026)]


def test_a_requisition_code_sharing_a_clause_with_graduation_wording_is_not_a_year() -> None:
    text = "Graduating 2026 batch, requisition REQ-2024-ABC."
    assert grad_windows(text) == [(2026, 2026)]


@pytest.mark.parametrize(
    ("year", "produced"),
    [(MIN_YEAR - 1, False), (MIN_YEAR, True), (MAX_YEAR, True), (MAX_YEAR + 1, False)],
)
def test_graduation_years_outside_the_shared_bounds_are_not_read(
    year: int, produced: bool
) -> None:
    """``MIN_YEAR``/``MAX_YEAR`` are the verifier's own constants, imported rather than re-stated.

    A derived window must not be able to express something a source-stated one could not.
    """
    assert bool(grad_windows(f"Graduating {year} required.")) is produced


def test_two_competing_graduation_years_are_both_proposed_and_neither_promoted() -> None:
    """Separate statements, two readings, no winner — the D8 rule applied to years."""
    text = "Graduating in 2025 required. Graduating in 2026 required."
    assert grad_windows(text) == [(2025, 2025), (2026, 2026)]
    assert verified_of(text) == ()


def test_an_inverted_range_is_not_read_as_a_window() -> None:
    """``2026-2025`` is not a window, and inventing the ordering would be a correction."""
    assert grad_windows("2026-2025 batch required.") != [(2026, 2025)]


# ---------------------------------------------------------------------------------------
# Field 3 — backlogs
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Candidates must have no active backlogs.", 0),
        ("No backlogs required.", 0),
        ("Zero backlogs required.", 0),
        ("Nil backlogs required.", 0),
        ("No current backlogs required.", 0),
        ("No pending backlogs required.", 0),
        ("Maximum 2 backlogs permitted.", 2),
        ("Max. 2 backlogs permitted.", 2),
        ("At most 1 backlog allowed.", 1),
        ("Not more than 2 active backlogs required.", 2),
        ("No more than 3 backlogs required.", 3),
        ("Up to 2 backlogs required.", 2),
        ("Upto 1 backlog required.", 1),
        ("2 backlogs or fewer required.", 2),
        ("2 backlogs or less required.", 2),
        ("1 backlog at most required.", 1),
    ],
)
def test_supported_backlog_forms_are_read_as_limits(text: str, expected: int) -> None:
    """Both word orders — quantifier first and quantifier last — and the zero forms."""
    assert backlog_limits(text) == [expected]


def test_the_zero_forms_state_zero_and_not_absence() -> None:
    """*"no active backlogs"* states a limit of zero as explicitly as *"maximum 0"* would.

    It is the commonest phrasing in real postings, and refusing it for want of the character
    ``0`` would be a limitation of the parser rather than of the evidence.
    """
    assert backlog_limits("Candidates must have no active backlogs.") == [0]
    assert verified_of("Candidates must have no active backlogs.")[0].value.max_backlogs == 0


@pytest.mark.parametrize(
    "text",
    [
        "Product backlog grooming experience required.",
        "You will own the sprint backlog.",
        "A backlog of support tickets awaits.",
        "Backlogs will be considered.",
        "Backlogs are discussed case by case.",
        "Candidates with backlogs may apply.",
        "Tell us about your backlog management approach.",
        "The team maintains a technical debt backlog.",
    ],
)
def test_a_backlog_without_a_quantifier_frame_produces_nothing(text: str) -> None:
    """A mention of backlogs is not a limit — and emphatically not a limit of zero.

    No word list distinguishes a product backlog from an academic one. The quantifier frame
    does, without the extractor needing to know what either phrase means.
    """
    assert backlog_limits(text) == []


def test_a_generic_backlog_mention_does_not_become_a_zero_limit() -> None:
    """The most damaging possible false positive for this field, named on its own.

    A job that merely mentions backlogs, read as *"zero backlogs"*, excludes every candidate
    with one from a role the employer never closed to them.
    """
    assert backlog_limits("Backlogs will be considered on a case-by-case basis.") == []
    assert verified_of("Backlogs will be considered on a case-by-case basis.") == ()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("15 backlogs allowed.", [15]),
        ("Maximum 15 backlogs permitted.", [15]),
        ("Maximum 10 backlogs permitted.", [10]),
    ],
)
def test_a_longer_number_is_not_read_as_a_shorter_count(
    text: str, expected: list[int]
) -> None:
    """``15`` is fifteen. A limit of 1 or 5 read out of it would be a fabricated requirement."""
    assert backlog_limits(text) == expected


def test_competing_backlog_limits_are_both_proposed_and_neither_promoted() -> None:
    text = "Maximum 2 backlogs permitted. Maximum 1 backlog permitted."
    assert backlog_limits(text) == [2, 1]
    assert verified_of(text) == ()


def test_the_without_phrasing_is_deliberately_not_recognised() -> None:
    """A verifier limitation this module matches rather than works around.

    The verifier's zero-backlog pattern lists a ``without`` alternative that cannot fire: the
    alternative consumes its own trailing whitespace and is then followed by a mandatory
    ``\\s+``, so it needs a double space, which ``collapse_whitespace`` guarantees pinned text
    never contains. Recognising *"without backlogs"* here would produce a proposal condition 5
    then refuses — a requirement that silently never materialises. **The verifier is not
    changed from this PR**; the defect is recorded for its own review, and this test pins the
    current, consistent behaviour so that fixing it there turns this red rather than passing
    unnoticed.
    """
    assert backlog_limits("Without any backlogs required.") == []
    assert backlog_limits("Without backlogs required.") == []


# ---------------------------------------------------------------------------------------
# Strength — recognised, never inferred (ADR-030 D10, D10a)
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Minimum CGPA 7.5/10 required.", RequirementStrength.REQUIRED),
        ("CGPA 7.5/10 is mandatory.", RequirementStrength.REQUIRED),
        ("CGPA 7.5/10 preferred.", RequirementStrength.PREFERRED),
        ("CGPA 7.5/10 is desirable.", RequirementStrength.PREFERRED),
        ("CGPA 7.5/10 may be waived.", RequirementStrength.CONDITIONAL),
        ("CGPA 7.5/10 at the discretion of the panel.", RequirementStrength.CONDITIONAL),
        ("Typically CGPA 7.5/10.", RequirementStrength.INFORMATIONAL),
        ("Generally CGPA 7.5/10.", RequirementStrength.INFORMATIONAL),
    ],
)
def test_each_explicit_strength_class_is_reported_as_read(
    text: str, expected: RequirementStrength
) -> None:
    """Recognition, not classification: the marker is present in the evidence (D10a row B)."""
    assert extract_min_cgpa(text)[0].reported_strength is expected


def test_evidence_with_no_marker_reports_no_strength() -> None:
    """A bare *"CGPA 7.5/10"* says what the number is, never whether it gates anything.

    This is D10a's third row and the commonest shape in real prose. The extractor reports
    nothing, and the verifier refuses it with its own named failure.
    """
    proposal = extract_min_cgpa("CGPA 7.5/10.")[0]
    assert proposal.reported_strength is None
    assert VerificationFailure.STRENGTH_NOT_ESTABLISHED in failures_of("CGPA 7.5/10.")[0]


def test_conflicting_markers_report_no_strength() -> None:
    """Two marker classes in one evidence string is a conflict, not a majority vote."""
    text = "Minimum CGPA 7.5/10 required unless waived."
    assert extract_min_cgpa(text)[0].reported_strength is None
    assert VerificationFailure.STRENGTH_AMBIGUOUS in failures_of(text)[0]


def test_an_absent_marker_never_becomes_required() -> None:
    """The single most important property in this module, asserted over a corpus.

    *"An unestablished strength is not a weak REQUIRED; it is the absence of a strength"*
    (D10a). Nothing — a sentence that reads like a cutoff, a value repeated three times, a
    number with a scale — may promote silence into a gate.
    """
    unmarked = [
        "CGPA 7.5/10.",
        "CGPA 7.5/10. CGPA 7.5/10. CGPA 7.5/10.",
        "Eligibility: CGPA 7.5/10.",
        "We look for CGPA 7.5/10 in applicants.",
        "Graduating 2026.",
        "2026 batch.",
        "1 backlog allowed.",
    ]
    for text in unmarked:
        for proposal in extract_requirements(text):
            assert proposal.reported_strength is not RequirementStrength.REQUIRED, text
        assert verified_of(text) == (), text


def test_reported_strength_always_matches_the_shared_recognition_helper() -> None:
    """The extractor reads strength with the verifier's own function, never a second table.

    Two implementations would eventually disagree, and the disagreement would appear as a
    proposal reporting ``REQUIRED`` that the verifier then refuses — or worse, the reverse.
    """
    corpus = [
        "Minimum CGPA 7.5/10 required.",
        "CGPA 7.5/10 preferred.",
        "CGPA 7.5/10.",
        "CGPA 7.5/10 may be waived.",
        "Typically CGPA 7.5/10.",
        "Minimum CGPA 7.5/10 required unless waived.",
        "Maximum 2 backlogs permitted.",
        "Graduating 2026 or later required.",
    ]
    for text in corpus:
        for proposal in extract_requirements(text):
            recognised = recognise_strength(proposal.evidence_text)
            assert proposal.reported_strength is recognised.strength, text
            if recognised.recognition is not StrengthRecognition.ESTABLISHED:
                assert proposal.reported_strength is None, text


def test_a_non_required_statement_is_still_observed() -> None:
    """D10's *disclosed / observed* class survives as a proposal, refused by condition 7.

    Dropping it in the extractor would move condition 7 upstream and leave a posting's
    preference indistinguishable from a posting that said nothing — the verifier would report
    no failure because there would be no proposal to fail.
    """
    text = "CGPA 7.5/10 preferred."
    proposals = extract_min_cgpa(text)
    assert len(proposals) == 1
    assert proposals[0].reported_strength is RequirementStrength.PREFERRED
    assert verified_of(text) == ()
    assert VerificationFailure.STRENGTH_NOT_REQUIRED in failures_of(text)[0]


# ---------------------------------------------------------------------------------------
# The proposal contract
# ---------------------------------------------------------------------------------------

#: One description exercising all three fields, reused by the contract tests below.
WHOLE_POSTING = (
    "Software Engineer, Bengaluru. Compensation 18 LPA. Requires 7.5 years of experience "
    "with distributed systems. Requisition REQ-2026-ABC posted 2026-01-15. "
    "Eligibility: minimum CGPA 7.5/10 required. Candidates must have no active backlogs. "
    "Only the 2025-2026 graduating batch is required to apply."
)


def test_the_whole_posting_yields_one_proposal_per_field() -> None:
    """The noise — salary, experience, requisition, posting date — contributes nothing."""
    proposals = extract_requirements(WHOLE_POSTING)
    assert [p.requirement_type for p in proposals] == [
        RequirementType.MIN_CGPA,
        RequirementType.GRAD_YEAR_WINDOW,
        RequirementType.MAX_BACKLOGS,
    ]
    assert len(verify_proposals(proposals, collapse_whitespace(WHOLE_POSTING)).verified) == 3


@pytest.mark.parametrize(
    "proposal", extract_requirements(WHOLE_POSTING), ids=lambda p: p.requirement_type.value
)
def test_every_proposal_carries_the_contracted_provenance_fields(
    proposal: ExtractionProposal,
) -> None:
    """Provenance is the authority boundary (D1, D3) and is never anything else here."""
    assert proposal.provenance is RequirementProvenance.PROSE_DERIVED
    assert proposal.provider is None
    assert proposal.model is None
    assert proposal.extractor.startswith("deterministic.")
    assert proposal.extractor_version == EXTRACTOR_VERSION
    assert proposal.evidence_text.strip()
    assert proposal.reported_confidence is Confidence.MEDIUM
    assert proposal.requirement_type is proposal.value.requirement_type


def test_a_deterministic_proposal_never_names_a_provider_or_model() -> None:
    """D18 stores these; a deterministic extraction has neither, and must not invent one."""
    for proposal in extract_requirements(WHOLE_POSTING):
        assert proposal.provider is None and proposal.model is None


def test_reported_confidence_is_capped_and_changes_no_outcome() -> None:
    """D7a caps a prose-derived result at ``MEDIUM``; D7 makes confidence inert in verification.

    Re-verifying the same proposal with ``HIGH`` confidence and with none at all must give
    the identical outcome, or confidence has become an input to the eight conditions.
    """
    pinned = collapse_whitespace(WHOLE_POSTING)
    for proposal in extract_requirements(WHOLE_POSTING):
        assert proposal.reported_confidence is Confidence.MEDIUM
        baseline = verify_proposal(proposal, pinned)
        for confidence in (Confidence.HIGH, Confidence.LOW, None):
            altered = proposal.model_copy(update={"reported_confidence": confidence})
            assert verify_proposal(altered, pinned) == baseline


def test_no_proposal_field_can_carry_candidate_data() -> None:
    """INV-1 and D24, asserted on the shape of what the extractor emits."""
    forbidden = ("candidate", "applicant", "resume", "profile", "person", "student", "email")
    for proposal in extract_requirements(WHOLE_POSTING):
        assert not any(term in field.lower() for field in proposal.model_dump() for term in forbidden)


# ---------------------------------------------------------------------------------------
# Evidence — what is quoted, and that the verifier can find it
# ---------------------------------------------------------------------------------------

#: Descriptions exercising every field, every shape and most of the ways to say nothing.
EVIDENCE_CORPUS = (
    WHOLE_POSTING,
    "Minimum CGPA 7.5/10 required.",
    "Minimum aggregate 60% is mandatory.",
    "<ul><li>Minimum CGPA 7.5/10</li><li>Maximum 2 backlogs</li></ul>",
    "Eligibility criteria; minimum CGPA 8/10 required; no active backlogs required",
    "Graduating 2026 or later required.",
    "min. 7.5/10 CGPA. Students should apply early.",
    "CGPA 7.5/10 preferred. Graduating 2026.",
    "2025-2026 batch required. Max. 2 backlogs permitted.",
)


@pytest.mark.parametrize("text", EVIDENCE_CORPUS)
def test_evidence_is_verbatim_in_the_pinned_normalized_text(text: str) -> None:
    """Condition 4's precondition, met by construction rather than by luck.

    The extractor pins the description with ``collapse_whitespace`` — the same single
    normalization the stored column goes through (D9) — and quotes substrings of the result.
    """
    pinned = collapse_whitespace(text)
    for proposal in extract_requirements(text):
        assert proposal.evidence_text in pinned


def test_evidence_survives_a_raw_payload_with_uncollapsed_whitespace() -> None:
    """A caller may pass the raw description or the stored one; the evidence must match both.

    ``collapse_whitespace`` is idempotent, so pinning inside the extractor means a newline-
    and tab-ridden payload yields evidence locatable in exactly the string the database holds.
    """
    raw = "Eligibility:\n\n   Minimum CGPA 7.5/10   required.\t\tApply soon."
    pinned = collapse_whitespace(raw)
    assert "\n" not in pinned and "  " not in pinned

    from_raw = extract_requirements(raw)
    from_pinned = extract_requirements(pinned)
    assert [p.evidence_text for p in from_raw] == [p.evidence_text for p in from_pinned]
    assert from_raw[0].evidence_text in pinned
    assert len(verify_proposals(from_raw, pinned).verified) == 1


@pytest.mark.parametrize("text", EVIDENCE_CORPUS)
def test_evidence_never_exceeds_the_quotable_cap(text: str) -> None:
    for proposal in extract_requirements(text):
        assert 0 < len(proposal.evidence_text) <= MAX_EVIDENCE_CHARS


def test_a_long_clause_is_narrowed_and_still_verifies() -> None:
    """A posting with no punctuation still produces a quotable, locatable evidence string."""
    text = f"{FILLER * 6}minimum CGPA 7.5/10 required {FILLER * 6}"
    proposals = extract_min_cgpa(text)
    assert len(proposals) == 1

    evidence = proposals[0].evidence_text
    assert len(evidence) <= MAX_EVIDENCE_CHARS
    assert "minimum CGPA 7.5/10" in evidence
    assert evidence in collapse_whitespace(text)
    assert len(verify_proposals(proposals, collapse_whitespace(text)).verified) == 1


def test_narrowing_past_a_marker_refuses_rather_than_assumes() -> None:
    """Trimming can cost a statement its marker, and the answer is silence, not a guess.

    The marker here sits far enough from the value that the quotable span cannot reach it, so
    no strength is established and condition 7 refuses the proposal — which is the correct
    outcome for evidence that no longer shows the reader why the value was a requirement.
    """
    text = f"required {FILLER * 6}CGPA 7.5/10 {FILLER * 6}"
    proposal = extract_min_cgpa(text)[0]
    assert "required" not in proposal.evidence_text
    assert proposal.reported_strength is None
    assert verified_of(text) == ()


def test_a_clause_boundary_keeps_an_abbreviated_marker_with_its_value() -> None:
    """``min.`` and ``max.`` are explicit ``REQUIRED`` markers and must not be split off.

    The sentence rule requires a capital after the terminator precisely so that these survive
    without the extractor consulting a list of abbreviations, which D12 rules out.
    """
    for text in ("min. 7.5/10 CGPA. Students may apply.", "max. 2 backlogs. Apply soon."):
        proposal = extract_requirements(text)[0]
        assert proposal.reported_strength is RequirementStrength.REQUIRED
        assert len(verified_of(text)) == 1


def test_markup_separates_two_list_items_into_two_statements() -> None:
    """Greenhouse content is HTML and tags survive normalization as literal characters (D9).

    Without markup as a boundary the two bullets below would be one clause, and a posting
    stating a CGPA and a backlog limit would quote both in each piece of evidence.
    """
    text = "<ul><li>Minimum CGPA 7.5/10</li><li>Maximum 2 backlogs</li></ul>"
    proposals = extract_requirements(text)
    assert [p.evidence_text for p in proposals] == [
        "Minimum CGPA 7.5/10",
        "Maximum 2 backlogs",
    ]
    assert len(verify_proposals(proposals, collapse_whitespace(text)).verified) == 2


def test_evidence_carries_no_offsets() -> None:
    """Offsets are computed internally and discarded; they are not provenance (D9, OD-3)."""
    for proposal in extract_requirements(WHOLE_POSTING):
        assert "start" not in proposal.model_dump()
        assert "offset" not in proposal.model_dump()
    assert "offset" not in {field for field in ExtractionProposal.model_fields}


# ---------------------------------------------------------------------------------------
# Integration — the extractor's output through the unmodified verifier
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("text", EVIDENCE_CORPUS)
def test_every_proposal_states_a_value_its_own_evidence_supports(text: str) -> None:
    """Conditions 1 and 5 pass for everything this module emits.

    This is the alignment assertion: the extractor's grammar and the verifier's must agree,
    and a drift in either shows up here as a named failure rather than as a capability that
    quietly stops working.
    """
    pinned = collapse_whitespace(text)
    for proposal in extract_requirements(text):
        failures = set(verify_proposal(proposal, pinned).failures)
        assert VerificationFailure.VALUE_NOT_IN_EVIDENCE not in failures
        assert VerificationFailure.VALUE_NOT_SUPPORTED_BY_EVIDENCE not in failures
        assert VerificationFailure.EVIDENCE_NOT_IN_SOURCE not in failures
        assert VerificationFailure.EVIDENCE_EMPTY not in failures
        assert VerificationFailure.PROVENANCE_NOT_DERIVED not in failures
        assert VerificationFailure.UNRECOGNISED_REQUIREMENT_TYPE not in failures
        assert VerificationFailure.REQUIREMENT_TYPE_MISMATCH not in failures


def test_an_explicitly_required_cgpa_reaches_verification() -> None:
    """Phase 1 is a working capability, not a no-op (D11)."""
    text = "Minimum CGPA 7.5/10 required."
    verified = verified_of(text)
    assert len(verified) == 1
    assert verified[0].value.min_cgpa == 7.5
    assert verified[0].value.min_cgpa_scale is GradeScale.SCALE_10
    assert verified[0].provenance is RequirementProvenance.PROSE_DERIVED
    assert verified[0].strength is RequirementStrength.REQUIRED
    assert verified[0].extractor == CGPA_EXTRACTOR


def test_seven_point_five_years_of_experience_never_reaches_the_verifier() -> None:
    """The canonical false positive, refused one stage earlier than the verifier would.

    The verifier would refuse it on condition 5 if a proposal arrived. None does, because the
    scale is mandatory — and a value that is never proposed cannot be promoted by a later
    weakening of anything downstream.
    """
    text = "Minimum 7.5 years of experience required."
    assert extract_requirements(text) == ()
    assert verified_of(text) == ()


def test_a_preferred_cgpa_is_observed_but_never_verified() -> None:
    """The proposal exists and is classified; the requirement does not (D10)."""
    text = "CGPA 7.5/10 preferred."
    proposals = extract_min_cgpa(text)
    assert proposals and proposals[0].reported_strength is RequirementStrength.PREFERRED
    assert verified_of(text) == ()


def test_a_waived_requirement_is_not_silently_reconciled() -> None:
    """Condition 8's qualifying-language case, reached from real extractor output."""
    text = "Minimum CGPA 7.5/10 required. This requirement is waived for exceptional candidates."
    assert cgpa_values(text) == [(7.5, GradeScale.SCALE_10)]
    assert verified_of(text) == ()
    assert VerificationFailure.CONTRADICTED_IN_WINDOW in failures_of(text)[0]


def test_contradictory_values_are_never_reconciled_by_the_extractor() -> None:
    """Across all three fields: both readings survive to the verifier, neither is chosen."""
    cases = {
        "Minimum CGPA 7.0/10 required. Minimum CGPA 7.5/10 required.": 2,
        "Graduating 2025 required. Graduating 2026 required.": 2,
        "Maximum 1 backlog permitted. Maximum 2 backlogs permitted.": 2,
    }
    for text, expected_proposals in cases.items():
        proposals = extract_requirements(text)
        assert len(proposals) == expected_proposals, text
        assert verified_of(text) == (), text
        assert all(
            VerificationFailure.CONTRADICTED_IN_WINDOW in failures
            for failures in failures_of(text)
        ), text


def test_the_extractor_is_deterministic_across_repeated_calls() -> None:
    """Same input, same proposals, same order. A stored extraction must be comparable."""
    first = extract_requirements(WHOLE_POSTING)
    for _ in range(3):
        assert extract_requirements(WHOLE_POSTING) == first


def test_prose_that_states_no_criterion_produces_nothing() -> None:
    """Conservative absence is correct, and absence is never a failure for a candidate."""
    text = (
        "We are hiring a backend engineer. You will work with Python, Go and Kubernetes, "
        "own the product backlog, and collaborate with design. Compensation 18 to 24 LPA. "
        "Requires 5 years of experience. Requisition REQ-2026-ABC, posted 2026-01-15."
    )
    assert extract_requirements(text) == ()
