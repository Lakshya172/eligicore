"""Recommendations API contract and privacy tests (PR 5B — ADR-022).

Drives ``POST /api/v1/recommendations`` through the real application against an isolated
in-memory catalogue. Proves the contract, the error envelope, and that the endpoint is
read-only on the server: the catalogue is read in one query and never written, and nothing
about the candidate reaches a log or the database (INV-1, INV-4, ADR-002).

All data is obviously synthetic.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.job import Job, JobStatus
from app.schemas.candidate import JobType
from app.schemas.matching import MAX_RECOMMENDATION_JOBS
from tests.conftest import ALLOWED_OPERATIONAL_TABLES

URL = "/api/v1/recommendations"
BASE_TIME = datetime(2026, 9, 1, tzinfo=timezone.utc)

CANDIDATE_ID = "CID-recommend-marker-91c3"
NAME = "Zyxwv Recommend-Marker"
EMAIL = "recommend.marker.91c3@example.com"
PHONE = "+19990004242"
SKILL = "MarkerSkillQuorlang"
EXPERIENCE = "Markerised Pipeline Wrangling"
RESUME_TEXT = "RESUME-BODY-MARKER-77e1"
INSTITUTION = "Qwertyuiop Marker College"
MARKERS = [CANDIDATE_ID, NAME, EMAIL, PHONE, SKILL, EXPERIENCE, RESUME_TEXT, INSTITUTION]


def profile(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "candidate_id": CANDIDATE_ID,
        "name": NAME,
        "email": EMAIL,
        "phone": PHONE,
        "education": [
            {
                "degree": "B.Tech",
                "level": "BACHELORS",
                "field_of_study": "Information Technology",
                "institution": INSTITUTION,
                "grad_year": 2027,
                "cgpa": 8.2,
                "scale": "SCALE_10",
            }
        ],
        "skills": ["Python", "SQL", SKILL],
        "experience": [{"title": "Data Intern", "description": f"{EXPERIENCE} in Python."}],
        "backlogs": 0,
        "resume_raw_text": RESUME_TEXT,
    }
    base.update(overrides)
    return base


@dataclass
class Catalogue:
    client: TestClient
    factory: sessionmaker[Session]
    engine: Any
    queries: list[str]


def add_job(session: Session, job_id: str, **overrides: Any) -> None:
    values: dict[str, Any] = {
        "id": job_id,
        "company_name": "Example Co",
        "role_title": "Software Engineering Intern",
        "job_type": JobType.INTERNSHIP,
        "description": "Build backend services and data pipelines in Python.",
        "requirements": {},
        "allowed_fields": [],
        "required_skills": ["Python", "SQL"],
        "source": "test",
        "content_hash": job_id.ljust(64, "0")[:64],
        "status": JobStatus.ACTIVE,
        "last_verified_at": BASE_TIME,
    }
    values.update(overrides)
    session.add(Job(**values))


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
    queries: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def _record(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        queries.append(statement)

    with factory() as seed:
        add_job(seed, "eligible", min_cgpa=7.0, min_cgpa_scale="SCALE_10")
        add_job(seed, "ineligible", min_cgpa=9.0, min_cgpa_scale="SCALE_10")
        add_job(seed, "review", min_cgpa=7.0, min_cgpa_scale="SCALE_10", max_backlogs=None,
                min_grad_year=2020, max_grad_year=2030, allowed_fields=["Mathematics"])
        add_job(seed, "unknown-status", status=JobStatus.UNKNOWN)
        add_job(seed, "closed", status=JobStatus.CLOSED)
        add_job(seed, "expired", status=JobStatus.EXPIRED)
        seed.commit()

    def override_get_db() -> Iterator[Session]:
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    queries.clear()
    try:
        yield Catalogue(TestClient(app), factory, engine, queries)
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def dump(cat: Catalogue) -> str:
    with cat.engine.connect() as connection:
        return "\n".join(connection.connection.iterdump())


def item_ids(body: dict[str, Any], group: str) -> list[str]:
    return [item["eligibility"]["job_id"] for item in body[group]]


# ---------------------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------------------

RESPONSE_FIELDS = {
    "candidate_id", "engine_version", "matching_version", "evaluated_at", "corpus_size",
    "corpus_fingerprint", "jobs_considered", "jobs_not_considered", "ranked", "needs_review",
    "not_eligible", "not_open", "not_found_job_ids",
}


def test_default_request_returns_the_full_contract(catalogue: Catalogue) -> None:
    response = catalogue.client.post(URL, json={"profile": profile()})
    assert response.status_code == 200
    body = response.json()

    assert set(body) == RESPONSE_FIELDS
    assert body["candidate_id"] == CANDIDATE_ID
    assert body["engine_version"] == "2"
    assert body["matching_version"] == "1"
    assert body["corpus_size"] == 6
    assert len(body["corpus_fingerprint"]) == 64
    assert body["jobs_considered"] == 4 and body["jobs_not_considered"] == 0
    assert body["not_found_job_ids"] == []
    # Same text and skills, so equal scores: the tie is broken by id.
    assert item_ids(body, "ranked") == ["eligible", "unknown-status"]
    assert [i["rank"] for i in body["ranked"]] == [1, 2]
    # CGPA and year pass; the non-exact field goes to the (default, uncertain) AI stage.
    assert item_ids(body, "needs_review") == ["review"]
    assert item_ids(body, "not_eligible") == ["ineligible"]
    assert body["not_open"] == []

    item = body["ranked"][0]
    assert set(item) == {"rank", "eligibility", "match", "explanation"}
    assert set(item["match"]) == {
        "match_score", "score_basis", "matched_required_skills", "missing_required_skills",
        "required_skill_count", "top_terms",
    }
    assert "match_score" not in item["eligibility"]
    for forbidden in ("overall_score", "combined_score", "recommendation_score"):
        assert forbidden not in response.text


def test_explicit_ids_cover_every_status_and_report_unknown(catalogue: Catalogue) -> None:
    body = catalogue.client.post(
        URL,
        json={
            "profile": profile(),
            "job_ids": ["closed", "ghost-1", "eligible", "expired", "closed", "unknown-status", "ghost-2"],
        },
    ).json()
    assert body["not_found_job_ids"] == ["ghost-1", "ghost-2"]
    assert sorted(item_ids(body, "not_open")) == ["closed", "expired"]
    assert sorted(item_ids(body, "ranked")) == ["eligible", "unknown-status"]
    assert body["jobs_considered"] == 4 and body["jobs_not_considered"] == 0
    assert body["not_open"][0]["rank"] is None


def test_recommendation_verdicts_equal_the_eligibility_endpoint(catalogue: Catalogue) -> None:
    requested = ["eligible", "ineligible", "review", "unknown-status", "closed", "expired"]
    recs = catalogue.client.post(URL, json={"profile": profile(), "job_ids": requested}).json()
    check = catalogue.client.post(
        "/api/v1/eligibility/check", json={"profile": profile(), "job_ids": requested}
    ).json()
    by_id = {result["job_id"]: result for result in check["results"]}
    for group in ("ranked", "needs_review", "not_eligible", "not_open"):
        for item in recs[group]:
            assert item["eligibility"] == by_id[item["eligibility"]["job_id"]]


def test_all_unknown_ids(catalogue: Catalogue) -> None:
    body = catalogue.client.post(URL, json={"profile": profile(), "job_ids": ["x", "y"]}).json()
    assert body["not_found_job_ids"] == ["x", "y"]
    assert body["jobs_considered"] == 0
    assert body["ranked"] == body["needs_review"] == body["not_eligible"] == body["not_open"] == []


def test_fifty_ids_are_accepted(catalogue: Catalogue) -> None:
    ids = ["eligible", *[f"ghost-{i}" for i in range(MAX_RECOMMENDATION_JOBS - 1)]]
    response = catalogue.client.post(URL, json={"profile": profile(), "job_ids": ids})
    assert response.status_code == 200
    assert len(response.json()["not_found_job_ids"]) == 49


def test_no_jobs_in_default_scope(catalogue: Catalogue) -> None:
    with catalogue.factory() as session:
        for job in session.query(Job).all():
            job.status = JobStatus.CLOSED
        session.commit()
    body = catalogue.client.post(URL, json={"profile": profile()}).json()
    assert body["jobs_considered"] == 0 and body["corpus_size"] == 6
    assert body["ranked"] == body["not_open"] == []


def test_profile_without_terms_gets_null_scores(catalogue: Catalogue) -> None:
    body = catalogue.client.post(
        URL, json={"profile": profile(skills=[], experience=[]), "job_ids": ["eligible"]}
    ).json()
    match = body["ranked"][0]["match"]
    assert match["match_score"] is None and match["score_basis"] == "NO_CANDIDATE_TERMS"


def test_catalogue_is_read_in_one_query(catalogue: Catalogue) -> None:
    catalogue.client.post(URL, json={"profile": profile()})
    selects = [q for q in catalogue.queries if q.lstrip().upper().startswith("SELECT")]
    writes = [q for q in catalogue.queries if q.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))]
    assert len(selects) == 1 and "FROM jobs" in selects[0]
    assert writes == []


def test_openapi_documents_the_endpoint_and_no_score_route() -> None:
    spec = TestClient(app).get("/openapi.json").json()
    assert "post" in spec["paths"]["/api/v1/recommendations"]
    assert "get" not in spec["paths"]["/api/v1/recommendations"]
    assert "/api/v1/matching/score" not in spec["paths"]
    schema = spec["components"]["schemas"]["RecommendationResponse"]
    assert set(schema["properties"]) == RESPONSE_FIELDS


# ---------------------------------------------------------------------------------------
# Errors — the existing envelope, no echo
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"job_ids": ["eligible"]},  # missing profile
        {"profile": profile(), "job_ids": []},  # empty job_ids
        {"profile": profile(), "job_ids": [f"j{i}" for i in range(MAX_RECOMMENDATION_JOBS + 1)]},
        {"profile": profile(), "job_ids": [""]},  # malformed id
        {"profile": profile(), "job_ids": ["x" * 101]},  # malformed id
        {"profile": profile(), "unexpected": True},  # extra field
        {"profile": profile(email="not-an-email " + NAME)},  # invalid profile value
        {"profile": profile(), "job_ids": "eligible"},  # wrong type
    ],
)
def test_invalid_requests_are_422_without_echo(catalogue: Catalogue, payload: dict[str, Any]) -> None:
    response = catalogue.client.post(URL, json=payload)
    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "VALIDATION_ERROR" and body["request_id"]
    for marker in MARKERS:
        assert marker not in response.text


def test_malformed_json_is_422(catalogue: Catalogue) -> None:
    response = catalogue.client.post(
        URL, content=b'{"profile": {', headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422
    assert response.json()["error"] == "VALIDATION_ERROR"


def test_get_is_not_allowed(catalogue: Catalogue) -> None:
    response = catalogue.client.get(URL)
    assert response.status_code == 405
    assert response.json()["error"] == "HTTP_ERROR"


def test_unexpected_failure_is_a_generic_500_that_logs_no_candidate_data(
    catalogue: Catalogue, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def boom(profile_, job_ids, catalogue_, ai_service):
        raise RuntimeError(f"failure mentioning {profile_.email} and {profile_.name}")

    monkeypatch.setattr("app.routers.matching.recommend", boom)
    client = TestClient(app, raise_server_exceptions=False)
    with caplog.at_level(logging.DEBUG):
        response = client.post(URL, json={"profile": profile()})
    assert response.status_code == 500
    for marker in MARKERS:
        assert marker not in response.text
        assert marker not in caplog.text


# ---------------------------------------------------------------------------------------
# Privacy — nothing stored, nothing logged
# ---------------------------------------------------------------------------------------


def test_database_is_byte_identical_after_recommendations(catalogue: Catalogue) -> None:
    before = dump(catalogue)
    catalogue.client.post(URL, json={"profile": profile()})
    catalogue.client.post(URL, json={"profile": profile(), "job_ids": ["closed", "eligible", "ghost"]})
    assert dump(catalogue) == before
    assert set(Base.metadata.tables) == ALLOWED_OPERATIONAL_TABLES


def test_no_candidate_data_in_any_log(catalogue: Catalogue, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        response = catalogue.client.post(URL, json={"profile": profile()})
    assert response.status_code == 200
    logged = caplog.text + "\n".join(str(record.args) for record in caplog.records)
    for marker in MARKERS:
        assert marker not in logged
    lines = [r.getMessage() for r in caplog.records if r.name == "eligicore.recommendations"]
    assert len(lines) == 1
    assert re.fullmatch(
        r"recommendations jobs_considered=4 jobs_not_considered=0 not_found=0 ranked=2 "
        r"needs_review=1 not_eligible=1 not_open=0 null_scores=0 corpus_size=6 "
        r"duration_ms=[\d.]+",
        lines[0],
    )
    # No per-job score or shared term anywhere in the logs.
    for item in response.json()["ranked"]:
        assert str(item["match"]["match_score"]) not in lines[0].split("duration_ms")[0]
        for term in item["match"]["top_terms"]:
            assert term["term"] not in caplog.text


def test_response_does_not_echo_the_profile(catalogue: Catalogue) -> None:
    text = catalogue.client.post(URL, json={"profile": profile()}).text
    for marker in (NAME, EMAIL, PHONE, SKILL, EXPERIENCE, RESUME_TEXT, INSTITUTION):
        assert marker not in text
    assert CANDIDATE_ID in text  # the one approved echo


def test_default_scope_over_the_cap_through_the_api(catalogue: Catalogue) -> None:
    with catalogue.factory() as session:
        for i in range(MAX_RECOMMENDATION_JOBS + 3):
            add_job(session, f"bulk-{i:03d}", last_verified_at=BASE_TIME - timedelta(days=1 + i))
        session.commit()
    body = catalogue.client.post(URL, json={"profile": profile()}).json()
    assert body["jobs_considered"] == MAX_RECOMMENDATION_JOBS
    # 4 seeded open jobs + 53 bulk open jobs; the oldest 7 bulk jobs fall outside the cap.
    assert body["jobs_not_considered"] == 7
    returned = {item["eligibility"]["job_id"] for g in ("ranked", "needs_review", "not_eligible") for item in body[g]}
    assert "bulk-052" not in returned and "bulk-000" in returned
    assert body["corpus_size"] == 6 + MAX_RECOMMENDATION_JOBS + 3


# ---------------------------------------------------------------------------------------
# Layered guards and corpus identity
# ---------------------------------------------------------------------------------------


def test_request_schema_deduplicates_in_first_seen_order() -> None:
    """The schema layer de-duplicates on its own; the service repeats it defensively (C-21)."""
    from app.schemas.matching import RecommendationRequest

    request = RecommendationRequest.model_validate(
        {"profile": {}, "job_ids": ["b", "a", "b", "c", "a"]}
    )
    assert request.job_ids == ["b", "a", "c"]
    assert RecommendationRequest.model_validate({"profile": {}}).job_ids is None
    assert RecommendationRequest.model_validate({"profile": {}, "job_ids": None}).job_ids is None


def test_fingerprint_ignores_verification_time_but_tracks_content(catalogue: Catalogue) -> None:
    """The corpus is taken in id order, so re-verifying jobs does not change its identity."""
    first = catalogue.client.post(URL, json={"profile": profile()}).json()["corpus_fingerprint"]

    with catalogue.factory() as session:
        for offset, job in enumerate(session.query(Job).order_by(Job.id).all()):
            job.last_verified_at = BASE_TIME + timedelta(days=100 - offset)
        session.commit()
    reverified = catalogue.client.post(URL, json={"profile": profile()}).json()
    assert reverified["corpus_fingerprint"] == first

    with catalogue.factory() as session:
        session.get(Job, "closed").description = "Rewritten posting text."
        session.commit()
    edited = catalogue.client.post(URL, json={"profile": profile()}).json()
    assert edited["corpus_fingerprint"] != first
