# ADR-001 — Local-first personal data

**Status:** Accepted · **Date:** 2026-09-10 · **Source:** dossier §8.1a, §8.1b, §10
*Recorded during initialization. The decision itself was made in the dossier, not here.*

## Context

EligiCore handles resumes, contact details, education records, backlog counts and application
history — some of the most sensitive material a student possesses. A conventional backend would
store all of it server-side keyed by a user account.

## Decision

**Personal candidate data lives on the user's device by default.** The backend is a processing
service and an operational job-data service — not a personal-data database.

**On the device (IndexedDB):** candidate profile, resume file and extracted data, preferences,
cached jobs, eligibility results, matching results, application tracking and status, notes,
chat and conversation history, AI memory and context.

**On the server:** job catalogue, adapter and ingestion state, operational logs. Nothing else.

Personal data may pass through the backend for processing and may exist temporarily during it,
but is not intentionally persisted as part of normal operation.

## Consequences

**Positive.** The user owns their resume and application history outright. Server-side exposure
of sensitive personal data is drastically reduced. Results already computed remain available on
the device. Processing architecture, adapters, AI abstraction and endpoint design are unchanged
— only the resting place of personal data moves.

**Negative / accepted costs.** No server-side cross-device sync. No server-side analytics over
candidate data. Every personal-data operation must carry its input in the request, so payloads
are larger. Phase 1 has no frontend, so nothing persists personal data at all yet — tests must
supply profiles in request bodies as a client would.

## Scope of the commitment

This is a design commitment about how the application is built and configured. It is **not** an
absolute guarantee about every layer of underlying infrastructure. Request handling, temporary
storage, infrastructure logs and error telemetry must be *designed and configured* to avoid
retaining unnecessary personal data.

## Revisit conditions

Phase 4 (multi-user platform with authentication and per-user isolation) is the first phase
that would legitimately reopen this. Until an explicit, documented scope change, it holds.

## Enforcement

INV-1, INV-4, INV-11 · QG-005 · `reviewers/security.md` · `standards/security_privacy.md`
