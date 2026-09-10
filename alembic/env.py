"""Alembic migration environment for EligiCore's OPERATIONAL database.

The database URL comes from application settings (``ELIGICORE_DATABASE_URL``) rather than
from ``alembic.ini``, so migrations and the application can never disagree about which
database they are pointed at, and so no connection string is ever committed.

╔══════════════════════════════════════════════════════════════════════════════════════╗
║  MIGRATIONS MAY ONLY CREATE OPERATIONAL TABLES.                                      ║
║                                                                                      ║
║  Never write a migration creating `candidates`, `applications`, `evaluations`, or    ║
║  any table holding candidate profiles, resumes, results or application records.      ║
║  Candidate data is in-flight only (ADR-011, INV-1, QG-006 items 1-3).                ║
╚══════════════════════════════════════════════════════════════════════════════════════╝

There are no migrations yet — Week 1 introduces no tables. The first will be the job
catalogue in Week 3.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import get_settings
from app.database import Base

# Alembic Config object, providing access to alembic.ini values.
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override the placeholder URL in alembic.ini with the real, environment-driven one.
config.set_main_option("sqlalchemy.url", get_settings().database_url)

# Autogenerate compares against this. Currently empty by design — see the module docstring.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without a DBAPI connection, emitting SQL to the script output."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Required for SQLite, which cannot ALTER most columns in place. Harmless on
        # PostgreSQL, and keeps migrations portable across both (ADR-009).
        render_as_batch=True,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
