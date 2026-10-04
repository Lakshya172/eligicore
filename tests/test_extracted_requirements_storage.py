"""Storage tests for ``extracted_requirements`` (ADR-030 D16-D19).

Four things are being pinned here, and they are different kinds of claim.

**The schema**, because a column that is nullable when it should not be is a defect nobody
notices until a row is wrong. **The constraints**, because four of them encode ADR-030
decisions rather than data types — a ``PREFERRED`` requirement reaching evaluation should be
a database error, not a code review finding. **The boundary**, because this table must stay
outside ``compute_content_hash`` and outside the ingestion update path or it reintroduces the
two hazards D16 exists to avoid. And **privacy**, because a table about job postings must
never acquire a column about a person.

Every fixture is a synthetic job posting. There is no candidate anywhere in this file, and
there is no column for one.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import pathlib
import uuid
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import get_type_hints

import pytest
from sqlalchemy import UniqueConstraint, create_engine, inspect as sa_inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models import extracted_requirement as model_module
from app.models.extracted_requirement import ExtractedRequirement, ExtractionStatus
from app.models.job import Job, JobStatus
from app.schemas.candidate import GradeScale, JobType
from app.schemas.eligibility import RequirementType
from app.schemas.extraction import RequirementProvenance, RequirementStrength
from app.schemas.job import RawJob
from app.services.job_ingestion import _UPDATABLE_FIELDS
from app.services.job_normalizer import compute_content_hash, normalize_job
from tests.conftest import ALLOWED_OPERATIONAL_TABLES, FORBIDDEN_TABLES

TABLE = "extracted_requirements"
SEEDED_AT = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
DESCRIPTION = "Eligibility: minimum CGPA 7.5/10 required. Apply online."


def digest(text: str) -> str:
    """The pinned-text digest, computed the way the storage contract defines it."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@pytest.fixture
def session() -> Iterator[Session]:
    """An isolated in-memory database per test, matching the ingestion tests' fixture."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        yield db
    Base.metadata.drop_all(engine)


@pytest.fixture
def job(session: Session) -> Job:
    """One stored posting for derived rows to hang off."""
    raw = RawJob(
        company_name="Example Analytics",
        role_title="Software Engineering Intern",
        job_type=JobType.INTERNSHIP,
        description=DESCRIPTION,
        source_job_id="EX-001",
    )
    normalized = normalize_job(raw, "curated")
    record = Job(
        id=str(uuid.uuid4()),
        source=normalized.source,
        source_job_id=normalized.source_job_id,
        status=JobStatus.ACTIVE,
        last_verified_at=SEEDED_AT,
        created_at=SEEDED_AT,
        updated_at=SEEDED_AT,
        **{field: getattr(normalized, field) for field in _UPDATABLE_FIELDS},
    )
    session.add(record)
    session.commit()
    return record


def derived(job: Job, **overrides: object) -> ExtractedRequirement:
    """A valid `MIN_CGPA` row. Overrides vary exactly one thing per test."""
    fields: dict[str, object] = {
        "id": str(uuid.uuid4()),
        "job_id": job.id,
        "source_text_digest": digest(job.description),
        "content_hash": job.content_hash,
        "requirement_type": RequirementType.MIN_CGPA,
        "provenance": RequirementProvenance.PROSE_DERIVED,
        "strength": RequirementStrength.REQUIRED,
        "min_cgpa": 7.5,
        "min_cgpa_scale": GradeScale.SCALE_10,
        "evidence_text": "minimum CGPA 7.5/10 required",
        "extractor": "deterministic.cgpa",
        "extractor_version": "v1",
        "extracted_at": SEEDED_AT,
        "status": ExtractionStatus.ACTIVE,
    }
    fields.update(overrides)
    return ExtractedRequirement(**fields)


def store(session: Session, row: ExtractedRequirement) -> None:
    """Persist a row, so a constraint violation surfaces here rather than at teardown."""
    session.add(row)
    session.commit()


# ---------------------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------------------


def test_the_table_exists_and_is_on_the_allowlist(session: Session) -> None:
    """A new operational table is admitted deliberately, never by exemption."""
    assert TABLE in sa_inspect(session.get_bind()).get_table_names()
    assert TABLE in ALLOWED_OPERATIONAL_TABLES
    assert set(Base.metadata.tables) == ALLOWED_OPERATIONAL_TABLES


EXPECTED_COLUMNS: dict[str, bool] = {
    # column -> nullable
    "id": False,
    "job_id": False,
    "source_text_digest": False,
    "content_hash": False,
    "requirement_type": False,
    "provenance": False,
    "strength": False,
    "min_cgpa": True,
    "min_cgpa_scale": True,
    "min_grad_year": True,
    "max_grad_year": True,
    "max_backlogs": True,
    "evidence_text": False,
    "extractor": False,
    "extractor_version": False,
    "provider": True,
    "model": True,
    "extracted_at": False,
    "status": False,
    "invalidated_at": True,
}


def test_the_column_set_is_exactly_what_the_contract_names(session: Session) -> None:
    """No extra column, and none missing — the set is asserted, not merely contained."""
    columns = {c["name"] for c in sa_inspect(session.get_bind()).get_columns(TABLE)}

    assert columns == set(EXPECTED_COLUMNS)


@pytest.mark.parametrize(("column", "nullable"), sorted(EXPECTED_COLUMNS.items()))
def test_column_nullability_is_explicit(
    session: Session, column: str, nullable: bool
) -> None:
    """Nullability is declared rather than incidental (QG-006 item 10)."""
    actual = {
        c["name"]: c["nullable"] for c in sa_inspect(session.get_bind()).get_columns(TABLE)
    }

    assert actual[column] is nullable


def test_extraction_status_has_exactly_two_members() -> None:
    """``ACTIVE`` and ``INVALIDATED``, and no third state (ADR-030 storage contract)."""
    assert [s.value for s in ExtractionStatus] == ["ACTIVE", "INVALIDATED"]


def test_enums_are_stored_as_varchar_with_a_check_not_a_native_type(
    session: Session,
) -> None:
    """``native_enum=False`` on every enum column, so SQLite and PostgreSQL agree (ADR-009).

    A PostgreSQL native enum type is not expressible in SQLite, which is why the whole
    schema uses VARCHAR plus a CHECK instead. Asserted on the reflected type rather than on
    the model, because the model's intent is not what the database ends up holding.
    """
    types = {
        c["name"]: str(c["type"]) for c in sa_inspect(session.get_bind()).get_columns(TABLE)
    }

    for column in ("requirement_type", "provenance", "strength", "min_cgpa_scale", "status"):
        assert types[column].startswith("VARCHAR"), (column, types[column])


def test_the_declared_indexes_exist(session: Session) -> None:
    """Three ordinary indexes for the read path, plus the ACTIVE-only uniqueness index."""
    names = {ix["name"] for ix in sa_inspect(session.get_bind()).get_indexes(TABLE)}

    assert {
        "ix_extracted_requirements_job_id",
        "ix_extracted_requirements_source_text_digest",
        "ix_extracted_requirements_status",
        "uq_extracted_requirements_one_active",
    } <= names


def test_the_table_declares_no_total_unique_constraint() -> None:
    """The old key is gone, not merely unused.

    A total UNIQUE over (job_id, source_text_digest, requirement_type) is what made the
    A -> B -> A history unrepresentable, and leaving it in place beside the partial index
    would restore the problem while the new tests kept passing.
    """
    table = Base.metadata.tables[TABLE]
    assert [c.name for c in table.constraints if isinstance(c, UniqueConstraint)] == []


# ---------------------------------------------------------------------------------------
# Valid rows, one per Phase 1 requirement type
# ---------------------------------------------------------------------------------------


def test_a_valid_cgpa_row_is_accepted(session: Session, job: Job) -> None:
    """The ordinary case: a grade and its scale, with every other typed column null."""
    store(session, derived(job))
    stored = session.execute(select(ExtractedRequirement)).scalar_one()

    assert stored.min_cgpa == 7.5
    assert stored.min_cgpa_scale is GradeScale.SCALE_10
    assert stored.is_active


def test_a_valid_graduation_year_row_is_accepted(session: Session, job: Job) -> None:
    """Either bound alone is a window, so only one of the two need be populated."""
    store(
        session,
        derived(
            job,
            requirement_type=RequirementType.GRAD_YEAR_WINDOW,
            min_cgpa=None,
            min_cgpa_scale=None,
            min_grad_year=2026,
            evidence_text="required: 2026 graduating batch",
        ),
    )

    assert session.execute(select(ExtractedRequirement)).scalar_one().min_grad_year == 2026


def test_a_valid_backlog_row_is_accepted(session: Session, job: Job) -> None:
    """Zero is a real limit, and must not be confused with an absent one."""
    store(
        session,
        derived(
            job,
            requirement_type=RequirementType.MAX_BACKLOGS,
            min_cgpa=None,
            min_cgpa_scale=None,
            max_backlogs=0,
            evidence_text="candidates must have no active backlogs",
        ),
    )

    assert session.execute(select(ExtractedRequirement)).scalar_one().max_backlogs == 0


def test_the_deterministic_path_stores_no_provider_or_model(
    session: Session, job: Job
) -> None:
    """Phase 1 uses no provider and no model, so both stay null (ADR-030 D11, D18)."""
    store(session, derived(job))
    stored = session.execute(select(ExtractedRequirement)).scalar_one()

    assert stored.provider is None
    assert stored.model is None
    assert stored.extractor == "deterministic.cgpa"
    assert stored.extractor_version == "v1"


# ---------------------------------------------------------------------------------------
# Constraints that encode decisions (ADR-030 D1, D10, D11)
# ---------------------------------------------------------------------------------------


def test_a_second_active_row_for_the_same_job_and_type_is_rejected(
    session: Session, job: Job
) -> None:
    """**At most one ACTIVE derivation per job and requirement type.**

    This is what makes "at most one requirement of this type is in force" a property of the
    database rather than of whichever code path happens to be writing. It replaces the old
    total key, and it is stricter in the direction that matters: the old key compared the
    digest too, so two ACTIVE rows under two digests were permitted and only application
    code prevented them.
    """
    store(session, derived(job))

    with pytest.raises(IntegrityError):
        store(session, derived(job, min_cgpa=8.0, evidence_text="minimum CGPA 8.0/10"))


def test_a_second_active_row_under_a_different_digest_is_also_rejected(
    session: Session, job: Job
) -> None:
    """The case the old key allowed. Changing the digest does not buy a second live row."""
    store(session, derived(job))

    with pytest.raises(IntegrityError):
        store(
            session,
            derived(
                job,
                source_text_digest=digest("A different description."),
                min_cgpa=8.0,
            ),
        )


def test_the_same_type_is_accepted_under_a_different_digest(
    session: Session, job: Job
) -> None:
    """A changed description is a new derivation, not a duplicate.

    The old row stays, invalidated; the new one is written under the recomputed digest.
    Uniqueness applies to the live row, so the withdrawn one is no obstacle.
    """
    first = derived(job)
    store(session, first)
    first.invalidate(SEEDED_AT)
    store(session, derived(job, source_text_digest=digest("A different description.")))

    assert len(session.execute(select(ExtractedRequirement)).scalars().all()) == 2


def test_two_invalidated_rows_at_the_same_digest_and_type_are_allowed(
    session: Session, job: Job
) -> None:
    """History may repeat. Nothing constrains rows that have been withdrawn."""
    first = derived(job)
    store(session, first)
    first.invalidate(SEEDED_AT)

    second = derived(job)
    store(session, second)
    second.invalidate(SEEDED_AT)

    rows = session.execute(select(ExtractedRequirement)).scalars().all()
    assert len(rows) == 2
    assert {r.source_text_digest for r in rows} == {digest(job.description)}
    assert all(r.status is ExtractionStatus.INVALIDATED for r in rows)


def test_an_active_row_may_sit_beside_an_invalidated_one_at_the_same_digest(
    session: Session, job: Job
) -> None:
    """The shape the correction exists for: the same text derived twice, once in force."""
    old = derived(job)
    store(session, old)
    old.invalidate(SEEDED_AT)
    store(session, derived(job, min_cgpa=8.0, evidence_text="minimum CGPA 8.0/10"))

    rows = sorted(
        session.execute(select(ExtractedRequirement)).scalars().all(),
        key=lambda r: r.status.value,
    )
    assert [r.status for r in rows] == [
        ExtractionStatus.ACTIVE,
        ExtractionStatus.INVALIDATED,
    ]
    assert {r.source_text_digest for r in rows} == {digest(job.description)}


def test_the_a_b_a_lifecycle_is_representable(session: Session, job: Job) -> None:
    """The whole owner ruling, in one sequence.

    A is derived and withdrawn, B is derived and withdrawn, and A returns as a **new** row.
    No row is reactivated, no row is deleted, and exactly one derivation is in force at the
    end — the new one, under A's digest.
    """
    digest_a = digest(job.description)
    digest_b = digest("A materially different description.")

    first_a = derived(job, source_text_digest=digest_a)
    store(session, first_a)
    assert first_a.is_active

    # The description changes to B.
    first_a.invalidate(SEEDED_AT)
    b = derived(job, source_text_digest=digest_b, min_cgpa=8.0)
    store(session, b)

    # And changes back to A. The original A row is still there, still withdrawn.
    b.invalidate(SEEDED_AT)
    second_a = derived(job, source_text_digest=digest_a)
    store(session, second_a)

    rows = session.execute(select(ExtractedRequirement)).scalars().all()
    assert len(rows) == 3, "no row was replaced or removed"
    assert second_a.id != first_a.id, "the returning derivation is a new row"

    active = [r for r in rows if r.is_active]
    assert [r.id for r in active] == [second_a.id]
    assert active[0].source_text_digest == digest_a

    assert first_a.status is ExtractionStatus.INVALIDATED
    assert first_a.invalidated_at is not None
    assert b.status is ExtractionStatus.INVALIDATED


def test_the_a_b_a_lifecycle_deletes_nothing(session: Session, job: Job) -> None:
    """Row ids are recorded up front, so a silent replacement cannot pass as a survival."""
    digest_a = digest(job.description)
    digest_b = digest("A materially different description.")

    first_a = derived(job, source_text_digest=digest_a)
    store(session, first_a)
    first_a.invalidate(SEEDED_AT)
    b = derived(job, source_text_digest=digest_b, min_cgpa=8.0)
    store(session, b)
    b.invalidate(SEEDED_AT)

    historical = {first_a.id, b.id}
    second_a = derived(job, source_text_digest=digest_a)
    store(session, second_a)

    stored = {r.id for r in session.execute(select(ExtractedRequirement)).scalars()}
    assert historical <= stored
    assert stored == historical | {second_a.id}


def test_source_stated_provenance_is_rejected(session: Session, job: Job) -> None:
    """A source-stated requirement lives in a ``jobs`` column and has no extraction path (D1)."""
    with pytest.raises(IntegrityError):
        store(session, derived(job, provenance=RequirementProvenance.SOURCE_STATED))


@pytest.mark.parametrize(
    "strength",
    [
        RequirementStrength.PREFERRED,
        RequirementStrength.CONDITIONAL,
        RequirementStrength.INFORMATIONAL,
    ],
)
def test_non_required_strength_is_rejected(
    session: Session, job: Job, strength: RequirementStrength
) -> None:
    """Only ``REQUIRED`` is ever stored (D10, OD-5).

    The verifier already discards everything else, so this is defence in depth — and it is
    the kind that matters: it makes "a `PREFERRED` statement gated eligibility" a constraint
    violation rather than something a reviewer has to notice.
    """
    with pytest.raises(IntegrityError):
        store(session, derived(job, strength=strength))


def test_an_unknown_grade_scale_is_rejected(session: Session, job: Job) -> None:
    """A grade with no scale is comparable to nothing, so it is not a storable requirement."""
    with pytest.raises(IntegrityError):
        store(session, derived(job, min_cgpa_scale=GradeScale.UNKNOWN))


@pytest.mark.parametrize(
    ("label", "overrides"),
    [
        ("cgpa row with no scale", {"min_cgpa_scale": None}),
        ("cgpa row with no grade", {"min_cgpa": None}),
        ("cgpa row carrying a backlog limit", {"max_backlogs": 2}),
        ("cgpa row carrying a year", {"min_grad_year": 2026}),
        (
            "year row with neither bound",
            {
                "requirement_type": RequirementType.GRAD_YEAR_WINDOW,
                "min_cgpa": None,
                "min_cgpa_scale": None,
            },
        ),
        (
            "year row carrying a grade",
            {
                "requirement_type": RequirementType.GRAD_YEAR_WINDOW,
                "min_grad_year": 2026,
            },
        ),
        (
            "backlog row with no count",
            {
                "requirement_type": RequirementType.MAX_BACKLOGS,
                "min_cgpa": None,
                "min_cgpa_scale": None,
            },
        ),
        (
            "backlog row carrying a grade",
            {"requirement_type": RequirementType.MAX_BACKLOGS, "max_backlogs": 1},
        ),
    ],
)
def test_typed_value_columns_must_match_the_requirement_type(
    session: Session, job: Job, label: str, overrides: dict[str, object]
) -> None:
    """Each type populates its own columns and leaves every other one null."""
    with pytest.raises(IntegrityError):
        store(session, derived(job, **overrides))


@pytest.mark.parametrize(
    "excluded", [RequirementType.MIN_DEGREE_LEVEL, RequirementType.ALLOWED_FIELDS]
)
def test_requirement_types_outside_phase_1_cannot_be_stored(
    session: Session, job: Job, excluded: RequirementType
) -> None:
    """D12 excludes degree-level mapping and field ontology from extraction permanently.

    Both are real ``RequirementType`` members, so the column's own enum check admits them.
    What refuses them is the value-column constraint being **exhaustive by omission**: a row
    for either satisfies no branch, whatever columns it populates.
    """
    with pytest.raises(IntegrityError):
        store(session, derived(job, requirement_type=excluded))


# ---------------------------------------------------------------------------------------
# Status lifecycle
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("status", list(ExtractionStatus))
def test_both_statuses_are_accepted(
    session: Session, job: Job, status: ExtractionStatus
) -> None:
    """Both members are storable; the lifecycle rule is about transitions, not values."""
    store(session, derived(job, status=status))

    assert session.execute(select(ExtractedRequirement)).scalar_one().status is status


def test_a_third_status_is_rejected(session: Session, job: Job) -> None:
    """The enum check is closed, so an invented state fails at the database."""
    with pytest.raises(IntegrityError):
        store(session, derived(job, status="SUPERSEDED"))


def test_invalidate_is_the_only_transition_and_records_when(
    session: Session, job: Job
) -> None:
    """``ACTIVE -> INVALIDATED``, with a timestamp, and nothing in the other direction."""
    row = derived(job)
    store(session, row)
    assert row.is_active and row.invalidated_at is None

    row.invalidate(SEEDED_AT)
    session.commit()

    assert row.status is ExtractionStatus.INVALIDATED
    assert row.invalidated_at == SEEDED_AT
    assert not row.is_active


def test_the_model_offers_no_way_back_to_active() -> None:
    """``INVALIDATED`` is terminal, and the model encodes no reverse transition.

    A database CHECK cannot express a transition rule — it sees one row, not the row it
    replaced — and a trigger would be neither portable nor in scope. The guarantee is
    therefore structural in the model: there is exactly one mutator, it moves one way, and
    no source line sets the status back.
    """
    source = inspect.getsource(model_module)
    mutators = {
        node.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
    }

    assert mutators == {"is_active", "invalidate"}
    assert "ExtractionStatus.ACTIVE" not in source.split("def invalidate")[1]
    assert "reactivate" not in source and "restore" not in source


def test_an_invalidated_row_is_never_reported_as_active(session: Session, job: Job) -> None:
    """``is_active`` is derived from ``status`` and cannot disagree with it (ADR-014)."""
    store(session, derived(job, status=ExtractionStatus.INVALIDATED))
    stored = session.execute(select(ExtractedRequirement)).scalar_one()

    assert not stored.is_active
    assert (
        session.execute(
            select(ExtractedRequirement).where(
                ExtractedRequirement.status == ExtractionStatus.ACTIVE
            )
        ).scalars().all()
        == []
    )


# ---------------------------------------------------------------------------------------
# Digest, and the content-hash boundary (ADR-030 D17)
# ---------------------------------------------------------------------------------------


def test_the_digest_is_sha256_of_the_description_as_stored(
    session: Session, job: Job
) -> None:
    """64 lowercase hex characters, over ``jobs.description`` exactly as persisted (D9)."""
    store(session, derived(job))
    stored = session.execute(select(ExtractedRequirement)).scalar_one()

    assert stored.source_text_digest == digest(job.description)
    assert len(stored.source_text_digest) == 64
    assert set(stored.source_text_digest) <= set("0123456789abcdef")


def test_the_digest_and_the_content_hash_are_stored_independently(
    session: Session, job: Job
) -> None:
    """They are different values answering different questions, and neither derives the other.

    ``compute_content_hash`` canonicalizes the description before hashing it, so a
    punctuation-only edit leaves the content hash identical while the stored text — and
    therefore the digest — changes. Keying derived rows on the content hash alone would let
    a row look current while its evidence no longer occurs in the text.
    """
    store(session, derived(job))
    stored = session.execute(select(ExtractedRequirement)).scalar_one()

    assert stored.content_hash == job.content_hash
    assert stored.source_text_digest != stored.content_hash

    edited = RawJob(
        company_name="Example Analytics",
        role_title="Software Engineering Intern",
        job_type=JobType.INTERNSHIP,
        description="Eligibility: minimum CGPA 7.5/10 required! Apply online!",
        source_job_id="EX-001",
    )
    assert compute_content_hash(edited, "curated") == job.content_hash
    assert digest(normalize_job(edited, "curated").description) != stored.source_text_digest


def test_extracted_rows_are_not_an_input_to_the_job_content_hash(
    session: Session, job: Job
) -> None:
    """Writing derived data must not move ``jobs.content_hash`` (D17).

    This is the feedback loop D16 names: if it did move, the job would present as changed on
    the next ingestion, which would re-extract, which would change the hash again.
    """
    before = job.content_hash
    store(session, derived(job))
    store(
        session,
        derived(
            job,
            requirement_type=RequirementType.MAX_BACKLOGS,
            min_cgpa=None,
            min_cgpa_scale=None,
            max_backlogs=0,
            evidence_text="must have no active backlogs",
        ),
    )
    session.refresh(job)

    assert job.content_hash == before


def test_compute_content_hash_cannot_see_derived_data() -> None:
    """Structural, not behavioural: the hash takes a ``RawJob``, which has no field for it.

    ``RawJob`` is ``extra="forbid"``, so there is no parameter for derived data to arrive in
    and no filter anyone has to remember to apply — the same property the AI provider
    signatures rely on.
    """
    hints = get_type_hints(compute_content_hash)

    assert list(inspect.signature(compute_content_hash).parameters) == ["job", "source"]
    assert hints["job"] is RawJob
    # The storage-only columns have no counterpart on the adapter contract, so none of them
    # can reach the hash even by name.
    storage_only = set(EXPECTED_COLUMNS) - set(Job.__table__.columns.keys())
    assert storage_only and not (storage_only & set(RawJob.model_fields))
    assert "extracted" not in inspect.getsource(compute_content_hash)


def test_the_ingestion_update_path_cannot_touch_derived_rows() -> None:
    """``_apply_updates`` copies only source-owned job fields (D17).

    Hazard 2 of D16: a live adapter supplies ``None`` for every typed requirement column, so
    anything derived that lived in one would be erased on the next run. Nothing in the
    updatable set names this table.
    """
    assert TABLE not in _UPDATABLE_FIELDS
    assert not {f for f in _UPDATABLE_FIELDS if "extract" in f or "derived" in f}
    assert set(_UPDATABLE_FIELDS) <= set(Job.__table__.columns.keys())


# ---------------------------------------------------------------------------------------
# Foreign key — declared, and deliberately not relied upon
# ---------------------------------------------------------------------------------------


def test_the_foreign_key_is_declared_with_cascade(session: Session) -> None:
    """Correct on PostgreSQL, documentary on SQLite, and depended upon by nothing."""
    keys = sa_inspect(session.get_bind()).get_foreign_keys(TABLE)

    assert len(keys) == 1
    assert keys[0]["referred_table"] == "jobs"
    assert keys[0]["constrained_columns"] == ["job_id"]
    assert keys[0]["referred_columns"] == ["id"]
    assert keys[0]["options"].get("ondelete") == "CASCADE"


def test_nothing_turns_on_sqlite_foreign_key_enforcement() -> None:
    """This PR must not create new global database behaviour.

    SQLite ignores foreign keys unless ``PRAGMA foreign_keys=ON`` is set, and enabling it
    would change how every existing table behaves. That is its own decision and has not been
    taken, so no test here may depend on the cascade actually running.
    """
    import app.database as database

    assert "foreign_keys" not in inspect.getsource(database)
    assert "PRAGMA" not in inspect.getsource(database)
    assert "event" not in inspect.getsource(database)


def test_deleting_a_job_does_not_cascade_on_sqlite(session: Session, job: Job) -> None:
    """Documenting the actual behaviour rather than the declared one.

    The row survives because SQLite is not enforcing the key. Nothing in the product deletes
    a job — they are closed, never deleted (ADR-006, ADR-014) — so this is recorded so that
    a future reader is not surprised, and so that turning the pragma on is a visible change
    rather than a silent one.
    """
    store(session, derived(job))
    session.delete(job)
    session.commit()

    assert len(session.execute(select(ExtractedRequirement)).scalars().all()) == 1


# ---------------------------------------------------------------------------------------
# Privacy (INV-1, ADR-011, ADR-030 D24)
# ---------------------------------------------------------------------------------------


CANDIDATE_TERMS = (
    "candidate",
    "profile",
    "resume",
    "cgpa_actual",
    "email",
    "phone",
    "applicant",
    "person",
    "user_id",
    "application",
    "evaluation",
)


@pytest.mark.parametrize("term", CANDIDATE_TERMS)
def test_no_column_names_a_person(term: str) -> None:
    """The table records what a posting says, never anything about who reads it."""
    columns = set(ExtractedRequirement.__table__.columns.keys())

    assert not {c for c in columns if term in c.lower()}


def test_the_only_foreign_key_points_at_a_job() -> None:
    """No candidate relationship exists, and none can be added without this test failing."""
    targets = {
        fk.column.table.name for fk in ExtractedRequirement.__table__.foreign_keys
    }

    assert targets == {"jobs"}
    assert not ExtractedRequirement.__mapper__.relationships


def test_the_model_imports_no_candidate_type() -> None:
    """``GradeScale`` is an enum, not candidate data. Nothing else comes from that module.

    Asserted on the parsed imports rather than the text, so the module docstring may say why
    candidate data is absent without tripping the check.
    """
    tree = ast.parse(inspect.getsource(model_module))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }

    assert "CandidateProfile" not in imported
    assert "EducationEntry" not in imported
    assert imported & {"GradeScale"} == {"GradeScale"}


def test_no_forbidden_table_is_introduced(session: Session) -> None:
    """The migration adds one operational table and nothing resembling a personal one."""
    names = set(sa_inspect(session.get_bind()).get_table_names())

    assert not names & FORBIDDEN_TABLES
    assert names == ALLOWED_OPERATIONAL_TABLES


def test_the_repr_carries_no_free_text() -> None:
    """A repr is one ``logger.info("%s", row)`` away from being a log line (INV-4)."""
    row = ExtractedRequirement(
        id="row-1",
        job_id="job-1",
        requirement_type=RequirementType.MIN_CGPA,
        status=ExtractionStatus.ACTIVE,
        evidence_text="minimum CGPA 7.5/10 required",
    )
    rendered = repr(row)

    assert "minimum CGPA" not in rendered
    assert "row-1" in rendered and "MIN_CGPA" in rendered


# ---------------------------------------------------------------------------------------
# Migration portability (QG-006)
# ---------------------------------------------------------------------------------------


REVISION = "e7b4c0d21a95"
DOWN_REVISION = "c4f1a8b92d63"

#: The lifecycle correction that replaced the full derivation key with ACTIVE-only
#: uniqueness. It chains directly from the revision that created the table.
ACTIVE_UNIQUENESS_REVISION = "d5c2e9a1f7b4"


def _alembic(db_path: pathlib.Path, *args: str):
    import os
    import subprocess
    import sys

    env = {**os.environ, "ELIGICORE_DATABASE_URL": f"sqlite:///{db_path.as_posix()}"}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=pathlib.Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
    )


def _tables(db_path: pathlib.Path) -> set[str]:
    import sqlite3

    with sqlite3.connect(db_path) as con:
        return {
            row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }


def _revision_source(revision: str) -> str:
    versions = pathlib.Path("alembic/versions")
    module = next(p for p in versions.glob("*.py") if p.stem.startswith(revision))
    return module.read_text(encoding="utf-8")


def test_the_revisions_chain_in_order() -> None:
    """Two revisions own this table, and each names the one before it."""
    versions = sorted(p.stem for p in pathlib.Path("alembic/versions").glob("*.py"))

    creation = _revision_source(REVISION)
    assert f'revision: str = "{REVISION}"' in creation
    assert f'down_revision: Union[str, None] = "{DOWN_REVISION}"' in creation

    correction = _revision_source(ACTIVE_UNIQUENESS_REVISION)
    assert f'revision: str = "{ACTIVE_UNIQUENESS_REVISION}"' in correction
    assert f'down_revision: Union[str, None] = "{REVISION}"' in correction

    assert len(versions) == 6


def test_the_migration_round_trips_on_sqlite(tmp_path: pathlib.Path) -> None:
    """Upgrade, downgrade, upgrade again — each clean, on a real file database.

    The downgrade removes only what this revision created: the other three tables and the
    previous head are untouched by it.
    """
    db = tmp_path / "migration.sqlite3"

    assert _alembic(db, "upgrade", "head").returncode == 0
    assert TABLE in _tables(db)

    assert _alembic(db, "downgrade", DOWN_REVISION).returncode == 0
    after_downgrade = _tables(db)
    assert TABLE not in after_downgrade
    assert {"jobs", "ingestion_state", "alembic_version"} <= after_downgrade

    assert _alembic(db, "upgrade", "head").returncode == 0
    assert _tables(db) == ALLOWED_OPERATIONAL_TABLES | {"alembic_version"}


#: Every named constraint the contract requires, as it must appear in the DDL the migration
#: actually produces.
MIGRATED_CONSTRAINTS = (
    "ck_extracted_requirements_provenance_derived",
    "ck_extracted_requirements_strength_required",
    "ck_extracted_requirements_scale_known",
    "ck_extracted_requirements_value_columns",
    "requirementtype",
    "requirementprovenance",
    "requirementstrength",
    "gradescale",
    "extractionstatus",
)


@pytest.mark.parametrize("constraint", MIGRATED_CONSTRAINTS)
def test_the_migrated_schema_carries_every_constraint(
    tmp_path: pathlib.Path, constraint: str
) -> None:
    """The constraints must exist in the schema the **migration** builds, not just the model.

    This is the gap ``alembic check`` cannot close: autogenerate does not compare CHECK
    constraints, so a migration that silently omitted one would still report no drift while
    the tests — which build their schema from ``Base.metadata`` — kept passing. Production
    schemas come from the migration, so a constraint missing there is missing in the only
    place it matters. Found by mutation: removing the value-column CHECK from the migration
    alone left the whole suite green until this existed.
    """
    import sqlite3

    db = tmp_path / "constraints.sqlite3"
    assert _alembic(db, "upgrade", "head").returncode == 0

    with sqlite3.connect(db) as con:
        ddl = con.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)
        ).fetchone()[0]

    assert constraint in ddl


def test_the_migrated_schema_declares_the_cascading_foreign_key(
    tmp_path: pathlib.Path,
) -> None:
    """The cascade is in the migration's DDL too, not only in the model."""
    import sqlite3

    db = tmp_path / "fk.sqlite3"
    assert _alembic(db, "upgrade", "head").returncode == 0

    with sqlite3.connect(db) as con:
        ddl = con.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)
        ).fetchone()[0]

    assert "REFERENCES jobs (id) ON DELETE CASCADE" in ddl


def test_alembic_check_reports_no_drift(tmp_path: pathlib.Path) -> None:
    """The migration and the model describe the same schema.

    The repository's established proof for this, used at every previous migration gate.
    """
    db = tmp_path / "check.sqlite3"
    assert _alembic(db, "upgrade", "head").returncode == 0

    result = _alembic(db, "check")

    assert result.returncode == 0
    assert "No new upgrade operations detected" in result.stdout + result.stderr


# ---------------------------------------------------------------------------------------
# The ACTIVE-only predicate, at DDL level and in both supported dialects
# ---------------------------------------------------------------------------------------

#: What the index's predicate must be, written out rather than imported from the model.
#: A test that derives its expectation from the thing under test proves only that the thing
#: equals itself — this is the one place the literal belongs.
ACTIVE_PREDICATE_SQL = "WHERE status = 'ACTIVE'"
ACTIVE_INDEX = "uq_extracted_requirements_one_active"


def _compiled_index(dialect_name: str) -> str:
    from sqlalchemy.dialects import postgresql, sqlite
    from sqlalchemy.schema import CreateIndex

    dialect = {"sqlite": sqlite, "postgresql": postgresql}[dialect_name].dialect()
    index = next(
        ix for ix in Base.metadata.tables[TABLE].indexes if ix.name == ACTIVE_INDEX
    )
    return str(CreateIndex(index).compile(dialect=dialect))


@pytest.mark.parametrize("dialect", ["sqlite", "postgresql"])
def test_the_model_emits_the_partial_predicate_for_both_dialects(dialect: str) -> None:
    """ADR-009's two engines, each asserted separately.

    SQLAlchemy has no dialect-neutral spelling for a partial index: the predicate must be
    given once per dialect, and a dialect for which it is **not** given silently receives a
    **total** unique index. That index would forbid the second row at a returning digest and
    reintroduce exactly the lifecycle bug this correction removes — with no error anywhere,
    because the index would still be created and still carry the right name.
    """
    statement = _compiled_index(dialect)

    assert "CREATE UNIQUE INDEX" in statement
    assert "(job_id, requirement_type)" in statement
    assert ACTIVE_PREDICATE_SQL in statement


def test_the_predicate_matches_the_stored_enum_value() -> None:
    """A predicate naming a status that cannot occur is a constraint enforcing nothing."""
    assert ExtractionStatus.ACTIVE.value == "ACTIVE"
    assert f"status = '{ExtractionStatus.ACTIVE.value}'" in _compiled_index("sqlite")


def test_the_migrated_index_carries_the_predicate(tmp_path: pathlib.Path) -> None:
    """Read from the database a real ``alembic upgrade`` produced, not from the model.

    ``alembic check`` cannot close this gap. A database holding a **total** unique index
    where the model declares a partial one was compared against the metadata and
    autogenerate reported no difference at all — the predicate is simply not part of what it
    compares, exactly as CHECK constraints are not.
    """
    import sqlite3

    db = tmp_path / "predicate.sqlite3"
    assert _alembic(db, "upgrade", "head").returncode == 0

    with sqlite3.connect(db) as con:
        ddl = con.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name=?", (ACTIVE_INDEX,)
        ).fetchone()

    assert ddl is not None, f"{ACTIVE_INDEX} is missing from the migrated schema"
    assert "UNIQUE" in ddl[0]
    assert ACTIVE_PREDICATE_SQL in ddl[0]


def test_the_migrated_schema_has_no_total_unique_constraint(
    tmp_path: pathlib.Path,
) -> None:
    """The old key must be absent from the migration's output, not only from the model."""
    import sqlite3

    db = tmp_path / "nokey.sqlite3"
    assert _alembic(db, "upgrade", "head").returncode == 0

    with sqlite3.connect(db) as con:
        ddl = con.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)
        ).fetchone()[0]

    assert "uq_extracted_requirements_job_digest_type" not in ddl


def test_the_migrated_schema_keeps_the_ordinary_indexes(tmp_path: pathlib.Path) -> None:
    """The correction rebuilds the table on SQLite; the read-path indexes must survive it."""
    import sqlite3

    db = tmp_path / "indexes.sqlite3"
    assert _alembic(db, "upgrade", "head").returncode == 0

    with sqlite3.connect(db) as con:
        names = {
            row[0]
            for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=?", (TABLE,)
            )
        }

    assert {
        "ix_extracted_requirements_job_id",
        "ix_extracted_requirements_source_text_digest",
        "ix_extracted_requirements_status",
        ACTIVE_INDEX,
    } <= names


# ---------------------------------------------------------------------------------------
# Downgrade safety — the newer schema holds histories the older one cannot
# ---------------------------------------------------------------------------------------


def _seed_job(db: pathlib.Path) -> None:
    import sqlite3

    with sqlite3.connect(db) as con:
        con.execute(
            "INSERT INTO jobs (id, company_name, role_title, job_type, description,"
            " requirements, allowed_fields, required_skills, source, content_hash, status,"
            " last_verified_at, created_at, updated_at) VALUES"
            " ('J1','Co','Eng','INTERNSHIP','A','{}','[]','[]','fake','h','ACTIVE',"
            "datetime('now'),datetime('now'),datetime('now'))"
        )


def _seed_derived(db: pathlib.Path, row_id: str, text_digest: str, status: str) -> None:
    import sqlite3

    with sqlite3.connect(db) as con:
        con.execute(
            "INSERT INTO extracted_requirements (id, job_id, source_text_digest,"
            " content_hash, requirement_type, provenance, strength, min_cgpa,"
            " min_cgpa_scale, evidence_text, extractor, extractor_version, extracted_at,"
            " status, invalidated_at) VALUES (?,?,?,'h','MIN_CGPA','PROSE_DERIVED',"
            "'REQUIRED',7.5,'SCALE_10','minimum CGPA 7.5/10 required','deterministic.cgpa',"
            "'1',datetime('now'),?,?)",
            (
                row_id,
                "J1",
                text_digest,
                status,
                None if status == "ACTIVE" else "2026-01-01",
            ),
        )


def _derived_rows(db: pathlib.Path) -> list[tuple[str, str, str]]:
    import sqlite3

    with sqlite3.connect(db) as con:
        return [
            tuple(row)
            for row in con.execute(
                "SELECT id, source_text_digest, status FROM extracted_requirements"
                " ORDER BY id"
            )
        ]


def test_the_downgrade_succeeds_when_no_history_blocks_it(tmp_path: pathlib.Path) -> None:
    """Clean data: the old key is restored and every other schema element survives."""
    import sqlite3

    db = tmp_path / "clean.sqlite3"
    assert _alembic(db, "upgrade", "head").returncode == 0
    _seed_job(db)
    _seed_derived(db, "r1", "digestA", "ACTIVE")

    result = _alembic(db, "downgrade", REVISION)
    assert result.returncode == 0, result.stderr

    with sqlite3.connect(db) as con:
        ddl = con.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)
        ).fetchone()[0]
        index = con.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name=?", (ACTIVE_INDEX,)
        ).fetchone()
        revision = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]

    assert "uq_extracted_requirements_job_digest_type" in ddl
    assert index is None
    assert revision == REVISION
    # The rebuild must not have cost the constraint reflection cannot round trip.
    assert "ck_extracted_requirements_value_columns" in ddl
    assert "REFERENCES jobs (id) ON DELETE CASCADE" in ddl
    assert _derived_rows(db) == [("r1", "digestA", "ACTIVE")]


def test_the_downgrade_refuses_when_a_b_a_history_exists(tmp_path: pathlib.Path) -> None:
    """The case that must fail, and the reason the preflight exists.

    Two rows share a job, a digest and a requirement type — valid now, impossible under the
    old key. The downgrade must refuse rather than choose which one to destroy.
    """
    db = tmp_path / "history.sqlite3"
    assert _alembic(db, "upgrade", "head").returncode == 0
    _seed_job(db)
    _seed_derived(db, "r1", "digestA", "INVALIDATED")
    _seed_derived(db, "r2", "digestB", "INVALIDATED")
    _seed_derived(db, "r3", "digestA", "ACTIVE")

    result = _alembic(db, "downgrade", REVISION)

    assert result.returncode != 0
    assert "cannot represent" in (result.stdout + result.stderr)


def test_a_refused_downgrade_changes_nothing(tmp_path: pathlib.Path) -> None:
    """Aborting before the DDL is the whole point. Schema, revision and rows must be intact.

    A preflight that ran *after* the index was dropped would leave a database on the new
    revision, missing its uniqueness guarantee, reporting a clean failure.
    """
    import sqlite3

    db = tmp_path / "unchanged.sqlite3"
    assert _alembic(db, "upgrade", "head").returncode == 0
    _seed_job(db)
    _seed_derived(db, "r1", "digestA", "INVALIDATED")
    _seed_derived(db, "r2", "digestB", "INVALIDATED")
    _seed_derived(db, "r3", "digestA", "ACTIVE")
    before = _derived_rows(db)

    assert _alembic(db, "downgrade", REVISION).returncode != 0

    with sqlite3.connect(db) as con:
        revision = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        index = con.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name=?", (ACTIVE_INDEX,)
        ).fetchone()
        ddl = con.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)
        ).fetchone()[0]

    assert revision == ACTIVE_UNIQUENESS_REVISION
    assert index is not None and ACTIVE_PREDICATE_SQL in index[0]
    assert "uq_extracted_requirements_job_digest_type" not in ddl
    assert "ck_extracted_requirements_value_columns" in ddl
    assert _derived_rows(db) == before


def test_a_refused_downgrade_deletes_and_reactivates_nothing(
    tmp_path: pathlib.Path,
) -> None:
    """Deduplicating would be the tempting fix, and is explicitly forbidden."""
    db = tmp_path / "nodedupe.sqlite3"
    assert _alembic(db, "upgrade", "head").returncode == 0
    _seed_job(db)
    _seed_derived(db, "r1", "digestA", "INVALIDATED")
    _seed_derived(db, "r2", "digestA", "ACTIVE")

    assert _alembic(db, "downgrade", REVISION).returncode != 0

    assert _derived_rows(db) == [
        ("r1", "digestA", "INVALIDATED"),
        ("r2", "digestA", "ACTIVE"),
    ]
