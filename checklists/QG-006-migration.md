# QG-006 — Database Model or Migration

**Applies:** a SQLAlchemy model or Alembic migration is added or changed
**Reviewers:** architect + security + qa

## Entry criteria

QG-001 passed. A model or migration changed.

## Checklist

### Data ownership (INV-1, ADR-001)

| # | Requirement | Evidence |
|---|---|---|
| 1 | The table holds **operational data only** — job catalogue, ingestion state, or logs | Model file |
| 2 | No table represents a candidate, profile, evaluation, or application | Migration diff |
| 3 | No column stores resume text, contact details, or other PII | Column list |

### Migration correctness (ADR-009)

| # | Requirement | Evidence |
|---|---|---|
| 4 | An Alembic migration exists — the schema was not changed by table recreation | Migration path |
| 5 | The migration applies cleanly on a fresh database | Command output |
| 6 | The migration applies cleanly on an existing database with data | Command output |
| 7 | A downgrade path exists and works | Command output |
| 8 | Column types are portable — no reliance on SQLite-specific behaviour | Model review |
| 9 | JSON columns, enums and booleans are declared portably across SQLite and PostgreSQL | Model review |
| 10 | Nullability and defaults are explicit, not incidental | Model review |
| 11 | Indexes exist on columns actually filtered — `content_hash`, `source` + `source_job_id`, `status` | Model review |
| 12 | The migration is reviewed as written, not accepted blindly from autogenerate | Diff read |

### Before deployment

| # | Requirement | Evidence |
|---|---|---|
| 13 | Verified against **PostgreSQL**, not only SQLite — or explicitly deferred to QG-007 with a note in `state.md` | Command output, or the deferral note |

## Exit decision

- **PASS** — all items evidenced.
- **FAIL** — any of items 1–8, 12 unmet.
- **PASS WITH WARNINGS** — item 13 deferred to deployment, provided the deferral is recorded in
  `context/state.md`.

## Note on item 13

The dossier flags SQLite/PostgreSQL parity as a known risk in its own stack section. SQLite's
permissive typing will accept schemas PostgreSQL rejects. Deferring the check is acceptable
during development; **assuming parity is not**, and it must not still be deferred at QG-007.
