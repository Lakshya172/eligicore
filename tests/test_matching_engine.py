"""Matching engine tests (PR 5A — ADR-020, ADR-021).

Unit tests against the pure service: no server, no database, no AI provider. That the whole
module is testable this way is itself the INV-7 check.

Fixtures are obviously synthetic.
"""

from __future__ import annotations

import ast
import logging
import math
import os
import pathlib
import re
from datetime import datetime, timezone

import pytest
import sklearn
from scipy.sparse import csr_matrix
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

from app.database import Base
from app.schemas.candidate import CandidateProfile
from app.schemas.job import JobRead
from app.services import matching_engine as engine
from app.services.matching_engine import (
    MATCHING_VERSION,
    MAX_TOP_TERMS,
    CandidateMatchInput,
    JobMatch,
    JobMatchInput,
    ScoreBasis,
    SkillCoverage,
    TermKind,
    TopTerm,
    build_explanation,
    build_vectorizer,
    candidate_match_input,
    candidate_terms,
    cosine_similarity,
    job_match_input,
    job_terms,
    match_order_key,
    normalize_score,
    order_matches,
    score_jobs,
    skill_coverage,
    skill_entries,
    text_tokens,
)
from tests.conftest import ALLOWED_OPERATIONAL_TABLES

ENGINE_PATH = pathlib.Path(engine.__file__)


def job(
    job_id: str,
    skills: tuple[str, ...] = (),
    title: str = "",
    description: str = "",
) -> JobMatchInput:
    return JobMatchInput(
        job_id=job_id, role_title=title, description=description, required_skills=skills
    )


def candidate(skills: tuple[str, ...] = (), texts: tuple[str, ...] = ()) -> CandidateMatchInput:
    return CandidateMatchInput(skills=skills, experience_texts=texts)


def match_for(result, job_id: str) -> JobMatch:
    return next(m for m in result.matches if m.job_id == job_id)


# ---------------------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------------------


def test_installed_scikit_learn_matches_the_pin() -> None:
    """Stopwords and TF-IDF behaviour are reproducible only if the pinned version is the one run."""
    requirements = pathlib.Path("requirements.txt").read_text(encoding="utf-8")
    pinned = re.search(r"^scikit-learn==(\S+)$", requirements, re.MULTILINE)
    assert pinned is not None, "scikit-learn must be pinned with =="
    assert sklearn.__version__ == pinned.group(1)


def test_building_the_vectorizer_emits_no_unused_parameter_warning() -> None:
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        build_vectorizer().fit([["skill:python", "backend"]])


# ---------------------------------------------------------------------------------------
# Narrow inputs — privacy by signature
# ---------------------------------------------------------------------------------------

MARKERS = {
    "candidate_id": "MARKER-ID-7731",
    "name": "Marker Name Zebulon",
    "email": "marker.zebulon@example.com",
    "phone": "MARKER-PHONE-5550100",
    "location": "Markerville",
    "company": "Markercorp Holdings",
    "duration": "MARKER-DURATION",
    "degree": "MARKER-DEGREE",
    "field_of_study": "Markerology",
    "institution": "Marker Institute",
    "language": "Markerese",
    "project": "Marker Project Quasar",
    "project_description": "markerprojectdescription",
    "certification": "Marker Certification",
    "resume": "markerresumetext",
    "preference_location": "Markerpref City",
}


def marker_profile() -> CandidateProfile:
    return CandidateProfile.model_validate(
        {
            "candidate_id": MARKERS["candidate_id"],
            "name": MARKERS["name"],
            "email": MARKERS["email"],
            "phone": MARKERS["phone"],
            "location": MARKERS["location"],
            "education": [
                {
                    "degree": MARKERS["degree"],
                    "level": "BACHELORS",
                    "field_of_study": MARKERS["field_of_study"],
                    "institution": MARKERS["institution"],
                    "grad_year": 2027,
                    "cgpa": 8.2,
                    "scale": "SCALE_10",
                }
            ],
            "experience": [
                {
                    "title": "Data Pipeline Intern",
                    "company": MARKERS["company"],
                    "duration": MARKERS["duration"],
                    "description": "Built ingestion pipelines in Python.",
                },
                {"title": "Teaching Assistant"},
            ],
            "skills": ["Python", "SQL"],
            "projects": [{"name": MARKERS["project"], "description": MARKERS["project_description"]}],
            "certifications": [{"name": MARKERS["certification"]}],
            "languages": [MARKERS["language"]],
            "backlogs": 0,
            "preferences": {"locations": [MARKERS["preference_location"]]},
            "resume_raw_text": MARKERS["resume"],
        }
    )


def test_candidate_input_keeps_only_skills_and_experience_titles_and_descriptions() -> None:
    narrowed = candidate_match_input(marker_profile())

    assert narrowed.skills == ("Python", "SQL")
    assert narrowed.experience_texts == (
        "Data Pipeline Intern",
        "Built ingestion pipelines in Python.",
        "Teaching Assistant",
    )
    flattened = repr(narrowed)
    for field, marker in MARKERS.items():
        assert marker not in flattened, field
    assert "8.2" not in flattened and "2027" not in flattened


def test_only_the_narrowing_function_receives_a_candidate_profile() -> None:
    tree = ast.parse(ENGINE_PATH.read_text(encoding="utf-8"))
    receivers = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and "CandidateProfile" in ast.unparse(node.args)
    }
    assert receivers == {"candidate_match_input"}


def test_job_input_keeps_only_matching_fields() -> None:
    read = JobRead.model_validate(
        {
            "id": "job-1",
            "company_name": "Example Co",
            "role_title": "Backend Intern",
            "job_type": "INTERNSHIP",
            "location": "Remote",
            "description": "Build services.",
            "requirements": {"notes": "eligibility note"},
            "min_cgpa": 7.0,
            "min_cgpa_scale": "SCALE_10",
            "allowed_fields": ["Computer Science"],
            "min_degree_level": "BACHELORS",
            "max_backlogs": 0,
            "min_grad_year": 2026,
            "max_grad_year": 2027,
            "required_skills": ["Python", "Git"],
            "apply_link": "https://careers.example.com/x",
            "deadline": None,
            "source": "curated",
            "source_job_id": "EX-1",
            "status": "ACTIVE",
            "is_active": True,
            "last_verified_at": datetime(2026, 9, 1, tzinfo=timezone.utc),
        }
    )
    assert job_match_input(read) == JobMatchInput(
        job_id="job-1",
        role_title="Backend Intern",
        description="Build services.",
        required_skills=("Python", "Git"),
    )


def test_job_document_holds_only_skills_title_and_description() -> None:
    """Nothing else — not even the job id — becomes a term."""
    terms = job_terms(job("jobidmarker", ("Python",), "Backend Intern", "Build services."))
    assert terms == ["skill:python", "backend", "intern", "build", "services"]


# ---------------------------------------------------------------------------------------
# Skill comparison (ADR-021)
# ---------------------------------------------------------------------------------------


def covers(candidate_skill: str, job_skill: str) -> bool:
    return skill_coverage([candidate_skill], [job_skill]).matched_required_skills == (job_skill,)


@pytest.mark.parametrize(
    ("candidate_skill", "job_skill"),
    [
        ("python", "Python"),
        ("PYTHON", "Python"),
        ("  Python  ", "Python"),
        ("Python.", "Python"),
        ("Python ,", "Python"),
        ("JS", "JavaScript"),
        ("NodeJS", "Node.js"),
        ("node js", "Node.js"),
        ("cpp", "C++"),
        ("Postgres", "PostgreSQL"),
        ("Spring Boot", "SpringBoot"),
        ("spring-boot", "Spring Boot"),
        (".NET", "NET"),
        ("dotnet", ".NET"),
        (".net", ".NET"),
        ("JavaScript", "JS"),  # the job side is normalized too
        ("PostgreSQL", "postgres"),
    ],
)
def test_skill_variants_compare_equal(candidate_skill: str, job_skill: str) -> None:
    assert covers(candidate_skill, job_skill)


@pytest.mark.parametrize(
    ("candidate_skill", "job_skill"),
    [
        ("Node", "Node.js"),
        ("rest", "REST APIs"),
        ("express", "Express.js"),
        ("vue", "Vue.js"),
    ],
)
def test_weak_seed_aliases_apply_to_skill_lists(candidate_skill: str, job_skill: str) -> None:
    """Documented in ADR-021: defensible inside a skill list, never applied to prose."""
    assert covers(candidate_skill, job_skill)


@pytest.mark.parametrize(
    ("candidate_skill", "job_skill"),
    [("C", "C++"), ("C", "C#"), ("C++", "C#"), ("C#", "C"), ("R", "C"), ("ASP.NET", ".NET")],
)
def test_distinct_skills_do_not_compare_equal(candidate_skill: str, job_skill: str) -> None:
    assert not covers(candidate_skill, job_skill)


def test_c_family_and_r_keep_distinct_skill_terms() -> None:
    terms = candidate_terms(candidate(("C", "C++", "C#", "R")))
    assert terms == ["skill:c", "skill:c++", "skill:c#", "skill:r"]


@pytest.mark.parametrize("composite", ["CI/CD", "TCP/IP", "PL/SQL", "Node.js/Express"])
def test_composite_skills_are_one_skill_and_never_split(composite: str) -> None:
    coverage = skill_coverage(["CI", "CD", "TCP", "IP", "PL", "SQL", "Node.js", "Express"], [composite])
    assert coverage.required_skill_count == 1
    assert coverage.matched_required_skills == ()
    assert covers(composite, composite)


def test_duplicate_and_blank_skills_are_dropped_first_occurrence_wins() -> None:
    entries = skill_entries(["Python", " ", "", "python", "PYTHON", "SQL", ".", "JS", "JavaScript"])
    assert [(e.key, e.display) for e in entries] == [
        ("python", "Python"),
        ("sql", "SQL"),
        ("javascript", "JS"),
    ]


def test_aliases_are_never_applied_to_free_text() -> None:
    assert text_tokens("js rest node express postgres cpp k8s") == [
        "js", "rest", "node", "express", "postgres", "cpp", "k8s",
    ]


def test_prose_mentioning_a_skill_alias_does_not_cover_the_skill() -> None:
    result = score_jobs(
        candidate(texts=("Worked with js and postgres",)),
        [job("j", ("JavaScript", "PostgreSQL"))],
    )
    coverage = result.matches[0].skill_coverage
    assert coverage.matched_required_skills == ()


# ---------------------------------------------------------------------------------------
# Skill coverage
# ---------------------------------------------------------------------------------------


def test_full_coverage() -> None:
    coverage = skill_coverage(["sql", "python"], ["Python", "SQL"])
    assert coverage == SkillCoverage(("Python", "SQL"), (), 2)


def test_partial_coverage_keeps_job_order_and_display_names() -> None:
    coverage = skill_coverage(["git", "js"], ["Python", "JavaScript", "SQL", "Git"])
    assert coverage.matched_required_skills == ("JavaScript", "Git")
    assert coverage.missing_required_skills == ("Python", "SQL")
    assert coverage.required_skill_count == 4


def test_no_coverage() -> None:
    coverage = skill_coverage(["Rust"], ["Python", "SQL"])
    assert coverage == SkillCoverage((), ("Python", "SQL"), 2)


def test_duplicates_do_not_inflate_coverage() -> None:
    coverage = skill_coverage(["Python", "python", "PYTHON"], ["Python", "python", "Py thon", "SQL"])
    assert coverage.required_skill_count == 2
    assert coverage.matched_required_skills == ("Python",)
    assert coverage.missing_required_skills == ("SQL",)


def test_no_required_skills_is_none_listed_not_a_percentage() -> None:
    coverage = skill_coverage(["Python"], [])
    assert coverage.none_listed is True
    assert coverage.required_skill_count == 0
    assert coverage.matched_required_skills == () and coverage.missing_required_skills == ()
    assert not hasattr(coverage, "percentage") and not hasattr(coverage, "coverage_score")


# ---------------------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------------------


def test_tokenizer_keeps_technical_tokens_and_case_folds() -> None:
    assert text_tokens("C++ and C# developers using Node.js") == [
        "c++", "c#", "developers", "using", "node", "js",
    ]


def test_tokenizer_drops_numbers_single_characters_and_leading_symbols() -> None:
    assert text_tokens("2024 3d #python ++ _x R c 42% x2") == ["3d", "python", "x2"]


def test_tokenizer_removes_english_stop_words_only() -> None:
    assert "the" in ENGLISH_STOP_WORDS and "go" in ENGLISH_STOP_WORDS
    assert text_tokens("the team will go to the data centre") == ["team", "data", "centre"]


def test_tokenizer_does_not_stem() -> None:
    assert text_tokens("pipelines pipeline building built") == [
        "pipelines", "pipeline", "building", "built",
    ]


def test_tokenizer_handles_empty_and_unicode_text() -> None:
    assert text_tokens("") == []
    assert text_tokens(None) == []
    assert text_tokens("   \n\t") == []
    assert text_tokens("Données ANALYSE") == ["données", "analyse"]


def test_stop_words_never_remove_skill_terms() -> None:
    """"go" is an English stop word; the Go skill still has its term."""
    assert candidate_terms(candidate(("Go",), ("go",))) == ["skill:go"]


def test_skill_terms_are_deduplicated_but_text_frequency_is_kept() -> None:
    terms = candidate_terms(candidate(("Python", "python"), ("data data", "data")))
    assert terms == ["skill:python", "data", "data", "data"]


# ---------------------------------------------------------------------------------------
# TF-IDF (ADR-020)
# ---------------------------------------------------------------------------------------

#: Three documents: skill:python df 2, backend df 2, data df 2, skill:sql df 1.
THREE_JOBS = [
    job("a", ("Python",), "backend"),
    job("b", ("Python", "SQL"), "data"),
    job("c", (), "backend", "data"),
]
IDF_DF2 = math.log((1 + 3) / (1 + 2)) + 1
IDF_DF1 = math.log((1 + 3) / (1 + 1)) + 1


def test_idf_matches_the_smoothed_formula_on_a_three_job_corpus() -> None:
    vectorizer = build_vectorizer()
    vectorizer.fit([job_terms(j) for j in THREE_JOBS])
    idf = dict(zip(vectorizer.get_feature_names_out(), vectorizer.idf_))

    assert set(idf) == {"backend", "data", "skill:python", "skill:sql"}
    assert idf["skill:python"] == pytest.approx(IDF_DF2)
    assert idf["backend"] == pytest.approx(IDF_DF2)
    assert idf["data"] == pytest.approx(IDF_DF2)
    assert idf["skill:sql"] == pytest.approx(IDF_DF1)


def test_job_weights_are_l2_normalized_tf_idf() -> None:
    vectorizer = build_vectorizer()
    matrix = vectorizer.fit_transform([job_terms(j) for j in THREE_JOBS])
    weights = dict(zip(vectorizer.get_feature_names_out(), matrix.toarray()[1]))

    norm = math.sqrt(2 * IDF_DF2**2 + IDF_DF1**2)
    assert weights["skill:python"] == pytest.approx(IDF_DF2 / norm)
    assert weights["data"] == pytest.approx(IDF_DF2 / norm)
    assert weights["skill:sql"] == pytest.approx(IDF_DF1 / norm)
    assert weights["backend"] == 0.0


def test_term_frequency_is_raw_not_sublinear() -> None:
    """A term repeated three times weighs three times its IDF (``sublinear_tf=False``)."""
    vectorizer = build_vectorizer()
    matrix = vectorizer.fit_transform([["data", "data", "data", "backend"], ["backend"]])
    weights = dict(zip(vectorizer.get_feature_names_out(), matrix.toarray()[0]))

    idf_data = math.log((1 + 2) / (1 + 1)) + 1
    idf_backend = math.log((1 + 2) / (1 + 2)) + 1
    norm = math.sqrt((3 * idf_data) ** 2 + idf_backend**2)
    assert weights["data"] == pytest.approx(3 * idf_data / norm)
    assert weights["backend"] == pytest.approx(idf_backend / norm)


def expected_partial_overlap_score() -> float:
    """Candidate [skill:python, data] against job b [skill:python, skill:sql, data]."""
    candidate_weight = 1 / math.sqrt(2)  # both candidate terms have idf for df 2
    job_norm = math.sqrt(2 * IDF_DF2**2 + IDF_DF1**2)
    cosine = 2 * candidate_weight * (IDF_DF2 / job_norm)
    return round(100 * cosine, 1)


def test_partial_overlap_score_matches_manual_calculation() -> None:
    result = score_jobs(candidate(("Python",), ("data",)), THREE_JOBS)
    b = match_for(result, "b")
    assert b.score_basis is ScoreBasis.SCORED
    assert b.match_score == expected_partial_overlap_score()
    assert b.match_score == 73.2


def test_candidate_is_not_fitted_into_the_corpus() -> None:
    """Fitting the candidate would change every IDF, and so the hand-computed score."""
    result = score_jobs(candidate(("Python", "Rust"), ("data",)), THREE_JOBS)
    assert match_for(result, "b").match_score == expected_partial_overlap_score()


def test_out_of_vocabulary_candidate_terms_are_ignored() -> None:
    plain = score_jobs(candidate(("Python",), ("data",)), THREE_JOBS)
    noisy = score_jobs(
        candidate(("Python", "Haskell", "Erlang"), ("data zebra quokka",)), THREE_JOBS
    )
    assert [m.match_score for m in plain.matches] == [m.match_score for m in noisy.matches]


def test_whole_catalogue_is_the_corpus() -> None:
    """Adding a catalogue job changes IDF, so it changes scores."""
    base = score_jobs(candidate(("Python",), ("data",)), THREE_JOBS)
    extended = score_jobs(
        candidate(("Python",), ("data",)), [*THREE_JOBS, job("d", ("Python",), "data")]
    )
    assert match_for(base, "b").match_score != match_for(extended, "b").match_score


def test_score_does_not_depend_on_the_selected_subset() -> None:
    who = candidate(("Python",), ("data backend",))
    everything = score_jobs(who, THREE_JOBS)
    only_b = score_jobs(who, THREE_JOBS, job_ids=["b"])
    b_and_a = score_jobs(who, THREE_JOBS, job_ids=["b", "a"])

    assert only_b.corpus_size == 3
    assert [m.job_id for m in only_b.matches] == ["b"]
    assert match_for(only_b, "b") == match_for(everything, "b")
    assert match_for(b_and_a, "a") == match_for(everything, "a")


def test_selection_order_is_kept_and_repeated_ids_are_scored_once() -> None:
    result = score_jobs(candidate(("Python",)), THREE_JOBS, job_ids=["c", "a", "c"])
    assert [m.job_id for m in result.matches] == ["c", "a"]


def test_catalogue_order_does_not_change_scores() -> None:
    who = candidate(("Python", "SQL"), ("backend data",))
    forward = {m.job_id: m for m in score_jobs(who, THREE_JOBS).matches}
    backward = {m.job_id: m for m in score_jobs(who, list(reversed(THREE_JOBS))).matches}
    assert forward == backward


def test_repeated_runs_are_identical() -> None:
    who = candidate(("Python", "SQL", "Git"), ("Built backend data services",))
    assert score_jobs(who, THREE_JOBS) == score_jobs(who, THREE_JOBS)


def test_skill_and_text_namespaces_do_not_collide() -> None:
    """The word "rust" in a description is not the Rust skill."""
    catalogue = [job("j", (), "", "rust removal"), job("k", ("Rust",))]
    result = score_jobs(candidate(("Rust",)), catalogue)
    j = match_for(result, "j")
    assert j.score_basis is ScoreBasis.SCORED
    assert j.match_score == 0.0
    assert j.top_terms == ()


def test_stop_words_contribute_nothing_to_a_score() -> None:
    catalogue = [job("j", (), "", "the and of data"), job("k", (), "", "systems")]
    with_stop_words = score_jobs(candidate(texts=("the and of data",)), catalogue)
    without = score_jobs(candidate(texts=("data",)), catalogue)
    assert match_for(with_stop_words, "j").match_score == 100.0
    assert with_stop_words == without


def test_duplicate_candidate_skills_do_not_change_the_score() -> None:
    catalogue = [job("j", ("Python", "SQL"), "data"), job("k", ("Java",), "backend")]
    single = score_jobs(candidate(("Python", "SQL"), ("backend",)), catalogue)
    repeated = score_jobs(candidate(("Python", "python", "PYTHON", "SQL"), ("backend",)), catalogue)
    assert single == repeated


def test_repeated_catalogue_ids_and_unknown_selections_are_rejected() -> None:
    with pytest.raises(ValueError):
        score_jobs(candidate(("Python",)), [job("a", ("Python",)), job("a", ("SQL",))])
    with pytest.raises(ValueError):
        score_jobs(candidate(("Python",)), THREE_JOBS, job_ids=["missing"])


# ---------------------------------------------------------------------------------------
# Cosine, score and null semantics
# ---------------------------------------------------------------------------------------


def test_identical_vectors_score_100() -> None:
    result = score_jobs(candidate(("Python",), ("data",)), [job("j", ("Python",), "data")])
    assert result.matches[0].match_score == 100.0


def test_orthogonal_vectors_score_zero_not_null() -> None:
    result = score_jobs(candidate(("SQL",)), [job("a", ("Python",)), job("b", ("SQL",))])
    a = match_for(result, "a")
    assert a.score_basis is ScoreBasis.SCORED
    assert a.match_score == 0.0


def test_candidate_with_no_terms_is_null_not_zero() -> None:
    result = score_jobs(candidate((), ("the", "  ")), THREE_JOBS)
    for match in result.matches:
        assert match.match_score is None
        assert match.score_basis is ScoreBasis.NO_CANDIDATE_TERMS
        assert match.top_terms == ()


def test_candidate_with_only_out_of_vocabulary_terms_is_null() -> None:
    result = score_jobs(candidate(("Haskell",), ("quokka",)), THREE_JOBS)
    assert {m.score_basis for m in result.matches} == {ScoreBasis.NO_CANDIDATE_TERMS}
    assert {m.match_score for m in result.matches} == {None}


def test_job_with_no_terms_is_null() -> None:
    result = score_jobs(candidate(("Python",)), [job("empty", (), "the", "of and"), *THREE_JOBS])
    empty = match_for(result, "empty")
    assert empty.match_score is None
    assert empty.score_basis is ScoreBasis.NO_JOB_TERMS


def test_job_with_no_terms_is_reported_as_such_even_for_an_empty_candidate() -> None:
    result = score_jobs(candidate(), [job("empty"), *THREE_JOBS])
    assert match_for(result, "empty").score_basis is ScoreBasis.NO_JOB_TERMS
    assert match_for(result, "a").score_basis is ScoreBasis.NO_CANDIDATE_TERMS


def test_catalogue_without_any_terms_does_not_raise() -> None:
    result = score_jobs(candidate(("Python",)), [job("a"), job("b", (" ",), "the", "")])
    assert [m.score_basis for m in result.matches] == [ScoreBasis.NO_JOB_TERMS] * 2
    assert [m.match_score for m in result.matches] == [None, None]


def test_empty_catalogue_scores_nothing() -> None:
    result = score_jobs(candidate(("Python",)), [])
    assert result.matches == ()
    assert result.corpus_size == 0
    assert result.matching_version == MATCHING_VERSION == "1"


def test_cosine_similarity_of_zero_vectors_is_none() -> None:
    zero = csr_matrix((1, 3))
    unit = csr_matrix([[1.0, 0.0, 0.0]])
    assert cosine_similarity(zero, unit) is None
    assert cosine_similarity(unit, zero) is None
    assert cosine_similarity(unit, unit) == 1.0


@pytest.mark.parametrize(
    ("cosine", "score"),
    [
        (1.0, 100.0),
        (1.0000000000000002, 100.0),
        (1.01, 100.0),
        (-0.01, 0.0),
        (0.0, 0.0),
        (0.41349, 41.3),
        (0.41351, 41.4),
        (0.123456, 12.3),
    ],
)
def test_score_is_clamped_to_0_100_and_rounded_to_one_decimal(cosine: float, score: float) -> None:
    assert normalize_score(cosine) == score


# ---------------------------------------------------------------------------------------
# Top terms
# ---------------------------------------------------------------------------------------


def test_top_terms_are_shared_terms_only() -> None:
    who = candidate(("Python", "Haskell"), ("backend pipelines quokka",))
    catalogue = [job("j", ("Python", "SQL"), "backend engineer", "pipelines services"), job("k", ("Java",))]
    result = score_jobs(who, catalogue)
    j = match_for(result, "j")

    candidate_side = set(candidate_terms(who))
    job_side = set(job_terms(catalogue[0]))
    reported = {("skill:python" if t.kind is TermKind.SKILL else t.term) for t in j.top_terms}
    assert reported == {"skill:python", "backend", "pipelines"}
    assert reported <= candidate_side & job_side
    assert all(t.contribution > 0 for t in j.top_terms)


def test_top_terms_are_ordered_by_contribution_then_term() -> None:
    catalogue = [job("j", (), "", "zeta alpha beta"), job("k", (), "", "beta")]
    result = score_jobs(candidate(texts=("zeta alpha beta",)), catalogue)
    terms = match_for(result, "j").top_terms
    contributions = [t.contribution for t in terms]

    assert contributions == sorted(contributions, reverse=True)
    # alpha and zeta contribute equally and outrank beta, which k's document makes common.
    assert [t.term for t in terms] == ["alpha", "zeta", "beta"]
    assert terms[0].contribution == terms[1].contribution


def test_top_terms_are_capped_at_five() -> None:
    words = "alpha bravo charlie delta echo foxtrot golf"
    result = score_jobs(candidate(texts=(words,)), [job("j", (), "", words)])
    terms = result.matches[0].top_terms
    assert MAX_TOP_TERMS == 5
    assert len(terms) == 5
    assert [t.term for t in terms] == ["alpha", "bravo", "charlie", "delta", "echo"]


def test_skill_top_terms_use_the_job_display_name() -> None:
    result = score_jobs(candidate(("js", "postgres")), [job("j", ("JavaScript", "PostgreSQL"))])
    terms = result.matches[0].top_terms
    assert {(t.term, t.kind) for t in terms} == {
        ("JavaScript", TermKind.SKILL),
        ("PostgreSQL", TermKind.SKILL),
    }


def test_no_top_terms_without_overlap() -> None:
    result = score_jobs(candidate(("SQL",)), [job("a", ("Python",)), job("b", ("SQL",))])
    assert match_for(result, "a").top_terms == ()


# ---------------------------------------------------------------------------------------
# Explanations
# ---------------------------------------------------------------------------------------


def test_explanation_template_with_score_and_evidence() -> None:
    coverage = SkillCoverage(("Python", "SQL"), ("Git",), 3)
    terms = (
        TopTerm("python", TermKind.TEXT, 0.3),
        TopTerm("SQL", TermKind.SKILL, 0.2),
        TopTerm("pipelines", TermKind.TEXT, 0.1),
    )
    assert build_explanation(coverage, 41.3, ScoreBasis.SCORED, terms) == (
        "Matches 2 of 3 required skills listed (Python, SQL); missing: Git. "
        "Similarity 41.3 of 100, from shared terms: python, SQL, pipelines."
    )


def test_explanation_without_matches_or_shared_terms() -> None:
    coverage = SkillCoverage((), ("Git",), 1)
    assert build_explanation(coverage, 0.0, ScoreBasis.SCORED, ()) == (
        "Matches 0 of 1 required skill listed; missing: Git. "
        "Similarity 0.0 of 100, with no shared terms."
    )


def test_explanation_for_no_required_skills_and_null_scores() -> None:
    none_listed = SkillCoverage((), (), 0)
    assert build_explanation(none_listed, None, ScoreBasis.NO_CANDIDATE_TERMS, ()) == (
        "This job lists no required skills. No similarity score: the profile supplies no "
        "skill or experience terms that appear in the job catalogue."
    )
    assert build_explanation(none_listed, None, ScoreBasis.NO_JOB_TERMS, ()) == (
        "This job lists no required skills. No similarity score: this job has no skill, "
        "title or description terms to compare."
    )


def test_explanation_in_a_scored_match_reflects_the_computation() -> None:
    result = score_jobs(candidate(("Python",), ("data",)), THREE_JOBS)
    b = match_for(result, "b")
    assert b.explanation == (
        "Matches 1 of 2 required skills listed (Python); missing: SQL. "
        f"Similarity {b.match_score:.1f} of 100, from shared terms: "
        f"{', '.join(t.term for t in b.top_terms)}."
    )
    assert score_jobs(candidate(("Python",), ("data",)), THREE_JOBS).matches == result.matches


def test_explanations_contain_no_candidate_only_values_or_judgements() -> None:
    who = candidate(("Python", "Kotlin"), ("Zanzibar logistics analytics",))
    result = score_jobs(who, [job("j", ("Python", "SQL"), "Analytics Intern"), job("k", (), "", "logistics")])
    denylist = re.compile(
        r"great fit|strong candidate|excellent match|perfect candidate|ideal|"
        r"highly qualified|you should apply|recommended",
        re.IGNORECASE,
    )
    for match in result.matches:
        assert "Kotlin" not in match.explanation
        assert "zanzibar" not in match.explanation.casefold()
        assert not denylist.search(match.explanation)


# ---------------------------------------------------------------------------------------
# Ordering foundation
# ---------------------------------------------------------------------------------------


def made(job_id: str, score: float | None) -> JobMatch:
    basis = ScoreBasis.SCORED if score is not None else ScoreBasis.NO_CANDIDATE_TERMS
    return JobMatch(job_id, score, basis, (), SkillCoverage((), (), 0), "x")


def test_order_is_score_descending_nulls_last_then_job_id() -> None:
    matches = [
        made("n2", None),
        made("c", 12.5),
        made("b", 41.3),
        made("n1", None),
        made("a", 41.3),
        made("d", 99.9),
        made("z", 0.0),
    ]
    assert [m.job_id for m in order_matches(matches)] == ["d", "a", "b", "c", "z", "n1", "n2"]


def test_ties_are_broken_by_job_id_regardless_of_input_order() -> None:
    forward = order_matches([made("a", 50.0), made("b", 50.0), made("c", 50.0)])
    backward = order_matches([made("c", 50.0), made("b", 50.0), made("a", 50.0)])
    assert [m.job_id for m in forward] == [m.job_id for m in backward] == ["a", "b", "c"]


def test_order_key_uses_only_score_and_job_id() -> None:
    richer = JobMatch("b", 10.0, ScoreBasis.SCORED, (), SkillCoverage(("X", "Y"), (), 2), "x")
    poorer = JobMatch("a", 10.0, ScoreBasis.SCORED, (), SkillCoverage((), ("X", "Y"), 2), "x")
    assert match_order_key(richer) == (False, -10.0, "b")
    assert [m.job_id for m in order_matches([richer, poorer])] == ["a", "b"]


def test_zero_ranks_above_null() -> None:
    assert [m.job_id for m in order_matches([made("a", None), made("b", 0.0)])] == ["b", "a"]


# ---------------------------------------------------------------------------------------
# Privacy
# ---------------------------------------------------------------------------------------


def test_matching_logs_nothing(caplog: pytest.LogCaptureFixture) -> None:
    """Unscoped capture (memory D-10): no logger anywhere may record candidate data."""
    profile = marker_profile()
    with caplog.at_level(logging.DEBUG):
        result = score_jobs(candidate_match_input(profile), THREE_JOBS)
    assert result.matches
    logged = caplog.text + "\n".join(str(record.args) for record in caplog.records)
    for marker in [*MARKERS.values(), "Data Pipeline Intern", "ingestion pipelines"]:
        assert marker not in logged


def test_matching_writes_no_files(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    score_jobs(candidate_match_input(marker_profile()), THREE_JOBS)
    assert os.listdir(tmp_path) == []


def test_matching_adds_no_database_tables() -> None:
    assert set(Base.metadata.tables) == ALLOWED_OPERATIONAL_TABLES


def test_result_holds_no_candidate_only_values() -> None:
    result = score_jobs(candidate_match_input(marker_profile()), THREE_JOBS)
    flattened = repr(result)
    for marker in MARKERS.values():
        assert marker not in flattened
    assert "Teaching" not in flattened  # candidate text absent from every job


# ---------------------------------------------------------------------------------------
# Architecture boundary
# ---------------------------------------------------------------------------------------

FORBIDDEN_IMPORT_PREFIXES = (
    "fastapi",
    "starlette",
    "sqlalchemy",
    "app.ai",
    "app.routers",
    "app.database",
    "app.models",
    "app.main",
    "app.services.eligibility_engine",
    "app.services.eligibility_ai",
    "app.services.job_ingestion",
    "app.services.resume_parser",
    "app.adapters",
    "httpx",
    "logging",
    "pickle",
    "shelve",
    "sqlite3",
    "tempfile",
    "pathlib",
    "os",
    "io",
    "joblib",
    "functools",
)


def imported_modules(path: pathlib.Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_matching_engine_imports_no_framework_database_ai_eligibility_or_io() -> None:
    for module in imported_modules(ENGINE_PATH):
        for forbidden in FORBIDDEN_IMPORT_PREFIXES:
            assert module != forbidden and not module.startswith(forbidden + "."), module


def test_matching_engine_makes_no_io_calls() -> None:
    tree = ast.parse(ENGINE_PATH.read_text(encoding="utf-8"))
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not called & {"open", "print", "exec", "eval", "__import__"}


@pytest.mark.parametrize(
    "module", ["app/services/eligibility_engine.py", "app/services/eligibility_ai.py"]
)
def test_eligibility_never_imports_matching(module: str) -> None:
    assert not any("matching" in name for name in imported_modules(pathlib.Path(module)))


def test_matching_engine_is_importable_without_the_application() -> None:
    """A fresh interpreter importing only the engine must not load FastAPI, SQLAlchemy or AI code."""
    import subprocess
    import sys

    probe = (
        "import sys; import app.services.matching_engine; "
        "bad = sorted(m for m in sys.modules if m.split('.')[0] in {'fastapi', 'sqlalchemy', 'httpx'} "
        "or m.startswith(('app.ai', 'app.services.eligibility', 'app.routers', 'app.models', 'app.database'))); "
        "print(','.join(bad))"
    )
    output = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert output == ""
