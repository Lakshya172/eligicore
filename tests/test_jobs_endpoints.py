"""Jobs API contract, filtering, pagination and privacy tests.

These endpoints serve public data, which makes them the one place in this codebase where a
leak would be *un*surprising. The privacy tests are here anyway — to prove the catalogue
carries nothing personal, and that adding a candidate parameter would be caught.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models.job import Job, JobStatus
from app.schemas.candidate import JobType
from app.schemas.job import JobStatusSchema, RawJob
from app.services.job_ingestion import ingest_source
from tests.conftest import ALLOWED_OPERATIONAL_TABLES, FORBIDDEN_TABLES
from tests.test_job_ingestion import FakeAdapter, make_raw

JOBS_URL = "/api/v1/jobs"


@pytest.fixture
def jobs_client() -> Iterator[TestClient]:
    """Client backed by an isolated in-memory catalogue."""
    # StaticPool is required, not incidental: a SQLite `:memory:` database belongs to the
    # connection that opened it, so the default pool hands the TestClient's worker thread a
    # fresh, empty database and every query fails with "no such table". StaticPool keeps
    # one connection, so the seeded catalogue is the one the endpoints see.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_db() -> Iterator[Session]:
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with factory() as seed:
        ingest_source(
            seed,
            FakeAdapter(
                [
                    make_raw(source_job_id="A-1", role_title="Intern One"),
                    make_raw(
                        source_job_id="A-2",
                        role_title="Backend Engineer",
                        job_type=JobType.FULL_TIME,
                    ),
                    make_raw(source_job_id="A-3", role_title="Intern Three"),
                ],
                source_name="alpha",
            ),
        )
        ingest_source(
            seed,
            FakeAdapter(
                [make_raw(source_job_id="B-1", role_title="Data Intern")],
                source_name="beta",
            ),
        )
        # Close one alpha job by dropping it from the authoritative fetch.
        ingest_source(
            seed,
            FakeAdapter(
                [
                    make_raw(source_job_id="A-1", role_title="Intern One"),
                    make_raw(
                        source_job_id="A-2",
                        role_title="Backend Engineer",
                        job_type=JobType.FULL_TIME,
                    ),
                ],
                source_name="alpha",
            ),
        )

    yield TestClient(app)
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


# ---------------------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------------------


def test_list_jobs_returns_active_by_default(jobs_client: TestClient) -> None:
    body = jobs_client.get(JOBS_URL).json()

    assert body["total"] == 3, "A-3 was closed and must be excluded by default"
    assert all(item["is_active"] for item in body["items"])
    assert all(item["status"] == "ACTIVE" for item in body["items"])


def test_list_response_shape(jobs_client: TestClient) -> None:
    body = jobs_client.get(JOBS_URL).json()
    assert set(body) == {"items", "total", "limit", "offset"}

    item = body["items"][0]
    assert {"id", "company_name", "role_title", "job_type", "status", "is_active",
            "source", "min_cgpa", "min_cgpa_scale", "last_verified_at"} <= set(item)


def test_get_one_job(jobs_client: TestClient) -> None:
    listed = jobs_client.get(JOBS_URL).json()["items"][0]
    body = jobs_client.get(f"{JOBS_URL}/{listed['id']}").json()

    assert body["id"] == listed["id"]
    assert body["role_title"] == listed["role_title"]


def test_unknown_job_returns_404(jobs_client: TestClient) -> None:
    response = jobs_client.get(f"{JOBS_URL}/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"] == "HTTP_ERROR"


def test_closed_job_remains_retrievable(jobs_client: TestClient) -> None:
    """A posting is never deleted, so a stored reference stays resolvable (ADR-006)."""
    closed = jobs_client.get(JOBS_URL, params={"is_active": False}).json()["items"]
    assert len(closed) == 1

    body = jobs_client.get(f"{JOBS_URL}/{closed[0]['id']}").json()
    assert body["status"] == "CLOSED"
    assert body["is_active"] is False


def test_routes_are_versioned_and_read_only(jobs_client: TestClient) -> None:
    paths = jobs_client.get("/openapi.json").json()["paths"]
    job_paths = {p: set(m) for p, m in paths.items() if "/jobs" in p}

    assert job_paths, "jobs routes must be documented"
    for path, methods in job_paths.items():
        assert methods == {"get"}, f"{path} exposes {methods}; Week 3 is read-only"
    assert all(p.startswith("/api/v1/") for p in paths)


def test_ingest_endpoint_is_not_exposed(jobs_client: TestClient) -> None:
    """Deferred, not dropped: the dossier lists it, the approved Week 3 scope does not."""
    paths = jobs_client.get("/openapi.json").json()["paths"]
    assert f"{JOBS_URL}/ingest" not in paths
    assert jobs_client.post(f"{JOBS_URL}/ingest").status_code in (404, 405)


def test_schema_and_model_status_enums_agree() -> None:
    """The two are deliberately separate; a test keeps them in step (ADR-010)."""
    assert {s.value for s in JobStatusSchema} == {s.value for s in JobStatus}


# ---------------------------------------------------------------------------------------
# Filters — only what Weeks 4-5 justify
# ---------------------------------------------------------------------------------------


def test_filter_by_is_active_false(jobs_client: TestClient) -> None:
    body = jobs_client.get(JOBS_URL, params={"is_active": False}).json()
    assert body["total"] == 1
    assert body["items"][0]["is_active"] is False


def test_is_active_is_a_two_state_filter(jobs_client: TestClient) -> None:
    """No 'return everything' option exists, deliberately.

    FastAPI cannot distinguish an omitted boolean query parameter from an explicit null, so
    a tri-state would need an invented sentinel. Nothing in the current scope needs one, and
    the two filters together cover the whole catalogue — 3 active plus 1 closed.
    """
    active = jobs_client.get(JOBS_URL, params={"is_active": True}).json()
    inactive = jobs_client.get(JOBS_URL, params={"is_active": False}).json()

    assert active["total"] == 3
    assert inactive["total"] == 1
    assert active["total"] + inactive["total"] == 4

    ids = {i["id"] for i in active["items"]} | {i["id"] for i in inactive["items"]}
    assert len(ids) == 4, "the two filters partition the catalogue, with no overlap"


def test_is_active_rejects_a_non_boolean(jobs_client: TestClient) -> None:
    assert jobs_client.get(JOBS_URL, params={"is_active": "maybe"}).status_code == 422


def test_filter_by_job_type(jobs_client: TestClient) -> None:
    body = jobs_client.get(JOBS_URL, params={"job_type": "FULL_TIME"}).json()
    assert body["total"] == 1
    assert body["items"][0]["job_type"] == "FULL_TIME"


def test_filter_by_source(jobs_client: TestClient) -> None:
    body = jobs_client.get(JOBS_URL, params={"source": "beta"}).json()
    assert body["total"] == 1
    assert body["items"][0]["source"] == "beta"


def test_filters_combine(jobs_client: TestClient) -> None:
    body = jobs_client.get(
        JOBS_URL, params={"source": "alpha", "job_type": "INTERNSHIP"}
    ).json()
    assert body["total"] == 1


def test_no_candidate_filter_exists(jobs_client: TestClient) -> None:
    """Eligibility and matching are Weeks 4 and 5. A candidate filter here would be
    those engines leaking into ingestion."""
    params = jobs_client.get("/openapi.json").json()["paths"][JOBS_URL]["get"].get(
        "parameters", []
    )
    names = {p["name"] for p in params}

    assert names == {"is_active", "job_type", "source", "limit", "offset"}
    for forbidden in ("candidate_id", "profile", "eligible", "min_cgpa", "match_score"):
        assert forbidden not in names


# ---------------------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------------------


def test_pagination_limits_results(jobs_client: TestClient) -> None:
    body = jobs_client.get(JOBS_URL, params={"limit": 2}).json()
    assert len(body["items"]) == 2
    assert body["total"] == 3, "total ignores pagination"


def test_pagination_offset_walks_the_catalogue(jobs_client: TestClient) -> None:
    first = jobs_client.get(JOBS_URL, params={"limit": 2, "offset": 0}).json()["items"]
    second = jobs_client.get(JOBS_URL, params={"limit": 2, "offset": 2}).json()["items"]

    ids = [i["id"] for i in first] + [i["id"] for i in second]
    assert len(set(ids)) == 3, "no job appears twice and none is skipped"


def test_pagination_ordering_is_deterministic(jobs_client: TestClient) -> None:
    """Without a tiebreaker, jobs sharing a timestamp swap between pages."""
    first = [i["id"] for i in jobs_client.get(JOBS_URL).json()["items"]]
    second = [i["id"] for i in jobs_client.get(JOBS_URL).json()["items"]]
    assert first == second


@pytest.mark.parametrize("limit", [0, -1, 101, 1000])
def test_out_of_range_limit_is_rejected(jobs_client: TestClient, limit: int) -> None:
    """A caller cannot request the whole catalogue in one response."""
    assert jobs_client.get(JOBS_URL, params={"limit": limit}).status_code == 422


def test_negative_offset_is_rejected(jobs_client: TestClient) -> None:
    assert jobs_client.get(JOBS_URL, params={"offset": -1}).status_code == 422


def test_invalid_job_type_is_rejected(jobs_client: TestClient) -> None:
    assert jobs_client.get(JOBS_URL, params={"job_type": "PART_TIME"}).status_code == 422


# ---------------------------------------------------------------------------------------
# Privacy — the catalogue carries nothing personal
# ---------------------------------------------------------------------------------------


def test_no_personal_data_table_exists(jobs_client: TestClient) -> None:
    jobs_client.get(JOBS_URL)

    registered = set(Base.metadata.tables)
    assert not (registered - ALLOWED_OPERATIONAL_TABLES)
    assert not (registered & FORBIDDEN_TABLES)


def test_job_table_has_no_candidate_column() -> None:
    """A job is a public posting. Nothing may correlate it to a person (INV-1)."""
    columns = set(Job.__table__.columns.keys())
    for forbidden in ("candidate_id", "user_id", "email", "profile", "resume",
                      "eligibility_state", "match_score"):
        assert forbidden not in columns


def test_job_response_carries_no_candidate_field(jobs_client: TestClient) -> None:
    item = jobs_client.get(JOBS_URL).json()["items"][0]
    for forbidden in ("candidate_id", "eligibility_state", "match_score", "is_eligible"):
        assert forbidden not in item


def test_response_contains_no_evaluation_verdict(jobs_client: TestClient) -> None:
    """Week 3 stores what a posting states; it decides nothing about anyone."""
    body = jobs_client.get(JOBS_URL).text.lower()
    for forbidden in ("eligible", "not_eligible", "needs_review", "match_score"):
        assert forbidden not in body


def test_database_holds_only_operational_tables(jobs_client: TestClient) -> None:
    jobs_client.get(JOBS_URL)
    from app.database import engine

    existing = set(inspect(engine).get_table_names())
    assert not (existing & FORBIDDEN_TABLES)


def test_404_does_not_echo_the_requested_id(jobs_client: TestClient) -> None:
    """A job id is not personal, but echoing caller input back is a habit worth keeping."""
    marker = "SENSITIVE-LOOKUP-MARKER-4a7c"
    response = jobs_client.get(f"{JOBS_URL}/{marker}")

    assert response.status_code == 404
    assert marker not in response.text


def test_request_logs_contain_no_job_content(
    jobs_client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("DEBUG"):
        jobs_client.get(JOBS_URL)

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "Example Analytics" not in logged
    assert "path=/api/v1/jobs" in logged
