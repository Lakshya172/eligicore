# Project State — EligiCore

> **MANDATORY first read for every session.**
> **Rule:** nothing is marked complete because the dossier plans it. Only because it exists,
> runs, and is tested. Planned ≠ done.
> **Update:** at the end of every session that changes the repository.

---

## Snapshot

| Field | Value |
|---|---|
| **Date** | 2026-09-21 |
| **Phase** | **Week 7 — Application preparation · IN PROGRESS.** Slice 7A (deterministic truthfulness validator) is **complete and merged**; Slice 7B (`POST /api/v1/applications/prepare`) is **NOT started**. Week 6 remains the dossier's declared safe stopping point (§15), and **Checkpoint 6 remains the current checkpoint** — Week 7 has produced none. |
| **Roadmap position** | **Weeks 1–6 complete and merged.** Week 6 delivered as PR 6A (Checkpoint 6A) + PR 6B (Checkpoint 6). **Week 7 is partially delivered:** its design gate is ruled (**ADR-025**, PR #23, amended by PR #25) and **Slice 7A is merged** (PR #24); **Slice 7B is NOT started**. **Weeks 8–10 NOT started.** `/matching/score` and HTTP `/jobs/ingest` remain explicitly deferred (C-25, ADR-023 §11, ADR-024); `/applications/prepare` is specified by ADR-025 and unimplemented. |
| **Health** | 🟢 GREEN — 1259 tests passing on `main`; mutations 42/42 (7A), 23/23 (6B), 30/30 (6A), 40/40 (5B), 36/36 (5A), 27/27 (Week 4); 33/33 live checks; CI green; quickstart verified from a fresh clone of `main` in 72 s; no open blockers |
| **Stable branch** | `main` |
| **Current checkpoint** | **Checkpoint 6** — Week 6 MVP (final) — `13eb8325149cab60a039534631265803250b767a`. `main` is six merges ahead at `f5b81f0de65d28b8418b7ba0283e20a9a295cf44` — PR #21 (OpenAPI status), PR #22 (Week 6 state cleanup), PR #23 (ADR-025), PR #24 (Slice 7A validator), PR #25 (ADR-025 evidence-boundary correction), PR #26 (docstring correction), all merged. **None created a checkpoint: there is no Checkpoint 7.** |
| **Produced by** | PR #17 (`0125703`, Excel tracker export) + PR #19 (`13eb832`, demo path and full-flow test), both **MERGED**. Checkpoint 6A remains the intermediate Week 6 checkpoint; Checkpoint 5 (`0aaaa1d`) remains the final Week 5 checkpoint. |
| **Rollback target** | Checkpoint 6 first; Checkpoint 6A by reverting PR #19 (no database step); Checkpoint 5 by also reverting PR #17 (no database step); Checkpoint 5A by also reverting PR #15 (no database step); Checkpoint 4 by also reverting PR #13; Checkpoint 4A by also reverting PR #11; Checkpoint 3 also needs `alembic downgrade 7c2f1a9b4d30`; below Checkpoint 3 also needs `alembic downgrade base`. |
| **Next milestone** | **Week 7 Slice 7B — the `POST /api/v1/applications/prepare` endpoint and package orchestration. Designed (ADR-025) but NOT started and NOT authorized**; it begins only on explicit instruction. Everything after Week 6 is enhancement (dossier §15). |
| **AI provider** | Phase 1 default: **Google Gemini Flash** (ADR-013). Runtime default is `mock`. |
| **Repository** | `Lakshya172/eligicore` (public). Default branch `main`, protected. CI on push and PR. |
| **Python** | 3.12.10 local, 3.12 in CI (dossier requires 3.11+ — satisfied) |

---

## Completed

| Item | Evidence |
|---|---|
| Product definition, scope, architecture planning | `EligiCore_Dossier_update.md` (872 lines, v1.0 Final) |
| AgentOS engineering layer initialized | `AGENTOS.md`, `context/`, `standards/`, `reviewers/`, `checklists/`, `artifacts/decisions/` |
| 10 foundational ADRs recorded from dossier decisions | `artifacts/decisions/ADR-001..010` |
| **Git repository initialized** | `.git/` on branch `master`; `.gitignore` written and verified (`.env` ignored, `.env.example` tracked, `.gitkeep` tracked). No commits, no remote. |
| **Contradiction C-1 ruled** | `ADR-011` — no server-side candidate or application persistence |
| **Contradiction C-2 ruled** | `ADR-012` — `ingestion_state` is a legitimate operational model |
| **GitHub repository established** | `Lakshya172/eligicore`, public, `main` protected (PR required, `test` check required, force-push and deletion blocked). CI workflow runs install → import check → no-personal-data-table guard → `alembic check` → `pytest`. |
| **Week 1 — application foundation** | `app/config.py` (ELIGICORE_ settings), `app/database.py` (engine, session factory, `Base` — **zero models**), `app/main.py` (app, middleware, sanitized error handlers) |
| **Week 1 — candidate schema** | `app/schemas/candidate.py` — universal profile, multiple education entries, explicit `GradeScale` with first-class `UNKNOWN` |
| **Week 1 — normalization service** | `app/services/candidate_normalizer.py` — skill canonicalization, scale-independent grade fractions, gap reporting. No FastAPI import; verified to run headless. |
| **Week 1 — stateless endpoints** | `POST /api/v1/candidates/validate`, `POST /api/v1/candidates/normalize`, `GET /api/v1/health` |
| **Week 1 — Alembic** | Environment initialized and wired to settings. **No migration exists** — Week 1 creates no tables; `alembic check` reports no pending operations. |
| **Week 1 — tests** | 86 passing. Includes 9 privacy tests and mutation-verified coverage of the unknown-scale rule and the PII-echo guard. |
| **AI provider decision** | `ADR-013` — Gemini Flash as the Phase 1 default, resolving C-4 / D-1. Concrete implementation only; ADR-004's abstraction unchanged. |
| **Week 2 — AI abstraction** | `app/ai/providers/base.py` (interface), `mock.py` (mandatory, default), `gemini.py` (Phase 1 concrete), `errors.py`, `ai_service.py` (selection + usage logging), `prompts/` (files, not inline strings) |
| **Week 2 — resume parser** | `app/services/resume_parser.py` — magic-byte format detection, pdfplumber/python-docx extraction incl. table cells, temp-file lifecycle, traceability checking, deterministic confidence rules |
| **Week 2 — endpoint** | `POST /api/v1/resumes/parse` — stateless, file deleted after processing on both paths |
| **Week 2 — tests** | 117 new (203 total). Week 1's 86 unchanged and passing. Suite runs offline with no API key. |
| **Week 2 — privacy fix** | pdfminer logged resume text at DEBUG; library loggers now pinned at WARNING with propagation off. Found by test, mutation-verified. |
| **Week 3 design decisions** | `ADR-014` job status model, `ADR-015` ingestion state (closes D-4), `ADR-016` local store recorded-not-built. Four dossier tensions reconciled without overriding it (C-5..C-8). |
| **Week 3 — operational models** | `app/models/job.py`, `app/models/ingestion_state.py` — the first tables. Migration `54a85d64881e`, verified upgrade/downgrade/re-upgrade with data. |
| **Week 3 — adapters** | `JobSourceAdapter` interface (`is_authoritative` defaults False), `CuratedJobAdapter`, 5 synthetic curated jobs |
| **Week 3 — normalization + hashing** | `app/services/job_normalizer.py` — canonicalized dedup per dossier §10.2, never raw text |
| **Week 3 — ingestion** | `app/services/job_ingestion.py` — dedup, upsert, disappearance→CLOSED, one state row per source |
| **Week 3 — jobs API** | `GET /api/v1/jobs`, `GET /api/v1/jobs/{id}` — minimal filters only |
| **Week 3 — tests** | 125 new (328 total). Weeks 1–2's 203 unchanged. Four mutations verified. |
| **Week 3 — enum enforcement** | Migration `7c2f1a9b4d30` adds DB-level CHECK constraints, so ADR-014's four states are a guarantee rather than a convention. Found during final verification; `f538015` lacked it. |
| **QG-008** | New quality gate for resume processing and AI extraction |
| **Week 4 design gate** | Rulings C-9..C-13, A-1..A-4, R-2, R-4 recorded as **ADR-017** (states and precedence) and **ADR-018** (requirement inputs). |
| **Week 4 PR 4A — `min_degree_level`** *(merged, PR #9)* | Nullable typed column; additive migration `b3e8d2c61a47`; RawJob/NormalizedJob/JobRead/ingestion carry it; two curated jobs require BACHELORS. Merged migrations untouched. |
| **Week 4 PR 4A — deterministic engine** *(merged, PR #9)* | `app/services/eligibility_engine.py` — MIN_CGPA (same scale only), GRAD_YEAR_WINDOW, MAX_BACKLOGS, MIN_DEGREE_LEVEL, ALLOWED_FIELDS exact match; single-qualification selection; five-state precedence; structural hard-failure guard for the future AI stage. |
| **Week 4 PR 4A — endpoint** *(merged, PR #9)* | `POST /api/v1/eligibility/check` — stateless, at most 50 ids, de-duplicated, `not_found_job_ids`, read-only on the catalogue. |
| **Week 4 PR 4A — tests** *(merged, PR #9)* | 196 new (524 total); 328 existing unchanged. 13 mutations verified caught. |
| **Week 4 PR 4B — AI field relatedness** *(merged, PR #11)* | `AIProvider.assess_field_relatedness`; conservative mock (UNCERTAIN/LOW default); Gemini via the existing transport and a prompt file; `app/services/eligibility_ai.py` as the second stage; lazy provider construction; request-scoped de-duplication; fail-closed `UNKNOWN`; confidence capped at MEDIUM; `ENGINE_VERSION` 2. ADR-019. |
| **Week 4 PR 4B — tests** *(merged, PR #11)* | 91 new (615 total). Literal zero-call and zero-build assertions; captured-request privacy checks. 27/27 mutations caught. |
| **Checkpoint 4** | Final Week 4 checkpoint at `f56d7df`, verified post-merge (see `context/workflow.md`). |
| **Week 5 design gate** | Approved 2026-09-17; rulings C-17, C-18 recorded as **ADR-020** (match scoring) and **ADR-021** (skill comparison). Split into PR 5A and PR 5B. |
| **Week 5 PR 5A — matching engine** *(merged, PR #13)* | `app/services/matching_engine.py` — narrow inputs, skill comparison, custom tokenizer, `skill:` namespace, TF-IDF fitted on the whole catalogue (never the candidate), cosine 0–100 or `null`, skill coverage, top terms, template explanations, ordering key; `scikit-learn==1.7.2`; `.NET` normalizer correction. Service only. |
| **Week 5 PR 5A — tests** *(merged, PR #13)* | 121 new (736 total); 615 existing unchanged. 36/36 mutations caught. |
| **Checkpoint 5A** | Intermediate Week 5 checkpoint at `05534af`, verified post-merge (see `context/workflow.md`). |
| **Week 5B design gate** | Approved; rulings C-19..C-22 recorded as **ADR-022** (recommendation orchestration); ADR-020 §5 amended for the corpus fingerprint. |
| **Week 5 PR 5B — recommendations** *(merged, PR #15)* | `POST /api/v1/recommendations` — `app/services/recommendations.py` orchestrates one Week 4 eligibility pass and one Week 5A matching pass over the whole catalogue; groups `ranked` / `needs_review` / `not_eligible` / `not_open`; default ACTIVE + UNKNOWN scope capped at 50 with disclosure; explicit ids of any status; `corpus_fingerprint`; composed explanations. |
| **Week 5 PR 5B — tests** *(merged, PR #15)* | 114 new (850 total); existing tests unchanged. 40/40 mutations caught. |
| **Checkpoint 5** | Final Week 5 checkpoint at `0aaaa1d`, verified post-merge (see `context/workflow.md`). |
| **Week 6 design gate** | Approved 2026-09-19; rulings C-23..C-29 and A-25..A-36 recorded as **ADR-023** (tracker export contract). Split into PR 6A (export) and PR 6B (polish). |
| **Week 6 PR 6A — tracker export** *(merged, PR #17)* | `POST /api/v1/applications/export`: client-supplied tracker rows (1–500, unique `job_id`) rendered in memory to `.xlsx` — `Tracker` sheet in request order, optional `Requirements` sheet; nullable score as an empty cell; real Excel dates; formula-injection defence; fixed metadata and filename; binary 200 (documented API exception, C-23), standard JSON errors. No database, AI, engine or model change. `openpyxl==3.1.5`, `et-xmlfile==2.0.0`. OpenAPI status text corrected (C-29). |
| **Week 6 PR 6A — tests** *(merged, PR #17)* | 225 new (1075 total); 850 existing unchanged. 30/30 mutations caught. Opened cleanly in Microsoft Excel. |
| **Checkpoint 6A** | Intermediate Week 6 checkpoint at `0125703`, verified post-merge (see `context/workflow.md`). |
| **Week 6B design gate** | Approved 2026-09-20; rulings C-30..C-34 and A-37..A-52 recorded as **ADR-024** (Week 6 MVP scope: local seed command, 40-job catalogue, full-flow test, quickstart). |
| **Week 6 PR 6B — demo path** *(merged, PR #19)* | Curated catalogue expanded to **40 synthetic jobs** (original five byte-identical); `python -m app.cli seed-catalogue` loads them through the existing adapter and ingestion service, refusing a database behind the Alembic head; offline full-flow test across the public API for two distinct profiles; README quickstart. No new endpoint, AI, model, migration or dependency. |
| **Week 6 PR 6B — tests** *(merged, PR #19)* | 58 new (1133 total); three catalogue-coupled assertions updated (C-31), no other existing test touched. 23/23 mutations caught. |
| **Checkpoint 6** | Final Week 6 checkpoint at `13eb832`, verified post-merge (see `context/workflow.md`). The dossier's declared safe stopping point. |
| **Week 7 design gate** | Approved 2026-09-20; rulings C-3, C-35..C-40 and A-53..A-70 recorded as **ADR-025** (application preparation and truthfulness validation), merged as PR #23 and amended by PR #25 so the evidence boundary is stated exactly. Split into Slice 7A (validator) and Slice 7B (endpoint). |
| **Week 7 Slice 7A — truthfulness validator** *(merged, PR #24)* | `app/services/truthfulness_validator.py` and `app/schemas/application.py` — deterministic, AI-free, framework-free claim validation; remove-by-default with a structured removal list; evidence is the provider-visible structured profile only, never `resume_raw_text` (ADR-025 D11, D12). No route, schema-for-request, model, migration, dependency or AI change, and **no checkpoint**. |
| **Week 7 Slice 7A — tests** *(merged, PR #24)* | 124 new (1259 total); 1135 existing unchanged. 42/42 mutations caught. Docs-only PR #26 (`f5b81f0`) then corrected a stale `_Evidence` docstring with no executable change (AST identical ignoring docstrings). |

## Partial

| Item | State |
|---|---|
| Skill alias map (`app/services/candidate_normalizer.py`) | A deliberate **seed** of ~60 common variants, not an ontology. Extend it as real resumes reveal real variants. Unknown skills pass through with their casing intact. |
| Operational database | Foundation only — engine, session factory, `Base`. No models, no migrations. First table is the job catalogue in Week 3. |
| `get_db()` dependency | Written and exercised by no endpoint. Week 1 and 2 endpoints are stateless by design; it exists so Week 3 has a session source. |
| **Jobs API trigger for ingestion** | `POST /api/v1/jobs/ingest` is in dossier §11 but **not** in the approved API scope: an unauthenticated route that writes the catalogue is an abuse surface. Deferred, not dropped (C-25, ADR-023 §11, ADR-024 §1). **PR 6B supplies the local trigger instead:** `python -m app.cli seed-catalogue`. |
| **Gemini provider** | Implemented and fully tested through `httpx.MockTransport`, but **never executed against the live Gemini service** — no API key exists in this environment and the suite must run without one. The default model identifier is a configured default, not a verified one (ADR-013 § Unverified). First live use is an outstanding integration step. |
| **Traceability checking** | Covers skills only. Free-text fields (job descriptions, project summaries) are legitimately paraphrased during extraction and cannot be verified by substring matching. Documented in the service docstring as a known limitation. |
| **spaCy fallback** | Not implemented. The dossier lists it as a deterministic cost-saver for predictable fields (emails, phones, dates). Currently every parse makes an AI call. Deferred, not forgotten. |

## Missing — i.e. everything in the product

| Component | Roadmap week | Status |
|---|---|---|
| spaCy deterministic fallback extraction (cost-saver, dossier §9) | 2 (deferred) | NOT STARTED |
| Eligibility engine (deterministic stage) | 4 | **COMPLETE** — PR #9, Checkpoint 4A |
| Eligibility engine (AI ambiguity stage) | 4 | **COMPLETE** — PR #11, Checkpoint 4; field-of-study relatedness only (ADR-019) |
| Matching engine (skill normalization, TF-IDF, cosine) | 5 | **COMPLETE** — PR #13, Checkpoint 5A; service only (ADR-020, ADR-021) |
| Recommendations (eligibility + matching, `POST /api/v1/recommendations`) | 5 | **COMPLETE** — PR #15, Checkpoint 5 (ADR-022) |
| Single-pair match scoring (`POST /api/v1/matching/score`, dossier §11) | 5C | **DEFERRED** — explicitly, by the Week 6 design gate (C-25, ADR-023 §11) |
| Excel export (openpyxl, `POST /api/v1/applications/export`) | 6 | **COMPLETE** — PR #17, Checkpoint 6A (ADR-023) |
| Week 6 polish: 40 curated jobs, local seed command, README quickstart, full-flow test | 6 | **COMPLETE** — PR #19, Checkpoint 6 (ADR-024) |
| Deterministic **eligibility** test suite (boundary/missing/invalid per constraint) | 4 | **COMPLETE** — PR #9 |
| Truthfulness validator (deterministic service, no endpoint) | 7 | **COMPLETE** — PR #24, Slice 7A (ADR-025); no checkpoint |
| Application preparation endpoint (`POST /api/v1/applications/prepare`) | 7 | NOT STARTED — designed as Slice 7B in ADR-025, not authorized |
| Caching, AI cost logging | 8 | NOT STARTED |
| Deployment (Render/Railway), README, docs | 9 | NOT STARTED |

**Week 6 is the declared safe stopping point** — at that line the system is complete and
demoable. Weeks 7–10 are enhancement.

---

## Next approved phase

**None. Week 7 Slice 7B — the application-preparation endpoint — is NOT started and NOT
authorized.** Week 6 is the dossier's declared safe stopping point (§15): everything after it is
enhancement. The Week 7 design gate is ruled (ADR-025) and Slice 7A is merged; Slice 7B begins
only on explicit instruction.

### Week 7 — Application preparation · IN PROGRESS (no checkpoint)

Design gate approved 2026-09-20 and recorded as **ADR-025** (PR #23, `c205770`), amended by
PR #25 (`5e90636`) so the ruling states the evidence boundary exactly. Two slices:

- **Slice 7A — truthfulness validator.** **Merged** as PR #24 (`365e7a4`) and verified
  post-merge. `app/services/truthfulness_validator.py` and `app/schemas/application.py`: deterministic
  and AI-free, with no FastAPI, database, filesystem or network dependency; remove-by-default with a
  structured removal list; evidence is the provider-visible structured profile only — never
  `resume_raw_text` (ADR-025 D11, D12). No route, model, migration, dependency or AI change, and
  **no checkpoint**. Docs-only PR #26 (`f5b81f0`) then corrected a stale `_Evidence` docstring.
- **Slice 7B — `POST /api/v1/applications/prepare`.** **NOT started, NOT authorized.** Designed in
  ADR-025; no endpoint, request/response schema, provider generation method or prompt exists.

### Week 6 — Polish, Excel export, testing · COMPLETE

Design gates approved 2026-09-19 (ADR-023) and 2026-09-20 (ADR-024). Two PRs:

- **PR 6A — Excel tracker export.** **Merged** as PR #17 (`0125703`) and verified post-merge;
  recorded as intermediate **Checkpoint 6A**. `POST /api/v1/applications/export` renders
  client-supplied tracking rows as an `.xlsx` file, entirely in memory; the one documented binary
  response in the API (C-23). Also corrected the stale OpenAPI status text (C-29).
- **PR 6B — Week 6 polish.** **Merged** as PR #19 (`13eb832`) and verified post-merge; recorded
  as final **Checkpoint 6**. Curated catalogue expanded to 40 synthetic jobs with the original
  five preserved (C-26, C-31); `python -m app.cli seed-catalogue` as the local setup path,
  guarded by an Alembic-head check (C-27, C-33); an offline full-flow integration test across
  the public API for two distinct profiles; a README quickstart verified from a fresh clone.
  Recorded in **ADR-024**. Not a release, tag or version (C-28).
- **Week 6 follow-up — final OpenAPI status (C-32).** **Merged** as PR #21 (`932d719`) after
  Checkpoint 6 and verified post-merge. The published status now reads **"Weeks 1–6 of a 10-week
  build are complete."**; the two tests that pin the sentence reject the stale wording and Week
  7-era claims. Three files — `app/main.py` and those two tests; no route, schema, model,
  migration, dependency or behaviour change. **Checkpoint 6 (`13eb832`) remains the Week 6 record**
  — the follow-up created no new checkpoint, tag or release.

`/api/v1/matching/score` and HTTP `/api/v1/jobs/ingest` stay **explicitly deferred** (C-25) — no
stub routes.

**Week 5 — Matching Engine is COMPLETE** as **Checkpoint 5** (`0aaaa1d`). Design gate approved
2026-09-17; delivered as PR 5A and PR 5B.

- **PR 5A — deterministic matching foundation.** **Merged** as PR #13 (`05534af`) and verified
  post-merge; recorded as intermediate **Checkpoint 5A**. Service only: `app/services/matching_engine.py`
  (narrow inputs, skill comparison, custom tokenizer, TF-IDF fitted on the whole catalogue,
  cosine 0–100 or null, skill coverage, top terms, template explanations, ordering key),
  `scikit-learn==1.7.2`, the `.NET` normalizer correction, ADR-020 and ADR-021. No router, no
  endpoint, no eligibility, AI or database change.
- **PR 5B — recommendations.** **Merged** as PR #15 (`0aaaa1d`) and verified post-merge;
  recorded as final **Checkpoint 5**. `POST /api/v1/recommendations`: one catalogue query, one
  Week 4 eligibility pass, one Week 5A matching pass over the whole catalogue; default scope
  ACTIVE + UNKNOWN capped at 50 with disclosure; explicit ids of any status; groups `ranked`,
  `needs_review`, `not_eligible`, `not_open` (precedence); no score in `not_eligible`, full
  match result but no rank in `not_open`;
  composed explanations; `corpus_fingerprint` added to the matching engine. ADR-022. No
  database, AI or eligibility change. `/matching/score` is not implemented.

Dossier §12.2 and §15: skill normalization, TF-IDF vectorization, cosine similarity, and ranked,
explained recommendations. Eligibility and matching stay separate: matching must consume Week 4
verdicts without changing them, and a `NOT_ELIGIBLE` job is excluded from ranking but remains
retrievable with its reason (ADR-006).

Week 4 is complete: the deterministic engine (PR #9, Checkpoint 4A) and the AI field-relatedness
stage (PR #11, ADR-019) are merged and verified as **Checkpoint 4**.

**No implementation may begin without explicit human approval of the specific step.**

---

## Blockers

**None open.**

## Resolved blockers

| # | Blocker | Resolved | How |
|---|---|---|---|
| 1 | Repository not under version control | 2026-09-10 | `git init` run on owner instruction. Branch `master`, all pre-existing files preserved and untracked, no remote configured, no history rewritten. |
| 2 | No `.gitignore`, with `.env` due in Week 2 | 2026-09-10 | `.gitignore` written and verified with `git check-ignore`: `.env` ignored, `.env.example` tracked, databases/caches/venvs/logs ignored, `.gitkeep` and the engineering layer tracked. |

---

## Risks currently live

| Risk | Severity | Note |
|---|---|---|
| Scope creep — dossier §16 flags this as the top solo-project risk | High | Mitigated by the fixed feature set, the Week 6 checkpoint, and the human-approval loop in `context/workflow.md`. |
| Job data acquisition is legally/technically hard | High | Deferred behind the adapter boundary (`ADR-005`). Phase 1 uses curated data. Not a Phase 1 risk. |
| Secret leakage via `.env` or logs | Medium | `.gitignore` now covers `.env` (verified). Residual risk is logging — see `standards/security_privacy.md` §2 and QG-005. |
| Local-first commitment eroding under implementation pressure | Medium | The easiest wrong turn is "just add a candidates table to make testing simpler." `ADR-001`/`ADR-002` and QG-005 exist specifically to catch this. |
| SQLite→PostgreSQL parity unvalidated | Medium | Dossier §9 flags this explicitly. Must be validated before Week 9 deployment, not assumed. |

---

## Contradictions

Per `AGENTOS.md`, contradictions between the dossier and this layer are surfaced to the human,
never silently fixed. These are internal to the dossier.

### Resolved

| # | Contradiction | Where | Ruling |
|---|---|---|---|
| **C-1** | §8.2 folder structure lists `models/candidate.py` and `models/application.py` (SQLAlchemy ORM models), but §10.2 states plainly "there is no server-side `candidates` table and no server-side store of evaluations by default." | dossier §8.2 vs §10.2 | **RESOLVED 2026-09-10 — [ADR-011](../artifacts/decisions/ADR-011-no-server-side-candidate-or-application-persistence.md).** §8.2's listing is **stale**; local-first has authority. Those models and tables **must not exist**. Candidate and application-tracking data remain client-owned; candidate APIs remain stateless; application status remains client-side. Pydantic schemas are unaffected. |
| **C-4** | §8.2 shows only `openai_provider.py`; §9.2 names OpenAI, OpenRouter, Anthropic and local models as swappable. Which is the Phase 1 default was unstated. | dossier §8.2 vs §9.2 | **RESOLVED 2026-09-10 — [ADR-013](../artifacts/decisions/ADR-013-gemini-flash-phase-1-default-provider.md).** Phase 1 default is **Google Gemini Flash**. Owner decision. A concrete implementation behind the ADR-004 abstraction, not a dependency of it: the mock provider stays mandatory, credentials are never committed, and the model id is configuration. |
| **C-2** | §8.2 lists no model for `ingestion_state`, but §10.2 requires that table for ingestion to work across runs. | dossier §8.2 vs §10.2 | **RESOLVED 2026-09-10 — [ADR-012](../artifacts/decisions/ADR-012-ingestion-state-operational-model.md).** Same staleness, opposite direction. Ingestion is server-side operational functionality, so `app/models/ingestion_state.py` is legitimate — bounded to adapter identity, run history, timestamps, outcome counts and status. Never a `candidate_id`, never personal data. **Not yet implemented — Week 3 work.** |

| **C-5** | The approved Week 3 decision says `is_active = false` for disappeared curated jobs; dossier §10.2 specifies `status` as a four-state enum (ACTIVE / EXPIRED / CLOSED / UNKNOWN). A boolean would drop three states. | approved decision vs dossier §10.2 | **RECONCILED 2026-09-10 — [ADR-014](../artifacts/decisions/ADR-014-job-status-model.md).** The enum is stored as the dossier specifies; `is_active` is derived (`status is ACTIVE`) and available as a filter. Neither source is overridden. |
| **C-6** | The approved Week 3 decision says one `ingestion_state` row per source with no run history; dossier §10.2 describes "adapter run history". | approved decision vs dossier §10.2 | **RESOLVED 2026-09-10 — [ADR-015](../artifacts/decisions/ADR-015-ingestion-state-one-row-per-source.md).** Current state per source satisfies the dossier's stated purpose ("required for ingestion to work correctly across runs"). The historical log is a genuine narrowing, approved and recorded as such. |
| **C-7** | Dossier §10.2's dedup canonicalization inputs include "Normalized location", but the `jobs` table in the same section lists no `location` column. | dossier §10.2, internal | **RESOLVED 2026-09-10 — a `location` column is required to implement the dossier's own deduplication spec.** Added; not speculative. |
| **C-8** | The approved Phase 1 local store is `~/.eligicore/`; dossier §8.1a/§10.1 names IndexedDB. | approved decision vs dossier §8.1a | **NOT A CONTRADICTION — [ADR-016](../artifacts/decisions/ADR-016-local-personal-data-store.md).** Two mechanisms for one commitment: personal data rests on the user's own device. IndexedDB presupposes the Phase 2 browser client; a Phase 1 non-browser client needs a filesystem equivalent. Recorded; **not implemented**. |

| **C-9** | §7 lists four verdict states; §10.1 lists five; UNKNOWN vs NEEDS_REVIEW and the role of LIKELY_ELIGIBLE were undefined. | dossier §7 vs §10.1 vs §12.1 | **RULED 2026-09-17 — [ADR-017](../artifacts/decisions/ADR-017-eligibility-states-and-verdict-precedence.md).** Five states with defined meanings and exact precedence. |
| **C-10** | Degree level is a named hard constraint (§12.1, §17) but `jobs` had no field for it. | dossier §12.1/§17 vs §10.2 | **RULED 2026-09-17 — [ADR-018](../artifacts/decisions/ADR-018-eligibility-requirement-inputs.md).** Nullable typed `min_degree_level`, additive migration `b3e8d2c61a47`. |
| **C-11** | §11's sample eligibility response includes `match_score` and skill overlap. | dossier §11 vs §7/§15 | **RULED 2026-09-17.** Excluded from Week 4; matching is Week 5. |
| **C-12** | The Week 1 `NormalizedGrade` docstring claimed a linear fraction enabled cross-scale comparison; `standards/eligibility.md` §4 requires a defined conversion. | repo vs standard | **RULED 2026-09-17 — ADR-018.** Same-scale comparison only; docstring corrected. |
| **C-13** | §12.1 "evaluation stops" after a hard failure — the whole job, or only AI? | dossier §12.1 | **RULED 2026-09-17 — ADR-017.** Deterministic evaluation continues; AI stops. |
| **C-14** | The PR 4B brief said empty `allowed_fields` → `UNKNOWN`; merged ruling A-2 omits the requirement, and R-4 depends on it. | PR 4B brief vs ADR-018 | **RULED 2026-09-17.** A-2 stands: empty means no field restriction — omitted, never `UNKNOWN`, never sent to AI. |
| **C-17** | `normalize_skill(".NET")` returned `"NET"`: a leading dot was trimmed as punctuation. | Week 1 code vs dossier §12.2 | **RULED 2026-09-17 — ADR-021.** Dot trimmed from the end only; `net`/`dotnet` alias to `.NET`. Fixed in PR 5A. |
| **C-18** | scikit-learn's default token pattern deletes C, R, C++ and C#, contradicting memory D-3/D-12. | library default vs repo rule | **RULED 2026-09-17 — ADR-020.** Custom tokenizer plus a separate skill namespace. Implemented in PR 5A. |
| **C-19** | The recommendation contract needs `corpus_fingerprint`; `MatchingResult` had none. | Week 5B contract vs Week 5A engine | **RULED 2026-09-19 — ADR-022, amends ADR-020 §5.** Added to `MatchingResult`, computed in `score_jobs` from job ids and terms only. |
| **C-20** | `score_jobs` raises for an id absent from the catalogue; eligibility reports unknown ids. | matching vs eligibility error models | **RULED 2026-09-19 — ADR-022.** The service splits out `not_found_job_ids` first; `score_jobs` unchanged. |
| **C-21** | `check_eligibility_with_ai` does not de-duplicate ids; only its request schema does. | eligibility service vs schema | **RULED 2026-09-19 — ADR-022.** De-duplicated by the recommendation schema and again by the service. |
| **C-22** | Explicit CLOSED/EXPIRED jobs would still go through Week 4 eligibility (and possibly AI). | Week 4 path vs `not_open` | **RULED 2026-09-19 — ADR-022, option (a).** Evaluated unchanged, then grouped `not_open` with precedence. |
| **C-23** | The export must "return the file"; the API standard requires a Pydantic `response_model` on every route. | dossier §11 vs `standards/api_design.md` §3, QG-004 #3 | **RULED 2026-09-19 — ADR-023 §8.** Binary `.xlsx` 200 as a documented, single-endpoint exception; request and all errors stay Pydantic/JSON. |
| **C-24** | §10.1 declares `match_score` a 0–100 float; ADR-020/022 define null scores. | dossier §10.1 vs ADR-020/022 | **RULED 2026-09-19 — ADR-023 §4.** Nullable; a null score is an empty cell, never 0. |
| **C-25** | Week 6 is "complete" while §11's `/matching/score` and `/jobs/ingest` are unimplemented. | dossier §11/§15 vs repo | **RULED 2026-09-19 — ADR-023 §11.** Both explicitly deferred; no stubs. |
| **C-26** | 5 curated jobs vs the Week 3 deliverable of 30–50. | dossier §15 vs `app/data/curated_jobs.json` | **RULED 2026-09-19.** Expanded with synthetic jobs in PR 6B, not 6A. |
| **C-27** | A fresh clone has no documented migration step and no way to load the catalogue. | dossier §17 vs README | **RULED 2026-09-19.** Local setup/demo command and README quickstart in PR 6B. |
| **C-28** | CHANGELOG calls the Week 6 checkpoint a release milestone; the workflow says a checkpoint is not a release, version or tag. | CHANGELOG vs `context/workflow.md` | **RULED 2026-09-19.** Checkpoint only — no release, tag or version. |
| **C-29** | The OpenAPI description still said Week 5 was in progress. | `app/main.py` vs this file | **RULED 2026-09-19.** Corrected in PR 6A, guarded by a test. |
| **C-30** | Status diversity was wanted in the catalogue, but `RawJob` has no status and ingestion makes every job ACTIVE. ADR-014's review condition (are `EXPIRED`/`UNKNOWN` used?) had come due. | adapter contract vs demo wish | **RULED 2026-09-20 — ADR-024 §3.** No `RawJob` status field; curated jobs stay ACTIVE. The enum is **kept**: `CLOSED` comes from authoritative disappearance, `EXPIRED`/`UNKNOWN` are reserved for future sources. `not_open` stays covered by test fixtures. |
| **C-31** | Expanding the catalogue breaks three existing assertions that assume five jobs. | Week 3–4 tests vs C-26 | **RULED 2026-09-20 — ADR-024 §4.** Exactly those three assertions change; the golden verdicts themselves are unchanged. |
| **C-32** | A merged test pins the OpenAPI status sentence, which would go stale when Week 6 closes. | `tests/test_tracker_export_endpoint.py` vs `app/main.py` | **RULED 2026-09-20 — ADR-024 §6.** The sentence stays until Checkpoint 6, so that assertion is untouched; a new test pins the seed sentence and rejects premature claims. **CLOSED 2026-09-20 in PR #21** (`932d719`): with Week 6 closed, the status became "Weeks 1–6 of a 10-week build are complete." and both pinned assertions were re-aimed at Week 7-era claims. |
| **C-33** | Dossier §8.2's folder structure lists no CLI, but setup without HTTP needs one. | dossier §8.2 vs C-25 | **RULED 2026-09-20 — ADR-024 §1.** `app/cli.py` is local tooling holding no business logic. |
| **C-34** | §17's "stranger in under 10 minutes" overlaps Week 9 documentation. | dossier §17 vs §15 | **RULED 2026-09-20 — ADR-024 §6.** PR 6B ships a local quickstart only; deployment and full documentation stay in Week 9. |
| **C-3** | §12.3 says generated content is checked "against the **stored** candidate profile." Under local-first nothing is stored server-side; §11 confirms the profile travels in the request body. Wording predates the local-first revision. | dossier §12.3 vs §8.1a/§11 | **RULED 2026-09-20 — [ADR-025](../artifacts/decisions/ADR-025-week-7-application-preparation.md) D1.** Closed as stale wording: truthfulness validation runs against the profile **supplied in the request**. Nothing is stored or read server-side. |

### Still open — not to be resolved without instruction

**None recorded here.** C-3, the last entry, was ruled by ADR-025 (D1) and moved to the
resolved table above. The Week 7 design gate also raised C-35..C-40 and A-53..A-70; **ADR-025 is
the authoritative record of those rulings** and they have not been transcribed into this register.


---

## Recent decisions

Full index in `context/decisions.md`.

| ADR | Title | Date |
|---|---|---|
| ADR-025 | Week 7 application preparation and truthfulness validation (C-3, C-35..C-40, A-53..A-70) | 2026-09-20 |
| ADR-024 | Week 6 MVP scope: local setup, curated catalogue, full-flow test (C-30..C-34) | 2026-09-20 |
| ADR-023 | Tracker export contract (C-23..C-29) | 2026-09-19 |
| ADR-022 | Recommendation orchestration (C-19..C-22) | 2026-09-19 |
| ADR-021 | Skill comparison for matching (C-17) | 2026-09-17 |
| ADR-020 | Match scoring (C-18) | 2026-09-17 |
| ADR-019 | AI-assisted field-of-study relatedness (A-3, R-2, C-14) | 2026-09-17 |
| ADR-018 | Eligibility requirement inputs (rules on C-10, C-12, A-1, A-2, A-4) | 2026-09-17 |
| ADR-017 | Eligibility states and verdict precedence (rules on C-9, C-13, R-2, R-4) | 2026-09-17 |
| ADR-012 | `ingestion_state` as an operational model (ruling on C-2) | 2026-09-10 |
| ADR-011 | No server-side candidate or application persistence (ruling on C-1) | 2026-09-10 |
| ADR-001 | Local-first personal data | 2026-09-10 (recorded; decided in dossier) |

---

## Checkpoints

**Canonical registry: [`context/workflow.md`](workflow.md) § Checkpoint registry.** That table
governs; this is a summary.

| # | Checkpoint | Commit on `main` | Produced by | State |
|---|---|---|---|---|
| **0** | Phase 0 — AgentOS engineering layer | `e8c68b7` | Direct commits before branch protection | **Stable** |
| **1** | Week 1 — Foundation and Candidate Profile Schema | `2e79454` | PR #2, merged 2026-09-10 | **Stable** |
| **2** | Week 2 — Resume Parser and Gemini Flash AI Service Layer | `91dd31d` | PR #4, merged 2026-09-10 | **Stable** |
| **3** | Week 3 — Job Schema, Adapters and Ingestion | `2cfd4f0` | PR #6 + PR #7, merged 2026-09-10 | **Stable** |
| **4A** | Week 4 — Deterministic Eligibility Engine (**intermediate**) | `4a5cb84` | PR #9, merged 2026-09-17 | **Stable** |
| **4** | Week 4 — Eligibility Intelligence (final) | `f56d7df` | PR #9 + PR #11, merged 2026-09-17 | **Stable** |
| **5A** | Week 5 — Deterministic Matching Engine (**intermediate**) | `05534af` | PR #13, merged 2026-09-17 | **Stable** |
| **5** | Week 5 — Matching Engine (final) | `0aaaa1d` | PR #13 + PR #15, merged 2026-09-19 | **Stable** |
| **6A** | Week 6 — Excel Export (**intermediate**) | `0125703` | PR #17, merged 2026-09-19 | **Stable** |
| **6** | Week 6 — MVP (final) | `13eb832` | PR #17 + PR #19, merged 2026-09-20 | **Stable — current** |

**Checkpoint 1 full SHA:** `2e79454f787019ff29af39fcfd285aee59c8bc77`
**Checkpoint 2 full SHA:** `91dd31d50e7749ad37acf14babd5d1ee90141abd`
**Checkpoint 3 full SHA:** `2cfd4f0276b60de393ec604afc10b3c52f483ca7`
**Checkpoint 4A full SHA:** `4a5cb844d1aa4ca4aa3e0906481d0d91c8fc67d4`
**Checkpoint 4 full SHA:** `f56d7dfabeeb8a7addac693d2c7552b0c1fc4e76`
**Checkpoint 5A full SHA:** `05534affced482f6bc5e188ac465144dd425f9a7`
**Checkpoint 5 full SHA:** `0aaaa1da6fe643b8164df645113322adc889075d`
**Checkpoint 6A full SHA:** `0125703ad9464216b1622c14941664ec32ac9bac`
**Checkpoint 6 full SHA:** `13eb8325149cab60a039534631265803250b767a`

```
main
  |
  ├── e8c68b7  Checkpoint 0 — Phase 0 (AgentOS engineering layer)
  |
  ├── 2e79454  Checkpoint 1 — Week 1 Foundation
  |                 ↑  PR #2  (feature/week-1-foundation, 11 commits)
  |
  ├── 91dd31d  Checkpoint 2 — Week 2 Resume Parser + Gemini Flash AI
  |                 ↑  PR #4  (feature/week-2-resume-ai, 16 commits)
  |
  ├── f538015  PR #6 — Week 3 implementation (NOT a checkpoint: defects found after merge)
  |
  ├── 2cfd4f0  Checkpoint 3 — Week 3 Job Schema + Adapters + Ingestion
  |                 ↑  PR #7  (verification repairs)
  |
  ├── 4a5cb84  Checkpoint 4A — Week 4 deterministic eligibility engine (intermediate)
  |                 ↑  PR #9  (feature/week-4-eligibility-engine, 6 commits)
  |
  ├── f56d7df  Checkpoint 4 — Week 4 Eligibility Intelligence (final)
  |                 ↑  PR #11 (feature/week-4-eligibility-ai, 6 commits)
  |
  ├── 05534af  Checkpoint 5A — Week 5 deterministic matching engine (intermediate)
  |                 ↑  PR #13 (feature/week-5-matching-engine, 5 commits)
  |
  ├── 0aaaa1d  Checkpoint 5 — Week 5 Matching Engine (final)
  |                 ↑  PR #15 (feature/week-5-recommendations, 9 commits)
  |
  ├── 0125703  Checkpoint 6A — Week 6 Excel Export (intermediate)
  |                 ↑  PR #17 (feature/week-6-excel-export, 10 commits)
  |
  └── 13eb832  Checkpoint 6 — Week 6 MVP (final)  <- current
                    ↑  PR #19 (feature/week-6-polish, 9 commits)
```

Checkpoint 0 is the single commit `e8c68b7` — the state of `main` at the end of Phase 0 — not the
two-commit range that built it. Each checkpoint is declared stable only after the merged `main`
state is verified: merge confirmed on GitHub, tree clean, full suite run from `main`, and CI
green on the merged commit.

**Checkpoint 6 is the current rollback target; Checkpoint 6A is next.** Earlier checkpoints remain
recoverable indefinitely and are not superseded — a regression whose cause predates the newest
checkpoint needs an older target.

Recovery rules are in `context/workflow.md` § Recovery and rollback. In short: never rewrite
`main` history, never `git reset --hard` as recovery, never roll back without human approval.

---

## Next actions

1. **Await explicit instruction before starting Week 7 Slice 7B.** The Week 7 design gate is ruled
   (ADR-025) and Slice 7A — the deterministic truthfulness validator — is merged and verified
   (PR #24). Slice 7B, the `POST /api/v1/applications/prepare` endpoint, is designed but **not
   started and not authorized**. Checkpoint 6 remains the current checkpoint and no Checkpoint 7
   exists. No phase or slice rolls into the next automatically.
2. Before relying on live AI: exercise Gemini's `assess_field_relatedness` (and
   `extract_resume`) against the real service once, and confirm the model identifier.
3. Before deployment (Week 9 / QG-007): verify the migration chain against PostgreSQL.
   `batch_alter_table` has only ever run on SQLite.

**Outstanding integration step:** the Gemini provider — resume extraction and field relatedness —
has never run against the live service. Confirm the model identifier and exercise one real call before
relying on live extraction.

**Weeks 1–6 are complete; Week 7 is in progress — Slice 7A merged, Slice 7B not started;
Weeks 8–10 have not started.** Checkpoint 6 (`13eb832`) is the final Week 6 record,
**Stable — current**, and the declared safe stopping point; Checkpoint 6A remains the
intermediate one. **Week 7 has produced no checkpoint.** **The OpenAPI status is finalized** — it
reads "Weeks 1–6 of a 10-week build are complete." and matches Checkpoint 6 (C-32 closed in
PR #21); Slice 7A added no API surface, so that published status is still correct.
No `/matching/score` route, no `/jobs/ingest` route and no `/applications/prepare` route exists.
The truthfulness validator exists as a **service only** (PR #24); no application-preparation
endpoint, provider generation method, prompt, caching or cost-logging code exists anywhere in
the repository.

**Doc drift corrected:** the OpenAPI "Current status" string in `app/main.py` said the AI
field-relatedness stage was not yet implemented. The docs-only Checkpoint 4 record PR corrected the
description string; no route, schema, handler or behaviour changed.
