"""Deterministic truthfulness validator (Slice 7A — ADR-025, ADR-007, dossier §12.3).

Three things are under test, in order of how much damage they would do if they broke:

1. **Removal actually happens.** An untraceable claim leaves the content, every time, with no way
   to turn that off (ADR-025 D5). A validator that quietly passes a fabrication is worse than no
   validator, because the caller believes the content was checked.
2. **The knowledge boundary holds.** A claim about data the generator never received is removed
   even when it matches the profile (D12) — otherwise a lucky guess becomes a pass.
3. **Nothing else is touched.** Surviving text is returned verbatim, and the module reaches no
   provider, database, network, filesystem, clock or random source (D6).

The corpus in :mod:`tests.truthfulness_corpus` carries the case table; this module carries the
structural, boundary and purity tests around it.
"""

from __future__ import annotations

import ast
import pathlib
from typing import Any

import pytest

from app.schemas.application import (
    MAX_REMOVED_CLAIM_TEXT,
    AnswerOutcome,
    ClaimCategory,
    GenerationOutcome,
    PackageStatus,
    RemovalReason,
    RemovalScope,
    RemovedClaim,
)
from app.schemas.candidate import CandidateProfile
from app.services import truthfulness_validator as tv
from tests.truthfulness_corpus import CORPUS, CORPUS_PROFILE, CorpusCase

ROOT = pathlib.Path(__file__).resolve().parent.parent
VALIDATOR_SOURCE = ROOT / "app" / "services" / "truthfulness_validator.py"
SCHEMA_SOURCE = ROOT / "app" / "schemas" / "application.py"

#: Importing any of these from the validator would end one of ADR-025 D6's guarantees.
FORBIDDEN_IMPORTS = frozenset(
    {
        "app.ai",
        "app.database",
        "app.db",
        "app.models",
        "fastapi",
        "starlette",
        "sqlalchemy",
        "alembic",
        "httpx",
        "requests",
        "socket",
        "urllib",
        "random",
        "secrets",
        "datetime",
        "time",
        "os",
        "pathlib",
        "shutil",
        "tempfile",
        "functools",
        "sklearn",
    }
)


@pytest.fixture
def profile() -> CandidateProfile:
    return CandidateProfile.model_validate(CORPUS_PROFILE)


def run(content: str, profile: CandidateProfile, **kwargs: Any) -> tuple[str, list[RemovedClaim]]:
    return tv.validate(content, profile, RemovalScope.COVER_LETTER, **kwargs)


# ---------------------------------------------------------------------------------------
# The maintained corpus (dossier §17)
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("case", CORPUS, ids=[c.id for c in CORPUS])
def test_corpus_case_gets_its_verdict(case: CorpusCase, profile: CandidateProfile) -> None:
    kept, removed = run(case.content, profile)

    if case.survives:
        assert kept, f"{case.id}: should have survived — {case.why}"
        assert not removed
    else:
        assert kept == "", f"{case.id}: should have been removed — {case.why}"
        assert [(r.category, r.reason) for r in removed] == [(case.category, case.reason)]


def test_the_corpus_covers_both_directions_and_stays_large_enough() -> None:
    """A corpus of only-failures would pass a validator that removes everything (C-38)."""
    survive = [case for case in CORPUS if case.survives]
    remove = [case for case in CORPUS if not case.survives]
    assert len(CORPUS) >= 40
    assert len(survive) >= 15 and len(remove) >= 15
    assert len({case.id for case in CORPUS}) == len(CORPUS)
    assert {case.category for case in remove} == set(ClaimCategory)


# ---------------------------------------------------------------------------------------
# Structure — what is removed, and what survives untouched
# ---------------------------------------------------------------------------------------


def test_a_mixed_paragraph_keeps_the_good_sentences_verbatim(profile: CandidateProfile) -> None:
    content = (
        "I have experience with Python and Django. "
        "I am proficient in JavaScript. "
        "I built Campus Ledger to track hostel dues."
    )
    kept, removed = run(content, profile)

    assert kept == (
        "I have experience with Python and Django. "
        "I built Campus Ledger to track hostel dues."
    )
    assert [r.category for r in removed] == [ClaimCategory.SKILL]
    assert removed[0].text == "I am proficient in JavaScript."


def test_one_untraceable_claim_takes_the_whole_sentence(profile: CandidateProfile) -> None:
    """Clause surgery would leave prose that reads true and is not (ADR-025 § Validator)."""
    kept, removed = run("I write Python daily, and I led a team of 12.", profile)

    assert kept == ""
    assert removed[0].text == "I write Python daily, and I led a team of 12."


def test_paragraph_breaks_are_preserved(profile: CandidateProfile) -> None:
    content = (
        "I have experience with Python.\n\n"
        "I am proficient in JavaScript.\n\n"
        "I built Campus Ledger."
    )
    kept, _ = run(content, profile)

    assert kept == "I have experience with Python.\n\nI built Campus Ledger."


def test_bullet_lines_are_removed_individually(profile: CandidateProfile) -> None:
    content = "- I work with Python.\n- I am proficient in JavaScript.\n- I work with Docker."
    kept, removed = run(content, profile)

    assert kept == "- I work with Python.\n- I work with Docker."
    assert len(removed) == 1


def test_an_enumerated_list_loses_only_the_bad_item(profile: CandidateProfile) -> None:
    content = "My tools: Python, Kubernetes, Docker."
    kept, removed = run(content, profile)

    assert kept == "My tools: Python, Docker."
    assert [r.text for r in removed] == ["Kubernetes"]


def test_a_listed_project_or_certification_survives(profile: CandidateProfile) -> None:
    """A list item may name any evidence the profile holds, not only a skill."""
    kept, removed = run("My work: Campus Ledger, Kubernetes, Django.", profile)

    assert kept == "My work: Campus Ledger, Django."
    assert [r.text for r in removed] == ["Kubernetes"]


def test_a_bad_list_lead_in_takes_the_whole_list(profile: CandidateProfile) -> None:
    """The text before the colon is a unit too: it must not slip past validation."""
    kept, removed = run("My CGPA and tools: Python, Docker.", profile)

    assert kept == ""
    assert removed[0].category is ClaimCategory.EXCLUDED_DATA
    assert removed[0].text == "My CGPA and tools: Python, Docker."


def test_surviving_text_is_never_rewritten(profile: CandidateProfile) -> None:
    content = "I  have   experience with Python. I am proficient in JavaScript."
    kept, _ = run(content, profile)

    assert kept == "I have experience with Python."
    assert "JavaScript" not in kept


def test_empty_content_returns_nothing_removed(profile: CandidateProfile) -> None:
    assert run("", profile) == ("", [])
    assert run("   \n\t  ", profile) == ("", [])


def test_content_with_nothing_traceable_returns_empty_and_reports(
    profile: CandidateProfile,
) -> None:
    content = "I am proficient in JavaScript. My CGPA is 8.2."
    kept, removed = run(content, profile)

    assert kept == ""
    assert [r.category for r in removed] == [ClaimCategory.SKILL, ClaimCategory.EXCLUDED_DATA]


def test_an_empty_profile_traces_nothing(profile: CandidateProfile) -> None:
    empty = CandidateProfile.model_validate({"education": [], "skills": []})
    kept, removed = run("I have experience with Python.", empty)

    assert kept == ""
    assert removed[0].reason is RemovalReason.CLAIM_NOT_TRACEABLE
    # The same sentence survives against a profile that actually lists the skill.
    assert run("I have experience with Python.", profile)[0]


def test_resume_text_is_evidence_for_a_project_the_profile_never_listed() -> None:
    """The résumé is the candidate's own words, and it stays local (ADR-025 D11, A-70)."""
    profile = CandidateProfile.model_validate(
        {
            "education": [],
            "skills": [],
            "projects": [],
            "resume_raw_text": "Campus Ledger: a service for tracking hostel dues.",
        }
    )
    kept, removed = run("I built Campus Ledger.", profile)

    assert kept == "I built Campus Ledger."
    assert removed == []


def test_resume_text_is_not_a_blanket_pass() -> None:
    profile = CandidateProfile.model_validate(
        {"education": [], "skills": [], "resume_raw_text": "Campus Ledger."}
    )
    kept, removed = run("I built Orbital Freight Tracker.", profile)

    assert kept == ""
    assert removed[0].category is ClaimCategory.PROJECT


def test_validation_is_deterministic(profile: CandidateProfile) -> None:
    content = "I write Python. I am proficient in JavaScript. I improved latency by 30%."
    first = run(content, profile)
    second = run(content, profile)

    assert first[0] == second[0]
    assert [r.model_dump() for r in first[1]] == [r.model_dump() for r in second[1]]


def test_the_profile_is_not_modified(profile: CandidateProfile) -> None:
    before = profile.model_dump()
    run("I am proficient in JavaScript.", profile)

    assert profile.model_dump() == before


# ---------------------------------------------------------------------------------------
# Disclosure
# ---------------------------------------------------------------------------------------


def test_every_removal_records_scope_and_question(profile: CandidateProfile) -> None:
    _, removed = tv.validate(
        "I am proficient in JavaScript.", profile, RemovalScope.ANSWER, question_id="q-1"
    )

    assert removed[0].scope is RemovalScope.ANSWER
    assert removed[0].question_id == "q-1"


def test_a_cover_letter_removal_carries_no_question_id(profile: CandidateProfile) -> None:
    _, removed = run("I am proficient in JavaScript.", profile)

    assert removed[0].scope is RemovalScope.COVER_LETTER
    assert removed[0].question_id is None


def test_long_removed_text_is_truncated_at_a_word_boundary(profile: CandidateProfile) -> None:
    filler = "and I have experience with Kubernetes " * 20
    kept, removed = run(f"I am proficient in JavaScript {filler}.", profile)

    assert kept == ""
    assert removed[0].truncated is True
    assert len(removed[0].text) <= MAX_REMOVED_CLAIM_TEXT
    assert removed[0].text.endswith("…")
    assert "  " not in removed[0].text


def test_short_removed_text_is_disclosed_whole(profile: CandidateProfile) -> None:
    _, removed = run("I am proficient in JavaScript.", profile)

    assert removed[0].truncated is False
    assert removed[0].text == "I am proficient in JavaScript."


# ---------------------------------------------------------------------------------------
# Matching rules — the ones ADR-025 states exactly
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("claim", "survives"),
    [
        ("I am skilled in Java.", True),
        ("I am skilled in JavaScript.", False),
        ("I am skilled in C++.", True),
        ("I am skilled in C#.", False),
        ("I am skilled in Python.", True),
        ("I am skilled in Pythonista.", False),
    ],
)
def test_skills_are_compared_by_canonical_equality(
    claim: str, survives: bool, profile: CandidateProfile
) -> None:
    """Substring matching is exactly what makes Java look like evidence for JavaScript."""
    kept, _ = run(claim, profile)

    assert bool(kept) is survives


def test_a_skill_alias_on_the_profile_is_accepted() -> None:
    """`JS` and `JavaScript` are one skill after canonicalization (ADR-021)."""
    profile = CandidateProfile.model_validate({"education": [], "skills": ["JS"]})
    kept, _ = tv.validate(
        "I am proficient in JavaScript.", profile, RemovalScope.COVER_LETTER
    )

    assert kept == "I am proficient in JavaScript."


@pytest.mark.parametrize(
    ("months_claimed", "survives"),
    [("five months", True), ("six months", True), ("seven months", True), ("eight months", False)],
)
def test_duration_tolerance_is_one_month(
    months_claimed: str, survives: bool, profile: CandidateProfile
) -> None:
    kept, _ = run(f"I spent {months_claimed} on backend work.", profile)

    assert bool(kept) is survives


def test_an_exaggerated_duration_is_reported_as_exceeding(profile: CandidateProfile) -> None:
    _, removed = run("I spent three years on backend work.", profile)

    assert removed[0].reason is RemovalReason.CLAIM_EXCEEDS_PROFILE_VALUE


@pytest.mark.parametrize(
    ("claim", "survives"),
    [("30%", True), ("30.0%", True), ("31%", False), ("3%", False), ("300%", False)],
)
def test_numbers_must_match_exactly(
    claim: str, survives: bool, profile: CandidateProfile
) -> None:
    kept, _ = run(f"I improved latency by {claim}.", profile)

    assert bool(kept) is survives


def test_duration_parsing_never_reads_the_clock() -> None:
    """An open-ended span stays unparseable: a verdict must not change with the date."""
    assert tv._duration_months("since 2019") is None
    assert tv._duration_months("6 months") == 6
    assert tv._duration_months("2 years") == 24
    assert tv._duration_months("1 year and 6 months") == 18
    assert tv._duration_months("2022 - 2024") == 24
    assert tv._duration_months("a while") is None


def test_evidence_excludes_data_outside_the_knowledge_boundary(
    profile: CandidateProfile,
) -> None:
    """Grades, backlogs, institutions and contact details are never gathered as evidence."""
    evidence = tv.build_evidence(profile)

    assert 8.2 not in evidence.numbers
    assert "example institute of technology" not in evidence.corpus
    assert "examplecorp" not in evidence.corpus


# ---------------------------------------------------------------------------------------
# Purity — ADR-025 D6
# ---------------------------------------------------------------------------------------


def imported_modules(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


@pytest.mark.parametrize("source", [VALIDATOR_SOURCE, SCHEMA_SOURCE], ids=["validator", "schemas"])
def test_slice_7a_imports_nothing_forbidden(source: pathlib.Path) -> None:
    for module in imported_modules(source):
        root = module.split(".")[0]
        assert module not in FORBIDDEN_IMPORTS, module
        assert root not in FORBIDDEN_IMPORTS, module


def test_the_validators_only_service_dependency_is_also_clean() -> None:
    """The skill normalizer is reused rather than re-implemented (ADR-021) — it must be pure."""
    normalizer = ROOT / "app" / "services" / "candidate_normalizer.py"
    assert "app.services.candidate_normalizer" in imported_modules(VALIDATOR_SOURCE)
    for module in imported_modules(normalizer):
        root = module.split(".")[0]
        assert root not in {"app.ai", "sqlalchemy", "fastapi", "httpx", "socket", "requests"}


def test_the_validator_touches_no_io_and_no_global_state() -> None:
    tree = ast.parse(VALIDATOR_SOURCE.read_text(encoding="utf-8"))
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }

    assert not {"open", "eval", "exec", "compile", "__import__"} & called
    assert not {"now", "today", "monotonic", "getenv", "environ", "urandom"} & attributes
    assert not [node for node in ast.walk(tree) if isinstance(node, ast.Global)]


def test_the_module_exposes_no_way_to_disable_removal() -> None:
    """ADR-025 D5: no warn-only mode, no flag, no setting."""
    source = VALIDATOR_SOURCE.read_text(encoding="utf-8")

    assert "validate=" not in source and "strict" not in source
    assert "def validate(" in source
    signature = source.split("def validate(", 1)[1].split(")", 1)[0]
    assert set(signature.split(",")[0:4])  # content, profile, scope, question_id only
    assert "enabled" not in signature and "dry_run" not in signature


# ---------------------------------------------------------------------------------------
# Schema contract
# ---------------------------------------------------------------------------------------


def test_removed_claim_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError):
        RemovedClaim(
            text="x",
            category=ClaimCategory.SKILL,
            reason=RemovalReason.CLAIM_NOT_TRACEABLE,
            scope=RemovalScope.COVER_LETTER,
            surprise="no",
        )


def test_package_vocabulary_is_pinned() -> None:
    """These strings are an API contract in Slice 7B; renaming one is a breaking change."""
    assert [s.value for s in PackageStatus] == ["COMPLETE", "PARTIAL", "NOTHING_VERIFIABLE"]
    assert [g.value for g in GenerationOutcome] == [
        "GENERATED",
        "AI_GENERATION_UNAVAILABLE",
        "AI_GENERATION_INVALID",
        "AI_GENERATION_EMPTY",
    ]
    assert [a.value for a in AnswerOutcome] == [
        "GENERATED",
        "REMOVED_ENTIRELY",
        "UNAVAILABLE",
        "INVALID",
        "EMPTY",
        "REQUIRES_EXCLUDED_DATA",
    ]
    assert [c.value for c in ClaimCategory] == [
        "SKILL",
        "PROJECT",
        "EMPLOYMENT",
        "DURATION",
        "CREDENTIAL",
        "QUANTITY",
        "EXCLUDED_DATA",
    ]
    assert [r.value for r in RemovalReason] == [
        "CLAIM_NOT_TRACEABLE",
        "CLAIM_EXCEEDS_PROFILE_VALUE",
        "CLAIM_OUTSIDE_KNOWLEDGE_BOUNDARY",
        "ANSWER_REQUIRES_EXCLUDED_DATA",
    ]
    assert [s.value for s in RemovalScope] == ["COVER_LETTER", "ANSWER"]
    assert tv.VALIDATOR_VERSION == "1"


def test_the_eligibility_reason_codes_are_untouched() -> None:
    """Generated-content vocabulary lives in its own module (ADR-010, ADR-025)."""
    from app.schemas.eligibility import ReasonCode

    assert not {code.value for code in ReasonCode} & {r.value for r in RemovalReason}
