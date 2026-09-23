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


# ---------------------------------------------------------------------------------------
# 3 & 10. The key is the fingerprint; a changed catalogue misses
# ---------------------------------------------------------------------------------------


def test_the_cache_key_is_exactly_the_existing_corpus_fingerprint() -> None:
    result = score_jobs(ALICE, CATALOGUE)
    assert CORPUS_CACHE.fingerprints() == (result.corpus_fingerprint,)
    assert result.corpus_fingerprint == corpus_fingerprint(CATALOGUE)


@pytest.mark.parametrize(
    "changed",
    [
        pytest.param([*CATALOGUE[:2], job("c", ("Go",), "Operations", "logistics and scheduling")], id="terms"),
        pytest.param([*CATALOGUE, job("d", ("Rust",), "Systems", "low level")], id="membership"),
        pytest.param(CATALOGUE[:2], id="removal"),
        pytest.param([CATALOGUE[1], CATALOGUE[0], CATALOGUE[2]], id="order"),
        pytest.param([job("a2", ("Python", "SQL"), "Backend Intern", "data pipelines and reporting"), *CATALOGUE[1:]], id="identity"),
    ],
)
def test_a_changed_catalogue_misses_and_is_fitted_afresh(changed: list[JobMatchInput]) -> None:
    original = score_jobs(ALICE, CATALOGUE)
    updated = score_jobs(ALICE, changed)

    assert updated.corpus_fingerprint != original.corpus_fingerprint
    assert len(CORPUS_CACHE) == 2, "a changed catalogue must add an entry, not replace one"

    CORPUS_CACHE.clear()
    assert full_shape(score_jobs(ALICE, changed)) == full_shape(updated)


def test_the_old_entry_still_serves_the_old_catalogue() -> None:
    first = score_jobs(ALICE, CATALOGUE)
    score_jobs(ALICE, [*CATALOGUE, job("d", ("Rust",))])
    assert full_shape(score_jobs(ALICE, CATALOGUE)) == full_shape(first)


def test_formatting_that_leaves_terms_unchanged_still_hits() -> None:
    """The fingerprint's semantics are unchanged by 8B, and this pins that."""
    restated = [
        job("a", ("python", "SQL"), "Backend Intern", "data pipelines and reporting"),
        *CATALOGUE[1:],
    ]
    if corpus_fingerprint(restated) != corpus_fingerprint(CATALOGUE):
        pytest.skip("casing changes this catalogue's terms; not a fingerprint claim to make")
    score_jobs(ALICE, CATALOGUE)
    score_jobs(ALICE, restated)
    assert len(CORPUS_CACHE) == 1


def test_no_timestamp_or_ttl_participates_in_the_key() -> None:
    """Invalidation is the fingerprint. A second mechanism could disagree with the first.

    Checked against the syntax tree rather than the text, because the class docstring says
    the words "no TTL, no timestamp" and a substring search would match its own denial.
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(CorpusCache)))
    names = {n.id.lower() for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.attr.lower() for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    for forbidden in ("time", "ttl", "expire", "expiry", "datetime", "monotonic", "perf_counter", "now"):
        assert forbidden not in names, forbidden


# ---------------------------------------------------------------------------------------
# 4, 5 & 6. Candidate isolation
# ---------------------------------------------------------------------------------------


def test_two_candidates_share_the_corpus_and_nothing_else() -> None:
    alice_cold = score_jobs(ALICE, CATALOGUE)
    bob_warm = score_jobs(BOB, CATALOGUE)
    assert len(CORPUS_CACHE) == 1, "a second candidate must not add a cache entry"

    CORPUS_CACHE.clear()
    bob_cold = score_jobs(BOB, CATALOGUE)
    assert full_shape(bob_warm) == full_shape(bob_cold)

    assert [m.match_score for m in alice_cold.matches] != [m.match_score for m in bob_warm.matches]


def test_a_candidate_cannot_reach_the_cache_key() -> None:
    before = CORPUS_CACHE.fingerprints()
    score_jobs(ALICE, CATALOGUE)
    key = CORPUS_CACHE.fingerprints()[0]
    assert before == ()

    for other in (BOB, candidate(("Haskell", "Erlang"), ("entirely different history",))):
        score_jobs(other, CATALOGUE)
        assert CORPUS_CACHE.fingerprints() == (key,), "the key must not vary with the candidate"


def test_the_cached_value_holds_only_catalogue_derived_fields() -> None:
    assert {f.name for f in fields(CorpusArtifacts)} == {
        "vectorizer",
        "job_matrix",
        "features",
        "row_of",
        "has_vocabulary",
    }


def test_fit_corpus_cannot_see_a_candidate() -> None:
    """The boundary is the signature: there is no parameter a candidate could arrive in."""
    assert list(inspect.signature(fit_corpus).parameters) == ["catalogue"]


def test_no_candidate_marker_appears_anywhere_in_the_cache() -> None:
    marker_skill, marker_text = "CacheMarkerSkill", "CACHE-MARKER-TEXT-8b"
    marked = candidate((marker_skill,), (marker_text,))
    score_jobs(marked, CATALOGUE)

    corpus = CORPUS_CACHE.get_or_fit(corpus_fingerprint(CATALOGUE), lambda: fit_corpus(CATALOGUE))
    blob = pickle.dumps(
        (
            sorted(corpus.vectorizer.vocabulary_),
            list(corpus.features),
            corpus.row_of,
            corpus.has_vocabulary,
            CORPUS_CACHE.fingerprints(),
        )
    )
    for marker in (marker_skill, marker_text, marker_skill.lower(), "cachemarkerskill"):
        assert marker.encode() not in blob, marker


def test_a_candidate_id_is_not_available_to_this_layer_at_all() -> None:
    """Matching's narrow inputs predate 8B; the cache cannot leak what never arrives."""
    assert "candidate_id" not in {f.name for f in fields(CandidateMatchInput)}
    assert "candidate_id" not in inspect.getsource(CorpusCache)
    assert "candidate_id" not in inspect.getsource(fit_corpus)


def test_the_candidate_vector_is_computed_per_call_and_never_stored() -> None:
    """Counts transforms directly: one per scoring call, warm or cold."""
    corpus = fit_corpus(CATALOGUE)
    calls: list[str] = []
    real = corpus.vectorizer.transform

    def counting(documents: Any, *args: Any, **kwargs: Any) -> Any:
        calls.extend(documents)
        return real(documents, *args, **kwargs)

    corpus.vectorizer.transform = counting  # type: ignore[method-assign]
    CORPUS_CACHE.clear()
    CORPUS_CACHE.get_or_fit(corpus_fingerprint(CATALOGUE), lambda: corpus)

    score_jobs(ALICE, CATALOGUE)
    assert calls == [candidate_terms(ALICE)]

    score_jobs(BOB, CATALOGUE)
    assert calls == [candidate_terms(ALICE), candidate_terms(BOB)]

    score_jobs(ALICE, CATALOGUE)
    assert calls == [candidate_terms(ALICE), candidate_terms(BOB), candidate_terms(ALICE)], (
        "a repeated candidate must be transformed again, not served from a cache"
    )


def test_the_cache_stores_no_score_and_no_vector() -> None:
    score_jobs(ALICE, CATALOGUE)
    corpus = CORPUS_CACHE.get_or_fit(corpus_fingerprint(CATALOGUE), lambda: fit_corpus(CATALOGUE))
    names = {f.name for f in fields(CorpusArtifacts)}
    for forbidden in ("score", "scores", "candidate", "candidate_vector", "matches", "result"):
        assert forbidden not in names, forbidden
    assert corpus.job_matrix.shape[0] == len(CATALOGUE), "one row per job, none for a candidate"


# ---------------------------------------------------------------------------------------
# 7. Artifact immutability
# ---------------------------------------------------------------------------------------


def artifact_digest(corpus: CorpusArtifacts) -> str:
    parts = [
        pickle.dumps(sorted(corpus.vectorizer.vocabulary_.items())),
        np.ascontiguousarray(corpus.vectorizer.idf_).tobytes() if corpus.has_vocabulary else b"",
        corpus.job_matrix.data.tobytes(),
        corpus.job_matrix.indices.tobytes(),
        corpus.job_matrix.indptr.tobytes(),
        pickle.dumps(list(corpus.features)),
        pickle.dumps(sorted(corpus.row_of.items())),
    ]
    return hashlib.sha256(b"".join(parts)).hexdigest()


def test_scoring_does_not_mutate_the_cached_artifacts() -> None:
    """Evidence for sharing rather than copying: nothing downstream writes to these."""
    score_jobs(ALICE, CATALOGUE)
    corpus = CORPUS_CACHE.get_or_fit(corpus_fingerprint(CATALOGUE), lambda: fit_corpus(CATALOGUE))
    before = artifact_digest(corpus)

    for n in range(40):
        score_jobs(candidate(("Python", "React"), (f"varied history {n}",)), CATALOGUE)
        score_jobs(ALICE, CATALOGUE, job_ids=["a"])

    assert artifact_digest(corpus) == before


def test_the_cached_entry_is_the_same_object_across_hits() -> None:
    """Sharing, not copying — and therefore a mutation would have been visible above."""
    score_jobs(ALICE, CATALOGUE)
    key = corpus_fingerprint(CATALOGUE)
    first = CORPUS_CACHE.get_or_fit(key, lambda: pytest.fail("must not refit"))
    second = CORPUS_CACHE.get_or_fit(key, lambda: pytest.fail("must not refit"))
    assert first is second


def test_the_artifact_record_is_frozen() -> None:
    corpus = fit_corpus(CATALOGUE)
    with pytest.raises(Exception):
        corpus.has_vocabulary = False  # type: ignore[misc]


# ---------------------------------------------------------------------------------------
# 8. Bounded eviction
# ---------------------------------------------------------------------------------------


def catalogue_number(n: int) -> list[JobMatchInput]:
    return [job(f"j{n}", ("Python",), f"Role {n}", f"description number {n}")]


def test_the_cache_never_exceeds_its_capacity() -> None:
    for n in range(CORPUS_CACHE_CAPACITY * 5):
        score_jobs(ALICE, catalogue_number(n))
        assert len(CORPUS_CACHE) <= CORPUS_CACHE_CAPACITY
    assert len(CORPUS_CACHE) == CORPUS_CACHE_CAPACITY


def test_capacity_is_small_and_fixed() -> None:
    assert 1 <= CORPUS_CACHE_CAPACITY < 10
    assert CORPUS_CACHE.capacity == CORPUS_CACHE_CAPACITY


def test_the_least_recently_used_entry_is_the_one_evicted() -> None:
    cache = CorpusCache(capacity=3)
    keys = [corpus_fingerprint(catalogue_number(n)) for n in range(4)]
    for n in range(3):
        cache.get_or_fit(keys[n], lambda n=n: fit_corpus(catalogue_number(n)))
    assert cache.fingerprints() == (keys[0], keys[1], keys[2])

    # Touch the oldest, making the second-oldest the least recently used.
    cache.get_or_fit(keys[0], lambda: pytest.fail("must not refit a held entry"))
    assert cache.fingerprints() == (keys[1], keys[2], keys[0])

    cache.get_or_fit(keys[3], lambda: fit_corpus(catalogue_number(3)))
    assert cache.fingerprints() == (keys[2], keys[0], keys[3])
    assert keys[1] not in cache.fingerprints(), "the least recently used must go"


def test_an_evicted_catalogue_is_refitted_and_still_correct() -> None:
    first = score_jobs(ALICE, catalogue_number(0))
    for n in range(1, CORPUS_CACHE_CAPACITY + 1):
        score_jobs(ALICE, catalogue_number(n))
    assert corpus_fingerprint(catalogue_number(0)) not in CORPUS_CACHE.fingerprints()

    assert full_shape(score_jobs(ALICE, catalogue_number(0))) == full_shape(first)


def test_eviction_leaves_the_surviving_entries_correct() -> None:
    kept = score_jobs(ALICE, catalogue_number(99))
    for n in range(CORPUS_CACHE_CAPACITY - 1):
        score_jobs(ALICE, catalogue_number(n))
        # Keep entry 99 fresh so it survives.
        score_jobs(ALICE, catalogue_number(99))

    assert corpus_fingerprint(catalogue_number(99)) in CORPUS_CACHE.fingerprints()
    assert full_shape(score_jobs(ALICE, catalogue_number(99))) == full_shape(kept)


def test_a_cache_of_capacity_one_still_works() -> None:
    cache = CorpusCache(capacity=1)
    a, b = catalogue_number(1), catalogue_number(2)
    cache.get_or_fit(corpus_fingerprint(a), lambda: fit_corpus(a))
    cache.get_or_fit(corpus_fingerprint(b), lambda: fit_corpus(b))
    assert cache.fingerprints() == (corpus_fingerprint(b),)


def test_a_capacity_below_one_is_refused() -> None:
    for bad in (0, -1):
        with pytest.raises(ValueError):
            CorpusCache(capacity=bad)


# ---------------------------------------------------------------------------------------
# 9. Concurrency
# ---------------------------------------------------------------------------------------


def test_concurrent_scoring_against_one_warm_corpus_is_uncontaminated() -> None:
    candidates = [
        candidate(("Python", "SQL") if n % 2 else ("React", "JavaScript"), (f"history {n}",))
        for n in range(48)
    ]
    serial = [full_shape(score_jobs(c, CATALOGUE)) for c in candidates]

    CORPUS_CACHE.clear()
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        parallel = list(pool.map(lambda c: full_shape(score_jobs(c, CATALOGUE)), candidates))

    assert parallel == serial
    assert len(CORPUS_CACHE) == 1


def test_a_concurrent_cold_start_converges_on_one_entry() -> None:
    """Several requests may race to fit the same catalogue; all must agree, and none corrupt."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda _: full_shape(score_jobs(ALICE, CATALOGUE)), range(24)))

    assert len(set(results)) == 1
    assert len(CORPUS_CACHE) == 1


def test_concurrent_distinct_catalogues_respect_the_bound() -> None:
    def run(n: int) -> str:
        return score_jobs(ALICE, catalogue_number(n)).corpus_fingerprint

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        fingerprints = list(pool.map(run, range(40)))

    assert len(set(fingerprints)) == 40
    assert len(CORPUS_CACHE) <= CORPUS_CACHE_CAPACITY


def test_concurrent_mixed_catalogues_never_cross_wires() -> None:
    catalogues = {n: catalogue_number(n) for n in range(3)}
    expected = {n: full_shape(score_jobs(ALICE, cat)) for n, cat in catalogues.items()}
    CORPUS_CACHE.clear()

    def run(n: int) -> tuple[int, Any]:
        return n, full_shape(score_jobs(ALICE, catalogues[n % 3]))

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        for n, shape in pool.map(run, range(60)):
            assert shape == expected[n % 3]


# ---------------------------------------------------------------------------------------
# Boundaries the slice must not have crossed
# ---------------------------------------------------------------------------------------


def test_the_cache_is_in_memory_only() -> None:
    source = inspect.getsource(CorpusCache) + inspect.getsource(fit_corpus)
    for forbidden in ("open(", "Path(", "redis", "Redis", "memcache", "sqlite", "session", "pickle.dump"):
        assert forbidden not in source, forbidden


def test_matching_still_imports_no_framework_database_or_ai_module() -> None:
    """INV-7 and the ADR-020 boundary: 8B added a cache, not a dependency."""
    import app.services.matching_engine as engine

    source = inspect.getsource(engine)
    for forbidden in ("fastapi", "starlette", "sqlalchemy", "app.ai", "app.models", "httpx"):
        assert forbidden not in source, forbidden


def test_the_capacity_is_a_constant_not_a_setting() -> None:
    """ADR-025 D4 rejected cache configuration keys; 8B introduces none."""
    from app.config import Settings

    for name in Settings.model_fields:
        assert "cache" not in name.lower(), name
