"""Week 8 Slice 8B — the candidate-free corpus cache (ADR-026 D7, ADR-020 §5 as amended).

Slice 8B is an **output-identical optimization**. Everything here exists to prove one claim
in two halves:

* **Nothing observable changed.** Scores, bases, top terms, ordering, fingerprint and
  grouping are the same cold, warm and after eviction. A cache that changes an answer is not
  a cache, it is a bug with a hit rate.
* **Nothing candidate-derived is shared.** The fit is cached; the candidate's transform is
  not. Two candidates against one warm corpus share the catalogue's vocabulary and nothing
  else, and no candidate value reaches the key, the value or anywhere near them.

The cache is process-wide, so every test here clears it first. That is also why
``CORPUS_CACHE.clear()`` exists: tests need a cold start, not production code.
"""

from __future__ import annotations

import ast
import concurrent.futures
import hashlib
import inspect
import pickle
import textwrap
from dataclasses import fields
from typing import Any

import numpy as np
import pytest

from app.services.matching_engine import (
    CORPUS_CACHE,
    CORPUS_CACHE_CAPACITY,
    CandidateMatchInput,
    CorpusArtifacts,
    CorpusCache,
    JobMatchInput,
    MatchingResult,
    candidate_terms,
    corpus_fingerprint,
    fit_corpus,
    job_terms,
    score_jobs,
)


@pytest.fixture(autouse=True)
def cold_cache() -> Any:
    """Every test starts cold and leaves nothing behind for the next one."""
    CORPUS_CACHE.clear()
    yield
    CORPUS_CACHE.clear()


def job(job_id: str, skills: tuple[str, ...] = (), title: str = "", description: str = "") -> JobMatchInput:
    return JobMatchInput(
        job_id=job_id, role_title=title, description=description, required_skills=skills
    )


def candidate(
    skills: tuple[str, ...] = (), texts: tuple[str, ...] = ()
) -> CandidateMatchInput:
    return CandidateMatchInput(skills=skills, experience_texts=texts)


CATALOGUE = [
    job("a", ("Python", "SQL"), "Backend Intern", "data pipelines and reporting"),
    job("b", ("React", "JavaScript"), "Frontend Intern", "interface work"),
    job("c", (), "Operations", "logistics and scheduling"),
]
ALICE = candidate(("Python", "SQL"), ("built data pipelines",))
BOB = candidate(("React",), ("interface work at a startup",))


def full_shape(result: MatchingResult) -> Any:
    """Everything a client can observe, in a comparable form."""
    return (
        result.matching_version,
        result.corpus_size,
        result.corpus_fingerprint,
        tuple(
            (
                m.job_id,
                m.match_score,
                m.score_basis,
                tuple((t.term, t.kind, t.contribution) for t in m.top_terms),
                m.skill_coverage,
                m.explanation,
            )
            for m in result.matches
        ),
    )


# ---------------------------------------------------------------------------------------
# 1 & 2. Cold and warm produce the same answer
# ---------------------------------------------------------------------------------------


def test_a_warm_result_is_identical_to_the_cold_one() -> None:
    cold = score_jobs(ALICE, CATALOGUE)
    assert len(CORPUS_CACHE) == 1, "the cold call must populate the cache"

    warm = score_jobs(ALICE, CATALOGUE)
    assert len(CORPUS_CACHE) == 1, "the warm call must not add an entry"

    assert warm == cold
    assert full_shape(warm) == full_shape(cold)


def test_warm_results_stay_identical_over_many_calls() -> None:
    baseline = full_shape(score_jobs(ALICE, CATALOGUE))
    for _ in range(25):
        assert full_shape(score_jobs(ALICE, CATALOGUE)) == baseline
    assert len(CORPUS_CACHE) == 1


def test_a_warm_cache_matches_a_never_cached_computation() -> None:
    """The strongest form: compare against the artifacts a fresh fit produces."""
    warm = score_jobs(ALICE, CATALOGUE)
    score_jobs(BOB, CATALOGUE)

    CORPUS_CACHE.clear()
    cold_again = score_jobs(ALICE, CATALOGUE)
    assert full_shape(warm) == full_shape(cold_again)


def test_every_observable_field_survives_a_cache_hit() -> None:
    cold = score_jobs(ALICE, CATALOGUE)
    warm = score_jobs(ALICE, CATALOGUE)
    for a, b in zip(cold.matches, warm.matches):
        assert a.match_score == b.match_score
        assert a.score_basis is b.score_basis
        assert a.top_terms == b.top_terms
        assert a.skill_coverage == b.skill_coverage
        assert a.explanation == b.explanation
    assert [m.job_id for m in cold.matches] == [m.job_id for m in warm.matches]
    assert cold.corpus_fingerprint == warm.corpus_fingerprint


def test_a_selected_subset_is_unaffected_by_warmth() -> None:
    """ADR-020: a job's score does not depend on which subset was asked for."""
    whole_cold = score_jobs(ALICE, CATALOGUE)
    subset_warm = score_jobs(ALICE, CATALOGUE, job_ids=["b"])
    assert subset_warm.matches[0] == next(m for m in whole_cold.matches if m.job_id == "b")
    assert subset_warm.corpus_fingerprint == whole_cold.corpus_fingerprint


def test_an_empty_vocabulary_catalogue_caches_and_replays_correctly() -> None:
    empty = [job("x"), job("y")]
    cold = score_jobs(candidate(("Python",)), empty)
    warm = score_jobs(candidate(("Python",)), empty)
    assert full_shape(cold) == full_shape(warm)
    assert all(m.match_score is None for m in warm.matches)


def test_an_empty_catalogue_caches_and_replays_correctly() -> None:
    cold = score_jobs(ALICE, [])
    warm = score_jobs(ALICE, [])
    assert full_shape(cold) == full_shape(warm)
    assert warm.matches == ()


def test_caller_errors_are_raised_on_a_warm_cache_too() -> None:
    score_jobs(ALICE, CATALOGUE)
    with pytest.raises(ValueError):
        score_jobs(ALICE, CATALOGUE, job_ids=["missing"])
    with pytest.raises(ValueError):
        score_jobs(ALICE, [job("a", ("Python",)), job("a", ("SQL",))])
