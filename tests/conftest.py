"""Shared test fixtures.

**Every fixture here is obviously synthetic.** No real names, emails, phone numbers or
institutions appear anywhere in this repository's tests
(``standards/testing.md`` §5, QG-005 item 19).

Profiles are built as dictionaries and passed in request bodies, exactly as a client would
send them. Nothing is ever seeded into a database — there is no table to seed (ADR-002,
ADR-011).
"""

from __future__ import annotations

import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------------------
# Test database isolation — must run before anything imports ``app``
# ---------------------------------------------------------------------------------------
#
# ``Settings.database_url`` defaults to ``sqlite:///./eligicore.db``, relative to wherever
# pytest is started, and ``app.database`` builds its engine from it at import time. Run from
# a checkout that holds a developer database, that path *is* the developer database. The
# suite is therefore pointed at a database it owns before ``app`` is first imported.
#
# A file, not ``sqlite://``: an in-memory SQLite database belongs to one connection, and
# the TestClient serves requests from another thread, so a privacy check would inspect a
# different, always-empty database from the one the request used.
#
# Forced rather than defaulted, so neither a shell variable nor a ``.env`` file can point
# the suite back at a real database: pydantic-settings ranks the environment above the
# dotenv file. Child processes inherit it, and tests that need their own database still
# pass one explicitly.
#
# This module is imported twice in one run — once by pytest as a conftest, once as
# ``tests.conftest`` by tests importing its constants — so the directory is created once
# and handed to the second import through the environment.

REPO_ROOT = Path(__file__).resolve().parent.parent

_TEST_DATABASE_DIR_VARIABLE = "_ELIGICORE_TEST_DATABASE_DIR"
_first_import = _TEST_DATABASE_DIR_VARIABLE not in os.environ
if _first_import:
    os.environ[_TEST_DATABASE_DIR_VARIABLE] = tempfile.mkdtemp(prefix="eligicore-test-db-")
_TEST_DATABASE_DIR = Path(os.environ[_TEST_DATABASE_DIR_VARIABLE])


def _remove_test_database() -> None:
    # Registered before the guard below, so a refused run does not leak the directory.
    database = sys.modules.get("app.database")
    if database is not None:
        database.engine.dispose()
    shutil.rmtree(_TEST_DATABASE_DIR, ignore_errors=True)


if _first_import:
    atexit.register(_remove_test_database)

TEST_DATABASE_PATH = (_TEST_DATABASE_DIR / "eligicore-test.db").resolve()
TEST_DATABASE_URL = f"sqlite:///{TEST_DATABASE_PATH.as_posix()}"
os.environ["ELIGICORE_DATABASE_URL"] = TEST_DATABASE_URL

#: The database files a developer may have beside the repository, plus SQLite's sidecars.
#: The suite must never create or change any of them.
_DEVELOPER_DATABASE_FILES = tuple(
    root / f"eligicore.db{suffix}"
    for root in {REPO_ROOT, Path.cwd().resolve()}
    for suffix in ("", "-journal", "-wal", "-shm")
)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import inspect  # noqa: E402

from app.database import engine as _application_engine  # noqa: E402
from app.database import get_db  # noqa: E402
from app.main import app  # noqa: E402

_resolved = Path(_application_engine.url.database or "").resolve()
if _resolved != TEST_DATABASE_PATH:
    raise RuntimeError(
        "Refusing to run: the application engine resolves to "
        f"{_resolved}, not the test-owned database {TEST_DATABASE_PATH}. "
        "app.database was imported before tests/conftest.py could isolate it."
    )


def _stat_developer_database_files() -> dict[Path, tuple[int, int] | None]:
    """Size and mtime of each file, or ``None`` if absent. Never opens a database."""
    snapshot: dict[Path, tuple[int, int] | None] = {}
    for path in _DEVELOPER_DATABASE_FILES:
        try:
            stat = path.stat()
        except FileNotFoundError:
            snapshot[path] = None
        else:
            snapshot[path] = (stat.st_size, stat.st_mtime_ns)
    return snapshot


_developer_files_at_start = _stat_developer_database_files()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Fail the run if any developer database file was created or changed.

    The guard that does not depend on settings: it also catches a test that builds its own
    engine on the default path.
    """
    now = _stat_developer_database_files()
    changed = [
        str(path) for path, before in _developer_files_at_start.items() if now[path] != before
    ]
    if changed:
        session.config.get_terminal_writer().line(
            "\nERROR: the test suite created or modified a developer database file: "
            + ", ".join(changed),
            red=True,
        )
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def application_database_tables() -> set[str]:
    """Table names in the database the application hands a request.

    Resolved through ``get_db`` — the override when a test installs one — so a privacy
    check inspects the database the request under test actually used.
    """
    sessions = app.dependency_overrides.get(get_db, get_db)()
    db = next(sessions)
    try:
        return set(inspect(db.get_bind()).get_table_names())
    finally:
        sessions.close()


#: Tables the server is permitted to have. An **allowlist**, deliberately: naming only the
#: forbidden tables would let a fourth personal-data table through under a name nobody
#: thought to ban. Anything registered outside this set fails the privacy tests, which is
#: the behaviour we want when someone adds a model without thinking about INV-1.
#:
#: Weeks 1–2 asserted this set was empty, which was true then but was never the invariant.
#: Week 3 adds the first operational tables; the rule — operational data only, no personal
#: data — is unchanged.
#:
#: ``extracted_requirements`` joins it for ADR-030 D16: verified requirements read out of a
#: job's own description. It is job-derived operational data in the same sense as ``jobs``
#: — no candidate identifier, no profile, no evaluation — and it is listed here rather than
#: exempted anywhere, so the privacy tests cover it like everything else.
ALLOWED_OPERATIONAL_TABLES = {"jobs", "ingestion_state", "extracted_requirements"}

#: Names that must never appear, checked in addition to the allowlist so the intent stays
#: legible at each call site.
FORBIDDEN_TABLES = {
    "candidates",
    "candidate",
    "applications",
    "application",
    "evaluations",
    "evaluation",
    "profiles",
    "resumes",
}


@pytest.fixture
def anyio_backend() -> str:
    """Run async tests on asyncio only.

    anyio would otherwise parameterize every async test across asyncio and trio, doubling
    the suite to exercise a backend this project does not use.
    """
    return "asyncio"


@pytest.fixture
def client() -> TestClient:
    """A test client for the FastAPI application."""
    return TestClient(app)


@pytest.fixture
def minimal_profile() -> dict[str, Any]:
    """The smallest profile that carries an education record."""
    return {
        "education": [
            {
                "degree": "B.Tech",
                "level": "BACHELORS",
                "field_of_study": "Information Technology",
                "institution": "Example Institute of Technology",
                "grad_year": 2027,
                "cgpa": 8.2,
                "scale": "SCALE_10",
            }
        ]
    }


@pytest.fixture
def complete_profile() -> dict[str, Any]:
    """A fully populated, entirely fictional candidate profile."""
    return {
        "candidate_id": "client-generated-test-id-0001",
        "name": "Test Candidate",
        "email": "test.candidate@example.com",
        "phone": "+10000000000",
        "location": "Example City",
        "education": [
            {
                "degree": "B.Tech",
                "level": "BACHELORS",
                "field_of_study": "Information Technology",
                "institution": "Example Institute of Technology",
                "grad_year": 2027,
                "cgpa": 8.2,
                "scale": "SCALE_10",
            },
            {
                "degree": "High School",
                "level": "HIGH_SCHOOL",
                "institution": "Example Public School",
                "grad_year": 2023,
                "cgpa": 92.0,
                "scale": "PERCENTAGE",
            },
        ],
        "experience": [
            {
                "title": "Software Engineering Intern",
                "company": "Example Corp",
                "duration": "Jun 2026 - Aug 2026",
                "description": "Built internal tooling.",
            }
        ],
        "skills": ["Python", "ReactJS", "React.js", "  SQL  ", "docker"],
        "projects": [{"name": "Example Project", "description": "A sample project."}],
        "certifications": [{"name": "Example Certification", "issuer": "Example Body"}],
        "languages": ["English", "english"],
        "backlogs": 0,
        "preferences": {
            "locations": ["Example City", "Remote"],
            "job_types": ["INTERNSHIP"],
            "work_mode": "HYBRID",
        },
        "field_confidence": {"name": "HIGH", "email": "MEDIUM"},
    }
