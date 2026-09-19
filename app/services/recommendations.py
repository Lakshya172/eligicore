"""Recommendation orchestration — eligibility first, matching second, never combined.

This module is an **orchestrator**, not an engine. It decides which catalogue jobs a request
covers, asks Week 4 for their eligibility verdicts and Week 5A for their match evidence, and
arranges the two side by side. Every rule it relies on lives elsewhere:

* eligibility — :func:`app.services.eligibility_ai.check_eligibility_with_ai`, unchanged, called
  once per request, including its AI stage for ambiguous fields (ADR-017, ADR-019);
* matching — :func:`app.services.matching_engine.score_jobs`, called once per request with the
  **whole catalogue** as its TF-IDF corpus (ADR-020).

What it adds is ADR-022: scope, grouping, ranking and explanation composition.

* **Scope is not corpus.** The corpus is every catalogue job; the scope is the jobs returned.
  Default scope is ACTIVE + UNKNOWN, capped at :data:`MAX_RECOMMENDATION_JOBS` by
  ``last_verified_at`` descending then id, with the remainder disclosed. Explicit ``job_ids``
  may request any status; unknown ids are reported, never raised.
* **Grouping never rewrites a verdict.** ``not_open`` (a requested CLOSED or EXPIRED job) takes
  precedence; otherwise the Week 4 state decides. The embedded ``JobEligibility`` is the object
  Week 4 returned.
* **Similarity only orders within a group.** A high score cannot move a job between groups. Jobs
  in ``not_eligible`` carry no score; a ``not_open`` job keeps its full match result, whatever its
  verdict — ``not_open`` changes the group, not the matching result.

Stateless: nothing is stored, cached or written. One counts-only log line; never the profile,
``candidate_id``, skills, experience, terms or per-job scores (INV-4).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence

from app.ai.ai_service import AIService
from app.schemas.candidate import CandidateProfile
from app.schemas.eligibility import EligibilityState, JobEligibility
from app.schemas.job import JobRead, JobStatusSchema
from app.schemas.matching import (
    MAX_RECOMMENDATION_JOBS,
    MatchScoreBasis,
    MatchTermKind,
    RecommendationItem,
    RecommendationMatch,
    RecommendationResponse,
    SharedTerm,
)
from app.services.eligibility_ai import check_eligibility_with_ai
from app.services.matching_engine import (
    JobMatch,
    candidate_match_input,
    job_match_input,
    order_matches,
    score_jobs,
)

logger = logging.getLogger("eligicore.recommendations")

#: Statuses the default scope returns. ``UNKNOWN`` is included: not knowing whether a posting is
#: open is not evidence that it is closed (ADR-014).
DEFAULT_SCOPE_STATUSES = frozenset({JobStatusSchema.ACTIVE, JobStatusSchema.UNKNOWN})

#: Statuses that place a requested job in ``not_open``, ahead of any eligibility group.
NOT_OPEN_STATUSES = frozenset({JobStatusSchema.CLOSED, JobStatusSchema.EXPIRED})

RANKED_STATES = frozenset({EligibilityState.ELIGIBLE, EligibilityState.LIKELY_ELIGIBLE})
REVIEW_STATES = frozenset({EligibilityState.NEEDS_REVIEW, EligibilityState.UNKNOWN})

#: Group names, in response order.
RANKED = "ranked"
NEEDS_REVIEW = "needs_review"
NOT_ELIGIBLE = "not_eligible"
NOT_OPEN = "not_open"


# ---------------------------------------------------------------------------------------
# Scope
# ---------------------------------------------------------------------------------------


def default_scope(catalogue: Sequence[JobRead]) -> tuple[list[str], int]:
    """The ACTIVE and UNKNOWN jobs, newest ``last_verified_at`` first then id, capped.

    Returns the selected ids and how many open jobs the cap left out. Status is read as
    stored; a deadline is never used to infer one.
    """
    open_jobs = [job for job in catalogue if job.status in DEFAULT_SCOPE_STATUSES]
    # Two stable sorts: id ascending, then last_verified_at descending.
    open_jobs.sort(key=lambda job: job.id)
    open_jobs.sort(key=lambda job: job.last_verified_at, reverse=True)
    selected = [job.id for job in open_jobs[:MAX_RECOMMENDATION_JOBS]]
    return selected, len(open_jobs) - len(selected)


def explicit_scope(
    job_ids: Sequence[str], catalogue_ids: set[str]
) -> tuple[list[str], list[str]]:
    """Requested ids split into found (deduplicated, first-seen order) and not found."""
    requested = list(dict.fromkeys(job_ids))
    found = [job_id for job_id in requested if job_id in catalogue_ids]
    not_found = [job_id for job_id in requested if job_id not in catalogue_ids]
    return found, not_found


# ---------------------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------------------


def group_for(eligibility: JobEligibility) -> str:
    """The one group a job belongs to. ``not_open`` first; otherwise the Week 4 state."""
    if eligibility.job_status in NOT_OPEN_STATUSES:
        return NOT_OPEN
    if eligibility.eligibility_state in RANKED_STATES:
        return RANKED
    if eligibility.eligibility_state in REVIEW_STATES:
        return NEEDS_REVIEW
    return NOT_ELIGIBLE


# ---------------------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------------------


def score_withheld(group: str) -> bool:
    """True only for the ``not_eligible`` group, whose jobs are not scored for recommendation.

    A ``not_open`` job keeps its score whatever its verdict: ``not_open`` changes the group,
    not the matching result, and it is never ranked (ADR-022 §7).
    """
    return group == NOT_ELIGIBLE


def match_view(match: JobMatch, group: str) -> RecommendationMatch:
    """The matching engine's evidence, as the API shows it.

    In ``not_eligible`` the score and its shared terms are withheld; skill coverage is still
    shown. Every other group shows the matching result unchanged.
    """
    coverage = match.skill_coverage
    withheld = score_withheld(group)
    return RecommendationMatch(
        match_score=None if withheld else match.match_score,
        score_basis=(
            MatchScoreBasis.WITHHELD_NOT_ELIGIBLE
            if withheld
            else MatchScoreBasis(match.score_basis.value)
        ),
        matched_required_skills=list(coverage.matched_required_skills),
        missing_required_skills=list(coverage.missing_required_skills),
        required_skill_count=coverage.required_skill_count,
        top_terms=[]
        if withheld
        else [
            SharedTerm(
                term=term.term,
                kind=MatchTermKind(term.kind.value),
                contribution=term.contribution,
            )
            for term in match.top_terms
        ],
    )


def compose_explanation(eligibility: JobEligibility, match: JobMatch, group: str) -> str:
    """Join the Week 4 summary and the Week 5A match explanation. No text is generated here
    beyond fixed connecting sentences."""
    if score_withheld(group):
        body = (
            f"{eligibility.summary} Similarity is not reported for a job the profile is not "
            "eligible for."
        )
    else:
        body = f"{eligibility.summary} {match.explanation}"
    if group == NOT_OPEN:
        return (
            f"This posting is {eligibility.job_status.value} and is listed for reference, not "
            f"ranked. {body}"
        )
    return body


# ---------------------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------------------


async def recommend(
    profile: CandidateProfile,
    job_ids: Sequence[str] | None,
    catalogue: Sequence[JobRead],
    ai_service: AIService,
) -> RecommendationResponse:
    """Build grouped, explained recommendations for one profile.

    ``catalogue`` is the whole job catalogue, in the order the corpus fingerprint is taken
    over. It is both the TF-IDF corpus and the pool the scope is drawn from.
    """
    started = time.perf_counter()
    jobs_by_id = {job.id: job for job in catalogue}

    if job_ids is None:
        selected, not_considered = default_scope(catalogue)
        not_found: list[str] = []
    else:
        selected, not_found = explicit_scope(job_ids, set(jobs_by_id))
        not_considered = 0

    eligibility = await check_eligibility_with_ai(
        profile, selected, {job_id: jobs_by_id[job_id] for job_id in selected}, ai_service
    )
    matching = score_jobs(
        candidate_match_input(profile),
        [job_match_input(job) for job in catalogue],
        job_ids=selected,
    )
    matches = {match.job_id: match for match in matching.matches}

    grouped: dict[str, list[tuple[JobEligibility, JobMatch]]] = {
        RANKED: [], NEEDS_REVIEW: [], NOT_ELIGIBLE: [], NOT_OPEN: []
    }
    for result in eligibility.results:
        grouped[group_for(result)].append((result, matches[result.job_id]))

    groups: dict[str, list[RecommendationItem]] = {}
    for name, pairs in grouped.items():
        if name in (RANKED, NEEDS_REVIEW):
            order = {m.job_id: i for i, m in enumerate(order_matches(m for _, m in pairs))}
            pairs.sort(key=lambda pair: order[pair[1].job_id])
            ranks: list[int | None] = list(range(1, len(pairs) + 1))
        else:
            pairs.sort(key=lambda pair: pair[0].job_id)
            ranks = [None] * len(pairs)
        groups[name] = [
            RecommendationItem(
                rank=rank,
                eligibility=result,
                match=match_view(match, name),
                explanation=compose_explanation(result, match, name),
            )
            for rank, (result, match) in zip(ranks, pairs)
        ]

    response = RecommendationResponse(
        candidate_id=eligibility.candidate_id,
        engine_version=eligibility.engine_version,
        matching_version=matching.matching_version,
        evaluated_at=eligibility.evaluated_at,
        corpus_size=matching.corpus_size,
        corpus_fingerprint=matching.corpus_fingerprint,
        jobs_considered=len(selected),
        jobs_not_considered=not_considered,
        ranked=groups[RANKED],
        needs_review=groups[NEEDS_REVIEW],
        not_eligible=groups[NOT_ELIGIBLE],
        not_open=groups[NOT_OPEN],
        not_found_job_ids=not_found,
    )

    logger.info(
        "recommendations jobs_considered=%d jobs_not_considered=%d not_found=%d ranked=%d "
        "needs_review=%d not_eligible=%d not_open=%d null_scores=%d corpus_size=%d "
        "duration_ms=%.1f",
        response.jobs_considered,
        response.jobs_not_considered,
        len(not_found),
        len(response.ranked),
        len(response.needs_review),
        len(response.not_eligible),
        len(response.not_open),
        sum(
            1
            for group in (response.ranked, response.needs_review, response.not_open)
            for item in group
            if item.match.score_basis
            in (MatchScoreBasis.NO_CANDIDATE_TERMS, MatchScoreBasis.NO_JOB_TERMS)
        ),
        response.corpus_size,
        (time.perf_counter() - started) * 1000,
    )
    return response
