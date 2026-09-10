"""SQLAlchemy models — OPERATIONAL DATA ONLY.

╔══════════════════════════════════════════════════════════════════════════════════════╗
║  Permitted here:                                                                     ║
║      job.py              — the job catalogue                                         ║
║      ingestion_state.py  — adapter state, one row per source (ADR-015)               ║
║                                                                                      ║
║  FORBIDDEN — do not create, and do not write migrations for:                          ║
║      candidate.py · application.py · evaluation.py                                   ║
║      or any table holding profiles, resumes, results or application records.         ║
║                                                                                      ║
║  The dossier §8.2 folder listing shows ``models/candidate.py`` and                    ║
║  ``models/application.py``. That listing is STALE. §10.2 governs, and ADR-011         ║
║  rules on it explicitly. Candidate data is in-flight only (INV-1).                    ║
╚══════════════════════════════════════════════════════════════════════════════════════╝

Importing this package registers every model on ``Base.metadata`` so Alembic autogenerate
can see them. Add new operational models to the imports below.
"""

from app.models.ingestion_state import IngestionState, IngestionStatus
from app.models.job import Job, JobStatus

__all__ = ["IngestionState", "IngestionStatus", "Job", "JobStatus"]
