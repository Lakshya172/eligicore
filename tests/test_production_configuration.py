"""Week 9A-3 — production configuration behaviour, pinned.

QG-007 items 7-9 require that a public deployment runs with debug off and without verbose
tracebacks. Until this file existed, **no test set ``ELIGICORE_ENVIRONMENT=production`` at
all**, so the whole of production mode was unverified: the gate could only ever have been
satisfied by assertion in prose.

Nothing here changes production semantics. Every test observes behaviour that already exists
on ``main``; the point is to make it reproducible and to make a regression fail loudly.

**The finding these tests encode.** Traceback suppression is *unconditional* — it comes from
the merged ``@app.exception_handler(Exception)`` and from the application never being
constructed with ``debug=True``, not from the environment setting. Production therefore
satisfies the requirement, but is not what causes it. That is a stronger guarantee than
"production suppresses tracebacks", because it cannot be lost by misconfiguring the
environment, and :func:`test_suppression_cannot_be_switched_off_by_configuration` and
:func:`test_the_handler_reads_no_configuration` pin it in that stronger form deliberately.

The controlled 500 is produced the way ``tests/test_operational_logs.py`` already produces one:
by overriding a real endpoint's dependency so it raises. No test-only route is added and no
application source is touched.
"""

from __future__ import annotations

import ast
import inspect
import json
import subprocess
import sys
import textwrap
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Environment, Settings, get_settings
from app.database import get_db
from app.main import app, unhandled_exception_handler

#: Tokens that must never appear in a 5xx response. Each is something a framework in debug
#: mode, or a handler that echoed the exception, would readily emit.
INTERNAL_MARKERS = {
    "traceback banner": "Traceback (most recent call last)",
    "exception message": "internal failure at",
    "source path fragment": "/secret/path/",
    "python filename": ".py",
    "stack frame marker": 'File "',
    "line number marker": "line 42",
    "exception type name": "RuntimeError",
    "site-packages path": "site-packages",
    "candidate name": "Priya Sharma",
    "candidate email": "priya@example.com",
    "candidate institution": "Example Institute",
}

#: Raised by the broken dependency. It deliberately embeds a path, a line number and candidate
#: data, so a response that leaks *anything* about the exception trips the scan above.
BOOM = "internal failure at /secret/path/app/services/thing.py line 42 for Priya Sharma"

PROFILE = {
    "candidate_id": "prod-config-probe",
    "full_name": "Priya Sharma",
    "email": "priya@example.com",
    "education": [
        {
            "degree": "B.Tech",
            "level": "BACHELORS",
            "field_of_study": "Computer Science",
            "institution": "Example Institute",
            "grad_year": 2026,
            "cgpa": 8.1,
            "grade_scale": "SCALE_10",
        }
    ],
    "skills": ["Python"],
}


@pytest.fixture(autouse=True)
def _restore_settings_cache() -> Iterator[None]:
    """Leave the process-wide settings cache exactly as this module found it.

    ``get_settings`` is ``lru_cache``d and global. These tests deliberately rebuild it under
    other environments, so the cache is cleared on the way out as well as the way in - a
    module that reaches into shared state owes the rest of the suite that.
    """
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()


def settings_for(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    """Build a fresh ``Settings`` under the given environment variables.

    Same approach as ``tests/test_cli_seed.py``: set the variables, clear the settings cache,
    read, and clear again so no later test inherits the override.
    """
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    try:
        return get_settings()
    finally:
        get_settings.cache_clear()


def in_child(body: str, **env: str) -> str:
    """Run ``body`` in a fresh interpreter under ``env`` and return its stdout.

    A subprocess is not decoration here: ``app.main`` builds the application object and reads
    its settings **at import time**, so production mode can only be observed honestly in a
    process that was started under it.
    """
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(body)],
        capture_output=True,
        text=True,
        env={**_base_env(), **env},
        cwd=_repo_root(),
    )
    assert result.returncode == 0, f"child failed:\n{result.stdout}\n{result.stderr}"
    return result.stdout


def _repo_root() -> str:
    import pathlib

    return str(pathlib.Path(__file__).resolve().parent.parent)


def _base_env() -> dict[str, str]:
    import os

    keep = {"PATH", "SYSTEMROOT", "TEMP", "TMP", "COMSPEC", "PATHEXT", "WINDIR", "HOME", "LANG"}
    env = {k: v for k, v in os.environ.items() if k in keep or not k.startswith("ELIGICORE_")}
    env["PYTHONPATH"] = _repo_root()
    return env


# ---------------------------------------------------------------------------------------
# Settings under production
# ---------------------------------------------------------------------------------------


def test_production_environment_disables_debug(monkeypatch: pytest.MonkeyPatch) -> None:
    """QG-007 #9, the configuration half: production runs with debug off."""
    settings = settings_for(monkeypatch, ELIGICORE_ENVIRONMENT="production")
    assert settings.environment is Environment.PRODUCTION
    assert settings.environment.value == "production"
    assert settings.is_production is True
    assert settings.debug is False


def test_production_changes_nothing_but_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Selecting production must not quietly switch any other setting.

    The inverse failure matters just as much as the obvious one: a production flag that also
    flipped, say, ``log_level`` or ``ai_provider`` would be a surprise waiting in a deployment.
    """
    development = settings_for(monkeypatch, ELIGICORE_ENVIRONMENT="development")
    production = settings_for(monkeypatch, ELIGICORE_ENVIRONMENT="production")

    differing = {
        name
        for name in Settings.model_fields
        if getattr(development, name) != getattr(production, name)
    }
    assert differing == {"environment"}, differing

    # Derived properties count too, and are the easier place to hide a surprise: a new
    # `@property` that branches on the environment is invisible to `model_fields`. Only
    # `is_production` may differ, because differing is the whole of its job.
    properties = {
        name
        for name, attribute in vars(type(development)).items()
        if isinstance(attribute, property)
    }
    assert "is_production" in properties, "is_production is no longer a property"
    differing_properties = {
        name
        for name in properties
        if getattr(development, name) != getattr(production, name)
    }
    assert differing_properties == {"is_production"}, differing_properties
    assert development.is_production is False and production.is_production is True

    # Spelled out, because these are the ones a deployment would actually be harmed by.
    for name in ("debug", "log_level", "ai_provider", "database_url", "ai_cost_rates"):
        assert getattr(development, name) == getattr(production, name), name


def test_the_application_never_runs_in_framework_debug_mode() -> None:
    """Starlette's own debug flag renders a full traceback page. It must stay off.

    Checked in a child process under production, because the application object is built at
    import time.
    """
    out = in_child(
        """
        from app.main import app
        from app.config import get_settings
        print(f"app.debug={app.debug} settings.debug={get_settings().debug}")
        """,
        ELIGICORE_ENVIRONMENT="production",
    )
    assert "app.debug=False" in out
    assert "settings.debug=False" in out


# ---------------------------------------------------------------------------------------
# Traceback suppression
# ---------------------------------------------------------------------------------------


def controlled_500(client: TestClient) -> Any:
    """Make a real endpoint raise, without adding a route or touching application source."""

    def exploding() -> Any:
        raise RuntimeError(BOOM)

    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = exploding
    try:
        return client.post(
            "/api/v1/eligibility/check", json={"profile": PROFILE, "job_ids": ["job-1"]}
        )
    finally:
        # Targeted restore, never `.clear()`: this module must not remove an override some
        # enclosing fixture installed on the shared `app` singleton.
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous


def assert_no_internals(status_code: int, body: str, headers: str) -> None:
    assert status_code == 500
    haystack = f"{body} {headers}"
    for label, marker in INTERNAL_MARKERS.items():
        assert marker not in haystack, f"{label} leaked into the 500 response"


def test_a_server_error_under_production_exposes_no_internals() -> None:
    """QG-007 #9, the response half — observed in a process started under production."""
    out = in_child(
        f"""
        import json
        from fastapi.testclient import TestClient
        from app.database import get_db
        from app.main import app

        def exploding():
            raise RuntimeError({BOOM!r})

        app.dependency_overrides[get_db] = exploding
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/v1/eligibility/check",
            json={{"profile": {PROFILE!r}, "job_ids": ["job-1"]}},
        )
        print("STATUS", response.status_code)
        print("BODY", response.text)
        print("HEADERS", json.dumps(dict(response.headers)))
        """,
        ELIGICORE_ENVIRONMENT="production",
    )
    status_line = next(line for line in out.splitlines() if line.startswith("STATUS"))
    body = next(line for line in out.splitlines() if line.startswith("BODY"))
    headers = next(line for line in out.splitlines() if line.startswith("HEADERS"))

    assert_no_internals(int(status_line.split()[1]), body, headers)
    payload = json.loads(body[len("BODY ") :])
    assert payload["error"] == "INTERNAL_ERROR"
    assert payload["message"] == "An internal error occurred."
    assert set(payload) == {"error", "message", "request_id", "details"}


def test_suppression_cannot_be_switched_off_by_configuration() -> None:
    """``ELIGICORE_DEBUG=true`` in production must not start exposing internals.

    This pins the guarantee in its strong form. Suppression does not depend on the
    environment, so no combination of the documented settings can turn it off — which is why
    a misconfigured deployment still cannot leak a traceback.
    """
    out = in_child(
        f"""
        from fastapi.testclient import TestClient
        from app.config import get_settings
        from app.database import get_db
        from app.main import app

        def exploding():
            raise RuntimeError({BOOM!r})

        app.dependency_overrides[get_db] = exploding
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/v1/eligibility/check",
            json={{"profile": {PROFILE!r}, "job_ids": ["job-1"]}},
        )
        print("SETTINGSDEBUG", get_settings().debug)
        print("APPDEBUG", app.debug)
        print("STATUS", response.status_code)
        print("BODY", response.text)
        """,
        ELIGICORE_ENVIRONMENT="production",
        ELIGICORE_DEBUG="true",
    )
    # The setting is accepted and does change `settings.debug` ...
    assert "SETTINGSDEBUG True" in out
    # ... but reaches neither the framework nor the response.
    assert "APPDEBUG False" in out
    body = next(line for line in out.splitlines() if line.startswith("BODY"))
    assert_no_internals(500, body, "")


def test_the_handler_reads_no_configuration() -> None:
    """The 500 handler must not become environment-dependent.

    Checked on the syntax tree rather than by string search, so a docstring mentioning
    "settings" cannot pass or fail it by accident.
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(unhandled_exception_handler)))
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    for forbidden in ("settings", "get_settings", "Environment"):
        assert forbidden not in names, f"the 500 handler now reads {forbidden}"
    for forbidden in ("debug", "environment", "is_production"):
        assert forbidden not in attributes, f"the 500 handler now branches on {forbidden}"


def test_development_is_suppressed_too(client_free_app: TestClient) -> None:
    """Establishes that production is not what causes suppression.

    Recorded honestly rather than claimed the other way round: the default test environment is
    not production, and a 500 here is just as clean. If this ever starts leaking while the
    production test stays green, suppression has become conditional and the guarantee above
    has quietly weakened.
    """
    response = controlled_500(client_free_app)
    assert_no_internals(response.status_code, response.text, str(dict(response.headers)))


@pytest.fixture
def client_free_app() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)
