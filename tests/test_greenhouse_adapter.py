"""Greenhouse public Job Board adapter.

**Every request goes through an injected ``httpx.MockTransport``. No test here touches a
network, and the transport fails the test if a POST is ever attempted** — the executable
form of "EligiCore never submits an application" (ADR-008, INV-10).

Fixtures follow Greenhouse's documented public response shape. Descriptions are synthetic
and minimal; nothing is copied from a real posting.

The assertions that matter most are the negative ones: that a job titled "Intern" still maps
to ``UNKNOWN``, that no eligibility criterion is invented from prose, and that a board token
never reaches a log line or an error.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.base_adapter import AdapterError, JobSourceAdapter
from app.adapters.greenhouse_adapter import GreenhouseAdapter
from app.adapters.live_http_adapter import LiveHTTPAdapter
from app.database import Base
from app.schemas.candidate import JobType
from app.schemas.job import RawJob

# Obviously synthetic. The token is the thing that must never surface in output.
TOKEN = "exampleorg"
SECOND_TOKEN = "otherorg"
ORG_NAME = "Example Organization"
SECOND_ORG = "Other Organization"
DESCRIPTION = "Synthetic description for testing."
BODY_MARKER = "CONFIDENTIAL-RESPONSE-BODY-MARKER"


def board_payload(name: str = ORG_NAME) -> dict[str, Any]:
    """The documented ``GET /v1/boards/{token}`` shape."""
    return {"name": name, "content": "<p>About us.</p>"}


def job_payload(identifier: int = 123, **overrides: Any) -> dict[str, Any]:
    """The documented list-jobs record under ``content=true``."""
    entry: dict[str, Any] = {
        "id": identifier,
        "internal_job_id": identifier + 1000,
        "title": "Software Engineering Intern",
        "updated_at": "2026-01-14T10:55:28-05:00",
        "requisition_id": "REQ-1",
        "location": {"name": "New York, NY"},
        "absolute_url": f"https://boards.greenhouse.io/{TOKEN}/jobs/{identifier}",
        "language": "en",
        "metadata": None,
        "content": DESCRIPTION,
        "departments": [{"id": 1, "name": "Engineering"}],
        "offices": [{"id": 2, "name": "East Coast"}],
    }
    entry.update(overrides)
    return entry


def jobs_payload(*entries: dict[str, Any]) -> dict[str, Any]:
    return {"jobs": list(entries), "meta": {"total": len(entries)}}


class Recorder:
    """A mock transport that records every request and rejects any non-GET."""

    def __init__(self, routes: dict[str, Any]) -> None:
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.method == "GET", (
            f"the adapter issued a {request.method}; it must only ever read "
            f"(ADR-008 — no application submission)"
        )

        path = request.url.path
        for suffix, response in self.routes.items():
            if path.endswith(suffix):
                if isinstance(response, Exception):
                    raise response
                if isinstance(response, httpx.Response):
                    return response
                return httpx.Response(200, json=response)
        return httpx.Response(404, text="no route")

    @property
    def urls(self) -> list[str]:
        return [str(request.url) for request in self.requests]


def build(
    routes: dict[str, Any],
    *,
    tokens: list[str] | None = None,
    **options: Any,
) -> tuple[GreenhouseAdapter, Recorder]:
    recorder = Recorder(routes)
    adapter = GreenhouseAdapter(
        board_tokens=tokens if tokens is not None else [TOKEN],
        client=httpx.AsyncClient(transport=httpx.MockTransport(recorder)),
        max_retries=options.pop("max_retries", 0),
        requests_per_second=1000.0,
        burst=1000,
        sleep=_no_sleep,
        **options,
    )
    return adapter, recorder


async def _no_sleep(_seconds: float) -> None:
    return None


def one_board(jobs: dict[str, Any] | None = None, name: str = ORG_NAME) -> dict[str, Any]:
    return {
        f"/boards/{TOKEN}/jobs": jobs if jobs is not None else jobs_payload(job_payload()),
        f"/boards/{TOKEN}": board_payload(name),
    }


# ---------------------------------------------------------------------------------------
# A, B, C — what is requested
# ---------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_a_no_board_tokens_makes_zero_requests() -> None:
    """The default checkout stays offline: nothing configured, nothing contacted."""
    adapter, recorder = build(one_board(), tokens=[])
    assert await adapter.fetch() == []
    assert recorder.requests == []


def test_a_an_adapter_with_no_tokens_needs_no_client() -> None:
    assert GreenhouseAdapter().board_tokens == ()


@pytest.mark.anyio
async def test_b_one_board_issues_the_board_request_then_the_jobs_request() -> None:
    adapter, recorder = build(one_board())
    await adapter.fetch()

    assert len(recorder.requests) == 2
    assert recorder.urls[0].endswith(f"/v1/boards/{TOKEN}")
    assert recorder.urls[1].startswith(f"https://boards-api.greenhouse.io/v1/boards/{TOKEN}/jobs")
    assert "content=true" in recorder.urls[1]
    assert all(request.method == "GET" for request in recorder.requests)


@pytest.mark.anyio
async def test_b_the_board_name_is_requested_once_per_fetch() -> None:
    """Cached for the fetch — one board request, not one per job."""
    adapter, recorder = build(
        one_board(jobs_payload(job_payload(1), job_payload(2), job_payload(3)))
    )
    jobs = await adapter.fetch()

    assert len(jobs) == 3
    board_requests = [url for url in recorder.urls if url.endswith(f"/boards/{TOKEN}")]
    assert len(board_requests) == 1


@pytest.mark.anyio
async def test_c_multiple_boards_are_each_fetched_in_order() -> None:
    routes = {
        f"/boards/{TOKEN}/jobs": jobs_payload(job_payload(1)),
        f"/boards/{TOKEN}": board_payload(ORG_NAME),
        f"/boards/{SECOND_TOKEN}/jobs": jobs_payload(job_payload(2)),
        f"/boards/{SECOND_TOKEN}": board_payload(SECOND_ORG),
    }
    adapter, recorder = build(routes, tokens=[TOKEN, SECOND_TOKEN])
    jobs = await adapter.fetch()

    assert len(recorder.requests) == 4
    assert {job.company_name for job in jobs} == {ORG_NAME, SECOND_ORG}
    assert {job.source_job_id for job in jobs} == {"1", "2"}


def test_c_duplicate_tokens_are_collapsed_preserving_order() -> None:
    adapter = GreenhouseAdapter(board_tokens=[TOKEN, SECOND_TOKEN, TOKEN])
    assert adapter.board_tokens == (TOKEN, SECOND_TOKEN)


@pytest.mark.parametrize("bad", ["", "   "])
def test_c_an_empty_board_token_is_rejected_at_construction(bad: str) -> None:
    with pytest.raises(ValueError):
        GreenhouseAdapter(board_tokens=[bad])


# ---------------------------------------------------------------------------------------
# D–I — the mapping
# ---------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_defghi_the_full_mapping_is_exactly_what_greenhouse_supplied() -> None:
    adapter, _ = build(one_board())
    job = (await adapter.fetch())[0]

    assert job.company_name == ORG_NAME                                       # D
    assert job.role_title == "Software Engineering Intern"                    # E
    assert job.source_job_id == "123"                                         # F
    assert job.apply_link == f"https://boards.greenhouse.io/{TOKEN}/jobs/123"  # G
    assert job.description == DESCRIPTION                                     # H
    assert job.location == "New York, NY"                                     # I


@pytest.mark.anyio
async def test_f_the_job_post_id_is_used_not_the_internal_job_id() -> None:
    """`id` addresses the post a human applies to; `internal_job_id` does not."""
    adapter, _ = build(
        one_board(jobs_payload(job_payload(123, internal_job_id=999999)))
    )
    job = (await adapter.fetch())[0]

    assert job.source_job_id == "123"
    assert job.source_job_id != "999999"


@pytest.mark.anyio
async def test_g_the_apply_url_is_preserved_byte_for_byte() -> None:
    """Never reconstructed from the token and id — the source's URL is the canonical one."""
    odd = "https://example.greenhouse.invalid/careers?gh_jid=44444&utm=x"
    adapter, _ = build(one_board(jobs_payload(job_payload(7, absolute_url=odd))))
    assert (await adapter.fetch())[0].apply_link == odd


@pytest.mark.anyio
async def test_d_the_company_name_comes_from_the_board_endpoint_not_the_token() -> None:
    adapter, _ = build(one_board(name="Entirely Different Name"))
    job = (await adapter.fetch())[0]

    assert job.company_name == "Entirely Different Name"
    assert TOKEN not in job.company_name


@pytest.mark.anyio
async def test_d_a_board_without_a_name_fails_rather_than_inventing_one() -> None:
    for payload in ({}, {"name": ""}, {"name": None}, []):
        adapter, _ = build({f"/boards/{TOKEN}": payload})
        with pytest.raises(AdapterError) as caught:
            await adapter.fetch()
        assert "step=board" in str(caught.value)


# ---------------------------------------------------------------------------------------
# J, K, L, M — nothing is inferred
# ---------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_j_employment_type_is_unknown_because_greenhouse_states_none() -> None:
    adapter, _ = build(one_board())
    assert (await adapter.fetch())[0].job_type is JobType.UNKNOWN


@pytest.mark.anyio
@pytest.mark.parametrize(
    "title",
    [
        "Software Engineering Intern",
        "Summer 2027 Internship Program",
        "Full-Time Backend Engineer",
        "Graduate Engineer (Full Time)",
        "Part-time Contractor",
    ],
)
async def test_k_no_title_however_suggestive_changes_the_employment_type(
    title: str,
) -> None:
    """ADR-029 D3, as an executable rule.

    A title is prose. "Intern" appears in "Internal Audit Manager"; a confident wrong
    answer is worse than an honest unknown, so the title is never consulted.
    """
    adapter, _ = build(
        one_board(
            jobs_payload(
                job_payload(
                    1,
                    title=title,
                    content=f"This is a {title} role, full-time, internship, permanent.",
                )
            )
        )
    )
    assert (await adapter.fetch())[0].job_type is JobType.UNKNOWN


@pytest.mark.anyio
async def test_l_no_eligibility_criterion_is_extracted_from_prose() -> None:
    """ADR-028 D9: a fabricated requirement is worse than an absent one."""
    loud = (
        "Requirements: minimum CGPA 8.5/10, B.Tech in Computer Science or IT only, "
        "no active backlogs, graduating 2026-2027. Must know Python, SQL and Docker. "
        "Masters preferred. Apply before 30 November 2026."
    )
    adapter, _ = build(one_board(jobs_payload(job_payload(1, content=loud))))
    job = (await adapter.fetch())[0]

    assert job.min_cgpa is None
    assert job.min_cgpa_scale is None
    assert job.allowed_fields == []
    assert job.min_degree_level is None
    assert job.max_backlogs is None
    assert job.min_grad_year is None
    assert job.max_grad_year is None
    assert job.required_skills == []
    assert job.requirements == {}
    # The text is still carried verbatim as the description — kept, never interpreted.
    assert job.description == loud


@pytest.mark.anyio
async def test_m_no_deadline_is_inferred_even_when_the_text_states_one() -> None:
    adapter, _ = build(
        one_board(
            jobs_payload(
                job_payload(1, content="Applications close 30 November 2026.")
            )
        )
    )
    assert (await adapter.fetch())[0].deadline is None


# ---------------------------------------------------------------------------------------
# N — unmapped fields are dropped, not leaked
# ---------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_n_greenhouse_only_fields_do_not_enter_rawjob() -> None:
    """``RawJob`` forbids extras, so an unmapped field must be dropped deliberately."""
    adapter, _ = build(one_board())
    job = (await adapter.fetch())[0]

    dumped = job.model_dump()
    for unmapped in (
        "internal_job_id", "updated_at", "requisition_id", "language",
        "metadata", "departments", "offices", "first_published", "absolute_url",
        "content", "id", "title",
    ):
        assert unmapped not in dumped, f"{unmapped} leaked into RawJob"
    assert set(dumped) == set(RawJob.model_fields)


@pytest.mark.anyio
async def test_n_an_unexpected_extra_field_does_not_break_the_mapping() -> None:
    adapter, _ = build(
        one_board(jobs_payload(job_payload(1, brand_new_field={"x": 1})))
    )
    assert len(await adapter.fetch()) == 1


# ---------------------------------------------------------------------------------------
# O, P, Q, R, S — awkward payloads
# ---------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_o_a_duplicate_job_id_within_one_board_is_collapsed() -> None:
    adapter, _ = build(
        one_board(jobs_payload(job_payload(5), job_payload(5), job_payload(6)))
    )
    jobs = await adapter.fetch()

    assert [job.source_job_id for job in jobs] == ["5", "6"]


@pytest.mark.anyio
async def test_o_the_same_id_on_two_boards_is_not_cross_deduplicated() -> None:
    """Two boards listing one id are two attributed rows; ingestion decides, not the adapter."""
    routes = {
        f"/boards/{TOKEN}/jobs": jobs_payload(job_payload(9)),
        f"/boards/{TOKEN}": board_payload(ORG_NAME),
        f"/boards/{SECOND_TOKEN}/jobs": jobs_payload(job_payload(9)),
        f"/boards/{SECOND_TOKEN}": board_payload(SECOND_ORG),
    }
    adapter, _ = build(routes, tokens=[TOKEN, SECOND_TOKEN])
    jobs = await adapter.fetch()

    assert len(jobs) == 2
    assert {job.company_name for job in jobs} == {ORG_NAME, SECOND_ORG}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "broken",
    [
        pytest.param("not-a-dict", id="string"),
        pytest.param(42, id="number"),
        pytest.param({"id": None}, id="null-id"),
        pytest.param({"id": True}, id="bool-id"),
        pytest.param({"title": "No id at all"}, id="missing-id"),
        pytest.param({"id": 1, "title": "x" * 400}, id="title-too-long"),
    ],
)
async def test_p_a_malformed_record_is_skipped_and_the_good_ones_survive(
    broken: Any,
) -> None:
    adapter, _ = build(one_board(jobs_payload(broken, job_payload(77))))
    jobs = await adapter.fetch()

    assert [job.source_job_id for job in jobs] == ["77"]


@pytest.mark.anyio
async def test_q_an_empty_job_list_is_a_valid_empty_result_not_a_failure() -> None:
    adapter, _ = build(one_board(jobs_payload()))
    assert await adapter.fetch() == []


@pytest.mark.anyio
async def test_q_a_structurally_invalid_jobs_response_fails_rather_than_reading_as_empty()  -> None:
    """An unreadable response must not be indistinguishable from a board with no roles."""
    for payload in ({"meta": {"total": 0}}, {"jobs": "nope"}, {"jobs": None}, []):
        adapter, _ = build({f"/boards/{TOKEN}/jobs": payload, f"/boards/{TOKEN}": board_payload()})
        with pytest.raises(AdapterError) as caught:
            await adapter.fetch()
        assert "step=jobs" in str(caught.value)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("overrides", "field", "expected"),
    [
        pytest.param({"content": None}, "description", "", id="null-content"),
        pytest.param({}, "description", DESCRIPTION, id="content-present"),
        pytest.param({"location": None}, "location", None, id="null-location"),
        pytest.param({"location": {}}, "location", None, id="location-without-name"),
        pytest.param({"absolute_url": None}, "apply_link", None, id="null-url"),
    ],
)
async def test_rs_missing_optional_fields_fall_back_without_inventing_anything(
    overrides: dict[str, Any], field: str, expected: Any
) -> None:
    adapter, _ = build(one_board(jobs_payload(job_payload(1, **overrides))))
    jobs = await adapter.fetch()

    assert len(jobs) == 1
    assert getattr(jobs[0], field) == expected


# ---------------------------------------------------------------------------------------
# T–AA — failures
# ---------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_t_a_board_name_request_failure_fails_the_fetch() -> None:
    adapter, _ = build({f"/boards/{TOKEN}": httpx.Response(500)})
    with pytest.raises(AdapterError):
        await adapter.fetch()


@pytest.mark.anyio
async def test_u_a_jobs_request_failure_fails_the_fetch() -> None:
    adapter, _ = build(
        {f"/boards/{TOKEN}/jobs": httpx.Response(500), f"/boards/{TOKEN}": board_payload()}
    )
    with pytest.raises(AdapterError):
        await adapter.fetch()


@pytest.mark.anyio
async def test_v_one_board_failing_fails_the_whole_fetch_rather_than_half_reporting() -> None:
    """The deliberate choice, and the reason for it.

    ``fetch`` has one return channel: jobs, or an ``AdapterError``. Returning the healthy
    board's jobs would have ingestion record SUCCESS for a run that silently lost a board —
    indistinguishable from that board genuinely having no openings. Failing keeps the two
    apart, and because the source is non-authoritative nothing is closed as a result.
    """
    routes = {
        f"/boards/{TOKEN}/jobs": jobs_payload(job_payload(1)),
        f"/boards/{TOKEN}": board_payload(ORG_NAME),
        f"/boards/{SECOND_TOKEN}": httpx.Response(503),
    }
    adapter, recorder = build(routes, tokens=[TOKEN, SECOND_TOKEN])

    with pytest.raises(AdapterError):
        await adapter.fetch()

    # The healthy board really was fetched first — the failure is the second board's.
    assert any(url.endswith(f"/boards/{TOKEN}/jobs?content=true") for url in recorder.urls)


@pytest.mark.anyio
@pytest.mark.parametrize("status", [404, 429, 500, 503])
async def test_wxy_http_errors_surface_as_adapter_errors(status: int) -> None:
    adapter, _ = build(
        {f"/boards/{TOKEN}": httpx.Response(status, text=BODY_MARKER)}
    )
    with pytest.raises(AdapterError) as caught:
        await adapter.fetch()
    assert BODY_MARKER not in str(caught.value)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(httpx.ReadTimeout("slow", request=None), id="timeout"),       # Z
        pytest.param(httpx.ConnectError("refused", request=None), id="transport"),  # AA
    ],
)
async def test_za_timeouts_and_transport_failures_surface_as_adapter_errors(
    failure: Exception,
) -> None:
    adapter, _ = build({f"/boards/{TOKEN}": failure})
    with pytest.raises(AdapterError):
        await adapter.fetch()


# ---------------------------------------------------------------------------------------
# AB — sanitization. The assertions that matter most.
# ---------------------------------------------------------------------------------------


def leak_markers() -> list[str]:
    return [TOKEN, SECOND_TOKEN, BODY_MARKER, "boards-api.greenhouse.io", "content=true"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "routes",
    [
        pytest.param({f"/boards/{TOKEN}": httpx.Response(500, text=BODY_MARKER)}, id="board-500"),
        pytest.param({f"/boards/{TOKEN}": httpx.Response(404, text=BODY_MARKER)}, id="board-404"),
        pytest.param({f"/boards/{TOKEN}": {"no_name": BODY_MARKER}}, id="board-nameless"),
        pytest.param(
            {f"/boards/{TOKEN}/jobs": httpx.Response(429, text=BODY_MARKER),
             f"/boards/{TOKEN}": board_payload()},
            id="jobs-429",
        ),
        pytest.param(
            {f"/boards/{TOKEN}/jobs": {"jobs": BODY_MARKER},
             f"/boards/{TOKEN}": board_payload()},
            id="jobs-malformed",
        ),
    ],
)
async def test_ab_no_failure_leaks_the_token_the_url_or_the_body(
    routes: dict[str, Any],
) -> None:
    adapter, _ = build(routes)

    with pytest.raises(AdapterError) as caught:
        await adapter.fetch()

    message = str(caught.value)
    for marker in leak_markers():
        assert marker not in message, f"{marker!r} leaked into the adapter error"
    assert "greenhouse" in message


@pytest.mark.anyio
async def test_ab_nothing_sensitive_reaches_a_log_line(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_title = "SECRET-JOB-TITLE-MARKER"
    adapter, _ = build(
        one_board(
            jobs_payload(
                {"id": None, "title": secret_title, "content": BODY_MARKER},
                job_payload(1, title=secret_title, content=BODY_MARKER),
            )
        )
    )
    with caplog.at_level(logging.DEBUG):
        await adapter.fetch()

    emitted = "\n".join(record.getMessage() for record in caplog.records)
    assert emitted, "the skipped record must be visible as a count at all"
    for marker in [*leak_markers(), secret_title]:
        assert marker not in emitted, f"{marker!r} leaked into a log line"
    assert "skipped=1" in emitted


@pytest.mark.anyio
async def test_ab_a_successful_fetch_logs_counts_only(
    caplog: pytest.LogCaptureFixture,
) -> None:
    adapter, _ = build(one_board())
    with caplog.at_level(logging.DEBUG):
        await adapter.fetch()

    emitted = "\n".join(record.getMessage() for record in caplog.records)
    for marker in leak_markers():
        assert marker not in emitted
    assert "boards=1" in emitted and "jobs=1" in emitted


# ---------------------------------------------------------------------------------------
# AC — read-only, no application endpoint
# ---------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_ac_only_public_get_endpoints_are_called() -> None:
    """The transport asserts GET; this pins the exact URL shapes as well."""
    adapter, recorder = build(one_board())
    await adapter.fetch()

    for request in recorder.requests:
        assert request.method == "GET"
        path = request.url.path
        assert path in (f"/v1/boards/{TOKEN}", f"/v1/boards/{TOKEN}/jobs")
        # The application-submission and application-question surfaces, never touched.
        assert "questions" not in str(request.url)
        assert not path.endswith("/applications")
        assert request.content == b""


def test_ac_the_adapter_contains_no_post_and_no_application_endpoint() -> None:
    import pathlib

    source = (
        pathlib.Path(__file__).resolve().parent.parent
        / "app" / "adapters" / "greenhouse_adapter.py"
    ).read_text(encoding="utf-8")

    for forbidden in (".post(", "POST ", "applications", "questions=true"):
        assert forbidden not in source, f"{forbidden!r} has no business in this adapter"


# ---------------------------------------------------------------------------------------
# Contract and reuse
# ---------------------------------------------------------------------------------------


def test_the_source_name_is_stable_and_carries_no_runtime_data() -> None:
    """Changing this orphans every persisted Greenhouse row, so it is pinned."""
    assert GreenhouseAdapter.source_name == "greenhouse"
    assert GreenhouseAdapter(board_tokens=[TOKEN]).source_name == "greenhouse"
    for leaked in (TOKEN, ORG_NAME.lower(), "boards-api"):
        assert leaked not in GreenhouseAdapter.source_name


def test_the_adapter_is_non_authoritative() -> None:
    assert GreenhouseAdapter.is_authoritative is False
    assert GreenhouseAdapter(board_tokens=[TOKEN]).is_authoritative is False


def test_it_builds_on_the_shared_http_foundation_rather_than_its_own() -> None:
    assert issubclass(GreenhouseAdapter, LiveHTTPAdapter)
    assert issubclass(GreenhouseAdapter, JobSourceAdapter)

    import pathlib

    source = (
        pathlib.Path(__file__).resolve().parent.parent
        / "app" / "adapters" / "greenhouse_adapter.py"
    ).read_text(encoding="utf-8")
    # No duplicated transport machinery: retries, limiter and client are all inherited.
    for duplicated in ("AsyncClient(", "max_retries=", "RateLimiter(", "asyncio.sleep"):
        assert duplicated not in source, f"{duplicated!r} duplicates LiveHTTPAdapter"


def test_no_board_token_is_hard_coded_anywhere_in_the_adapter() -> None:
    import pathlib

    source = (
        pathlib.Path(__file__).resolve().parent.parent
        / "app" / "adapters" / "greenhouse_adapter.py"
    ).read_text(encoding="utf-8")
    assert "board_tokens: list[str] | tuple[str, ...] = ()" in source


# ---------------------------------------------------------------------------------------
# AD, AE, AF — the real ingestion pipeline
# ---------------------------------------------------------------------------------------


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        yield db
    Base.metadata.drop_all(engine)


def test_ad_the_real_ingestion_service_accepts_the_adapter(session: Session) -> None:
    from app.models.job import Job, JobStatus
    from app.services.job_ingestion import ingest_source

    adapter, _ = build(one_board(jobs_payload(job_payload(1), job_payload(2))))
    outcome = ingest_source(session, adapter)

    assert outcome.source == "greenhouse"
    assert outcome.jobs_created == 2
    assert outcome.jobs_deactivated == 0

    stored = session.query(Job).all()
    assert {job.source for job in stored} == {"greenhouse"}
    assert {job.job_type for job in stored} == {JobType.UNKNOWN}
    assert all(job.status is JobStatus.ACTIVE for job in stored)
    assert {job.company_name for job in stored} == {ORG_NAME}


def test_ae_re_ingesting_the_same_board_updates_rather_than_duplicates(
    session: Session,
) -> None:
    from app.models.job import Job
    from app.services.job_ingestion import ingest_source

    for _ in range(3):
        adapter, _ = build(one_board(jobs_payload(job_payload(1))))
        ingest_source(session, adapter)

    assert session.query(Job).count() == 1


def test_af_a_job_disappearing_is_not_closed_because_the_source_is_not_authoritative(
    session: Session,
) -> None:
    """ADR-028 D14: absence from a non-authoritative source proves nothing."""
    from app.models.job import Job, JobStatus
    from app.services.job_ingestion import ingest_source

    first, _ = build(one_board(jobs_payload(job_payload(1), job_payload(2))))
    ingest_source(session, first)

    second, _ = build(one_board(jobs_payload(job_payload(1))))
    outcome = ingest_source(session, second)

    assert outcome.jobs_deactivated == 0
    assert session.query(Job).count() == 2
    assert all(job.status is JobStatus.ACTIVE for job in session.query(Job).all())


def test_a_failed_board_is_recorded_as_failed_not_as_an_empty_success(
    session: Session,
) -> None:
    """The distinction ingestion needs: a real failure versus a board with no roles."""
    from app.models.ingestion_state import IngestionState, IngestionStatus
    from app.services.job_ingestion import ingest_all

    failing, _ = build({f"/boards/{TOKEN}": httpx.Response(503)})
    assert ingest_all(session, [failing]) == []

    state = session.get(IngestionState, "greenhouse")
    assert state is not None
    assert state.last_status is IngestionStatus.FAILED
    assert state.last_error is not None
    for marker in leak_markers():
        assert marker not in state.last_error


def test_an_empty_board_is_recorded_as_a_successful_empty_run(session: Session) -> None:
    from app.models.ingestion_state import IngestionState, IngestionStatus
    from app.services.job_ingestion import ingest_source

    adapter, _ = build(one_board(jobs_payload()))
    outcome = ingest_source(session, adapter)

    assert outcome.jobs_seen == 0 and outcome.jobs_created == 0
    state = session.get(IngestionState, "greenhouse")
    assert state is not None and state.last_status is IngestionStatus.SUCCESS


# ---------------------------------------------------------------------------------------
# Scope
# ---------------------------------------------------------------------------------------


def test_only_greenhouse_was_added_to_the_adapter_package() -> None:
    import pathlib

    adapters = {
        path.name
        for path in (pathlib.Path(__file__).resolve().parent.parent / "app" / "adapters")
        .glob("*.py")
    }
    assert adapters == {
        "__init__.py",
        "base_adapter.py",
        "curated_adapter.py",
        "greenhouse_adapter.py",
        "live_http_adapter.py",
    }


def test_the_curated_catalogue_is_untouched_and_still_states_real_types() -> None:
    import json
    import pathlib

    entries = json.loads(
        (pathlib.Path(__file__).resolve().parent.parent / "app" / "data" / "curated_jobs.json")
        .read_text(encoding="utf-8")
    )
    assert len(entries) == 40
    assert {entry["job_type"] for entry in entries} == {"INTERNSHIP", "FULL_TIME"}
