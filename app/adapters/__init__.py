"""Job source adapters.

Every source — a curated file today, a portal API later — implements the same interface
and returns the same normalized shape. Adding a source is one new class; the eligibility
and matching engines never change (ADR-005, INV-6).

**Adapters must operate within their source's Terms of Service.** An adapter requiring
CAPTCHA solving, anti-bot circumvention or an authentication bypass is out of scope
permanently (ADR-008, INV-10).

**Two ways to write one.**

* Subclass :class:`~app.adapters.base_adapter.JobSourceAdapter` directly when the source is
  not HTTP — the curated dataset reads a file, and needs none of the machinery below.
* Subclass :class:`~app.adapters.live_http_adapter.LiveHTTPAdapter` for a source reached
  over HTTP. It supplies the transport concerns every live source shares — one client per
  fetch, an explicit timeout, bounded retries with jittered backoff, in-process rate
  limiting, pagination, and errors that cannot carry a URL, a header or a response body
  into a log line (ADR-028 D13). A subclass supplies three hooks: where to start, how to
  read a page, and where the next page is.

**No live source exists yet.** ``LiveHTTPAdapter`` is abstract and has no concrete
subclass, nothing imports it outside its tests, and the curated dataset remains the only
source the application ever ingests. Greenhouse, Lever and Ashby are the named initial
targets (ADR-028 D5), each requiring its own implementation gate and its own Terms-of-Service
confirmation (ADR-028 D8).
"""

from app.adapters.base_adapter import JobSourceAdapter
from app.adapters.curated_adapter import CuratedJobAdapter
from app.adapters.live_http_adapter import LiveHTTPAdapter, PageRequest, RateLimiter

__all__ = [
    "CuratedJobAdapter",
    "JobSourceAdapter",
    "LiveHTTPAdapter",
    "PageRequest",
    "RateLimiter",
]
