"""Job source adapters.

Every source — a curated file today, a portal API later — implements the same interface
and returns the same normalized shape. Adding a source is one new class; the eligibility
and matching engines never change (ADR-005, INV-6).

**Adapters must operate within their source's Terms of Service.** An adapter requiring
CAPTCHA solving, anti-bot circumvention or an authentication bypass is out of scope
permanently (ADR-008, INV-10).
"""

from app.adapters.base_adapter import JobSourceAdapter
from app.adapters.curated_adapter import CuratedJobAdapter

__all__ = ["CuratedJobAdapter", "JobSourceAdapter"]
