# ADR-002 — Stateless candidate APIs

**Status:** Accepted · **Date:** 2026-09-10 · **Source:** dossier §11
**Depends on:** ADR-001

## Context

ADR-001 places personal data on the device. An earlier design exposed `GET` and `PATCH` on a
candidate resource, which implies a server-held record and quietly contradicts local-first.

## Decision

**Every endpoint handling personal data is stateless.** The client sends the data an operation
needs, the backend computes and returns a result, and the client persists that result locally.
No endpoint creates a permanent server-side candidate record.

Specific consequences of the shape:

- `GET` and `PATCH` on a candidate resource are **removed**. Retrieval and update happen against
  IndexedDB on the client; the backend is called only when processing is needed.
- Candidate operations are `POST /api/v1/candidates/validate` and `POST .../normalize` — both
  take a profile in the body and return a computed result.
- `/api/v1/recommendations` is `POST`, not `GET`, because the profile travels in the body.
- **There is no application-status endpoint.** Status transitions (`NOT_APPLIED` → `APPLIED` →
  `INTERVIEW` → …) are written directly to IndexedDB by the client. The backend is not involved
  because it holds no application records.

## `candidate_id` semantics

`candidate_id` is a **client-generated stable identifier** used to correlate operations and
results across requests. It is *not* a pointer to a server-side personal-data record. The
client generates it, owns it, and stores it alongside the profile.

## Consequences

**Positive.** The absence of the endpoints is itself the enforcement mechanism — there is no
route through which a profile could be persisted. Horizontal scaling is trivial. No session
state, no user table, no auth needed in Phase 1.

**Negative / accepted costs.** Larger request payloads. The client is responsible for data
durability. Server-side rate limiting cannot key on a trusted user identity.

## Enforcement

INV-1, INV-12 · QG-004, QG-005 · `reviewers/api.md` · `standards/api_design.md`
