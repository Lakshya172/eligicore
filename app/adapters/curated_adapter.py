"""Curated dataset adapter — the Phase 1 job source.

Reads a manually curated JSON file. This is a deliberate de-risking move, not a placeholder
to be rushed past: job data acquisition at scale is the highest-severity risk in the dossier
(§16), legally and technically, and isolating it behind this boundary means everything
downstream can be built and validated while that problem stays unsolved (ADR-005).

**Authoritative.** The file lists every job this source knows about, so a job disappearing
from it is genuine evidence the posting is gone, and ingestion may close it (ADR-014).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import ValidationError

from app.adapters.base_adapter import AdapterError, JobSourceAdapter
from app.schemas.job import RawJob

logger = logging.getLogger("eligicore.adapters.curated")

DEFAULT_DATASET = Path(__file__).resolve().parent.parent / "data" / "curated_jobs.json"


class CuratedJobAdapter(JobSourceAdapter):
    """Supplies jobs from a curated JSON file."""

    source_name = "curated"
    is_authoritative = True

    def __init__(self, dataset_path: Path | None = None) -> None:
        self._dataset_path = dataset_path or DEFAULT_DATASET

    async def fetch(self) -> list[RawJob]:
        """Read and validate every job in the curated dataset.

        Raises:
            AdapterError: The file is missing, unreadable, or not a JSON list.
        """
        raw_text = self._read_file()
        payload = self._parse_json(raw_text)

        if not isinstance(payload, list):
            raise AdapterError(
                f"Curated dataset must contain a JSON list, found {type(payload).__name__}."
            )

        jobs: list[RawJob] = []
        skipped = 0
        for index, entry in enumerate(payload):
            try:
                jobs.append(RawJob.model_validate(entry))
            except ValidationError as exc:
                # One malformed entry must not discard the whole file — the other jobs are
                # still usable. Only the index and error count are recorded; the entry
                # itself is not logged, because a future non-curated source could carry
                # anything (INV-4).
                skipped += 1
                logger.warning(
                    "curated_dataset_entry_invalid source=%s index=%d error_count=%d",
                    self.source_name,
                    index,
                    exc.error_count(),
                )

        if skipped:
            logger.warning(
                "curated_dataset_partial source=%s valid=%d skipped=%d",
                self.source_name,
                len(jobs),
                skipped,
            )

        return jobs

    # -- internals ----------------------------------------------------------------------

    def _read_file(self) -> str:
        try:
            return self._dataset_path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            # The path is a repository file, not user data, so naming it is safe and makes
            # the failure actionable.
            raise AdapterError(
                f"Curated dataset not found at {self._dataset_path}."
            ) from exc
        except OSError as exc:
            raise AdapterError(
                f"Curated dataset could not be read ({type(exc).__name__})."
            ) from exc

    def _parse_json(self, raw_text: str) -> object:
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError as exc:
            # Position only. The message would otherwise quote file content back.
            raise AdapterError(
                f"Curated dataset is not valid JSON (line {exc.lineno}, column {exc.colno})."
            ) from exc
