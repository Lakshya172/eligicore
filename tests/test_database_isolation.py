"""The suite runs against a database it owns, never a developer's.

``Settings.database_url`` defaults to ``sqlite:///./eligicore.db``, relative to the working
directory, and ``tests/conftest.py`` redirects it before ``app`` is imported. These tests pin
that redirection, so losing it fails here by name rather than by a privacy check quietly
inspecting a developer database. ``conftest.py`` additionally refuses to start, and fails
the session if a developer database file is created or changed.
"""

from __future__ import annotations

from pathlib import Path

from app.config import Settings, get_settings
from app.database import engine
from tests.conftest import REPO_ROOT, TEST_DATABASE_PATH, TEST_DATABASE_URL

DEVELOPER_DATABASE = REPO_ROOT / "eligicore.db"


def test_the_application_engine_uses_the_test_owned_database() -> None:
    resolved = Path(engine.url.database or "").resolve()
    assert resolved == TEST_DATABASE_PATH
    assert resolved != DEVELOPER_DATABASE.resolve()
    assert resolved != (Path.cwd() / "eligicore.db").resolve()


def test_settings_resolve_to_the_test_owned_database() -> None:
    get_settings.cache_clear()
    try:
        assert get_settings().database_url == TEST_DATABASE_URL
    finally:
        get_settings.cache_clear()


def test_a_dotenv_file_cannot_point_the_suite_at_a_developer_database(
    tmp_path: Path,
) -> None:
    """A developer's ``.env`` beside the repository must not win over the isolation."""
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        f"ELIGICORE_DATABASE_URL=sqlite:///{DEVELOPER_DATABASE.as_posix()}\n",
        encoding="utf-8",
    )
    assert Settings(_env_file=dotenv).database_url == TEST_DATABASE_URL


def test_the_production_default_is_unchanged() -> None:
    """Isolation lives in the test suite; the application's own default is untouched."""
    assert Settings.model_fields["database_url"].default == "sqlite:///./eligicore.db"
