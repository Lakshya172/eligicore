"""Recommendation service tests (PR 5B — ADR-022).

The service is exercised directly with in-memory ``JobRead`` catalogues and the mock AI
provider: no server, no database. Endpoint contract and privacy against a real database are in
``tests/test_recommendations_endpoint.py``.

Every fixture is obviously synthetic.
"""

from __future__ import annotations

import ast
import logging
import os
import pathlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from app.ai.ai_service import AIService
from app.ai.providers.mock import MockAIProvider
from app.schemas.candidate import CandidateProfile
from app.schemas.eligibility import EligibilityState, FieldRelatednessAssessment
from app.schemas.job import JobRead
from app.schemas.matching import MAX_RECOMMENDATION_JOBS, MatchScoreBasis
from app.services import matching_engine
from app.services import recommendations as service
from app.services.eligibility_ai import check_eligibility_with_ai
from app.services.matching_engine import (
    candidate_match_input,
    job_match_input,
    score_jobs,
)
from app.services.recommendations import recommend

pytestmark = pytest.mark.anyio

SERVICE_PATH = pathlib.Path(service.__file__)
BASE_TIME = datetime(2026, 9, 1, tzinfo=timezone.utc)

#: Denylisted judgement phrases: explanations describe evidence, never a hiring opinion.
JUDGEMENTS = re.compile(
    r"perfect fit|excellent candidate|best job|you should apply|highly suitable|great fit|"
    r"strong candidate|excellent match|ideal",
    re.IGNORECASE,
)


def make_job(job_id: str, **overrides: Any) -> JobRead:
    """A synthetic catalogue job; no requirements unless overridden."""
    base: dict[str, Any] = {
        "id": job_id,
        "company_name": "Example Co",
        "role_title": "Software Engineering Intern",
        "job_type": "INTERNSHIP",
        "location": "Remote",
        "description": "Build backend services and data pipelines in Python.",
        "requirements": {},
        "min_cgpa": None,
        "min_cgpa_scale": None,
        "allowed_fields": [],
        "min_degree_level": None,
        "max_backlogs": None,
        "min_grad_year": None,
        "max_grad_year": None,
        "required_skills": ["Python", "SQL"],
        "apply_link": None,
        "deadline": None,
        "source": "test",
        "source_job_id": None,
        "status": "ACTIVE",
        "last_verified_at": BASE_TIME,
    }
    base.update(overrides)
    base["is_active"] = base["status"] == "ACTIVE"
    return JobRead.model_validate(base)


# One profile drives every state: CGPA 8.2/10, backlogs unknown, field Information Technology.
PROFILE: dict[str, Any] = {
    "candidate_id": "client-correlation-id",
    "education": [
        {
            "degree": "B.Tech",
            "level": "BACHELORS",
            "field_of_study": "Information Technology",
            "grad_year": 2027,
            "cgpa": 8.2,
            "scale": "SCALE_10",
        }
    ],
    "skills": ["Python", "SQL"],
    "experience": [{"title": "Data Intern", "description": "Built data pipelines in Python."}],
}

#: Requirement sets producing each Week 4 state for PROFILE.
ELIGIBLE = {"min_cgpa": 7.0, "min_cgpa_scale": "SCALE_10"}
NOT_ELIGIBLE = {"min_cgpa": 9.0, "min_cgpa_scale": "SCALE_10"}
UNKNOWN = {"max_backlogs": 0}
NEEDS_REVIEW = {"min_cgpa": 7.0, "min_cgpa_scale": "SCALE_10", "max_backlogs": 0}
AMBIGUOUS_FIELD = {"allowed_fields": ["Computer Science"]}


def profile(**overrides: Any) -> CandidateProfile:
    return CandidateProfile.model_validate({**PROFILE, **overrides})


def ai(answer: str = "UNCERTAIN", confidence: str = "LOW") -> AIService:
    return AIService(
        provider=MockAIProvider(
            return_relatedness=FieldRelatednessAssessment(
                result=answer, confidence=confidence, reason="Synthetic answer."
            )
        )
    )


def related() -> AIService:
    return ai("RELATED", "HIGH")


def all_items(response):
    return [*response.ranked, *response.needs_review, *response.not_eligible, *response.not_open]


def ids(items) -> list[str]:
    return [item.eligibility.job_id for item in items]


def group_of(response, job_id: str) -> str:
    groups = [
        name
        for name in ("ranked", "needs_review", "not_eligible", "not_open")
        if job_id in ids(getattr(response, name))
    ]
    assert len(groups) == 1, groups
    return groups[0]


# ---------------------------------------------------------------------------------------
# Grouping — every state, exactly one group, verdict unchanged
# ---------------------------------------------------------------------------------------

STATE_CATALOGUE = [
    make_job("eligible", **ELIGIBLE),
    make_job("likely", **AMBIGUOUS_FIELD),
    make_job("review", **NEEDS_REVIEW),
    make_job("unknown", **UNKNOWN),
    make_job("ineligible", **NOT_ELIGIBLE),
]


@pytest.mark.parametrize(
    ("job_id", "state", "group"),
    [
        ("eligible", EligibilityState.ELIGIBLE, "ranked"),
        ("likely", EligibilityState.LIKELY_ELIGIBLE, "ranked"),
        ("review", EligibilityState.NEEDS_REVIEW, "needs_review"),
        ("unknown", EligibilityState.UNKNOWN, "needs_review"),
        ("ineligible", EligibilityState.NOT_ELIGIBLE, "not_eligible"),
    ],
)
async def test_each_eligibility_state_lands_in_its_group(
    job_id: str, state: EligibilityState, group: str
) -> None:
    response = await recommend(profile(), None, STATE_CATALOGUE, related())
    item = next(i for i in all_items(response) if i.eligibility.job_id == job_id)
    assert item.eligibility.eligibility_state is state
    assert group_of(response, job_id) == group


@pytest.mark.parametrize("status", ["CLOSED", "EXPIRED"])
@pytest.mark.parametrize(
    "requirements", [ELIGIBLE, AMBIGUOUS_FIELD, NEEDS_REVIEW, UNKNOWN, NOT_ELIGIBLE]
)
async def test_requested_closed_or_expired_job_is_not_open_whatever_its_verdict(
    status: str, requirements: dict[str, Any]
) -> None:
    catalogue = [make_job("gone", status=status, **requirements)]
    response = await recommend(profile(), ["gone"], catalogue, related())
    assert group_of(response, "gone") == "not_open"
    assert response.not_open[0].rank is None


async def test_every_found_job_appears_in_exactly_one_group() -> None:
    catalogue = [
        *STATE_CATALOGUE,
        make_job("closed", status="CLOSED", **ELIGIBLE),
        make_job("expired", status="EXPIRED", **NOT_ELIGIBLE),
    ]
    requested = [job.id for job in catalogue]
    response = await recommend(profile(), requested, catalogue, related())
    assert sorted(ids(all_items(response))) == sorted(requested)
    for job_id in requested:
        group_of(response, job_id)


async def test_embedded_eligibility_is_exactly_the_week_4_result() -> None:
    catalogue = [*STATE_CATALOGUE, make_job("closed", status="CLOSED", **ELIGIBLE)]
    requested = [job.id for job in catalogue]
    response = await recommend(profile(), requested, catalogue, related())
    week4 = await check_eligibility_with_ai(
        profile(), requested, {job.id: job for job in catalogue}, related()
    )

    expected = {result.job_id: result.model_dump() for result in week4.results}
    for item in all_items(response):
        assert item.eligibility.model_dump() == expected[item.eligibility.job_id]
    assert response.engine_version == week4.engine_version == "2"


# ---------------------------------------------------------------------------------------
# Scope — corpus is the catalogue, scope is what is returned
# ---------------------------------------------------------------------------------------


async def test_default_scope_is_active_and_unknown_only() -> None:
    catalogue = [
        make_job("active", status="ACTIVE"),
        make_job("unknown-status", status="UNKNOWN"),
        make_job("closed", status="CLOSED"),
        make_job("expired", status="EXPIRED"),
    ]
    response = await recommend(profile(), None, catalogue, ai())
    assert sorted(ids(all_items(response))) == ["active", "unknown-status"]
    assert response.not_open == []
    assert response.jobs_considered == 2 and response.jobs_not_considered == 0
    assert response.corpus_size == 4


@pytest.mark.parametrize("status", ["ACTIVE", "UNKNOWN", "CLOSED", "EXPIRED"])
async def test_explicitly_requested_job_is_returned_whatever_its_status(status: str) -> None:
    catalogue = [make_job("x", status=status, **ELIGIBLE)]
    response = await recommend(profile(), ["x"], catalogue, ai())
    assert ids(all_items(response)) == ["x"]
    assert response.not_found_job_ids == []


async def test_past_deadline_does_not_make_an_active_job_expired() -> None:
    catalogue = [make_job("late", deadline="2020-01-01", **ELIGIBLE)]
    response = await recommend(profile(), None, catalogue, ai())
    assert ids(response.ranked) == ["late"]
    assert response.ranked[0].eligibility.job_status.value == "ACTIVE"


async def test_default_scope_over_the_cap_takes_the_newest_first_and_discloses_the_rest() -> None:
    catalogue = [
        make_job(f"job-{i:03d}", last_verified_at=BASE_TIME + timedelta(hours=i))
        for i in range(MAX_RECOMMENDATION_JOBS + 7)
    ]
    catalogue.append(make_job("closed-newest", status="CLOSED", last_verified_at=BASE_TIME + timedelta(days=30)))
    response = await recommend(profile(), None, catalogue, ai())

    newest = {f"job-{i:03d}" for i in range(7, MAX_RECOMMENDATION_JOBS + 7)}
    assert set(ids(all_items(response))) == newest
    assert response.jobs_considered == MAX_RECOMMENDATION_JOBS == 50
    assert response.jobs_not_considered == 7
    assert response.corpus_size == len(catalogue)


async def test_cap_ties_on_verification_time_are_broken_by_id() -> None:
    catalogue = [make_job(f"t-{i:03d}") for i in range(MAX_RECOMMENDATION_JOBS + 2)]
    response = await recommend(profile(), None, catalogue, ai())
    returned = set(ids(all_items(response)))
    assert returned == {f"t-{i:03d}" for i in range(MAX_RECOMMENDATION_JOBS)}
    assert response.jobs_not_considered == 2


async def test_empty_default_scope_is_an_empty_response() -> None:
    response = await recommend(profile(), None, [make_job("closed", status="CLOSED")], ai())
    assert all_items(response) == []
    assert response.jobs_considered == 0 and response.corpus_size == 1


async def test_empty_catalogue() -> None:
    response = await recommend(profile(), None, [], ai())
    assert all_items(response) == [] and response.corpus_size == 0


# ---------------------------------------------------------------------------------------
# Batching — duplicates, unknown ids
# ---------------------------------------------------------------------------------------


async def test_unknown_ids_are_reported_in_request_order_never_raised() -> None:
    response = await recommend(
        profile(), ["nope-2", "eligible", "nope-1"], STATE_CATALOGUE, ai()
    )
    assert response.not_found_job_ids == ["nope-2", "nope-1"]
    assert ids(all_items(response)) == ["eligible"]
    assert response.jobs_considered == 1


async def test_all_unknown_ids() -> None:
    response = await recommend(profile(), ["x", "y"], STATE_CATALOGUE, ai())
    assert response.not_found_job_ids == ["x", "y"]
    assert all_items(response) == [] and response.jobs_considered == 0


async def test_duplicates_are_evaluated_and_reported_once() -> None:
    response = await recommend(
        profile(), ["eligible", "eligible", "review", "eligible", "ghost", "ghost"],
        STATE_CATALOGUE, ai(),
    )
    assert sorted(ids(all_items(response))) == ["eligible", "review"]
    assert response.not_found_job_ids == ["ghost"]
    assert response.jobs_considered == 2


async def test_all_duplicates_collapse_to_one_job() -> None:
    response = await recommend(profile(), ["eligible"] * 5, STATE_CATALOGUE, ai())
    assert ids(all_items(response)) == ["eligible"]


async def test_fifty_explicit_ids() -> None:
    catalogue = [make_job(f"j-{i:02d}") for i in range(MAX_RECOMMENDATION_JOBS)]
    response = await recommend(profile(), [j.id for j in catalogue], catalogue, ai())
    assert len(all_items(response)) == 50 and response.jobs_considered == 50


# ---------------------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------------------

RANKING_CATALOGUE = [
    make_job("b-low", required_skills=["Java"], description="Frontend styling work.", **ELIGIBLE),
    make_job("a-high", required_skills=["Python", "SQL"], **ELIGIBLE),
    make_job("c-tie", required_skills=["Python", "SQL"], **ELIGIBLE),
    make_job("d-empty", required_skills=[], role_title="The", description="", **ELIGIBLE),
    make_job("r-2", required_skills=["Java"], description="Frontend styling work.", **NEEDS_REVIEW),
    make_job("r-1", required_skills=["Python", "SQL"], **NEEDS_REVIEW),
    make_job("z-ineligible", required_skills=["Python", "SQL"], **NOT_ELIGIBLE),
    make_job("y-ineligible", required_skills=["Java"], **NOT_ELIGIBLE),
]


async def test_ranked_orders_by_score_then_id_with_nulls_last() -> None:
    response = await recommend(profile(), None, RANKING_CATALOGUE, ai())
    ranked = response.ranked
    assert ids(ranked) == ["a-high", "c-tie", "b-low", "d-empty"]
    assert [i.rank for i in ranked] == [1, 2, 3, 4]
    assert ranked[0].match.match_score == ranked[1].match.match_score
    assert ranked[1].match.match_score > ranked[2].match.match_score
    assert ranked[3].match.match_score is None
    assert ranked[3].match.score_basis is MatchScoreBasis.NO_JOB_TERMS


async def test_needs_review_uses_the_same_ordering() -> None:
    response = await recommend(profile(), None, RANKING_CATALOGUE, ai())
    assert ids(response.needs_review) == ["r-1", "r-2"]
    assert [i.rank for i in response.needs_review] == [1, 2]


async def test_ranking_does_not_depend_on_request_order() -> None:
    forward = [j.id for j in RANKING_CATALOGUE]
    first = await recommend(profile(), forward, RANKING_CATALOGUE, ai())
    second = await recommend(profile(), list(reversed(forward)), RANKING_CATALOGUE, ai())
    for name in ("ranked", "needs_review", "not_eligible", "not_open"):
        assert ids(getattr(first, name)) == ids(getattr(second, name))


async def test_not_eligible_is_unranked_by_id_and_unscored() -> None:
    response = await recommend(profile(), None, RANKING_CATALOGUE, ai())
    group = response.not_eligible
    assert ids(group) == ["y-ineligible", "z-ineligible"]
    assert [i.rank for i in group] == [None, None]
    for item in group:
        assert item.match.match_score is None
        assert item.match.score_basis is MatchScoreBasis.WITHHELD_NOT_ELIGIBLE
        assert item.match.top_terms == []
    # Coverage is still reported.
    assert group[1].match.matched_required_skills == ["Python", "SQL"]


async def test_a_perfect_score_cannot_promote_a_not_eligible_job() -> None:
    catalogue = [
        make_job("perfect", required_skills=["Python", "SQL"], role_title="Data Intern",
                 description="Built data pipelines in Python.", **NOT_ELIGIBLE),
        make_job("other", required_skills=["Java"]),
    ]
    raw = score_jobs(
        candidate_match_input(profile()), [job_match_input(j) for j in catalogue], ["perfect"]
    )
    assert raw.matches[0].match_score == 100.0
    response = await recommend(profile(), None, catalogue, ai())
    assert group_of(response, "perfect") == "not_eligible"
    assert response.not_eligible[0].eligibility.eligibility_state is EligibilityState.NOT_ELIGIBLE


async def test_a_high_score_cannot_rank_a_not_open_job() -> None:
    catalogue = [
        make_job("closed-perfect", status="CLOSED", required_skills=["Python", "SQL"],
                 role_title="Data Intern", description="Built data pipelines in Python.",
                 **ELIGIBLE),
        make_job("a-open", required_skills=["Java"], **ELIGIBLE),
    ]
    response = await recommend(profile(), ["closed-perfect", "a-open"], catalogue, ai())
    assert ids(response.ranked) == ["a-open"]
    assert ids(response.not_open) == ["closed-perfect"]
    assert response.not_open[0].rank is None
    assert response.not_open[0].match.match_score == 100.0  # shown, never ranked


async def test_not_open_is_ordered_by_id() -> None:
    catalogue = [make_job(i, status="CLOSED") for i in ("c", "a", "b")]
    response = await recommend(profile(), ["c", "a", "b"], catalogue, ai())
    assert ids(response.not_open) == ["a", "b", "c"]


# not_open changes the group, not the matching result (ADR-022 §7).
PERFECT = {
    "required_skills": ["Python", "SQL"],
    "role_title": "Data Intern",
    "description": "Built data pipelines in Python.",
}


@pytest.mark.parametrize(
    ("status", "requirements", "state"),
    [
        ("CLOSED", NOT_ELIGIBLE, EligibilityState.NOT_ELIGIBLE),
        ("EXPIRED", NOT_ELIGIBLE, EligibilityState.NOT_ELIGIBLE),
        ("CLOSED", ELIGIBLE, EligibilityState.ELIGIBLE),
        ("EXPIRED", NEEDS_REVIEW, EligibilityState.NEEDS_REVIEW),
    ],
)
async def test_not_open_keeps_the_full_match_result_whatever_the_verdict(
    status: str, requirements: dict[str, Any], state: EligibilityState
) -> None:
    catalogue = [make_job("gone", status=status, **PERFECT, **requirements), make_job("other")]
    response = await recommend(profile(), ["gone"], catalogue, ai())
    item = response.not_open[0]
    direct = score_jobs(
        candidate_match_input(profile()), [job_match_input(j) for j in catalogue], ["gone"]
    ).matches[0]

    assert item.rank is None
    assert item.eligibility.eligibility_state is state
    assert item.match.match_score == direct.match_score == 100.0
    assert item.match.score_basis is MatchScoreBasis.SCORED
    assert [t.term for t in item.match.top_terms] == [t.term for t in direct.top_terms]
    assert item.match.matched_required_skills == ["Python", "SQL"]
    assert item.explanation.endswith(direct.explanation)
    assert all_items(response) == [item]


async def test_not_open_order_ignores_scores() -> None:
    catalogue = [
        make_job("a-low", status="CLOSED", required_skills=["Java"], description="Frontend work.",
                 **NOT_ELIGIBLE),
        make_job("b-high", status="EXPIRED", **PERFECT, **NOT_ELIGIBLE),
        make_job("c-mid", status="CLOSED", **ELIGIBLE),
    ]
    response = await recommend(profile(), ["c-mid", "b-high", "a-low"], catalogue, ai())
    assert ids(response.not_open) == ["a-low", "b-high", "c-mid"]
    assert [i.rank for i in response.not_open] == [None, None, None]
    scores = [i.match.match_score for i in response.not_open]
    assert scores[1] > scores[2] > scores[0]  # the highest score is not first: order is by id


async def test_withholding_is_limited_to_the_not_eligible_group() -> None:
    catalogue = [
        make_job("open-ineligible", **PERFECT, **NOT_ELIGIBLE),
        make_job("closed-ineligible", status="CLOSED", **PERFECT, **NOT_ELIGIBLE),
    ]
    response = await recommend(profile(), [j.id for j in catalogue], catalogue, ai())
    assert response.not_eligible[0].match.match_score is None
    assert response.not_eligible[0].match.score_basis is MatchScoreBasis.WITHHELD_NOT_ELIGIBLE
    assert response.not_open[0].match.match_score == 100.0
    for item in all_items(response):
        assert item.eligibility.eligibility_state is EligibilityState.NOT_ELIGIBLE


# ---------------------------------------------------------------------------------------
# Corpus fingerprint through the service (ADR-020 §5, C-19)
# ---------------------------------------------------------------------------------------

FINGERPRINT_CATALOGUE = [
    make_job("fp-a", required_skills=["Python"], description="Backend services."),
    make_job("fp-b", required_skills=["SQL"], description="Data pipelines.", status="CLOSED"),
    make_job("fp-c", required_skills=["Java"], description="Frontend styling."),
]


async def fingerprint(catalogue, who=None) -> str:
    return (await recommend(who or profile(), None, catalogue, ai())).corpus_fingerprint


async def test_fingerprint_a_same_jobs_same_order_is_identical() -> None:
    copy = [job.model_copy() for job in FINGERPRINT_CATALOGUE]
    assert await fingerprint(FINGERPRINT_CATALOGUE) == await fingerprint(copy)


async def test_fingerprint_b_same_jobs_different_order_differs() -> None:
    reordered = [FINGERPRINT_CATALOGUE[2], FINGERPRINT_CATALOGUE[0], FINGERPRINT_CATALOGUE[1]]
    first = await recommend(profile(), None, FINGERPRINT_CATALOGUE, ai())
    second = await recommend(profile(), None, reordered, ai())
    assert first.corpus_fingerprint != second.corpus_fingerprint
    # Only the fingerprint moves: scores do not depend on catalogue order.
    assert {i.eligibility.job_id: i.match for i in all_items(first)} == {
        i.eligibility.job_id: i.match for i in all_items(second)
    }


async def test_fingerprint_c_only_last_verified_at_changed_is_identical() -> None:
    reverified = [
        job.model_copy(update={"last_verified_at": BASE_TIME + timedelta(days=90 - n)})
        for n, job in enumerate(FINGERPRINT_CATALOGUE)
    ]
    assert await fingerprint(FINGERPRINT_CATALOGUE) == await fingerprint(reverified)


@pytest.mark.parametrize(
    "update",
    [
        {"description": "Rewritten posting."},
        {"role_title": "Platform Engineer"},
        {"required_skills": ["SQL", "Git"]},
    ],
)
async def test_fingerprint_d_changed_matching_content_differs(update: dict[str, Any]) -> None:
    edited = [
        FINGERPRINT_CATALOGUE[0],
        FINGERPRINT_CATALOGUE[1].model_copy(update=update),
        FINGERPRINT_CATALOGUE[2],
    ]
    assert await fingerprint(FINGERPRINT_CATALOGUE) != await fingerprint(edited)


async def test_fingerprint_e_changed_candidate_is_identical() -> None:
    others = [
        profile(candidate_id="someone-else", skills=["Haskell"], experience=[]),
        profile(skills=[], experience=[{"title": "Quokka wrangler"}]),
        marker_profile(),
    ]
    baseline = await fingerprint(FINGERPRINT_CATALOGUE)
    for other in others:
        assert await fingerprint(FINGERPRINT_CATALOGUE, other) == baseline


# ---------------------------------------------------------------------------------------
# Integration — one eligibility pass, one matching pass, the whole catalogue as corpus
# ---------------------------------------------------------------------------------------


async def test_eligibility_is_called_once_with_each_found_job_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    async def spy(profile_, job_ids, jobs_by_id, ai_service):
        calls.append(list(job_ids))
        return await check_eligibility_with_ai(profile_, job_ids, jobs_by_id, ai_service)

    monkeypatch.setattr(service, "check_eligibility_with_ai", spy)
    await recommend(profile(), ["review", "eligible", "review", "ghost"], STATE_CATALOGUE, ai())
    assert calls == [["review", "eligible"]]


async def test_matching_is_called_once_with_the_whole_catalogue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], list[str]]] = []

    def spy(candidate, catalogue, job_ids=None):
        calls.append(([j.job_id for j in catalogue], list(job_ids)))
        return score_jobs(candidate, catalogue, job_ids)

    monkeypatch.setattr(service, "score_jobs", spy)
    catalogue = [*STATE_CATALOGUE, make_job("closed", status="CLOSED")]
    await recommend(profile(), ["eligible"], catalogue, ai())
    assert calls == [([j.id for j in catalogue], ["eligible"])]


async def test_scores_and_corpus_equal_a_direct_matching_call() -> None:
    catalogue = [*RANKING_CATALOGUE, make_job("closed", status="CLOSED", **ELIGIBLE)]
    response = await recommend(profile(), None, catalogue, ai())
    direct = score_jobs(
        candidate_match_input(profile()), [job_match_input(j) for j in catalogue]
    )
    scores = {m.job_id: m.match_score for m in direct.matches}
    for item in [*response.ranked, *response.needs_review]:
        assert item.match.match_score == scores[item.eligibility.job_id]
    assert response.corpus_size == direct.corpus_size == len(catalogue)
    assert response.corpus_fingerprint == direct.corpus_fingerprint
    assert response.matching_version == direct.matching_version == "1"


async def test_scope_does_not_change_scores_or_fingerprint() -> None:
    one = await recommend(profile(), ["a-high"], RANKING_CATALOGUE, ai())
    everything = await recommend(profile(), None, RANKING_CATALOGUE, ai())
    assert one.corpus_fingerprint == everything.corpus_fingerprint
    assert one.ranked[0].match == next(i for i in everything.ranked if i.eligibility.job_id == "a-high").match


async def test_candidate_never_changes_the_corpus_fingerprint() -> None:
    first = await recommend(profile(), None, STATE_CATALOGUE, ai())
    second = await recommend(
        profile(candidate_id="other", skills=["Haskell"], experience=[]), None, STATE_CATALOGUE, ai()
    )
    assert first.corpus_fingerprint == second.corpus_fingerprint


async def test_ambiguous_field_goes_through_the_week_4_ai_stage() -> None:
    provider = MockAIProvider(
        return_relatedness=FieldRelatednessAssessment(result="RELATED", confidence="HIGH", reason="x")
    )
    response = await recommend(profile(), ["likely"], STATE_CATALOGUE, AIService(provider=provider))
    assert provider.relatedness_call_count == 1
    assert response.ranked[0].eligibility.eligibility_state is EligibilityState.LIKELY_ELIGIBLE


async def test_no_ai_call_when_nothing_is_ambiguous() -> None:
    provider = MockAIProvider()
    await recommend(profile(), None, [make_job("e", **ELIGIBLE), make_job("n", **NOT_ELIGIBLE)],
                    AIService(provider=provider))
    assert provider.relatedness_call_count == 0


async def test_hard_failure_stays_not_eligible_even_with_an_ambiguous_field() -> None:
    provider = MockAIProvider(
        return_relatedness=FieldRelatednessAssessment(result="RELATED", confidence="HIGH", reason="x")
    )
    catalogue = [make_job("hard", **NOT_ELIGIBLE, **AMBIGUOUS_FIELD)]
    response = await recommend(profile(), None, catalogue, AIService(provider=provider))
    assert group_of(response, "hard") == "not_eligible"
    assert provider.relatedness_call_count == 0


async def test_response_metadata() -> None:
    response = await recommend(profile(), None, STATE_CATALOGUE, related())
    assert response.candidate_id == "client-correlation-id"
    assert response.engine_version == "2" and response.matching_version == "1"
    assert response.evaluated_at.tzinfo is not None
    assert re.fullmatch(r"[0-9a-f]{64}", response.corpus_fingerprint)


# ---------------------------------------------------------------------------------------
# Explanations
# ---------------------------------------------------------------------------------------


async def test_explanations_compose_the_week_4_summary_and_the_match_explanation() -> None:
    catalogue = [*RANKING_CATALOGUE, make_job("gone", status="CLOSED", **ELIGIBLE)]
    response = await recommend(profile(), [j.id for j in catalogue], catalogue, ai())
    direct = {
        m.job_id: m
        for m in score_jobs(
            candidate_match_input(profile()), [job_match_input(j) for j in catalogue]
        ).matches
    }
    for item in [*response.ranked, *response.needs_review]:
        assert item.explanation == f"{item.eligibility.summary} {direct[item.eligibility.job_id].explanation}"
    for item in response.not_eligible:
        assert item.explanation == (
            f"{item.eligibility.summary} Similarity is not reported for a job the profile is "
            "not eligible for."
        )
        assert "Similarity" not in item.explanation.split("Similarity is not reported")[0]
    closed = response.not_open[0]
    assert closed.explanation.startswith(
        "This posting is CLOSED and is listed for reference, not ranked. "
    )
    assert closed.explanation.endswith(direct["gone"].explanation)


async def test_explanations_contain_no_judgements() -> None:
    catalogue = [*STATE_CATALOGUE, *RANKING_CATALOGUE, make_job("gone", status="EXPIRED")]
    response = await recommend(profile(), [j.id for j in catalogue], catalogue, related())
    for item in all_items(response):
        assert not JUDGEMENTS.search(item.explanation), item.explanation


# ---------------------------------------------------------------------------------------
# Privacy
# ---------------------------------------------------------------------------------------

MARKERS = [
    "MARKER-ID-5b19",
    "Marker Person Qelvin",
    "qelvin.marker@example.com",
    "MARKER-PHONE-5550142",
    "Markerburg",
    "MarkerSkillZorblang",
    "Markerologist Title",
    "markerexperiencedescription",
    "Markercorp Experience",
    "Marker Institute Ivy",
    "markerresumebody",
]


def marker_profile() -> CandidateProfile:
    return profile(
        candidate_id=MARKERS[0],
        name=MARKERS[1],
        email=MARKERS[2],
        phone=MARKERS[3],
        location=MARKERS[4],
        skills=["Python", MARKERS[5]],
        experience=[
            {"title": MARKERS[6], "description": MARKERS[7], "company": MARKERS[8]}
        ],
        education=[{**PROFILE["education"][0], "institution": MARKERS[9]}],
        resume_raw_text=MARKERS[10],
    )


async def test_nothing_about_the_candidate_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        response = await recommend(marker_profile(), None, [*STATE_CATALOGUE, *RANKING_CATALOGUE], related())
    assert all_items(response)
    logged = caplog.text + "\n".join(str(record.args) for record in caplog.records)
    for marker in MARKERS:
        assert marker not in logged
    line = next(r for r in caplog.records if r.name == "eligicore.recommendations")
    assert re.fullmatch(
        r"recommendations jobs_considered=\d+ jobs_not_considered=\d+ not_found=\d+ ranked=\d+ "
        r"needs_review=\d+ not_eligible=\d+ not_open=\d+ null_scores=\d+ corpus_size=\d+ "
        r"duration_ms=[\d.]+",
        line.getMessage(),
    )


async def test_response_holds_no_candidate_values_outside_eligibility_breakdowns() -> None:
    response = await recommend(marker_profile(), None, STATE_CATALOGUE, related())
    for item in all_items(response):
        text = item.match.model_dump_json() + item.explanation
        for marker in MARKERS:
            assert marker not in text
    assert response.candidate_id == MARKERS[0]  # the one approved echo


async def test_recommending_writes_no_files(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    await recommend(marker_profile(), None, STATE_CATALOGUE, related())
    assert os.listdir(tmp_path) == []


# ---------------------------------------------------------------------------------------
# Architecture
# ---------------------------------------------------------------------------------------


def imported_modules(path: pathlib.Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_service_uses_no_framework_database_or_provider_code() -> None:
    for module in imported_modules(SERVICE_PATH):
        assert not module.startswith(
            ("fastapi", "starlette", "sqlalchemy", "app.routers", "app.models", "app.database",
             "app.ai.providers", "httpx")
        ), module


def test_service_reuses_eligibility_and_matching_rather_than_reimplementing_them() -> None:
    source = SERVICE_PATH.read_text(encoding="utf-8")
    modules = imported_modules(SERVICE_PATH)
    assert "app.services.eligibility_ai" in modules
    assert "app.services.matching_engine" in modules
    assert "app.services.eligibility_engine" not in modules
    for reimplementation in ("TfidfVectorizer", "sklearn", "compose_verdict", "evaluate_requirements"):
        assert reimplementation not in source


@pytest.mark.parametrize(
    "module",
    [
        "app/services/matching_engine.py",
        "app/services/eligibility_engine.py",
        "app/services/eligibility_ai.py",
    ],
)
def test_nothing_below_the_service_imports_recommendations(module: str) -> None:
    assert not any(
        "recommendations" in name or "routers" in name
        for name in imported_modules(pathlib.Path(module))
    )


def test_matching_engine_still_has_no_logging_or_io() -> None:
    modules = imported_modules(pathlib.Path(matching_engine.__file__))
    assert not modules & {"logging", "os", "io", "pathlib", "tempfile", "pickle", "sqlite3"}
