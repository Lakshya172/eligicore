"""Reusable HTTP foundation for live job-source adapters (ADR-028 D13).

**Infrastructure only. This module knows nothing about any job source.** No endpoint, no
field name, no pagination convention and no vendor's error shape appears here — that is the
point. A concrete adapter supplies three hooks and inherits the parts every live source
would otherwise re-implement badly: bounded retries, backoff with jitter, an explicit
timeout, rate limiting, client reuse, and error messages that cannot leak a credential.

**Why a base class with no subclass yet.** ``standards/code_quality.md`` §3 forbids exactly
that, so the exception is deliberate and recorded: ADR-028 D5 names three concrete sources
(Greenhouse, Lever, Ashby) as the initial implementation targets, and ADR-028 D13 authorizes
this shared infrastructure as its own slice ahead of them. The alternative — writing the
first adapter with all of this inlined and extracting it when the second arrived — would
mean the first source's shape leaks into the abstraction, which is the failure
``base_adapter.py`` was written to avoid.

**Nothing here runs by default.** No module imports this one, the curated adapter is
untouched, and a default checkout still makes zero outbound requests. Constructing a
subclass is what opens a socket, and no subclass exists yet.

Privacy: a live source's URL may carry an API key in a query string and its response body
may quote anything at all, so **neither ever reaches a log line, an exception message or an
:class:`~app.adapters.base_adapter.AdapterError`** (INV-4, ADR-028 § Security and privacy
impact). Diagnostics are confined to source name, error category, HTTP status, page number,
attempt count and timings.
"""

from __future__ import annotations

import asyncio
import enum
import json
import logging
import random
import time
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from app.adapters.base_adapter import AdapterError, JobSourceAdapter
from app.schemas.job import RawJob

logger = logging.getLogger("eligicore.adapters.live_http")

#: Statuses worth trying again. A 429 and a 5xx may both succeed on a later attempt; every
#: other 4xx is a statement about the request itself, and repeating it repeats the answer.
#: Mirrors the rule the Gemini provider already proved (``app/ai/providers/gemini.py``).
_RETRYABLE_STATUSES = frozenset({429})


class _SuppressHTTPXRequestLine(logging.Filter):
    """Drops httpx's own ``HTTP Request: GET <url> "200 OK"`` records.

    **This is a privacy control, not noise reduction (INV-4).** httpx logs every request's
    *full* URL on the ``httpx`` logger at INFO, and a job API may require its key as a
    query parameter — so with a live adapter configured and the application's own default
    log level, the credential would be written to the application log by a library nobody
    thought to audit. The Gemini provider never hits this because it puts its key in a
    header; a job source does not get to make that choice for us.

    Dropping only these records leaves httpx's warnings and errors intact.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return not record.getMessage().startswith("HTTP Request:")


def _install_httpx_log_guard() -> None:
    """Attach the request-line filter to the ``httpx`` logger, once.

    Called when a live adapter is **constructed**, never at import. A checkout that never
    builds one — which is every checkout today — has its logging configuration untouched,
    and the guard is in place before any live adapter can issue a request.
    """
    httpx_logger = logging.getLogger("httpx")
    if any(isinstance(existing, _SuppressHTTPXRequestLine) for existing in httpx_logger.filters):
        return
    httpx_logger.addFilter(_SuppressHTTPXRequestLine())


class HTTPErrorCategory(str, enum.Enum):
    """What went wrong, at a granularity that is safe to log and to return.

    A category is the most detail an adapter error may carry about a failure beyond the
    status code: the alternative — a provider's own message — is exactly the string that
    might quote the submitted URL or the response body back (INV-4).
    """

    TIMEOUT = "timeout"
    TRANSPORT = "transport"
    SERVER_ERROR = "server_error"
    RATE_LIMITED = "rate_limited"
    CLIENT_ERROR = "client_error"
    INVALID_BODY = "invalid_body"
    PAGINATION = "pagination"


@dataclass(frozen=True, slots=True)
class PageRequest:
    """One HTTP request for one page of results.

    Deliberately not an ``httpx.Request``: a concrete adapter should describe *what* to ask
    for, while this module decides how the asking is done — timeout, retries, limiter.

    Attributes:
        url: Absolute URL, without credentials. **Never logged** — a query string is a
            documented place for an API key to hide.
        params: Query parameters, sent separately so a subclass never has to build a query
            string by hand. **Never logged.**
        headers: Request headers. **Prefer this for a credential** — a query string is
            the documented place for a key to end up somewhere it should not be. Where a
            source insists on a key as a parameter, :func:`_install_httpx_log_guard`
            is what keeps it out of the log. **Never logged.**
    """

    url: str
    params: Mapping[str, str] | None = None
    headers: Mapping[str, str] | None = None


class RateLimiter:
    """An in-process token bucket, one per adapter instance.

    **This is not quota accounting and must not be mistaken for it.** It holds no state
    across processes, writes nothing to disk or to the database, and forgets everything on
    restart. Its only job is to stop *this* process hammering a source inside one run.

    A source with a daily, monthly or lifetime quota needs durable accounting, which
    ADR-028 leaves open as OD-3. Keeping this class free of persistence is what allows that
    to be added later beside it rather than untangled from it.

    Time and sleeping are injected, never called directly, so the behaviour is testable
    without a real clock (``standards/code_quality.md`` §6).
    """

    def __init__(
        self,
        *,
        requests_per_second: float,
        burst: int = 1,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if requests_per_second <= 0:
            raise ValueError("requests_per_second must be positive.")
        if burst < 1:
            raise ValueError("burst must be at least 1.")

        self._rate = requests_per_second
        self._capacity = float(burst)
        self._tokens = float(burst)
        self._clock = clock
        self._sleep = sleep
        self._updated_at = clock()

    async def acquire(self) -> float:
        """Consume one token, waiting if the bucket is empty.

        Returns:
            Seconds actually waited — 0.0 when a token was available. Returned rather than
            logged so a caller can report it as a count, and so a test can assert the rate
            was enforced without reaching into private state.
        """
        self._refill()
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return 0.0

        wait = (1.0 - self._tokens) / self._rate
        await self._sleep(wait)
        self._refill()
        # The refill above is credited from the clock, which a fake clock in a test may not
        # have advanced. Spend the token unconditionally: having waited the computed time,
        # this call has paid for it either way.
        self._tokens = max(0.0, self._tokens - 1.0)
        return wait

    def _refill(self) -> None:
        now = self._clock()
        elapsed = max(0.0, now - self._updated_at)
        self._updated_at = now
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)


class LiveHTTPAdapter(JobSourceAdapter, ABC):
    """Base class for a job source reached over HTTP.

    A subclass sets :attr:`~app.adapters.base_adapter.JobSourceAdapter.source_name` and
    implements three hooks — :meth:`initial_request`, :meth:`parse_page` and
    :meth:`next_request`. Everything else is inherited.

    **``is_authoritative`` stays ``False`` and a subclass should think hard before changing
    it** (ADR-028 D14). A live API returns a page, a filtered query or a rate-limited
    window; a job missing from one fetch is not evidence the posting is gone, and treating
    it as such would close the catalogue on the first short page.
    """

    source_name: str = "live-http"
    is_authoritative: bool = False

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 15.0,
        max_retries: int = 2,
        max_pages: int = 100,
        requests_per_second: float = 5.0,
        burst: int = 5,
        backoff_initial_seconds: float = 0.5,
        backoff_max_seconds: float = 8.0,
        jitter_ratio: float = 0.25,
        rng: random.Random | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Configure the transport behaviour.

        Every value is a constructor argument with a conservative default, and **no new
        environment variable is introduced** (ADR-028 § Operational impact): the defaults
        below are transport hygiene, not policy, and the policy questions — cadence, quota,
        credentials — are owner decisions this slice deliberately does not answer.

        Args:
            client: A caller-owned client to reuse. When given it is **never closed here**,
                because the owner may still need it. When omitted, one client is created
                per :meth:`fetch` and shared by every page and every retry within that
                fetch, then closed — a client per request is the thing this avoids.
            timeout_seconds: Applied explicitly to each request, so an injected client's
                own default cannot quietly govern.
            max_retries: Additional attempts after the first. ``0`` disables retrying. An
                unbounded loop against a rate-limited API is a defect, not resilience.
            max_pages: Hard stop on pagination. A source that keeps returning a next-page
                cursor would otherwise loop forever; failing loudly beats spinning.
            requests_per_second: Token refill rate for this source's limiter.
            burst: Bucket capacity.
            backoff_initial_seconds: First backoff, doubled per attempt.
            backoff_max_seconds: Cap on the doubling.
            jitter_ratio: Fraction of the delay that may be shaved off at random, in
                ``[0, 1)``. Spreads retries so repeated failures do not resynchronize.
            rng: Injected randomness, so backoff is reproducible under test.
            sleep: Injected, so a test never actually waits.
            clock: Injected, for the limiter and for duration reporting.
        """
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")
        if max_retries < 0:
            raise ValueError("max_retries must not be negative.")
        if max_pages < 1:
            raise ValueError("max_pages must be at least 1.")
        if not 0.0 <= jitter_ratio < 1.0:
            raise ValueError("jitter_ratio must be in [0, 1).")
        if backoff_initial_seconds < 0 or backoff_max_seconds < backoff_initial_seconds:
            raise ValueError("backoff bounds must satisfy 0 <= initial <= max.")

        _install_httpx_log_guard()

        self._client = client
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._max_pages = max_pages
        self._backoff_initial = backoff_initial_seconds
        self._backoff_max = backoff_max_seconds
        self._jitter_ratio = jitter_ratio
        self._rng = rng if rng is not None else random.Random()
        self._sleep = sleep
        self._clock = clock
        self._limiter = RateLimiter(
            requests_per_second=requests_per_second,
            burst=burst,
            clock=clock,
            sleep=sleep,
        )

    # -- hooks a concrete adapter implements ---------------------------------------------

    @abstractmethod
    def initial_request(self) -> PageRequest:
        """The request for the first page.

        Returns:
            Where to start. Credentials, if the source needs any, belong in
            :attr:`PageRequest.headers`.
        """

    @abstractmethod
    def parse_page(self, payload: Any, page_number: int) -> list[RawJob]:
        """Translate one decoded page into the common shape.

        Runs inside the fetch, so raising here fails the whole fetch — which is correct for
        a structurally unexpected page. A **single** malformed record among good ones should
        instead be skipped and counted, following ``CuratedJobAdapter``: one bad entry must
        not discard the rest, and the entry itself is never logged (INV-4).

        Args:
            payload: The decoded body, as :meth:`decode_response` produced it. Typed
                ``Any`` because a page's shape is the source's business, not this layer's.
            page_number: 1-based, for counting only.

        Returns:
            The jobs on this page.
        """

    @abstractmethod
    def next_request(
        self, payload: Any, previous: PageRequest, page_number: int
    ) -> PageRequest | None:
        """The request for the page after this one, or ``None`` when finished.

        Returning ``None`` is how a fetch ends normally. Returning a request identical to
        ``previous`` forever is caught by ``max_pages`` rather than hanging.
        """

    # -- the template ---------------------------------------------------------------------

    async def fetch(self) -> list[RawJob]:
        """Fetch every page and return the jobs from all of them.

        **A failure on any page fails the whole fetch.** Pages already parsed are discarded
        rather than returned, because a partial catalogue that looks complete is the worst
        possible outcome: ingestion cannot tell it apart from a real result, and for an
        authoritative source it would read as evidence that the missing jobs had closed.
        Failing honestly is the behaviour ``is_authoritative`` and this method are both
        built around (ADR-028 D14, dossier §10.2).

        Returns:
            Every job across every page, in page order.

        Raises:
            AdapterError: Any request failed after its retries, a body could not be decoded,
                a page could not be parsed, or pagination exceeded ``max_pages``. The
                message carries no URL, no header, no body and no credential.
        """
        started = self._clock()
        client, owned = self._resolve_client()
        jobs: list[RawJob] = []
        page_number = 0

        try:
            request: PageRequest | None = self.initial_request()
            while request is not None:
                page_number += 1
                if page_number > self._max_pages:
                    raise AdapterError(
                        f"{self.source_name} fetch failed: "
                        f"category={HTTPErrorCategory.PAGINATION.value} "
                        f"pages={self._max_pages} reason=page_limit_exceeded."
                    )

                await self._limiter.acquire()
                payload = await self._request_page(client, request, page_number)
                jobs.extend(self.parse_page(payload, page_number))
                request = self.next_request(payload, request, page_number)
        except AdapterError:
            logger.warning(
                "live_fetch source=%s outcome=failed pages_attempted=%d jobs_discarded=%d",
                self.source_name,
                page_number,
                len(jobs),
            )
            raise
        finally:
            if owned:
                await client.aclose()

        logger.info(
            "live_fetch source=%s outcome=success pages=%d jobs=%d duration_ms=%d",
            self.source_name,
            page_number,
            len(jobs),
            int((self._clock() - started) * 1000),
        )
        return jobs

    def decode_response(self, response: httpx.Response) -> Any:
        """Decode one successful response body. JSON by default.

        Overridable for a source that serves something else. The default raises rather than
        returning ``None`` on unparseable content: silently treating a broken body as an
        empty page would look like a source with no jobs, which for an authoritative source
        is a closure signal (``standards/code_quality.md`` §8).

        Raises:
            AdapterError: The body was not valid JSON. The message carries the decode
                position, never the content.
        """
        try:
            return response.json()
        except (json.JSONDecodeError, ValueError, UnicodeDecodeError) as exc:
            detail = ""
            if isinstance(exc, json.JSONDecodeError):
                detail = f" line={exc.lineno} column={exc.colno}"
            raise AdapterError(
                f"{self.source_name} fetch failed: "
                f"category={HTTPErrorCategory.INVALID_BODY.value}{detail}."
            ) from exc

    # -- internals -------------------------------------------------------------------------

    def _resolve_client(self) -> tuple[httpx.AsyncClient, bool]:
        """The client to use, and whether this fetch owns it.

        One client per fetch, shared across every page and every retry. An injected client
        is reused and left open; a created one is closed in :meth:`fetch`'s ``finally``.

        Creating the client here rather than in ``__init__`` is what keeps this compatible
        with the existing synchronous ingestion runner, which calls ``asyncio.run`` once per
        adapter: a client built under one event loop holds connections that are useless to
        the next. Binding the client's lifetime to a single ``fetch`` sidesteps that without
        the ingestion service changing at all.
        """
        if self._client is not None:
            return self._client, False
        return httpx.AsyncClient(timeout=self._timeout), True

    def backoff_delay(self, attempt: int) -> float:
        """Seconds to wait before ``attempt`` (0-based), exponential with jitter.

        The delay is ``min(initial * 2**attempt, max)``, reduced by up to ``jitter_ratio``
        of itself. It is therefore always within ``[base * (1 - jitter_ratio), base]`` and
        never exceeds ``backoff_max_seconds`` — bounded by construction, which is what makes
        it assertable in a test rather than merely plausible.
        """
        base = min(self._backoff_initial * (2**attempt), self._backoff_max)
        return base * (1.0 - self._jitter_ratio * self._rng.random())

    async def _request_page(
        self, client: httpx.AsyncClient, request: PageRequest, page_number: int
    ) -> Any:
        """Request one page, retrying only what a retry could plausibly fix.

        Iterative, not recursive, and it never re-enters :meth:`fetch`: a retry repeats one
        HTTP request, not the pagination walk, so a retried page cannot duplicate the jobs
        from the pages before it.
        """
        last_category = HTTPErrorCategory.TRANSPORT
        last_status: int | None = None

        for attempt in range(self._max_retries + 1):
            try:
                response = await self._send(client, request)
            except httpx.TimeoutException as exc:
                last_category, last_status, error = HTTPErrorCategory.TIMEOUT, None, exc
            except httpx.HTTPError as exc:
                # Deliberately not str(exc): an httpx error can echo the request URL, and a
                # URL is a documented hiding place for an API key.
                last_category, last_status, error = HTTPErrorCategory.TRANSPORT, None, exc
            else:
                status = response.status_code
                if status < 400:
                    return self.decode_response(response)

                last_status = status
                last_category = self._categorize(status)
                if last_category is HTTPErrorCategory.CLIENT_ERROR:
                    # The same request produces the same rejection. The body may quote the
                    # submitted content back, so it is neither read nor included.
                    raise self._failure(last_category, status, page_number, attempt + 1)
                error = None

            if attempt < self._max_retries:
                logger.warning(
                    "live_fetch source=%s page=%d attempt=%d/%d outcome=retryable "
                    "category=%s status=%s",
                    self.source_name,
                    page_number,
                    attempt + 1,
                    self._max_retries + 1,
                    last_category.value,
                    last_status if last_status is not None else "none",
                )
                await self._sleep(self.backoff_delay(attempt))

        raise self._failure(
            last_category, last_status, page_number, self._max_retries + 1
        ) from error

    async def _send(
        self, client: httpx.AsyncClient, request: PageRequest
    ) -> httpx.Response:
        """Perform one HTTP request with an explicit timeout.

        Query parameters are **merged into** the URL rather than passed alongside it.
        httpx's ``params=`` argument *replaces* whatever query the URL already carried, so
        a next-page URL of ``.../postings?cursor=2`` fetched with an auth parameter would
        silently lose its cursor and return page one again — pagination would loop until
        ``max_pages`` and the catalogue would be wrong rather than the run being loud.
        Merging is what lets a subclass return a source's own opaque next-page URL from
        :meth:`next_request` and have it work.
        """
        url = httpx.URL(request.url)
        if request.params:
            url = url.copy_merge_params(dict(request.params))

        return await client.get(
            url,
            headers=dict(request.headers) if request.headers else None,
            timeout=self._timeout,
        )

    @staticmethod
    def _categorize(status: int) -> HTTPErrorCategory:
        """Classify an error status. Only the first two are worth retrying."""
        if status >= 500:
            return HTTPErrorCategory.SERVER_ERROR
        if status in _RETRYABLE_STATUSES:
            return HTTPErrorCategory.RATE_LIMITED
        return HTTPErrorCategory.CLIENT_ERROR

    def _failure(
        self,
        category: HTTPErrorCategory,
        status: int | None,
        page_number: int,
        attempts: int,
    ) -> AdapterError:
        """Build the only error this module lets out.

        **Every component is safe by construction.** The source name is a constant, the
        category is a fixed enum, the status is an integer, and the counts are integers.
        Nothing derived from the URL, the headers, the response body or an httpx message
        can reach this string (INV-4, ADR-028 § Security and privacy impact).
        """
        status_text = str(status) if status is not None else "none"
        return AdapterError(
            f"{self.source_name} fetch failed: category={category.value} "
            f"status={status_text} page={page_number} attempts={attempts}."
        )
