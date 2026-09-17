"""``min_degree_level`` on the job catalogue (ruling C-10, ADR-018).

An additive Week 4 change to Week 3 contracts. These tests pin that the field flows through
every layer — adapter contract, normalization, ingestion updates, storage constraint and the
read API — and that the merged migrations were not edited to get it there.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.job import Job
from app.schemas.candidate import DegreeLevel
from app.schemas.job import JobRead
from app.services.job_ingestion import ingest_source
from app.services.job_normalizer import normalize_job
from tests.test_job_ingestion import FakeAdapter, make_raw

ROOT = Path(__file__).resolve().parent.parent
VERSIONS = ROOT / "alembic" / "versions"


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as db:
        yield db


def test_raw_job_defaults_to_no_degree_requirement() -> None:
    assert make_raw().min_degree_level is None


def test_raw_job_accepts_a_degree_level() -> None:
    assert make_raw(min_degree_level="MASTERS").min_degree_level is DegreeLevel.MASTERS


@pytest.mark.parametrize("value", ["PHD", "bachelors degree", "", 3])
def test_raw_job_rejects_a_value_outside_degree_level(value: object) -> None:
    with pytest.raises(ValidationError):
        make_raw(min_degree_level=value)


def test_normalization_passes_degree_level_through_unchanged() -> None:
    normalized = normalize_job(make_raw(min_degree_level=DegreeLevel.BACHELORS), "curated")
    assert normalized.min_degree_level is DegreeLevel.BACHELORS
    assert normalize_job(make_raw(), "curated").min_degree_level is None


def test_degree_level_does_not_change_the_content_hash() -> None:
    """Consistent with every other structured criterion: not a hash input (dossier §10.2)."""
    plain = normalize_job(make_raw(), "curated").content_hash
    with_level = normalize_job(make_raw(min_degree_level="BACHELORS"), "curated").content_hash
    assert plain == with_level


def test_ingestion_stores_degree_level(session: Session) -> None:
    ingest_source(session, FakeAdapter([make_raw(min_degree_level="MASTERS")]))
    job = session.query(Job).one()
    assert job.min_degree_level is DegreeLevel.MASTERS
    assert JobRead.model_validate(job).min_degree_level is DegreeLevel.MASTERS


def test_changing_only_degree_level_is_an_update(session: Session) -> None:
    ingest_source(session, FakeAdapter([make_raw(min_degree_level="BACHELORS")]))
    outcome = ingest_source(session, FakeAdapter([make_raw(min_degree_level="MASTERS")]))
    assert (outcome.jobs_updated, outcome.jobs_unchanged, outcome.jobs_created) == (1, 0, 0)
    assert session.query(Job).one().min_degree_level is DegreeLevel.MASTERS


def test_removing_a_degree_requirement_is_an_update(session: Session) -> None:
    ingest_source(session, FakeAdapter([make_raw(min_degree_level="BACHELORS")]))
    outcome = ingest_source(session, FakeAdapter([make_raw()]))
    assert outcome.jobs_updated == 1
    assert session.query(Job).one().min_degree_level is None


def test_database_rejects_an_invalid_degree_level(session: Session) -> None:
    ingest_source(session, FakeAdapter([make_raw()]))
    with pytest.raises(IntegrityError):
        session.execute(text("UPDATE jobs SET min_degree_level = 'NOT_A_LEVEL'"))
        session.flush()


def test_jobs_api_exposes_degree_level() -> None:
    assert "min_degree_level" in JobRead.model_fields


def test_curated_dataset_exercises_a_degree_requirement() -> None:
    entries = json.loads((ROOT / "app" / "data" / "curated_jobs.json").read_text("utf-8"))
    levels = [entry.get("min_degree_level") for entry in entries]
    assert any(level is not None for level in levels)
    for level in levels:
        assert level is None or DegreeLevel(level)


def test_degree_migration_is_additive_and_follows_the_merged_chain() -> None:
    migration = (VERSIONS / "b3e8d2c61a47_add_min_degree_level_to_jobs.py").read_text("utf-8")
    assert 'down_revision: Union[str, None] = "7c2f1a9b4d30"' in migration
    assert "add_column" in migration
    assert "create_check_constraint" in migration
    for destructive in ("drop_table", "create_table", "alter_column"):
        assert destructive not in migration
    # Exactly one migration descends from the merged head: the chain stays linear.
    children = [
        path.name for path in VERSIONS.glob("*.py")
        if 'down_revision: Union[str, None] = "7c2f1a9b4d30"' in path.read_text("utf-8")
    ]
    assert children == ["b3e8d2c61a47_add_min_degree_level_to_jobs.py"]
