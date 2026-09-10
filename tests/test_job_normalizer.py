"""Job normalization and canonical content hashing tests.

The hashing tests are the important ones. Getting deduplication wrong is costly in both
directions: too loose and distinct postings collapse into one, too strict and the catalogue
fills with duplicates of the same job.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.schemas.candidate import JobType
from app.schemas.job import RawJob
from app.services.job_normalizer import (
    canonicalize,
    canonicalize_company,
    canonicalize_url,
    compute_content_hash,
    normalize_job,
    normalize_skill_list,
)


def make_raw(**overrides: object) -> RawJob:
    """Build a RawJob with sensible synthetic defaults."""
    base: dict[str, object] = {
        "company_name": "Example Analytics",
        "role_title": "Software Engineering Intern",
        "job_type": JobType.INTERNSHIP,
        "location": "Bengaluru, India",
        "description": "Six-month internship building internal tooling.",
        "apply_link": "https://careers.example.com/roles/swe-intern",
        "source_job_id": "EX-001",
    }
    base.update(overrides)
    return RawJob.model_validate(base)


# ---------------------------------------------------------------------------------------
# Canonicalization primitives
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Software Engineer", "software engineer"),
        ("  Software   Engineer  ", "software engineer"),
        ("Software-Engineer", "software engineer"),
        ("SOFTWARE ENGINEER!", "software engineer"),
        (None, ""),
        ("", ""),
    ],
)
def test_canonicalize(raw: str | None, expected: str) -> None:
    assert canonicalize(raw) == expected


@pytest.mark.parametrize(
    "variant",
    [
        "Example Analytics",
        "Example Analytics Pvt. Ltd.",
        "example analytics ltd",
        "  EXAMPLE   ANALYTICS  Inc.  ",
        "Example Analytics Private Limited",
    ],
)
def test_company_variants_canonicalize_alike(variant: str) -> None:
    """Legal suffixes and formatting must not make one company look like several."""
    assert canonicalize_company(variant) == "example analytics"


def test_company_suffix_stripping_does_not_eat_real_names() -> None:
    """A name that merely contains a suffix word keeps it."""
    assert canonicalize_company("Limited Edition Labs") == "limited edition labs"
    assert canonicalize_company("Incorporated Systems Group") == "incorporated systems group"


def test_distinct_companies_stay_distinct() -> None:
    assert canonicalize_company("Example Analytics") != canonicalize_company("Example Cloud")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://careers.example.com/x", "https://careers.example.com/x"),
        ("HTTPS://Careers.Example.COM/x", "https://careers.example.com/x"),
        ("https://www.example.com/x", "https://example.com/x"),
        ("https://example.com/x/", "https://example.com/x"),
        (None, ""),
    ],
)
def test_canonicalize_url(raw: str | None, expected: str) -> None:
    assert canonicalize_url(raw) == expected


def test_url_path_case_is_preserved() -> None:
    """Application URLs often carry case-sensitive ids; lowercasing merges real postings."""
    assert canonicalize_url("https://example.com/JOB-AbC123") == "https://example.com/JOB-AbC123"
    assert canonicalize_url("https://example.com/JOB-AbC123") != canonicalize_url(
        "https://example.com/job-abc123"
    )


# ---------------------------------------------------------------------------------------
# Content hashing
# ---------------------------------------------------------------------------------------


def test_hash_is_deterministic() -> None:
    job = make_raw()
    assert compute_content_hash(job, "curated") == compute_content_hash(job, "curated")


@pytest.mark.parametrize(
    "overrides",
    [
        {"company_name": "  Example   Analytics  "},
        {"company_name": "EXAMPLE ANALYTICS"},
        {"company_name": "Example Analytics Pvt. Ltd."},
        {"role_title": "software engineering intern"},
        {"role_title": "Software  Engineering   Intern"},
        {"location": "BENGALURU, INDIA"},
        {"description": "Six-month   internship building internal tooling."},
        {"apply_link": "https://www.careers.example.com/roles/swe-intern/"},
    ],
    ids=["ws", "case", "suffix", "title-case", "title-ws", "loc", "desc-ws", "url"],
)
def test_formatting_differences_do_not_change_the_hash(overrides: dict) -> None:
    """The core dedup requirement (dossier §10.2)."""
    assert compute_content_hash(make_raw(), "curated") == compute_content_hash(
        make_raw(**overrides), "curated"
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"company_name": "Example Cloud"},
        {"role_title": "Backend Engineer"},
        {"location": "Pune, India"},
        {"apply_link": "https://careers.example.com/roles/other"},
        {"source_job_id": "EX-999"},
        {"description": "A different posting entirely."},
        {"requirements": {"notes": "something else"}},
    ],
    ids=["company", "title", "location", "url", "source-id", "description", "requirements"],
)
def test_meaningful_differences_change_the_hash(overrides: dict) -> None:
    assert compute_content_hash(make_raw(), "curated") != compute_content_hash(
        make_raw(**overrides), "curated"
    )


def test_same_posting_from_two_sources_hashes_differently() -> None:
    """Source is part of the hash: one posting on two portals is two rows, two apply links."""
    job = make_raw()
    assert compute_content_hash(job, "curated") != compute_content_hash(job, "other")


def test_requirements_key_order_does_not_affect_the_hash() -> None:
    """Dict ordering must not become part of a job's identity."""
    a = make_raw(requirements={"min_cgpa": 7.0, "notes": "final year"})
    b = make_raw(requirements={"notes": "final year", "min_cgpa": 7.0})
    assert compute_content_hash(a, "curated") == compute_content_hash(b, "curated")


def test_field_boundaries_cannot_collide() -> None:
    """Concatenation without a separator would make ('ab','c') and ('a','bc') collide."""
    a = make_raw(company_name="ab", role_title="c")
    b = make_raw(company_name="a", role_title="bc")
    assert compute_content_hash(a, "curated") != compute_content_hash(b, "curated")


def test_hash_is_a_sha256_hex_digest() -> None:
    digest = compute_content_hash(make_raw(), "curated")
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)


def test_unserializable_requirements_do_not_crash_hashing() -> None:
    """A source emitting an odd value must not abort ingestion."""
    job = make_raw(requirements={"when": date(2026, 1, 1)})
    assert len(compute_content_hash(job, "curated")) == 64


# ---------------------------------------------------------------------------------------
# Skill list normalization
# ---------------------------------------------------------------------------------------


def test_skill_list_cleans_and_deduplicates() -> None:
    assert normalize_skill_list(["  Python  ", "python", "SQL", ""]) == ["Python", "SQL"]


def test_skill_list_preserves_order() -> None:
    assert normalize_skill_list(["Docker", "Python", "SQL"]) == ["Docker", "Python", "SQL"]


def test_job_skills_are_not_mapped_to_candidate_vocabulary() -> None:
    """Week 5 owns cross-side comparison. Mapping here would bury a matching decision."""
    assert normalize_skill_list(["ReactJS"]) == ["ReactJS"]


# ---------------------------------------------------------------------------------------
# Whole-job normalization
# ---------------------------------------------------------------------------------------


def test_normalize_job_produces_canonical_shape() -> None:
    normalized = normalize_job(make_raw(company_name="  Example   Analytics "), "curated")

    assert normalized.company_name == "Example Analytics"
    assert normalized.source == "curated"
    assert normalized.source_job_id == "EX-001"
    assert len(normalized.content_hash) == 64


def test_normalize_job_preserves_display_casing() -> None:
    """Canonicalization is for hashing. What the API returns stays human-readable."""
    normalized = normalize_job(make_raw(), "curated")
    assert normalized.company_name == "Example Analytics"
    assert normalized.role_title == "Software Engineering Intern"


def test_normalize_job_never_invents_a_cgpa_scale() -> None:
    """A cutoff with no stated scale stays null — the job-side mirror of INV-3."""
    normalized = normalize_job(make_raw(min_cgpa=8.0, min_cgpa_scale=None), "curated")
    assert normalized.min_cgpa == 8.0
    assert normalized.min_cgpa_scale is None


def test_normalize_job_preserves_stated_scale() -> None:
    normalized = normalize_job(make_raw(min_cgpa=7.0, min_cgpa_scale="SCALE_10"), "curated")
    assert normalized.min_cgpa_scale == "SCALE_10"


def test_normalize_job_preserves_absent_fields() -> None:
    """Normalization cleans representation; it does not fill gaps."""
    normalized = normalize_job(
        make_raw(deadline=None, max_backlogs=None, apply_link=None), "curated"
    )
    assert normalized.deadline is None
    assert normalized.max_backlogs is None
    assert normalized.apply_link is None


def test_normalize_job_evaluates_no_requirement() -> None:
    """Week 3 stores what a posting states. Week 4 decides what it means."""
    normalized = normalize_job(make_raw(min_cgpa=7.0, max_backlogs=0), "curated")
    assert normalized.min_cgpa == 7.0
    assert normalized.max_backlogs == 0
    assert not hasattr(normalized, "eligibility_state")


def test_normalize_job_is_idempotent() -> None:
    once = normalize_job(make_raw(), "curated")
    twice = normalize_job(make_raw(), "curated")
    assert once.model_dump() == twice.model_dump()
