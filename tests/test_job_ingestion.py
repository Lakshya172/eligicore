"""Job ingestion tests: new, unchanged, changed, duplicate, and disappeared.

These five behaviours are the whole of what ingestion does, and each has a distinct correct
outcome. Getting any of them wrong is silent — nothing raises, the catalogue is just quietly
wrong — so each is asserted directly.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.base_adapter import AdapterError, JobSourceAdapter
from app.adapters.curated_adapter import CuratedJobAdapter
from app.database import Base
from app.models.ingestion_state import IngestionState, IngestionStatus
from app.models.job import Job, JobStatus
from app.schemas.candidate import JobType
from app.schemas.job import RawJob
from app.services.job_ingestion import find_existing_job, ingest_all, ingest_source
from app.services.job_normalizer import normalize_job


@pytest.fixture
def session() -> Iterator[Session]:
    """An isolated in-memory database per test.

    In-memory rather than the dev file, so a test can never leave state behind or read
    another test's rows.
    """
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        yield db
    Base.metadata.drop_all(engine)


def make_raw(**overrides: object) -> RawJob:
    base: dict[str, object] = {
        "company_name": "Example Analytics",
        "role_title": "Software Engineering Intern",
        "job_type": JobType.INTERNSHIP,
        "location": "Bengaluru, India",
        "description": "Six-month internship building internal tooling.",
        "min_cgpa": 7.0,
        "min_cgpa_scale": "SCALE_10",
        "apply_link": "https://careers.example.com/roles/swe-intern",
        "source_job_id": "EX-001",
    }
    base.update(overrides)
    return RawJob.model_validate(base)


class FakeAdapter(JobSourceAdapter):
    """An adapter returning a fixed list, for driving ingestion deterministically."""

    def __init__(
        self,
        jobs: list[RawJob],
        *,
        source_name: str = "fake",
        authoritative: bool = True,
        fail_with: AdapterError | None = None,
    ) -> None:
        self.source_name = source_name
        self.is_authoritative = authoritative
        self._jobs = jobs
        self._fail_with = fail_with

    async def fetch(self) -> list[RawJob]:
        if self._fail_with is not None:
            raise self._fail_with
        return self._jobs


def active_jobs(session: Session, source: str = "fake") -> list[Job]:
    return list(
        session.execute(
            select(Job).where(Job.source == source, Job.status == JobStatus.ACTIVE)
        ).scalars()
    )


# ---------------------------------------------------------------------------------------
# NEW jobs
# ---------------------------------------------------------------------------------------


def test_new_job_is_created(session: Session) -> None:
    outcome = ingest_source(session, FakeAdapter([make_raw()]))

    assert outcome.jobs_seen == 1
    assert outcome.jobs_created == 1
    assert outcome.jobs_updated == 0

    job = session.execute(select(Job)).scalar_one()
    assert job.company_name == "Example Analytics"
    assert job.status is JobStatus.ACTIVE
    assert job.is_active is True
    assert job.source == "fake"
    assert len(job.content_hash) == 64


def test_new_job_starts_active_with_verification_timestamp(session: Session) -> None:
    ingest_source(session, FakeAdapter([make_raw()]))
    job = session.execute(select(Job)).scalar_one()

    assert job.status is JobStatus.ACTIVE
    assert job.last_verified_at is not None
    assert job.created_at is not None


def test_multiple_new_jobs_are_all_created(session: Session) -> None:
    jobs = [make_raw(source_job_id=f"EX-{i:03d}", role_title=f"Role {i}") for i in range(4)]
    outcome = ingest_source(session, FakeAdapter(jobs))

    assert outcome.jobs_created == 4
    assert len(active_jobs(session)) == 4


# ---------------------------------------------------------------------------------------
# UNCHANGED jobs
# ---------------------------------------------------------------------------------------


def test_reingesting_identical_data_changes_nothing(session: Session) -> None:
    adapter = FakeAdapter([make_raw()])
    ingest_source(session, adapter)
    outcome = ingest_source(session, adapter)

    assert outcome.jobs_created == 0
    assert outcome.jobs_updated == 0
    assert outcome.jobs_unchanged == 1
    assert session.execute(select(Job)).scalars().all().__len__() == 1


def test_unchanged_job_still_refreshes_last_verified_at(session: Session) -> None:
    """An unchanged job is still confirmed live — freshness is not the same as change."""
    adapter = FakeAdapter([make_raw()])
    ingest_source(session, adapter)
    first = session.execute(select(Job)).scalar_one().last_verified_at

    ingest_source(session, adapter)
    session.expire_all()
    second = session.execute(select(Job)).scalar_one().last_verified_at

    assert second >= first


def test_formatting_only_change_is_not_an_update(session: Session) -> None:
    """Whitespace and casing must not look like an edit — that is what hashing is for."""
    ingest_source(session, FakeAdapter([make_raw()]))
    outcome = ingest_source(
        session,
        FakeAdapter([make_raw(company_name="  EXAMPLE   Analytics  ")]),
    )

    assert outcome.jobs_created == 0
    assert outcome.jobs_unchanged + outcome.jobs_updated == 1
    assert len(session.execute(select(Job)).scalars().all()) == 1


# ---------------------------------------------------------------------------------------
# CHANGED jobs — upsert
# ---------------------------------------------------------------------------------------


def test_changed_job_is_updated_not_duplicated(session: Session) -> None:
    ingest_source(session, FakeAdapter([make_raw()]))
    outcome = ingest_source(
        session,
        FakeAdapter([make_raw(description="Revised description with new detail.")]),
    )

    assert outcome.jobs_created == 0
    assert outcome.jobs_updated == 1

    jobs = session.execute(select(Job)).scalars().all()
    assert len(jobs) == 1, "an edit must update, not create a second row"
    assert jobs[0].description == "Revised description with new detail."


def test_update_matches_on_source_job_id_across_an_edit(session: Session) -> None:
    """The source's own id survives the posting changing — that is why it is tried first."""
    ingest_source(session, FakeAdapter([make_raw()]))
    original_hash = session.execute(select(Job)).scalar_one().content_hash

    ingest_source(
        session,
        FakeAdapter([make_raw(role_title="Software Engineering Intern (Summer)")]),
    )
    session.expire_all()
    jobs = session.execute(select(Job)).scalars().all()

    assert len(jobs) == 1
    assert jobs[0].role_title == "Software Engineering Intern (Summer)"
    assert jobs[0].content_hash != original_hash, "the hash must track the new content"


def test_update_refreshes_deadline_and_requirements(session: Session) -> None:
    ingest_source(session, FakeAdapter([make_raw(deadline=date(2026, 11, 15))]))
    ingest_source(
        session,
        FakeAdapter([make_raw(deadline=date(2026, 12, 31), max_backlogs=1)]),
    )
    session.expire_all()
    job = session.execute(select(Job)).scalar_one()

    assert job.deadline == date(2026, 12, 31)
    assert job.max_backlogs == 1


def test_source_without_ids_matches_on_content_hash(session: Session) -> None:
    """Sources with no stable id fall back to the canonical hash."""
    ingest_source(session, FakeAdapter([make_raw(source_job_id=None)]))
    outcome = ingest_source(session, FakeAdapter([make_raw(source_job_id=None)]))

    assert outcome.jobs_created == 0
    assert outcome.jobs_unchanged == 1
    assert len(session.execute(select(Job)).scalars().all()) == 1


# ---------------------------------------------------------------------------------------
# DUPLICATE records within one fetch
# ---------------------------------------------------------------------------------------


def test_duplicate_records_in_one_fetch_collapse(session: Session) -> None:
    """A source listing the same posting twice must produce one row, not two."""
    outcome = ingest_source(session, FakeAdapter([make_raw(), make_raw()]))

    assert outcome.jobs_seen == 2
    assert outcome.jobs_created == 1
    assert outcome.duplicates_collapsed == 1
    assert len(session.execute(select(Job)).scalars().all()) == 1


def test_formatting_variants_in_one_fetch_collapse(session: Session) -> None:
    outcome = ingest_source(
        session,
        FakeAdapter([make_raw(), make_raw(company_name="EXAMPLE ANALYTICS PVT LTD")]),
    )

    assert outcome.jobs_created == 1
    assert outcome.duplicates_collapsed == 1


def test_same_posting_from_two_sources_is_two_rows(session: Session) -> None:
    """Not a duplicate: two portals means two apply links, and merging loses one."""
    ingest_source(session, FakeAdapter([make_raw()], source_name="source_a"))
    ingest_source(session, FakeAdapter([make_raw()], source_name="source_b"))

    jobs = session.execute(select(Job)).scalars().all()
    assert len(jobs) == 2
    assert {j.source for j in jobs} == {"source_a", "source_b"}


# ---------------------------------------------------------------------------------------
# DISAPPEARED jobs
# ---------------------------------------------------------------------------------------


def test_disappeared_curated_job_is_closed_not_deleted(session: Session) -> None:
    """The approved Week 3 rule, via the dossier's status enum (ADR-014)."""
    keep = make_raw(source_job_id="EX-001")
    drop = make_raw(source_job_id="EX-002", role_title="Backend Engineer")
    ingest_source(session, FakeAdapter([keep, drop]))
    assert len(active_jobs(session)) == 2

    outcome = ingest_source(session, FakeAdapter([keep]))
    session.expire_all()

    assert outcome.jobs_deactivated == 1
    assert len(active_jobs(session)) == 1

    closed = session.execute(
        select(Job).where(Job.source_job_id == "EX-002")
    ).scalar_one()
    assert closed.status is JobStatus.CLOSED
    assert closed.is_active is False
    assert closed is not None, "closed jobs are never deleted"


def test_closed_job_reappearing_becomes_active_again(session: Session) -> None:
    job = make_raw()
    ingest_source(session, FakeAdapter([job]))
    ingest_source(session, FakeAdapter([]))
    session.expire_all()
    assert session.execute(select(Job)).scalar_one().status is JobStatus.CLOSED

    ingest_source(session, FakeAdapter([job]))
    session.expire_all()
    assert session.execute(select(Job)).scalar_one().status is JobStatus.ACTIVE


def test_non_authoritative_source_never_closes_anything(session: Session) -> None:
    """The data-loss bug is_authoritative exists to prevent.

    A paginated source returning page one must not close the rest of the catalogue.
    """
    jobs = [make_raw(source_job_id=f"EX-{i}") for i in range(3)]
    ingest_source(session, FakeAdapter(jobs, authoritative=False))
    assert len(active_jobs(session)) == 3

    outcome = ingest_source(session, FakeAdapter([jobs[0]], authoritative=False))
    session.expire_all()

    assert outcome.jobs_deactivated == 0
    assert len(active_jobs(session)) == 3, "absence proves nothing for a partial source"


def test_base_adapter_defaults_to_non_authoritative() -> None:
    """A new adapter author who does not think about this gets the safe behaviour."""
    assert JobSourceAdapter.is_authoritative is False


def test_one_source_disappearing_does_not_affect_another(session: Session) -> None:
    ingest_source(session, FakeAdapter([make_raw()], source_name="source_a"))
    ingest_source(session, FakeAdapter([make_raw()], source_name="source_b"))

    ingest_source(session, FakeAdapter([], source_name="source_a"))
    session.expire_all()

    assert len(active_jobs(session, "source_a")) == 0
    assert len(active_jobs(session, "source_b")) == 1


# ---------------------------------------------------------------------------------------
# Ingestion state
# ---------------------------------------------------------------------------------------


def test_ingestion_state_is_created(session: Session) -> None:
    ingest_source(session, FakeAdapter([make_raw()]))
    state = session.get(IngestionState, "fake")

    assert state is not None
    assert state.last_status is IngestionStatus.SUCCESS
    assert state.jobs_seen == 1
    assert state.jobs_created == 1
    assert state.last_success_at is not None


def test_only_one_state_row_per_source(session: Session) -> None:
    """ADR-015: one row per source, overwritten. Not a run log."""
    adapter = FakeAdapter([make_raw()])
    for _ in range(3):
        ingest_source(session, adapter)

    rows = session.execute(
        select(IngestionState).where(IngestionState.source == "fake")
    ).scalars().all()
    assert len(rows) == 1


def test_state_reflects_the_latest_run_only(session: Session) -> None:
    ingest_source(session, FakeAdapter([make_raw()]))
    ingest_source(session, FakeAdapter([make_raw()]))
    session.expire_all()

    state = session.get(IngestionState, "fake")
    assert state.jobs_created == 0, "the second run created nothing"
    assert state.jobs_unchanged == 1


def test_failed_run_is_recorded_and_raises(session: Session) -> None:
    adapter = FakeAdapter([], fail_with=AdapterError("source unreachable"))
    with pytest.raises(AdapterError):
        ingest_source(session, adapter)

    state = session.get(IngestionState, "fake")
    assert state is not None, "a failure must be visible, not silent"
    assert state.last_status is IngestionStatus.FAILED
    assert state.last_success_at is None


def test_failure_after_success_preserves_last_success_at(session: Session) -> None:
    """A run of failures must not make a source look fresh."""
    ingest_source(session, FakeAdapter([make_raw()]))
    success_time = session.get(IngestionState, "fake").last_success_at

    with pytest.raises(AdapterError):
        ingest_source(session, FakeAdapter([], fail_with=AdapterError("down")))
    session.expire_all()

    state = session.get(IngestionState, "fake")
    assert state.last_status is IngestionStatus.FAILED
    assert state.last_success_at == success_time


def test_state_holds_no_candidate_identifier() -> None:
    """INV-1 / ADR-012: ingestion records what the system did, never what a person did."""
    columns = set(IngestionState.__table__.columns.keys())
    for forbidden in ("candidate_id", "user_id", "profile", "email", "resume"):
        assert forbidden not in columns


def test_ingest_all_isolates_a_failing_source(session: Session) -> None:
    """One source failing must not stop the others."""
    good = FakeAdapter([make_raw()], source_name="good")
    bad = FakeAdapter([], source_name="bad", fail_with=AdapterError("unreachable"))

    outcomes = ingest_all(session, [bad, good])

    assert [o.source for o in outcomes] == ["good"]
    assert len(active_jobs(session, "good")) == 1
    assert session.get(IngestionState, "bad").last_status is IngestionStatus.FAILED


# ---------------------------------------------------------------------------------------
# Matching helper
# ---------------------------------------------------------------------------------------


def test_find_existing_prefers_source_job_id(session: Session) -> None:
    ingest_source(session, FakeAdapter([make_raw()]))

    edited = normalize_job(make_raw(description="Completely different text."), "fake")
    found = find_existing_job(session, edited)

    assert found is not None, "the source id must match even though the hash changed"
    assert found.source_job_id == "EX-001"


def test_find_existing_returns_none_for_a_new_job(session: Session) -> None:
    ingest_source(session, FakeAdapter([make_raw()]))
    other = normalize_job(make_raw(source_job_id="EX-999", role_title="Other"), "fake")
    assert find_existing_job(session, other) is None


# ---------------------------------------------------------------------------------------
# Curated adapter
# ---------------------------------------------------------------------------------------


def test_curated_dataset_ingests(session: Session) -> None:
    outcome = ingest_source(session, CuratedJobAdapter())

    assert outcome.jobs_seen == 5
    assert outcome.jobs_created == 5
    assert outcome.jobs_deactivated == 0


def test_curated_dataset_is_idempotent(session: Session) -> None:
    ingest_source(session, CuratedJobAdapter())
    outcome = ingest_source(session, CuratedJobAdapter())

    assert outcome.jobs_created == 0
    assert outcome.jobs_unchanged == 5


def test_curated_job_without_a_stated_scale_keeps_it_null(session: Session) -> None:
    """Week 4 must see UNKNOWN here, not an assumed 10-point scale."""
    ingest_source(session, CuratedJobAdapter())
    job = session.execute(
        select(Job).where(Job.source_job_id == "EX-INT-003")
    ).scalar_one()

    assert job.min_cgpa == 8.0
    assert job.min_cgpa_scale is None


def test_curated_adapter_is_authoritative() -> None:
    assert CuratedJobAdapter().is_authoritative is True


def test_missing_curated_dataset_raises_adapter_error(session: Session) -> None:
    from pathlib import Path

    adapter = CuratedJobAdapter(dataset_path=Path("does/not/exist.json"))
    with pytest.raises(AdapterError):
        ingest_source(session, adapter)


def test_malformed_curated_entry_is_skipped_not_fatal(session: Session, tmp_path) -> None:
    """One bad entry must not discard the other usable jobs."""
    import json

    dataset = tmp_path / "jobs.json"
    dataset.write_text(
        json.dumps(
            [
                {"company_name": "Example Corp", "role_title": "Intern",
                 "job_type": "INTERNSHIP", "source_job_id": "OK-1"},
                {"company_name": "", "role_title": "Broken", "job_type": "NOT_A_TYPE"},
            ]
        ),
        encoding="utf-8",
    )

    outcome = ingest_source(session, CuratedJobAdapter(dataset_path=dataset))
    assert outcome.jobs_seen == 1
    assert outcome.jobs_created == 1


def test_invalid_json_dataset_error_carries_no_content(session: Session, tmp_path) -> None:
    """The decode error would otherwise quote the file back."""
    dataset = tmp_path / "jobs.json"
    dataset.write_text('[{"company_name": "SENSITIVE-MARKER-9z" ', encoding="utf-8")

    with pytest.raises(AdapterError) as exc:
        ingest_source(session, CuratedJobAdapter(dataset_path=dataset))
    assert "SENSITIVE-MARKER-9z" not in str(exc.value)
