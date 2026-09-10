# Changelog

All notable changes to EligiCore are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). This project is in
active pre-release development and does **not** yet follow semantic versioning — there is no
released version. Development progresses through **checkpoints**, one per completed and merged
phase.

The first meaningful release milestone will be the **Week 6 MVP checkpoint**, at which point the
dossier considers the system complete and demoable. No release is claimed before then.

---

## [Unreleased]

Nothing pending.

---

## Checkpoint 1 — Week 1: Foundation and Candidate Profile Schema

**Date:** 2026-09-10 · **Branch:** `feature/week-1-foundation` · **Tests:** 86 passing

First product implementation phase. A running FastAPI application, the operational database
foundation, the universal candidate profile schema, and two stateless candidate endpoints.

### Added

- **Application foundation** — `app/config.py` (`ELIGICORE_`-prefixed settings via
  pydantic-settings), `app/database.py` (engine, session factory, declarative `Base`),
  `app/main.py` (application, request-context middleware, sanitized error handlers)
- **Candidate profile schema** — `app/schemas/candidate.py`. Multiple education entries, each
  carrying its own `GradeScale`. `UNKNOWN` is a first-class scale value, never inferred.
- **Normalization service** — `app/services/candidate_normalizer.py`. Skill canonicalization,
  scale-independent grade fractions, gap reporting. No web-framework dependency.
- **Endpoints** — `POST /api/v1/candidates/validate`, `POST /api/v1/candidates/normalize`,
  `GET /api/v1/health`
- **Alembic** — environment initialized and wired to application settings. No migration, because
  Week 1 creates no tables.
- **Tests** — 86, including 9 privacy tests. The unknown-scale rule and the PII-echo guard were
  mutation-verified: deliberately breaking each makes the relevant tests fail.
- **CI** — GitHub Actions: install → import check → no-personal-data-table guard →
  `alembic check` → `pytest`. Runs with no credentials configured.
- **Repository** — `.gitattributes`, `.env.example`, `requirements.txt`, `pytest.ini`

### Privacy

- No `candidates`, `applications` or `evaluations` table exists or is registered, verified by test
- The 422 handler drops Pydantic's `input` and `ctx`, which would otherwise echo submitted
  candidate values back to the caller
- Request logs carry request id, method, path, status and duration only

### Fixed

- `GradeScale` validator moved to `mode="before"` so an explicit `"scale": null` resolves to
  `UNKNOWN` instead of raising a 422. Semantically identical to omitting the field.

### Not included

Resume parsing, AI providers, job ingestion, eligibility evaluation, matching, application
preparation, frontend, authentication, deployment.

---

## Checkpoint 0 — Phase 0: Engineering environment initialized

**Date:** 2026-09-10 · **Branch:** `main`

The AgentOS engineering layer, the repository standard, and the two architectural contradiction
rulings. **No product code.**

### Added

- `AGENTOS.md` — engineering layer entry point, authority hierarchy, session protocol
- `context/` — vision, state, architecture, tech stack, decisions, workflow, memory
- `standards/` — eligibility, security & privacy, AI, API design, code quality, testing
- `reviewers/` — architect, api, security, ai, qa, performance, documentation, release
- `checklists/` — quality gates QG-001 through QG-007
- `artifacts/decisions/` — ADR-001 through ADR-012
- `.agentos/config.yml` — reviewer routing, context loading, the 12 architectural invariants
- `.gitignore` — secrets, personal data, databases, caches
- `README.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `LICENSE`

### Decided

- **ADR-001** Local-first personal data — the backend is a processing service, not a
  personal-data store
- **ADR-002** Stateless candidate APIs — no server-held candidate record
- **ADR-003** Deterministic eligibility precedence — AI never overrides a verified hard failure
- **ADR-004** AI provider abstraction
- **ADR-005** Pluggable job-source adapters
- **ADR-006** Explainable eligibility and matching
- **ADR-007** Truthfulness validation
- **ADR-008** No auto-submit in current scope
- **ADR-009** Database strategy — SQLite → PostgreSQL via SQLAlchemy and Alembic
- **ADR-010** API versioning under `/api/v1/`
- **ADR-011** No server-side candidate or application persistence — **ruling on dossier
  contradiction C-1**; the §8.2 folder listing showing `models/candidate.py` and
  `models/application.py` is stale and those models must not exist
- **ADR-012** `ingestion_state` as an operational model — **ruling on dossier contradiction
  C-2**; ingestion state is legitimate server-side operational data, bounded to adapter run
  history and never holding a `candidate_id`

### Known open questions

- **C-3** — dossier §12.3 refers to a "stored candidate profile"; stale wording under
  local-first. Low impact, relevant at Week 7.
- **C-4 / D-1** — which AI provider is the Phase 1 default. Needed before Week 2.
- **D-4** — whether `ingestion_state` needs its own deduplication-hash ledger given
  `jobs.content_hash`. Deferred to Week 3.
