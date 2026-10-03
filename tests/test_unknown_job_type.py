"""Explicit unknown employment type — enum, schema, persistence, API and migration.

ADR-029 adds ``JobType.UNKNOWN`` meaning exactly *the source did not explicitly provide the
employment type*. The tests here exist to stop that meaning drifting, because every way it
could drift is silent: a wildcard preference that quietly matches everything, a typed filter
that quietly widens, an eligibility path that quietly starts reading ``job_type``, or a
downgrade that quietly discards rows.

**Offline and deterministic.** SQLite in-memory or a tmp file, no network, no API key.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.job import Job, JobStatus
from app.schemas.candidate import PREFERABLE_JOB_TYPES, CandidatePreferences, JobType
from app.schemas.job import JobRead, NormalizedJob, RawJob
from app.services.job_normalizer import normalize_job
from tests.conftest import ALLOWED_OPERATIONAL_TABLES

REPO = pathlib.Path(__file__).resolve().parent.parent
MIGRATION = REPO / "alembic" / "versions" / "c4f1a8b92d63_widen_job_type_check_for_unknown.py"


# ---------------------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------------------


@pytest.fixture
def session() -> Iterator[Session]:
    """An isolated in-memory database per test.

    ``StaticPool`` is required, not incidental: a SQLite ``:memory:`` database belongs to
    the connection that opened it, so the default pool hands the TestClient's worker thread
    a fresh, empty database (the reason ``tests/test_jobs_endpoints.py`` does the same).
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        yield db
    Base.metadata.drop_all(engine)


@pytest.fixture
def api(session: Session) -> Iterator[TestClient]:
    """A client whose jobs endpoint reads the same in-memory database."""

    def override_get_db() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def profile_payload(**overrides: Any) -> dict[str, Any]:
    """An entirely fictional profile in the shape the endpoints accept."""
    payload: dict[str, Any] = {
        "candidate_id": "client-generated-test-id-0001",
        "name": "Test Candidate",
        "email": "test.candidate@example.com",
        "education": [
            {
                "degree": "B.Tech",
                "level": "BACHELORS",
                "field_of_study": "Information Technology",
                "institution": "Example Institute of Technology",
                "grad_year": 2027,
                "cgpa": 8.2,
                "scale": "SCALE_10",
            }
        ],
        "experience": [],
        "skills": ["Python"],
        "backlogs": 0,
    }
    payload.update(overrides)
    return payload


def make_job(job_type: JobType, **overrides: Any) -> Job:
    """One obviously synthetic stored job."""
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    fields: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "company_name": "Example Analytics",
        "role_title": "Software Engineer",
        "job_type": job_type,
        "description": "Synthetic posting.",
        "requirements": {},
        "allowed_fields": [],
        "required_skills": [],
        "source": "scratch",
        "source_job_id": uuid.uuid4().hex[:12],
        "content_hash": uuid.uuid4().hex,
        "status": JobStatus.ACTIVE,
        "last_verified_at": now,
        "created_at": now,
        "updated_at": now,
    }
    fields.update(overrides)
    return Job(**fields)


def raw(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "company_name": "Example Analytics",
        "role_title": "Software Engineer",
        "apply_link": "https://careers.example.invalid/roles/1",
        "source_job_id": "EX-1",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------------------
# Enum and domain semantics
# ---------------------------------------------------------------------------------------


def test_the_enum_has_exactly_three_members_and_unknown_is_its_own() -> None:
    assert [member.value for member in JobType] == ["INTERNSHIP", "FULL_TIME", "UNKNOWN"]
    assert JobType.UNKNOWN is not JobType.INTERNSHIP
    assert JobType.UNKNOWN is not JobType.FULL_TIME
    assert JobType("UNKNOWN") is JobType.UNKNOWN
    assert JobType.UNKNOWN.value == "UNKNOWN"


def test_unknown_is_not_a_preferable_type() -> None:
    """The allow-list is the one place the job/preference distinction is encoded."""
    assert PREFERABLE_JOB_TYPES == {JobType.INTERNSHIP, JobType.FULL_TIME}
    assert JobType.UNKNOWN not in PREFERABLE_JOB_TYPES


def test_there_is_only_one_job_type_enum() -> None:
    """ADR-029 D4 keeps the shared enum; a second one would drift from the first."""
    from app.schemas import job as job_schemas

    assert job_schemas.JobType is JobType


# ---------------------------------------------------------------------------------------
# RawJob default and normalization propagation
# ---------------------------------------------------------------------------------------


def test_rawjob_defaults_to_unknown_when_a_source_omits_the_type() -> None:
    """An adapter for a source that publishes no employment type omits the field."""
    assert RawJob.model_validate(raw()).job_type is JobType.UNKNOWN


@pytest.mark.parametrize("known", [JobType.INTERNSHIP, JobType.FULL_TIME])
def test_a_stated_type_is_kept_exactly_and_the_default_never_applies(known: JobType) -> None:
    assert RawJob.model_validate(raw(job_type=known.value)).job_type is known


def test_unknown_may_also_be_stated_explicitly() -> None:
    assert RawJob.model_validate(raw(job_type="UNKNOWN")).job_type is JobType.UNKNOWN


def test_an_invalid_job_type_is_still_rejected() -> None:
    """Widening the enum must not turn it into a free-text column."""
    with pytest.raises(Exception):
        RawJob.model_validate(raw(job_type="PART_TIME"))


@pytest.mark.parametrize(
    "value", [JobType.INTERNSHIP, JobType.FULL_TIME, JobType.UNKNOWN]
)
def test_normalization_carries_the_type_through_verbatim(value: JobType) -> None:
    """ADR-029 D5: the normalizer must not translate, default or 'repair' UNKNOWN."""
    normalized = normalize_job(RawJob.model_validate(raw(job_type=value.value)), "scratch")
    assert isinstance(normalized, NormalizedJob)
    assert normalized.job_type is value


def test_normalization_of_an_omitted_type_yields_unknown_not_none() -> None:
    normalized = normalize_job(RawJob.model_validate(raw()), "scratch")
    assert normalized.job_type is JobType.UNKNOWN
    assert normalized.job_type is not None


# ---------------------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value", [JobType.INTERNSHIP, JobType.FULL_TIME, JobType.UNKNOWN]
)
def test_every_member_persists_and_round_trips(session: Session, value: JobType) -> None:
    job = make_job(value)
    session.add(job)
    session.commit()

    stored = session.execute(select(Job).where(Job.id == job.id)).scalar_one()
    assert stored.job_type is value


def test_the_column_is_still_not_null(session: Session) -> None:
    """ADR-029 D4 keeps NOT NULL; ``Optional[JobType]`` would have weakened it."""
    from app.models.job import Job as JobModel

    assert JobModel.__table__.c.job_type.nullable is False

    with pytest.raises(Exception):
        session.add(make_job(JobType.UNKNOWN, job_type=None))
        session.commit()
    session.rollback()


def test_an_unknown_job_can_be_updated_to_a_known_type_and_back(session: Session) -> None:
    """A source that later starts publishing the type must be able to correct the row."""
    job = make_job(JobType.UNKNOWN)
    session.add(job)
    session.commit()

    job.job_type = JobType.INTERNSHIP
    session.commit()
    assert session.execute(select(Job.job_type)).scalar_one() is JobType.INTERNSHIP


# ---------------------------------------------------------------------------------------
# API — serialization and the complete filter matrix
# ---------------------------------------------------------------------------------------


def test_jobread_serializes_unknown(session: Session, api: TestClient) -> None:
    job = make_job(JobType.UNKNOWN)
    session.add(job)
    session.commit()

    body = api.get(f"/api/v1/jobs/{job.id}").json()
    assert body["job_type"] == "UNKNOWN"
    assert JobRead.model_validate(body).job_type is JobType.UNKNOWN


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        pytest.param(
            None, {"INTERNSHIP", "FULL_TIME", "UNKNOWN"}, id="no-filter-returns-all-three"
        ),
        pytest.param("INTERNSHIP", {"INTERNSHIP"}, id="internship-excludes-unknown"),
        pytest.param("FULL_TIME", {"FULL_TIME"}, id="full-time-excludes-unknown"),
        pytest.param("UNKNOWN", {"UNKNOWN"}, id="unknown-returns-only-unknown"),
    ],
)
def test_the_complete_filter_matrix(
    session: Session, api: TestClient, query: str | None, expected: set[str]
) -> None:
    """ADR-029 D8/D9, asserted through the real endpoint rather than a helper.

    The exclusions are the point: a typed filter must never quietly widen to include
    unknown-type jobs, and there is no parameter that makes it.
    """
    for value in (JobType.INTERNSHIP, JobType.FULL_TIME, JobType.UNKNOWN):
        session.add(make_job(value))
    session.commit()

    params = {} if query is None else {"job_type": query}
    response = api.get("/api/v1/jobs", params=params)

    assert response.status_code == 200
    returned = {item["job_type"] for item in response.json()["items"]}
    assert returned == expected
    assert response.json()["total"] == len(expected)


def test_a_returned_unknown_job_is_labelled_unknown_never_relabelled(
    session: Session, api: TestClient
) -> None:
    session.add(make_job(JobType.UNKNOWN))
    session.add(make_job(JobType.INTERNSHIP))
    session.commit()

    items = api.get("/api/v1/jobs").json()["items"]
    by_type = {item["job_type"] for item in items}
    assert by_type == {"UNKNOWN", "INTERNSHIP"}


def test_an_invalid_filter_value_is_still_rejected(api: TestClient) -> None:
    assert api.get("/api/v1/jobs", params={"job_type": "PART_TIME"}).status_code == 422


def test_no_include_unknown_type_parameter_exists(api: TestClient) -> None:
    """ADR-029 D9 rejected it by name; a later PR must not quietly reintroduce it."""
    spec = api.get("/openapi.json").json()
    params = spec["paths"]["/api/v1/jobs"]["get"].get("parameters", [])
    names = {parameter["name"] for parameter in params}
    assert "include_unknown_type" not in names
    assert names == {"is_active", "job_type", "source", "limit", "offset"}


def test_openapi_publishes_the_three_member_enum(api: TestClient) -> None:
    spec = api.get("/openapi.json").json()
    assert spec["components"]["schemas"]["JobType"]["enum"] == [
        "INTERNSHIP",
        "FULL_TIME",
        "UNKNOWN",
    ]


def test_the_preference_restriction_is_documented_where_a_client_will_see_it(
    api: TestClient,
) -> None:
    """The shared enum advertises three values but the field accepts two (ADR-029 D15).

    That divergence is acceptable only because it is stated in the published description,
    so the description is pinned rather than left to drift.
    """
    spec = api.get("/openapi.json").json()
    field = spec["components"]["schemas"]["CandidatePreferences"]["properties"]["job_types"]
    description = field.get("description", "")
    assert "UNKNOWN" in description
    assert "not accepted" in description.lower()


# ---------------------------------------------------------------------------------------
# CandidatePreferences — UNKNOWN is rejected, never absorbed
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "job_types",
    [
        pytest.param(["UNKNOWN"], id="alone"),
        pytest.param(["INTERNSHIP", "UNKNOWN"], id="mixed-with-internship"),
        pytest.param(["UNKNOWN", "FULL_TIME"], id="mixed-with-full-time"),
        pytest.param(["UNKNOWN", "UNKNOWN"], id="repeated"),
    ],
)
def test_unknown_is_rejected_as_a_preference(job_types: list[str]) -> None:
    with pytest.raises(Exception) as caught:
        CandidatePreferences.model_validate({"job_types": job_types})
    assert "UNKNOWN" in str(caught.value)


@pytest.mark.parametrize(
    "job_types",
    [
        pytest.param([], id="empty"),
        pytest.param(["INTERNSHIP"], id="internship"),
        pytest.param(["FULL_TIME"], id="full-time"),
        pytest.param(["INTERNSHIP", "FULL_TIME"], id="both-known"),
    ],
)
def test_known_preferences_behave_exactly_as_before(job_types: list[str]) -> None:
    preferences = CandidatePreferences.model_validate({"job_types": job_types})
    assert [entry.value for entry in preferences.job_types] == job_types


def test_a_rejected_preference_is_never_silently_filtered_down() -> None:
    """The failure mode this guards: accepting the request minus the invalid member."""
    with pytest.raises(Exception):
        CandidatePreferences.model_validate({"job_types": ["INTERNSHIP", "UNKNOWN"]})


@pytest.mark.parametrize("endpoint", ["validate", "normalize"])
def test_the_rejection_is_observable_through_the_public_endpoints(endpoint: str) -> None:
    """Asserted at the contract, not only at the model."""
    payload = profile_payload(preferences={"job_types": ["UNKNOWN"]})
    response = TestClient(app).post(f"/api/v1/candidates/{endpoint}", json=payload)

    assert response.status_code == 422
    assert "UNKNOWN" in response.text


@pytest.mark.parametrize("endpoint", ["validate", "normalize"])
def test_a_known_preference_still_passes_the_public_endpoint(endpoint: str) -> None:
    payload = profile_payload(preferences={"job_types": ["INTERNSHIP"]})
    response = TestClient(app).post(f"/api/v1/candidates/{endpoint}", json=payload)

    assert response.status_code == 200


# ---------------------------------------------------------------------------------------
# Eligibility and matching parity — UNKNOWN changes nothing
# ---------------------------------------------------------------------------------------


def test_job_type_is_absent_from_the_eligibility_and_matching_engines() -> None:
    """ADR-029 D6/D7. Structural, so no value of job_type can ever produce a verdict.

    Asserted against source rather than behaviour: a behavioural test would pass on the
    day someone introduced the coupling with a default that happened to agree.
    """
    for module in (
        "app/services/eligibility_engine.py",
        "app/services/eligibility_ai.py",
        "app/services/matching_engine.py",
        "app/services/recommendations.py",
    ):
        source = (REPO / module).read_text(encoding="utf-8")
        assert "job_type" not in source, f"{module} started reading job_type"


def job_read(job_type: JobType) -> JobRead:
    """One catalogue job as the eligibility engine receives it."""
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    return JobRead.model_validate(
        {
            "id": str(uuid.uuid4()),
            "company_name": "Example Analytics",
            "role_title": "Software Engineer",
            "job_type": job_type,
            "location": "Example City",
            "description": "Synthetic posting.",
            "requirements": {},
            "min_cgpa": 7.0,
            "min_cgpa_scale": "SCALE_10",
            "allowed_fields": [],
            "min_degree_level": None,
            "max_backlogs": 0,
            "min_grad_year": 2026,
            "max_grad_year": 2028,
            "required_skills": ["Python"],
            "apply_link": "https://careers.example.invalid/roles/1",
            "deadline": None,
            "source": "scratch",
            "source_job_id": "EX-1",
            "status": "ACTIVE",
            "is_active": True,
            "last_verified_at": now,
        }
    )


def test_changing_a_job_to_unknown_does_not_change_its_eligibility_verdict() -> None:
    """The same job evaluated three times, differing only in employment type.

    ADR-029 D6: `UNKNOWN` must not produce `NOT_ELIGIBLE`, must not flip a verdict, and
    must not move confidence — merely because of its value.
    """
    from app.schemas.candidate import CandidateProfile
    from app.services.eligibility_engine import evaluate_job

    profile = CandidateProfile.model_validate(profile_payload())

    results = {
        value: evaluate_job(profile, job_read(value))
        for value in (JobType.INTERNSHIP, JobType.FULL_TIME, JobType.UNKNOWN)
    }

    states = {value: result.eligibility_state for value, result in results.items()}
    assert len(set(states.values())) == 1, states
    assert states[JobType.UNKNOWN].value != "NOT_ELIGIBLE"

    # The per-requirement breakdown must be identical too, not merely the headline state:
    # a differing confidence or reason code would still be job_type leaking into a verdict.
    breakdowns = {
        value: [
            (item.requirement_type, item.status, item.confidence, item.reason_code)
            for item in result.requirement_breakdown
        ]
        for value, result in results.items()
    }
    assert len({tuple(rows) for rows in breakdowns.values()}) == 1, breakdowns
    assert len({result.summary for result in results.values()}) == 1


def test_the_matching_projection_cannot_see_job_type_at_all() -> None:
    """ADR-029 D7: `UNKNOWN` must never become a scoring penalty.

    Structural rather than numeric: ``JobMatchInput`` has no ``job_type`` field, so no
    employment type — known or unknown — can reach match scoring. A score comparison
    would only show they happen to agree today.
    """
    import dataclasses

    from app.services.matching_engine import JobMatchInput, job_match_input

    field_names = {field.name for field in dataclasses.fields(JobMatchInput)}
    assert "job_type" not in field_names
    assert field_names == {"job_id", "role_title", "description", "required_skills"}

    without_ids = [
        {
            name: value
            for name, value in dataclasses.asdict(job_match_input(job_read(member))).items()
            if name != "job_id"
        }
        for member in JobType
    ]
    assert all(entry == without_ids[0] for entry in without_ids)


# ---------------------------------------------------------------------------------------
# Curated catalogue unchanged
# ---------------------------------------------------------------------------------------


def test_the_curated_catalogue_still_states_a_real_type_for_every_job() -> None:
    """ADR-029 D11: no row converted, no backfill, no curated job left unknown."""
    import json

    entries = json.loads((REPO / "app" / "data" / "curated_jobs.json").read_text("utf-8"))
    assert len(entries) == 40
    types = [entry["job_type"] for entry in entries]
    assert set(types) == {"INTERNSHIP", "FULL_TIME"}
    assert "UNKNOWN" not in types
    assert all("job_type" in entry for entry in entries)


# ---------------------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------------------


#: The revision this module is about, and the one below it. Named explicitly because
#: ``downgrade -1`` means "whatever is under head", which stopped being c4f1a8b92d63 as soon
#: as a later migration existed.
C4_REVISION = "c4f1a8b92d63"
BELOW_C4_REVISION = "b3e8d2c61a47"


def _alembic(db_path: pathlib.Path, *args: str) -> subprocess.CompletedProcess[str]:
    import os

    env = {**os.environ, "ELIGICORE_DATABASE_URL": f"sqlite:///{db_path.as_posix()}"}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO, env=env, capture_output=True, text=True,
    )


def _insert(db_path: pathlib.Path, job_type: str) -> tuple[bool, str]:
    import sqlite3

    try:
        with sqlite3.connect(db_path) as con:
            con.execute(
                "INSERT INTO jobs (id, company_name, role_title, job_type, description,"
                " requirements, allowed_fields, required_skills, source, content_hash,"
                " status, last_verified_at, created_at, updated_at) VALUES"
                " (?,?,?,?,'','{}','[]','[]',?,?,'ACTIVE',datetime('now'),"
                "datetime('now'),datetime('now'))",
                (str(uuid.uuid4()), "Example Co", "Role", job_type, "scratch",
                 uuid.uuid4().hex),
            )
        return True, ""
    except sqlite3.IntegrityError as exc:
        return False, str(exc)


@pytest.fixture
def migrated_db(tmp_path: pathlib.Path) -> pathlib.Path:
    db = tmp_path / "migration.db"
    assert _alembic(db, "upgrade", "head").returncode == 0
    return db


def test_the_migration_is_constraint_only_and_extends_the_merged_chain() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'down_revision: Union[str, None] = "b3e8d2c61a47"' in source
    assert 'revision: str = "c4f1a8b92d63"' in source
    for destructive in ("drop_table", "create_table", "add_column", "drop_column",
                        "alter_column", "DELETE", "UPDATE jobs"):
        assert destructive not in source, f"{destructive} has no business in this migration"


def test_the_migration_copies_the_enum_rather_than_importing_it() -> None:
    """A migration describes the schema at its revision, not the enum as it reads later."""
    source = MIGRATION.read_text(encoding="utf-8")
    assert "from app.schemas" not in source
    assert 'JOB_TYPES_AFTER = ("INTERNSHIP", "FULL_TIME", "UNKNOWN")' in source


def test_upgrade_admits_unknown_and_still_rejects_nonsense(
    migrated_db: pathlib.Path,
) -> None:
    for value in ("UNKNOWN", "INTERNSHIP", "FULL_TIME"):
        accepted, error = _insert(migrated_db, value)
        assert accepted, f"{value} rejected after upgrade: {error}"

    rejected, _ = _insert(migrated_db, "PART_TIME")
    assert not rejected, "the widened constraint must not accept arbitrary strings"


def test_downgrade_refuses_while_unknown_rows_exist_and_changes_nothing(
    migrated_db: pathlib.Path,
) -> None:
    """The test ADR-029 D16 calls the one that matters most.

    A downgrade verified only on an empty database is not a verified rollback path.
    """
    import sqlite3

    assert _insert(migrated_db, "UNKNOWN")[0]
    assert _insert(migrated_db, "INTERNSHIP")[0]

    # Step off any later revision first, so the downgrade under test is c4f1a8b92d63's own
    # and "changes nothing" stays a claim about that migration rather than about whatever
    # happens to sit above it.
    assert _alembic(migrated_db, "downgrade", C4_REVISION).returncode == 0
    result = _alembic(migrated_db, "downgrade", BELOW_C4_REVISION)
    output = result.stdout + result.stderr

    assert result.returncode != 0, "the downgrade must fail, not report success"
    assert "Refusing to downgrade" in output
    assert "1 job(s)" in output

    # Only a count may appear — never a job's contents (INV-4).
    for leaked in ("Example Co", "Role", "scratch"):
        assert leaked not in output, f"{leaked!r} leaked out of the migration"

    with sqlite3.connect(migrated_db) as con:
        assert con.execute(
            "SELECT COUNT(*) FROM jobs WHERE job_type='UNKNOWN'"
        ).fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 2
        assert con.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0] == "c4f1a8b92d63"
        ddl = con.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='jobs'"
        ).fetchone()[0]
    assert "'UNKNOWN'" in ddl, "the schema must be left exactly as it was"


def test_downgrade_succeeds_once_no_unknown_row_remains(
    migrated_db: pathlib.Path,
) -> None:
    import sqlite3

    assert _insert(migrated_db, "INTERNSHIP")[0]
    assert _insert(migrated_db, "UNKNOWN")[0]

    with sqlite3.connect(migrated_db) as con:
        con.execute("DELETE FROM jobs WHERE job_type='UNKNOWN'")

    assert _alembic(migrated_db, "downgrade", C4_REVISION).returncode == 0
    assert _alembic(migrated_db, "downgrade", BELOW_C4_REVISION).returncode == 0

    rejected, _ = _insert(migrated_db, "UNKNOWN")
    assert not rejected, "the narrowed constraint must reject UNKNOWN again"

    with sqlite3.connect(migrated_db) as con:
        assert con.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 1
        ddl = con.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='jobs'"
        ).fetchone()[0]
    # Batch-mode table recreation must not drop the neighbouring constraints or indexes.
    for survivor in ("jobstatus", "degreelevel", "uq_jobs_source_source_job_id"):
        assert survivor in ddl, f"{survivor} lost during SQLite table recreation"


def test_the_chain_round_trips_and_alembic_check_is_clean(
    migrated_db: pathlib.Path,
) -> None:
    assert _alembic(migrated_db, "downgrade", BELOW_C4_REVISION).returncode == 0
    assert _alembic(migrated_db, "upgrade", "head").returncode == 0

    result = _alembic(migrated_db, "check")
    assert result.returncode == 0
    assert "No new upgrade operations detected" in result.stdout + result.stderr


def test_the_migration_leaves_no_temporary_or_duplicate_tables(
    migrated_db: pathlib.Path,
) -> None:
    import sqlite3

    _alembic(migrated_db, "downgrade", BELOW_C4_REVISION)
    _alembic(migrated_db, "upgrade", "head")
    with sqlite3.connect(migrated_db) as con:
        tables = {
            row[0]
            for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert tables == ALLOWED_OPERATIONAL_TABLES | {"alembic_version"}


# ---------------------------------------------------------------------------------------
# Scope
# ---------------------------------------------------------------------------------------


def test_the_unknown_type_change_added_no_table() -> None:
    """The server-side table set is still operational data only (INV-1).

    The adapter list is deliberately no longer asserted here: Greenhouse was added by its
    own later gate, and `tests/test_greenhouse_adapter.py` pins the package contents. The
    table set is read from the shared allowlist for the same reason: `extracted_requirements`
    arrived with ADR-030, not with this change.
    """
    assert set(Base.metadata.tables) == ALLOWED_OPERATIONAL_TABLES
