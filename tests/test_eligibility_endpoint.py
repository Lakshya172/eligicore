"""Eligibility API contract and privacy tests.

This is the first endpoint that combines personal data with the database. The privacy
tests prove the combination is read-only on the server side: the profile is evaluated and
returned, the catalogue is read and never written, and nothing about the candidate reaches
a log (INV-1, INV-4, ADR-002).

All data is obviously synthetic.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.job import Job
from app.schemas.candidate import DegreeLevel, JobType
from app.schemas.eligibility import MAX_JOB_IDS
from app.services.job_ingestion import ingest_source
from tests.conftest import ALLOWED_OPERATIONAL_TABLES, FORBIDDEN_TABLES
from tests.test_job_ingestion import FakeAdapter, make_raw

CHECK_URL = "/api/v1/eligibility/check"

# Distinctive markers, so a leak is unambiguous wherever it appears.
CANDIDATE_ID = "CID-privacy-marker-7d1e0c"
NAME = "Zyxwv Privacy-Marker"
EMAIL = "privacy.marker.7d1e@example.com"
PHONE = "+19990007777"
INSTITUTION = "Qwertyuiop Marker Institute"
FIELD = "Xylography Marker Studies"
CGPA = 8.37
SKILL = "MarkerSkillLang"
RESUME_TEXT = "RESUME-BODY-MARKER-4b2a"


@dataclass
class Catalogue:
    client: TestClient
    factory: sessionmaker[Session]
    ids: dict[str, str]  # source_job_id -> catalogue id
    engine: Any


@pytest.fixture
def catalogue() -> Iterator[Catalogue]:
    """An isolated in-memory catalogue behind the real application."""
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
                    make_raw(
                        source_job_id="STRICT",
                        role_title="Strict Intern",
                        min_cgpa=7.0,
                        min_cgpa_scale="SCALE_10",
                        min_grad_year=2026,
                        max_grad_year=2027,
                        max_backlogs=0,
                        min_degree_level=DegreeLevel.BACHELORS,
                        allowed_fields=[FIELD],
                        requirements={"notes": "Final year students."},
                    ),
                    make_raw(
                        source_job_id="HIGH-BAR",
                        role_title="High Bar Engineer",
                        job_type=JobType.FULL_TIME,
                        min_cgpa=9.0,
                        min_cgpa_scale="SCALE_10",
                    ),
                    make_raw(
                        source_job_id="OPEN",
                        role_title="Open Intern",
                        min_cgpa=None,
                        min_cgpa_scale=None,
                    ),
                    make_raw(source_job_id="TO-CLOSE", role_title="Closing Intern"),
                ],
                source_name="alpha",
            ),
        )
        # Drop TO-CLOSE from an authoritative fetch so it becomes CLOSED.
        ingest_source(
            seed,
            FakeAdapter(
                [
                    make_raw(
                        source_job_id="STRICT",
                        role_title="Strict Intern",
                        min_cgpa=7.0,
                        min_cgpa_scale="SCALE_10",
                        min_grad_year=2026,
                        max_grad_year=2027,
                        max_backlogs=0,
                        min_degree_level=DegreeLevel.BACHELORS,
                        allowed_fields=[FIELD],
                        requirements={"notes": "Final year students."},
                    ),
                    make_raw(
                        source_job_id="HIGH-BAR",
                        role_title="High Bar Engineer",
                        job_type=JobType.FULL_TIME,
                        min_cgpa=9.0,
                        min_cgpa_scale="SCALE_10",
                    ),
                    make_raw(
                        source_job_id="OPEN",
                        role_title="Open Intern",
                        min_cgpa=None,
                        min_cgpa_scale=None,
                    ),
                ],
                source_name="alpha",
            ),
        )
        ids = {
            job.source_job_id: job.id
            for job in seed.execute(select(Job)).scalars()
        }

    try:
        yield Catalogue(TestClient(app), factory, ids, engine)
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def profile(**overrides: Any) -> dict[str, Any]:
    """A fully populated profile carrying privacy markers in every personal field."""
    data: dict[str, Any] = {
        "candidate_id": CANDIDATE_ID,
        "name": NAME,
        "email": EMAIL,
        "phone": PHONE,
        "location": "Marker City",
        "education": [
            {
                "degree": "B.Tech",
                "level": "BACHELORS",
                "field_of_study": FIELD,
                "institution": INSTITUTION,
                "grad_year": 2027,
                "cgpa": CGPA,
                "scale": "SCALE_10",
            }
        ],
        "skills": [SKILL],
        "backlogs": 0,
        "resume_raw_text": RESUME_TEXT,
    }
    data.update(overrides)
    return data


def check(cat: Catalogue, job_ids: list[str], **profile_overrides: Any) -> Any:
    return cat.client.post(
        CHECK_URL, json={"profile": profile(**profile_overrides), "job_ids": job_ids}
    )


# ---------------------------------------------------------------------------------------
# Success contract
# ---------------------------------------------------------------------------------------


def test_check_returns_explained_verdicts(catalogue: Catalogue) -> None:
    response = check(catalogue, [catalogue.ids["STRICT"]])

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "candidate_id", "engine_version", "evaluated_at", "results", "not_found_job_ids",
    }
    assert body["candidate_id"] == CANDIDATE_ID
    assert body["engine_version"] == "1"
    assert body["not_found_job_ids"] == []

    (result,) = body["results"]
    assert result["job_id"] == catalogue.ids["STRICT"]
    assert result["eligibility_state"] == "ELIGIBLE"
    assert result["job_status"] == "ACTIVE"
    assert result["summary"].startswith("Eligible")
    assert "not evaluated" in result["summary"]
    kinds = [entry["requirement_type"] for entry in result["requirement_breakdown"]]
    assert kinds == [
        "MIN_CGPA", "GRAD_YEAR_WINDOW", "MAX_BACKLOGS", "MIN_DEGREE_LEVEL", "ALLOWED_FIELDS",
    ]
    for entry in result["requirement_breakdown"]:
        assert set(entry) == {
            "requirement_type", "requirement", "candidate_value", "status",
            "confidence", "method", "reason_code", "note",
        }
        assert entry["status"] == "PASS"
        assert entry["method"] == "deterministic"
        assert entry["confidence"] == "HIGH"


def test_evaluated_at_is_utc(catalogue: Catalogue) -> None:
    body = check(catalogue, [catalogue.ids["OPEN"]]).json()
    assert body["evaluated_at"].endswith(("Z", "+00:00"))


def test_verdicts_differ_per_job(catalogue: Catalogue) -> None:
    ids = [catalogue.ids["STRICT"], catalogue.ids["HIGH-BAR"], catalogue.ids["OPEN"]]
    states = [r["eligibility_state"] for r in check(catalogue, ids).json()["results"]]
    assert states == ["ELIGIBLE", "NOT_ELIGIBLE", "ELIGIBLE"]


def test_missing_profile_data_yields_unknown_not_rejection(catalogue: Catalogue) -> None:
    body = check(catalogue, [catalogue.ids["HIGH-BAR"]], education=[]).json()
    (result,) = body["results"]
    assert result["eligibility_state"] == "UNKNOWN"
    assert result["requirement_breakdown"][0]["reason_code"] == "NO_QUALIFICATION"


def test_results_follow_request_order(catalogue: Catalogue) -> None:
    ids = [catalogue.ids["OPEN"], catalogue.ids["STRICT"], catalogue.ids["HIGH-BAR"]]
    body = check(catalogue, ids).json()
    assert [r["job_id"] for r in body["results"]] == ids


def test_duplicates_are_removed_preserving_first_seen_order(catalogue: Catalogue) -> None:
    a, b = catalogue.ids["HIGH-BAR"], catalogue.ids["OPEN"]
    body = check(catalogue, [b, a, b, a, b]).json()
    assert [r["job_id"] for r in body["results"]] == [b, a]


def test_unknown_ids_are_reported_not_fatal(catalogue: Catalogue) -> None:
    ids = ["missing-2", catalogue.ids["OPEN"], "missing-1", "missing-2"]
    response = check(catalogue, ids)
    assert response.status_code == 200
    body = response.json()
    assert [r["job_id"] for r in body["results"]] == [catalogue.ids["OPEN"]]
    assert body["not_found_job_ids"] == ["missing-2", "missing-1"]


def test_all_ids_unknown_returns_empty_results(catalogue: Catalogue) -> None:
    body = check(catalogue, ["nope"]).json()
    assert body["results"] == []
    assert body["not_found_job_ids"] == ["nope"]


def test_closed_job_is_still_evaluated_and_reports_status(catalogue: Catalogue) -> None:
    body = check(catalogue, [catalogue.ids["TO-CLOSE"]]).json()
    (result,) = body["results"]
    assert result["job_status"] == "CLOSED"
    assert result["eligibility_state"] == "ELIGIBLE"


def test_exactly_fifty_ids_is_accepted(catalogue: Catalogue) -> None:
    ids = [f"id-{n}" for n in range(MAX_JOB_IDS)]
    response = check(catalogue, ids)
    assert response.status_code == 200
    assert len(response.json()["not_found_job_ids"]) == MAX_JOB_IDS


def test_response_has_no_match_score_or_top_level_confidence(catalogue: Catalogue) -> None:
    text = check(catalogue, [catalogue.ids["STRICT"]]).text
    for forbidden in ("match_score", "score", "ranking", "recommend"):
        assert forbidden not in text
    body = check(catalogue, [catalogue.ids["STRICT"]]).json()
    assert "confidence" not in body
    assert "confidence" not in body["results"][0]


# ---------------------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"profile": {}, "job_ids": []},  # empty
        {"profile": {}, "job_ids": [f"id-{n}" for n in range(MAX_JOB_IDS + 1)]},  # 51
        {"job_ids": ["x"]},  # no profile
        {"profile": {}},  # no job ids
        {"profile": {}, "job_ids": ["x"], "unexpected": True},  # extra field
        {"profile": {}, "job_ids": [""]},  # empty id
        {"profile": {"backlogs": -1}, "job_ids": ["x"]},  # invalid profile
        {"profile": {"education": [{"degree": "B.Tech", "cgpa": -3}]}, "job_ids": ["x"]},
        {"profile": {}, "job_ids": "not-a-list"},
    ],
)
def test_invalid_requests_are_422(catalogue: Catalogue, payload: dict[str, Any]) -> None:
    assert catalogue.client.post(CHECK_URL, json=payload).status_code == 422


def test_validation_error_does_not_echo_candidate_values(catalogue: Catalogue) -> None:
    secret = "SENSITIVE-ELIGIBILITY-VALUE-5c1f"
    response = catalogue.client.post(
        CHECK_URL,
        json={"profile": {"email": secret, "name": NAME}, "job_ids": [secret]},
    )
    assert response.status_code == 422
    assert secret not in response.text
    assert NAME not in response.text
    for detail in response.json()["details"]:
        assert "input" not in detail
        assert "ctx" not in detail


def test_only_post_check_route_exists(catalogue: Catalogue) -> None:
    routes = {
        (method, route.path)
        for route in app.routes
        if "eligibility" in getattr(route, "path", "")
        for method in getattr(route, "methods", set())
    }
    assert routes == {("POST", "/api/v1/eligibility/check")}
    assert catalogue.client.get(CHECK_URL).status_code == 405


def test_no_ingest_route_was_added() -> None:
    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/api/v1/jobs/ingest" not in paths


def test_openapi_documents_the_route() -> None:
    schema = TestClient(app).get("/openapi.json").json()
    operation = schema["paths"]["/api/v1/eligibility/check"]["post"]
    assert operation["summary"]
    assert "Nothing is stored" in operation["description"]


# ---------------------------------------------------------------------------------------
# Privacy (INV-1, INV-4, ADR-002)
# ---------------------------------------------------------------------------------------

MARKERS = (CANDIDATE_ID, NAME, EMAIL, PHONE, INSTITUTION, FIELD, str(CGPA), SKILL, RESUME_TEXT)


def test_no_personal_data_table_exists_after_a_check(catalogue: Catalogue) -> None:
    check(catalogue, list(catalogue.ids.values()))
    tables = set(inspect(catalogue.engine).get_table_names())
    assert tables == ALLOWED_OPERATIONAL_TABLES
    assert not tables & FORBIDDEN_TABLES
    assert set(Base.metadata.tables) == ALLOWED_OPERATIONAL_TABLES


def _catalogue_snapshot(cat: Catalogue) -> list[tuple[Any, ...]]:
    with cat.factory() as db:
        rows = db.execute(select(Job).order_by(Job.id)).scalars().all()
        return [
            tuple(getattr(row, column.key) for column in Job.__table__.columns)
            for row in rows
        ]


def test_check_does_not_write_to_the_catalogue(catalogue: Catalogue) -> None:
    before = _catalogue_snapshot(catalogue)
    for _ in range(2):
        assert check(catalogue, list(catalogue.ids.values())).status_code == 200
    assert _catalogue_snapshot(catalogue) == before


def _database_dump(cat: Catalogue) -> str:
    with cat.engine.connect() as connection:
        return "\n".join(connection.connection.iterdump())


def test_no_candidate_data_is_stored_anywhere_in_the_database(catalogue: Catalogue) -> None:
    before = _database_dump(catalogue)
    check(catalogue, list(catalogue.ids.values()))
    after = _database_dump(catalogue)

    # The whole database is byte-identical: nothing was written, anywhere.
    assert after == before
    # FIELD is excluded only because the seeded job legitimately lists it as a permitted
    # field — public catalogue data, present before the request was made.
    for marker in MARKERS:
        if marker != FIELD:
            assert marker not in after


def test_logs_contain_no_candidate_data_or_candidate_id(
    catalogue: Catalogue, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    response = check(catalogue, list(catalogue.ids.values()) + ["missing-x"])
    assert response.status_code == 200

    logged = caplog.text + "\n".join(str(record.args) for record in caplog.records)
    for marker in MARKERS:
        assert marker not in logged, f"leaked into logs: {marker}"

    lines = [r.getMessage() for r in caplog.records if r.name == "eligicore.eligibility"]
    assert len(lines) == 1
    assert "jobs_requested=5 jobs_found=4 not_found=1" in lines[0]


def test_response_does_not_echo_the_profile(catalogue: Catalogue) -> None:
    response = check(catalogue, list(catalogue.ids.values()))
    text = response.text
    for marker in (NAME, EMAIL, PHONE, INSTITUTION, SKILL, RESUME_TEXT, "Marker City"):
        assert marker not in text
    body = response.json()
    assert "profile" not in body
    # Values needed to explain a verdict are returned — to the caller only.
    assert f"{CGPA} (SCALE_10)" in text
    for result in body["results"]:
        assert CANDIDATE_ID not in result["summary"]
        assert str(CGPA) not in result["summary"]
        assert FIELD not in result["summary"]
