"""The amended D4 verdict precedence (ADR-030 D4, D4a; ADR-017 provenance amendment).

```
1. Zero structured requirements                                  -> ELIGIBLE
2. Any SOURCE_STATED deterministic FAIL                          -> NOT_ELIGIBLE   (narrowed)
3. Every requirement UNKNOWN                                     -> UNKNOWN
4. Any UNKNOWN, any AI-reasoned FAIL, or any PROSE_DERIVED FAIL  -> NEEDS_REVIEW   (widened)
5. All PASS, at least one by AI reasoning or PROSE_DERIVED       -> LIKELY_ELIGIBLE (widened)
6. All PASS, all deterministic and SOURCE_STATED                 -> ELIGIBLE       (narrowed)
```

**Every test here builds `RequirementResult`s directly.** Nothing in the engine can yet
produce a `PROSE_DERIVED` entry — supplying derived requirements to evaluation is the
engine-boundary decision and its own PR — so constructing them is the only way to reach
the amended branches, and it is exactly what D20 says the boundary must keep possible:
*"A test can supply derived requirements directly, with no database and no extractor,
which keeps the precedence and authority rules unit-testable in isolation."*

The adversarial direction is the one that matters: a prose-derived failure must **never**
reach `NOT_ELIGIBLE`, by any combination of other entries, and must never close the AI
stage (D4a, OD-13).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from app.schemas.candidate import Confidence, JobType
from app.schemas.eligibility import (
    EligibilityState,
    EvaluationMethod,
    ReasonCode,
    RequirementProvenance,
    RequirementResult,
    RequirementStatus,
    RequirementType,
)
from app.schemas.job import JobRead, JobStatusSchema
from app.services.eligibility_engine import (
    ambiguous_requirements,
    build_summary,
    compose_verdict,
    has_verified_hard_failure,
)

SOURCE = RequirementProvenance.SOURCE_STATED
DERIVED = RequirementProvenance.PROSE_DERIVED
DETERMINISTIC = EvaluationMethod.DETERMINISTIC
AI = EvaluationMethod.AI_REASONING

EVIDENCE = "A minimum CGPA of 7.0 on a 10 point scale is required."


def entry(
    status: RequirementStatus,
    *,
    provenance: RequirementProvenance = SOURCE,
    method: EvaluationMethod = DETERMINISTIC,
    requirement_type: RequirementType = RequirementType.MIN_CGPA,
    **overrides: Any,
) -> RequirementResult:
    """One breakdown entry. Reason codes are plausible but not under test here."""
    reason = {
        RequirementStatus.PASS: ReasonCode.MEETS_MINIMUM,
        RequirementStatus.FAIL: ReasonCode.BELOW_MINIMUM,
        RequirementStatus.UNKNOWN: ReasonCode.MISSING_CANDIDATE_VALUE,
    }[status]
    base: dict[str, Any] = {
        "requirement_type": requirement_type,
        "requirement": "Minimum CGPA 7.0 (SCALE_10)",
        "status": status,
        "confidence": Confidence.LOW if status is RequirementStatus.UNKNOWN else Confidence.HIGH,
        "method": method,
        "provenance": provenance,
        "reason_code": reason,
        "note": "Synthetic entry for a precedence test.",
    }
    if provenance is DERIVED:
        base["evidence"] = EVIDENCE
    base.update(overrides)
    return RequirementResult.model_validate(base)


def make_job(**overrides: Any) -> JobRead:
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


PASS_SOURCE = entry(RequirementStatus.PASS)
PASS_DERIVED = entry(RequirementStatus.PASS, provenance=DERIVED)
PASS_AI = entry(
    RequirementStatus.PASS,
    method=AI,
    requirement_type=RequirementType.ALLOWED_FIELDS,
    confidence=Confidence.MEDIUM,
    reason_code=ReasonCode.AI_FIELD_RELATED,
)
FAIL_SOURCE = entry(RequirementStatus.FAIL)
FAIL_DERIVED = entry(RequirementStatus.FAIL, provenance=DERIVED)
FAIL_AI = entry(
    RequirementStatus.FAIL,
    method=AI,
    requirement_type=RequirementType.ALLOWED_FIELDS,
    confidence=Confidence.MEDIUM,
    reason_code=ReasonCode.AI_FIELD_NOT_RELATED,
)
UNKNOWN_SOURCE = entry(RequirementStatus.UNKNOWN)
UNKNOWN_DERIVED = entry(RequirementStatus.UNKNOWN, provenance=DERIVED)


# ---------------------------------------------------------------------------------------
# Rule 2, narrowed — the hard-failure predicate
# ---------------------------------------------------------------------------------------


def test_source_stated_deterministic_failure_is_a_hard_failure() -> None:
    assert has_verified_hard_failure([FAIL_SOURCE])


def test_prose_derived_deterministic_failure_is_not_a_hard_failure() -> None:
    """The whole of ADR-030 D2: authority follows provenance, not the extractor."""
    assert not has_verified_hard_failure([FAIL_DERIVED])


def test_ai_reasoned_failure_is_not_a_hard_failure() -> None:
    """Unchanged by this amendment (ADR-017 R-2)."""
    assert not has_verified_hard_failure([FAIL_AI])


def test_a_derived_failure_does_not_mask_a_source_stated_one() -> None:
    assert has_verified_hard_failure([FAIL_DERIVED, FAIL_SOURCE])


@pytest.mark.parametrize("status", [RequirementStatus.PASS, RequirementStatus.UNKNOWN])
def test_only_a_failure_counts(status: RequirementStatus) -> None:
    """An UNKNOWN is an absence of evidence, never evidence of a state (INV-3)."""
    assert not has_verified_hard_failure([entry(status)])


# ---------------------------------------------------------------------------------------
# Precedence, rule by rule
# ---------------------------------------------------------------------------------------


def test_rule_1_zero_requirements_is_eligible() -> None:
    assert compose_verdict([]) is EligibilityState.ELIGIBLE


def test_rule_2_source_stated_failure_is_not_eligible() -> None:
    assert compose_verdict([FAIL_SOURCE]) is EligibilityState.NOT_ELIGIBLE


def test_rule_2_outranks_everything_else_present() -> None:
    verdict = compose_verdict([PASS_DERIVED, UNKNOWN_SOURCE, FAIL_AI, FAIL_SOURCE])
    assert verdict is EligibilityState.NOT_ELIGIBLE


def test_rule_3_all_unknown_is_unknown() -> None:
    assert compose_verdict([UNKNOWN_SOURCE, UNKNOWN_DERIVED]) is EligibilityState.UNKNOWN


def test_rule_4_prose_derived_failure_is_needs_review() -> None:
    """The widening. Before D4 this composed ``NOT_ELIGIBLE``."""
    assert compose_verdict([FAIL_DERIVED]) is EligibilityState.NEEDS_REVIEW


def test_rule_4_derived_failure_beside_passes_is_still_needs_review() -> None:
    verdict = compose_verdict([PASS_SOURCE, PASS_AI, FAIL_DERIVED])
    assert verdict is EligibilityState.NEEDS_REVIEW


def test_rule_4_unknown_is_needs_review() -> None:
    assert compose_verdict([PASS_SOURCE, UNKNOWN_SOURCE]) is EligibilityState.NEEDS_REVIEW


def test_rule_4_ai_failure_is_needs_review() -> None:
    assert compose_verdict([PASS_SOURCE, FAIL_AI]) is EligibilityState.NEEDS_REVIEW


def test_rule_5_all_pass_with_a_derived_requirement_is_likely_eligible() -> None:
    """The failure D4 closes: this must not be plain ``ELIGIBLE``."""
    assert compose_verdict([PASS_SOURCE, PASS_DERIVED]) is EligibilityState.LIKELY_ELIGIBLE


def test_rule_5_an_entirely_derived_all_pass_is_likely_eligible() -> None:
    assert compose_verdict([PASS_DERIVED]) is EligibilityState.LIKELY_ELIGIBLE


def test_rule_5_all_pass_with_ai_is_likely_eligible() -> None:
    """Unchanged by this amendment."""
    assert compose_verdict([PASS_SOURCE, PASS_AI]) is EligibilityState.LIKELY_ELIGIBLE


def test_rule_6_all_pass_source_stated_and_deterministic_is_eligible() -> None:
    assert compose_verdict([PASS_SOURCE, PASS_SOURCE]) is EligibilityState.ELIGIBLE


# ---------------------------------------------------------------------------------------
# Adversarial: a derived requirement must never exclude anyone (INV-2, D2)
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "others",
    [
        [],
        [PASS_SOURCE],
        [PASS_AI],
        [PASS_DERIVED],
        [UNKNOWN_SOURCE],
        [FAIL_AI],
        [FAIL_DERIVED],
        [PASS_SOURCE, PASS_AI, UNKNOWN_SOURCE, FAIL_AI, FAIL_DERIVED],
    ],
    ids=["alone", "pass", "ai-pass", "derived-pass", "unknown", "ai-fail", "twin", "all"],
)
def test_no_combination_of_derived_failures_reaches_not_eligible(
    others: list[RequirementResult],
) -> None:
    """Exhaustive over the shapes available: without a SOURCE_STATED deterministic FAIL,
    ``NOT_ELIGIBLE`` is unreachable however many prose-derived failures are present."""
    assert compose_verdict([FAIL_DERIVED, *others]) is not EligibilityState.NOT_ELIGIBLE


def test_many_derived_failures_still_only_reach_needs_review() -> None:
    assert compose_verdict([FAIL_DERIVED] * 5) is EligibilityState.NEEDS_REVIEW


def test_a_derived_failure_never_produces_a_passing_verdict() -> None:
    """It is reported honestly: it cannot exclude, and it cannot be ignored either."""
    for verdict in (
        compose_verdict([FAIL_DERIVED]),
        compose_verdict([PASS_SOURCE, FAIL_DERIVED]),
        compose_verdict([PASS_DERIVED, FAIL_DERIVED]),
    ):
        assert verdict not in (EligibilityState.ELIGIBLE, EligibilityState.LIKELY_ELIGIBLE)


def test_a_derived_pass_never_reaches_plain_eligible() -> None:
    """The strongest verdict stays reserved for structurally published requirements."""
    assert compose_verdict([PASS_DERIVED]) is not EligibilityState.ELIGIBLE
    assert compose_verdict([PASS_SOURCE, PASS_DERIVED]) is not EligibilityState.ELIGIBLE


# ---------------------------------------------------------------------------------------
# D4a / OD-13 — the AI stage stays reachable after a prose-derived failure
# ---------------------------------------------------------------------------------------


def _ambiguous_entry() -> RequirementResult:
    return entry(
        RequirementStatus.UNKNOWN,
        requirement_type=RequirementType.ALLOWED_FIELDS,
        reason_code=ReasonCode.FIELD_NOT_EXACT_MATCH,
    )


def test_a_source_stated_failure_still_closes_the_ai_stage() -> None:
    """Unchanged, and the half of C-13 that must not move."""
    assert ambiguous_requirements([FAIL_SOURCE, _ambiguous_entry()]) == []


def test_a_prose_derived_failure_leaves_the_ai_stage_reachable() -> None:
    """ADR-030 D4a, OD-13: not a verified hard failure, so the guard does not fire."""
    assert ambiguous_requirements([FAIL_DERIVED, _ambiguous_entry()]) == [1]


@pytest.mark.parametrize(
    "ai_answer,expected_status",
    [(ReasonCode.AI_FIELD_RELATED, RequirementStatus.PASS),
     (ReasonCode.AI_FIELD_NOT_RELATED, RequirementStatus.FAIL)],
)
def test_the_verdict_cannot_move_whatever_the_ai_answers(
    ai_answer: ReasonCode, expected_status: RequirementStatus
) -> None:
    """Rule 4 fires on the derived failure either way, so INV-2 is untouched."""
    resolved = entry(
        expected_status,
        method=AI,
        requirement_type=RequirementType.ALLOWED_FIELDS,
        confidence=Confidence.MEDIUM,
        reason_code=ai_answer,
    )
    assert compose_verdict([FAIL_DERIVED, resolved]) is EligibilityState.NEEDS_REVIEW


# ---------------------------------------------------------------------------------------
# Summaries track the rules (ADR-006)
# ---------------------------------------------------------------------------------------


def test_not_eligible_summary_does_not_count_a_derived_failure_as_verified() -> None:
    results = [FAIL_SOURCE, FAIL_DERIVED]
    summary = build_summary(EligibilityState.NOT_ELIGIBLE, results, make_job())
    assert "1 of 2 stated requirement(s) failed a verified check" in summary


def test_not_eligible_summary_still_discloses_the_derived_failure() -> None:
    summary = build_summary(
        EligibilityState.NOT_ELIGIBLE, [FAIL_SOURCE, FAIL_DERIVED], make_job()
    )
    assert "read from the job description were not met" in summary
    assert "never on its own enough to rule a candidate out" in summary


def test_likely_eligible_summary_never_reports_zero_by_ai() -> None:
    """The newly reachable all-derived case. The old sentence said "0 of them by AI"."""
    summary = build_summary(
        EligibilityState.LIKELY_ELIGIBLE, [PASS_DERIVED], make_job()
    )
    assert "0 " not in summary
    assert "1 read from the job description" in summary


def test_likely_eligible_summary_reports_both_reasons_when_both_apply() -> None:
    summary = build_summary(
        EligibilityState.LIKELY_ELIGIBLE, [PASS_AI, PASS_DERIVED], make_job()
    )
    assert "1 by AI reasoning" in summary
    assert "1 read from the job description" in summary


def test_likely_eligible_summary_still_reports_ai_alone() -> None:
    summary = build_summary(
        EligibilityState.LIKELY_ELIGIBLE, [PASS_SOURCE, PASS_AI], make_job()
    )
    assert "1 by AI reasoning" in summary
    assert "read from the job description" not in summary


def test_likely_eligible_summary_degrades_safely_on_an_inconsistent_call() -> None:
    """``build_summary`` is public and does not re-derive the state it is given."""
    summary = build_summary(
        EligibilityState.LIKELY_ELIGIBLE, [PASS_SOURCE], make_job()
    )
    assert "0" not in summary
    assert summary.startswith("Likely eligible:")


def test_needs_review_summary_does_not_call_a_derived_failure_unconfirmed() -> None:
    summary = build_summary(EligibilityState.NEEDS_REVIEW, [FAIL_DERIVED], make_job())
    assert "could not be confirmed" not in summary
    assert "read from the job description were not met" in summary


def test_needs_review_summary_still_reports_unconfirmed_entries() -> None:
    summary = build_summary(
        EligibilityState.NEEDS_REVIEW, [PASS_SOURCE, UNKNOWN_SOURCE], make_job()
    )
    assert "1 of 2 stated requirement(s) met" in summary
    assert "could not be confirmed" in summary


def test_a_derived_pass_is_never_reported_as_a_derived_failure() -> None:
    """Only a FAIL is disclosed. A derived requirement the candidate *met* must not be
    counted against them, nor subtracted from the met total."""
    results = [PASS_DERIVED, UNKNOWN_SOURCE]
    summary = build_summary(EligibilityState.NEEDS_REVIEW, results, make_job())
    assert "1 of 2 stated requirement(s) met" in summary
    assert "read from the job description were not met" not in summary


def test_a_derived_pass_beside_a_hard_failure_is_not_disclosed_as_failing() -> None:
    results = [FAIL_SOURCE, PASS_DERIVED]
    summary = build_summary(EligibilityState.NOT_ELIGIBLE, results, make_job())
    assert "1 of 2 stated requirement(s) failed a verified check" in summary
    assert "read from the job description were not met" not in summary


def test_needs_review_summary_reports_both_kinds_together() -> None:
    results = [PASS_SOURCE, UNKNOWN_SOURCE, FAIL_DERIVED]
    summary = build_summary(EligibilityState.NEEDS_REVIEW, results, make_job())
    assert "1 of 3 stated requirement(s) met" in summary
    assert "could not be confirmed" in summary
    assert "read from the job description were not met" in summary


# ---------------------------------------------------------------------------------------
# The description disclosure (ADR-017 R-4 amendment)
# ---------------------------------------------------------------------------------------


DESCRIBED = {"description": "We are hiring. A minimum CGPA of 7.0 is required."}


def test_an_unread_description_is_still_disclosed_as_unread() -> None:
    summary = build_summary(EligibilityState.ELIGIBLE, [PASS_SOURCE], make_job(**DESCRIBED))
    assert "The job description was not evaluated" in summary


def test_a_partly_read_description_is_no_longer_called_unevaluated() -> None:
    """A requirement was promoted out of that text, so the old sentence is false."""
    summary = build_summary(
        EligibilityState.LIKELY_ELIGIBLE, [PASS_DERIVED], make_job(**DESCRIBED)
    )
    assert "The job description was not evaluated" not in summary
    assert "Requirements read from the job description are included above" in summary
    assert "the rest of its text was not evaluated" in summary


def test_the_disclosure_is_never_dropped_entirely() -> None:
    """Unpromoted text stays disclosed-only whatever else happened (ADR-017 R-4)."""
    for results in ([PASS_SOURCE], [PASS_DERIVED], [FAIL_DERIVED], []):
        summary = build_summary(
            compose_verdict(results), results, make_job(**DESCRIBED)
        )
        assert "not evaluated" in summary


def test_a_job_with_no_description_discloses_nothing() -> None:
    summary = build_summary(EligibilityState.ELIGIBLE, [PASS_SOURCE], make_job())
    assert "job description" not in summary


def test_summaries_never_name_a_candidate_value() -> None:
    """INV-4: a client logging summaries must not be logging grades."""
    for state, results in (
        (EligibilityState.NOT_ELIGIBLE, [FAIL_SOURCE, FAIL_DERIVED]),
        (EligibilityState.NEEDS_REVIEW, [FAIL_DERIVED, UNKNOWN_SOURCE]),
        (EligibilityState.LIKELY_ELIGIBLE, [PASS_DERIVED, PASS_AI]),
    ):
        summary = build_summary(state, results, make_job(**DESCRIBED))
        assert EVIDENCE not in summary
        assert "8.0" not in summary
