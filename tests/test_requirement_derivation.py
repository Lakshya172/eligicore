"""Derivation orchestration tests (ADR-030 D21, D22, D26).

This layer is where four independently-correct pieces can still combine into something
wrong: an extractor that runs when it should not, a verified requirement that never reaches
storage, a stale row that outlives the text it was read from, or a parsing failure that takes
a valid ingestion run down with it. These tests are written around those four.

**Every fixture here is public job prose.** No candidate, no profile, no personal data —
derivation has no parameter for any of it, and these tests assert that too.

The guard is tested first and hardest, because ``extraction_enabled`` defaulting to False is
what makes every merged step of ADR-030 safe to ship before the last one.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import logging
import pathlib
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.database import Base
from app.models.extracted_requirement import ExtractedRequirement, ExtractionStatus
from app.models.job import Job
from app.schemas.candidate import GradeScale
from app.schemas.eligibility import RequirementType
from app.schemas.extraction import RequirementProvenance, RequirementStrength
from app.services import job_ingestion, requirement_derivation
from app.services.job_ingestion import ingest_source
from app.services.job_normalizer import compute_content_hash, normalize_job
from app.services.requirement_derivation import (
    DerivationStatus,
    derive_for_job,
    source_text_digest,
)
from app.services.requirement_extractors import EXTRACTOR_VERSION
from tests.test_job_ingestion import FakeAdapter, make_raw

MODULE = pathlib.Path(requirement_derivation.__file__)

#: Extraction on. Constructed rather than monkeypatched onto the cached global, so a test
#: can never leak an enabled setting into another one.
ENABLED = Settings(extraction_enabled=True)

#: A posting stating all three Phase 1 criteria, surrounded by the numbers that must not
#: become criteria: an experience requirement, a salary band, a requisition code and a date.
FULL = (
    "Backend Engineer. Compensation 18 LPA. The role requires 7.5 years of experience. "
    "Requisition REQ-2026-ABC posted 2026-01-15. "
    "Eligibility: minimum CGPA 7.5/10 required. Candidates must have no active backlogs. "
    "Only the 2025-2026 graduating batch is required to apply."
)
CGPA_ONLY = "Eligibility: minimum CGPA 8.0/10 required. Apply by 2026-03-01."
NO_CRITERIA = "Backend Engineer. You will own the product backlog and ship weekly."


# ---------------------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------------------


@pytest.fixture
def session() -> Iterator[Session]:
    """An isolated in-memory database per test, matching the ingestion tests' fixture."""
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
    enabled: bool = True,
    source_job_id: str = "EX-001",
    **overrides: object,
) -> None:
    """Run one ingestion carrying one posting."""
    raw = make_raw(description=description, source_job_id=source_job_id, **overrides)
    ingest_source(
        session,
        FakeAdapter([raw]),
        settings=ENABLED if enabled else Settings(),
    )


def rows(session: Session) -> list[ExtractedRequirement]:
    """Every derived row, ordered so assertions read the same way every run."""
    return sorted(
        session.execute(select(ExtractedRequirement)).scalars().all(),
        key=lambda r: (r.source_text_digest, r.requirement_type.value),
    )


def active(session: Session) -> list[ExtractedRequirement]:
    return [row for row in rows(session) if row.is_active]


def by_type(session: Session) -> dict[RequirementType, ExtractedRequirement]:
    return {row.requirement_type: row for row in active(session)}


def pinned(description: str) -> str:
    """The description exactly as ingestion would store it."""
    return normalize_job(make_raw(description=description), "fake").description


def the_job(session: Session) -> Job:
    return session.execute(select(Job)).scalars().first()  # type: ignore[return-value]


def count_derivations(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every job derivation is called for, and still run it.

    **Counting, never raising.** ``_derive_requirements`` catches ``Exception`` so that one
    bad posting cannot fail an ingestion run, and ``AssertionError`` is an ``Exception`` — a
    spy that raised would be swallowed by the very fail-closed handler these tests also
    cover, and would pass while the thing it guards was broken. Mutation testing found
    exactly that, in three tests below.
    """
    calls: list[str] = []
    real = job_ingestion.derive_for_job

    def spy(db: Session, job: Job) -> object:
        calls.append(job.id)
        return real(db, job)

    monkeypatch.setattr(job_ingestion, "derive_for_job", spy)
    return calls


def seed_job(session: Session, description: str) -> Job:
    """A stored job, created without ingestion, for testing the service directly."""
    normalized = normalize_job(make_raw(description=description), "fake")
    job = Job(
        id=str(uuid.uuid4()),
        source="fake",
        source_job_id=normalized.source_job_id,
        **{
            field: getattr(normalized, field)
            for field in job_ingestion._UPDATABLE_FIELDS
        },
    )
    session.add(job)
    session.commit()
    return job


# ---------------------------------------------------------------------------------------
# Configuration — the default is the safety property
# ---------------------------------------------------------------------------------------


def test_extraction_is_disabled_by_default() -> None:
    """ADR-030 sequences every step to be mergeable with the capability off.

    An unconfigured checkout and CI must ingest exactly as they did before extraction
    existed, and this default is the single thing that guarantees it.
    """
    assert Settings().extraction_enabled is False


def test_enabling_extraction_changes_no_ai_setting() -> None:
    """The deterministic path is not an AI path. Enabling it authorizes no provider call."""
    assert ENABLED.ai_provider is Settings().ai_provider
    assert ENABLED.gemini_model == "gemini-2.0-flash"
    assert ENABLED.gemini_api_key is None


# ---------------------------------------------------------------------------------------
# Disabled — nothing runs, nothing is written, nothing is logged
# ---------------------------------------------------------------------------------------


def test_disabled_ingestion_writes_no_derived_rows(session: Session) -> None:
    ingest(session, FULL, enabled=False)
    assert rows(session) == []


def test_disabled_ingestion_calls_no_extractor_and_no_verifier(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guard is checked before anything is reached, not after.

    Both the orchestration entry point and the two functions behind it are made explosive,
    so a guard that merely discarded the result would still turn this red.
    """

    def explode(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("extraction ran while disabled")

    monkeypatch.setattr(job_ingestion, "derive_for_job", explode)
    monkeypatch.setattr(requirement_derivation, "extract_requirements", explode)
    monkeypatch.setattr(requirement_derivation, "verify_proposals", explode)

    ingest(session, FULL, enabled=False)
    assert the_job(session) is not None


def test_disabled_ingestion_behaves_exactly_as_before(session: Session) -> None:
    """Create, update and unchanged counts are untouched by the guarded hook."""
    raw = make_raw(description=FULL)
    first = ingest_source(session, FakeAdapter([raw]))
    second = ingest_source(session, FakeAdapter([raw]))

    assert (first.jobs_created, first.jobs_updated, first.jobs_unchanged) == (1, 0, 0)
    assert (second.jobs_created, second.jobs_updated, second.jobs_unchanged) == (0, 0, 1)
    assert rows(session) == []


def test_disabled_ingestion_logs_nothing_about_derivation(
    session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG, logger="eligicore.ingestion"):
        ingest(session, FULL, enabled=False)
    assert not [r for r in caplog.records if "derivation" in r.getMessage()]


# ---------------------------------------------------------------------------------------
# A new job
# ---------------------------------------------------------------------------------------


def test_a_new_job_is_derived_verified_and_stored(session: Session) -> None:
    """The whole path: extractors propose, the verifier decides, storage records."""
    ingest(session, FULL)

    stored = by_type(session)
    assert set(stored) == {
        RequirementType.MIN_CGPA,
        RequirementType.GRAD_YEAR_WINDOW,
        RequirementType.MAX_BACKLOGS,
    }


def test_a_job_stating_no_criterion_stores_nothing(session: Session) -> None:
    """Ordinary and common. Absence is never a failure for a candidate (ADR-003)."""
    ingest(session, NO_CRITERIA)
    assert rows(session) == []


def test_verified_zero_is_distinguishable_from_unavailable(session: Session) -> None:
    """Two different outcomes, deliberately not collapsed into one.

    Were they the same, a broken extractor would be indistinguishable from a catalogue of
    postings that genuinely state no criterion.
    """
    job = seed_job(session, NO_CRITERIA)
    outcome = derive_for_job(session, job)
    assert outcome.status is DerivationStatus.COMPLETED
    assert outcome.verified == 0


def test_every_ingested_job_is_derived_individually(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One job per call. There is no batch extraction entry point (D21)."""
    seen: list[object] = []
    real = job_ingestion.derive_for_job

    def spy(db: Session, job: Job) -> object:
        seen.append(job.id)
        return real(db, job)

    monkeypatch.setattr(job_ingestion, "derive_for_job", spy)
    ingest_source(
        session,
        FakeAdapter(
            [
                make_raw(description=FULL, source_job_id="A"),
                make_raw(description=CGPA_ONLY, source_job_id="B"),
                make_raw(description=NO_CRITERIA, source_job_id="C"),
            ]
        ),
        settings=ENABLED,
    )
    assert len(seen) == 3 and len(set(seen)) == 3


def test_the_service_takes_one_job_and_no_collection() -> None:
    """Asserted on the signature, so a batch overload cannot be added without noticing."""
    parameters = inspect.signature(derive_for_job).parameters
    assert list(parameters) == ["session", "job"]
    assert parameters["job"].annotation == "Job"


# ---------------------------------------------------------------------------------------
# Unchanged source — idempotency
# ---------------------------------------------------------------------------------------


def test_repeated_ingestion_of_unchanged_text_does_not_duplicate_rows(
    session: Session,
) -> None:
    ingest(session, FULL)
    first = {row.id for row in rows(session)}

    for _ in range(3):
        ingest(session, FULL)

    assert {row.id for row in rows(session)} == first
    assert len(active(session)) == 3


def test_unchanged_text_does_not_re_derive_at_all(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D22: *"ordinary ingestion never silently re-extracts the catalogue."*

    The job is unchanged, so the ingestion hook does not even call derivation — which is the
    behaviour that keeps re-ingesting a large catalogue from re-running every extractor.
    """
    ingest(session, FULL)

    calls = count_derivations(monkeypatch)
    ingest(session, FULL)

    assert calls == []
    assert len(active(session)) == 3


def test_an_update_that_leaves_the_text_alone_does_not_re_derive(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``_apply_updates`` reports a change for any of seventeen fields.

    A deadline or an apply-link edit changes the job without changing a single character a
    derivation was read from, and re-deriving for it would be work with no possible result.
    """
    ingest(session, FULL)

    calls = count_derivations(monkeypatch)
    ingest(session, FULL, role_title="Backend Engineer II")

    assert calls == []
    job = the_job(session)
    assert job.role_title == "Backend Engineer II"
    assert len(active(session)) == 3


def test_calling_the_service_directly_on_current_text_is_skipped(session: Session) -> None:
    """The second guard, below the ingestion trigger: already derived from this exact text."""
    job = seed_job(session, FULL)
    assert derive_for_job(session, job).status is DerivationStatus.COMPLETED
    session.commit()

    outcome = derive_for_job(session, job)
    assert outcome.status is DerivationStatus.SKIPPED
    assert (outcome.rows_created, outcome.rows_updated, outcome.rows_invalidated) == (0, 0, 0)


def test_skipping_runs_no_extractor(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = seed_job(session, FULL)
    derive_for_job(session, job)
    session.commit()

    def explode(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("extracted while skipping")

    monkeypatch.setattr(requirement_derivation, "extract_requirements", explode)
    assert derive_for_job(session, job).status is DerivationStatus.SKIPPED


def test_the_unique_constraint_is_respected_rather_than_worked_around(
    session: Session,
) -> None:
    """At most one row per (job, digest, requirement type), however many times it runs."""
    ingest(session, FULL)
    ingest(session, FULL)

    keys = [(r.job_id, r.source_text_digest, r.requirement_type) for r in rows(session)]
    assert len(keys) == len(set(keys))


def test_at_most_one_active_row_per_requirement_type(session: Session) -> None:
    ingest(session, FULL)
    ingest(session, CGPA_ONLY)
    ingest(session, FULL)

    types = [row.requirement_type for row in active(session)]
    assert len(types) == len(set(types))


# ---------------------------------------------------------------------------------------
# Changed source text — invalidation
# ---------------------------------------------------------------------------------------


def test_a_changed_description_invalidates_the_old_rows(session: Session) -> None:
    ingest(session, FULL)
    old_ids = {row.id for row in rows(session)}

    ingest(session, CGPA_ONLY)

    superseded = [row for row in rows(session) if row.id in old_ids]
    assert len(superseded) == 3
    assert all(row.status is ExtractionStatus.INVALIDATED for row in superseded)
    assert all(row.invalidated_at is not None for row in superseded)


def test_invalidated_rows_are_never_deleted(session: Session) -> None:
    """A withdrawn requirement is as much a fact about the posting as a current one."""
    ingest(session, FULL)
    ingest(session, CGPA_ONLY)
    ingest(session, NO_CRITERIA)

    assert len(rows(session)) == 4
    assert len(active(session)) == 0


def test_new_rows_are_written_under_the_new_digest(session: Session) -> None:
    ingest(session, FULL)
    ingest(session, CGPA_ONLY)

    live = active(session)
    assert len(live) == 1
    assert live[0].requirement_type is RequirementType.MIN_CGPA
    assert live[0].min_cgpa == 8.0
    assert live[0].source_text_digest == source_text_digest(the_job(session).description)


def test_a_type_no_longer_verified_from_the_current_text_is_invalidated(
    session: Session,
) -> None:
    """Not merely left behind under an old digest — actively withdrawn.

    The new description states a CGPA and nothing else, so the graduation window and the
    backlog limit stop applying and must stop being active.
    """
    ingest(session, FULL)
    ingest(session, CGPA_ONLY)

    assert {row.requirement_type for row in active(session)} == {RequirementType.MIN_CGPA}


def test_a_returning_description_derives_a_new_row(session: Session) -> None:
    """A → B → A, end to end through real ingestion. **The case this PR was blocked on.**

    The returning text is derived afresh. The original rows stay invalidated beside the new
    ones, keeping the evidence and timestamps of the verification they actually recorded —
    a verification performed against text the system had since replaced is not evidence
    about the text it holds now.
    """
    digest_a = source_text_digest(pinned(FULL))

    ingest(session, FULL)
    original_a = {row.id for row in active(session)}
    assert len(original_a) == 3

    ingest(session, CGPA_ONLY)
    ingest(session, FULL)

    returning = active(session)
    assert len(returning) == 3, "the returning description is derived again, not skipped"
    assert {row.source_text_digest for row in returning} == {digest_a}
    assert {row.id for row in returning}.isdisjoint(original_a), "new rows, not revived ones"

    withdrawn = [row for row in rows(session) if row.id in original_a]
    assert len(withdrawn) == 3
    assert all(row.status is ExtractionStatus.INVALIDATED for row in withdrawn)
    assert all(row.invalidated_at is not None for row in withdrawn)


def test_the_original_rows_survive_a_returning_description(session: Session) -> None:
    """Nothing is deleted, and the history is still queryable for audit."""
    ingest(session, FULL)
    first = {row.id for row in rows(session)}
    ingest(session, CGPA_ONLY)
    second = {row.id for row in rows(session)} - first
    ingest(session, FULL)

    stored = {row.id for row in rows(session)}
    assert first <= stored and second <= stored
    assert len(stored) == len(first) + len(second) + 3


def test_an_invalidated_only_digest_is_never_current(session: Session) -> None:
    """The precise defect the correction removes, asserted on the predicate itself.

    Before the fix this returned ``SKIPPED`` and wrote nothing, because rows existed for
    the digest and the predicate never looked at their status.
    """
    ingest(session, FULL)
    ingest(session, CGPA_ONLY)

    job = the_job(session)
    stored = rows(session)
    digest_a = source_text_digest(pinned(FULL))
    at_a = [row for row in stored if row.source_text_digest == digest_a]
    assert at_a and all(not row.is_active for row in at_a), "the fixture must be history-only"

    assert requirement_derivation._is_current(stored, digest_a) is False

    job.description = pinned(FULL)
    session.commit()
    outcome = derive_for_job(session, job)
    assert outcome.status is DerivationStatus.COMPLETED
    assert outcome.rows_created == 3


def test_a_punctuation_only_change_still_triggers_re_derivation(session: Session) -> None:
    """The reason the digest exists and ``content_hash`` could not be the staleness key.

    ``compute_content_hash`` canonicalizes before hashing — lowercasing and stripping
    punctuation — so these two descriptions hash identically. The digest does not, and the
    stored evidence genuinely differs between them, so derivation must re-run.
    """
    first = "Eligibility: minimum CGPA 7.5/10 required."
    second = "Eligibility - Minimum CGPA 7.5/10 required"

    assert compute_content_hash(
        make_raw(description=first), "fake"
    ) == compute_content_hash(make_raw(description=second), "fake")
    assert source_text_digest(first) != source_text_digest(second)

    ingest(session, first)
    before = {row.id for row in active(session)}
    ingest(session, second)
    after = {row.id for row in active(session)}

    assert before and after and before != after
    assert len(active(session)) == 1
    assert active(session)[0].evidence_text == "Eligibility - Minimum CGPA 7.5/10 required"


# ---------------------------------------------------------------------------------------
# Extractor version — replacement in place
# ---------------------------------------------------------------------------------------


def test_a_stale_extractor_version_re_derives_the_same_row_in_place(
    session: Session,
) -> None:
    """D22's version trigger. Same text, same key, so the row is rewritten, not duplicated."""
    ingest(session, CGPA_ONLY)
    row = active(session)[0]
    original_id = row.id

    row.extractor_version = "0"
    session.commit()

    outcome = derive_for_job(session, the_job(session))
    session.commit()

    assert outcome.status is DerivationStatus.COMPLETED
    assert (outcome.rows_created, outcome.rows_updated) == (0, 1)
    assert len(rows(session)) == 1
    refreshed = rows(session)[0]
    assert refreshed.id == original_id
    assert refreshed.extractor_version == EXTRACTOR_VERSION
    assert refreshed.is_active


def test_replacement_clears_any_invalidation_timestamp(session: Session) -> None:
    """An active row carrying an invalidation time is incoherent and must not survive one."""
    ingest(session, CGPA_ONLY)
    row = active(session)[0]
    row.extractor_version = "0"
    row.invalidated_at = requirement_derivation._utcnow()
    session.commit()

    derive_for_job(session, the_job(session))
    session.commit()

    assert rows(session)[0].invalidated_at is None


def seed_row(
    session: Session,
    job: Job,
    requirement_type: RequirementType,
    *,
    version: str = "0",
    status: ExtractionStatus = ExtractionStatus.ACTIVE,
    **columns: object,
) -> ExtractedRequirement:
    """A derived row placed directly, for states ordinary ingestion reaches only slowly."""
    row = ExtractedRequirement(
        id=str(uuid.uuid4()),
        job_id=job.id,
        source_text_digest=source_text_digest(job.description),
        content_hash=job.content_hash,
        requirement_type=requirement_type,
        provenance=RequirementProvenance.PROSE_DERIVED,
        strength=RequirementStrength.REQUIRED,
        evidence_text="seeded",
        extractor="deterministic.seed",
        extractor_version=version,
        status=status,
        invalidated_at=(
            None if status is ExtractionStatus.ACTIVE else requirement_derivation._utcnow()
        ),
        **columns,
    )
    session.add(row)
    session.commit()
    return row


def test_a_type_no_longer_verified_at_the_same_digest_is_invalidated(
    session: Session,
) -> None:
    """The half of the invalidation rule a digest change cannot exercise.

    When the text changes, every old row is stale by digest alone. The ``requirement_type
    not in verified`` clause only earns its place when the digest is **unchanged** and a new
    extractor version reads fewer requirements out of the same sentence — exactly D22's
    replacement case. Without it that requirement would stay active forever, asserted
    against text that no longer supports it.
    """
    ingest(session, CGPA_ONLY)
    job = the_job(session)

    # Force a re-derivation, and give it a row for a type this text does not state.
    active(session)[0].extractor_version = "0"
    session.commit()
    orphan = seed_row(session, job, RequirementType.MAX_BACKLOGS, max_backlogs=2)

    derive_for_job(session, job)
    session.commit()

    assert by_type(session).keys() == {RequirementType.MIN_CGPA}
    session.refresh(orphan)
    assert orphan.status is ExtractionStatus.INVALIDATED
    assert orphan.invalidated_at is not None


def test_an_invalidated_row_at_the_current_digest_is_not_resurrected(
    session: Session,
) -> None:
    """``INVALIDATED`` is terminal even when the current text would verify it again.

    Reachable through a re-derivation at an unchanged digest: one type is already withdrawn,
    another is stale, so the loop runs and meets the withdrawn row. It is passed over and a
    **new** row is written beside it. Refreshing it would re-assert a verification that had
    been withdrawn, which is the one transition the model says does not exist.
    """
    ingest(session, FULL)
    stored = by_type(session)
    withdrawn = stored[RequirementType.MIN_CGPA]
    withdrawn.invalidate()
    for requirement_type in (
        RequirementType.GRAD_YEAR_WINDOW,
        RequirementType.MAX_BACKLOGS,
    ):
        stored[requirement_type].extractor_version = "0"
    session.commit()

    outcome = derive_for_job(session, the_job(session))
    session.commit()

    session.refresh(withdrawn)
    assert withdrawn.status is ExtractionStatus.INVALIDATED
    assert withdrawn.id not in {row.id for row in active(session)}
    assert outcome.rows_updated == 2, "the two in-force rows are rewritten in place"
    assert outcome.rows_created == 1, "the withdrawn type gets a NEW row, not its old one"
    assert by_type(session).keys() == {
        RequirementType.MIN_CGPA,
        RequirementType.GRAD_YEAR_WINDOW,
        RequirementType.MAX_BACKLOGS,
    }
    assert len(rows(session)) == 4, "the withdrawn row is kept beside the new one"


def test_ordinary_ingestion_does_not_re_extract_on_a_version_change(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D22 again, and the distinction that matters: the trigger, not the capability.

    The service re-derives a stale version when it is called. Ingestion does not call it for
    a job whose text is unchanged, so enabling a new extractor never silently rewrites the
    catalogue — that is the explicit re-extraction operation D22 defers elsewhere.
    """
    ingest(session, CGPA_ONLY)
    row = active(session)[0]
    row.extractor_version = "0"
    session.commit()

    calls = count_derivations(monkeypatch)
    ingest(session, CGPA_ONLY)

    assert calls == []
    assert rows(session)[0].extractor_version == "0"


# ---------------------------------------------------------------------------------------
# The verifier is the authority
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("description", "reason"),
    [
        ("Eligibility: CGPA 7.5/10 preferred.", "PREFERRED fails condition 7"),
        ("Eligibility: CGPA 7.5/10.", "no marker, strength not established"),
        ("Eligibility: typically CGPA 7.5/10.", "INFORMATIONAL fails condition 7"),
        ("Eligibility: minimum CGPA 7.5/10 required unless waived.", "ambiguous markers"),
        (
            "Minimum CGPA 7.5/10 required. This requirement is waived for some candidates.",
            "contradicted within the window",
        ),
        (
            "Minimum CGPA 7.0/10 required. CGPA 7.5/10 preferred.",
            "competing values, neither promoted",
        ),
        ("The role requires 7.5 years of experience.", "not a grade at all"),
        ("Minimum CGPA 7.5 required.", "no explicit scale"),
    ],
)
def test_a_proposal_the_verifier_refuses_is_never_persisted(
    session: Session, description: str, reason: str
) -> None:
    """Nothing refused is stored, downgraded, or kept as a weaker observation (D6, D10)."""
    ingest(session, description)
    assert rows(session) == [], reason


def test_seven_point_five_years_of_experience_creates_no_cgpa_row(
    session: Session,
) -> None:
    """The canonical false positive, asserted end to end through the real pipeline."""
    ingest(session, "Backend Engineer. The role requires 7.5 years of experience.")
    assert not [r for r in rows(session) if r.requirement_type is RequirementType.MIN_CGPA]


def test_only_verified_requirements_reach_storage(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A verifier that promotes nothing stores nothing, whatever the extractors proposed.

    The extractors are left alone and only the verifier is neutralised, so this fails if
    anything ever writes a row from a proposal rather than from an outcome.
    """
    from app.schemas.extraction import CollectionVerification

    monkeypatch.setattr(
        requirement_derivation,
        "verify_proposals",
        lambda *_a, **_k: CollectionVerification(verified=(), outcomes=()),
    )
    ingest(session, FULL)
    assert rows(session) == []


def test_stored_rows_are_always_prose_derived_and_required(session: Session) -> None:
    """Both are ``Literal`` on the verified type, so a wrong one is unconstructible."""
    ingest(session, FULL)
    for row in rows(session):
        assert row.provenance is RequirementProvenance.PROSE_DERIVED
        assert row.strength is RequirementStrength.REQUIRED


# ---------------------------------------------------------------------------------------
# Fail-closed
# ---------------------------------------------------------------------------------------


def _boom(*_args: object, **_kwargs: object) -> object:
    raise RuntimeError("deliberate failure with 'quoted description' inside")


def test_an_extractor_exception_does_not_fail_ingestion(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(requirement_derivation, "extract_requirements", _boom)
    ingest(session, FULL)

    assert the_job(session) is not None
    assert rows(session) == []


def test_a_verifier_exception_does_not_fail_ingestion(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(requirement_derivation, "verify_proposals", _boom)
    ingest(session, FULL)

    assert the_job(session) is not None
    assert rows(session) == []


def test_a_failure_is_reported_as_unavailable_not_as_zero_requirements(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(requirement_derivation, "extract_requirements", _boom)
    job = seed_job(session, FULL)

    outcome = derive_for_job(session, job)
    assert outcome.status is DerivationStatus.UNAVAILABLE
    assert (outcome.verified, outcome.rows_created, outcome.rows_invalidated) == (0, 0, 0)


def test_a_failure_leaves_existing_rows_untouched(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unavailable means *the system learned nothing*, not *the requirements went away*."""
    ingest(session, FULL)
    before = {(r.id, r.status) for r in rows(session)}

    monkeypatch.setattr(requirement_derivation, "extract_requirements", _boom)
    ingest(session, CGPA_ONLY)

    assert {(r.id, r.status) for r in rows(session)} == before


def test_a_persistence_failure_leaves_no_partial_row_and_no_broken_ingestion(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A row the database refuses must take nothing else with it.

    The stand-in writes a row violating the ``strength = 'REQUIRED'`` check and returns
    normally, so the failure happens at commit — the hardest place for a partial write to be
    cleaned up correctly.
    """

    def writes_a_bad_row(db: Session, job: Job) -> object:
        db.add(
            ExtractedRequirement(
                id=str(uuid.uuid4()),
                job_id=job.id,
                source_text_digest=source_text_digest(job.description),
                content_hash=job.content_hash,
                requirement_type=RequirementType.MIN_CGPA,
                provenance=RequirementProvenance.PROSE_DERIVED,
                strength=RequirementStrength.PREFERRED,
                min_cgpa=7.5,
                min_cgpa_scale=GradeScale.SCALE_10,
                evidence_text="CGPA 7.5/10 preferred",
                extractor="deterministic.cgpa",
                extractor_version=EXTRACTOR_VERSION,
            )
        )
        return requirement_derivation.DerivationOutcome(
            status=DerivationStatus.COMPLETED, source_text_digest="x" * 64
        )

    monkeypatch.setattr(job_ingestion, "derive_for_job", writes_a_bad_row)
    ingest(session, FULL)

    assert the_job(session) is not None
    assert rows(session) == []


def test_one_job_failing_does_not_stop_the_next(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = requirement_derivation.extract_requirements
    calls = {"n": 0}

    def fails_first(description: str) -> object:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("first job only")
        return real(description)

    monkeypatch.setattr(requirement_derivation, "extract_requirements", fails_first)
    ingest_source(
        session,
        FakeAdapter(
            [
                make_raw(description=FULL, source_job_id="A"),
                make_raw(description=CGPA_ONLY, source_job_id="B"),
            ]
        ),
        settings=ENABLED,
    )

    assert len(session.execute(select(Job)).scalars().all()) == 2
    assert {row.requirement_type for row in active(session)} == {RequirementType.MIN_CGPA}


def test_no_fallback_requirement_is_ever_fabricated(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(requirement_derivation, "extract_requirements", _boom)
    for description in (FULL, CGPA_ONLY, NO_CRITERIA):
        ingest(session, description, source_job_id=description[:10])
    assert rows(session) == []


# ---------------------------------------------------------------------------------------
# What gets stored
# ---------------------------------------------------------------------------------------


def test_a_cgpa_requirement_stores_its_value_and_scale(session: Session) -> None:
    ingest(session, FULL)
    row = by_type(session)[RequirementType.MIN_CGPA]

    assert row.min_cgpa == 7.5
    assert row.min_cgpa_scale is GradeScale.SCALE_10
    assert (row.min_grad_year, row.max_grad_year, row.max_backlogs) == (None, None, None)


def test_a_graduation_window_stores_both_bounds(session: Session) -> None:
    ingest(session, FULL)
    row = by_type(session)[RequirementType.GRAD_YEAR_WINDOW]

    assert (row.min_grad_year, row.max_grad_year) == (2025, 2026)
    assert (row.min_cgpa, row.min_cgpa_scale, row.max_backlogs) == (None, None, None)


def test_a_backlog_limit_stores_its_count_including_zero(session: Session) -> None:
    ingest(session, FULL)
    row = by_type(session)[RequirementType.MAX_BACKLOGS]

    assert row.max_backlogs == 0
    assert (row.min_cgpa, row.min_grad_year, row.max_grad_year) == (None, None, None)


def test_stored_evidence_is_verbatim_from_the_pinned_description(session: Session) -> None:
    """Condition 4's guarantee, carried all the way into storage."""
    ingest(session, FULL)
    description = the_job(session).description
    for row in rows(session):
        assert row.evidence_text and row.evidence_text in description


def test_stored_rows_carry_the_deterministic_extractor_identity(session: Session) -> None:
    ingest(session, FULL)
    identities = {row.extractor for row in rows(session)}

    assert identities == {
        "deterministic.cgpa",
        "deterministic.grad_year",
        "deterministic.backlogs",
    }
    assert {row.extractor_version for row in rows(session)} == {EXTRACTOR_VERSION}


def test_a_deterministic_row_names_no_provider_and_no_model(session: Session) -> None:
    ingest(session, FULL)
    for row in rows(session):
        assert row.provider is None
        assert row.model is None


def test_stored_rows_carry_the_digest_and_the_hash_for_their_own_purposes(
    session: Session,
) -> None:
    ingest(session, FULL)
    job = the_job(session)
    for row in rows(session):
        assert row.source_text_digest == source_text_digest(job.description)
        assert row.content_hash == job.content_hash
        assert row.status is ExtractionStatus.ACTIVE
        assert row.invalidated_at is None
        assert row.extracted_at is not None


def test_the_digest_is_sha256_of_the_description_exactly_as_stored() -> None:
    """Pinned against the literal definition, not against the implementation."""
    text = "Eligibility: minimum CGPA 7.5/10 required."
    assert source_text_digest(text) == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert len(source_text_digest(text)) == 64


def test_the_stored_description_is_already_the_pinned_normalized_text() -> None:
    """D9's definition holds because ``normalize_job`` collapses whitespace on the way in.

    If that ever stopped being true, evidence quoted from a re-collapsed string would not be
    locatable in the stored one and the verifier would silently promote nothing.
    """
    from app.services.job_normalizer import collapse_whitespace

    messy = "Eligibility:\n\n   minimum CGPA 7.5/10\t\trequired.  "
    stored = normalize_job(make_raw(description=messy), "fake").description
    assert stored == collapse_whitespace(stored)


# ---------------------------------------------------------------------------------------
# The content-hash boundary (D17)
# ---------------------------------------------------------------------------------------


def test_derivation_does_not_change_the_job_content_hash(session: Session) -> None:
    """The stored hash is exactly what the normalizer computed, derivation notwithstanding."""
    raw = make_raw(description=FULL)
    ingest_source(session, FakeAdapter([raw]), settings=ENABLED)

    assert len(active(session)) == 3
    assert the_job(session).content_hash == compute_content_hash(raw, "fake")


def test_derived_values_never_land_in_a_job_column(session: Session) -> None:
    """D16's second hazard: ``_apply_updates`` would erase them on the next run anyway."""
    ingest(session, FULL, min_cgpa=None, min_cgpa_scale=None)
    job = the_job(session)

    assert len(active(session)) == 3, "the fixture must actually derive something"
    assert job.min_cgpa is None
    assert job.min_cgpa_scale is None
    assert job.min_grad_year is None
    assert job.max_grad_year is None
    assert job.max_backlogs is None
    assert job.requirements in (None, {})


def test_derivation_does_not_overwrite_a_source_stated_column(session: Session) -> None:
    """The source says 7.0 and the prose says 7.5. The column must still say 7.0.

    This is the sharper half of D16: the hazard is not only an empty column being filled,
    but a **source-stated** value being replaced by a derived one of lower authority (D1).
    """
    ingest(session, FULL, min_cgpa=7.0, min_cgpa_scale="SCALE_10")
    job = the_job(session)

    assert job.min_cgpa == 7.0
    assert by_type(session)[RequirementType.MIN_CGPA].min_cgpa == 7.5


def test_a_second_ingestion_after_derivation_reports_the_job_unchanged(
    session: Session,
) -> None:
    """D16's first hazard: a derived value inside the hash would make the job churn forever."""
    ingest(session, FULL)
    outcome = ingest_source(
        session, FakeAdapter([make_raw(description=FULL)]), settings=ENABLED
    )
    assert (outcome.jobs_updated, outcome.jobs_unchanged) == (0, 1)


def test_the_derivation_module_never_touches_the_content_hash() -> None:
    """Checked on parsed imports and calls, not on text.

    The module's docstring explains at length why ``compute_content_hash`` is *not* the
    staleness key, so a substring search finds the name and proves nothing.
    """
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "compute_content_hash" not in imported
    assert "compute_content_hash" not in called

    # Nothing assigns to a job attribute at all: the job is read, never written.
    assigned = {
        target.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Attribute)
        and isinstance(target.value, ast.Name)
        and target.value.id == "job"
    }
    assert assigned == set()


def test_updatable_fields_gained_nothing(session: Session) -> None:
    """``_UPDATABLE_FIELDS`` is source-owned data only; nothing derived may join it."""
    assert len(job_ingestion._UPDATABLE_FIELDS) == 17
    assert not [
        field
        for field in job_ingestion._UPDATABLE_FIELDS
        if "extract" in field or "derived" in field or "provenance" in field
    ]


# ---------------------------------------------------------------------------------------
# Purity, privacy and the boundaries that must stay closed
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "forbidden",
    [
        "fastapi",
        "httpx",
        "requests",
        "logging",
        "subprocess",
        "socket",
        "urllib",
        "google",
        "openai",
        "anthropic",
        "app.ai",
        "app.adapters",
        "app.routers",
        "app.config",
        "app.main",
    ],
)
def test_derivation_imports_no_framework_provider_network_or_logger(
    forbidden: str,
) -> None:
    """Database access is permitted here; everything else on this list is not.

    Parsed from the real import statements, so a module named in a docstring cannot pass or
    fail this by accident.
    """
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    offenders = {
        name for name in imported if name == forbidden or name.startswith(f"{forbidden}.")
    }
    assert not offenders, f"{MODULE.name} imports {sorted(offenders)}"


def test_derivation_accesses_the_database_deliberately() -> None:
    """The counterpart to the test above: this layer *is* the persistence boundary."""
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "sqlalchemy.orm" in imported


def test_derivation_defines_no_logger() -> None:
    """The caller logs counts it already holds. Nothing here can reach a description."""
    source = MODULE.read_text(encoding="utf-8")
    for marker in ("getLogger", "logging.", "logger", "print("):
        assert marker not in source, f"{MODULE.name} contains {marker!r}"


@pytest.mark.parametrize(
    "forbidden", ["CandidateProfile", "ResumeExtraction", "EligibilityResult"]
)
def test_derivation_imports_no_candidate_type(forbidden: str) -> None:
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert forbidden not in imported


def test_no_public_function_here_takes_candidate_data() -> None:
    for function in (derive_for_job, source_text_digest):
        parameters = list(inspect.signature(function).parameters)
        assert not [
            p
            for p in parameters
            if any(term in p.lower() for term in ("candidate", "profile", "resume", "user"))
        ]


def test_a_derived_row_has_no_candidate_column(session: Session) -> None:
    ingest(session, FULL)
    columns = {column.name for column in ExtractedRequirement.__table__.columns}
    assert not [
        name
        for name in columns
        if any(
            term in name
            for term in ("candidate", "applicant", "resume", "profile", "person", "email")
        )
    ]
    assert {fk.target_fullname for fk in ExtractedRequirement.__table__.foreign_keys} == {
        "jobs.id"
    }


def test_no_description_or_evidence_reaches_a_log(
    session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    """INV-4 and D24, asserted with markers distinctive enough that a leak is unambiguous."""
    marker = "ZQXMARKERQZ"
    description = f"{marker}. Eligibility: minimum CGPA 7.5/10 required."

    with caplog.at_level(logging.DEBUG):
        ingest(session, description)

    assert active(session), "the fixture must actually derive something"
    evidence = active(session)[0].evidence_text
    for record in caplog.records:
        message = record.getMessage()
        assert marker not in message
        assert evidence not in message
        assert "CGPA" not in message


def test_the_derivation_log_line_carries_counts_only(
    session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="eligicore.ingestion"):
        ingest(session, FULL)

    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("derivation")]
    assert len(lines) == 1
    assert "rows_created=3" in lines[0]
    assert the_job(session).id not in lines[0]


# ---------------------------------------------------------------------------------------
# Derivation is reachable from ingestion and from nowhere else
# ---------------------------------------------------------------------------------------


def test_no_router_references_derivation_or_extraction() -> None:
    """D21: extraction runs at ingestion time, never from a request."""
    for path in sorted(pathlib.Path("app/routers").rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        for symbol in (
            "requirement_derivation",
            "derive_for_job",
            "requirement_extractors",
            "extract_requirements",
            "ExtractedRequirement",
        ):
            assert symbol not in source, f"{path} references {symbol}"


def test_only_ingestion_imports_the_orchestration_service() -> None:
    """One caller in the application, so the trigger rule has exactly one place to live."""
    callers = []
    for path in sorted(pathlib.Path("app").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == (
                "app.services.requirement_derivation"
            ):
                callers.append(path.as_posix())
    assert callers == ["app/services/job_ingestion.py"]


def test_an_eligibility_request_derives_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Asserted by running a real request against the real application, not by inspection."""
    from collections.abc import Iterator as _Iterator

    from fastapi.testclient import TestClient
    from sqlalchemy.pool import StaticPool

    from app.database import get_db
    from app.main import app

    def explode(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("an eligibility request triggered derivation")

    monkeypatch.setattr(requirement_derivation, "derive_for_job", explode)
    monkeypatch.setattr(job_ingestion, "derive_for_job", explode)

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as seed:
        seed_job(seed, FULL)

    def override_get_db() -> _Iterator[Session]:
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        payload: dict[str, Any] = {
            "profile": {
                "education": [
                    {
                        "institution": "Example Institute",
                        "degree_level": "BACHELORS",
                        "field_of_study": "Computer Science",
                        "cgpa": 8.0,
                        "cgpa_scale": "SCALE_10",
                        "graduation_year": 2026,
                        "backlogs": 0,
                    }
                ],
                "skills": ["Python"],
            }
        }
        response = client.post("/api/v1/eligibility/check", json=payload)
        assert response.status_code in (200, 422)
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(engine)
