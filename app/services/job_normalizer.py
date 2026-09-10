"""Job normalization and canonical content hashing.

Pure functions. No FastAPI, no database, no I/O (INV-7).

Implements the deduplication rule from dossier §10.2:

    content_hash is computed over a CANONICALIZED set of stable fields, not over raw
    posting text. Formatting differences between sources should not create duplicate jobs.

    Canonicalization inputs: normalized company name, normalized role title, normalized
    location, apply URL when available, source job ID when available, normalized
    description and requirements.

The whole point is that two sources describing the same posting with different whitespace,
casing, or a trailing "Pvt. Ltd." must produce the *same* hash. Getting this wrong in either
direction is costly: too loose and distinct jobs collapse into one, too strict and the
catalogue fills with duplicates.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from app.schemas.job import NormalizedJob, RawJob

_WHITESPACE = re.compile(r"\s+")
_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)

#: Company suffixes stripped before hashing, so "Example Corp" and "Example Corp Pvt. Ltd."
#: hash alike. Ordered longest-first so "pvt ltd" is removed before "ltd" can match part of
#: it. Deliberately short — an aggressive list would start merging genuinely distinct
#: companies, which is the more expensive mistake.
_COMPANY_SUFFIXES = (
    "private limited",
    "pvt ltd",
    "pvt limited",
    "limited",
    "incorporated",
    "corporation",
    "company",
    "ltd",
    "llp",
    "llc",
    "inc",
    "plc",
    "gmbh",
    "corp",
    "co",
)


def collapse_whitespace(value: str) -> str:
    """Trim and collapse internal whitespace runs to single spaces."""
    return _WHITESPACE.sub(" ", value).strip()


def normalize_display_text(value: str | None) -> str | None:
    """Clean a human-readable field without altering its meaning.

    Whitespace only — casing and punctuation are preserved, because this is what the API
    returns and what a person reads. Hashing normalizes far more aggressively, and does so
    separately.
    """
    if value is None:
        return None
    cleaned = collapse_whitespace(value)
    return cleaned or None


def canonicalize(value: str | None) -> str:
    """Reduce a string to its comparison form for hashing.

    Lowercases, strips punctuation, and collapses whitespace, per the dossier's rule.
    ``None`` becomes an empty string so an absent field contributes consistently rather
    than shifting every following field's position in the hash input.
    """
    if not value:
        return ""
    lowered = value.lower()
    without_punctuation = _PUNCTUATION.sub(" ", lowered)
    return collapse_whitespace(without_punctuation)


def canonicalize_company(value: str | None) -> str:
    """Canonicalize a company name and strip a trailing legal suffix.

    "Example Corp", "Example Corp." and "Example Corp Pvt. Ltd." all reduce to "example".
    Only trailing suffixes are stripped, and repeatedly — "Example Pvt Ltd Inc" is
    contrived but should still reduce cleanly.
    """
    canonical = canonicalize(value)
    changed = True
    while changed and canonical:
        changed = False
        for suffix in _COMPANY_SUFFIXES:
            if canonical.endswith(" " + suffix):
                canonical = canonical[: -(len(suffix) + 1)].strip()
                changed = True
                break
    return canonical


def canonicalize_url(value: str | None) -> str:
    """Reduce a URL to a comparison form.

    Lowercases scheme and host, drops a trailing slash, and strips a leading ``www.``.
    The path keeps its case — many application URLs carry case-sensitive identifiers, and
    lowercasing them would merge genuinely different postings.
    """
    if not value:
        return ""
    url = value.strip()
    match = re.match(r"^(https?)://([^/]+)(.*)$", url, re.IGNORECASE)
    if not match:
        return url.lower().rstrip("/")
    scheme, host, path = match.groups()
    host = host.lower().removeprefix("www.")
    return f"{scheme.lower()}://{host}{path.rstrip('/')}"


def _canonical_requirements(requirements: dict[str, Any]) -> str:
    """Serialize requirements deterministically.

    ``sort_keys`` matters: two sources emitting the same requirements in a different key
    order must hash identically. Without it, dict ordering silently becomes part of the
    identity of a job.
    """
    try:
        return json.dumps(requirements, sort_keys=True, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        # Unserializable requirements should not abort ingestion; they contribute a stable
        # fallback and the rest of the hash still distinguishes the posting.
        return str(sorted(requirements.items(), key=lambda kv: kv[0]))


def compute_content_hash(job: RawJob, source: str) -> str:
    """Compute the canonical deduplication hash for a job.

    Hashes the canonicalized field set from dossier §10.2 — never the raw posting text.
    Fields are joined with a separator that cannot occur in canonicalized output, so
    ``("ab", "c")`` and ``("a", "bc")`` cannot collide.
    """
    parts = [
        canonicalize_company(job.company_name),
        canonicalize(job.role_title),
        canonicalize(job.location),
        canonicalize_url(job.apply_link),
        canonicalize(job.source_job_id),
        canonicalize(job.description),
        canonicalize(_canonical_requirements(job.requirements)),
        canonicalize(source),
    ]
    payload = "\x1f".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_skill_list(values: list[str]) -> list[str]:
    """Clean, deduplicate case-insensitively, and preserve order.

    Job-side skills are cleaned but **not** mapped through the candidate alias table. The
    matching engine in Week 5 owns comparison across the two sides; normalizing job skills
    into candidate vocabulary here would bury a matching decision inside ingestion.
    """
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = collapse_whitespace(value)
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result


def normalize_job(raw: RawJob, source: str) -> NormalizedJob:
    """Normalize an adapter's job into canonical form with its content hash.

    Normalization cleans representation. It does not invent, drop, or reinterpret
    information: an absent deadline stays absent, an unstated grading scale stays unstated,
    and no requirement is evaluated here.
    """
    description = collapse_whitespace(raw.description)

    return NormalizedJob(
        company_name=normalize_display_text(raw.company_name) or raw.company_name,
        role_title=normalize_display_text(raw.role_title) or raw.role_title,
        job_type=raw.job_type,
        location=normalize_display_text(raw.location),
        description=description,
        requirements=raw.requirements,
        min_cgpa=raw.min_cgpa,
        # Never inferred. A cutoff with no stated scale stays None, exactly as a candidate
        # grade with no stated scale stays UNKNOWN (standards/eligibility.md §4).
        min_cgpa_scale=normalize_display_text(raw.min_cgpa_scale),
        allowed_fields=normalize_skill_list(raw.allowed_fields),
        max_backlogs=raw.max_backlogs,
        min_grad_year=raw.min_grad_year,
        max_grad_year=raw.max_grad_year,
        required_skills=normalize_skill_list(raw.required_skills),
        apply_link=normalize_display_text(raw.apply_link),
        deadline=raw.deadline,
        source=source,
        source_job_id=normalize_display_text(raw.source_job_id),
        content_hash=compute_content_hash(raw, source),
    )
