# ADR-012 — `ingestion_state` as an operational model

**Status:** Accepted · **Date:** 2026-09-10
**Type:** Contradiction ruling (resolves **C-2**) · **Ruled by:** project owner
**Depends on:** ADR-005 (adapters), ADR-009 (database strategy) · **Bounded by:** ADR-011, INV-1

---

## The contradiction (C-2)

The dossier's §8.2 folder listing shows no model for ingestion state, while §10.2 requires the
table:

> **Table: `ingestion_state`** — "Adapter run history, last-fetch timestamps, and deduplication
> hashes — required for ingestion to work correctly across runs."

This is the same staleness as C-1: §8.2's listing was not updated alongside the §10 data-design
revision. Here the omission points the opposite way — §8.2 is missing something that is genuinely
needed, rather than including something that must not exist.

## The ruling

**Job ingestion is server-side operational functionality, so its state is legitimately
server-side operational data.** The backend needs it to work correctly across runs — an adapter
must know what it fetched last time.

**Location:** `app/models/ingestion_state.py` — a SQLAlchemy model in the server data layer,
alongside `app/models/job.py`.

This is consistent with the existing architecture and requires no new structure. The server data
layer already exists for exactly this category: operational data that is not personal data
(`context/architecture.md` §1, §2).

## Boundary — what it may and may not contain

**May contain (operational only):**

| Category | Examples |
|---|---|
| Adapter identity | which source/adapter the row describes |
| Run history | run timestamps, last successful fetch time |
| Run outcome | counts of jobs fetched, created, updated, skipped as duplicates |
| Run status | success / partial / failed, plus a sanitized error summary |
| Source cursors | a page token or high-water mark a source requires to resume |

**Must never contain — this is not a style preference:**

- Any candidate profile data, resume content, or PII (INV-1, INV-4)
- Any evaluation, match score, recommendation, or application record
- Any `candidate_id`, or any field correlating ingestion to a specific user
- Any per-user view of the catalogue — ingestion is global and user-agnostic

**`ingestion_state` is a record of what the system did, never of what a person did.** Job
ingestion runs independently of any candidate (dossier §7, Step 4 — "runs independently"), so
there is no legitimate reason for a user identifier to appear in this table. A `candidate_id`
column here would be a defect, not a convenience.

Error summaries must be sanitized. An ingestion failure against a future live source could
otherwise capture response bodies into a stored error field.

## Deliberately not decided here: the deduplication hash ledger

§10.2 lists "deduplication hashes" among `ingestion_state`'s contents, while the `jobs` table
already carries `content_hash` as its deduplication key.

**`jobs.content_hash` is the canonical deduplication index** — that is where §10.2 defines the
dedup semantics and the canonicalization inputs. Whether `ingestion_state` additionally needs
its own hash ledger (for example, to remember hashes of postings seen but deliberately not
stored) is an **implementation question for Week 3**, when ingestion is actually built and the
need is either real or it is not.

It is recorded here as an open sub-decision rather than settled now, because settling it would
mean designing the ingestion engine during Phase 0 cleanup — outside the approved scope. What is
settled: any such ledger stays operational and stays inside the boundary above.

## Consequences

**Positive.** Ingestion can resume correctly across runs and report per-adapter history. The
adapter boundary (ADR-005) stays clean — adapters report outcomes, the model records them.
Removing a source means removing its rows, not migrating anything else.

**Negative / accepted costs.** One more operational table to migrate and keep portable across
SQLite and PostgreSQL (ADR-009). The table grows monotonically with run history and will
eventually want a retention policy — noted, not solved now.

## Status of the model

**Not implemented.** This ADR rules on *where it belongs and what it may hold*. Creating
`app/models/ingestion_state.py` is Week 3 work (job schema, adapters, ingestion) and is not
authorized by this ruling.

## Enforcement

INV-1 · QG-006 (items 1–3) · `reviewers/security.md`, `reviewers/architect.md` ·
`standards/security_privacy.md` §1
