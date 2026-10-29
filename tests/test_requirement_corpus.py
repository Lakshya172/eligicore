"""ADR-030 Step 9a-1: the job-requirement fixture corpus, run through the real pipeline.

The corpus in :mod:`tests.requirement_corpus` carries the case table; this module runs it.
Four things are under test, in order of how much damage they would do if they broke:

1. **Authority holds.** A source-stated deterministic failure is final; a prose-derived one is
   ``NEEDS_REVIEW`` and never ``NOT_ELIGIBLE``; an all-derived pass is never plain
   ``ELIGIBLE``; a source-stated value suppresses a derived one of the same type (ADR-030
   D2, D4, D20a).
2. **Nothing is promoted without evidence in the stored text.** Each description is ingested
   through the real normalizer and derivation, so expectations are about the pinned text as
   stored (D9) — including entity-escaped HTML, which is stored exactly as the source sent it.
3. **The instruction gate's limits are measured, not hidden.** Verified rejections, documented
   false negatives and documented false positives are asserted separately, and every false
   negative is shown to be capped at ``NEEDS_REVIEW`` by provenance.
4. **Failure leaves nothing behind.** Malformed model output and provider failure raise before
   any proposal exists, and an unavailable derivation never overwrites or withdraws a row.

**Offline.** Every database is in-memory SQLite (the conftest guard pins the process URL to a
temporary file as well); every Gemini request goes to ``httpx.MockTransport`` with a
placeholder key. Nothing here reaches a network, a live provider or the developer database.

**Nothing here wires extraction.** Where a case needs model proposals, the test calls the
Gemini operation itself and hands its proposals to the verifier. No production path does that;
Step 9b, which would, is not approved.
"""

from __future__ import annotations

import ast
import json
import logging
import pathlib
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai import errors
from app.ai.providers.gemini import GeminiFlashProvider
from app.ai.usage import UsageSink
from app.config import Settings
from app.database import Base
from app.models.extracted_requirement import ExtractedRequirement
from app.models.job import Job
from app.schemas.candidate import CandidateProfile
from app.schemas.eligibility import (
    EligibilityState,
    RequirementProvenance,
    RequirementType,
)
from app.schemas.extraction import (
    ExtractionProposal,
    RequirementStrength,
    VerifiedDerivedRequirement,
)
from app.schemas.job import JobRead
from app.services import requirement_derivation
from app.services.derived_requirements import load_derived_requirements
from app.services.eligibility_engine import evaluate_job
from app.services.job_ingestion import ingest_source
from app.services.job_normalizer import collapse_whitespace
from app.services.requirement_derivation import DerivationStatus, derive_for_job
from app.services.requirement_extractors import extract_requirements
from app.services.requirement_verifier import verify_proposals
from tests import requirement_corpus as corpus
from tests.requirement_corpus import (
    AUTHORITY_CASES,
    DERIVATION_CASES,
    PROPOSAL_CASES,
    PROVIDER_CASES,
    AuthorityCase,
    DerivationCase,
    ProposalCase,
    ProviderCase,
)
from tests.test_eligibility_engine import make_job
from tests.test_job_ingestion import FakeAdapter, make_raw

ROOT = pathlib.Path(__file__).resolve().parent.parent
CORPUS_SOURCE = ROOT / "tests" / "requirement_corpus.py"

ENABLED = Settings(extraction_enabled=True)
DISABLED = Settings()

API_BASE = "https://generativelanguage.example.invalid/v1beta"
MODEL_ID = "gemini-corpus-model"
KEY = "test-key-not-real"

PHASE_1 = (
    RequirementType.MIN_CGPA,
    RequirementType.GRAD_YEAR_WINDOW,
    RequirementType.MAX_BACKLOGS,
)


# ---------------------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------------------


@pytest.fixture
def session() -> Iterator[Session]:
    """An isolated in-memory database per test, matching the derivation tests' fixture."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        yield db
    Base.metadata.drop_all(engine)


def ingest(
    session: Session,
    description: str,
    *,
    source: dict[str, Any] | None = None,
    settings: Settings = ENABLED,
) -> Job:
    """Ingest one posting through the real adapter → normalizer → derivation path."""
    raw = make_raw(description=description, **(corpus.NO_SOURCE if source is None else source))
    ingest_source(session, FakeAdapter([raw]), settings=settings)
    job = session.execute(select(Job)).scalars().one()
    return job


def rows(session: Session) -> list[ExtractedRequirement]:
    return list(session.execute(select(ExtractedRequirement)).scalars())


def active(session: Session) -> list[ExtractedRequirement]:
    return [row for row in rows(session) if row.is_active]


def row_value(row: ExtractedRequirement) -> object:
    """The typed value a stored row carries, built the way the read path builds it."""
    if row.requirement_type is RequirementType.MIN_CGPA:
        return corpus.cgpa(row.min_cgpa, row.min_cgpa_scale)  # type: ignore[arg-type]
    if row.requirement_type is RequirementType.GRAD_YEAR_WINDOW:
        return corpus.window(row.min_grad_year, row.max_grad_year)
    return corpus.backlogs(row.max_backlogs)  # type: ignore[arg-type]


def failures(outcomes: Any) -> tuple[tuple[Any, ...], ...]:
    return tuple(outcome.failures for outcome in outcomes)


def promoted(verified: Any) -> tuple[tuple[object, str, str], ...]:
    return tuple((r.value, r.evidence_text, r.extractor) for r in verified)


def expected(case: DerivationCase | ProposalCase) -> tuple[tuple[object, str, str], ...]:
    return tuple((p.value, p.evidence, p.extractor) for p in case.promoted)


def gemini(handler: Any) -> GeminiFlashProvider:
    return GeminiFlashProvider(
        api_key=KEY,
        model=MODEL_ID,
        api_base=API_BASE,
        timeout_seconds=5,
        max_retries=0,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def reply_with(payload: Any) -> httpx.Response:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]})


async def model_proposals(
    description: str, reply: tuple[dict[str, Any], ...]
) -> list[ExtractionProposal]:
    """What the Gemini operation hands back for a mocked reply. No production path calls it."""
    provider = gemini(lambda _request: reply_with({"proposals": list(reply)}))
    return await provider.extract_job_requirements(description)


def stored(description: str) -> str:
    """The description exactly as ingestion stores it — the pinned text (D9)."""
    return collapse_whitespace(description)


# ---------------------------------------------------------------------------------------
# The corpus itself
# ---------------------------------------------------------------------------------------


def test_every_category_keeps_its_minimum() -> None:
    counts = corpus.category_counts()
    short = {
        category: (counts[category], minimum)
        for category, minimum in corpus.MINIMUM_PER_CATEGORY.items()
        if counts[category] < minimum
    }
    assert short == {}, f"categories below their minimum (have, need): {short}"
    assert set(corpus.MINIMUM_PER_CATEGORY) == set(corpus.CATEGORIES)


def test_case_ids_are_unique_within_and_across_tables() -> None:
    ids = (
        corpus.derivation_ids() + corpus.authority_ids()
        + corpus.proposal_ids() + corpus.provider_ids()
    )
    assert len(ids) == len(set(ids))


def test_gate_classifications_are_injection_cases_and_each_kind_is_represented() -> None:
    cases = (*DERIVATION_CASES, *PROPOSAL_CASES)
    for case in cases:
        assert case.classification in {
            corpus.EXPECTED, corpus.EXTRACTION_GAP, *corpus.GATE_CLASSIFICATIONS
        }, case.id
        if case.classification in corpus.GATE_CLASSIFICATIONS:
            assert case.category == corpus.INJECTION, case.id
    kinds = [case.classification for case in cases]
    assert kinds.count(corpus.INJECTION_REJECTED) >= 5
    assert kinds.count(corpus.INJECTION_MISSED) >= 8
    assert kinds.count(corpus.GATE_FALSE_POSITIVE) >= 4


def test_the_corpus_module_is_data_and_imports_only_schemas() -> None:
    """No network, provider, database or service code can be reached from the table."""
    tree = ast.parse(CORPUS_SOURCE.read_text(encoding="utf-8"))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert imported <= {
        "__future__", "dataclasses", "typing",
        "app.schemas.candidate", "app.schemas.eligibility", "app.schemas.extraction",
    }, imported


# ---------------------------------------------------------------------------------------
# Derivation — the real stored-description pipeline
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("case", DERIVATION_CASES, ids=corpus.derivation_ids())
def test_the_verifier_reads_the_stored_description_as_the_corpus_expects(
    case: DerivationCase,
) -> None:
    pinned = stored(case.description)
    result = verify_proposals(extract_requirements(pinned), pinned)

    assert failures(result.outcomes) == case.outcomes
    assert promoted(result.verified) == expected(case)


@pytest.mark.parametrize("case", DERIVATION_CASES, ids=corpus.derivation_ids())
def test_ingestion_stores_exactly_the_promoted_requirements(
    session: Session, case: DerivationCase
) -> None:
    job = ingest(session, case.description)

    # The pinned text is the collapsed string, entities untouched (D9).
    assert job.description == stored(case.description)

    got = sorted(
        (
            (row.requirement_type.value, repr(row_value(row)), row.evidence_text, row.extractor)
            for row in active(session)
        )
    )
    want = sorted(
        (p.value.requirement_type.value, repr(p.value), p.evidence, p.extractor)
        for p in case.promoted
    )
    assert got == want
    for row in active(session):
        assert row.provenance is RequirementProvenance.PROSE_DERIVED
        assert row.strength is RequirementStrength.REQUIRED
        assert (row.provider, row.model) == (None, None)
        assert row.evidence_text in job.description
        assert row.source_text_digest == requirement_derivation.source_text_digest(
            job.description
        )


def test_ingestion_with_extraction_disabled_stores_no_row(session: Session) -> None:
    ingest(session, corpus.DERIVATION_CASES[1].description, settings=DISABLED)
    assert rows(session) == []


# ---------------------------------------------------------------------------------------
# The instruction gate: rejections, false negatives, false positives (ADR-030 D25a)
# ---------------------------------------------------------------------------------------


def _gate_cases(*kinds: str) -> list[DerivationCase | ProposalCase]:
    return [
        case for case in (*DERIVATION_CASES, *PROPOSAL_CASES) if case.classification in kinds
    ]


@pytest.mark.parametrize(
    "case",
    _gate_cases(corpus.INJECTION_REJECTED, corpus.GATE_FALSE_POSITIVE),
    ids=lambda case: case.id,
)
def test_gate_refusals_are_the_gate_alone(case: DerivationCase | ProposalCase) -> None:
    """Every refused proposal is refused by the gate **and nothing else**.

    So a rejection case cannot pass for an unrelated reason, and a false-positive case really
    does cost the job a requirement it would otherwise keep.
    """
    assert case.promoted == ()
    assert case.outcomes and all(outcome == (corpus.GATE,) for outcome in case.outcomes)


@pytest.mark.parametrize("case", _gate_cases(corpus.INJECTION_MISSED), ids=lambda case: case.id)
def test_documented_false_negatives_promote_and_never_meet_the_gate(
    case: DerivationCase | ProposalCase,
) -> None:
    assert case.promoted
    assert all(corpus.GATE not in outcome for outcome in case.outcomes)


@pytest.mark.parametrize(
    "case", _gate_cases(corpus.EXPECTED, corpus.EXTRACTION_GAP), ids=lambda case: case.id
)
def test_ordinary_cases_never_meet_the_gate(case: DerivationCase | ProposalCase) -> None:
    assert all(corpus.GATE not in outcome for outcome in case.outcomes)


@pytest.mark.parametrize("case", _gate_cases(corpus.INJECTION_MISSED), ids=lambda case: case.id)
def test_a_missed_injection_is_capped_at_needs_review(case: DerivationCase | ProposalCase) -> None:
    """The harm of a false negative is bounded by provenance (D2), and this shows the bound.

    A candidate below the injected cutoff is told ``NEEDS_REVIEW`` — never ``NOT_ELIGIBLE`` —
    and the entry says it was read from prose.
    """
    verified = [
        VerifiedDerivedRequirement(
            requirement_type=p.value.requirement_type,
            value=p.value,
            evidence_text=p.evidence,
            extractor=p.extractor,
            extractor_version="1",
        )
        for p in case.promoted
    ]
    job = make_job(description=stored(case.description))
    verdict = evaluate_job(CandidateProfile.model_validate(corpus.candidate(7.0)), job, verified)

    assert verdict.eligibility_state is EligibilityState.NEEDS_REVIEW
    entry = next(r for r in verdict.requirement_breakdown if r.requirement_type in PHASE_1)
    assert entry.provenance is RequirementProvenance.PROSE_DERIVED


# ---------------------------------------------------------------------------------------
# Source-stated versus prose-derived authority, through storage and the engine
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("case", AUTHORITY_CASES, ids=corpus.authority_ids())
def test_authority_follows_provenance(session: Session, case: AuthorityCase) -> None:
    settings = ENABLED if case.extraction_enabled else DISABLED
    job = ingest(session, case.description, source=case.source, settings=settings)

    derived = load_derived_requirements(session, [job], settings=settings).get(job.id, ())
    verdict = evaluate_job(
        CandidateProfile.model_validate(case.profile), JobRead.model_validate(job), derived
    )

    assert verdict.eligibility_state is case.state
    entries = tuple(
        corpus.Entry(r.requirement_type, r.provenance, r.status, r.confidence)
        for r in verdict.requirement_breakdown
        if r.requirement_type in PHASE_1
    )
    assert entries == case.entries
    for result in verdict.requirement_breakdown:
        if result.provenance is RequirementProvenance.PROSE_DERIVED:
            assert result.evidence and result.evidence in job.description
    if not case.extraction_enabled:
        assert rows(session) == []


def test_stored_rows_are_not_read_while_extraction_is_disabled(session: Session) -> None:
    """Rows written while extraction was on stay inert once it is off (D20b read gate)."""
    case = next(c for c in AUTHORITY_CASES if c.id == "derived-fail-is-needs-review")
    job = ingest(session, case.description, source=case.source)
    assert active(session), "rows must exist for the read gate to be exercised"

    derived = load_derived_requirements(session, [job], settings=DISABLED).get(job.id, ())
    verdict = evaluate_job(
        CandidateProfile.model_validate(case.profile), JobRead.model_validate(job), derived
    )

    assert derived == ()
    assert verdict.eligibility_state is EligibilityState.ELIGIBLE


def test_a_suppressed_derived_row_is_kept_and_unmodified(session: Session) -> None:
    """R-COLLISION suppresses at read time; the stored row is retained exactly (D20a)."""
    case = next(c for c in AUTHORITY_CASES if c.id == "source-stated-fail-is-final")
    ingest(session, case.description, source=case.source)

    [row] = active(session)
    assert (row.requirement_type, row.min_cgpa) == (RequirementType.MIN_CGPA, 7.0)


# ---------------------------------------------------------------------------------------
# Conflicting proposals and provenance — deterministic and model proposals together
# ---------------------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("case", PROPOSAL_CASES, ids=corpus.proposal_ids())
async def test_proposals_from_both_extractors_are_verified_together(case: ProposalCase) -> None:
    pinned = stored(case.description)
    from_model = await model_proposals(pinned, case.reply)
    from_rules = list(extract_requirements(pinned))
    ordered = (
        [*from_rules, *from_model]
        if case.order == corpus.DETERMINISTIC_FIRST
        else [*from_model, *from_rules]
    )

    result = verify_proposals(ordered, pinned)

    assert failures(result.outcomes) == case.outcomes
    assert promoted(result.verified) == expected(case)
    for requirement in result.verified:
        assert requirement.provenance is RequirementProvenance.PROSE_DERIVED
        assert requirement.strength is RequirementStrength.REQUIRED
        assert requirement.evidence_text in pinned
        if requirement.extractor == corpus.MODEL:
            assert (requirement.provider, requirement.model) == ("gemini", MODEL_ID)
        else:
            assert (requirement.provider, requirement.model) == (None, None)


@pytest.mark.anyio
async def test_the_model_cannot_choose_its_own_provenance() -> None:
    """Whatever the model says, the provider labels every proposal PROSE_DERIVED (D1)."""
    case = next(c for c in PROPOSAL_CASES if c.id == "agree-model-first")
    [proposal] = await model_proposals(stored(case.description), case.reply)
    assert proposal.provenance is RequirementProvenance.PROSE_DERIVED
    assert (proposal.extractor, proposal.provider, proposal.model) == (
        corpus.MODEL, "gemini", MODEL_ID,
    )


# ---------------------------------------------------------------------------------------
# Malformed output and provider failure (D26)
# ---------------------------------------------------------------------------------------


def _transport(case: ProviderCase, seen: list[httpx.Request]) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if case.status is None:
            raise httpx.ReadTimeout("timed out", request=request)
        if case.raw is not None:
            return httpx.Response(case.status, json=case.raw)
        return reply_with(case.text)
    return handler


@pytest.mark.anyio
@pytest.mark.parametrize("case", PROVIDER_CASES, ids=corpus.provider_ids())
async def test_a_bad_reply_or_failed_provider_yields_no_proposal(case: ProviderCase) -> None:
    seen: list[httpx.Request] = []
    sink = UsageSink()
    error = getattr(errors, case.error)

    with pytest.raises(error) as raised:
        await gemini(_transport(case, seen)).extract_job_requirements(
            stored(case.description), usage=sink
        )

    assert len(seen) == case.requests
    # The error names a category; it never quotes the posting or the reply.
    assert stored(case.description) not in str(raised.value)
    assert "7.5" not in str(raised.value)


# ---------------------------------------------------------------------------------------
# Unavailable derivation never overwrites or withdraws an existing row
# ---------------------------------------------------------------------------------------


def _boom(*_args: object, **_kwargs: object) -> object:
    raise RuntimeError("extractor down")


_WITH_ROWS = [case for case in DERIVATION_CASES if case.promoted]


@pytest.mark.parametrize("target", ["extract_requirements", "verify_proposals"])
@pytest.mark.parametrize("case", _WITH_ROWS, ids=[case.id for case in _WITH_ROWS])
def test_an_unavailable_rederivation_leaves_every_row_as_it_was(
    session: Session, monkeypatch: pytest.MonkeyPatch, case: DerivationCase, target: str
) -> None:
    ingest(session, case.description)
    before = sorted(
        (r.id, r.status, r.evidence_text, r.source_text_digest, r.extracted_at)
        for r in rows(session)
    )
    assert before, "the case must have rows for this test to mean anything"

    monkeypatch.setattr(requirement_derivation, target, _boom)
    ingest(session, f"{case.description} Updated posting.")

    after = sorted(
        (r.id, r.status, r.evidence_text, r.source_text_digest, r.extracted_at)
        for r in rows(session)
    )
    assert after == before


def test_derivation_reports_unavailable_and_writes_nothing(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = ingest(session, corpus.DERIVATION_CASES[0].description, settings=DISABLED)
    monkeypatch.setattr(requirement_derivation, "extract_requirements", _boom)

    outcome = derive_for_job(session, job)

    assert outcome.status is DerivationStatus.UNAVAILABLE
    assert (outcome.verified, outcome.rows_created, outcome.rows_invalidated) == (0, 0, 0)
    assert rows(session) == []


# ---------------------------------------------------------------------------------------
# Privacy: derivation logs counts, never text (D24)
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case",
    [c for c in DERIVATION_CASES if c.category in {corpus.INJECTION, corpus.ESCAPED_HTML}],
    ids=lambda case: case.id,
)
def test_ingestion_logs_no_description_or_evidence(
    session: Session, caplog: pytest.LogCaptureFixture, case: DerivationCase
) -> None:
    with caplog.at_level(logging.DEBUG):
        ingest(session, case.description)

    assert "derivation source=fake" in caplog.text
    assert "CGPA" not in caplog.text
    for p in case.promoted:
        assert p.evidence not in caplog.text
