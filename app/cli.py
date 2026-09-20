"""Local setup commands (ADR-024 §1).

``python -m app.cli seed-catalogue`` loads the curated job catalogue into the operational
database configured by ``ELIGICORE_DATABASE_URL``, so a fresh clone can run the demo.

**Local tooling, not a product surface.** There is deliberately no HTTP ingestion endpoint: an
unauthenticated route that writes the catalogue would be an abuse surface on a public deployment
(C-25, ADR-023 §11). Dossier §7 step 4 has ingestion running independently of the API, and this is
that trigger.

**It adds no logic.** Seeding is :func:`app.services.job_ingestion.ingest_all` over the existing
:class:`~app.adapters.curated_adapter.CuratedJobAdapter`, so normalization, content hashing,
deduplication, upserts, ``ingestion_state`` and authoritative closure behave exactly as they do
everywhere else. Re-running it changes nothing.

**It is not a migration tool.** The schema must already be at the Alembic head; the command
checks, and refuses rather than migrating, creating tables or repairing anything.

**It handles only public job data.** No candidate profile, résumé or identifier can reach it: it
takes no input beyond the subcommand name, and it prints counts only.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.adapters.curated_adapter import CuratedJobAdapter
from app.config import Settings, get_settings
from app.database import create_db_engine
from app.services.job_ingestion import ingest_all

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sqlalchemy.engine import Engine

    from app.schemas.job import IngestionOutcome

#: Repository root — the Alembic configuration lives beside this package.
ROOT = Path(__file__).resolve().parent.parent
ALEMBIC_INI = ROOT / "alembic.ini"

#: What to tell the developer when the schema is behind. Deliberately free of the database URL:
#: a URL can carry credentials, and this text reaches terminals and CI logs.
NOT_AT_HEAD = (
    "seed-catalogue: the database schema is not at the latest migration.\n"
    "Run `alembic upgrade head` first, then seed again."
)
NO_DATABASE = (
    "seed-catalogue: no database found at the configured location.\n"
    "Run `alembic upgrade head` first, then seed again."
)
SEED_FAILED = "seed-catalogue: the curated source could not be read; nothing was written."


class SchemaNotCurrentError(RuntimeError):
    """The database is missing, or behind the latest migration."""


def expected_heads() -> set[str]:
    """Revision ids the migration scripts define as head."""
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    return set(ScriptDirectory.from_config(config).get_heads())


def current_heads(engine: Engine) -> set[str]:
    """Revision ids the database records. Read-only: nothing is created or stamped."""
    with engine.connect() as connection:
        return set(MigrationContext.configure(connection).get_current_heads())


def ensure_database_exists(settings: Settings) -> None:
    """Fail before connecting when a SQLite file is absent.

    Connecting to a missing SQLite file creates an empty one. A setup command that silently
    produced an empty, schema-less database would be worse than one that refuses.
    """
    url = make_url(settings.database_url)
    if url.get_backend_name() != "sqlite":
        return
    if url.database in (None, "", ":memory:"):
        return
    if not Path(url.database).exists():
        raise SchemaNotCurrentError(NO_DATABASE)


def ensure_schema_is_current(engine: Engine) -> None:
    """Raise unless the database is at the migration head. Never migrates (ADR-024 §1)."""
    if current_heads(engine) != expected_heads():
        raise SchemaNotCurrentError(NOT_AT_HEAD)


def seed_catalogue(session: Session) -> list[IngestionOutcome]:
    """Ingest the curated catalogue through the existing adapter and ingestion service.

    The full-flow test calls this too, so the demo path and the test path cannot drift.
    """
    return ingest_all(session, [CuratedJobAdapter()])


def _run_seed(engine: Engine | None = None) -> int:
    settings = get_settings()
    owns_engine = engine is None
    if owns_engine:
        ensure_database_exists(settings)
        engine = create_db_engine(settings)
    try:
        ensure_schema_is_current(engine)
        with Session(bind=engine, autoflush=False, expire_on_commit=False) as session:
            outcomes = seed_catalogue(session)
    finally:
        if owns_engine:
            engine.dispose()

    if not outcomes:
        print(SEED_FAILED, file=sys.stderr)
        return 1

    for outcome in outcomes:
        # Counts only: no job id, company, role, link or description (INV-4).
        print(
            f"seed-catalogue source={outcome.source} seen={outcome.jobs_seen} "
            f"created={outcome.jobs_created} updated={outcome.jobs_updated} "
            f"unchanged={outcome.jobs_unchanged} closed={outcome.jobs_deactivated} "
            f"duplicates={outcome.duplicates_collapsed}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    """The command-line interface. No dataset path, no reset flag, no candidate input."""
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="Local setup commands for EligiCore. Handles public job data only.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser(
        "seed-catalogue",
        help="Load the curated job catalogue into the configured database.",
        description=(
            "Ingests the curated catalogue through the normal adapter and ingestion path. "
            "Idempotent, never deletes, and requires the schema to be at the Alembic head."
        ),
    )
    return parser


def main(argv: list[str] | None = None, *, engine: Engine | None = None) -> int:
    """Entry point. Returns a process exit code; never raises for expected failures."""
    args = build_parser().parse_args(argv)
    if args.command == "seed-catalogue":
        try:
            return _run_seed(engine)
        except SchemaNotCurrentError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    raise AssertionError(f"unhandled command: {args.command}")  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover - exercised through a subprocess test
    raise SystemExit(main())
