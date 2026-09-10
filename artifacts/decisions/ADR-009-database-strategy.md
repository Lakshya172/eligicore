# ADR-009 — Database strategy: SQLite → PostgreSQL via SQLAlchemy and Alembic

**Status:** Accepted · **Date:** 2026-09-10 · **Source:** dossier §9, §10.2
**Depends on:** ADR-001 (which determines *what* the database is allowed to hold)

## Context

The server needs durable storage for the job catalogue and ingestion state. Development is
solo, on a laptop; production is a free-tier host. Those two environments want different
database engines.

## Decision

**SQLAlchemy as the ORM, SQLite in development, PostgreSQL in production, Alembic for
migrations.**

The database holds **operational data only**:

| Table | Contents |
|---|---|
| `jobs` | The job catalogue |
| `ingestion_state` | Adapter run history, last-fetch timestamps, dedup hashes |
| operational logs | Request counts, AI usage and cost, error records |

**There is no `candidates` table and no server-side store of evaluations.** Those records live
on the user's device (ADR-001).

## Rationale

**SQLAlchemy** lets the same model code target both engines and keeps database access in Python
objects. **SQLite** requires zero setup and is a single file — ideal for solo development.
**Alembic** versions schema changes as explicit, reviewable scripts rather than relying on table
recreation; necessary because the schema will evolve and because dev and prod engines differ.

## Known risk — parity is not free

The dossier flags this itself: SQLAlchemy *minimizes* but does not *eliminate* engine
differences. JSON column behaviour, enum handling, case sensitivity and type coercion all
differ between SQLite and PostgreSQL.

**Alembic migrations and PostgreSQL compatibility must be validated before production
deployment, not assumed because the SQLite tests pass.** Prefer portable column types. This is
a Week 9 gate, tracked as risk in `context/state.md` and pitfall I-2 in `context/memory.md`.

## Consequences

**Positive.** Zero-setup local development. No database server to run while building. Migration
history is reviewable and is itself portfolio evidence.

**Negative / accepted costs.** Two engines means two behaviours to verify. SQLite's permissive
typing can mask schema errors that PostgreSQL will reject. Migrations must be written
conservatively rather than using engine-specific features.

## Enforcement

QG-006 · `reviewers/architect.md`, `reviewers/security.md`
