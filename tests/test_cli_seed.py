"""Local seed command (PR 6B — ADR-024 §1).

``python -m app.cli seed-catalogue`` is setup tooling, not a product surface. These tests hold it
to that: it reuses the existing adapter and ingestion service, refuses a database that is not at
the migration head, never migrates or creates tables, writes only the two operational tables,
accepts no candidate input, prints counts only, and adds no HTTP route.

The migration-dependent cases run real Alembic against a temporary SQLite file, because the guard
is only meaningful against a real revision table.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import pathlib
import subprocess
import sys
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app import cli
from app.adapters.curated_adapter import CuratedJobAdapter
from app.database import Base
from app.models.ingestion_state import IngestionState, IngestionStatus
from app.models.job import Job, JobStatus
from tests.conftest import ALLOWED_OPERATIONAL_TABLES, FORBIDDEN_TABLES

ROOT = pathlib.Path(__file__).resolve().parent.parent
CLI_PATH = ROOT / "app" / "cli.py"
DATASET = ROOT / "app" / "data" / "curated_jobs.json"
CURATED_COUNT = len(json.loads(DATASET.read_text(encoding="utf-8")))
HEAD_REVISION = "b3e8d2c61a47"
PREVIOUS_REVISION = "7c2f1a9b4d30"


def alembic(database_url: str, revision: str) -> None:
    """Run real Alembic against a temporary database."""
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", revision],
        cwd=ROOT,
        env={**os.environ, "ELIGICORE_DATABASE_URL": database_url},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.fixture
def migrated(tmp_path: pathlib.Path) -> Iterator[tuple[str, Any]]:
    """A temporary database at the migration head, plus an engine bound to it."""
    path = tmp_path / "seed.db"
    url = f"sqlite:///{path.as_posix()}"
    alembic(url, "head")
    engine = create_engine(url, future=True, connect_args={"check_same_thread": False})
    try:
        yield url, engine
    finally:
        engine.dispose()


def rows(engine: Any) -> list[Job]:
    with Session(bind=engine) as session:
        return list(session.execute(select(Job)).scalars().all())


# ---------------------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------------------


def test_seed_creates_every_curated_job(migrated: tuple[str, Any], capsys: pytest.CaptureFixture[str]) -> None:
    _, engine = migrated
    assert cli.main(["seed-catalogue"], engine=engine) == 0
    jobs = rows(engine)
    assert len(jobs) == CURATED_COUNT == 40
    assert {job.status for job in jobs} == {JobStatus.ACTIVE}
    assert "created=40" in capsys.readouterr().out


def test_second_run_is_idempotent(migrated: tuple[str, Any], capsys: pytest.CaptureFixture[str]) -> None:
    _, engine = migrated
    cli.main(["seed-catalogue"], engine=engine)
    before = {(job.id, job.content_hash, job.source_job_id) for job in rows(engine)}
    capsys.readouterr()

    assert cli.main(["seed-catalogue"], engine=engine) == 0

    assert {(job.id, job.content_hash, job.source_job_id) for job in rows(engine)} == before
    assert len(rows(engine)) == CURATED_COUNT
    out = capsys.readouterr().out
    assert f"created=0 updated=0 unchanged={CURATED_COUNT}" in out


def test_seed_writes_only_the_operational_tables(migrated: tuple[str, Any]) -> None:
    url, engine = migrated
    cli.main(["seed-catalogue"], engine=engine)
    with engine.connect() as connection:
        names = {
            row[0]
            for row in connection.exec_driver_sql(
                "select name from sqlite_master where type='table'"
            )
        }
    assert names == ALLOWED_OPERATIONAL_TABLES | {"alembic_version"}
    assert not names & FORBIDDEN_TABLES
    assert set(Base.metadata.tables) == ALLOWED_OPERATIONAL_TABLES


def test_seed_records_ingestion_state(migrated: tuple[str, Any]) -> None:
    _, engine = migrated
    cli.main(["seed-catalogue"], engine=engine)
    with Session(bind=engine) as session:
        states = list(session.execute(select(IngestionState)).scalars().all())
    assert len(states) == 1
    assert states[0].source == "curated"
    assert states[0].last_status is IngestionStatus.SUCCESS


def test_seed_uses_the_existing_adapter_and_ingestion_service(
    migrated: tuple[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second ingestion implementation would not call these."""
    seen: dict[str, Any] = {}
    real = cli.ingest_all

    def spy(session: Any, adapters: list[Any]) -> Any:
        seen["adapters"] = [type(a).__name__ for a in adapters]
        return real(session, adapters)

    monkeypatch.setattr(cli, "ingest_all", spy)
    _, engine = migrated
    cli.main(["seed-catalogue"], engine=engine)
    assert seen["adapters"] == ["CuratedJobAdapter"]


def test_removed_source_entry_is_closed_not_deleted(
    migrated: tuple[str, Any], tmp_path: pathlib.Path
) -> None:
    """Existing authoritative behaviour, unchanged: closure, never deletion."""
    _, engine = migrated
    cli.main(["seed-catalogue"], engine=engine)

    reduced = tmp_path / "reduced.json"
    entries = json.loads(DATASET.read_text(encoding="utf-8"))
    reduced.write_text(json.dumps(entries[:-1]), encoding="utf-8")

    with Session(bind=engine) as session:
        cli.ingest_all(session, [CuratedJobAdapter(reduced)])
    jobs = {job.source_job_id: job.status for job in rows(engine)}
    assert len(jobs) == CURATED_COUNT, "nothing deleted"
    assert jobs[entries[-1]["source_job_id"]] is JobStatus.CLOSED


# ---------------------------------------------------------------------------------------
# Schema guard
# ---------------------------------------------------------------------------------------


def test_refuses_a_database_behind_head(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "old.db"
    url = f"sqlite:///{path.as_posix()}"
    alembic(url, PREVIOUS_REVISION)
    engine = create_engine(url, future=True)
    try:
        assert cli.main(["seed-catalogue"], engine=engine) == 2
        with engine.connect() as connection:
            assert connection.exec_driver_sql("select count(*) from jobs").scalar() == 0
    finally:
        engine.dispose()
    err = capsys.readouterr().err
    assert "alembic upgrade head" in err
    assert str(path) not in err and "sqlite" not in err  # no path or URL in the message


def test_refuses_a_database_with_no_migrations(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "empty.db"
    path.write_bytes(b"")
    engine = create_engine(f"sqlite:///{path.as_posix()}", future=True)
    try:
        assert cli.main(["seed-catalogue"], engine=engine) == 2
    finally:
        engine.dispose()


def test_refuses_a_missing_database_without_creating_one(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "absent.db"
    monkeypatch.setenv("ELIGICORE_DATABASE_URL", f"sqlite:///{path.as_posix()}")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        assert cli.main(["seed-catalogue"]) == 2
    finally:
        get_settings.cache_clear()
    assert not path.exists(), "a missing SQLite file must not be created"
    assert "alembic upgrade head" in capsys.readouterr().err


def test_head_check_reads_without_writing(migrated: tuple[str, Any]) -> None:
    url, engine = migrated
    before = pathlib.Path(url.removeprefix("sqlite:///")).read_bytes()
    assert cli.expected_heads() == {HEAD_REVISION}
    assert cli.current_heads(engine) == {HEAD_REVISION}
    assert pathlib.Path(url.removeprefix("sqlite:///")).read_bytes() == before


# ---------------------------------------------------------------------------------------
# Interface: no candidate data, counts only, no HTTP
# ---------------------------------------------------------------------------------------


def test_only_one_subcommand_and_no_options() -> None:
    parser = cli.build_parser()
    (subparsers,) = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    assert set(subparsers.choices) == {"seed-catalogue"}
    seed = subparsers.choices["seed-catalogue"]
    optional = {o for a in seed._actions for o in a.option_strings}
    assert optional == {"-h", "--help"}, "no dataset path, no reset flag, no candidate input"


@pytest.mark.parametrize(
    "argv",
    [
        ["seed-catalogue", "--reset"],
        ["seed-catalogue", "--dataset", "anywhere.json"],
        ["seed-catalogue", "--profile", "candidate.json"],
        ["seed-catalogue", "--resume", "resume.pdf"],
        ["seed-catalogue", "extra"],
        ["seed-candidates"],
        [],
    ],
)
def test_rejected_arguments(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(argv)
    assert exit_info.value.code == 2


def test_output_is_counts_only(migrated: tuple[str, Any], capsys: pytest.CaptureFixture[str]) -> None:
    _, engine = migrated
    cli.main(["seed-catalogue"], engine=engine)
    out = capsys.readouterr().out.strip()
    assert out == (
        "seed-catalogue source=curated seen=40 created=40 updated=0 unchanged=0 "
        "closed=0 duplicates=0"
    )
    entries = json.loads(DATASET.read_text(encoding="utf-8"))
    for entry in entries:
        for field in ("company_name", "role_title", "apply_link", "source_job_id"):
            assert entry[field] not in out


def test_command_line_entry_point_works(tmp_path: pathlib.Path) -> None:
    """The documented command, run as a real process."""
    path = tmp_path / "subprocess.db"
    url = f"sqlite:///{path.as_posix()}"
    alembic(url, "head")
    env = {**os.environ, "ELIGICORE_DATABASE_URL": url}
    first = subprocess.run(
        [sys.executable, "-m", "app.cli", "seed-catalogue"],
        cwd=ROOT, env=env, capture_output=True, text=True,
    )
    second = subprocess.run(
        [sys.executable, "-m", "app.cli", "seed-catalogue"],
        cwd=ROOT, env=env, capture_output=True, text=True,
    )
    assert first.returncode == 0 and f"created={CURATED_COUNT}" in first.stdout
    assert second.returncode == 0 and f"unchanged={CURATED_COUNT}" in second.stdout


# ---------------------------------------------------------------------------------------
# Architecture
# ---------------------------------------------------------------------------------------


def imported_modules(path: pathlib.Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_cli_imports_no_web_framework_or_ai() -> None:
    for module in imported_modules(CLI_PATH):
        assert not module.startswith(("fastapi", "starlette", "httpx", "app.ai", "app.routers",
                                      "app.main", "app.schemas.candidate", "app.schemas.resume",
                                      "app.services.eligibility", "app.services.matching_engine",
                                      "app.services.recommendations", "app.services.tracker_export",
                                      "app.services.resume_parser")), module


def test_cli_reuses_ingestion_and_never_creates_schema() -> None:
    source = CLI_PATH.read_text(encoding="utf-8")
    modules = imported_modules(CLI_PATH)
    assert "app.services.job_ingestion" in modules
    assert "app.adapters.curated_adapter" in modules
    for forbidden in ("create_all", "drop_all", "command.upgrade", "alembic.command",
                      "DELETE FROM", "drop_table", "Base.metadata.create"):
        assert forbidden not in source, forbidden
    # No re-implementation of ingestion inside the CLI.
    for reimplementation in ("compute_content_hash", "find_existing_job", "Job(", "session.add"):
        assert reimplementation not in source, reimplementation


def test_cli_adds_no_http_route() -> None:
    source = CLI_PATH.read_text(encoding="utf-8")
    for forbidden in ("APIRouter", "@router", "@app.", "include_router", "FastAPI"):
        assert forbidden not in source, forbidden
    from app.main import app

    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]
    assert "/api/v1/jobs/ingest" not in paths
    assert not any("seed" in path for path in paths)


def test_nothing_in_the_application_imports_the_cli() -> None:
    for path in ROOT.joinpath("app").rglob("*.py"):
        if path == CLI_PATH:
            continue
        assert "app.cli" not in imported_modules(path), path
