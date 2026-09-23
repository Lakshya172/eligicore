"""Deterministic matching engine — relevance, not eligibility.

**Matching is not eligibility.** This module answers "how relevant is this job to what the
candidate has done?" It never reads or produces an eligibility state, never sees a grade, a
graduation year, a backlog count, a degree or a permitted field, and nothing it computes can
make a job eligible or ineligible. Eligibility is :mod:`app.services.eligibility_engine`; the
two are combined only by a caller that consumes both (dossier §12.2, ADR-006).

Pure business logic (INV-7). No FastAPI, no database, no AI, no I/O and no logging: every value
here is derived from candidate data, and a pure function has nothing to log.

**One thing is cached, and only one** (ADR-026 D7, partially superseding ADR-020 §5). The fitted
corpus — vectorizer, job matrix, feature names and row mapping — is derived from the catalogue
alone and is held in a small bounded in-memory cache keyed by :func:`corpus_fingerprint`. The
candidate is **transformed, never fitted**, and that transform runs per call and is never stored:
the fit is cached, the candidate's vector is not. No candidate value reaches the cache key or the
cached value, nothing is written to disk or a database, and results are identical whether an entry
was hit, missed or evicted.

The algorithm is fixed by ADR-020 (match scoring) and ADR-021 (skill comparison):

1. **Narrow inputs.** :func:`candidate_match_input` is the only function that reads a
   :class:`CandidateProfile`, and it keeps skills plus experience titles and descriptions.
   :func:`job_match_input` keeps a job's id, role title, description and required skills.
2. **Two term namespaces.** A skill becomes one term, ``skill:<comparison key>``; prose becomes
   plain word tokens. A skill never collides with a word: prose "go" is not ``skill:go``.
3. **TF-IDF fitted on the whole catalogue**, once per call, never on the candidate. A job's
   score therefore does not depend on which other jobs a caller happens to ask about.
4. **Cosine similarity** of the L2-normalized candidate and job vectors, reported as
   ``round(clamp(100 * cosine, 0, 100), 1)`` — or ``None`` when either vector is empty,
   because absence of evidence is not evidence of a mismatch.
5. **Skill coverage** is computed separately and never folded into the score.
6. **Explanations** are templates filled from those computed values. No model writes them.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from collections import OrderedDict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from enum import Enum

import numpy as np
from scipy.sparse import csr_matrix
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer

from app.schemas.candidate import CandidateProfile
from app.schemas.job import JobRead
from app.services.candidate_normalizer import skill_comparison_key

#: Version of the matching algorithm. A client holding stored scores can recompute when this
#: changes, exactly as ``engine_version`` works for eligibility (ADR-020).
MATCHING_VERSION = "1"

#: At most this many shared terms are reported as the evidence behind a score.
MAX_TOP_TERMS = 5

#: Prefix of every skill term. Prose tokens are built from ``[\w+#]`` and can never contain
#: the colon, so no word can be mistaken for a skill.
SKILL_TERM_PREFIX = "skill:"

#: A candidate text token: a maximal run of word characters, ``+`` and ``#``. ``+`` and ``#``
#: are kept so "c++" and "c#" survive as tokens. sklearn's default pattern ``\b\w\w+\b`` is
#: deliberately not used: it drops "c", "r", "c++" and "c#" entirely (ADR-020).
_TEXT_TOKEN = re.compile(r"[\w+#]+")

#: Symbols meaningful only as a suffix ("c++", "c#"). Leading ones ("#python") are trimmed.
_LEADING_TOKEN_SYMBOLS = "+#_"


class ScoreBasis(str, Enum):
    """Why a job has, or does not have, a score."""

    SCORED = "SCORED"
    #: The candidate contributes no skill or experience term found in the catalogue vocabulary.
    NO_CANDIDATE_TERMS = "NO_CANDIDATE_TERMS"
    #: The job — or the whole catalogue — has no usable skill, title or description term.
    NO_JOB_TERMS = "NO_JOB_TERMS"


class TermKind(str, Enum):
    """Which namespace a shared term belongs to."""

    SKILL = "skill"
    TEXT = "text"


# ---------------------------------------------------------------------------------------
# Narrow inputs
# ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class CandidateMatchInput:
    """Everything matching may know about a candidate — and nothing else.

    Skills, and the titles and descriptions of experience entries. No identity, contact,
    education, grade, backlog, preference, project, certification or resume text.
    """

    skills: tuple[str, ...]
    experience_texts: tuple[str, ...]


@dataclass(frozen=True)
class JobMatchInput:
    """The public job fields matching uses. Eligibility criteria are not among them."""

    job_id: str
    role_title: str
    description: str
    required_skills: tuple[str, ...]


def candidate_match_input(profile: CandidateProfile) -> CandidateMatchInput:
    """Narrow a profile to the matching input.

    The only function in this module that receives a :class:`CandidateProfile`. Reads
    ``skills`` and each experience entry's ``title`` and ``description``; company and duration
    are skipped, and every other profile field is never read.
    """
    texts: list[str] = []
    for entry in profile.experience:
        texts.append(entry.title)
        if entry.description:
            texts.append(entry.description)
    return CandidateMatchInput(skills=tuple(profile.skills), experience_texts=tuple(texts))


def job_match_input(job: JobRead) -> JobMatchInput:
    """Narrow a catalogue job to the matching input."""
    return JobMatchInput(
        job_id=job.id,
        role_title=job.role_title,
        description=job.description,
        required_skills=tuple(job.required_skills),
    )


# ---------------------------------------------------------------------------------------
# Skills (ADR-021)
# ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SkillEntry:
    """One distinct skill: its comparison key and the display name it was listed under."""

    key: str
    display: str


def skill_entries(skills: Iterable[str]) -> tuple[SkillEntry, ...]:
    """Distinct skills by comparison key, first occurrence wins, blanks dropped.

    The alias table applies here, through :func:`skill_comparison_key` — to skill lists only,
    never to prose. A composite entry such as "CI/CD" is one skill and is never split.
    """
    seen: set[str] = set()
    entries: list[SkillEntry] = []
    for raw in skills:
        key = skill_comparison_key(raw)
        if not key or key in seen:
            continue
        seen.add(key)
        entries.append(SkillEntry(key=key, display=" ".join(raw.split())))
    return tuple(entries)


def skill_term(key: str) -> str:
    """The TF-IDF term for a skill comparison key."""
    return f"{SKILL_TERM_PREFIX}{key}"


@dataclass(frozen=True)
class SkillCoverage:
    """Which of a job's required skills the candidate lists.

    Display names are the job's, in the job's order. Counts only — there is deliberately no
    percentage and no coverage score (ADR-020).
    """

    matched_required_skills: tuple[str, ...]
    missing_required_skills: tuple[str, ...]
    required_skill_count: int

    @property
    def none_listed(self) -> bool:
        """True when the job lists no required skills — neither 0% nor 100% coverage."""
        return self.required_skill_count == 0


def skill_coverage(
    candidate_skills: Iterable[str], required_skills: Iterable[str]
) -> SkillCoverage:
    """Compare required skills against candidate skills by comparison key."""
    candidate_keys = {entry.key for entry in skill_entries(candidate_skills)}
    required = skill_entries(required_skills)
    return SkillCoverage(
        matched_required_skills=tuple(e.display for e in required if e.key in candidate_keys),
        missing_required_skills=tuple(
            e.display for e in required if e.key not in candidate_keys
        ),
        required_skill_count=len(required),
    )


# ---------------------------------------------------------------------------------------
# Terms (ADR-020)
# ---------------------------------------------------------------------------------------


def text_tokens(text: str | None) -> list[str]:
    """Tokenize prose into literal, case-folded text terms.

    Keeps ``+`` and ``#`` inside and after a token, trims them from its start, and drops
    tokens with no letter (pure numbers), single-character tokens and sklearn's
    ``ENGLISH_STOP_WORDS``. No stemming, and no skill aliasing: prose "js" stays "js".
    """
    if not text:
        return []
    tokens: list[str] = []
    for raw in _TEXT_TOKEN.findall(text.casefold()):
        token = raw.lstrip(_LEADING_TOKEN_SYMBOLS)
        if len(token) < 2:
            continue
        if not any(character.isalpha() for character in token):
            continue
        if token in ENGLISH_STOP_WORDS:
            continue
        tokens.append(token)
    return tokens


def candidate_terms(candidate: CandidateMatchInput) -> list[str]:
    """The candidate query: one term per distinct skill, then experience text tokens."""
    terms = [skill_term(entry.key) for entry in skill_entries(candidate.skills)]
    for text in candidate.experience_texts:
        terms.extend(text_tokens(text))
    return terms


def job_terms(job: JobMatchInput) -> list[str]:
    """A job document: one term per distinct required skill, then title and description."""
    terms = [skill_term(entry.key) for entry in skill_entries(job.required_skills)]
    terms.extend(text_tokens(job.role_title))
    terms.extend(text_tokens(job.description))
    return terms


def _terms_as_given(terms: list[str]) -> list[str]:
    """Analyzer for pre-built term lists: the tokenization already happened."""
    return list(terms)


def build_vectorizer() -> TfidfVectorizer:
    """A fresh vectorizer with the ADR-020 configuration.

    With ``smooth_idf=True``: ``idf(t) = ln((1 + N) / (1 + df(t))) + 1``, where N is the
    number of catalogue documents.
    """
    return TfidfVectorizer(
        analyzer=_terms_as_given,
        lowercase=False,
        token_pattern=None,
        ngram_range=(1, 1),
        min_df=1,
        max_df=1.0,
        use_idf=True,
        smooth_idf=True,
        sublinear_tf=False,
        norm="l2",
        dtype=np.float64,
    )


# ---------------------------------------------------------------------------------------
# Scores
# ---------------------------------------------------------------------------------------


def normalize_score(cosine: float) -> float:
    """Report a cosine as a 0–100 score with one decimal place.

    Clamped first, so float error such as 1.0000000000000002 cannot exceed the range.
    """
    return round(min(max(100.0 * cosine, 0.0), 100.0), 1)


def cosine_similarity(candidate_vector: csr_matrix, job_vector: csr_matrix) -> float | None:
    """Cosine of two L2-normalized row vectors, or ``None`` when either is a zero vector.

    Both vectors are unit length, so the cosine is their dot product.
    """
    if candidate_vector.nnz == 0 or job_vector.nnz == 0:
        return None
    return float(candidate_vector.multiply(job_vector).sum())


@dataclass(frozen=True)
class TopTerm:
    """A term both sides share, and how much it contributed to the cosine."""

    term: str
    kind: TermKind
    contribution: float


def top_terms(
    candidate_vector: csr_matrix,
    job_vector: csr_matrix,
    features: Sequence[str],
    skill_displays: dict[str, str],
    limit: int = MAX_TOP_TERMS,
) -> tuple[TopTerm, ...]:
    """The shared terms with the largest ``candidate_component * job_component``.

    Only positive contributions, so every term reported is present in both vectors. Ordered
    by contribution descending, then by term name ascending. A skill term is shown under the
    job's display name; a text term as its literal token.
    """
    product = candidate_vector.multiply(job_vector).tocsr()
    shared = [
        (float(value), str(features[index]))
        for index, value in zip(product.indices, product.data)
        if value > 0
    ]
    shared.sort(key=lambda item: (-item[0], item[1]))

    terms: list[TopTerm] = []
    for contribution, feature in shared[:limit]:
        if feature.startswith(SKILL_TERM_PREFIX):
            key = feature[len(SKILL_TERM_PREFIX) :]
            terms.append(TopTerm(skill_displays[key], TermKind.SKILL, contribution))
        else:
            terms.append(TopTerm(feature, TermKind.TEXT, contribution))
    return tuple(terms)


# ---------------------------------------------------------------------------------------
# Explanations
# ---------------------------------------------------------------------------------------


def build_explanation(
    coverage: SkillCoverage,
    match_score: float | None,
    score_basis: ScoreBasis,
    shared_terms: Sequence[TopTerm],
) -> str:
    """Describe the evidence behind a match. Never a judgement about the candidate.

    Every name in the text is a job-side skill or a term present in the job, so the
    explanation repeats nothing the candidate supplied that the job does not also contain.
    """
    if coverage.none_listed:
        coverage_text = "This job lists no required skills."
    else:
        count = coverage.required_skill_count
        coverage_text = (
            f"Matches {len(coverage.matched_required_skills)} of {count} required "
            f"{'skill' if count == 1 else 'skills'} listed"
        )
        if coverage.matched_required_skills:
            coverage_text += f" ({', '.join(coverage.matched_required_skills)})"
        if coverage.missing_required_skills:
            coverage_text += f"; missing: {', '.join(coverage.missing_required_skills)}"
        coverage_text += "."

    if score_basis is ScoreBasis.SCORED and match_score is not None:
        score_text = f"Similarity {match_score:.1f} of 100"
        if shared_terms:
            score_text += f", from shared terms: {', '.join(t.term for t in shared_terms)}."
        else:
            score_text += ", with no shared terms."
    elif score_basis is ScoreBasis.NO_CANDIDATE_TERMS:
        score_text = (
            "No similarity score: the profile supplies no skill or experience terms that "
            "appear in the job catalogue."
        )
    else:
        score_text = (
            "No similarity score: this job has no skill, title or description terms to "
            "compare."
        )

    return f"{coverage_text} {score_text}"


# ---------------------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class JobMatch:
    """The matching evidence for one job. Carries no eligibility information."""

    job_id: str
    match_score: float | None
    score_basis: ScoreBasis
    top_terms: tuple[TopTerm, ...]
    skill_coverage: SkillCoverage
    explanation: str


@dataclass(frozen=True)
class MatchingResult:
    """Matches for the selected jobs, in selection order, and the corpus they were scored in."""

    matching_version: str
    corpus_size: int
    #: SHA-256 of the corpus as matching saw it (:func:`corpus_fingerprint`). Candidate-free.
    corpus_fingerprint: str
    matches: tuple[JobMatch, ...]


def corpus_fingerprint(catalogue: Sequence[JobMatchInput]) -> str:
    """Identify the TF-IDF corpus, so a client can tell when a stored score was computed
    against a different catalogue (ADR-020 §5).

    SHA-256 of a canonical JSON array holding, for each catalogue job **in the order given**,
    its id and its matching terms (:func:`job_terms`). JSON quoting makes the encoding
    unambiguous and independent of Python ``repr``; nothing about the candidate is read.
    Same catalogue in the same order gives the same fingerprint; changed matching content,
    membership or order gives a different one.
    """
    canonical = json.dumps(
        [[job.job_id, job_terms(job)] for job in catalogue],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()



#: How many fitted corpora to keep. Deliberately small: in practice one catalogue is scored
#: over and over, and a handful of entries covers a catalogue edit or a test suite moving
#: between fixtures. A module constant rather than configuration — ADR-025 D4 rejected cache
#: configuration keys, and a setting here would be a lever for widening a bounded cache into
#: an unbounded one.
CORPUS_CACHE_CAPACITY = 4


@dataclass(frozen=True)
class CorpusArtifacts:
    """The fitted corpus: everything derived from the catalogue, and nothing else.

    Every field is a function of the catalogue alone, which is what makes this cacheable at
    all. There is no candidate field here and no parameter through which one could arrive —
    the candidate's vector is built by the caller, per call, and never stored (ADR-026 D7).

    Treated as **immutable**. Downstream scoring only reads: it slices a row from
    ``job_matrix``, multiplies two vectors into a new one, sums, and indexes ``features``.
    Verified against scikit-learn 1.7.2 — a fitted vectorizer's ``transform`` leaves
    ``vocabulary_``, ``idf_`` and the matrix byte-identical, including under concurrent
    calls — so entries are shared rather than copied. Copying without that evidence would be
    cargo cult; mutating one would be a defect, and a test pins that nothing does.
    """

    vectorizer: TfidfVectorizer
    job_matrix: csr_matrix
    features: Sequence[str]
    row_of: dict[str, int]
    has_vocabulary: bool


class CorpusCache:
    """A bounded LRU of fitted corpora, keyed by corpus fingerprint.

    Process-local and in-memory. No disk, no database, no external cache service and no new
    dependency — an `OrderedDict` and a lock (ADR-026 D7).

    **Invalidation is the key.** A catalogue whose membership, order or matching terms change
    produces a different fingerprint and therefore a different entry; a stale fit cannot be
    served because it cannot be addressed. There is no TTL, no timestamp and no manual
    invalidation call, because each of those would be a second mechanism that could disagree
    with the first.

    The lock guards the mapping, not the fit. Two requests that miss the same key
    concurrently may both fit; that wastes work once and is otherwise harmless, because the
    fit is deterministic and the two results are identical. Holding the lock across a fit
    would make one catalogue's first request block every other catalogue's.
    """

    def __init__(self, capacity: int = CORPUS_CACHE_CAPACITY) -> None:
        if capacity < 1:
            raise ValueError("corpus cache capacity must be at least 1")
        self._capacity = capacity
        self._entries: OrderedDict[str, CorpusArtifacts] = OrderedDict()
        self._lock = threading.Lock()

    @property
    def capacity(self) -> int:
        return self._capacity

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def fingerprints(self) -> tuple[str, ...]:
        """Cached keys, least recently used first. For tests and diagnostics."""
        with self._lock:
            return tuple(self._entries)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def get_or_fit(
        self, fingerprint: str, fit: Callable[[], CorpusArtifacts]
    ) -> CorpusArtifacts:
        """Return the fitted corpus for ``fingerprint``, fitting it if it is not held."""
        with self._lock:
            found = self._entries.get(fingerprint)
            if found is not None:
                self._entries.move_to_end(fingerprint)
                return found

        built = fit()

        with self._lock:
            self._entries[fingerprint] = built
            self._entries.move_to_end(fingerprint)
            while len(self._entries) > self._capacity:
                self._entries.popitem(last=False)
        return built


#: The process-wide cache. One catalogue is scored repeatedly, so the hit rate is the point.
CORPUS_CACHE = CorpusCache()


def fit_corpus(catalogue: Sequence[JobMatchInput]) -> CorpusArtifacts:
    """Fit TF-IDF over the whole catalogue.

    Exactly the work ``score_jobs`` did inline before Slice 8B, moved out so it can be cached
    and so a test can compare a cached corpus against a freshly fitted one. The candidate is
    not a parameter here, which is the boundary: nothing candidate-derived can enter a
    cached value because nothing candidate-derived is in scope (ADR-020 §5, ADR-026 D7).
    """
    job_documents = [job_terms(job) for job in catalogue]
    row_of = {job.job_id: row for row, job in enumerate(catalogue)}
    has_vocabulary = any(job_documents)

    if not has_vocabulary:
        return CorpusArtifacts(
            vectorizer=build_vectorizer(),
            job_matrix=csr_matrix((len(catalogue), 0)),
            features=(),
            row_of=row_of,
            has_vocabulary=False,
        )

    vectorizer = build_vectorizer()
    job_matrix = vectorizer.fit_transform(job_documents).tocsr()
    return CorpusArtifacts(
        vectorizer=vectorizer,
        job_matrix=job_matrix,
        features=vectorizer.get_feature_names_out(),
        row_of=row_of,
        has_vocabulary=True,
    )


def score_jobs(
    candidate: CandidateMatchInput,
    catalogue: Sequence[JobMatchInput],
    job_ids: Sequence[str] | None = None,
) -> MatchingResult:
    """Score the candidate against selected catalogue jobs.

    TF-IDF is fitted on **every** catalogue job and never on the candidate, so a job scores
    the same whichever subset ``job_ids`` selects. ``job_ids`` defaults to the whole catalogue;
    repeated ids are scored once, in first-seen order.

    Raises ``ValueError`` for a catalogue with repeated job ids, or a selected id the
    catalogue does not hold — both are caller errors, not candidate data problems.
    """
    jobs_by_id: dict[str, JobMatchInput] = {}
    for job in catalogue:
        if job.job_id in jobs_by_id:
            raise ValueError("catalogue contains a repeated job id")
        jobs_by_id[job.job_id] = job

    selected = (
        list(dict.fromkeys(job_ids)) if job_ids is not None else list(jobs_by_id)
    )
    if any(job_id not in jobs_by_id for job_id in selected):
        raise ValueError("a selected job id is not in the catalogue")

    # Computed once and used twice: as the cache key, and as the result's fingerprint. The
    # same value must do both, or a cached corpus could be reported under a different
    # identity than the one it was stored under.
    fingerprint = corpus_fingerprint(catalogue)
    corpus = CORPUS_CACHE.get_or_fit(fingerprint, lambda: fit_corpus(catalogue))

    row_of = corpus.row_of
    has_vocabulary = corpus.has_vocabulary

    if has_vocabulary:
        job_matrix = corpus.job_matrix
        features = corpus.features
        # **Per call, never cached.** The candidate is transformed against the catalogue's
        # vocabulary and the result is local to this request: two candidates scored against
        # one warm corpus share the fit and share nothing else (ADR-020 §5, ADR-026 D7).
        candidate_vector = corpus.vectorizer.transform([candidate_terms(candidate)]).tocsr()

    matches: list[JobMatch] = []
    for job_id in selected:
        job = jobs_by_id[job_id]
        coverage = skill_coverage(candidate.skills, job.required_skills)
        score: float | None = None
        shared: tuple[TopTerm, ...] = ()

        if not has_vocabulary:
            basis = ScoreBasis.NO_JOB_TERMS
        else:
            job_vector = job_matrix[row_of[job_id]]
            cosine = cosine_similarity(candidate_vector, job_vector)
            if cosine is None:
                # A job with no terms is reported as such even when the candidate has none
                # either: that is the job-specific fact.
                basis = (
                    ScoreBasis.NO_JOB_TERMS
                    if job_vector.nnz == 0
                    else ScoreBasis.NO_CANDIDATE_TERMS
                )
            else:
                basis = ScoreBasis.SCORED
                score = normalize_score(cosine)
                displays = {e.key: e.display for e in skill_entries(job.required_skills)}
                shared = top_terms(candidate_vector, job_vector, features, displays)

        matches.append(
            JobMatch(
                job_id=job_id,
                match_score=score,
                score_basis=basis,
                top_terms=shared,
                skill_coverage=coverage,
                explanation=build_explanation(coverage, score, basis, shared),
            )
        )

    return MatchingResult(
        matching_version=MATCHING_VERSION,
        corpus_size=len(catalogue),
        corpus_fingerprint=fingerprint,
        matches=tuple(matches),
    )


# ---------------------------------------------------------------------------------------
# Ordering
# ---------------------------------------------------------------------------------------


def match_order_key(match: JobMatch) -> tuple[bool, float, str]:
    """Sort key: rounded score descending, unscored jobs last, then job id ascending.

    Uses the rounded score a caller displays, so any order is explainable from the output.
    There is no other weighting — no skill count, no eligibility, no combined score.
    """
    score = match.match_score
    return (score is None, -score if score is not None else 0.0, match.job_id)


def order_matches(matches: Iterable[JobMatch]) -> list[JobMatch]:
    """Matches in ranking order (see :func:`match_order_key`)."""
    return sorted(matches, key=match_order_key)
