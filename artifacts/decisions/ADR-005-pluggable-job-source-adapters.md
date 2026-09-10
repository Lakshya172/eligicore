# ADR-005 — Pluggable job-source adapters

**Status:** Accepted · **Date:** 2026-09-10 · **Source:** dossier §9.3, §6, §16

## Context

Job data acquisition at scale is the hardest unsolved problem in this domain — legally (portal
Terms of Service) and technically (scraping fragility, rate limits, format churn). The dossier
rates it the highest-severity risk in the project.

If that problem is entangled with eligibility and matching, it blocks everything.

## Decision

**Every job source implements the same interface and returns the same normalized shape.** A
curated JSON file, a portal API, and a future scraper are indistinguishable to the rest of the
system.

Phase 1 ships exactly one adapter: `manual_adapter.py`, reading a curated dataset. This is a
deliberate de-risking move, not a placeholder to be rushed past.

## Consequences

**Positive.** Adding a source means writing one class; nothing else changes. Sources can be
enabled or disabled independently. The system is testable with a fake source. The hardest
unsolved problem is isolated behind a stable boundary and can be solved independently later
(Phase 3) without touching downstream code.

**Negative / accepted costs.** The normalized shape has to be designed against sources that do
not exist yet, so it will need revision when real sources arrive. Source-specific richness is
lost at the boundary.

## Normalization and deduplication

Every adapter returns the canonical job representation. Deduplication uses `content_hash`
computed over a **canonicalized** field set — normalized company name, role title, location,
apply URL, source job ID, normalized description and requirements — not raw posting text.
Normalization means lowercasing, collapsing whitespace, stripping punctuation and common
suffixes. Formatting differences between sources must not create duplicate jobs.

`source` plus `source_job_id` remain an exact-match fast path where a source provides stable IDs.

Freshness is tracked via `status` (ACTIVE / EXPIRED / CLOSED / UNKNOWN) and `last_verified_at`.

## Constraint

Any future adapter must operate within the source's Terms of Service. Adapters that require
circumventing anti-bot measures, CAPTCHAs or authentication walls are out of scope — see
ADR-008.

## Enforcement

INV-6 · QG-001 · `reviewers/architect.md`
