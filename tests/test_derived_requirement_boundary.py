"""The derived-requirement engine boundary (ADR-030 D20) and R-COLLISION (D20a).

Verified derived requirements reach the engine as a separate collection beside the job.
Every test here builds them directly, with no database and no extractor, which is what D20
requires the boundary to keep possible.

The properties that matter most are adversarial:

* a derived requirement never acquires ``SOURCE_STATED`` authority, and never produces
  ``NOT_ELIGIBLE`` (D2, D4);
* a source-stated requirement of the same type always wins, by **presence** — even when the
  source-stated value is unusable (D20a);
* a suppressed derived requirement leaves no trace in the breakdown, and nothing is mutated.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.schemas.candidate import CandidateProfile, Confidence, DegreeLevel, GradeScale
from app.schemas.eligibility import (
    EligibilityState,
    EvaluationMethod,
    ReasonCode,
    RequirementProvenance,
    RequirementResult,
    RequirementStatus,
    RequirementType,
)
from app.schemas.extraction import (
    GradYearWindowValue,
    MaxBacklogsValue,
    MinCgpaValue,
    VerifiedDerivedRequirement,
)
from app.schemas.job import JobRead
from app.services.eligibility_engine import (
    ambiguous_requirements,
    compose_verdict,
    effective_derived_requirements,
    evaluate_job,
    evaluate_requirements,
)
from tests.test_eligibility_engine import CGPA_JOB, EVERYTHING, FIELDS, edu, make_job, make_profile

SOURCE = RequirementProvenance.SOURCE_STATED
DERIVED = RequirementProvenance.PROSE_DERIVED
P, F, U = RequirementStatus.PASS, RequirementStatus.FAIL, RequirementStatus.UNKNOWN

CGPA_EVIDENCE = "A minimum CGPA of 7.0 on a 10 point scale is required."
WINDOW_EVIDENCE = "Candidates must graduate in 2026 or 2027."
BACKLOG_EVIDENCE = "No more than 1 active backlog is permitted."


def derived(
    requirement_type: RequirementType, value: Any, evidence: str
) -> VerifiedDerivedRequirement:
    return VerifiedDerivedRequirement(
        requirement_type=requirement_type,
        value=value,
        evidence_text=evidence,
        extractor="deterministic-test",
        extractor_version="1",
    )


def cgpa(minimum: float = 7.0, scale: GradeScale = GradeScale.SCALE_10) -> VerifiedDerivedRequirement:
    return derived(
        RequirementType.MIN_CGPA,
        MinCgpaValue(min_cgpa=minimum, min_cgpa_scale=scale),
        CGPA_EVIDENCE,
    )


def window(low: int | None = 2026, high: int | None = 2027) -> VerifiedDerivedRequirement:
    return derived(
        RequirementType.GRAD_YEAR_WINDOW,
        GradYearWindowValue(min_grad_year=low, max_grad_year=high),
        WINDOW_EVIDENCE,
    )


def backlogs(limit: int = 1) -> VerifiedDerivedRequirement:
    return derived(
        RequirementType.MAX_BACKLOGS, MaxBacklogsValue(max_backlogs=limit), BACKLOG_EVIDENCE
    )


def of_type(results: list[RequirementResult], kind: RequirementType) -> list[RequirementResult]:
    return [r for r in results if r.requirement_type is kind]


def assert_labelled_as_derived(result: RequirementResult, evidence: str) -> None:
    """Every field that makes an entry derived, asserted together (D7a, D20)."""
    assert result.provenance is DERIVED
    assert result.evidence == evidence
    assert result.method is EvaluationMethod.DETERMINISTIC
    expected = Confidence.LOW if result.status is U else Confidence.MEDIUM
    assert result.confidence is expected, (result.status, result.confidence)


# ---------------------------------------------------------------------------------------
# No derived input — the existing behaviour, exactly
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "job_fields",
    [{}, CGPA_JOB, EVERYTHING, {**EVERYTHING, "description": "Prose the engine does not read."}],
)
@pytest.mark.parametrize(
    "profile",
    [make_profile(), make_profile([edu(cgpa=6.0, grad_year=2030)], backlogs=4), make_profile([])],
)
def test_no_derived_requirements_changes_nothing(
    job_fields: dict[str, Any], profile: CandidateProfile
) -> None:
    job = make_job(**job_fields)
    baseline = evaluate_requirements(profile, job)
    assert evaluate_requirements(profile, job, ()) == baseline
    assert evaluate_requirements(profile, job, []) == baseline
    assert evaluate_job(profile, job, ()) == evaluate_job(profile, job)
    assert all(r.provenance is SOURCE and r.evidence is None for r in baseline)


# ---------------------------------------------------------------------------------------
# Derived PASS / FAIL / UNKNOWN — the shared comparison, labelled as derived
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "requirement,profile,status,reason",
    [
        (cgpa(7.0), make_profile([edu(cgpa=8.0)]), P, ReasonCode.MEETS_MINIMUM),
        (cgpa(9.0), make_profile([edu(cgpa=8.0)]), F, ReasonCode.BELOW_MINIMUM),
        (cgpa(7.0), make_profile([edu(cgpa=None)]), U, ReasonCode.MISSING_CANDIDATE_VALUE),
        (cgpa(3.0, GradeScale.SCALE_4), make_profile([edu(cgpa=8.0)]), U, ReasonCode.SCALE_MISMATCH),
        (window(2026, 2027), make_profile([edu(grad_year=2027)]), P, ReasonCode.WITHIN_WINDOW),
        (window(2028, None), make_profile([edu(grad_year=2027)]), F, ReasonCode.BEFORE_WINDOW),
        (window(None, 2026), make_profile([edu(grad_year=2027)]), F, ReasonCode.AFTER_WINDOW),
        (window(2026, 2027), make_profile([edu(grad_year=None)]), U, ReasonCode.MISSING_CANDIDATE_VALUE),
        (backlogs(1), make_profile(backlogs=1), P, ReasonCode.WITHIN_LIMIT),
        (backlogs(1), make_profile(backlogs=3), F, ReasonCode.EXCEEDS_LIMIT),
        (backlogs(1), make_profile(backlogs=None), U, ReasonCode.MISSING_CANDIDATE_VALUE),
    ],
)
def test_a_derived_requirement_is_evaluated_and_labelled(
    requirement: VerifiedDerivedRequirement,
    profile: CandidateProfile,
    status: RequirementStatus,
    reason: ReasonCode,
) -> None:
    (result,) = evaluate_requirements(profile, make_job(), [requirement])
    assert result.requirement_type is requirement.requirement_type
    assert (result.status, result.reason_code) == (status, reason)
    assert_labelled_as_derived(result, requirement.evidence_text)


def test_the_comparison_matches_the_source_stated_one_apart_from_the_label() -> None:
    """Shared logic: only provenance, evidence and confidence may differ (D20, D7a)."""
    profile = make_profile([edu(cgpa=6.5)])
    (source,) = evaluate_requirements(profile, make_job(**CGPA_JOB))
    (derived_result,) = evaluate_requirements(profile, make_job(), [cgpa(7.0)])
    differing = {
        name
        for name in RequirementResult.model_fields
        if getattr(source, name) != getattr(derived_result, name)
    }
    assert differing == {"provenance", "evidence", "confidence"}
    assert (source.confidence, derived_result.confidence) == (Confidence.HIGH, Confidence.MEDIUM)


def test_every_derived_result_is_labelled_when_all_three_types_are_present() -> None:
    results = evaluate_requirements(
        make_profile(backlogs=0), make_job(), [cgpa(), window(), backlogs()]
    )
    assert [r.requirement_type for r in results] == [
        RequirementType.MIN_CGPA,
        RequirementType.GRAD_YEAR_WINDOW,
        RequirementType.MAX_BACKLOGS,
    ]
    for result, evidence in zip(results, (CGPA_EVIDENCE, WINDOW_EVIDENCE, BACKLOG_EVIDENCE)):
        assert_labelled_as_derived(result, evidence)


def test_a_derived_entry_takes_its_types_place_in_the_breakdown() -> None:
    job = make_job(**FIELDS, min_degree_level=DegreeLevel.BACHELORS)
    results = evaluate_requirements(make_profile(), job, [cgpa()])
    assert [r.requirement_type for r in results] == [
        RequirementType.MIN_CGPA,
        RequirementType.MIN_DEGREE_LEVEL,
        RequirementType.ALLOWED_FIELDS,
    ]
    assert [r.provenance for r in results] == [DERIVED, SOURCE, SOURCE]


# ---------------------------------------------------------------------------------------
# Verdicts — authority follows provenance (D2, D4)
# ---------------------------------------------------------------------------------------


def test_a_derived_failure_is_needs_review_never_not_eligible() -> None:
    verdict = evaluate_job(make_profile([edu(cgpa=6.0)]), make_job(), [cgpa(7.0)])
    assert verdict.eligibility_state is EligibilityState.NEEDS_REVIEW


def test_derived_failures_of_every_type_together_are_still_needs_review() -> None:
    profile = make_profile([edu(cgpa=6.0, grad_year=2030)], backlogs=5)
    verdict = evaluate_job(profile, make_job(), [cgpa(7.0), window(), backlogs(1)])
    assert [r.status for r in verdict.requirement_breakdown] == [F, F, F]
    assert verdict.eligibility_state is EligibilityState.NEEDS_REVIEW


def test_an_all_derived_pass_is_likely_eligible_not_eligible() -> None:
    verdict = evaluate_job(make_profile(backlogs=0), make_job(), [cgpa(), window(), backlogs()])
    assert verdict.eligibility_state is EligibilityState.LIKELY_ELIGIBLE


def test_a_source_stated_failure_still_decides_beside_a_derived_pass() -> None:
    job = make_job(max_backlogs=0)
    verdict = evaluate_job(make_profile(backlogs=2), job, [cgpa(7.0)])
    assert verdict.eligibility_state is EligibilityState.NOT_ELIGIBLE


def test_the_summary_discloses_what_was_read_from_the_description() -> None:
    job = make_job(description="A minimum CGPA of 7.0 on a 10 point scale is required.")
    verdict = evaluate_job(make_profile([edu(cgpa=6.0)]), job, [cgpa(7.0)])
    assert "read from the job description were not met (minimum CGPA)" in verdict.summary
    assert "Requirements read from the job description are included above" in verdict.summary


# ---------------------------------------------------------------------------------------
# D4a — a derived failure does not close the AI stage, through the engine path
# ---------------------------------------------------------------------------------------

AMBIGUOUS_FIELD = [edu(cgpa=6.0, field_of_study="Computer Science and Engineering")]


def test_a_derived_failure_leaves_the_ambiguous_field_for_the_ai_stage() -> None:
    results = evaluate_requirements(make_profile(AMBIGUOUS_FIELD), make_job(**FIELDS), [cgpa(7.0)])
    derived_cgpa, field = results
    assert (derived_cgpa.provenance, derived_cgpa.status) == (DERIVED, F)
    assert field.reason_code is ReasonCode.FIELD_NOT_EXACT_MATCH
    assert ambiguous_requirements(results) == [1]


def test_a_source_stated_failure_still_closes_the_ai_stage_on_the_same_job() -> None:
    results = evaluate_requirements(make_profile(AMBIGUOUS_FIELD), make_job(**FIELDS, **CGPA_JOB))
    assert results[1].reason_code is ReasonCode.SKIPPED_AFTER_HARD_FAILURE
    assert ambiguous_requirements(results) == []


@pytest.mark.parametrize("ai_status", [P, F])
def test_the_verdict_stays_needs_review_whatever_the_ai_answers(
    ai_status: RequirementStatus,
) -> None:
    results = evaluate_requirements(make_profile(AMBIGUOUS_FIELD), make_job(**FIELDS), [cgpa(7.0)])
    (index,) = ambiguous_requirements(results)
    results[index] = results[index].model_copy(
        update={
            "status": ai_status,
            "method": EvaluationMethod.AI_REASONING,
            "confidence": Confidence.MEDIUM,
        }
    )
    assert compose_verdict(results) is EligibilityState.NEEDS_REVIEW


# ---------------------------------------------------------------------------------------
# R-COLLISION — the source-stated requirement wins, by presence (D20a)
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source_fields,requirement",
    [
        ({"min_cgpa": 6.0, "min_cgpa_scale": "SCALE_10"}, cgpa(9.0)),
        ({"min_grad_year": 2020, "max_grad_year": 2030}, window(2028, 2029)),
        ({"min_grad_year": 2020}, window(2028, 2029)),
        ({"max_grad_year": 2030}, window(2028, 2029)),
        ({"max_backlogs": 5}, backlogs(0)),
    ],
)
def test_a_source_stated_requirement_suppresses_a_derived_one_of_its_type(
    source_fields: dict[str, Any], requirement: VerifiedDerivedRequirement
) -> None:
    """The derived values here would FAIL the candidate; the source-stated ones PASS."""
    profile = make_profile([edu(cgpa=8.0, grad_year=2027)], backlogs=1)
    job = make_job(**source_fields)

    results = evaluate_requirements(profile, job, [requirement])
    (only,) = of_type(results, requirement.requirement_type)
    assert only.provenance is SOURCE
    assert only.evidence is None
    assert only.status is P
    assert results == evaluate_requirements(profile, job)
    assert effective_derived_requirements(job, [requirement]) == {}


@pytest.mark.parametrize("candidate_cgpa", [6.0, 9.5])
def test_a_cgpa_stated_without_a_scale_still_suppresses_the_derived_one(
    candidate_cgpa: float,
) -> None:
    """Presence wins, not usability: a derived value never decides a cell the employer's
    own structured statement could not (D20a)."""
    job = make_job(min_cgpa=7.0, min_cgpa_scale=None)
    (only,) = evaluate_requirements(
        make_profile([edu(cgpa=candidate_cgpa)]), job, [cgpa(7.0)]
    )
    assert (only.provenance, only.status) == (SOURCE, U)
    assert only.reason_code is ReasonCode.JOB_SCALE_MISSING
    assert only.evidence is None


def test_a_suppressed_requirement_never_reaches_the_breakdown_or_the_verdict() -> None:
    job = make_job(**EVERYTHING)
    profile = make_profile([edu(cgpa=9.0, grad_year=2027)], backlogs=0)
    verdict = evaluate_job(profile, job, [cgpa(9.5), window(2030, 2031), backlogs(0)])

    assert verdict == evaluate_job(profile, job)
    assert all(r.provenance is SOURCE for r in verdict.requirement_breakdown)
    assert all(r.evidence is None for r in verdict.requirement_breakdown)
    assert verdict.eligibility_state is EligibilityState.ELIGIBLE


def test_suppression_is_per_type() -> None:
    job = make_job(**CGPA_JOB)
    results = evaluate_requirements(make_profile(backlogs=0), job, [cgpa(9.0), backlogs(1)])
    assert [(r.requirement_type, r.provenance) for r in results] == [
        (RequirementType.MIN_CGPA, SOURCE),
        (RequirementType.MAX_BACKLOGS, DERIVED),
    ]


def test_a_derived_requirement_is_effective_once_the_source_states_nothing() -> None:
    requirement = cgpa(7.0)
    assert effective_derived_requirements(make_job(**CGPA_JOB), [requirement]) == {}
    assert effective_derived_requirements(make_job(), [requirement]) == {
        RequirementType.MIN_CGPA: requirement
    }


# ---------------------------------------------------------------------------------------
# Nothing is mutated (D20, D20a)
# ---------------------------------------------------------------------------------------


def test_evaluation_mutates_neither_the_job_nor_the_derived_requirements() -> None:
    job = make_job(**CGPA_JOB, description="Some prose.")
    profile = make_profile([edu(cgpa=6.0)], backlogs=2)
    supplied = [cgpa(9.0), window(), backlogs(1)]
    job_before = job.model_dump()
    profile_before = profile.model_dump()
    supplied_before = [r.model_dump() for r in supplied]

    evaluate_job(profile, job, supplied)

    assert job.model_dump() == job_before
    assert job.max_backlogs is None and job.min_grad_year is None, "derived value injected"
    assert profile.model_dump() == profile_before
    assert [r.model_dump() for r in supplied] == supplied_before
    assert len(supplied) == 3


def test_any_iterable_is_accepted_and_read_once() -> None:
    results = evaluate_requirements(make_profile(), make_job(), iter([cgpa()]))
    assert [r.provenance for r in results] == [DERIVED]


# ---------------------------------------------------------------------------------------
# Input the verifier never produces is refused, not guessed at
# ---------------------------------------------------------------------------------------


def test_two_derived_requirements_of_one_type_are_refused() -> None:
    with pytest.raises(ValueError, match="more than one derived requirement of type MIN_CGPA"):
        evaluate_requirements(make_profile(), make_job(), [cgpa(7.0), cgpa(8.0)])


def test_duplicates_are_refused_even_when_the_type_is_suppressed() -> None:
    """A caller bug is reported whether or not R-COLLISION would have hidden it."""
    with pytest.raises(ValueError, match="more than one"):
        evaluate_requirements(make_profile(), make_job(**CGPA_JOB), [cgpa(7.0), cgpa(7.0)])


def test_a_type_that_disagrees_with_its_value_is_refused() -> None:
    mismatched = derived(
        RequirementType.MAX_BACKLOGS, MinCgpaValue(min_cgpa=7.0, min_cgpa_scale=GradeScale.SCALE_10),
        CGPA_EVIDENCE,
    )
    with pytest.raises(ValueError, match="disagrees"):
        evaluate_requirements(make_profile(), make_job(), [mismatched])


def test_a_window_with_no_bound_is_refused() -> None:
    with pytest.raises(ValueError, match="at least one bound"):
        evaluate_requirements(make_profile(), make_job(), [window(None, None)])
