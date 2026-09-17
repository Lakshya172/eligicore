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

### Week 5 — PR 5A: Deterministic matching foundation *(in review, not merged)*

#### Added

- **`app/services/matching_engine.py`** — service only, no endpoint. Narrow inputs (candidate
  skills plus experience titles and descriptions; job role title, description and required
  skills), skill comparison by canonical key, a custom tokenizer, TF-IDF fitted on the whole
  catalogue and never on the candidate, cosine similarity reported as a 0–100 score with one
  decimal or `null` when there is nothing to compare, separate skill coverage, the top five
  shared terms, deterministic template explanations and a score/null/job-id ordering key.
  `MATCHING_VERSION` 1.
- `skill_comparison_key` in the candidate normalizer.
- **`scikit-learn==1.7.2`** (approved stack, §9), pinned exactly.
- **121 new tests** (736 total) and a 36-mutation run, all caught.

#### Fixed

- `normalize_skill(".NET")` returned `"NET"`. A dot is now trimmed from the end only, and
  `NET`/`dotnet` canonicalize to `.NET`, so `POST /api/v1/candidates/normalize` returns `.NET`.

#### Decided

- **ADR-020** match scoring · **ADR-021** skill comparison for matching.

#### Not in this change

- No recommendation endpoint, no `/matching/score`, no eligibility, AI or database change.

---

## Checkpoint 4 — Week 4: Eligibility Intelligence

**Date:** 2026-09-17 · **Commit on `main`:** `f56d7df` · **Status:** Stable
**Produced by:** PR #9 (`4a5cb84`, deterministic engine — see Checkpoint 4A) + PR #11 (`f56d7df`,
AI-assisted field relatedness)
**Full SHA:** `f56d7dfabeeb8a7addac693d2c7552b0c1fc4e76` · **CI:** `test` success ·
**Tests:** 615 passing from `main` (Weeks 1–3's 328 and PR 4A's 196 unchanged) · **Mutations:** 27/27 caught

Week 4 as a whole: deterministic eligibility with final authority, a typed degree-level
requirement, five-state verdicts, and an AI stage that may only resolve an ambiguous field of
study — failing closed, never producing `NOT_ELIGIBLE`, and never receiving or persisting
candidate data beyond the field string. Checkpoint 4A below records the deterministic half.

### PR 4B — AI-assisted field relatedness

#### Added

- **`AIProvider.assess_field_relatedness(field_of_study, allowed_fields)`** returning a strictly
  validated `FieldRelatednessAssessment` (`RELATED` / `NOT_RELATED` / `UNCERTAIN`, confidence,
  reason). Implemented by the mock — `UNCERTAIN`/LOW by default — and by Gemini through the
  existing httpx transport with a new prompt file.
- **`app/services/eligibility_ai.py`** — the second stage. Consults AI only for a non-exact field
  of study on a job with no verified hard failure; de-duplicates identical questions per request;
  at most 4 concurrent calls. `POST /api/v1/eligibility/check` uses it; the API shape is unchanged.
- **Lazy AI service** (`AIService(builder=...)`, `get_lazy_ai_service`) — requests needing no AI
  never construct a provider.
- Reason codes `AI_FIELD_RELATED`, `AI_FIELD_NOT_RELATED`, `AI_ASSESSMENT_INCONCLUSIVE`,
  `AI_ASSESSMENT_UNAVAILABLE`.
- **91 new tests** (615 total), including literal zero-call and zero-construction assertions and
  captured-request privacy checks. 27 mutations, all caught.

#### Changed

- `ENGINE_VERSION` 1 → 2: an ambiguous field may now resolve to `LIKELY_ELIGIBLE` or
  `NEEDS_REVIEW` with an AI-reasoned entry.

#### Decided

- **ADR-019** AI-assisted field relatedness. **C-14:** empty `allowed_fields` stays omitted.

#### Known limitations

- Gemini's relatedness call has not been exercised against the live service, and the Gemini model
  identifier is unconfirmed.
- The default mock provider stays conservative (`UNCERTAIN`/LOW), so ambiguous fields remain `UNKNOWN`.
- AI "related" judgements are the provider's interpretation; they are labelled `ai_reasoning`,
  capped at MEDIUM, and never make a verdict `ELIGIBLE`.
- PostgreSQL has not been verified; migrations have run on SQLite only.

#### Documentation

- The OpenAPI "Current status" text in `app/main.py`, stale at `f56d7df`, now describes the Week 4
  implementation. Description string only; no behaviour change.

---

## Checkpoint 4A — Week 4, PR 4A: Deterministic Eligibility Engine *(intermediate)*

**Date:** 2026-09-17 · **Commit on `main`:** `4a5cb84` · **Status:** Stable — intermediate
**Produced by:** PR #9 (`feature/week-4-eligibility-engine`, 6 commits)
**Full SHA:** `4a5cb844d1aa4ca4aa3e0906481d0d91c8fc67d4` · **CI:** `test` success ·
**Tests:** 524 passing from `main` (Weeks 1–3's 328 unchanged)

This is **not Checkpoint 4**. Checkpoint 4 is reserved for Week 4 as a whole and follows PR 4B.

#### Added

- **`POST /api/v1/eligibility/check`** — evaluates a supplied profile against up to 50 catalogue
  jobs and returns, per job, a five-state verdict with a per-requirement breakdown and a summary.
  Stateless: the catalogue is read, nothing is written, the profile is not echoed.
- **Deterministic engine** — `app/services/eligibility_engine.py`. `MIN_CGPA` (same scale only),
  `GRAD_YEAR_WINDOW` (inclusive), `MAX_BACKLOGS`, `MIN_DEGREE_LEVEL`, and the exact-match portion
  of `ALLOWED_FIELDS`. Missing or invalid data is `UNKNOWN`, never `FAIL`, never defaulted.
- **`jobs.min_degree_level`** — nullable, typed with `DegreeLevel`; additive migration
  `b3e8d2c61a47` with a CHECK constraint. Two curated jobs now require `BACHELORS`.
- **196 new tests** (524 total; the existing 328 unchanged), mutation-verified against 13
  deliberate breakages.

#### Decided

- **ADR-017** Eligibility states and verdict precedence (C-9, C-13, R-2, R-4)
- **ADR-018** Requirement inputs: same-scale grades, qualification selection, degree level,
  exact-match fields, batch cap (C-10, C-12, A-1, A-2, A-4)

#### Fixed

- The Week 1 `NormalizedGrade` docstring claimed a linear `cgpa / max` fraction made
  cross-scale grade comparison possible. It does not; the docstring is corrected (C-12).

#### Known limitations

- No AI stage yet: a field of study that is not an exact match stays `UNKNOWN`, so such jobs
  resolve to `NEEDS_REVIEW` at best. PR 4B is approved and not started.
- Multi-entry profiles whose education levels were never set resolve per-qualification
  requirements to `UNKNOWN` (ADR-018 accepted cost).
- Free-text `requirements.notes` are disclosed as not evaluated, never interpreted.
- Migration `b3e8d2c61a47` verified on SQLite only.
- QG-002 item 4 (mock provider call count is zero after a hard failure) is deferred to PR 4B: no
  AI call path exists yet. The structural guard is tested and mutation-verified.

---

## Checkpoint 3 — Week 3: Job Schema, Adapters and Ingestion

**Date:** 2026-09-10 · **Commit on `main`:** `2cfd4f0` · **Status:** Stable
**Produced by:** PR #6 (`f538015`, implementation) + PR #7 (`2cfd4f0`, verification repairs)
**Full SHA:** `2cfd4f0276b60de393ec604afc10b3c52f483ca7` · **CI:** `test` success ·
**Tests:** 328 passing from `main` (Weeks 1–2's 203 unchanged)

The checkpoint is at PR #7, not PR #6. At `f538015` the database still accepted
`status='NOT_A_STATE'`, so the four-state job status was a convention rather than a guarantee,
and the failed-ingestion path was untested.

### Added

- **Operational models** — `Job` and `IngestionState`, the first tables in the project
- **Migration `54a85d64881e`** — the entire server-side schema; verified upgrade, downgrade,
  re-upgrade, and upgrade against a database holding data
- **Adapter layer** — `JobSourceAdapter` interface and `CuratedJobAdapter`, with 5 synthetic
  curated jobs
- **Normalization and canonical hashing** — `app/services/job_normalizer.py`, implementing the
  dossier §10.2 deduplication rule over canonicalized fields rather than raw posting text
- **Ingestion** — `app/services/job_ingestion.py`: dedup, upsert, authoritative-disappearance
  handling, and one `ingestion_state` row per source
- **Jobs API** — `GET /api/v1/jobs` and `GET /api/v1/jobs/{id}`, with only the filters Weeks 4–5
  justify
- 115 new tests

### Decided

- **ADR-014** Job status: the dossier's four-state enum is stored, `is_active` is derived
- **ADR-015** `ingestion_state`: one row per source, no run log, no hash ledger (closes D-4)
- **ADR-016** Phase 1 local personal-data store at `~/.eligicore/` — **recorded, not implemented**

### Changed

- Privacy guards moved from "zero tables" to an **allowlist**. The old assertion held only
  because no table existed; an allowlist is stricter, catching a personal-data table under any
  unanticipated name.

### Fixed (PR #7)

- **The four-state job status was not enforced by the database.** SQLAlchemy 2.0 defaults
  `create_constraint=False`, so the enum columns were bare `VARCHAR`. Repair migration
  `7c2f1a9b4d30` adds CHECK constraints; `54a85d64881e` is left byte-identical because amending
  a shipped migration would leave already-migrated databases unconstrained.
- **The failed-ingestion path was untested.** A failed fetch must never be read as "this source
  has no jobs" — otherwise a network blip closes the whole catalogue, silently.

### Known limitations

- `POST /api/v1/jobs/ingest` is in the dossier but not in the approved Week 3 API scope.
  Ingestion is implemented and tested as a service; no trigger endpoint is exposed.
- No PostgreSQL run yet — the migration chain is portable by construction but verified only on
  SQLite. `batch_alter_table` in particular has never run against PostgreSQL.
- CHECK constraints are not autogenerate-detected, so a future enum member added to a model
  will not be caught by `alembic check` and needs a hand-written migration.
- `EXPIRED` and `UNKNOWN` job statuses are modelled but set by no code path.

### Not included

Eligibility, matching, recommendations, application preparation, export, frontend, scraping,
authentication.

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
