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

## Checkpoint 2 — Week 2: Resume Parser and Gemini Flash AI Service Layer

**Date:** 2026-09-10 · **Commit on `main`:** `91dd31d` · **Status:** Stable
**Produced by:** PR #4 (`feature/week-2-resume-ai`, 16 commits), merged 2026-09-10
**Full SHA:** `91dd31d50e7749ad37acf14babd5d1ee90141abd` · **CI:** `test` success ·
**Tests:** 203 passing from `main` (Week 1's 86 unchanged)

### Added

- **AI provider abstraction** — `app/ai/providers/base.py`, plus `errors.py`, `ai_service.py`
  (provider selection and the single point of usage logging), and `prompts/` as files
- **Mock provider** — mandatory and the runtime default, so an unconfigured checkout cannot
  make a paid call. Deterministic, with injectable failure modes.
- **Gemini Flash provider** — the Phase 1 concrete implementation (ADR-013), via the official
  REST API through httpx. The only file that knows Gemini exists.
- **Resume parser** — `app/services/resume_parser.py`: magic-byte format detection, PDF and
  DOCX extraction including table cells, temp-file lifecycle, traceability checking, and
  deterministic confidence rules
- **`POST /api/v1/resumes/parse`** — stateless; the uploaded file is deleted after processing
  on both the success and failure paths
- **QG-008** — quality gate for resume processing and AI extraction
- 117 new tests, none of which make a network call or need an API key

### Decided

- **ADR-013** Google Gemini Flash as the Phase 1 default AI provider, resolving contradiction
  C-4 / decision D-1. Concrete implementation only — ADR-004's abstraction is unchanged.

### Fixed

- **pdfminer logged the literal resume text at DEBUG level.** Found by a privacy test, not by
  inspection: no application log statement was involved, so raising the root log level would
  have dumped candidate data into the logs. Library loggers are now pinned at WARNING with
  propagation disabled.

### Known limitations

- The Gemini provider has **never been executed against the live service** — no API key exists
  in this environment. The default model identifier is a configured default, not a verified one.
- Traceability checking covers skills only; free-text fields are legitimately paraphrased and
  cannot be verified by substring matching.
- The spaCy deterministic fallback is not implemented, so every parse currently makes an AI call.

### Not included

Job ingestion, job adapters, eligibility, matching, recommendations, application preparation,
frontend, authentication, deployment.

---

## Checkpoint 1 — Week 1: Foundation and Candidate Profile Schema

**Date:** 2026-09-10 · **Commit on `main`:** `2e79454` · **Status:** Stable
**Produced by:** PR #2 (`feature/week-1-foundation`, 11 commits), merged 2026-09-10
**Full SHA:** `2e79454f787019ff29af39fcfd285aee59c8bc77` · **CI:** `test` success · **Tests:** 86 passing from `main`

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

**Date:** 2026-09-10 · **Commit on `main`:** `e8c68b7` · **Status:** Stable
Built over two commits (`7f7abbb`, then `e8c68b7`). The checkpoint is the end state,
`e8c68b7` — a single commit, not the range. CI and tests read n/a: neither existed yet,
because Phase 0 contained no product code.

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
