# ADR-016 — Phase 1 local personal-data store at `~/.eligicore/`

**Status:** Accepted — **recorded, not implemented** · **Date:** 2026-09-10
**Decided by:** project owner · **Extends:** ADR-001, ADR-002 · **Enforces:** INV-1

> **Nothing in this ADR is built.** Week 3 is job ingestion; it touches no personal data. This
> records the decision so it is settled before the phase that needs it, per the instruction to
> record the architecture decision without building unnecessary storage.

---

## Context

ADR-001 established that personal candidate data lives on the user's device, and the dossier
(§8.1a, §10.1) names **IndexedDB** as the store, with localStorage for small preferences.

IndexedDB is a browser API. It presupposes the Phase 2 web frontend. Phase 1 is an API with no
frontend, so a client exercising it today — a script, a CLI, a test harness — has nowhere the
dossier names to put a profile.

## Decision

**The Phase 1 local personal-data store is the user's own filesystem, at `~/.eligicore/`:**

```
~/.eligicore/
├── profile.json        candidate profile
├── evaluations.json    eligibility and matching results
├── tracking.json       application status
└── resumes/            resume files
```

**Local-only. This must never become server-side personal-data persistence.**

## Why this is not a contradiction of the dossier

IndexedDB and `~/.eligicore/` are two mechanisms for the same architectural commitment: the
user's personal data lives on the user's own device, and the backend is a processing service
rather than a personal-data store.

ADR-001's substance is *where the data rests* and *who owns it*, not which API writes it. Both
answers are the same here — the user's machine, the user. The dossier names IndexedDB because
it was describing the Phase 2 browser client; it does not follow that a non-browser client has
no local store.

They are complementary, and both may exist: a Phase 2 browser client uses IndexedDB, a CLI or
desktop client uses `~/.eligicore/`. Neither changes the server.

## What does not change

Every consequence of ADR-001 and ADR-002 holds without modification:

- No `candidates`, `applications` or `evaluations` **table** — ADR-011 is untouched, and
  `evaluations.json` is a file on the user's machine, not a server table
- Every personal-data endpoint stays stateless; the client sends what an operation needs
- `candidate_id` remains a client-generated correlation identifier
- Resume files still exist server-side only for the duration of processing (INV-11)

**The server does not read, write, or know about this directory.** It is a client-side
convention. Nothing in `app/` may reference it.

## Consequences

**Positive.** A Phase 1 client has a defined place to persist results, so the local-first model
is exercisable before the frontend exists. Files are inspectable and portable — a user can read,
back up, or delete their own data with ordinary tools, which is a stronger form of ownership
than a browser store.

**Negative / accepted.** No encryption at rest beyond the operating system's file permissions,
and a plain-text profile on a shared machine is readable by anyone with that account. That is a
property of the user's own machine rather than something the backend can fix, but it should be
stated to the user rather than assumed. Two stores across phases means two client
implementations of the same persistence contract.

## Implementation status

**Not implemented, deliberately.** No code in this repository reads or writes `~/.eligicore/`,
and none should until a phase requires a client that persists locally. Building it now would be
speculative storage for a client that does not exist.

## Enforcement

INV-1 · QG-005 · `reviewers/security.md` — specifically, that no server-side code references
this path.
