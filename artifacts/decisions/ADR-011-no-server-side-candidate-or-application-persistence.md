# ADR-011 — No server-side candidate or application persistence

**Status:** Accepted · **Date:** 2026-09-10
**Type:** Contradiction ruling (resolves **C-1**) · **Ruled by:** project owner
**Reinforces:** ADR-001, ADR-002 · **Enforces:** INV-1

> **This ADR exists specifically so a future session cannot reintroduce these tables by
> reading the dossier's folder listing at face value.** If you arrived here from
> `EligiCore_Dossier_update.md` §8.2, read this whole file before creating any model.

---

## The contradiction (C-1)

The dossier contradicts itself on the project's central architectural claim.

**§8.2 — Project folder structure** lists SQLAlchemy database models:

```
├── models/                  # SQLAlchemy database models
│   ├── candidate.py
│   ├── job.py
│   └── application.py
```

**§10.2 — Server-side tables** states the opposite:

> "there is no server-side `candidates` table and no server-side store of evaluations by
> default. Those records live on the user's device."

Both cannot be true. This was surfaced during Phase 0 initialization, reported, and left
unresolved pending an owner ruling rather than silently decided.

## The ruling

**The local-first architecture has authority.** §8.2's model listing is **stale** — it predates
the local-first revision recorded in §8.1a and §10.2 and was not updated with it.

Therefore, and without exception:

| Forbidden | Status |
|---|---|
| `app/models/candidate.py` — any SQLAlchemy model representing a candidate or profile | **Must not exist** |
| `app/models/application.py` — any SQLAlchemy persistence model for applications or their status | **Must not exist** |
| A `candidates` table, or any table holding profile data | **Must not exist** |
| An `applications` table, or any table holding application records or status | **Must not exist** |
| An `evaluations` table, or any server-side store of eligibility/matching results | **Must not exist** |
| Any Alembic migration creating the above | **Must not be written** |

**Candidate profile data and application-tracking data remain client-owned.** Candidate APIs
remain stateless processing APIs. Application status remains client-side, written directly to
IndexedDB by the client, with no backend involvement and no endpoint.

## What this does *not* forbid

The ruling is about **persistence**, not about the domain existing in code:

- **Pydantic schemas are required and unaffected.** `app/schemas/candidate.py` defines the
  request and response shapes for the stateless endpoints. A Pydantic model is a data contract,
  not a table.
- Candidate data in memory during a request is fine — that is what processing is.
- A resume file existing temporarily during parsing is fine, subject to INV-11 (deleted on both
  the success and failure paths).

The distinction that matters: **schemas describe data in flight; models describe data at rest.**
EligiCore has candidate data in flight and never at rest on the server.

## Consequences

**Positive.** The contradiction is closed in favour of the architecture the dossier actually
argues for across §§6, 8.1a, 10, 11 and 14. The absence of these models is self-enforcing —
there is no table to write to. The differentiator is protected against the most likely form of
erosion, which is not a decision to abandon it but a convenient shortcut taken mid-task.

**Negative / accepted costs.** Tests must construct profile fixtures and pass them in request
bodies exactly as a client would; this feels less convenient than seeding a table, and that
inconvenience is the correct trade. Anyone reading §8.2 in isolation will be misled — hence
this ADR, and hence the standing note in `context/architecture.md` §10.

## Revisit conditions

Phase 4 (multi-user platform with authentication and per-user isolation) is the first phase
that could legitimately reopen this, and it would require its own ADR superseding this one.
Until then, a task that appears to require one of these tables is a misunderstood task — stop
and report it rather than creating the model.

## Enforcement

INV-1 · QG-005 (items 1–6), QG-006 (items 1–3) · `reviewers/security.md` (automatic FAIL) ·
`reviewers/architect.md` (automatic FAIL) · `standards/security_privacy.md` §1
