"""Deterministic eligibility engine — the suite the dossier requires at 100% (§17).

Pure unit tests: no server, no database, no AI. Every hard constraint has its boundary,
missing-value and invalid-value cases (``standards/testing.md`` §3), and every verdict
precedence combination from ADR-017 is asserted.

All data is obviously synthetic.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from app.schemas.candidate import CandidateProfile, Confidence, DegreeLevel, JobType
from app.schemas.eligibility import (
    EligibilityState,
    EvaluationMethod,
    JobEligibility,
    ReasonCode,
    RequirementResult,
    RequirementStatus,
    RequirementType,
)
from app.schemas.job import JobRead, JobStatusSchema
from app.services import eligibility_engine as engine
from app.services.eligibility_engine import (
    ambiguous_requirements,
    compose_verdict,
    evaluate_job,
    evaluate_requirements,
    select_qualification,
)

P, F, U = RequirementStatus.PASS, RequirementStatus.FAIL, RequirementStatus.UNKNOWN


# ---------------------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------------------


def make_job(**overrides: Any) -> JobRead:
    """A job stating no requirements unless overridden."""
    base: dict[str, Any] = {
        "id": "job-0001",
        "company_name": "Example Analytics",
        "role_title": "Software Engineering Intern",
        "job_type": JobType.INTERNSHIP,
        "location": None,
        "description": "",
        "requirements": {},
        "min_cgpa": None,
        "min_cgpa_scale": None,
        "allowed_fields": [],
        "min_degree_level": None,
        "max_backlogs": None,
        "min_grad_year": None,
        "max_grad_year": None,
        "required_skills": [],
        "apply_link": None,
        "deadline": None,
        "source": "test",
        "source_job_id": None,
        "status": JobStatusSchema.ACTIVE,
        "is_active": True,
        "last_verified_at": datetime(2026, 9, 1, tzinfo=timezone.utc),
    }
    base.update(overrides)
    return JobRead.model_validate(base)


def edu(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "degree": "B.Tech",
        "level": "BACHELORS",
        "field_of_study": "Computer Science",
        "grad_year": 2027,
        "cgpa": 8.0,
        "scale": "SCALE_10",
    }
    base.update(overrides)
    return base


def make_profile(education: list[dict[str, Any]] | None = None, **overrides: Any) -> CandidateProfile:
    data: dict[str, Any] = {
        "education": [edu()] if education is None else education,
        "backlogs": 0,
    }
    data.update(overrides)
    return CandidateProfile.model_validate(data)


def only(job: JobRead, profile: CandidateProfile) -> RequirementResult:
    """The single breakdown entry for a job stating exactly one requirement."""
    results = evaluate_requirements(profile, job)
    assert len(results) == 1, results
    return results[0]


def result(
    status: RequirementStatus,
    method: EvaluationMethod = EvaluationMethod.DETERMINISTIC,
    requirement_type: RequirementType = RequirementType.MIN_CGPA,
) -> RequirementResult:
    """A hand-built breakdown entry, for composing verdicts directly."""
    return RequirementResult(
        requirement_type=requirement_type,
        requirement="synthetic requirement",
        status=status,
        confidence=Confidence.HIGH if status is not U else Confidence.LOW,
        method=method,
        reason_code=ReasonCode.MEETS_MINIMUM,
        note="synthetic",
    )


AI = EvaluationMethod.AI_REASONING


# ---------------------------------------------------------------------------------------
# MIN_CGPA
# ---------------------------------------------------------------------------------------

CGPA_JOB = {"min_cgpa": 7.0, "min_cgpa_scale": "SCALE_10"}


@pytest.mark.parametrize(
    ("cgpa", "expected_status", "expected_reason"),
    [
        (9.0, P, ReasonCode.MEETS_MINIMUM),
        (7.0, P, ReasonCode.MEETS_MINIMUM),  # exactly at the cutoff
        (7.01, P, ReasonCode.MEETS_MINIMUM),  # one step above
        (6.99, F, ReasonCode.BELOW_MINIMUM),  # one step below
        (10.0, P, ReasonCode.MEETS_MINIMUM),  # scale maximum is valid
    ],
)
def test_cgpa_boundaries(
    cgpa: float, expected_status: RequirementStatus, expected_reason: ReasonCode
) -> None:
    r = only(make_job(**CGPA_JOB), make_profile([edu(cgpa=cgpa)]))
    assert (r.status, r.reason_code) == (expected_status, expected_reason)
    assert r.method is EvaluationMethod.DETERMINISTIC
    assert r.confidence is Confidence.HIGH


def test_cgpa_real_zero_is_evaluated_not_treated_as_missing() -> None:
    r = only(make_job(**CGPA_JOB), make_profile([edu(cgpa=0.0)]))
    assert r.status is F
    assert r.reason_code is ReasonCode.BELOW_MINIMUM
    assert r.candidate_value == "0.0 (SCALE_10)"


def test_cgpa_real_zero_passes_a_zero_minimum() -> None:
    r = only(make_job(min_cgpa=0.0, min_cgpa_scale="SCALE_10"), make_profile([edu(cgpa=0.0)]))
    assert r.status is P


def test_cgpa_missing_is_unknown_not_fail() -> None:
    r = only(make_job(**CGPA_JOB), make_profile([edu(cgpa=None)]))
    assert (r.status, r.reason_code) == (U, ReasonCode.MISSING_CANDIDATE_VALUE)
    assert r.confidence is Confidence.LOW
    assert r.candidate_value is None


def test_cgpa_missing_is_not_treated_as_zero_even_against_a_zero_minimum() -> None:
    """If a missing grade were defaulted to 0.0 this would PASS. It must stay UNKNOWN."""
    r = only(make_job(min_cgpa=0.0, min_cgpa_scale="SCALE_10"), make_profile([edu(cgpa=None)]))
    assert r.status is U


def test_cgpa_candidate_scale_unknown_is_unknown() -> None:
    r = only(make_job(**CGPA_JOB), make_profile([edu(cgpa=9.5, scale="UNKNOWN")]))
    assert (r.status, r.reason_code) == (U, ReasonCode.CANDIDATE_SCALE_UNKNOWN)


def test_cgpa_candidate_scale_null_is_unknown() -> None:
    r = only(make_job(**CGPA_JOB), make_profile([edu(cgpa=9.5, scale=None)]))
    assert (r.status, r.reason_code) == (U, ReasonCode.CANDIDATE_SCALE_UNKNOWN)


@pytest.mark.parametrize("job_scale", [None, "", "   ", "UNKNOWN"])
def test_cgpa_missing_job_scale_is_unknown(job_scale: str | None) -> None:
    r = only(make_job(min_cgpa=7.0, min_cgpa_scale=job_scale), make_profile([edu(cgpa=9.5)]))
    assert (r.status, r.reason_code) == (U, ReasonCode.JOB_SCALE_MISSING)


@pytest.mark.parametrize("job_scale", ["BOGUS", "10", "SCALE_7", "out of ten"])
def test_cgpa_invalid_job_scale_is_unknown(job_scale: str) -> None:
    r = only(make_job(min_cgpa=7.0, min_cgpa_scale=job_scale), make_profile([edu(cgpa=9.5)]))
    assert (r.status, r.reason_code) == (U, ReasonCode.JOB_SCALE_INVALID)


def test_cgpa_job_scale_is_read_case_and_whitespace_insensitively() -> None:
    r = only(make_job(min_cgpa=7.0, min_cgpa_scale=" scale_10 "), make_profile([edu(cgpa=9.0)]))
    assert r.status is P


@pytest.mark.parametrize(
    ("candidate_scale", "cgpa", "job_scale", "minimum"),
    [
        ("SCALE_4", 3.9, "SCALE_10", 3.0),  # would PASS if compared as raw numbers
        ("SCALE_4", 3.9, "SCALE_10", 7.0),  # would FAIL if compared as raw numbers
        ("SCALE_10", 8.2, "PERCENTAGE", 60.0),
        ("PERCENTAGE", 82.0, "SCALE_10", 7.0),
        ("SCALE_5", 4.0, "SCALE_4", 3.0),
    ],
)
def test_cgpa_mismatched_scales_are_unknown_never_converted(
    candidate_scale: str, cgpa: float, job_scale: str, minimum: float
) -> None:
    r = only(
        make_job(min_cgpa=minimum, min_cgpa_scale=job_scale),
        make_profile([edu(cgpa=cgpa, scale=candidate_scale)]),
    )
    assert (r.status, r.reason_code) == (U, ReasonCode.SCALE_MISMATCH)


def test_cgpa_candidate_above_scale_maximum_is_unknown() -> None:
    r = only(make_job(**CGPA_JOB), make_profile([edu(cgpa=10.5)]))
    assert (r.status, r.reason_code) == (U, ReasonCode.CANDIDATE_VALUE_EXCEEDS_SCALE)


def test_cgpa_job_minimum_above_scale_maximum_is_unknown() -> None:
    r = only(make_job(min_cgpa=11.0, min_cgpa_scale="SCALE_10"), make_profile([edu(cgpa=9.0)]))
    assert (r.status, r.reason_code) == (U, ReasonCode.JOB_VALUE_EXCEEDS_SCALE)


@pytest.mark.parametrize(
    ("cgpa", "expected"),
    [(75.0, P), (60.0, P), (59.99, F)],
)
def test_cgpa_same_scale_percentage_comparison(cgpa: float, expected: RequirementStatus) -> None:
    r = only(
        make_job(min_cgpa=60.0, min_cgpa_scale="PERCENTAGE"),
        make_profile([edu(cgpa=cgpa, scale="PERCENTAGE")]),
    )
    assert r.status is expected


def test_cgpa_same_scale_four_point_comparison() -> None:
    r = only(
        make_job(min_cgpa=3.0, min_cgpa_scale="SCALE_4"),
        make_profile([edu(cgpa=3.0, scale="SCALE_4")]),
    )
    assert r.status is P


def test_cgpa_not_stated_is_omitted() -> None:
    assert evaluate_requirements(make_profile(), make_job(min_cgpa_scale="SCALE_10")) == []


def test_cgpa_requirement_text_names_the_scale() -> None:
    r = only(make_job(**CGPA_JOB), make_profile())
    assert r.requirement == "Minimum CGPA 7.0 (SCALE_10)"
    assert r.requirement_type is RequirementType.MIN_CGPA


# ---------------------------------------------------------------------------------------
# GRAD_YEAR_WINDOW
# ---------------------------------------------------------------------------------------

WINDOW = {"min_grad_year": 2026, "max_grad_year": 2027}


@pytest.mark.parametrize(
    ("year", "expected_status", "expected_reason"),
    [
        (2026, P, ReasonCode.WITHIN_WINDOW),  # exact minimum
        (2027, P, ReasonCode.WITHIN_WINDOW),  # exact maximum
        (2025, F, ReasonCode.BEFORE_WINDOW),  # one below minimum
        (2028, F, ReasonCode.AFTER_WINDOW),  # one above maximum
        (2010, F, ReasonCode.BEFORE_WINDOW),
    ],
)
def test_grad_year_window_boundaries(
    year: int, expected_status: RequirementStatus, expected_reason: ReasonCode
) -> None:
    r = only(make_job(**WINDOW), make_profile([edu(grad_year=year)]))
    assert (r.status, r.reason_code) == (expected_status, expected_reason)
    assert r.confidence is (Confidence.HIGH)


@pytest.mark.parametrize(("year", "expected"), [(2026, P), (2030, P), (2025, F)])
def test_grad_year_min_only(year: int, expected: RequirementStatus) -> None:
    r = only(make_job(min_grad_year=2026), make_profile([edu(grad_year=year)]))
    assert r.status is expected
    assert r.requirement == "Graduation year 2026 or later"


@pytest.mark.parametrize(("year", "expected"), [(2026, P), (2020, P), (2027, F)])
def test_grad_year_max_only(year: int, expected: RequirementStatus) -> None:
    r = only(make_job(max_grad_year=2026), make_profile([edu(grad_year=year)]))
    assert r.status is expected
    assert r.requirement == "Graduation year 2026 or earlier"


@pytest.mark.parametrize(("year", "expected"), [(2026, P), (2025, F), (2027, F)])
def test_grad_year_equal_min_and_max(year: int, expected: RequirementStatus) -> None:
    r = only(make_job(min_grad_year=2026, max_grad_year=2026), make_profile([edu(grad_year=year)]))
    assert r.status is expected


def test_grad_year_missing_is_unknown() -> None:
    r = only(make_job(**WINDOW), make_profile([edu(grad_year=None)]))
    assert (r.status, r.reason_code) == (U, ReasonCode.MISSING_CANDIDATE_VALUE)
    assert r.confidence is Confidence.LOW


def test_grad_year_invalid_range_is_unknown() -> None:
    r = only(make_job(min_grad_year=2028, max_grad_year=2026), make_profile([edu(grad_year=2027)]))
    assert (r.status, r.reason_code) == (U, ReasonCode.INVALID_JOB_REQUIREMENT)


def test_grad_year_not_stated_is_omitted() -> None:
    assert evaluate_requirements(make_profile(), make_job()) == []


# ---------------------------------------------------------------------------------------
# MAX_BACKLOGS
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("backlogs", "limit", "expected_status", "expected_reason"),
    [
        (0, 0, P, ReasonCode.WITHIN_LIMIT),
        (1, 0, F, ReasonCode.EXCEEDS_LIMIT),
        (2, 2, P, ReasonCode.WITHIN_LIMIT),  # exact maximum
        (3, 2, F, ReasonCode.EXCEEDS_LIMIT),  # one above
        (1, 2, P, ReasonCode.WITHIN_LIMIT),
    ],
)
def test_backlog_boundaries(
    backlogs: int, limit: int, expected_status: RequirementStatus, expected_reason: ReasonCode
) -> None:
    r = only(make_job(max_backlogs=limit), make_profile(backlogs=backlogs))
    assert (r.status, r.reason_code) == (expected_status, expected_reason)
    assert r.candidate_value == str(backlogs)


def test_backlogs_missing_is_unknown() -> None:
    r = only(make_job(max_backlogs=2), make_profile(backlogs=None))
    assert (r.status, r.reason_code) == (U, ReasonCode.MISSING_CANDIDATE_VALUE)
    assert r.candidate_value is None


def test_backlogs_missing_is_not_treated_as_zero() -> None:
    """Against a limit of 0, a count defaulted to 0 would PASS. It must stay UNKNOWN."""
    r = only(make_job(max_backlogs=0), make_profile(backlogs=None))
    assert r.status is U
    assert r.status is not P


def test_backlogs_do_not_depend_on_education() -> None:
    r = only(make_job(max_backlogs=0), make_profile(education=[], backlogs=0))
    assert r.status is P


# ---------------------------------------------------------------------------------------
# MIN_DEGREE_LEVEL
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("candidate", "required", "expected_status", "expected_reason"),
    [
        ("BACHELORS", "BACHELORS", P, ReasonCode.MEETS_LEVEL),  # exact
        ("MASTERS", "BACHELORS", P, ReasonCode.MEETS_LEVEL),  # higher
        ("DOCTORATE", "MASTERS", P, ReasonCode.MEETS_LEVEL),
        ("DIPLOMA", "BACHELORS", F, ReasonCode.BELOW_LEVEL),  # lower
        ("HIGH_SCHOOL", "DIPLOMA", F, ReasonCode.BELOW_LEVEL),
        ("BACHELORS", "MASTERS", F, ReasonCode.BELOW_LEVEL),
        ("HIGH_SCHOOL", "HIGH_SCHOOL", P, ReasonCode.MEETS_LEVEL),
    ],
)
def test_degree_level_ordering(
    candidate: str, required: str, expected_status: RequirementStatus, expected_reason: ReasonCode
) -> None:
    r = only(
        make_job(min_degree_level=DegreeLevel(required)), make_profile([edu(level=candidate)])
    )
    assert (r.status, r.reason_code) == (expected_status, expected_reason)
    assert r.confidence is Confidence.HIGH


@pytest.mark.parametrize("candidate", ["UNKNOWN", "OTHER"])
def test_degree_candidate_level_unorderable_is_unknown(candidate: str) -> None:
    r = only(make_job(min_degree_level=DegreeLevel.BACHELORS), make_profile([edu(level=candidate)]))
    assert (r.status, r.reason_code) == (U, ReasonCode.CANDIDATE_LEVEL_UNKNOWN)


def test_degree_candidate_level_omitted_defaults_to_unknown_not_a_guess() -> None:
    entry = edu()
    del entry["level"]  # "B.Tech" must not be read as BACHELORS
    r = only(make_job(min_degree_level=DegreeLevel.BACHELORS), make_profile([entry]))
    assert r.status is U
    assert r.candidate_value is None


@pytest.mark.parametrize("required", [DegreeLevel.UNKNOWN, DegreeLevel.OTHER])
def test_degree_invalid_job_requirement_is_unknown(required: DegreeLevel) -> None:
    r = only(make_job(min_degree_level=required), make_profile([edu(level="DOCTORATE")]))
    assert (r.status, r.reason_code) == (U, ReasonCode.INVALID_JOB_REQUIREMENT)


def test_degree_not_stated_is_omitted() -> None:
    assert evaluate_requirements(make_profile(), make_job(min_degree_level=None)) == []


# ---------------------------------------------------------------------------------------
# ALLOWED_FIELDS
# ---------------------------------------------------------------------------------------

FIELDS = {"allowed_fields": ["Computer Science", "Information Technology"]}


@pytest.mark.parametrize(
    "field",
    [
        "Computer Science",
        "computer science",  # case
        "COMPUTER SCIENCE",
        "  Computer   Science ",  # whitespace
        "information\ttechnology",
    ],
)
def test_fields_exact_normalized_match_passes(field: str) -> None:
    r = only(make_job(**FIELDS), make_profile([edu(field_of_study=field)]))
    assert (r.status, r.reason_code) == (P, ReasonCode.EXACT_FIELD_MATCH)
    assert r.method is EvaluationMethod.DETERMINISTIC
    assert r.confidence is Confidence.HIGH


@pytest.mark.parametrize(
    "field",
    [
        "Computer Science and Engineering",  # related, but not exact
        "Computer Sci.",
        "CSE",
        "Mechanical Engineering",  # plainly different — still not a deterministic FAIL
    ],
)
def test_fields_non_exact_match_is_unknown_never_fail(field: str) -> None:
    r = only(make_job(**FIELDS), make_profile([edu(field_of_study=field)]))
    assert (r.status, r.reason_code) == (U, ReasonCode.FIELD_NOT_EXACT_MATCH)
    assert r.status is not F


def test_fields_missing_is_unknown() -> None:
    r = only(make_job(**FIELDS), make_profile([edu(field_of_study=None)]))
    assert (r.status, r.reason_code) == (U, ReasonCode.MISSING_CANDIDATE_VALUE)


def test_fields_empty_list_is_omitted() -> None:
    assert evaluate_requirements(make_profile(), make_job(allowed_fields=[])) == []


def test_fields_list_of_blank_strings_is_omitted() -> None:
    assert evaluate_requirements(make_profile(), make_job(allowed_fields=["", "  "])) == []


def test_fields_rule_can_never_produce_fail() -> None:
    """A-2: deterministic code has no ontology, so no input may yield a field FAIL."""
    fields = ["Computer Science", "Mechanical", "   ", None, "zzz", "Computer Science and Eng"]
    for field in fields:
        r = only(make_job(**FIELDS), make_profile([edu(field_of_study=field)]))
        assert r.status is not F


# ---------------------------------------------------------------------------------------
# Qualification selection (A-1)
# ---------------------------------------------------------------------------------------


def test_single_entry_is_selected_whatever_its_level() -> None:
    entries = make_profile([edu(level="UNKNOWN")]).education
    assert select_qualification(entries).entry is entries[0]


def test_bachelors_is_selected_over_school_record() -> None:
    profile = make_profile(
        [
            edu(degree="School", level="HIGH_SCHOOL", cgpa=95.0, scale="PERCENTAGE", grad_year=2023),
            edu(degree="B.Tech", level="BACHELORS", cgpa=8.0, grad_year=2027),
        ]
    )
    selection = select_qualification(profile.education)
    assert selection.entry is profile.education[1]
    r = only(make_job(**CGPA_JOB), profile)
    assert r.status is P
    assert r.candidate_value == "8.0 (SCALE_10)"


def test_highest_known_level_selected_even_beside_an_unknown_level() -> None:
    profile = make_profile([edu(level="UNKNOWN"), edu(level="MASTERS", cgpa=9.1)])
    assert select_qualification(profile.education).entry is profile.education[1]


def test_two_entries_at_same_highest_level_are_unknown() -> None:
    profile = make_profile([edu(level="BACHELORS"), edu(level="BACHELORS", cgpa=6.0)])
    assert select_qualification(profile.education).reason is ReasonCode.QUALIFICATION_NOT_DETERMINABLE
    r = only(make_job(**CGPA_JOB), profile)
    assert (r.status, r.reason_code) == (U, ReasonCode.QUALIFICATION_NOT_DETERMINABLE)


@pytest.mark.parametrize("levels", [("UNKNOWN", "UNKNOWN"), ("OTHER", "UNKNOWN"), ("OTHER", "OTHER")])
def test_multiple_entries_with_no_orderable_level_are_unknown(levels: tuple[str, str]) -> None:
    profile = make_profile([edu(level=levels[0]), edu(level=levels[1])])
    assert select_qualification(profile.education).entry is None
    r = only(make_job(**WINDOW), profile)
    assert (r.status, r.reason_code) == (U, ReasonCode.QUALIFICATION_NOT_DETERMINABLE)


def test_no_education_makes_every_per_qualification_requirement_unknown() -> None:
    job = make_job(
        **CGPA_JOB, **WINDOW, **FIELDS, min_degree_level=DegreeLevel.BACHELORS, max_backlogs=0
    )
    results = evaluate_requirements(make_profile(education=[], backlogs=0), job)
    by_type = {r.requirement_type: r for r in results}
    for kind in (
        RequirementType.MIN_CGPA,
        RequirementType.GRAD_YEAR_WINDOW,
        RequirementType.MIN_DEGREE_LEVEL,
        RequirementType.ALLOWED_FIELDS,
    ):
        assert (by_type[kind].status, by_type[kind].reason_code) == (U, ReasonCode.NO_QUALIFICATION)
    assert by_type[RequirementType.MAX_BACKLOGS].status is P


def test_records_are_never_combined_grade_from_another_entry() -> None:
    """The selected BACHELORS entry has no grade. The school record's grade must not fill it."""
    profile = make_profile(
        [
            edu(level="BACHELORS", cgpa=None, grad_year=2027),
            edu(level="HIGH_SCHOOL", cgpa=9.5, scale="SCALE_10", grad_year=2023),
        ]
    )
    r = only(make_job(**CGPA_JOB), profile)
    assert (r.status, r.reason_code) == (U, ReasonCode.MISSING_CANDIDATE_VALUE)


def test_records_are_never_combined_year_and_field_from_another_entry() -> None:
    profile = make_profile(
        [
            edu(level="MASTERS", grad_year=None, field_of_study=None),
            edu(level="BACHELORS", grad_year=2026, field_of_study="Computer Science"),
        ]
    )
    results = evaluate_requirements(profile, make_job(**WINDOW, **FIELDS))
    assert [r.status for r in results] == [U, U]


def test_all_per_qualification_rules_read_the_same_entry() -> None:
    profile = make_profile(
        [
            edu(level="HIGH_SCHOOL", cgpa=6.0, grad_year=2020, field_of_study="Science"),
            edu(level="MASTERS", cgpa=9.0, grad_year=2027, field_of_study="Computer Science"),
        ]
    )
    job = make_job(**CGPA_JOB, **WINDOW, **FIELDS, min_degree_level=DegreeLevel.MASTERS)
    values = [r.candidate_value for r in evaluate_requirements(profile, job)]
    assert values == ["9.0 (SCALE_10)", "2027", "MASTERS", "Computer Science"]


# ---------------------------------------------------------------------------------------
# Hard-failure guard (C-13, INV-2)
# ---------------------------------------------------------------------------------------


def test_all_deterministic_checks_run_after_a_failure() -> None:
    job = make_job(**CGPA_JOB, **WINDOW, max_backlogs=0)
    profile = make_profile([edu(cgpa=6.0, grad_year=2030)], backlogs=4)
    results = evaluate_requirements(profile, job)
    assert [r.status for r in results] == [F, F, F]
    verdict = evaluate_job(profile, job)
    assert verdict.eligibility_state is EligibilityState.NOT_ELIGIBLE
    assert "3 of 3" in verdict.summary


def test_ambiguous_field_is_offered_to_ai_stage_when_no_hard_failure() -> None:
    job = make_job(**CGPA_JOB, **FIELDS)
    profile = make_profile([edu(cgpa=9.0, field_of_study="Computer Science and Engineering")])
    results = evaluate_requirements(profile, job)
    assert ambiguous_requirements(results) == [1]
    assert results[1].reason_code is ReasonCode.FIELD_NOT_EXACT_MATCH


def test_hard_failure_blocks_the_ai_stage_structurally() -> None:
    job = make_job(**CGPA_JOB, **FIELDS)
    profile = make_profile([edu(cgpa=6.0, field_of_study="Computer Science and Engineering")])
    results = evaluate_requirements(profile, job)

    assert ambiguous_requirements(results) == []
    field = results[1]
    assert (field.status, field.reason_code) == (U, ReasonCode.SKIPPED_AFTER_HARD_FAILURE)
    assert field.method is EvaluationMethod.DETERMINISTIC


def test_guard_holds_even_on_an_unskipped_breakdown() -> None:
    """ambiguous_requirements itself refuses, independent of the skip marking."""
    fail = result(F)
    ambiguous = result(U, requirement_type=RequirementType.ALLOWED_FIELDS).model_copy(
        update={"reason_code": ReasonCode.FIELD_NOT_EXACT_MATCH}
    )
    assert ambiguous_requirements([fail, ambiguous]) == []
    assert ambiguous_requirements([result(P), ambiguous]) == [1]


def test_missing_data_is_never_offered_to_the_ai_stage() -> None:
    job = make_job(**CGPA_JOB, **FIELDS, max_backlogs=0)
    profile = make_profile([edu(cgpa=None, field_of_study=None)], backlogs=None)
    assert ambiguous_requirements(evaluate_requirements(profile, job)) == []


def test_ai_fail_is_not_a_verified_hard_failure() -> None:
    assert engine.has_verified_hard_failure([result(F, AI)]) is False
    assert engine.has_verified_hard_failure([result(F)]) is True


# ---------------------------------------------------------------------------------------
# Verdict precedence (ADR-017) — every combination
# ---------------------------------------------------------------------------------------

E = EligibilityState


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ([], E.ELIGIBLE),  # zero structured requirements
        ([result(P)], E.ELIGIBLE),
        ([result(P), result(P)], E.ELIGIBLE),
        ([result(P), result(U)], E.NEEDS_REVIEW),
        ([result(F), result(P)], E.NOT_ELIGIBLE),
        ([result(F), result(U)], E.NOT_ELIGIBLE),
        ([result(F), result(F)], E.NOT_ELIGIBLE),
        ([result(F)], E.NOT_ELIGIBLE),
        ([result(U)], E.UNKNOWN),
        ([result(U), result(U)], E.UNKNOWN),
        ([result(U), result(U), result(F)], E.NOT_ELIGIBLE),
        # AI-reasoned entries (composition must already be correct for PR 4B)
        ([result(P), result(P, AI)], E.LIKELY_ELIGIBLE),
        ([result(P, AI)], E.LIKELY_ELIGIBLE),
        ([result(F, AI)], E.NEEDS_REVIEW),  # AI FAIL alone is never NOT_ELIGIBLE
        ([result(P), result(F, AI)], E.NEEDS_REVIEW),
        ([result(U), result(F, AI)], E.NEEDS_REVIEW),
        ([result(P, AI), result(U)], E.NEEDS_REVIEW),
        ([result(P, AI), result(F, AI)], E.NEEDS_REVIEW),
        ([result(F), result(P, AI)], E.NOT_ELIGIBLE),
        ([result(F), result(F, AI)], E.NOT_ELIGIBLE),
    ],
)
def test_verdict_precedence(statuses: list[RequirementResult], expected: EligibilityState) -> None:
    assert compose_verdict(statuses) is expected


def test_verdict_uses_exactly_five_states() -> None:
    assert {state.value for state in EligibilityState} == {
        "ELIGIBLE",
        "LIKELY_ELIGIBLE",
        "NEEDS_REVIEW",
        "UNKNOWN",
        "NOT_ELIGIBLE",
    }


@pytest.mark.parametrize(
    ("education", "backlogs", "expected"),
    [
        ([edu(cgpa=9.0, grad_year=2027)], 0, E.ELIGIBLE),  # PASS + PASS + PASS
        ([edu(cgpa=9.0, grad_year=2027)], None, E.NEEDS_REVIEW),  # PASS + PASS + UNKNOWN
        ([edu(cgpa=6.0, grad_year=2027)], 0, E.NOT_ELIGIBLE),  # FAIL + PASS + PASS
        ([edu(cgpa=6.0, grad_year=2027)], None, E.NOT_ELIGIBLE),  # FAIL + PASS + UNKNOWN
        ([edu(cgpa=6.0, grad_year=2031)], 3, E.NOT_ELIGIBLE),  # FAIL + FAIL + FAIL
        ([edu(cgpa=None, grad_year=None)], None, E.UNKNOWN),  # all UNKNOWN
    ],
)
def test_end_to_end_verdicts(
    education: list[dict[str, Any]], backlogs: int | None, expected: EligibilityState
) -> None:
    job = make_job(**CGPA_JOB, **WINDOW, max_backlogs=0)
    verdict = evaluate_job(make_profile(education, backlogs=backlogs), job)
    assert verdict.eligibility_state is expected


# ---------------------------------------------------------------------------------------
# Explanations and confidence (INV-8, ADR-003)
# ---------------------------------------------------------------------------------------

EVERYTHING = {**CGPA_JOB, **WINDOW, **FIELDS, "min_degree_level": DegreeLevel.BACHELORS, "max_backlogs": 0}


@pytest.mark.parametrize(
    "profile",
    [
        make_profile(),
        make_profile([edu(cgpa=None, grad_year=None, field_of_study="CSE", level="UNKNOWN")], backlogs=None),
        make_profile([edu(cgpa=1.0, grad_year=2001, level="DIPLOMA")], backlogs=9),
        make_profile(education=[]),
    ],
)
def test_every_entry_is_explained(profile: CandidateProfile) -> None:
    verdict = evaluate_job(profile, make_job(**EVERYTHING))
    assert verdict.summary
    assert len(verdict.requirement_breakdown) == 5
    for entry in verdict.requirement_breakdown:
        assert entry.note.strip()
        assert isinstance(entry.reason_code, ReasonCode)
        assert entry.requirement.strip()
        assert entry.method is EvaluationMethod.DETERMINISTIC
        expected_confidence = Confidence.LOW if entry.status is U else Confidence.HIGH
        assert entry.confidence is expected_confidence


def test_deterministic_hard_failure_reports_high_confidence() -> None:
    verdict = evaluate_job(make_profile([edu(cgpa=6.0)]), make_job(**CGPA_JOB))
    assert verdict.eligibility_state is E.NOT_ELIGIBLE
    assert verdict.requirement_breakdown[0].confidence is Confidence.HIGH


def test_no_top_level_confidence_or_match_score_in_contract() -> None:
    for model in (JobEligibility,):
        fields = set(model.model_fields)
        assert "confidence" not in fields
        assert not {name for name in fields if "score" in name or "match" in name}


def test_summary_contains_no_candidate_values() -> None:
    profile = make_profile(
        [edu(cgpa=8.37, grad_year=2026, field_of_study="Xylography Studies", level="MASTERS")],
        backlogs=1,
    )
    job = make_job(
        min_cgpa=7.0, min_cgpa_scale="SCALE_10", min_grad_year=2025, max_grad_year=2027,
        allowed_fields=["Xylography Studies"], max_backlogs=3,
        min_degree_level=DegreeLevel.BACHELORS,
    )
    verdict = evaluate_job(profile, job)
    assert verdict.eligibility_state is E.ELIGIBLE
    for marker in ("8.37", "Xylography", "MASTERS"):
        assert marker not in verdict.summary
    assert any(e.candidate_value == "8.37 (SCALE_10)" for e in verdict.requirement_breakdown)


def test_zero_requirements_summary_says_so() -> None:
    verdict = evaluate_job(make_profile(), make_job())
    assert verdict.eligibility_state is E.ELIGIBLE
    assert verdict.requirement_breakdown == []
    assert "no structured eligibility requirements" in verdict.summary
    assert "not evaluated" not in verdict.summary


def test_zero_requirements_with_notes_discloses_they_were_not_evaluated() -> None:
    verdict = evaluate_job(
        make_profile(), make_job(requirements={"notes": "Open to final year students."})
    )
    assert verdict.eligibility_state is E.ELIGIBLE
    assert "no structured eligibility requirements" in verdict.summary
    assert "notes, which were not evaluated" in verdict.summary


def test_notes_disclosed_alongside_structured_requirements_too() -> None:
    verdict = evaluate_job(
        make_profile(), make_job(**CGPA_JOB, requirements={"notes": "No active backlogs."})
    )
    assert "not evaluated" in verdict.summary


@pytest.mark.parametrize("requirements", [{}, {"notes": ""}, {"notes": "   "}, {"notes": None}])
def test_empty_notes_are_not_disclosed(requirements: dict[str, Any]) -> None:
    verdict = evaluate_job(make_profile(), make_job(requirements=requirements))
    assert "not evaluated" not in verdict.summary


@pytest.mark.parametrize(
    ("profile", "state", "phrase"),
    [
        (make_profile([edu(cgpa=6.0)]), E.NOT_ELIGIBLE, "Not eligible"),
        (make_profile([edu(cgpa=None)]), E.UNKNOWN, "Unknown"),
        (make_profile([edu(field_of_study="CSE")]), E.NEEDS_REVIEW, "Needs review"),
        (make_profile(), E.ELIGIBLE, "Eligible"),
    ],
)
def test_summary_states_the_verdict(profile: CandidateProfile, state: EligibilityState, phrase: str) -> None:
    job = make_job(**CGPA_JOB, **FIELDS) if state is E.NEEDS_REVIEW else make_job(**CGPA_JOB)
    verdict = evaluate_job(profile, job)
    assert verdict.eligibility_state is state
    assert verdict.summary.startswith(phrase)


def test_job_status_is_informational_and_does_not_change_the_verdict() -> None:
    for status in JobStatusSchema:
        verdict = evaluate_job(make_profile(), make_job(**CGPA_JOB, status=status, is_active=False))
        assert verdict.eligibility_state is E.ELIGIBLE
        assert verdict.job_status is status


# ---------------------------------------------------------------------------------------
# Determinism and purity
# ---------------------------------------------------------------------------------------


def test_evaluation_is_deterministic() -> None:
    profile = make_profile([edu(field_of_study="CSE")], backlogs=None)
    job = make_job(**EVERYTHING)
    assert evaluate_job(profile, job) == evaluate_job(profile, job)


def test_evaluation_does_not_mutate_inputs() -> None:
    profile = make_profile([edu(field_of_study="CSE")])
    job = make_job(**EVERYTHING)
    before = (profile.model_dump(), job.model_dump())
    evaluate_job(profile, job)
    assert (profile.model_dump(), job.model_dump()) == before


def test_engine_imports_no_framework_database_or_ai_code() -> None:
    """INV-7 and INV-5: the engine is callable from a script with no server."""
    import ast

    source = Path(engine.__file__).read_text(encoding="utf-8")
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    forbidden_prefixes = ("fastapi", "starlette", "sqlalchemy", "app.ai", "app.models", "app.database", "httpx")
    assert not [name for name in imported if name.startswith(forbidden_prefixes)]


# ---------------------------------------------------------------------------------------
# Golden cases against the curated dataset
# ---------------------------------------------------------------------------------------


def _curated_jobs() -> dict[str, JobRead]:
    path = Path(engine.__file__).resolve().parent.parent / "data" / "curated_jobs.json"
    jobs: dict[str, JobRead] = {}
    for entry in json.loads(path.read_text(encoding="utf-8")):
        jobs[entry["source_job_id"]] = make_job(
            **{k: v for k, v in entry.items() if k != "source_job_id"},
            id=entry["source_job_id"],
            source_job_id=entry["source_job_id"],
        )
    return jobs


def test_curated_dataset_golden_verdicts() -> None:
    jobs = _curated_jobs()
    profile = make_profile(
        [edu(level="BACHELORS", field_of_study="Information Technology", grad_year=2026, cgpa=7.2)],
        backlogs=1,
    )
    states = {sid: evaluate_job(profile, job).eligibility_state for sid, job in jobs.items()}
    assert states == {
        "EX-INT-001": E.NOT_ELIGIBLE,  # backlogs 1 > 0
        "EX-FT-002": E.ELIGIBLE,  # every requirement, including BACHELORS, met
        "EX-INT-003": E.NEEDS_REVIEW,  # min_cgpa has no stated scale; field not exact
        "EX-FT-004": E.NOT_ELIGIBLE,  # CGPA 7.2 < 7.5 and backlogs 1 > 0
        "EX-INT-005": E.NOT_ELIGIBLE,  # graduation 2026 before the 2027 window
    }


def test_curated_degree_requirement_fails_a_diploma_holder() -> None:
    job = _curated_jobs()["EX-FT-002"]
    assert job.min_degree_level is DegreeLevel.BACHELORS
    profile = make_profile(
        [edu(level="DIPLOMA", field_of_study="Computer Science", grad_year=2025, cgpa=8.0)],
        backlogs=0,
    )
    verdict = evaluate_job(profile, job)
    assert verdict.eligibility_state is E.NOT_ELIGIBLE
    degree = [e for e in verdict.requirement_breakdown if e.requirement_type is RequirementType.MIN_DEGREE_LEVEL]
    assert degree[0].reason_code is ReasonCode.BELOW_LEVEL
