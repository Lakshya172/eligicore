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
