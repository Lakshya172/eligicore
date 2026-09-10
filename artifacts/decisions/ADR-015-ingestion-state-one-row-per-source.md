# ADR-015 — `ingestion_state`: one row per source, no run log, no hash ledger

**Status:** Accepted · **Date:** 2026-09-10 · **Decided by:** project owner
**Type:** Narrowing (resolves **C-6**, and closes deferred decision **D-4**)
**Supersedes the open question in:** ADR-012 § Deliberately not decided

---

## Context

ADR-012 established that `ingestion_state` is legitimate operational data and bounded what it
may hold, but deliberately left two things open until ingestion was actually built:

- whether it needs its own deduplication-hash ledger, given `jobs.content_hash` already exists
- what shape "adapter run history" should take

The dossier §10.2 describes the table as:

> Adapter run history, last-fetch timestamps, and deduplication hashes — required for ingestion
> to work correctly across runs.

## The tension (C-6)

The approved Week 3 decisions narrow that on both counts:

> One `ingestion_state` row per source. · No historical hash ledger. · No ingestion-run history.

Read literally, "adapter run history" suggests a log with one row per run. The approved decision
keeps one row per *source*, overwritten each run.

## Decision

**One row per source. Current state only. No run log. No hash ledger.**

Each row holds the outcome of that source's most recent run:

| Field | Purpose |
|---|---|
| `source` | Primary key — one row per source, by construction |
| `last_run_at`, `last_success_at` | Freshness and staleness detection |
| `last_status` | `SUCCESS` / `PARTIAL` / `FAILED` |
| `last_error` | Sanitized category only, never a raw payload |
| `jobs_seen`, `jobs_created`, `jobs_updated`, `jobs_deactivated` | Last run's outcome |
| `cursor` | High-water mark for sources that need one to resume |

## Why this does not override the dossier

The dossier states the table's *purpose* in the same sentence as its contents: **"required for
ingestion to work correctly across runs."** That purpose is fully served by current state. An
adapter needs to know what happened last time; it does not need to know what happened five runs
ago in order to run correctly now.

What is genuinely dropped is the historical *log* — the ability to answer "how did ingestion
behave last Tuesday". That is observability, not correctness, and the owner has approved
deferring it. Recorded as a narrowing rather than presented as equivalent.

## Why no hash ledger (closing D-4)

`jobs.content_hash` is already the canonical deduplication index, and it is where the dossier
defines the dedup semantics and canonicalization inputs. A second hash store would be a copy of
that data with its own opportunity to drift out of sync.

The only capability a ledger would add is remembering hashes of postings *seen but deliberately
not stored*. Phase 1 stores every job an adapter returns, so that set is empty. Building an
index for a set that is always empty is speculative.

## Consequences

**Positive.** The table stays small and bounded — it cannot grow without new sources being
added, so it needs no retention policy. Deduplication has exactly one source of truth. Removing
a source means deleting one row.

**Negative / accepted.** No historical trend or audit of ingestion behaviour; a failure is
visible only until the next run overwrites it. If ingestion reliability later needs
investigating, that is a real gap — and adding a separate append-only run-log table would be an
additive change requiring no alteration to this one.

## Boundary, unchanged from ADR-012

Operational data only. **Never** a `candidate_id`, profile data, resume content, evaluation,
match score, or any per-user view of the catalogue. Ingestion runs independently of any
candidate (dossier §7 step 4), so a user identifier here would be a defect (INV-1).

## Enforcement

INV-1 · QG-005, QG-006 · `reviewers/architect.md`, `reviewers/security.md`
