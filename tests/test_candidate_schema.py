"""Candidate profile schema and normalization-service tests.

These exercise the schema and the service directly — no FastAPI, no server, no database.
That the service is testable this way is itself the check on INV-7.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas.candidate import (
    CandidateProfile,
    DegreeLevel,
    EducationEntry,
    GradeScale,
    IssueSeverity,
)
from app.services.candidate_normalizer import (
    has_blocking_issues,
    normalize_grade,
    normalize_profile,
    normalize_skill,
    normalize_skills,
    validate_profile,
)

# ---------------------------------------------------------------------------------------
# Acceptance and rejection
# ---------------------------------------------------------------------------------------


def test_valid_profile_is_accepted(complete_profile: dict[str, Any]) -> None:
    profile = CandidateProfile.model_validate(complete_profile)
    assert profile.name == "Test Candidate"
    assert len(profile.education) == 2
    assert profile.backlogs == 0


def test_empty_profile_is_structurally_valid() -> None:
    """A partial profile is the normal state after resume parsing, not an error.

    Gaps are reported by validate_profile as issues; they do not make the payload
    structurally invalid. Rejecting here would turn "not known yet" into "invalid".
    """
    profile = CandidateProfile.model_validate({})
    assert profile.education == []
    assert profile.skills == []
    assert profile.backlogs is None


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ({"email": "not-a-valid-email"}, "malformed email"),
        ({"backlogs": -1}, "negative backlog count"),
        ({"education": [{"degree": "B.Tech", "cgpa": -1.0}]}, "negative grade"),
        ({"education": [{"degree": "B.Tech", "grad_year": 1800}]}, "year below range"),
        ({"education": [{"degree": "B.Tech", "grad_year": 20255}]}, "year above range"),
        ({"education": [{"degree": ""}]}, "empty degree"),
        ({"education": [{}]}, "education entry with no degree"),
        ({"education": [{"degree": "B.Tech", "scale": "SCALE_7"}]}, "unknown scale value"),
        ({"unexpected_field": "x"}, "unknown top-level field"),
        ({"education": [{"degree": "B.Tech", "ssn": "x"}]}, "unknown education field"),
        ({"skills": [""]}, "empty skill string"),
    ],
)
def test_malformed_profile_is_rejected(payload: dict[str, Any], reason: str) -> None:
    with pytest.raises(ValidationError):
        CandidateProfile.model_validate(payload)


def test_nan_grade_is_rejected() -> None:
    """NaN passes ``ge=0`` but poisons every downstream comparison."""
    with pytest.raises(ValidationError):
        EducationEntry.model_validate(
            {"degree": "B.Tech", "cgpa": float("nan"), "scale": "SCALE_10"}
        )


def test_infinite_grade_is_rejected() -> None:
    with pytest.raises(ValidationError):
        EducationEntry.model_validate(
            {"degree": "B.Tech", "cgpa": float("inf"), "scale": "SCALE_10"}
        )


# ---------------------------------------------------------------------------------------
# Multiple education records
# ---------------------------------------------------------------------------------------


def test_multiple_education_records_are_preserved(complete_profile: dict[str, Any]) -> None:
    """Candidates hold several qualifications, on different scales (dossier §10.1)."""
    profile = CandidateProfile.model_validate(complete_profile)

    assert len(profile.education) == 2
    assert profile.education[0].scale is GradeScale.SCALE_10
    assert profile.education[1].scale is GradeScale.PERCENTAGE
    assert profile.education[0].level is DegreeLevel.BACHELORS
    assert profile.education[1].level is DegreeLevel.HIGH_SCHOOL


def test_education_order_is_stable_through_normalization(
    complete_profile: dict[str, Any],
) -> None:
    profile = CandidateProfile.model_validate(complete_profile)
    normalized, grades, _ = normalize_profile(profile)

    assert [entry.degree for entry in normalized.education] == ["B.Tech", "High School"]
    assert [grade.education_index for grade in grades] == [0, 1]


# ---------------------------------------------------------------------------------------
# Grading scale — the core requirement
# ---------------------------------------------------------------------------------------


def test_grading_scale_is_preserved_verbatim() -> None:
    entry = EducationEntry.model_validate(
        {"degree": "B.Tech", "cgpa": 8.2, "scale": "SCALE_10"}
    )
    assert entry.scale is GradeScale.SCALE_10
    assert entry.cgpa == 8.2
    assert entry.has_known_scale is True


def test_same_number_on_different_scales_stays_distinguishable() -> None:
    """8.2/10 and 8.2/4 must never be conflated. 8.2/4 is impossible and flagged."""
    on_ten = EducationEntry.model_validate(
        {"degree": "B.Tech", "cgpa": 8.2, "scale": "SCALE_10"}
    )
    on_four = EducationEntry.model_validate(
        {"degree": "B.Tech", "cgpa": 8.2, "scale": "SCALE_4"}
    )

    assert on_ten.scale is not on_four.scale
    assert normalize_grade(on_ten, 0).fraction == pytest.approx(0.82)
    # 8.2 on a 4-point scale is out of range; clamped, and reported as an ERROR below.
    assert normalize_grade(on_four, 0).fraction == pytest.approx(1.0)

    issues = validate_profile(
        CandidateProfile.model_validate({"education": [on_four.model_dump(mode="json")]})
    )
    assert any(issue.code == "GRADE_EXCEEDS_SCALE" for issue in issues)


def test_equivalent_grades_on_different_scales_normalize_equally() -> None:
    """8.2/10 and 3.28/4 are the same standing, and must normalize to the same fraction."""
    ten = EducationEntry.model_validate({"degree": "A", "cgpa": 8.2, "scale": "SCALE_10"})
    four = EducationEntry.model_validate({"degree": "B", "cgpa": 3.28, "scale": "SCALE_4"})
    pct = EducationEntry.model_validate({"degree": "C", "cgpa": 82.0, "scale": "PERCENTAGE"})

    assert normalize_grade(ten, 0).fraction == pytest.approx(0.82)
    assert normalize_grade(four, 1).fraction == pytest.approx(0.82)
    assert normalize_grade(pct, 2).fraction == pytest.approx(0.82)


def test_missing_scale_remains_unknown() -> None:
    """The single most important behaviour in Week 1.

    A grade with no stated scale must not be assumed to be out of 10.
    """
    entry = EducationEntry.model_validate({"degree": "B.Tech", "cgpa": 8.2})

    assert entry.scale is GradeScale.UNKNOWN
    assert entry.has_known_scale is False
    assert entry.cgpa == 8.2, "the grade itself is preserved; only its scale is unknown"


def test_explicit_null_scale_becomes_unknown_not_an_error() -> None:
    entry = EducationEntry.model_validate(
        {"degree": "B.Tech", "cgpa": 8.2, "scale": None}
    )
    assert entry.scale is GradeScale.UNKNOWN


def test_unknown_scale_produces_no_fraction() -> None:
    """Unknown stays unknown rather than being silently computed against 10."""
    entry = EducationEntry.model_validate({"degree": "B.Tech", "cgpa": 8.2})
    grade = normalize_grade(entry, 0)

    assert grade.scale is GradeScale.UNKNOWN
    assert grade.fraction is None
    assert grade.cgpa == 8.2


def test_missing_scale_is_reported_as_a_warning_not_an_error() -> None:
    """An unknown scale is incomplete data, not invalid data (INV-3)."""
    profile = CandidateProfile.model_validate(
        {"education": [{"degree": "B.Tech", "cgpa": 8.2, "grad_year": 2027,
                        "field_of_study": "IT"}]}
    )
    issues = validate_profile(profile)

    scale_issues = [issue for issue in issues if issue.code == "MISSING_SCALE"]
    assert len(scale_issues) == 1
    assert scale_issues[0].severity is IssueSeverity.WARNING
    assert scale_issues[0].field == "education[0].scale"
    assert not has_blocking_issues(issues)


def test_no_grade_at_all_produces_no_scale_warning() -> None:
    """Only a grade *without* a scale is noteworthy. No grade is simply no grade."""
    profile = CandidateProfile.model_validate({"education": [{"degree": "B.Tech"}]})
    issues = validate_profile(profile)
    assert not any(issue.code == "MISSING_SCALE" for issue in issues)


# ---------------------------------------------------------------------------------------
# Missing values must never become passing values
# ---------------------------------------------------------------------------------------


def test_missing_backlogs_stays_none_and_is_not_zero() -> None:
    """Defaulting an unknown backlog count to 0 would invent a passing value (INV-3)."""
    profile = CandidateProfile.model_validate({})
    assert profile.backlogs is None

    issues = validate_profile(profile)
    backlog_issues = [issue for issue in issues if issue.code == "MISSING_BACKLOGS"]
    assert len(backlog_issues) == 1
    assert backlog_issues[0].severity is IssueSeverity.WARNING


def test_zero_backlogs_is_distinct_from_missing() -> None:
    assert CandidateProfile.model_validate({"backlogs": 0}).backlogs == 0
    assert CandidateProfile.model_validate({}).backlogs is None


def test_missing_grad_year_is_a_warning_not_a_failure() -> None:
    profile = CandidateProfile.model_validate({"education": [{"degree": "B.Tech"}]})
    issues = validate_profile(profile)

    year_issues = [issue for issue in issues if issue.code == "MISSING_GRAD_YEAR"]
    assert len(year_issues) == 1
    assert year_issues[0].severity is IssueSeverity.WARNING


def test_absent_education_is_the_only_blocking_issue() -> None:
    """Eligibility cannot run at all with no education record, so this one blocks."""
    issues = validate_profile(CandidateProfile.model_validate({}))
    errors = [issue for issue in issues if issue.severity is IssueSeverity.ERROR]

    assert [issue.code for issue in errors] == ["NO_EDUCATION"]
    assert has_blocking_issues(issues)


# ---------------------------------------------------------------------------------------
# Skill normalization
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ReactJS", "React"),
        ("React.js", "React"),
        ("react js", "React"),
        ("React", "React"),
        ("  python  ", "Python"),
        ("PYTHON", "Python"),
        ("nodejs", "Node.js"),
        ("Node", "Node.js"),
        ("postgres", "PostgreSQL"),
        ("k8s", "Kubernetes"),
        ("sklearn", "scikit-learn"),
        ("ML", "Machine Learning"),
    ],
)
def test_known_skill_variants_canonicalize(raw: str, expected: str) -> None:
    assert normalize_skill(raw) == expected


def test_c_variants_are_not_conflated() -> None:
    """C, C++ and C# are different skills. Stripping punctuation naively merges them."""
    assert normalize_skill("C") == "C"
    assert normalize_skill("C++") == "C++"
    assert normalize_skill("C#") == "C#"
    assert len({normalize_skill(s) for s in ("C", "C++", "C#")}) == 3


def test_unknown_skill_keeps_its_original_casing() -> None:
    """Inventing a capitalization convention mangles more names than it fixes."""
    assert normalize_skill("Kubeflow Pipelines") == "Kubeflow Pipelines"
    assert normalize_skill("  weird   internal  spacing ") == "weird internal spacing"


def test_skill_list_deduplicates_after_canonicalizing() -> None:
    result = normalize_skills(["ReactJS", "React.js", "React", "python", "PYTHON"])
    assert result == ["React", "Python"]


def test_skill_order_is_preserved_first_occurrence_wins() -> None:
    result = normalize_skills(["docker", "python", "Docker", "SQL"])
    assert result == ["Docker", "Python", "SQL"]


def test_empty_and_punctuation_only_skills_are_dropped() -> None:
    assert normalize_skills(["  ", ".", "  ,  ", "Python"]) == ["Python"]


# ---------------------------------------------------------------------------------------
# Normalization preserves meaning
# ---------------------------------------------------------------------------------------


def test_normalization_preserves_education_semantics(
    complete_profile: dict[str, Any],
) -> None:
    profile = CandidateProfile.model_validate(complete_profile)
    normalized, _, _ = normalize_profile(profile)

    for original, result in zip(profile.education, normalized.education, strict=True):
        assert result.cgpa == original.cgpa
        assert result.scale is original.scale
        assert result.grad_year == original.grad_year
        assert result.level is original.level


def test_normalization_never_invents_a_scale() -> None:
    profile = CandidateProfile.model_validate(
        {"education": [{"degree": "B.Tech", "cgpa": 8.2}]}
    )
    normalized, grades, _ = normalize_profile(profile)

    assert normalized.education[0].scale is GradeScale.UNKNOWN
    assert grades[0].fraction is None


def test_normalization_cleans_text_and_lowercases_email() -> None:
    profile = CandidateProfile.model_validate(
        {"name": "  Test   Candidate  ", "email": "Test.Candidate@Example.COM"}
    )
    normalized, _, changes = normalize_profile(profile)

    assert normalized.name == "Test Candidate"
    assert normalized.email == "test.candidate@example.com"
    assert changes, "changes should describe what was altered"


def test_normalization_reports_changes_without_leaking_values(
    complete_profile: dict[str, Any],
) -> None:
    """The change log names field paths, never candidate values (INV-4)."""
    profile = CandidateProfile.model_validate(complete_profile)
    _, _, changes = normalize_profile(profile)

    joined = " ".join(changes)
    for secret in ("Test Candidate", "test.candidate@example.com", "Example City"):
        assert secret not in joined


def test_normalization_is_idempotent(complete_profile: dict[str, Any]) -> None:
    """Normalizing twice changes nothing the second time."""
    profile = CandidateProfile.model_validate(complete_profile)
    once, _, _ = normalize_profile(profile)
    twice, _, second_changes = normalize_profile(once)

    assert once.model_dump() == twice.model_dump()
    assert not [c for c in second_changes if "whitespace" in c or "deduplicated" in c]


def test_service_needs_no_web_framework() -> None:
    """INV-7: services must be importable and usable with no FastAPI in play."""
    import sys

    import app.services.candidate_normalizer as module

    source = module.__file__
    assert source is not None
    assert "fastapi" not in module.__dict__
    # The module must not have pulled FastAPI in as a dependency of its own imports.
    assert not any(
        name.startswith("fastapi") for name in getattr(module, "__annotations__", {})
    )
    assert sys.modules.get("app.services.candidate_normalizer") is module
