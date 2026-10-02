"""Live HTTP adapter infrastructure: retries, pagination, rate limiting, sanitization.

**Every request in this file goes through an injected ``httpx.MockTransport``. Nothing here
touches a network** (``standards/testing.md`` §1). Sleeping, randomness and the clock are
injected too, so the suite asserts the backoff and rate-limit behaviour without waiting for
it (``standards/code_quality.md`` §6).

The sanitization tests are the important ones. A live source's URL may carry an API key and
its body may quote anything back, so the assertions below are written as *absence* checks
against a deliberately incriminating URL, header and body: if any of those strings ever
reaches an error or a log line, the test fails (INV-4, ADR-028 § Security and privacy).
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
import pytest

from app.adapters.base_adapter import AdapterError, JobSourceAdapter
from app.adapters.live_http_adapter import (
    HTTPErrorCategory,
    LiveHTTPAdapter,
    PageRequest,
    RateLimiter,
)
from app.schemas.candidate import JobType
from app.schemas.job import RawJob

# Strings that must never escape into an error, a log line or any other output. Obviously
# synthetic, and none is a real credential (``standards/testing.md`` §5).
SECRET_KEY = "sk-not-a-real-key-0123456789"
SECRET_HEADER = "Bearer not-a-real-token-abcdef"
BASE_URL = "https://jobs.example.invalid/v1/postings"
FULL_URL_MARKER = "jobs.example.invalid"
QUERY_MARKER = "api_key"
BODY_MARKER = "CONFIDENTIAL-RESPONSE-BODY-MARKER"


def make_job(identifier: str) -> dict[str, Any]:
    """One obviously synthetic posting in the source-agnostic shape."""
    return {
        "company_name": "Example Analytics",
        "role_title": "Software Engineering Intern",
        "job_type": JobType.INTERNSHIP.value,
        "location": "Bengaluru, India",
        "description": "Six-month internship building internal tooling.",
        "apply_link": f"https://careers.example.invalid/roles/{identifier}",
        "source_job_id": identifier,
    }


class RecordingSleep:
    """A stand-in for ``asyncio.sleep`` that records instead of waiting."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


class FixedRandom:
    """Deterministic ``random.Random`` stand-in — always returns the same fraction."""

    def __init__(self, value: float = 0.0) -> None:
        self._value = value

    def random(self) -> float:
        return self._value


class FakeClock:
    """A monotonic clock a test advances by hand."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _TestAdapter(LiveHTTPAdapter):
    """A minimal concrete adapter. Deliberately not a real source (ADR-028 non-goals).

    Paginates by following a ``next`` field the fake source supplies, which exercises the
    hook design without encoding any real provider's convention.
    """

    source_name = "test-live"

    def initial_request(self) -> PageRequest:
        return PageRequest(
            url=BASE_URL,
            params={QUERY_MARKER: SECRET_KEY},
            headers={"Authorization": SECRET_HEADER},
        )

    def parse_page(self, payload: Any, page_number: int) -> list[RawJob]:
        return [RawJob.model_validate(entry) for entry in payload.get("jobs", [])]

    def next_request(
        self, payload: Any, previous: PageRequest, page_number: int
    ) -> PageRequest | None:
        token = payload.get("next")
        if not token:
            return None
        return PageRequest(
            url=token, params=previous.params, headers=previous.headers
        )


def build(handler: Any, **kwargs: Any) -> tuple[_TestAdapter, RecordingSleep]:
    """An adapter wired to a mock transport, with sleeping and randomness injected."""
    sleep = RecordingSleep()
    options: dict[str, Any] = {
        "client": httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        "max_retries": 2,
        "backoff_initial_seconds": 0.5,
        "backoff_max_seconds": 8.0,
        "jitter_ratio": 0.25,
        "rng": FixedRandom(0.0),
        "sleep": sleep,
        "requests_per_second": 1000.0,
        "burst": 1000,
    }
    options.update(kwargs)
    return _TestAdapter(**options), sleep


# ---------------------------------------------------------------------------------------
# A — success
# ---------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_a_successful_request_returns_the_parsed_jobs() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"jobs": [make_job("EX-1"), make_job("EX-2")]})

    adapter, sleep = build(handler)
    jobs = await adapter.fetch()

    assert [job.source_job_id for job in jobs] == ["EX-1", "EX-2"]
    assert sleep.delays == [], "A successful first attempt must never back off."


# ---------------------------------------------------------------------------------------
# B, C, D, E — what is retried
# ---------------------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("status", [500, 502, 503, 504])
async def test_b_server_errors_are_retried_and_can_succeed(status: int) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(status, text=BODY_MARKER)
        return httpx.Response(200, json={"jobs": [make_job("EX-1")]})

    adapter, sleep = build(handler)
    jobs = await adapter.fetch()

    assert calls["n"] == 2
    assert len(jobs) == 1
    assert len(sleep.delays) == 1


@pytest.mark.anyio
async def test_c_rate_limited_429_is_retried() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, text=BODY_MARKER)
        return httpx.Response(200, json={"jobs": [make_job("EX-1")]})

    adapter, sleep = build(handler)
    assert len(await adapter.fetch()) == 1
    assert calls["n"] == 2
    assert len(sleep.delays) == 1


@pytest.mark.anyio
async def test_d_a_timeout_is_retried() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(200, json={"jobs": [make_job("EX-1")]})

    adapter, sleep = build(handler)
    assert len(await adapter.fetch()) == 1
    assert calls["n"] == 2
    assert len(sleep.delays) == 1


@pytest.mark.anyio
async def test_e_a_transport_failure_is_retried() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(200, json={"jobs": [make_job("EX-1")]})

    adapter, sleep = build(handler)
    assert len(await adapter.fetch()) == 1
    assert calls["n"] == 2


# ---------------------------------------------------------------------------------------
# F, G — what is not retried, and how far retrying goes
# ---------------------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("status", [400, 401, 403, 404, 410, 422])
async def test_f_ordinary_client_errors_are_not_retried(status: int) -> None:
    """A 4xx is a statement about the request. Repeating it repeats the answer."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(status, text=BODY_MARKER)

    adapter, sleep = build(handler)
    with pytest.raises(AdapterError) as caught:
        await adapter.fetch()

    assert calls["n"] == 1, f"{status} must not be retried."
    assert sleep.delays == []
    assert f"status={status}" in str(caught.value)
    assert HTTPErrorCategory.CLIENT_ERROR.value in str(caught.value)


@pytest.mark.anyio
@pytest.mark.parametrize("max_retries", [0, 1, 2, 3])
async def test_g_the_retry_cap_is_respected(max_retries: int) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503)

    adapter, sleep = build(handler, max_retries=max_retries)
    with pytest.raises(AdapterError) as caught:
        await adapter.fetch()

    assert calls["n"] == max_retries + 1
    assert len(sleep.delays) == max_retries
    assert f"attempts={max_retries + 1}" in str(caught.value)


# ---------------------------------------------------------------------------------------
# H — backoff is bounded, not merely plausible
# ---------------------------------------------------------------------------------------


def test_h_backoff_grows_exponentially_and_stays_within_its_bounds() -> None:
    adapter, _ = build(lambda request: httpx.Response(200, json={"jobs": []}))

    for attempt in range(12):
        base = min(0.5 * (2**attempt), 8.0)
        for fraction in (0.0, 0.5, 0.999):
            adapter._rng = FixedRandom(fraction)  # type: ignore[assignment]
            delay = adapter.backoff_delay(attempt)
            assert base * 0.75 <= delay <= base
            assert delay <= 8.0, "The cap must hold for every attempt and every jitter."

    adapter._rng = FixedRandom(0.0)  # type: ignore[assignment]
    undithered = [adapter.backoff_delay(n) for n in range(5)]
    assert undithered == [0.5, 1.0, 2.0, 4.0, 8.0]


def test_h_invalid_transport_settings_are_rejected_at_construction() -> None:
    for bad in (
        {"timeout_seconds": 0},
        {"max_retries": -1},
        {"max_pages": 0},
        {"jitter_ratio": 1.0},
        {"jitter_ratio": -0.1},
        {"backoff_initial_seconds": 5.0, "backoff_max_seconds": 1.0},
    ):
        with pytest.raises(ValueError):
            build(lambda request: httpx.Response(200), **bad)


# ---------------------------------------------------------------------------------------
# I, J — pagination, and failing honestly
# ---------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_i_pagination_walks_every_page_in_order() -> None:
    pages = [
        {"jobs": [make_job("EX-1")], "next": f"{BASE_URL}?page=2"},
        {"jobs": [make_job("EX-2")], "next": f"{BASE_URL}?page=3"},
        {"jobs": [make_job("EX-3")]},
    ]
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = pages[min(len(requested), len(pages) - 1)]
        requested.append(str(request.url))
        return httpx.Response(200, json=payload)

    adapter, _ = build(handler)
    jobs = await adapter.fetch()

    assert [job.source_job_id for job in jobs] == ["EX-1", "EX-2", "EX-3"]
    assert len(requested) == 3, "Exactly one request per page, and no fourth."
    assert "page=2" in requested[1], "The next-page hook must drive the second request."
    assert "page=3" in requested[2]
    # The credential the first request carried must travel to every later page too.
    assert all(SECRET_KEY in url for url in requested)


@pytest.mark.anyio
async def test_i_a_next_page_url_keeps_its_own_query_when_params_are_merged() -> None:
    """Regression: httpx's ``params=`` *replaces* a URL's query rather than adding to it.

    Found while building this slice. A source's opaque next-page URL carries its cursor in
    the query string; passing auth parameters alongside it would silently discard that
    cursor, re-fetch page one, and loop until ``max_pages`` — a wrong catalogue rather than
    a loud failure. :meth:`LiveHTTPAdapter._send` merges instead.
    """
    requested: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url)
        if len(requested) == 1:
            return httpx.Response(
                200, json={"jobs": [], "next": f"{BASE_URL}?cursor=opaque-token"}
            )
        return httpx.Response(200, json={"jobs": []})

    adapter, _ = build(handler)
    await adapter.fetch()

    assert len(requested) == 2, "The walk must advance, not repeat page one."
    second = requested[1]
    assert second.params.get("cursor") == "opaque-token", "The cursor survived the merge."
    assert second.params.get(QUERY_MARKER) == SECRET_KEY, "And auth still travelled."


@pytest.mark.anyio
async def test_j_a_failure_after_a_good_page_fails_rather_than_truncating() -> None:
    """The whole point of the design: a partial catalogue must never look complete."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(
                200, json={"jobs": [make_job("EX-1")], "next": f"{BASE_URL}?page=2"}
            )
        return httpx.Response(503)

    adapter, _ = build(handler, max_retries=1)
    with pytest.raises(AdapterError) as caught:
        await adapter.fetch()

    assert "page=2" in str(caught.value)
    assert calls["n"] == 3, "Page one once, page two twice (one retry)."


@pytest.mark.anyio
async def test_j_endless_pagination_stops_at_the_page_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"jobs": [], "next": BASE_URL})

    adapter, _ = build(handler, max_pages=4)
    with pytest.raises(AdapterError) as caught:
        await adapter.fetch()

    assert HTTPErrorCategory.PAGINATION.value in str(caught.value)
    assert "pages=4" in str(caught.value)


@pytest.mark.anyio
async def test_j_an_undecodable_body_fails_rather_than_reading_as_an_empty_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=f"<html>{BODY_MARKER}</html>")

    adapter, _ = build(handler)
    with pytest.raises(AdapterError) as caught:
        await adapter.fetch()

    assert HTTPErrorCategory.INVALID_BODY.value in str(caught.value)
    assert BODY_MARKER not in str(caught.value)


# ---------------------------------------------------------------------------------------
# K — rate limiting
# ---------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_k_the_limiter_lets_the_burst_through_then_paces_the_rest() -> None:
    clock, sleep = FakeClock(), RecordingSleep()
    limiter = RateLimiter(
        requests_per_second=2.0, burst=2, clock=clock, sleep=sleep
    )

    assert await limiter.acquire() == 0.0
    assert await limiter.acquire() == 0.0
    assert sleep.delays == [], "The burst must not be throttled."

    waited = await limiter.acquire()
    assert waited == pytest.approx(0.5), "2 requests/second means a half-second wait."
    assert sleep.delays == [pytest.approx(0.5)]


@pytest.mark.anyio
async def test_k_elapsed_time_refills_the_bucket() -> None:
    clock, sleep = FakeClock(), RecordingSleep()
    limiter = RateLimiter(requests_per_second=4.0, burst=1, clock=clock, sleep=sleep)

    assert await limiter.acquire() == 0.0
    clock.advance(1.0)
    assert await limiter.acquire() == 0.0, "A full second at 4/s refills the bucket."
    assert sleep.delays == []


@pytest.mark.anyio
async def test_k_the_limiter_is_applied_to_every_page() -> None:
    clock, sleep = FakeClock(), RecordingSleep()
    pages = [
        {"jobs": [make_job("EX-1")], "next": f"{BASE_URL}?p=2"},
        {"jobs": [make_job("EX-2")]},
    ]
    served = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        payload = pages[min(served["n"], len(pages) - 1)]
        served["n"] += 1
        return httpx.Response(200, json=payload)

    adapter = _TestAdapter(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        requests_per_second=1.0,
        burst=1,
        clock=clock,
        sleep=sleep,
        rng=FixedRandom(0.0),
    )
    assert len(await adapter.fetch()) == 2
    assert sleep.delays == [pytest.approx(1.0)], "Page two waits for a token."


def test_k_the_limiter_rejects_nonsensical_settings() -> None:
    for kwargs in ({"requests_per_second": 0}, {"requests_per_second": 5, "burst": 0}):
        with pytest.raises(ValueError):
            RateLimiter(**{"requests_per_second": 5.0, **kwargs})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------------------
# L, M, N — sanitization. The assertions that matter most.
# ---------------------------------------------------------------------------------------


def leak_markers() -> list[str]:
    """Everything that must never appear in an error or a log line."""
    return [
        SECRET_KEY,
        SECRET_HEADER,
        BODY_MARKER,
        FULL_URL_MARKER,
        QUERY_MARKER,
        "Authorization",
        BASE_URL,
    ]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "responder",
    [
        pytest.param(lambda request: httpx.Response(500, text=BODY_MARKER), id="500"),
        pytest.param(lambda request: httpx.Response(429, text=BODY_MARKER), id="429"),
        pytest.param(lambda request: httpx.Response(401, text=BODY_MARKER), id="401"),
        pytest.param(lambda request: httpx.Response(404, text=BODY_MARKER), id="404"),
        pytest.param(
            lambda request: httpx.Response(200, text=f"not json {BODY_MARKER}"),
            id="undecodable",
        ),
    ],
)
async def test_lmn_no_failure_leaks_a_url_a_credential_or_a_body(responder: Any) -> None:
    adapter, _ = build(responder, max_retries=1)

    with pytest.raises(AdapterError) as caught:
        await adapter.fetch()

    message = str(caught.value)
    for marker in leak_markers():
        assert marker not in message, f"{marker!r} leaked into the adapter error."
    assert "test-live" in message, "The source name is the one identifier that is safe."


@pytest.mark.anyio
@pytest.mark.parametrize(
    "raiser",
    [
        pytest.param(httpx.ReadTimeout, id="timeout"),
        pytest.param(httpx.ConnectError, id="connect"),
        pytest.param(httpx.ReadError, id="read"),
    ],
)
async def test_lmn_a_transport_exception_never_reaches_the_message(raiser: Any) -> None:
    """httpx embeds the request in its errors, so ``str(exc)`` is never interpolated."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise raiser(f"failure contacting {BASE_URL}?{QUERY_MARKER}={SECRET_KEY}", request=request)

    adapter, _ = build(handler, max_retries=1)
    with pytest.raises(AdapterError) as caught:
        await adapter.fetch()

    message = str(caught.value)
    for marker in leak_markers():
        assert marker not in message


@pytest.mark.anyio
async def test_lmn_nothing_sensitive_reaches_a_log_line(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text=BODY_MARKER)

    adapter, _ = build(handler, max_retries=2)
    with caplog.at_level(logging.DEBUG, logger="eligicore.adapters.live_http"):
        with pytest.raises(AdapterError):
            await adapter.fetch()

    assert caplog.records, "The failure must be visible in the log at all."
    emitted = "\n".join(record.getMessage() for record in caplog.records)
    for marker in leak_markers():
        assert marker not in emitted, f"{marker!r} leaked into a log line."
    assert "outcome=failed" in emitted


@pytest.mark.anyio
async def test_lmn_a_successful_fetch_logs_counts_and_nothing_else(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"jobs": [make_job("EX-1")]})

    adapter, _ = build(handler)
    with caplog.at_level(logging.DEBUG, logger="eligicore.adapters.live_http"):
        await adapter.fetch()

    emitted = "\n".join(record.getMessage() for record in caplog.records)
    for marker in leak_markers():
        assert marker not in emitted
    assert "pages=1" in emitted and "jobs=1" in emitted


@pytest.mark.anyio
async def test_lmn_httpx_own_request_logging_cannot_leak_a_query_string_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Regression: httpx logs the **full URL** at INFO on its own logger.

    Found while auditing this slice for secret leakage. With a key carried as a query
    parameter — which some job APIs require — httpx would write it to the application log
    at the project's default level, through a library the privacy tests had never looked
    at. Constructing a live adapter installs a filter that drops those records (INV-4).
    """
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"jobs": []})

    adapter, _ = build(handler)
    with caplog.at_level(logging.DEBUG, logger="httpx"):
        await adapter.fetch()

    emitted = "\n".join(record.getMessage() for record in caplog.records)
    assert SECRET_KEY not in emitted, "httpx logged the credential-bearing URL."
    assert BASE_URL not in emitted
    assert not any(
        record.getMessage().startswith("HTTP Request:") for record in caplog.records
    )


def test_lmn_the_httpx_log_guard_is_installed_once_and_not_at_import() -> None:
    """Importing must not touch logging; constructing must, and only once."""
    from app.adapters.live_http_adapter import _SuppressHTTPXRequestLine

    httpx_logger = logging.getLogger("httpx")
    installed = [
        f for f in httpx_logger.filters if isinstance(f, _SuppressHTTPXRequestLine)
    ]
    assert len(installed) <= 1, "The guard must be idempotent, not stacked per adapter."

    for _ in range(3):
        build(lambda request: httpx.Response(200, json={"jobs": []}))
    after = [f for f in httpx_logger.filters if isinstance(f, _SuppressHTTPXRequestLine)]
    assert len(after) == 1

    # A warning from httpx must still get through — this is a privacy filter, not a mute.
    guard = after[0]
    record = logging.LogRecord(
        "httpx", logging.WARNING, __file__, 0, "connection pool exhausted", None, None
    )
    assert guard.filter(record) is True


@pytest.mark.anyio
async def test_n_the_response_body_is_never_read_on_a_client_error() -> None:
    """A 4xx body may quote the submitted request back, so it is not even parsed."""
    body = json.dumps({"error": BODY_MARKER, "submitted_key": SECRET_KEY})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text=body)

    adapter, _ = build(handler)
    with pytest.raises(AdapterError) as caught:
        await adapter.fetch()

    assert BODY_MARKER not in str(caught.value)
    assert SECRET_KEY not in str(caught.value)


@pytest.mark.anyio
async def test_the_credential_is_still_actually_sent() -> None:
    """Sanitization must hide the credential from output, not from the request."""
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization")
        seen["query"] = request.url.params.get(QUERY_MARKER)
        return httpx.Response(200, json={"jobs": []})

    adapter, _ = build(handler)
    await adapter.fetch()

    assert seen["auth"] == SECRET_HEADER
    assert seen["query"] == SECRET_KEY


# ---------------------------------------------------------------------------------------
# O, P — the contract, and the offline default
# ---------------------------------------------------------------------------------------


def test_o_the_adapter_contract_is_unchanged() -> None:
    """The new base is a ``JobSourceAdapter``, not a parallel interface (ADR-028 D12)."""
    assert issubclass(LiveHTTPAdapter, JobSourceAdapter)
    assert LiveHTTPAdapter.is_authoritative is False, "ADR-028 D14."
    assert _TestAdapter.is_authoritative is False
    assert sorted(LiveHTTPAdapter.__abstractmethods__) == [
        "initial_request",
        "next_request",
        "parse_page",
    ]


def test_o_the_curated_adapter_is_untouched_by_the_new_base() -> None:
    from app.adapters.curated_adapter import CuratedJobAdapter

    assert not issubclass(CuratedJobAdapter, LiveHTTPAdapter)
    assert CuratedJobAdapter.is_authoritative is True
    assert CuratedJobAdapter.source_name == "curated"


def test_p_no_live_source_is_wired_into_the_default_path() -> None:
    """The base is abstract; concrete sources exist but none is wired in.

    Greenhouse became the first concrete subclass (ADR-028 D5). What this still guards is
    the property that matters: **the seed path remains curated-only**, so a default
    checkout contacts nothing.
    """
    with pytest.raises(TypeError):
        LiveHTTPAdapter()  # type: ignore[abstract]

    from app.adapters.curated_adapter import CuratedJobAdapter
    from app.adapters.greenhouse_adapter import GreenhouseAdapter
    from app.cli import seed_catalogue

    concrete = {
        cls.__name__
        for cls in LiveHTTPAdapter.__subclasses__()
        if not cls.__abstractmethods__ and cls.__module__.startswith("app.")
    }
    assert concrete == {"GreenhouseAdapter"}, f"Unexpected live source adapter: {concrete}"

    # Configured with nothing, it reaches nothing.
    assert GreenhouseAdapter().board_tokens == ()

    referenced = {
        constant
        for constant in seed_catalogue.__code__.co_names
        if isinstance(constant, str)
    }
    assert "CuratedJobAdapter" in referenced
    assert not any(
        "Live" in name or "Greenhouse" in name or "http" in name.lower()
        for name in referenced
    )
    assert CuratedJobAdapter.is_authoritative is True


def test_p_the_ingestion_pipeline_runs_a_live_adapter_unmodified() -> None:
    """Requirement 10: the existing synchronous runner needs no change.

    ``ingest_source`` drives ``asyncio.run(adapter.fetch())`` per adapter. Because a client
    is created **inside** ``fetch`` and closed there, each call gets one bound to the loop
    that is actually running — so the new infrastructure drops into the merged pipeline
    with no edit to ``_fetch_sync`` or ``ingest_all``. This test is the evidence for that
    claim rather than an assertion of it.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.database import Base
    from app.models.ingestion_state import IngestionStatus
    from app.models.job import Job, JobStatus
    from app.services.job_ingestion import ingest_source

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"jobs": [make_job("EX-1"), make_job("EX-2")]})

    adapter, _ = build(handler)

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        outcome = ingest_source(session, adapter)

        assert outcome.jobs_created == 2
        assert outcome.jobs_deactivated == 0, "Non-authoritative: nothing may be closed."
        assert {job.source for job in session.query(Job).all()} == {"test-live"}
        assert all(job.status is JobStatus.ACTIVE for job in session.query(Job).all())

        from app.models.ingestion_state import IngestionState

        state = session.get(IngestionState, "test-live")
        assert state is not None and state.last_status is IngestionStatus.SUCCESS
    Base.metadata.drop_all(engine)


def test_p_an_adapter_failure_reaches_ingestion_as_a_sanitized_adapter_error() -> None:
    """A live failure must arrive at ``ingestion_state.last_error`` carrying no secret."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.database import Base
    from app.models.ingestion_state import IngestionState, IngestionStatus
    from app.services.job_ingestion import ingest_all

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text=BODY_MARKER)

    adapter, _ = build(handler, max_retries=1)

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        outcomes = ingest_all(session, [adapter])

        assert outcomes == [], "A failed source yields no outcome, and does not raise."
        state = session.get(IngestionState, "test-live")
        assert state is not None and state.last_status is IngestionStatus.FAILED
        assert state.last_error is not None
        for marker in leak_markers():
            assert marker not in state.last_error, f"{marker!r} reached ingestion_state."
    Base.metadata.drop_all(engine)


def test_p_constructing_nothing_opens_no_socket() -> None:
    """Importing the module must not create a client. A client is per-fetch, not per-import."""
    import app.adapters.live_http_adapter as module

    assert not hasattr(module, "_shared_client")
    adapter, _ = build(lambda request: httpx.Response(200, json={"jobs": []}))
    assert adapter._client is not None, "This test injected one; nothing was created."

    unwired = _TestAdapter()
    assert unwired._client is None, "Without injection, no client exists until fetch()."


@pytest.mark.anyio
async def test_p_an_injected_client_is_reused_across_pages_and_never_closed() -> None:
    """One client per fetch, shared by every page — not one per request."""
    pages = [{"jobs": [], "next": f"{BASE_URL}?p=2"}, {"jobs": []}]
    served = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        payload = pages[min(served["n"], len(pages) - 1)]
        served["n"] += 1
        return httpx.Response(200, json=payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter, _ = build(handler, client=client)
    await adapter.fetch()

    assert served["n"] == 2
    assert not client.is_closed, "A caller-owned client must survive the fetch."
    await client.aclose()
