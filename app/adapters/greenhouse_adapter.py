"""Greenhouse public Job Board adapter — the first live source (ADR-028 D5).

Reads the **public, unauthenticated** Job Board GET endpoints. Greenhouse documents board
data as publicly available, so no credential exists to leak and none is sent:

* ``GET /v1/boards/{board_token}`` — the organization's name, which the jobs endpoint does
  not supply and which must not be guessed from the token (ADR-029, § Board identity).
* ``GET /v1/boards/{board_token}/jobs?content=true`` — every job post on that board, with
  its description, in one complete response.

**No application endpoint is ever called.** Greenhouse's submission endpoint is a POST, and
this adapter issues GETs only — EligiCore returns an apply URL and a human submits
(ADR-008, INV-10). Application-question retrieval is not used either; it is form metadata
this system has no use for.

**Non-authoritative, deliberately** (ADR-028 D14). A board's response is complete for *that
board*, but the source as a whole is a set of independently-fetched boards, so a job absent
from one run is not evidence the posting is gone. ``is_authoritative`` stays ``False`` and
ingestion therefore never closes a job because Greenhouse stopped listing it.

**Employment type is always ``UNKNOWN``.** The Greenhouse Job Board API publishes no
employment-type field in either endpoint, and ADR-029 D3 forbids inferring one from a title,
description, department or office. A posting called "Software Engineering Intern" maps to
``UNKNOWN`` like any other, because the title is prose and a confident wrong answer is worse
than an honest unknown.

**No structured eligibility is extracted.** Greenhouse publishes CGPA cutoffs, permitted
branches, backlog limits and graduation-year windows nowhere, so those fields stay absent
and the eligibility engine's existing missing-value semantics apply (ADR-028 D9).

Privacy: a board token is not a secret, but it is still never logged, never placed in an
error message and never echoed back — the same discipline the rest of the adapter layer
applies to anything that travels in a URL (INV-4). Logging here is counts only.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from app.adapters.base_adapter import AdapterError
from app.adapters.live_http_adapter import LiveHTTPAdapter, PageRequest
from app.schemas.candidate import JobType
from app.schemas.job import RawJob

logger = logging.getLogger("eligicore.adapters.greenhouse")

#: Greenhouse's documented public base. Overridable only so tests can point a mock
#: transport somewhere obviously fake; nothing reads it from the environment.
DEFAULT_API_BASE = "https://boards-api.greenhouse.io/v1"

#: Requests this adapter issues per board: the board itself, then its jobs.
REQUESTS_PER_BOARD = 2


class GreenhouseAdapter(LiveHTTPAdapter):
    """Supplies jobs from one or more public Greenhouse job boards.

    Board tokens are **constructor input only** — there is no environment variable, no
    default token and no registry entry (ADR-028 leaves source configuration to its own
    slice). A default checkout therefore constructs nothing, and an adapter built with no
    tokens makes **zero HTTP requests**.

    The walk is driven through :class:`~app.adapters.live_http_adapter.LiveHTTPAdapter`'s
    pagination hooks, two requests per board in a fixed order, so every request inherits the
    shared client, the explicit timeout, bounded retries with jittered backoff, the rate
    limiter and the sanitized error translation. **None of that is reimplemented here.**
    """

    source_name = "greenhouse"
    is_authoritative = False

    def __init__(
        self,
        *,
        board_tokens: list[str] | tuple[str, ...] = (),
        api_base: str = DEFAULT_API_BASE,
        **transport: Any,
    ) -> None:
        """Configure which boards to read.

        Args:
            board_tokens: The public board identifiers to fetch, in order. Empty means this
                adapter does nothing and contacts nothing. Duplicates are collapsed, order
                preserved, so a repeated token is not fetched twice.
            api_base: Base URL, without a trailing slash. Exists for test transports.
            **transport: Passed to :class:`LiveHTTPAdapter` — client, timeout, retries,
                rate limits, backoff, injected clock and sleep.
        """
        seen: dict[str, None] = {}
        for token in board_tokens:
            if not token or not token.strip():
                raise ValueError("board tokens must be non-empty strings")
            seen.setdefault(token.strip(), None)
        self._board_tokens: tuple[str, ...] = tuple(seen)

        # One page per request, two requests per board, plus headroom so a correct fetch can
        # never trip the base's runaway-pagination guard.
        transport.setdefault(
            "max_pages", max(1, REQUESTS_PER_BOARD * len(self._board_tokens))
        )
        super().__init__(**transport)

        self._api_base = api_base.rstrip("/")
        #: Board name per token, resolved once per fetch and reused by that board's jobs
        #: page. Cleared at the start of every fetch so a renamed organization is picked up.
        self._board_names: dict[str, str] = {}

    @property
    def board_tokens(self) -> tuple[str, ...]:
        """The boards this adapter will read. Deduplicated, order preserved."""
        return self._board_tokens

    # -- the walk -------------------------------------------------------------------------

    async def fetch(self) -> list[RawJob]:
        """Fetch every configured board.

        **Zero boards means zero requests** — no client is opened and nothing is contacted,
        which is what keeps a default checkout offline (ADR-028 § Operational impact).

        **A failure on any board fails the whole fetch**, inherited from
        :class:`LiveHTTPAdapter` and correct here for the same reason: ingestion must be
        able to tell a real failure from a board that genuinely has no open roles. An empty
        board returns ``[]`` and the run records SUCCESS; a failed board raises
        :class:`~app.adapters.base_adapter.AdapterError` and the run records FAILED. There
        is no third outcome, so a partially-fetched set can never be recorded as a complete
        one. Because this source is non-authoritative, a failed run closes nothing and the
        next run simply re-reads every board.
        """
        if not self._board_tokens:
            logger.info(
                "greenhouse_fetch source=%s outcome=skipped boards=0 reason=no_board_tokens",
                self.source_name,
            )
            return []

        self._board_names.clear()
        jobs = await super().fetch()
        logger.info(
            "greenhouse_fetch source=%s outcome=success boards=%d jobs=%d",
            self.source_name,
            len(self._board_tokens),
            len(jobs),
        )
        return jobs

    # -- pagination hooks -----------------------------------------------------------------
    #
    # The sequence is fixed and derivable from the page number alone, so no mutable cursor
    # is needed: page 1 is board 0's board request, page 2 its jobs, page 3 board 1's board
    # request, and so on. Deriving it beats sniffing the payload's shape, which would have
    # to guess what a response is from its keys.

    def initial_request(self) -> PageRequest:
        """The first board's board-name request."""
        return self._board_request(0)

    def next_request(
        self, payload: Any, previous: PageRequest, page_number: int
    ) -> PageRequest | None:
        """Jobs after a board, then the next board, then stop."""
        if self._is_board_step(page_number):
            return self._jobs_request(self._board_index(page_number))

        next_index = self._board_index(page_number) + 1
        if next_index >= len(self._board_tokens):
            return None
        return self._board_request(next_index)

    def parse_page(self, payload: Any, page_number: int) -> list[RawJob]:
        """Record a board's name, or map a board's jobs into :class:`RawJob`."""
        index = self._board_index(page_number)
        if self._is_board_step(page_number):
            self._board_names[self._board_tokens[index]] = self._read_board_name(payload)
            return []
        return self._read_jobs(payload, index)

    # -- requests -------------------------------------------------------------------------

    def _board_request(self, index: int) -> PageRequest:
        return PageRequest(url=f"{self._api_base}/boards/{self._board_tokens[index]}")

    def _jobs_request(self, index: int) -> PageRequest:
        return PageRequest(
            url=f"{self._api_base}/boards/{self._board_tokens[index]}/jobs",
            # The documented switch that returns each post's description. Nothing else is
            # requested — notably not `questions`, which is application-form metadata.
            params={"content": "true"},
        )

    @staticmethod
    def _is_board_step(page_number: int) -> bool:
        return (page_number - 1) % REQUESTS_PER_BOARD == 0

    @staticmethod
    def _board_index(page_number: int) -> int:
        return (page_number - 1) // REQUESTS_PER_BOARD

    # -- parsing --------------------------------------------------------------------------

    def _read_board_name(self, payload: Any) -> str:
        """The organization name Greenhouse publishes for a board.

        **The only acceptable source for ``company_name``.** Deriving it from the board
        token, the URL, a job title or description text would be inventing an employer name
        (ADR-029 § Board identity), and ``RawJob.company_name`` is required, so a board that
        does not supply one fails rather than being papered over.
        """
        if not isinstance(payload, dict):
            raise self._board_failure("response_not_an_object")

        name = payload.get("name")
        if not isinstance(name, str) or not name.strip():
            raise self._board_failure("no_organization_name")
        return name.strip()

    def _read_jobs(self, payload: Any, index: int) -> list[RawJob]:
        """Map one board's job posts, skipping individually malformed records.

        A **structurally** unusable response fails the fetch: if ``jobs`` is missing or is
        not a list, the response cannot be distinguished from a board with no openings, and
        guessing "empty" would be the silent-truncation failure the whole design avoids.

        A **single** malformed record is skipped and counted instead, following
        ``CuratedJobAdapter`` — one bad entry must not discard the board's good ones. Only
        the index and a count are logged; **the record itself never is**, because a live
        payload can contain anything (INV-4).
        """
        if not isinstance(payload, dict):
            raise self._jobs_failure("response_not_an_object")

        entries = payload.get("jobs")
        if not isinstance(entries, list):
            raise self._jobs_failure("jobs_not_a_list")

        token = self._board_tokens[index]
        company_name = self._board_names.get(token)
        if not company_name:
            # Unreachable through the normal walk; a guard rather than a silent "".
            raise self._jobs_failure("board_name_unresolved")

        jobs: list[RawJob] = []
        seen_ids: set[str] = set()
        skipped = 0
        duplicates = 0

        for position, entry in enumerate(entries):
            mapped = self._map_job(entry, company_name)
            if mapped is None:
                skipped += 1
                logger.warning(
                    "greenhouse_record_invalid source=%s board_index=%d position=%d",
                    self.source_name,
                    index,
                    position,
                )
                continue

            # One board listing the same post twice is the source's duplicate, not two
            # jobs. Collapsed here so ingestion is not handed a contradiction. Boards are
            # never deduplicated against each other — attribution stays per source row.
            if mapped.source_job_id in seen_ids:
                duplicates += 1
                continue

            seen_ids.add(str(mapped.source_job_id))
            jobs.append(mapped)

        logger.info(
            "greenhouse_board source=%s board_index=%d jobs=%d skipped=%d duplicates=%d",
            self.source_name,
            index,
            len(jobs),
            skipped,
            duplicates,
        )
        return jobs

    def _map_job(self, entry: Any, company_name: str) -> RawJob | None:
        """One Greenhouse job post as a :class:`RawJob`, or ``None`` when unusable.

        Only fields Greenhouse actually supplies are mapped. Everything else — every
        eligibility criterion, the deadline, and the required-skill list — is left at its
        default, because Greenhouse states none of them and ADR-028 D9 forbids inventing
        them. ``updated_at``, ``first_published``, ``departments``, ``offices``,
        ``requisition_id``, ``internal_job_id``, ``language`` and ``metadata`` are dropped
        deliberately: ``RawJob`` forbids extra fields, and representing freshness is the
        separate freshness slice's job.
        """
        if not isinstance(entry, dict):
            return None

        identifier = entry.get("id")
        if not isinstance(identifier, (int, str)) or isinstance(identifier, bool):
            return None

        location = entry.get("location")
        location_name = (
            location.get("name") if isinstance(location, dict) else None
        )
        content = entry.get("content")

        try:
            return RawJob(
                company_name=company_name,
                role_title=entry.get("title") or "",
                # Never inferred from the title or anything else (ADR-029 D3). Greenhouse
                # publishes no employment type, so this is the honest answer every time.
                job_type=JobType.UNKNOWN,
                location=location_name if isinstance(location_name, str) else None,
                description=content if isinstance(content, str) else "",
                apply_link=entry.get("absolute_url")
                if isinstance(entry.get("absolute_url"), str)
                else None,
                # Not published by the list endpoint, and never inferred from text.
                deadline=None,
                # The **job post** id, not internal_job_id: the post is what the apply URL
                # addresses and what a reader applies to.
                source_job_id=str(identifier),
            )
        except ValidationError:
            # error_count is not even recorded: pydantic's detail embeds the offending
            # values, which here are third-party payload content (INV-4).
            return None

    # -- errors ---------------------------------------------------------------------------

    def _board_failure(self, reason: str) -> AdapterError:
        return self._sanitized_failure("board", reason)

    def _jobs_failure(self, reason: str) -> AdapterError:
        return self._sanitized_failure("jobs", reason)

    def _sanitized_failure(self, step: str, reason: str) -> AdapterError:
        """The only error shape this module raises.

        Built from the source name, a fixed step and a fixed reason code — **never from a
        board token, a URL, a response body or a job's contents.** A board token is not a
        secret, but it identifies an employer and travels in a URL, so it is treated like
        everything else that does (INV-4).
        """
        return AdapterError(
            f"{self.source_name} fetch failed: step={step} reason={reason}."
        )
