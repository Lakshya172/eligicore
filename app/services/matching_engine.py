"""Deterministic matching engine — relevance, not eligibility.

**Matching is not eligibility.** This module answers "how relevant is this job to what the
candidate has done?" It never reads or produces an eligibility state, never sees a grade, a
graduation year, a backlog count, a degree or a permitted field, and nothing it computes can
make a job eligible or ineligible. Eligibility is :mod:`app.services.eligibility_engine`; the
two are combined only by a caller that consumes both (dossier §12.2, ADR-006).

Pure business logic (INV-7). No FastAPI, no database, no AI, no I/O and no logging: every value
here is derived from candidate data, and a pure function has nothing to log. Nothing is cached
or persisted — the vectorizer, vocabulary, IDF values, vectors and scores exist for one call.

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

import re
from collections.abc import Iterable, Sequence
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
    """Matches for the selected jobs, in selection order, and the size of their corpus."""

    matching_version: str
    corpus_size: int
    matches: tuple[JobMatch, ...]


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

    job_documents = [job_terms(job) for job in catalogue]
    row_of = {job.job_id: row for row, job in enumerate(catalogue)}
    has_vocabulary = any(job_documents)

    if has_vocabulary:
        vectorizer = build_vectorizer()
        job_matrix = vectorizer.fit_transform(job_documents).tocsr()
        features = vectorizer.get_feature_names_out()
        candidate_vector = vectorizer.transform([candidate_terms(candidate)]).tocsr()

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
