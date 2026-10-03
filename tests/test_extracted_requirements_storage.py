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
from sqlalchemy import create_engine, inspect as sa_inspect, select
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
    """The read path filters on job, digest and status, so all three are indexed."""
    names = {ix["name"] for ix in sa_inspect(session.get_bind()).get_indexes(TABLE)}

    assert {
        "ix_extracted_requirements_job_id",
        "ix_extracted_requirements_source_text_digest",
        "ix_extracted_requirements_status",
    } <= names


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


def test_duplicate_job_digest_and_type_is_rejected(session: Session, job: Job) -> None:
    """At most one derivation per requirement type per exact pinned text (D19).

    This is what makes "verified is at most one value" a property of the database rather
    than of whichever code path happens to be writing.
    """
    store(session, derived(job))

    with pytest.raises(IntegrityError):
        store(session, derived(job, min_cgpa=8.0, evidence_text="minimum CGPA 8.0/10"))


def test_the_same_type_is_accepted_under_a_different_digest(
    session: Session, job: Job
) -> None:
    """A changed description is a new derivation, not a duplicate.

    The old row stays, invalidated; the new one is written under the recomputed digest. That
    is why the key includes the digest rather than being ``(job_id, requirement_type)``.
    """
    first = derived(job)
    store(session, first)
    first.invalidate(SEEDED_AT)
    store(session, derived(job, source_text_digest=digest("A different description.")))

    assert len(session.execute(select(ExtractedRequirement)).scalars().all()) == 2


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


def test_the_revision_chains_from_the_previous_head() -> None:
    """Exactly one new revision, on the head that existed before this PR."""
    versions = sorted(p.stem for p in pathlib.Path("alembic/versions").glob("*.py"))
    module = next(v for v in versions if v.startswith(REVISION))
    source = (pathlib.Path("alembic/versions") / f"{module}.py").read_text(encoding="utf-8")

    assert f'revision: str = "{REVISION}"' in source
    assert f'down_revision: Union[str, None] = "{DOWN_REVISION}"' in source
    assert len(versions) == 5


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


def test_alembic_check_reports_no_drift(tmp_path: pathlib.Path) -> None:
    """The migration and the model describe the same schema.

    The repository's established proof for this, used at every previous migration gate.
    """
    db = tmp_path / "check.sqlite3"
    assert _alembic(db, "upgrade", "head").returncode == 0

    result = _alembic(db, "check")

    assert result.returncode == 0
    assert "No new upgrade operations detected" in result.stdout + result.stderr
