"""Operational database foundation: engine, session factory, declarative base.

╔══════════════════════════════════════════════════════════════════════════════════════╗
║  THIS DATABASE HOLDS OPERATIONAL DATA ONLY.                                          ║
║                                                                                      ║
║  Permitted, when their phases arrive:                                                ║
║      jobs               — the job catalogue                    (Week 3)              ║
║      ingestion_state    — adapter run history                  (Week 3, ADR-012)     ║
║      operational logs   — request counts, AI usage, errors                           ║
║                                                                                      ║
║  FORBIDDEN — do not create these, ever, and do not write migrations for them:        ║
║      candidates · applications · evaluations                                         ║
║      or any table holding profiles, resumes, results or application records.         ║
║                                                                                      ║
║  The dossier §8.2 folder listing shows ``models/candidate.py`` and                   ║
║  ``models/application.py``. That listing is STALE. §10.2 governs, and ADR-011        ║
║  rules on it explicitly. Candidate data is in-flight only (INV-1).                   ║
╚══════════════════════════════════════════════════════════════════════════════════════╝

See ``artifacts/decisions/ADR-011-no-server-side-candidate-or-application-persistence.md``
and ``artifacts/decisions/ADR-009-database-strategy.md``.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import Settings, get_settings


class Base(DeclarativeBase):
    """Declarative base for operational models.

    No model inherits from this yet — Week 1 introduces no tables. The first will be the
    job catalogue in Week 3.

    Read the module docstring before adding one.
    """


def _engine_kwargs(database_url: str) -> dict[str, Any]:
    """Return engine keyword arguments appropriate to the database backend.

    SQLite needs ``check_same_thread=False`` because FastAPI may use a session from a
    different thread than the one that created it. PostgreSQL needs no such flag, and
    passing it would raise (ADR-009 — the two engines are not silently interchangeable).
    """
    if database_url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {}


def create_db_engine(settings: Settings | None = None) -> Engine:
    """Create a SQLAlchemy engine from settings."""
    settings = settings or get_settings()
    return create_engine(
        settings.database_url,
        future=True,
        **_engine_kwargs(settings.database_url),
    )


engine: Engine = create_db_engine()

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding an operational database session.

    Not used by any Week 1 endpoint — the candidate endpoints are stateless and touch no
    database at all (ADR-002). It exists so the job endpoints in Week 3 have a session
    source, and so the foundation is verifiably complete.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
