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
import logging
import re
import subprocess
import sys
import textwrap
from collections.abc import Iterator
from datetime import datetime, timezone
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


# -------------------------------------------------------------------------------------
# Week 9A-5 - the Week 8C privacy guarantees, re-verified under production
#
# Slice 8C pinned these thoroughly, but every one of its tests runs in the default
# environment. Nothing asserted they survive ELIGICORE_ENVIRONMENT=production, and the
# realistic regression is specific: someone wires the environment into logging - a verbose
# production handler, a different level, a payload dump "just for production" - and the
# whole merged privacy suite stays green while the deployed system leaks.
#
# run_privacy_sweep() is a plain function so the child process can import and call it.
# -------------------------------------------------------------------------------------

#: Unmistakable synthetic markers. Nonsense strings, so a substring hit cannot be confused
#: with library output, and plainly not real personal data.
PRIVACY_MARKERS = {
    "candidate_id": "ZZQ-CANDID-9A5",
    "name": "Zzqmarker Personname",
    "email": "zzqmarker9a5@example.com",
    "phone": "+19995550911",
    "location": "Zzqville",
    "institution": "Zzq Institute of Marking",
    "cgpa": "6.83",
    "field_of_study": "Zzqology",
    "skill": "Zzqscript",
    "resume_text": "ZZQ-RESUME-BODY-9A5",
    "project": "Zzq Ledger Project",
    "certification": "Zzq Certified Marker",
    "private_note": "ZZQ-PRIVATE-NOTE-9A5",
    "secret_like": "ZZQ-SECRETLIKE-TOKEN-9A5",
    "employer": "Zzq Industries",
    "language": "Zzquese",
}

#: A marker made only of digits and dots - ``cgpa``, because a grade has to stay a number -
#: cannot be looked for as a bare substring. The text these sweeps scan is full of unrelated
#: numbers that legitimately contain one, and two such collisions were observed in practice,
#: both for ``6.83``:
#:
#: * a SQLite ``iterdump`` carries the seeded row's ``created_at``, and
#:   ``'2026-10-02 06:01:36.834134'`` contains it - roughly one run in 1500;
#: * :class:`Sink` records ``repr(record.args)``, and the request middleware's duration
#:   argument is an *unrounded* float, so ``16.830941107869148`` contains it too. The
#:   rendered line is safe (``duration_ms=%.1f``); the raw argument is not.
#:
#: Neither is a leak, and neither can be fixed by making the marker longer: a float repr
#: carries up to seventeen significant digits, so any decimal remains a possible substring
#: of one. Requiring that a numeric marker not be *part of a longer number* removes both
#: classes outright and deterministically, with nothing left to wall-clock timing.
#:
#: The assertion keeps its full strength, because a real leak renders the value as a value -
#: ``cgpa=6.83``, ``"cgpa": 6.83``, ``6.83 (SCALE_10)``, ``... is 6.83.`` - and never with a
#: digit against it. A trailing ``.`` is deliberately still a hit, since prose ends that way.
_PURELY_NUMERIC = re.compile(r"[0-9.]+\Z")

#: The seeded job's timestamps. A constant instant, so the database dump the sweep compares
#: contains no wall-clock text at all. Its digits are round on purpose: nothing in it can be
#: mistaken for a marker even if the anchoring above were removed.
SEEDED_AT = datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


def markers_present(haystack: str) -> list[str]:
    """Which privacy markers `haystack` contains, as markers rather than as digit runs.

    Text markers are matched by plain containment, exactly as before - they are nonsense
    strings that nothing else can emit. Numeric markers are matched only where they are the
    whole number, for the reason recorded above :data:`_PURELY_NUMERIC`.
    """
    found: list[str] = []
    for key, value in PRIVACY_MARKERS.items():
        text = str(value)
        if _PURELY_NUMERIC.match(text):
            hit = re.search(rf"(?<![0-9.]){re.escape(text)}(?!\d)", haystack) is not None
        else:
            hit = text in haystack
        if hit:
            found.append(key)
    return sorted(found)

MARKED_PROFILE: dict[str, Any] = {
    "candidate_id": PRIVACY_MARKERS["candidate_id"],
    "name": PRIVACY_MARKERS["name"],
    "email": PRIVACY_MARKERS["email"],
    "phone": PRIVACY_MARKERS["phone"],
    "location": PRIVACY_MARKERS["location"],
    "skills": [PRIVACY_MARKERS["skill"], "Python"],
    "projects": [
        {"name": PRIVACY_MARKERS["project"],
         "description": PRIVACY_MARKERS["private_note"]}
    ],
    "certifications": [{"name": PRIVACY_MARKERS["certification"]}],
    "languages": [PRIVACY_MARKERS["language"]],
    "experience": [{"title": "Intern", "company": PRIVACY_MARKERS["employer"]}],
    "education": [
        {
            "degree": "B.Tech",
            "institution": PRIVACY_MARKERS["institution"],
            "cgpa": float(PRIVACY_MARKERS["cgpa"]),
            "scale": "SCALE_10",
            # Not an exact match for the job's permitted field, which is what forces the
            # AI relatedness stage and therefore produces a cost record to inspect.
            "field_of_study": PRIVACY_MARKERS["field_of_study"],
        }
    ],
    "backlogs": 2,
    "resume_raw_text": PRIVACY_MARKERS["resume_text"],
}

#: Detects a middleware request record without constraining its shape.
#:
#: Deliberately loose. An earlier version matched the exact five-field line, which meant a
#: record that had been WIDENED no longer matched and was silently dropped from the sample
#: - so the field-set assertion never saw the regression it exists to catch. Detecting the
#: record by its opening fields and asserting the field set separately makes a widened
#: record fail instead of disappear.
MIDDLEWARE_RECORD = re.compile(r"^request_id=\S+ method=\S+ path=\S+ status=\d+ ")


def run_privacy_sweep() -> dict[str, Any]:
    """Exercise every candidate-carrying path and report what reached the outside.

    Called in a child interpreter started under production, because the application and
    its settings are built at import time.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.ai.ai_service import AIService
    from app.ai.providers.mock import MockAIProvider
    from app.config import ModelCostRate, Settings
    from app.database import Base
    from app.models.job import Job, JobStatus
    from app.routers.eligibility import get_lazy_ai_service
    from app.schemas.candidate import JobType

    records: list[str] = []

    class Sink(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            try:
                records.append(record.getMessage())
            except Exception:
                records.append(str(record.msg))
            records.append(repr(record.args))

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(Sink())
    for name in ("eligicore", "eligicore.ai", "eligicore.eligibility"):
        child = logging.getLogger(name)
        child.setLevel(logging.DEBUG)
        child.addHandler(Sink())

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as seed:
        seed.add(
            Job(
                id="job-1",
                company_name="Zzq Target Co",
                role_title="Backend Engineer",
                job_type=JobType.INTERNSHIP,
                description="Python backend work.",
                requirements={},
                allowed_fields=["Computer Science"],
                required_skills=["Python"],
                source="curated",
                source_job_id="A",
                content_hash="0" * 64,
                status=JobStatus.ACTIVE,
                # Pinned, not defaulted. `before` and `after` are compared byte for byte,
                # and these three columns default to `utcnow()` - the only wall-clock text
                # in the dump. Fixing them makes the fixture reproducible and leaves the
                # comparison with nothing to observe but what the requests actually wrote.
                last_verified_at=SEEDED_AT,
                created_at=SEEDED_AT,
                updated_at=SEEDED_AT,
            )
        )
        seed.commit()

    def db() -> Any:
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = db
    app.dependency_overrides[get_lazy_ai_service] = lambda: AIService(
        MockAIProvider(),
        settings=Settings(
            ai_cost_rates={
                "mock:mock-deterministic-v1": ModelCostRate(
                    prompt_micros_per_1k=100, completion_micros_per_1k=400
                )
            }
        ),
    )
    client = TestClient(app, raise_server_exceptions=False)

    def dump() -> str:
        return "\n".join(engine.connect().connection.iterdump())

    before = dump()
    statuses: dict[str, int] = {}
    bodies: list[str] = []
    question = "Describe " + PRIVACY_MARKERS["project"] + " and your CGPA."

    for label, url, payload in (
        ("validate", "/api/v1/candidates/validate", MARKED_PROFILE),
        ("normalize", "/api/v1/candidates/normalize", MARKED_PROFILE),
        ("eligibility", "/api/v1/eligibility/check",
         {"profile": MARKED_PROFILE, "job_ids": ["job-1"]}),
        ("recommendations", "/api/v1/recommendations", {"profile": MARKED_PROFILE}),
        ("prepare", "/api/v1/applications/prepare",
         {"profile": MARKED_PROFILE, "job_id": "job-1",
          "questions": [{"id": "q1", "text": question}]}),
        ("export", "/api/v1/applications/export",
         {"records": [{"job_id": "job-1", "company_name": "Zzq Target Co",
                       "role_title": "Backend Engineer",
                       "application_status": "NOT_APPLIED",
                       "notes": PRIVACY_MARKERS["private_note"]}]}),
    ):
        response = client.post(url, json=payload)
        statuses[label] = response.status_code

    def exploding() -> Any:
        raise RuntimeError(
            "failure carrying "
            + PRIVACY_MARKERS["name"] + " " + PRIVACY_MARKERS["email"] + " "
            + PRIVACY_MARKERS["resume_text"] + " " + PRIVACY_MARKERS["secret_like"]
        )

    app.dependency_overrides[get_db] = exploding
    failed = client.post(
        "/api/v1/eligibility/check",
        json={"profile": MARKED_PROFILE, "job_ids": ["job-1"]},
    )
    app.dependency_overrides[get_db] = db
    statuses["unhandled_500"] = failed.status_code
    bodies.append(failed.text + " " + json.dumps(dict(failed.headers)))

    missing = client.get("/api/v1/jobs/zzq-missing-job")
    statuses["not_found"] = missing.status_code
    bodies.append(missing.text)

    after = dump()
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_lazy_ai_service, None)

    logs = "\n".join(records)
    cost = [line for line in records if "cost_micros=" in line]
    middleware = [line.strip() for line in records
                  if MIDDLEWARE_RECORD.match(line.strip())]

    return {
        "statuses": statuses,
        "markers_in_logs": markers_present(logs),
        "markers_in_bodies": markers_present(" ".join(bodies)),
        "markers_in_cost": markers_present("\n".join(cost)),
        "markers_in_db": markers_present(after),
        "candidate_id_in_cost": "candidate_id" in "\n".join(cost),
        "cost_record_count": len(cost),
        "middleware_field_sets": sorted(
            {",".join(sorted(set(re.findall(r"\b(\w+)=", line)))) for line in middleware}
        ),
        "middleware_count": len(middleware),
        "middleware_paths": sorted(
            {m.group(1) for line in middleware
             for m in [re.search(r"path=(\S+)", line)] if m}
        ),
        "requests_made": len(statuses),
        "db_identical": before == after,
    }


def sweep_under_production() -> dict[str, Any]:
    out = in_child(
        "import json\n"
        "from tests.test_production_configuration import run_privacy_sweep\n"
        "print('RESULT ' + json.dumps(run_privacy_sweep()))\n",
        ELIGICORE_ENVIRONMENT="production",
    )
    line = next(ln for ln in out.splitlines() if ln.startswith("RESULT "))
    return json.loads(line[len("RESULT "):])


def test_no_candidate_marker_survives_any_path_under_production() -> None:
    """The Week 8C marker sweep, re-run with the application started in production."""
    result = sweep_under_production()

    # Guard first. A clean sweep over requests rejected at the validation boundary proves
    # nothing - the candidate data never reached a service. This assertion is the
    # difference between evidence and a green tick.
    executed = {k: v for k, v in result["statuses"].items()
                if k not in ("unhandled_500", "not_found")}
    assert all(code == 200 for code in executed.values()), executed
    assert result["statuses"]["unhandled_500"] == 500
    assert result["statuses"]["not_found"] == 404
    assert result["cost_record_count"] > 0, "the AI stage never ran; cost logging untested"

    assert result["markers_in_logs"] == []
    assert result["markers_in_bodies"] == []
    assert result["markers_in_cost"] == []
    assert result["candidate_id_in_cost"] is False


def test_the_request_record_keeps_its_five_fields_under_production() -> None:
    """Production must still emit one operational record, and must not widen it."""
    result = sweep_under_production()
    assert result["middleware_count"] > 0

    # Every record, not merely some record: a widened one is detected above and must show
    # up here as an extra field rather than vanish from the sample.
    assert result["middleware_field_sets"] == [
        "duration_ms,method,path,request_id,status"
    ], result["middleware_field_sets"]

    # And one per request: a record that stopped being emitted would otherwise pass the
    # assertion above simply by not existing. Eight requests cover seven distinct paths,
    # because the controlled 500 is driven through the eligibility path a second time.
    assert result["requests_made"] == 8, result["requests_made"]
    assert len(result["middleware_paths"]) == 7, result["middleware_paths"]
    for path in (
        "/api/v1/candidates/validate",
        "/api/v1/candidates/normalize",
        "/api/v1/eligibility/check",
        "/api/v1/recommendations",
        "/api/v1/applications/prepare",
        "/api/v1/applications/export",
        "/api/v1/jobs/zzq-missing-job",
    ):
        assert path in result["middleware_paths"], path


def test_the_database_is_byte_identical_across_production_requests() -> None:
    """Evaluation and logging write nothing. Compared by full dump, not row counts."""
    result = sweep_under_production()
    assert result["db_identical"] is True
    assert result["markers_in_db"] == []


# -------------------------------------------------------------------------------------
# The marker scan itself, pinned.
#
# Every assertion above is only as good as `markers_present`. These tests hold it from
# both sides: it must not report the numbers that really did collide, and it must still
# report a marker that a leak would actually render. Neither depends on the clock.
# -------------------------------------------------------------------------------------


def test_the_numeric_marker_is_not_reported_inside_an_unrelated_number() -> None:
    """The two collisions that actually happened, pinned so neither can return.

    Both are reproduced verbatim: the first came out of a failing run, the second out of
    the middleware's own argument tuple. Each genuinely contains the marker as a substring
    - that is asserted first, so this test cannot pass by the collision having quietly
    disappeared from the sample rather than from the matcher.
    """
    cgpa = PRIVACY_MARKERS["cgpa"]

    dumped_row = (
        "INSERT INTO jobs VALUES('job-1','Zzq Target Co','Backend Engineer',"
        "'INTERNSHIP','ACTIVE','2026-10-02 06:01:36.834134',"
        "'2026-10-02 06:01:36.834134');"
    )
    logged_args = "('req-1', 'POST', '/api/v1/eligibility/check', 200, 16.830941107869148)"

    assert cgpa in dumped_row, "the colliding timestamp no longer contains the marker"
    assert cgpa in logged_args, "the colliding duration no longer contains the marker"

    assert markers_present(dumped_row) == []
    assert markers_present(logged_args) == []


def test_a_real_numeric_marker_leak_is_still_reported() -> None:
    """The anchoring must not have bought its determinism by going blind."""
    cgpa = PRIVACY_MARKERS["cgpa"]
    for leak in (
        f"cgpa={cgpa}",
        f'{{"cgpa": {cgpa}}}',
        f"{cgpa} (SCALE_10)",
        f"Minimum CGPA 7.0 not met; candidate has {cgpa}.",
        f"[{cgpa}]",
        cgpa,
    ):
        assert markers_present(leak) == ["cgpa"], leak


def test_the_numeric_marker_is_searched_in_the_form_it_is_injected_in() -> None:
    """`MARKED_PROFILE` carries a float; the scan searches a string. They must agree.

    If `float(cgpa)` ever stopped rendering back to the literal - an extra digit, a
    trailing zero - every CGPA assertion in this module would pass by searching for text
    the application could never emit.
    """
    cgpa = PRIVACY_MARKERS["cgpa"]
    assert str(float(cgpa)) == cgpa
    assert MARKED_PROFILE["education"][0]["cgpa"] == float(cgpa)


def test_text_markers_are_still_matched_by_plain_containment() -> None:
    """Only the numeric marker is anchored. The nonsense strings keep substring matching."""
    assert markers_present("prefix" + PRIVACY_MARKERS["name"] + "suffix") == ["name"]
    assert markers_present(PRIVACY_MARKERS["resume_text"] + "9") == ["resume_text"]
    assert markers_present("nothing to see here") == []


def test_every_privacy_marker_is_covered_by_one_of_the_two_rules() -> None:
    """A marker added later gets anchoring automatically, or it is a nonsense string.

    A short, purely numeric marker that slipped past both would reintroduce exactly the
    flake this module just removed, so the set is checked rather than assumed.
    """
    for key, value in PRIVACY_MARKERS.items():
        text = str(value)
        assert text, key
        if _PURELY_NUMERIC.match(text):
            # Anchored, so being inside a longer number is not a hit.
            assert markers_present(f"1{text}1") == [], key
        else:
            # Not a number, so no generated timestamp, duration or id can contain it.
            assert any(not ch.isdigit() and ch != "." for ch in text), key
