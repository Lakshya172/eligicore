"""Week 8 Slice 8C — operational-log completeness (ADR-026 D10, dossier §10.2).

§10.2 names three things operational logs hold: **request counts, AI usage and cost logging,
and error records**, "kept for system operation and diagnostics, not as a record of any
individual's profile or applications". Slice 8A delivered the middle one. This slice audits
the other two and closes what the audit found.

The audit found exactly one production gap, and these tests exist mostly to pin it shut: a
request that ended in an unhandled exception produced an **error record but no request
record**, because Starlette's ``ServerErrorMiddleware`` sits outside the request middleware
and the exception never returned through ``call_next``. Every other status was recorded.

The rest is evidence rather than change. Where a category was already satisfied, that is
asserted rather than rebuilt: §10.2 asks for records, not for a logging subsystem.

No route is added anywhere here. An unhandled exception is produced by making a real
endpoint's dependency raise, so the app under test is the real one, with its real paths and
its real route count.
"""

from __future__ import annotations

import ast
import inspect
import io
import logging
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.ai_service import AIService, get_lazy_ai_service
from app.ai.providers.mock import MockAIProvider
from app.config import ModelCostRate, Settings
from app.database import Base, get_db
from app.main import app
from app.models.job import Job, JobStatus
from app.schemas.candidate import JobType

# Markers: every one is a value that must never reach an operational log line.
M_ID = "OPLOG-CAND-ID-8c"
M_NAME = "Oplogmarker Person"
M_EMAIL = "oplogmarker@example.com"
M_PHONE = "+19995550377"
M_LOCATION = "Oplogville"
M_INSTITUTION = "Oplog Institute"
M_CGPA = 6.77
M_BACKLOGS = 2
M_EMPLOYER = "Oplog Industries"
M_LANGUAGE = "Oploguese"
M_RESUME = "OPLOG-RESUME-TEXT-8c"
M_PROJECT = "Oplog Ledger"
M_QUESTION = "Tell us about the Oplog Ledger and your CGPA."
M_COMPANY = "Oplog Target Co"
M_SKILL = "Python"

PROFILE: dict[str, Any] = {
    "candidate_id": M_ID,
    "name": M_NAME,
    "email": M_EMAIL,
    "phone": M_PHONE,
    "location": M_LOCATION,
    "skills": [M_SKILL],
    "projects": [{"name": M_PROJECT}],
    "experience": [{"title": "Intern", "company": M_EMPLOYER}],
    "education": [
        {
            "degree": "B.Tech",
            "institution": M_INSTITUTION,
            "cgpa": M_CGPA,
            "scale": "SCALE_10",
            "field_of_study": "Information Technology",
        }
    ],
    "languages": [M_LANGUAGE],
    "backlogs": M_BACKLOGS,
    "resume_raw_text": M_RESUME,
}

MARKERS = {
    "candidate_id": M_ID,
    "name": M_NAME,
    "email": M_EMAIL,
    "phone": M_PHONE,
    "location": M_LOCATION,
    "institution": M_INSTITUTION,
    "cgpa": str(M_CGPA),
    "backlogs": f'"backlogs": {M_BACKLOGS}',
    "employer": M_EMPLOYER,
    "language": M_LANGUAGE,
    "resume text": M_RESUME,
    "question text": M_QUESTION,
    "project name": M_PROJECT,
    "target company": M_COMPANY,
}

PRICED = Settings(
    ai_cost_rates={
        "mock:mock-deterministic-v1": ModelCostRate(
            prompt_micros_per_1k=100, completion_micros_per_1k=400
        )
    }
)


class Capture:
    """Everything the root logger emitted while the block ran."""

    def __init__(self) -> None:
        self.buffer = io.StringIO()
        self._handler = logging.StreamHandler(self.buffer)
        self._root = logging.getLogger()
        self._previous = self._root.level

    def __enter__(self) -> Capture:
        self._root.addHandler(self._handler)
        self._root.setLevel(logging.DEBUG)
        return self

    def __exit__(self, *exc: object) -> None:
        self._root.removeHandler(self._handler)
        self._root.setLevel(self._previous)

    @property
    def text(self) -> str:
        return self.buffer.getvalue()

    @property
    def lines(self) -> list[str]:
        return [line for line in self.text.splitlines() if "request_id=" in line]

    def requests(self) -> list[str]:
        return [line for line in self.lines if " method=" in line and " status=" in line]

    def errors(self) -> list[str]:
        return [
            line
            for line in self.lines
            if "unhandled_exception" in line or "validation_failed" in line
        ]


def request_id_of(line: str) -> str:
    match = re.search(r"request_id=(\S+)", line)
    assert match is not None, line
    return match.group(1)


def field(line: str, name: str) -> str:
    match = re.search(rf"\b{name}=(\S+)", line)
    assert match is not None, f"{name} missing from {line}"
    return match.group(1)


@pytest.fixture
def client() -> Any:
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        session.add(
            Job(
                id="job-1",
                company_name=M_COMPANY,
                role_title="Backend Engineer",
                job_type=JobType.INTERNSHIP,
                description="Python",
                requirements={},
                allowed_fields=[],
                required_skills=[M_SKILL],
                source="curated",
                source_job_id="A",
                content_hash="0" * 64,
                status=JobStatus.ACTIVE,
            )
        )
        # A second job whose permitted fields do not match the profile exactly, so the
        # eligibility AI stage actually runs and the usage/cost line is actually emitted.
        session.add(
            Job(
                id="job-ai",
                company_name=M_COMPANY,
                role_title="Data Engineer",
                job_type=JobType.INTERNSHIP,
                description="Python",
                requirements={},
                allowed_fields=["Computer Science"],
                required_skills=[M_SKILL],
                source="curated",
                source_job_id="B",
                content_hash="1" * 64,
                status=JobStatus.ACTIVE,
            )
        )
        session.commit()

    def db() -> Any:
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = db
    app.dependency_overrides[get_lazy_ai_service] = lambda: AIService(
        MockAIProvider(), settings=PRICED
    )
    test_client = TestClient(app, raise_server_exceptions=False)
    test_client.engine = engine  # type: ignore[attr-defined]
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


def break_a_dependency() -> None:
    """Make a real endpoint raise, without adding a route to the application."""

    def exploding() -> Any:
        raise RuntimeError(
            f"internal failure while handling {M_NAME} {M_EMAIL} CGPA {M_CGPA} {M_RESUME}"
        )

    app.dependency_overrides[get_db] = exploding


# ---------------------------------------------------------------------------------------
# A. Request counts
# ---------------------------------------------------------------------------------------


def test_a_successful_request_is_recorded_once(client: TestClient) -> None:
    with Capture() as log:
        client.get("/api/v1/health")
    assert len(log.requests()) == 1
    line = log.requests()[0]
    assert field(line, "method") == "GET"
    assert field(line, "path") == "/api/v1/health"
    assert field(line, "status") == "200"
    assert float(field(line, "duration_ms")) >= 0


@pytest.mark.parametrize(
    ("name", "call", "expected"),
    [
        ("unknown route", lambda c: c.get("/api/v1/does-not-exist"), "404"),
        ("wrong method", lambda c: c.get("/api/v1/candidates/validate"), "405"),
        ("unknown job", lambda c: c.get("/api/v1/jobs/missing-job"), "404"),
        (
            "validation failure",
            lambda c: c.post("/api/v1/candidates/validate", json={"nonsense": True}),
            "422",
        ),
    ],
)
def test_every_failure_status_is_recorded_too(
    client: TestClient, name: str, call: Any, expected: str
) -> None:
    with Capture() as log:
        call(client)
    assert len(log.requests()) == 1, name
    assert field(log.requests()[0], "status") == expected, name


def test_an_unhandled_exception_is_still_counted(client: TestClient) -> None:
    """The gap this slice closed.

    ``ServerErrorMiddleware`` is outside the request middleware, so before Slice 8C the
    exception travelled back through ``call_next`` and no request line was ever emitted —
    the request record was blind to every 500.
    """
    break_a_dependency()
    with Capture() as log:
        response = client.post(
            "/api/v1/eligibility/check", json={"profile": PROFILE, "job_ids": ["job-1"]}
        )

    assert response.status_code == 500
    assert len(log.requests()) == 1, "a 500 must produce exactly one request record"
    line = log.requests()[0]
    assert field(line, "status") == "500"
    assert field(line, "method") == "POST"
    assert field(line, "path") == "/api/v1/eligibility/check"
    assert float(field(line, "duration_ms")) >= 0


def test_a_counted_request_and_its_error_record_share_one_request_id(
    client: TestClient,
) -> None:
    break_a_dependency()
    with Capture() as log:
        client.post("/api/v1/eligibility/check", json={"profile": PROFILE, "job_ids": ["job-1"]})

    assert len(log.requests()) == 1 and len(log.errors()) == 1
    assert request_id_of(log.requests()[0]) == request_id_of(log.errors()[0])


def test_each_request_is_counted_exactly_once(client: TestClient) -> None:
    with Capture() as log:
        for _ in range(5):
            client.get("/api/v1/health")
    assert len(log.requests()) == 5


def test_request_records_carry_only_sanctioned_metadata(client: TestClient) -> None:
    """§8.1b: request ids, timings, status codes, operation type and safe technical data."""
    with Capture() as log:
        client.post("/api/v1/eligibility/check", json={"profile": PROFILE, "job_ids": ["job-1"]})

    line = log.requests()[0]
    fields = set(re.findall(r"\b(\w+)=", line))
    assert fields == {"request_id", "method", "path", "status", "duration_ms"}


def test_a_supplied_request_id_is_reused_rather_than_replaced(client: TestClient) -> None:
    with Capture() as log:
        response = client.get("/api/v1/health", headers={"X-Request-ID": "given-8c"})
    assert request_id_of(log.requests()[0]) == "given-8c"
    assert response.headers["X-Request-ID"] == "given-8c"


def test_a_provider_retry_does_not_become_a_second_application_request() -> None:
    """Retries are outbound calls. They cannot reach the inbound middleware, and must not."""
    import httpx

    from app.ai.providers.gemini import GeminiFlashProvider
    from app.ai.usage import UsageSink

    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(503)

    provider = GeminiFlashProvider(
        api_key="test-key-not-real",
        model="m",
        api_base="https://example.invalid/v1",
        timeout_seconds=1,
        max_retries=2,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    import anyio

    from app.ai.errors import AIProviderUnavailableError

    async def run() -> None:
        with pytest.raises(AIProviderUnavailableError):
            await provider.assess_field_relatedness("IT", ["CS"], usage=UsageSink())

    with Capture() as log:
        anyio.run(run)

    assert len(attempts) == 3, "three outbound attempts"
    assert log.requests() == [], "and zero inbound request records"


# ---------------------------------------------------------------------------------------
# B. Error records
# ---------------------------------------------------------------------------------------


def test_an_unhandled_exception_records_its_type_and_nothing_else(
    client: TestClient,
) -> None:
    break_a_dependency()
    with Capture() as log:
        client.post("/api/v1/eligibility/check", json={"profile": PROFILE, "job_ids": ["job-1"]})

    assert len(log.errors()) == 1
    line = log.errors()[0]
    assert "type=RuntimeError" in line
    assert set(re.findall(r"\b(\w+)=", line)) == {"request_id", "path", "type"}


def test_an_exception_message_carrying_candidate_data_never_reaches_a_log(
    client: TestClient,
) -> None:
    """The exception raised above embeds a name, an email, a CGPA and résumé text."""
    break_a_dependency()
    with Capture() as log:
        response = client.post(
            "/api/v1/eligibility/check", json={"profile": PROFILE, "job_ids": ["job-1"]}
        )

    assert response.status_code == 500
    for label, marker in MARKERS.items():
        assert marker not in log.text, label
    assert "internal failure while handling" not in log.text


def test_the_error_response_body_leaks_nothing_either(client: TestClient) -> None:
    break_a_dependency()
    response = client.post(
        "/api/v1/eligibility/check", json={"profile": PROFILE, "job_ids": ["job-1"]}
    )
    body = response.json()
    assert body["error"] == "INTERNAL_ERROR"
    assert body["message"] == "An internal error occurred."
    for marker in MARKERS.values():
        assert marker not in response.text


def test_a_validation_failure_records_a_count_not_the_values(client: TestClient) -> None:
    with Capture() as log:
        response = client.post(
            "/api/v1/candidates/validate",
            json={"candidate_id": M_ID, "name": M_NAME, "email": "not-an-email"},
        )

    assert response.status_code == 422
    assert len(log.errors()) == 1
    line = log.errors()[0]
    assert set(re.findall(r"\b(\w+)=", line)) == {"request_id", "path", "error_count"}
    assert int(field(line, "error_count")) >= 1
    for marker in (M_NAME, "not-an-email", M_ID):
        assert marker not in log.text, marker


def test_an_http_error_is_represented_by_its_request_record(client: TestClient) -> None:
    """A 404 is not given a second, duplicate record. Its status is the classification."""
    with Capture() as log:
        response = client.get("/api/v1/jobs/no-such-job")

    assert response.status_code == 404
    assert len(log.requests()) == 1
    assert field(log.requests()[0], "status") == "404"
    assert log.errors() == [], "a 404 must not also emit an error record"


def test_error_records_are_not_duplicated(client: TestClient) -> None:
    break_a_dependency()
    with Capture() as log:
        client.post("/api/v1/eligibility/check", json={"profile": PROFILE, "job_ids": ["job-1"]})
    assert log.text.count("unhandled_exception") == 1


def test_logging_an_error_does_not_change_the_response(client: TestClient) -> None:
    """Silencing the logger must leave the status and body untouched."""
    break_a_dependency()
    quiet = logging.getLogger("eligicore")
    previous = quiet.disabled
    quiet.disabled = True
    try:
        silenced = client.post(
            "/api/v1/eligibility/check", json={"profile": PROFILE, "job_ids": ["job-1"]}
        )
    finally:
        quiet.disabled = previous

    logged = client.post(
        "/api/v1/eligibility/check", json={"profile": PROFILE, "job_ids": ["job-1"]}
    )
    assert silenced.status_code == logged.status_code == 500
    assert silenced.json()["error"] == logged.json()["error"]


def test_the_exception_handler_logs_no_exception_message() -> None:
    """Structural: the handler has no access to the message in its log call."""
    import app.main as main

    source = inspect.getsource(main.unhandled_exception_handler)
    tree = ast.parse(inspect.cleandoc(source.split('"""')[0] + source.split('"""')[2]))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") in {"error", "info"}:
            rendered = [ast.unparse(arg) for arg in node.args]
            assert "str(exc)" not in rendered, rendered
            assert "exc.args" not in " ".join(rendered)
            assert any("type(exc).__name__" in arg for arg in rendered)


# ---------------------------------------------------------------------------------------
# C. AI usage and cost — Slice 8A regression
# ---------------------------------------------------------------------------------------


def test_ai_usage_and_cost_fields_survive_this_slice(client: TestClient) -> None:
    """Through the real endpoint. ``job-ai`` restricts permitted fields, so the relatedness
    stage runs and Slice 8A's line is genuinely emitted rather than conditionally absent."""
    with Capture() as log:
        response = client.post(
            "/api/v1/eligibility/check", json={"profile": PROFILE, "job_ids": ["job-ai"]}
        )

    assert response.status_code == 200
    ai = [line for line in log.text.splitlines() if "ai_call" in line]
    assert ai, "the AI stage must have run for a job with restricted permitted fields"
    for name in (
        "provider",
        "model",
        "operation",
        "outcome",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "cost_micros",
        "duration_ms",
    ):
        assert f"{name}=" in ai[0], name
    for label, marker in MARKERS.items():
        assert marker not in "\n".join(ai), label


@pytest.mark.anyio
async def test_the_two_instrumented_operations_still_log_usage_and_cost(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = AIService(MockAIProvider(), settings=PRICED)
    with caplog.at_level(logging.INFO, logger="eligicore.ai"):
        await service.extract_resume("x" * 400)
        await service.assess_field_relatedness("Information Technology", ["Computer Science"])

    lines = [r.getMessage() for r in caplog.records if "ai_call" in r.getMessage()]
    assert len(lines) == 2
    for line in lines:
        for name in (
            "provider",
            "model",
            "operation",
            "outcome",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "cost_micros",
            "duration_ms",
        ):
            assert f"{name}=" in line, (name, line)


@pytest.mark.anyio
async def test_no_candidate_id_reaches_a_cost_record(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = AIService(MockAIProvider(), settings=PRICED)
    with caplog.at_level(logging.DEBUG, logger="eligicore.ai"):
        await service.assess_field_relatedness("Information Technology", ["Computer Science"])
    for record in caplog.records:
        assert M_ID not in record.getMessage()
        assert "candidate_id" not in record.getMessage()


# ---------------------------------------------------------------------------------------
# Generation boundary — unchanged by this slice
# ---------------------------------------------------------------------------------------


def test_the_generation_log_line_is_unchanged_by_slice_8c() -> None:
    import app.ai.ai_service as ai_service_module

    source = Path(ai_service_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    method = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "generate_application_content"
    )
    body = ast.get_source_segment(source, method) or ""
    for forbidden in (
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "cost_micros",
        "UsageSink",
        "_accounting",
        "usage=",
    ):
        assert forbidden not in body, forbidden
    for expected in ("operation=generate_application_content", "questions=%d", "duration_ms=%.1f"):
        assert expected in body, expected


def test_a_prepare_request_still_logs_no_token_or_cost_field(client: TestClient) -> None:
    with Capture() as log:
        response = client.post(
            "/api/v1/applications/prepare",
            json={
                "profile": PROFILE,
                "job_id": "job-1",
                "questions": [{"id": "q1", "text": M_QUESTION}],
            },
        )

    assert response.status_code == 200
    generation = [line for line in log.text.splitlines() if "generate_application_content" in line]
    assert generation, "the generation call must still be logged"
    for line in generation:
        for forbidden in ("prompt_tokens", "completion_tokens", "total_tokens", "cost_micros"):
            assert forbidden not in line, line


# ---------------------------------------------------------------------------------------
# Privacy sweep across every representative path
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "call"),
    [
        (
            "eligibility",
            lambda c: c.post(
                "/api/v1/eligibility/check", json={"profile": PROFILE, "job_ids": ["job-1"]}
            ),
        ),
        ("recommendations", lambda c: c.post("/api/v1/recommendations", json={"profile": PROFILE})),
        (
            "preparation",
            lambda c: c.post(
                "/api/v1/applications/prepare",
                json={
                    "profile": PROFILE,
                    "job_id": "job-1",
                    "questions": [{"id": "q1", "text": M_QUESTION}],
                },
            ),
        ),
        ("normalize", lambda c: c.post("/api/v1/candidates/normalize", json=PROFILE)),
        ("validate", lambda c: c.post("/api/v1/candidates/validate", json=PROFILE)),
        (
            "export",
            lambda c: c.post(
                "/api/v1/applications/export",
                json={
                    "records": [
                        {
                            "job_id": "job-1",
                            "company_name": M_COMPANY,
                            "role_title": "Backend Engineer",
                            "application_status": "APPLIED",
                        }
                    ]
                },
            ),
        ),
        ("not found", lambda c: c.get("/api/v1/jobs/missing")),
    ],
)
def test_no_marker_reaches_any_log_line(client: TestClient, name: str, call: Any) -> None:
    with Capture() as log:
        call(client)
    for label, marker in MARKERS.items():
        assert marker not in log.text, f"{label} leaked on the {name} path"


def test_the_database_is_untouched_by_a_logged_request(client: TestClient) -> None:
    engine = client.engine  # type: ignore[attr-defined]
    before = "\n".join(engine.connect().connection.iterdump())
    with Capture():
        client.post("/api/v1/eligibility/check", json={"profile": PROFILE, "job_ids": ["job-1"]})
        client.post(
            "/api/v1/applications/prepare",
            json={"profile": PROFILE, "job_id": "job-1", "questions": []},
        )
    after = "\n".join(engine.connect().connection.iterdump())
    assert before == after, "operational logging must write nothing to the database"


def test_slice_8c_added_no_persistence_and_no_new_logging_subsystem() -> None:
    source = Path("app/main.py").read_text(encoding="utf-8")
    for forbidden in ("open(", "session.add", "commit(", "logging.FileHandler", "logging.handlers"):
        assert forbidden not in source, forbidden
    assert source.count('logging.getLogger("eligicore")') == 1, "one logger, not a subsystem"


# ---------------------------------------------------------------------------------------
# Severity and measurement — closing the gaps that let level and timing mutants survive
# ---------------------------------------------------------------------------------------


def records_named(caplog: pytest.LogCaptureFixture, needle: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if needle in r.getMessage()]


def test_a_request_record_is_emitted_at_info_not_debug(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """A request record at DEBUG is invisible in any normal deployment, which is the same
    as not recording it. ``ELIGICORE_LOG_LEVEL`` defaults to INFO."""
    with caplog.at_level(logging.DEBUG, logger="eligicore"):
        client.get("/api/v1/health")
    lines = records_named(caplog, "method=GET")
    assert lines and all(r.levelno == logging.INFO for r in lines), [r.levelname for r in lines]


def test_the_five_hundred_request_record_is_also_at_info(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    break_a_dependency()
    with caplog.at_level(logging.DEBUG, logger="eligicore"):
        client.post("/api/v1/eligibility/check", json={"profile": PROFILE, "job_ids": ["job-1"]})
    lines = records_named(caplog, "status=500")
    assert lines and all(r.levelno == logging.INFO for r in lines), [r.levelname for r in lines]


def test_a_validation_record_is_at_info_and_an_unhandled_one_at_error(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG, logger="eligicore"):
        client.post("/api/v1/candidates/validate", json={"nonsense": True})
    validation = records_named(caplog, "validation_failed")
    assert validation and all(r.levelno == logging.INFO for r in validation)

    caplog.clear()
    break_a_dependency()
    with caplog.at_level(logging.DEBUG, logger="eligicore"):
        client.post("/api/v1/eligibility/check", json={"profile": PROFILE, "job_ids": ["job-1"]})
    unhandled = records_named(caplog, "unhandled_exception")
    assert unhandled and all(r.levelno == logging.ERROR for r in unhandled)


@pytest.mark.parametrize(
    ("name", "call"),
    [
        ("success", lambda c: c.get("/api/v1/health")),
        (
            "validation failure",
            lambda c: c.post("/api/v1/candidates/validate", json={"nonsense": True}),
        ),
        ("not found", lambda c: c.get("/api/v1/jobs/missing")),
    ],
)
def test_duration_is_a_measured_elapsed_time(
    client: TestClient, name: str, call: Any
) -> None:
    """Bounded on both sides. Zero means the timer was never read; an enormous value means
    it was read against the wrong origin. Both are timings that describe nothing."""
    with Capture() as log:
        call(client)
    duration = float(field(log.requests()[0], "duration_ms"))
    assert 0 < duration < 60_000, (name, duration)


def test_the_five_hundred_duration_is_measured_too(client: TestClient) -> None:
    break_a_dependency()
    with Capture() as log:
        client.post("/api/v1/eligibility/check", json={"profile": PROFILE, "job_ids": ["job-1"]})
    duration = float(field(log.requests()[0], "duration_ms"))
    assert 0 < duration < 60_000, duration


def test_a_slower_request_reports_a_longer_duration(client: TestClient) -> None:
    """The number tracks the work, rather than being a constant that happens to be in range."""
    with Capture() as trivial:
        client.get("/api/v1/health")
    with Capture() as heavier:
        client.post("/api/v1/recommendations", json={"profile": PROFILE})

    assert float(field(heavier.requests()[0], "duration_ms")) > float(
        field(trivial.requests()[0], "duration_ms")
    )


# ---------------------------------------------------------------------------------------
# Error envelopes stay exactly as specified
# ---------------------------------------------------------------------------------------


def test_a_not_found_body_carries_the_detail_and_nothing_more(client: TestClient) -> None:
    response = client.get("/api/v1/jobs/missing-job")
    body = response.json()
    assert response.status_code == 404
    assert body["error"] == "HTTP_ERROR"
    assert body["message"] == "Job not found."
    assert "404" not in body["message"], "the status must not be spliced into the message"
    assert body["request_id"]


def test_a_prepare_not_found_body_is_the_same_shape(client: TestClient) -> None:
    response = client.post(
        "/api/v1/applications/prepare",
        json={"profile": PROFILE, "job_id": "no-such-job", "questions": []},
    )
    assert response.status_code == 404
    body = response.json()
    assert body["error"] == "HTTP_ERROR"
    assert body["message"] == "Job not found."
    for marker in MARKERS.values():
        assert marker not in response.text


def test_a_validation_body_keeps_its_details_and_echoes_no_value(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/candidates/validate",
        json={"candidate_id": M_ID, "name": M_NAME, "email": "not-an-email"},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "VALIDATION_ERROR"
    assert body["details"], "a validation failure must say which fields failed"
    for detail in body["details"]:
        assert set(detail) == {"field", "code", "message"}
        assert detail["field"] and detail["code"]
    for marker in (M_NAME, M_ID, "not-an-email"):
        assert marker not in response.text, marker
