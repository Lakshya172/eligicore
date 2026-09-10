# ADR-014 — Job status model: dossier enum, with `is_active` derived

**Status:** Accepted · **Date:** 2026-09-10 · **Type:** Reconciliation (resolves **C-5**)
**Source:** dossier §10.2 vs the approved Week 3 decision
**Enforces:** INV-3 · **Bounded by:** ADR-009

---

## The tension (C-5)

The approved Week 3 decisions say:

> `is_active = false` for curated jobs that disappear from the authoritative curated dataset.

The dossier §10.2 `jobs` table says:

> | status | Enum | ACTIVE / EXPIRED / CLOSED / UNKNOWN |

A boolean and a four-state enum are not the same model. Taken literally, implementing a bare
`is_active` column would drop three of the dossier's four states.

**Why that would matter, beyond tidiness.** The enum distinguishes *why* a job is no longer
open: `EXPIRED` (the deadline passed), `CLOSED` (the employer withdrew it), `UNKNOWN` (we have
no basis to say). A boolean collapses all three into "not active", and the information is
unrecoverable afterwards. `UNKNOWN` in particular carries the same semantics INV-3 depends on
everywhere else in this system — absence of evidence is not evidence of a specific state.

## Decision

**Store the dossier's `status` enum. Expose `is_active` as a derived value.**

- `Job.status` is `JobStatus` — `ACTIVE`, `EXPIRED`, `CLOSED`, `UNKNOWN` — exactly as the
  dossier specifies. It is the stored truth.
- `Job.is_active` is a read-only property: `status is JobStatus.ACTIVE`. It is also a query
  filter on the jobs endpoint.
- A curated job that disappears from its authoritative source transitions
  `ACTIVE -> CLOSED`, which makes `is_active` false.

**Nothing is overridden.** The dossier's model is implemented as written, and the approved
decision's requirement — disappeared curated jobs become inactive rather than being deleted —
holds exactly, because `is_active` is false for every non-`ACTIVE` status.

## Why `CLOSED` for a disappeared curated job

The curated adapter is *authoritative* for the jobs it supplies — that is the approved wording.
When an authoritative source stops listing a job, the strongest available reading is that the
posting is no longer offered, which is `CLOSED`.

`EXPIRED` was rejected: it asserts a deadline passed, and disappearance is not evidence of that.
`UNKNOWN` was considered and rejected for *authoritative* sources only — an authoritative source
omitting a job is genuine evidence, not an absence of it.

**This distinction is carried on the adapter, not hard-coded.** `JobSourceAdapter.is_authoritative`
declares whether disappearance is meaningful. A future paginated or partial source would set it
false, and jobs missing from one fetch would be left untouched rather than closed. Deactivating
jobs because a paginated API returned page 1 would be a data-loss bug, and the flag exists so
that bug cannot be written by accident.

## Consequences

**Positive.** The dossier's freshness model survives intact for Week 4 and beyond. Callers get
the simple boolean they actually want to filter on. Nothing is deleted — a closed job stays
retrievable with its reason, consistent with ADR-006's rule that ineligible jobs remain
retrievable rather than silently disappearing.

**Negative / accepted.** One more concept than a bare boolean. `is_active` is not stored, so it
cannot be indexed directly — filtering goes through `status`, which is indexed, and the endpoint
translates.

## Revisit conditions

If `EXPIRED` and `UNKNOWN` are still unused by the end of Week 5, the enum is carrying weight it
has not earned and collapsing it is a reasonable simplification — with an ADR.

## Enforcement

QG-006 · `reviewers/architect.md` · covered by tests asserting a disappeared curated job becomes
`CLOSED` and `is_active` false, and that a non-authoritative source's omissions change nothing.
