"""ADR-030 Step 6 wiring: stored derived requirements reach both eligibility endpoints.

Every derived row here is produced by real ingestion — extractors, verifier, storage — with
extraction enabled, never written by hand, except the one deliberately unusable row. The
evaluation-time read gate is switched on per test by replacing the settings the loader reads,
so nothing leaks into the process-wide settings cache.

Owner rulings implemented, and tested here by name:

* **Q1** — reads are gated on ``extraction_enabled``; off means no derived requirements.
* **Q2** — an unusable stored row is skipped alone, and only a count is logged.
* **Q3** — a database error while reading fails the request through the sanitized 500.
* **OD-14 / D20b** — both endpoints evaluate the same derived requirements, through the
  shared path, and their verdicts stay identical field for field (ADR-022 §5).
"""

from __future__ import annotations

import ast
import inspect
import logging
import pathlib
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.routers.eligibility as eligibility_router
import app.services.recommendations as recommendations_service
from app.ai.ai_service import AIService, get_lazy_ai_service
from app.config import Settings
from app.database import Base, get_db
from app.main import app
from app.models.extracted_requirement import ExtractedRequirement, ExtractionStatus
from app.models.job import Job
from app.schemas.candidate import GradeScale
from app.schemas.eligibility import RequirementProvenance, RequirementType
from app.schemas.extraction import RequirementStrength
from app.services import derived_requirements, requirement_derivation
from app.services.eligibility_ai import check_eligibility_with_ai
from app.services.job_ingestion import ingest_source
from app.services.recommendations import recommend
from app.services.requirement_derivation import (
    _to_verified,
    effective_derived_requirements_by_job,
    effective_requirements,
    source_text_digest,
)
from tests.conftest import ALLOWED_OPERATIONAL_TABLES, application_database_tables
from tests.test_eligibility_ai_stage import SpyProvider
from tests.test_eligibility_engine import edu
from tests.test_job_ingestion import FakeAdapter, make_raw

ENABLED = Settings(extraction_enabled=True)
DISABLED = Settings(extraction_enabled=False)

CHECK_URL = "/api/v1/eligibility/check"
RECS_URL = "/api/v1/recommendations"

#: Derives exactly one requirement: minimum CGPA 8.0 on the 10-point scale.
CGPA_ONLY = "Eligibility: minimum CGPA 8.0/10 required. Apply by 2026-03-01."
#: Derives all three Phase 1 types: CGPA 7.5/10, zero backlogs, graduation 2025-2026.
FULL = (
    "Backend Engineer. Eligibility: minimum CGPA 7.5/10 required. Candidates must have no "
    "active backlogs. Only the 2025-2026 graduating batch is required to apply."
)
NO_CRITERIA = "Backend Engineer. You will own the product backlog and ship weekly."
EVIDENCE_FRAGMENTS = ("minimum CGPA 8.0/10", "minimum CGPA 7.5/10", "no active backlogs")

#: Source-owned columns cleared, so the description is the only place a requirement lives.
NO_STRUCTURED = {"min_cgpa": None, "min_cgpa_scale": None}


def profile(cgpa: float = 9.0, *, backlogs: int = 0, **education: Any) -> dict[str, Any]:
    return {"education": [edu(cgpa=cgpa, grad_year=2026, **education)], "backlogs": backlogs}


# ---------------------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------------------


@dataclass
class Store:
    session: Session
    client: TestClient

    def ingest(self, *raws: Any) -> None:
        """One real ingestion run, with extraction on, so derived rows are genuine."""
        ingest_source(self.session, FakeAdapter(list(raws)), settings=ENABLED)

    def job(self, source_job_id: str) -> Job:
        return self.session.execute(
            select(Job).where(Job.source_job_id == source_job_id)
        ).scalar_one()

    def ids(self, *source_job_ids: str) -> list[str]:
        return [self.job(s).id for s in source_job_ids]

    def row_count(self) -> int:
        return self.session.execute(
            select(func.count()).select_from(ExtractedRequirement)
        ).scalar_one()


@pytest.fixture
def store() -> Iterator[Store]:
    """One shared in-memory database, seen by both the test and the endpoints."""
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
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
    with factory() as session:
        yield Store(session=session, client=TestClient(app))
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


@pytest.fixture
def reads_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Switch the evaluation-time read gate on for this test only (owner ruling Q1)."""
    monkeypatch.setattr(derived_requirements, "get_settings", lambda: ENABLED)


def check(store: Store, job_ids: list[str], body: dict[str, Any]) -> dict[str, Any]:
    response = store.client.post(CHECK_URL, json={"profile": body, "job_ids": job_ids})
    assert response.status_code == 200, response.text
    return {result["job_id"]: result for result in response.json()["results"]}


def recommendations(store: Store, job_ids: list[str], body: dict[str, Any]) -> dict[str, Any]:
    response = store.client.post(RECS_URL, json={"profile": body, "job_ids": job_ids})
    assert response.status_code == 200, response.text
    return response.json()


def items(recs: dict[str, Any]) -> dict[str, tuple[str, dict[str, Any]]]:
    return {
        item["eligibility"]["job_id"]: (group, item["eligibility"])
        for group in ("ranked", "needs_review", "not_eligible", "not_open")
        for item in recs[group]
    }


def provenances(result: dict[str, Any]) -> dict[str, str]:
    return {e["requirement_type"]: e["provenance"] for e in result["requirement_breakdown"]}


# ---------------------------------------------------------------------------------------
# The loader — what is in force, and nothing else
# ---------------------------------------------------------------------------------------


def test_the_batch_loader_agrees_with_effective_requirements(store: Store) -> None:
    store.ingest(
        make_raw(source_job_id="full", description=FULL, **NO_STRUCTURED),
        make_raw(source_job_id="cgpa", description=CGPA_ONLY, **NO_STRUCTURED),
        make_raw(source_job_id="none", description=NO_CRITERIA, **NO_STRUCTURED),
    )
    jobs = [store.job(s) for s in ("full", "cgpa", "none")]
    load = effective_derived_requirements_by_job(store.session, jobs)

    assert load.unusable == 0
    for job in jobs:
        expected = tuple(_to_verified(row) for row in effective_requirements(store.session, job))
        assert load.by_job.get(job.id, ()) == expected
    assert len(load.by_job[jobs[0].id]) == 3 and len(load.by_job[jobs[1].id]) == 1
    assert jobs[2].id not in load.by_job


def test_invalidated_and_stale_rows_are_not_in_force(store: Store) -> None:
    store.ingest(make_raw(source_job_id="a", description=CGPA_ONLY, **NO_STRUCTURED))
    job = store.job("a")
    # The description changes but extraction is off: the stored row stays ACTIVE, and is
    # now about text the job no longer holds.
    ingest_source(
        store.session,
        FakeAdapter([make_raw(source_job_id="a", description=NO_CRITERIA, **NO_STRUCTURED)]),
        settings=DISABLED,
    )
    store.session.refresh(job)
    (row,) = store.session.execute(select(ExtractedRequirement)).scalars().all()
    assert row.status is ExtractionStatus.ACTIVE
    assert row.source_text_digest != source_text_digest(job.description)
    assert effective_derived_requirements_by_job(store.session, [job]).by_job == {}

    row.invalidate()
    store.session.commit()
    assert effective_derived_requirements_by_job(store.session, [job]).by_job == {}


def test_a_to_b_to_a_reads_only_the_new_derivation(store: Store) -> None:
    store.ingest(make_raw(source_job_id="a", description=CGPA_ONLY, **NO_STRUCTURED))
    job = store.job("a")
    first_id = effective_requirements(store.session, job)[0].id
    store.ingest(make_raw(source_job_id="a", description=NO_CRITERIA, **NO_STRUCTURED))
    store.ingest(make_raw(source_job_id="a", description=CGPA_ONLY, **NO_STRUCTURED))
    store.session.refresh(job)

    (current,) = effective_requirements(store.session, job)
    assert current.id != first_id
    assert store.session.get(ExtractedRequirement, first_id).status is ExtractionStatus.INVALIDATED
    (loaded,) = effective_derived_requirements_by_job(store.session, [job]).by_job[job.id]
    assert loaded == _to_verified(current)


def test_every_type_round_trips_from_storage(store: Store) -> None:
    store.ingest(make_raw(source_job_id="full", description=FULL, **NO_STRUCTURED))
    job = store.job("full")
    loaded = {r.requirement_type: r for r in
              effective_derived_requirements_by_job(store.session, [job]).by_job[job.id]}

    assert loaded[RequirementType.MIN_CGPA].value.min_cgpa == 7.5
    assert loaded[RequirementType.MIN_CGPA].value.min_cgpa_scale is GradeScale.SCALE_10
    assert loaded[RequirementType.MAX_BACKLOGS].value.max_backlogs == 0
    window = loaded[RequirementType.GRAD_YEAR_WINDOW].value
    assert (window.min_grad_year, window.max_grad_year) == (2025, 2026)
    for requirement in loaded.values():
        assert requirement.provenance is RequirementProvenance.PROSE_DERIVED
        assert requirement.strength is RequirementStrength.REQUIRED
        assert requirement.evidence_text and requirement.evidence_text in job.description


def test_the_query_is_chunked_without_changing_the_answer(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    store.ingest(*(make_raw(source_job_id=f"j{i}", description=CGPA_ONLY, **NO_STRUCTURED)
                   for i in range(5)))
    jobs = [store.job(f"j{i}") for i in range(5)]
    whole = effective_derived_requirements_by_job(store.session, jobs)
    monkeypatch.setattr(requirement_derivation, "_JOB_ID_CHUNK", 2)
    assert effective_derived_requirements_by_job(store.session, jobs) == whole
    assert len(whole.by_job) == 5


# ---------------------------------------------------------------------------------------
# Owner ruling Q2 — an unusable row is skipped alone and counted
# ---------------------------------------------------------------------------------------


def transient(**columns: Any) -> ExtractedRequirement:
    base: dict[str, Any] = {
        "requirement_type": RequirementType.MIN_CGPA, "min_cgpa": 7.0,
        "min_cgpa_scale": GradeScale.SCALE_10, "evidence_text": "Minimum CGPA 7.0/10.",
        "provenance": RequirementProvenance.PROSE_DERIVED,
        "strength": RequirementStrength.REQUIRED, "extractor": "x", "extractor_version": "1",
    }
    base.update(columns)
    return ExtractedRequirement(**base)


@pytest.mark.parametrize(
    "columns",
    [
        {"evidence_text": ""},
        {"min_cgpa": None},
        {"min_cgpa_scale": GradeScale.UNKNOWN},
        {"requirement_type": RequirementType.GRAD_YEAR_WINDOW, "min_cgpa": None,
         "min_cgpa_scale": None},
        {"requirement_type": RequirementType.MAX_BACKLOGS, "min_cgpa": None,
         "min_cgpa_scale": None},
        {"requirement_type": RequirementType.ALLOWED_FIELDS},
        {"provenance": RequirementProvenance.SOURCE_STATED},
    ],
    ids=["empty-evidence", "no-value", "unknown-scale", "boundless-window", "no-limit",
         "non-phase-1-type", "source-stated"],
)
def test_a_row_that_cannot_be_read_back_is_refused(columns: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        _to_verified(transient(**columns))


def test_an_unusable_row_is_skipped_alone_and_counted(store: Store) -> None:
    store.ingest(make_raw(source_job_id="a", description=CGPA_ONLY, **NO_STRUCTURED))
    job = store.job("a")
    # Bypasses the verifier: the database allows an empty string, nothing else would.
    store.session.add(ExtractedRequirement(
        id="unusable-row", job_id=job.id, source_text_digest=source_text_digest(job.description),
        content_hash=job.content_hash, requirement_type=RequirementType.MAX_BACKLOGS,
        max_backlogs=1, evidence_text="", extractor="x", extractor_version="1",
    ))
    store.session.commit()

    load = effective_derived_requirements_by_job(store.session, [job])
    assert load.unusable == 1
    assert [r.requirement_type for r in load.by_job[job.id]] == [RequirementType.MIN_CGPA]


def test_only_the_count_is_logged(
    store: Store, reads_enabled: None, caplog: pytest.LogCaptureFixture
) -> None:
    test_an_unusable_row_is_skipped_alone_and_counted(store)
    job = store.job("a")
    with caplog.at_level(logging.DEBUG):
        derived_requirements.load_derived_requirements(store.session, [job])
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings == ["derived_requirements unusable_rows=1"]
    for fragment in (*EVIDENCE_FRAGMENTS, job.id, job.description):
        assert fragment not in caplog.text


def test_nothing_is_logged_when_every_row_is_usable(
    store: Store, reads_enabled: None, caplog: pytest.LogCaptureFixture
) -> None:
    store.ingest(make_raw(source_job_id="a", description=FULL, **NO_STRUCTURED))
    with caplog.at_level(logging.DEBUG, logger="eligicore.eligibility"):
        derived_requirements.load_derived_requirements(store.session, [store.job("a")])
    assert "derived_requirements" not in caplog.text


# ---------------------------------------------------------------------------------------
# Owner ruling Q1 — the read gate
# ---------------------------------------------------------------------------------------


def test_reads_are_off_unless_extraction_is_enabled(store: Store) -> None:
    store.ingest(make_raw(source_job_id="a", description=FULL, **NO_STRUCTURED))
    job = store.job("a")
    before = [(r.id, r.status) for r in store.session.execute(select(ExtractedRequirement))
              .scalars()]

    assert derived_requirements.load_derived_requirements(
        store.session, [job], settings=DISABLED) == {}
    assert derived_requirements.load_derived_requirements(
        store.session, [job], settings=ENABLED)[job.id]
    after = [(r.id, r.status) for r in store.session.execute(select(ExtractedRequirement))
             .scalars()]
    assert after == before and len(before) == 3


def test_with_the_gate_off_stored_rows_change_no_response(store: Store) -> None:
    """The default configuration: rows exist, and both endpoints behave as before ADR-030."""
    store.ingest(make_raw(source_job_id="a", description=CGPA_ONLY, **NO_STRUCTURED))
    ids = store.ids("a")
    low = profile(cgpa=6.0)

    result = check(store, ids, low)[ids[0]]
    assert result["eligibility_state"] == "ELIGIBLE"
    assert result["requirement_breakdown"] == []
    group, embedded = items(recommendations(store, ids, low))[ids[0]]
    assert (group, embedded) == ("ranked", result)


# ---------------------------------------------------------------------------------------
# Owner ruling Q3 — database errors fail the request, sanitized
# ---------------------------------------------------------------------------------------

DB_SECRET = "SECRET-DB-DETAIL-extracted_requirements"


def explode(*_args: Any, **_kwargs: Any) -> Any:
    raise OperationalError(f"SELECT * FROM {DB_SECRET}", {}, Exception(DB_SECRET))


def test_a_database_error_is_not_swallowed_by_the_loader(store: Store) -> None:
    store.ingest(make_raw(source_job_id="a", description=CGPA_ONLY, **NO_STRUCTURED))
    job = store.job("a")

    class FailingSession:
        def execute(self, *_args: Any, **_kwargs: Any) -> Any:
            explode()

    with pytest.raises(OperationalError):
        effective_derived_requirements_by_job(FailingSession(), [job])  # type: ignore[arg-type]


@pytest.mark.parametrize("url", [CHECK_URL, RECS_URL])
def test_a_database_error_fails_the_request_through_the_sanitized_500(
    store: Store, reads_enabled: None, monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture, url: str,
) -> None:
    store.ingest(make_raw(source_job_id="a", description=CGPA_ONLY, **NO_STRUCTURED))
    monkeypatch.setattr(derived_requirements, "effective_derived_requirements_by_job", explode)
    client = TestClient(app, raise_server_exceptions=False)

    with caplog.at_level(logging.DEBUG):
        response = client.post(url, json={"profile": profile(), "job_ids": store.ids("a")})

    assert response.status_code == 500
    assert response.json()["error"] == "INTERNAL_ERROR"
    assert DB_SECRET not in response.text and "SELECT" not in response.text
    assert DB_SECRET not in caplog.text
    assert "type=OperationalError" in caplog.text


# ---------------------------------------------------------------------------------------
# Verdicts through both endpoints
# ---------------------------------------------------------------------------------------


def test_a_derived_failure_is_needs_review_on_both_endpoints(
    store: Store, reads_enabled: None
) -> None:
    store.ingest(make_raw(source_job_id="a", description=CGPA_ONLY, **NO_STRUCTURED))
    ids = store.ids("a")
    result = check(store, ids, profile(cgpa=7.0))[ids[0]]

    assert result["eligibility_state"] == "NEEDS_REVIEW"
    (entry,) = result["requirement_breakdown"]
    assert (entry["provenance"], entry["status"], entry["confidence"]) == (
        "PROSE_DERIVED", "FAIL", "MEDIUM")
    assert entry["evidence"] and entry["evidence"] in CGPA_ONLY
    assert items(recommendations(store, ids, profile(cgpa=7.0)))[ids[0]] == (
        "needs_review", result)


def test_a_derived_pass_is_likely_eligible_and_ranked(store: Store, reads_enabled: None) -> None:
    store.ingest(make_raw(source_job_id="a", description=CGPA_ONLY, **NO_STRUCTURED))
    ids = store.ids("a")
    result = check(store, ids, profile(cgpa=9.0))[ids[0]]

    assert result["eligibility_state"] == "LIKELY_ELIGIBLE"
    assert items(recommendations(store, ids, profile(cgpa=9.0)))[ids[0]] == ("ranked", result)


@pytest.mark.parametrize("scale", ["SCALE_10", None], ids=["usable", "scale-missing"])
def test_r_collision_through_the_endpoint(
    store: Store, reads_enabled: None, scale: str | None
) -> None:
    """The source states a CGPA, so the derived one (7.5/10, which 7.2 fails) never counts —
    including when the source's own value is unusable for lack of a scale (D20a)."""
    store.ingest(make_raw(source_job_id="a", description=FULL, min_cgpa=7.0,
                          min_cgpa_scale=scale))
    ids = store.ids("a")
    result = check(store, ids, profile(cgpa=7.2))[ids[0]]

    cgpa = [e for e in result["requirement_breakdown"] if e["requirement_type"] == "MIN_CGPA"]
    assert len(cgpa) == 1 and cgpa[0]["provenance"] == "SOURCE_STATED"
    assert cgpa[0]["evidence"] is None
    assert cgpa[0]["status"] == ("PASS" if scale else "UNKNOWN")
    assert provenances(result)["MAX_BACKLOGS"] == "PROSE_DERIVED"


def test_a_source_stated_failure_still_decides(store: Store, reads_enabled: None) -> None:
    store.ingest(make_raw(source_job_id="a", description=FULL, max_backlogs=0, **NO_STRUCTURED))
    ids = store.ids("a")
    result = check(store, ids, profile(cgpa=9.0, backlogs=2))[ids[0]]

    assert result["eligibility_state"] == "NOT_ELIGIBLE"
    assert provenances(result) == {
        "MIN_CGPA": "PROSE_DERIVED", "GRAD_YEAR_WINDOW": "PROSE_DERIVED",
        "MAX_BACKLOGS": "SOURCE_STATED",
    }
    assert items(recommendations(store, ids, profile(cgpa=9.0, backlogs=2)))[ids[0]][0] == (
        "not_eligible")


# ---------------------------------------------------------------------------------------
# OD-14 / D20b — the same derived requirements, and identical verdicts
# ---------------------------------------------------------------------------------------


def parity_catalogue(store: Store) -> list[str]:
    store.ingest(
        make_raw(source_job_id="fail", description=CGPA_ONLY, **NO_STRUCTURED),
        make_raw(source_job_id="all3", description=FULL, **NO_STRUCTURED),
        make_raw(source_job_id="collide", description=FULL, min_cgpa=7.0,
                 min_cgpa_scale="SCALE_10"),
        make_raw(source_job_id="hard", description=FULL, max_backlogs=0, **NO_STRUCTURED),
        make_raw(source_job_id="plain", description=NO_CRITERIA, **NO_STRUCTURED),
    )
    return store.ids("fail", "all3", "collide", "hard", "plain")


def test_recommendation_verdicts_equal_the_eligibility_endpoint_with_derived_rows(
    store: Store, reads_enabled: None
) -> None:
    ids = parity_catalogue(store)
    body = profile(cgpa=7.8, backlogs=1)
    checked = check(store, ids, body)
    recommended = items(recommendations(store, ids, body))

    assert set(recommended) == set(checked) == set(ids)
    for job_id in ids:
        assert recommended[job_id][1] == checked[job_id]
    derived_anywhere = [e for r in checked.values() for e in r["requirement_breakdown"]
                        if e["provenance"] == "PROSE_DERIVED"]
    assert derived_anywhere, "the parity check must exercise derived requirements"


def test_both_endpoints_hand_the_shared_path_the_same_derived_requirements(
    store: Store, reads_enabled: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = parity_catalogue(store)
    seen: dict[str, dict[str, Any]] = {}

    def spy_on(module: Any, name: str) -> None:
        async def spy(profile_, job_ids, jobs_by_id, ai_service, *, derived_by_job):
            seen[name] = {job_id: tuple(derived_by_job.get(job_id, ())) for job_id in job_ids}
            return await check_eligibility_with_ai(
                profile_, job_ids, jobs_by_id, ai_service, derived_by_job=derived_by_job
            )
        monkeypatch.setattr(module, "check_eligibility_with_ai", spy)

    spy_on(eligibility_router, "check")
    spy_on(recommendations_service, "recommendations")
    check(store, ids, profile())
    recommendations(store, ids, profile())

    assert seen["check"] == seen["recommendations"]
    assert sum(len(v) for v in seen["check"].values()) == 1 + 3 + 3 + 3


# ---------------------------------------------------------------------------------------
# D4a through HTTP — a derived failure leaves the AI stage reachable
# ---------------------------------------------------------------------------------------

CS = ["Computer Science"]


@pytest.mark.parametrize(
    "structured,expected_state,expected_calls",
    [(NO_STRUCTURED, "NEEDS_REVIEW", 1),
     ({"min_cgpa": 8.0, "min_cgpa_scale": "SCALE_10"}, "NOT_ELIGIBLE", 0)],
    ids=["derived-failure-reaches-ai", "source-failure-closes-ai"],
)
def test_d4a_through_the_endpoint(
    store: Store, reads_enabled: None, structured: dict[str, Any], expected_state: str,
    expected_calls: int,
) -> None:
    store.ingest(make_raw(source_job_id="a", description=CGPA_ONLY, allowed_fields=CS,
                          **structured))
    spy = SpyProvider()
    app.dependency_overrides[get_lazy_ai_service] = lambda: AIService(spy)
    ids = store.ids("a")

    result = check(store, ids, profile(cgpa=7.0, field_of_study="Computer Science and Engineering"))[ids[0]]

    assert result["eligibility_state"] == expected_state
    assert len(spy.calls) == expected_calls
    field = [e for e in result["requirement_breakdown"] if e["requirement_type"] == "ALLOWED_FIELDS"]
    assert field[0]["reason_code"] == (
        "AI_FIELD_RELATED" if expected_calls else "SKIPPED_AFTER_HARD_FAILURE")


# ---------------------------------------------------------------------------------------
# Boundaries: nothing extracted, nothing written, nothing logged, nothing omitted
# ---------------------------------------------------------------------------------------


def test_a_request_extracts_nothing_and_writes_nothing(
    store: Store, reads_enabled: None, monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    ids = parity_catalogue(store)
    rows_before = store.row_count()

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("a request reached derivation or extraction (ADR-030 D21)")

    for name in ("derive_for_job", "extract_requirements", "verify_proposals"):
        monkeypatch.setattr(requirement_derivation, name, forbidden)

    marker = "CANDIDATE-FIELD-MARKER-7f"
    with caplog.at_level(logging.DEBUG):
        check(store, ids, profile(field_of_study=marker))
        recommendations(store, ids, profile(field_of_study=marker))

    assert store.row_count() == rows_before
    assert application_database_tables() <= ALLOWED_OPERATIONAL_TABLES
    for fragment in (*EVIDENCE_FRAGMENTS, marker):
        assert fragment not in caplog.text


@pytest.mark.parametrize("function", [check_eligibility_with_ai, recommend])
def test_the_shared_path_requires_derived_requirements(function: Any) -> None:
    """No default: a caller cannot evaluate without stating what it supplies (D20b)."""
    parameter = inspect.signature(function).parameters["derived_by_job"]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is inspect.Parameter.empty


def test_recommendation_code_never_loads_derived_requirements() -> None:
    """D20b: recommendations group the verdict they are given; they read no derived data."""
    tree = ast.parse(pathlib.Path(recommendations_service.__file__).read_text(encoding="utf-8"))
    guarded = {
        id(node)
        for block in ast.walk(tree)
        if isinstance(block, ast.If) and getattr(block.test, "id", None) == "TYPE_CHECKING"
        for node in ast.walk(block)
    }
    runtime = {
        node.module for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module and id(node) not in guarded
    }
    for forbidden in ("app.services.derived_requirements", "app.services.requirement_derivation",
                      "app.models", "app.schemas.extraction", "app.database"):
        assert not any(m == forbidden or m.startswith(f"{forbidden}.") for m in runtime), forbidden
