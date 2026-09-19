"""Curated catalogue data quality (PR 6B — ADR-024 §2, §3).

The catalogue is the demo's only job source, so its contents are tested like code: exactly 40
synthetic postings, the original five preserved byte for byte, every entry a valid ``RawJob`` that
the production adapter accepts, no personal data, and enough diversity to exercise every
eligibility and matching path.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest

from app.adapters.curated_adapter import DEFAULT_DATASET, CuratedJobAdapter
from app.schemas.job import RawJob
from app.services.job_normalizer import compute_content_hash

DATASET = Path(__file__).resolve().parent.parent / "app" / "data" / "curated_jobs.json"

#: The original five entries (Weeks 3–4), as bytes: the file up to the closing brace of
#: EX-INT-005. Pinned so no edit to them — even whitespace — goes unnoticed (ADR-024 §2).
ORIGINAL_PREFIX_LENGTH = 4164
ORIGINAL_PREFIX_SHA256 = "8ef85d44976e693a1827eec6d4270cf005e83a38cf05bfecf63dfcb6ac113a7d"
ORIGINAL_IDS = ["EX-INT-001", "EX-FT-002", "EX-INT-003", "EX-FT-004", "EX-INT-005"]

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"\+?\d[\d\s().-]{8,}\d")
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def entries() -> list[dict[str, Any]]:
    return json.loads(DATASET.read_text(encoding="utf-8"))


def jobs() -> list[RawJob]:
    return [RawJob.model_validate(entry) for entry in entries()]


def strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in strings(v)]
    return []


# ---------------------------------------------------------------------------------------
# Size, identity, preservation
# ---------------------------------------------------------------------------------------


def test_the_adapter_reads_the_dataset_file() -> None:
    assert DEFAULT_DATASET.resolve() == DATASET.resolve()


def test_exactly_forty_jobs() -> None:
    assert len(entries()) == 40


def test_every_entry_is_a_valid_raw_job() -> None:
    assert len(jobs()) == 40


def test_production_adapter_accepts_every_entry(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="eligicore.adapters.curated"):
        fetched = asyncio.run(CuratedJobAdapter().fetch())
    assert len(fetched) == 40
    assert "curated_dataset_entry_invalid" not in caplog.text


def test_original_five_entries_are_byte_identical() -> None:
    raw = DATASET.read_bytes()
    assert hashlib.sha256(raw[:ORIGINAL_PREFIX_LENGTH]).hexdigest() == ORIGINAL_PREFIX_SHA256
    assert raw[ORIGINAL_PREFIX_LENGTH:ORIGINAL_PREFIX_LENGTH + 2] == b",\n"
    assert [e["source_job_id"] for e in entries()[:5]] == ORIGINAL_IDS


def test_source_ids_are_unique_stable_and_ordered() -> None:
    ids = [e["source_job_id"] for e in entries()]
    assert len(set(ids)) == 40
    assert all(re.fullmatch(r"EX-(INT|FT)-\d{3}", sid) for sid in ids)
    assert [int(sid[-3:]) for sid in ids] == list(range(1, 41))


def test_id_prefix_matches_job_type() -> None:
    for entry in entries():
        expected = "INT" if entry["job_type"] == "INTERNSHIP" else "FT"
        assert entry["source_job_id"].split("-")[1] == expected, entry["source_job_id"]


def test_content_hashes_are_unique() -> None:
    hashes = [compute_content_hash(job, CuratedJobAdapter.source_name) for job in jobs()]
    assert len(set(hashes)) == 40


def test_no_status_field_curated_jobs_stay_active() -> None:
    """C-30: the curated source states no status; ingestion makes every job ACTIVE."""
    assert "status" not in RawJob.model_fields
    assert all("status" not in entry for entry in entries())


def test_dataset_is_deterministic_json() -> None:
    raw = DATASET.read_text(encoding="utf-8")
    assert raw.endswith("\n]\n") and "\r" not in raw
    assert json.loads(raw) == entries()


# ---------------------------------------------------------------------------------------
# Synthetic, no personal data
# ---------------------------------------------------------------------------------------


def test_companies_are_fictional() -> None:
    for entry in entries():
        assert entry["company_name"].startswith(("Example ", "Sample ")), entry["company_name"]


def test_links_are_example_com_https() -> None:
    for entry in entries():
        url = urlparse(entry["apply_link"])
        assert url.scheme == "https"
        assert url.hostname == "example.com" or url.hostname.endswith(".example.com"), url.hostname


def test_no_email_address_phone_number_or_contact_anywhere() -> None:
    for entry in entries():
        for text in strings(entry):
            assert not EMAIL.search(text), text
            # ISO dates (deadlines) are structured data, not contact details.
            assert ISO_DATE.fullmatch(text) or not PHONE.search(text), text
            for word in ("contact", "recruiter", "whatsapp", "call ", "mobile:"):
                assert word not in text.lower(), text


def test_no_candidate_data() -> None:
    forbidden_keys = {"candidate_id", "name", "email", "phone", "resume", "profile", "backlogs"}
    for entry in entries():
        assert not forbidden_keys & set(entry), entry["source_job_id"]
        assert not forbidden_keys & set(entry.get("requirements", {})), entry["source_job_id"]


# ---------------------------------------------------------------------------------------
# Diversity (ADR-024 §2)
# ---------------------------------------------------------------------------------------

ROLE_FAMILIES = {
    "software": ("software engineer",),
    "backend": ("backend",),
    "frontend": ("frontend",),
    "full stack": ("full stack",),
    "data": ("data engineer", "data analyst", "data science"),
    "ml": ("machine learning",),
    "devops": ("devops", "site reliability", "platform", "cloud"),
    "qa": ("qa ",),
    "security": ("security",),
    "embedded": ("embedded", "hardware"),
    "analyst": ("analyst",),
    "mechanical": ("mechanical", "automotive", "manufacturing", "robotics"),
    "electrical": ("electrical", "power systems"),
    "finance": ("financial", "accounting", "quantitative"),
}


def test_role_family_coverage() -> None:
    titles = [e["role_title"].lower() + " " for e in entries()]
    for family, needles in ROLE_FAMILIES.items():
        assert any(n in t for t in titles for n in needles), family


def test_internships_and_full_time_roles() -> None:
    counts = Counter(e["job_type"] for e in entries())
    assert counts["INTERNSHIP"] >= 10 and counts["FULL_TIME"] >= 10


def test_cgpa_scales() -> None:
    pairs = [(e["min_cgpa"], e["min_cgpa_scale"]) for e in entries()]
    scales = Counter(scale for cgpa, scale in pairs if cgpa is not None)
    assert scales["SCALE_10"] >= 10
    assert scales["SCALE_4"] >= 1
    assert scales["PERCENTAGE"] >= 1
    assert scales[None] >= 1, "a cutoff with no stated scale (UNKNOWN on comparison)"
    assert sum(1 for cgpa, _ in pairs if cgpa is None) >= 3, "jobs with no CGPA cutoff"


def test_graduation_windows() -> None:
    windows = [(e["min_grad_year"], e["max_grad_year"]) for e in entries()]
    years = {y for w in windows for y in w if y is not None}
    assert {2025, 2026, 2027, 2028, 2029} <= years
    # 2024 appears in the original five entries, which are preserved unchanged.
    assert all(y is None or 2024 <= y <= 2029 for w in windows for y in w)
    assert any(lo is None and hi is not None for lo, hi in windows), "open lower bound"
    assert any(lo is not None and hi is None for lo, hi in windows), "open upper bound"
    assert any(lo is None and hi is None for lo, hi in windows), "no window"


def test_degree_levels() -> None:
    levels = Counter(e["min_degree_level"] for e in entries())
    assert levels[None] >= 5 and levels["BACHELORS"] >= 5 and levels["MASTERS"] >= 2


def test_allowed_field_kinds() -> None:
    fields = [e["allowed_fields"] for e in entries()]
    assert sum(1 for f in fields if not f) >= 5, "no field restriction"
    assert sum(1 for f in fields if "Information Technology" in f) >= 5, "exact match for IT"
    assert sum(1 for f in fields if f and "Information Technology" not in f and "Computer Science" not in f) >= 5, \
        "fields an IT candidate reaches only through the AI relatedness stage"
    assert sum(1 for f in fields if "Mechanical Engineering" in f) >= 2


def test_backlog_limits() -> None:
    limits = Counter(e["max_backlogs"] for e in entries())
    assert limits[0] >= 5 and limits[2] >= 2 and limits[None] >= 5 and limits[1] >= 1


def test_skill_coverage_including_aliases() -> None:
    skills = {s for e in entries() for s in e["required_skills"]}
    for skill in ("C++", "C#", ".NET", "React.js", "Node.js", "Python", "SQL", "Java", "Docker",
                  "Git", "SolidWorks", "MATLAB"):
        assert skill in skills, skill


def test_a_job_with_no_matching_terms() -> None:
    """``EX-INT-039``: a stop-word title, no description, no skills — ``NO_JOB_TERMS``."""
    (job,) = [e for e in entries() if e["source_job_id"] == "EX-INT-039"]
    assert job["description"] == "" and job["required_skills"] == []
    assert job["role_title"] == "Other"


def test_deadlines_are_static_dates_or_null() -> None:
    deadlines = [e["deadline"] for e in entries()]
    assert any(d is None for d in deadlines)
    assert all(d is None or re.fullmatch(r"202[67]-\d{2}-\d{2}", d) for d in deadlines)
