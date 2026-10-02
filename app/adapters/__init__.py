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

**Greenhouse** is the first concrete live source (ADR-028 D5):

* **Public GET API only** — ``GET /v1/boards/{board_token}`` for the organization's name
  and ``GET /v1/boards/{board_token}/jobs?content=true`` for its posts. Greenhouse
  documents both as publicly available, so **no authentication and no credential** is
  involved. **No application-submission endpoint is ever called** (ADR-008, INV-10).
* **Board tokens are constructor input**, nothing else. There is no environment variable
  and no default token, so a checkout that configures none makes zero requests — source
  configuration is its own later slice.
* **``company_name`` comes from the board endpoint**, because list-jobs does not supply one
  and deriving it from the token would be inventing an employer's name.
* **``source_job_id`` is the Greenhouse job *post* id** (``id``), not ``internal_job_id``:
  the post is what the apply URL addresses.
* **Employment type is always ``UNKNOWN``** — Greenhouse publishes none, and inferring one
  from a title or description is forbidden (ADR-029 D3). **No structured eligibility
  criterion is extracted** from prose either (ADR-028 D9); absent stays absent.
* **Non-authoritative**, so a job missing from one fetch is never closed (ADR-028 D14).

Lever and Ashby remain named targets, each needing its own implementation gate and its own
Terms-of-Service confirmation (ADR-028 D8).
"""

from app.adapters.base_adapter import JobSourceAdapter
from app.adapters.curated_adapter import CuratedJobAdapter
from app.adapters.greenhouse_adapter import GreenhouseAdapter
from app.adapters.live_http_adapter import LiveHTTPAdapter, PageRequest, RateLimiter

__all__ = [
    "CuratedJobAdapter",
    "GreenhouseAdapter",
    "JobSourceAdapter",
    "LiveHTTPAdapter",
    "PageRequest",
    "RateLimiter",
]
