# ADR-010 — API versioning under `/api/v1/`

**Status:** Accepted · **Date:** 2026-09-10 · **Source:** dossier §1 (naming conventions), §11

## Context

EligiCore is API-first. A frontend (Phase 2), a browser extension (Phase 2) and possibly
institutional consumers (Phase 5) will depend on the contract. The dossier's own success
criteria include a live public API that a stranger can understand and use.

A public contract that changes shape without notice breaks every consumer at once.

## Decision

**All endpoints live under `/api/v1/`.** The version is in the URL path, fixed by the dossier's
naming conventions alongside the `eligicore` package name, the `ELIGICORE_` environment prefix
and the `eligicore` database name.

## Compatibility rules within v1

Additive changes are permitted without a version bump:

- Adding a new endpoint
- Adding an optional request field
- Adding a response field

Breaking changes require `v2`, they do not get made in place:

- Removing or renaming a request or response field
- Changing a field's type or its semantics
- Making an optional request field required
- Removing an enum value, or changing what an existing one means
- Changing an endpoint's HTTP method or path

**Enum values are part of the contract.** The eligibility states (`ELIGIBLE`,
`LIKELY_ELIGIBLE`, `NEEDS_REVIEW`, `NOT_ELIGIBLE`, `UNKNOWN`), the confidence levels, the
`method` values and the application statuses are all consumer-visible. Adding a state is
additive; changing what one means is breaking.

## Consequences

**Positive.** Consumers can depend on the contract. FastAPI's generated OpenAPI document is the
published contract, so it stays accurate for free. Phase 2 and beyond can be built against v1
without coordination.

**Negative / accepted costs.** Path versioning means a v2 would duplicate routing. Some field
naming mistakes will have to be lived with until a genuine v2 rather than fixed cheaply.

## Note on shape

`/api/v1/recommendations` is not nested under a resource plural like the other routes. This is
intentional and follows from ADR-002 — it is an operation over a supplied profile, not a
collection under a server-held resource.

## Enforcement

INV-12 · QG-004 · `reviewers/api.md` · `standards/api_design.md`
