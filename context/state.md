# Project State — EligiCore

> **MANDATORY first read for every session.**
> **Rule:** nothing is marked complete because the dossier plans it. Only because it exists,
> runs, and is tested. Planned ≠ done.
> **Update:** at the end of every session that changes the repository.

---

## Snapshot

| Field | Value |
|---|---|
| **Date** | 2026-09-26 |
| **Phase** | **Week 9A — Local production readiness · COMPLETE.** All seven slices (9A-1 OpenAPI · 9A-2 PostgreSQL · 9A-3 production configuration · 9A-4 secret handling · 9A-5 privacy and logging · 9A-6 local end-to-end · 9A-7 documentation) are merged or verified and recorded as **Checkpoint 9A**. **Local execution is the normal operating mode; nothing is deployed.** **Week 9B — Deployment and Sharing — is OPTIONAL, owner-triggered and NOT started** (ADR-027). Previously: **Week 8 · COMPLETE.** Slice 8A (cost/usage accounting), Slice 8B (candidate-free corpus vectorizer cache) and Slice 8C (operational-log completeness) are all **complete and merged**, recorded as **Checkpoint 8**. Week 6 remains the dossier's declared safe stopping point (§15); Weeks 7 and 8 are enhancement on top of it. **Week 9 is NOT started and NOT authorized.** |
| **Roadmap position** | **Weeks 1–8 complete and merged; Week 9A complete.** Week 9 is two stages under **ADR-027** — 9A local production readiness (done, Checkpoint 9A) and 9B deployment and sharing (optional, not started). **Weeks 9B and 10 NOT started.** Earlier:  Week 7 delivered as Slice 7A (PR #24, no checkpoint) + Slice 7B (PR #28, **Checkpoint 7**) on **ADR-025**. Week 8 delivered as Slice 8A (PR #34), Slice 8B (PR #35) and Slice 8C (PR #36, **Checkpoint 8**) on the design gate ruled in **ADR-026** (PR #32, with ADR-020 §5's partial supersession recorded in PR #33) — **none of the three slices recorded a checkpoint of its own**. **Weeks 9–10 NOT started.** `/matching/score` and HTTP `/jobs/ingest` remain explicitly deferred (C-25, ADR-023 §11, ADR-024); **live Gemini application generation remains deferred** and was not implemented in Week 8. |
| **Health** | 🟢 GREEN — 1567 tests passing on `main`; PostgreSQL 18.6 migration compatibility verified by execution; production configuration, secret handling, privacy and logging re-verified; local end-to-end run and two fresh-clone quickstarts passed; mutations **230/230** re-verified from a clean tree — 32/32 (8C), 34/34 (8B), 68/68 (8A), 54/54 (7B), 42/42 (7A) — plus 23/23 (6B), 30/30 (6A), 40/40 (5B), 36/36 (5A), 27/27 (Week 4); CI green on `e5d6d36`, `f3fbf35` and `9aba1f2`; live privacy sweep clean; no open blockers |
| **Stable branch** | `main` |
| **Current checkpoint** | **Checkpoint 9A** — Week 9A Local Production Readiness — `95a1187715851ee7a67fa8cdbc7c6e87f3fa7ec3`, which is also the current head of `main`. **It records a verified local product, not a deployment: there is no hosted instance and no public URL.** Checkpoint 9 is reserved for the final Week 9 state and exists only if the owner deploys. Checkpoint 8 (`9aba1f2`) is now historical. Checkpoint 7 (`6c269a0`) is now historical; Checkpoint 6 (`13eb832`) remains recorded as the final Week 6 checkpoint and the declared safe stopping point. **Week 8 has no intermediate checkpoint: there is no Checkpoint 8A, 8B or 8C**, because none of the three slices recorded one. **There is no Checkpoint 9.** |
| **Produced by** | PR #39 (`65b15bb`, 9A-1) + PR #40 (`89b616a`, 9A-2 prerequisite) + PR #41 (`229acc1`, 9A-3) + PR #42 (`88c884b`, 9A-4) + PR #43 (`8cd6ad8`, 9A-5) + PR #44 (`95a1187`, 9A-7), all **MERGED**, on ADR-027 (PR #38, `1afd4e5`). 9A-2's migration validation and 9A-6's end-to-end run were **verification-only and produced no commit**. Checkpoint 7 (`6c269a0`) remains the final Week 7 checkpoint and Checkpoint 6 (`13eb832`) the final Week 6 one. |
| **Rollback target** | Checkpoint 9A first; Checkpoint 8 by reverting the Week 9A merges (PR #44, #43, #42, #41, #40, #39 and the ADR-027 record PR #38) — no database step, though reverting PR #40 removes the PostgreSQL driver; then Checkpoint 7 by also reverting the Week 8 merges as appropriate — PR #36, then PR #35, then PR #34 (no database step: Week 8 added no migration and no dependency); Checkpoint 6 by also reverting PR #28 (no database step); Checkpoint 6A by also reverting PR #19 (no database step); Checkpoint 5 by also reverting PR #17 (no database step); Checkpoint 5A by also reverting PR #15 (no database step); Checkpoint 4 by also reverting PR #13; Checkpoint 4A by also reverting PR #11; Checkpoint 3 also needs `alembic downgrade 7c2f1a9b4d30`; below Checkpoint 3 also needs `alembic downgrade base`. |
| **Next milestone** | **Week 9B — Deployment and Sharing. OPTIONAL, owner-triggered and NOT started.** It is not required for ordinary use and may never be performed; it begins only when the owner decides to share EligiCore, and seven owner decisions are open before it can (ADR-027). Live Gemini application generation remains deferred and is not scheduled by any merged decision. Week 10 remains buffer. |
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
| **Week 7 Slice 7B — application preparation** *(merged, PR #28)* | `POST /api/v1/applications/prepare` — `app/services/application_prep.py` orchestrates one catalogue read, one provider generation call and the Slice 7A validator, returning only sanitized text with a full removal audit and an explicit no-submission notice. Provider boundary `generate_application_content` added to `AIProvider`/`AIService`; deterministic conservative mock generation with injectable fabricating, over-length and empty modes; reviewed prompt file. Gemini generation is a stub (deferred to Week 8/9, D13). No persistence, cache, migration, table or dependency. Recorded as **Checkpoint 7**. |
| **Week 8 design gate** | Approved 2026-09-23; W8-A..W8-H ruled and recorded as **ADR-026** (PR #32), with ADR-020 §5's partial supersession recorded separately in PR #33 so the historical wording is preserved rather than rewritten. Week 8 is exactly three behaviour-preserving slices: 8A, 8B, 8C. |
| **Week 8 Slice 8A — cost and usage accounting** *(merged, PR #34)* | `app/ai/usage.py` (new) — `AIUsage`, a per-call `UsageSink` and integer micro-unit cost arithmetic; `extract_resume` and `assess_field_relatedness` log tokens and cost on both success and error paths; Gemini reports usage across retries, reading a retryable error body before translating it; the mock reports deterministic synthetic usage; `ModelCostRate` configuration with an **empty default** so no external price is hard-coded. **`generate_application_content` gained no usage parameter — the exclusion is structural** (ADR-026 D8). No endpoint, schema, contract, model, migration or dependency change. |
| **Week 8 Slice 8A — tests** *(merged, PR #34)* | 87 new across `tests/test_ai_cost_accounting.py` and `tests/test_ai_cost_privacy.py` (1445); a retry-accounting audit then found and fixed a real gap — usage on a 429/5xx body was discarded before it could be read (`0d2689c`) — and added 17 more (1462 total). Two merged test files were re-aimed and strengthened when the provider signature grew a keyword-only `usage` parameter; none was weakened. 68/68 mutations caught. |
| **Week 8 Slice 8B — corpus vectorizer cache** *(merged, PR #35)* | `CorpusArtifacts`, `CorpusCache` and `fit_corpus` in `app/services/matching_engine.py` — a process-local, bounded, in-memory LRU of **capacity 4**, keyed by the existing `corpus_fingerprint`, holding only catalogue-derived fitted artifacts. **The candidate transform stays per-request and is never cached.** No configuration key, no disk, no external cache service, no new dependency. An output-identical optimization: cold, warm and post-invalidation results are identical. |
| **Week 8 Slice 8B — tests** *(merged, PR #35)* | 43 new in `tests/test_corpus_cache.py` (1505 total) — cold/warm equivalence, fingerprint invalidation, candidate isolation, bounded eviction and artifact immutability. 34/34 mutations caught. |
| **Week 8 Slice 8C — operational-log completeness** *(merged, PR #36)* | One production gap, closed in eight lines of `app/main.py`: a request that ends in an unhandled exception now emits its request record before the exception propagates. Starlette's `ServerErrorMiddleware` sits outside the request middleware, so the request count had been systematically blind to exactly those requests. Nothing about the exception is logged there. Recorded as **Checkpoint 8**. |
| **Week 9 design ruling** | **ADR-027** (PR #38, `1afd4e5`) — EligiCore is primarily a locally run personal application; Week 9 splits into 9A local production readiness and 9B optional deployment. Records the deliberate deviation from dossier §15 row 9 and §17, which required a live public API. |
| **Week 9A-1 — OpenAPI currency** *(merged, PR #39)* | The published status corrected from Weeks 1–6 to Weeks 1–8. **The document is byte-identical once `info.description` is removed** — 10 paths, 58 schemas, all status codes unchanged. Two merged pinning tests re-aimed and strengthened; one new test pins the whole contract surface. |
| **Week 9A-2 — PostgreSQL compatibility** *(merged, PR #40 + verification)* | `psycopg2-binary==2.9.10` added, closing a real gap: ADR-009 names PostgreSQL for production but no driver was declared. The existing chain was then run against **local PostgreSQL 18.6** — upgrade, representative data, constraint probes, stepwise downgrade, re-upgrade and `alembic check` — all passing. **`batch_alter_table`, never before run outside SQLite, fell through to plain `ALTER TABLE` as documented.** No migration modified; head unchanged. |
| **Week 9A-3 — production configuration** *(merged, PR #41)* | Seven tests pin production mode, which nothing had covered. Finding: **traceback suppression is unconditional**, not caused by the environment setting — a stronger guarantee, pinned in that form. Two coherence gaps reported, not patched: `ELIGICORE_DEBUG` is read nowhere, and `Settings.is_production` has no consumer. |
| **Week 9A-4 — secret handling** *(merged, PR #42)* | Tree and full-history scans (412 blobs, 190 commits) found **no real secret**; all eight hits manually classified as false positives. **`.env` has zero historical revisions.** Two tests close the one unpinned gap: the provider key never reaches a log or an error message. |
| **Week 9A-5 — privacy and logging** *(merged, PR #43)* | Three tests re-verify the Week 8C guarantees **under production**, which no merged test had done. Sixteen markers, every candidate-carrying endpoint, a controlled 500, cost records and a full database dump — all clean. |
| **Week 9A-6 — local end-to-end** *(verification only, no commit)* | A real `uvicorn` process against local PostgreSQL under production: 40 jobs seeded, **all ten routes exercised from the live OpenAPI inventory, every one 200**, `/docs` `/redoc` `/openapi.json` served, a genuine 500 from stopping the database, and the **downgrade and re-upgrade executed** with 41 rows preserved through both data-preserving steps and the application restarted against the restored schema. |
| **Week 9A-7 — documentation** *(merged, PR #44)* | README made current against the live application in both directions; local-first documented as normal; optional deployment path documented and **not executed**, with the seven 9B decisions left open. **Two fresh clones from GitHub reached a running API in 3 min 7 s and 2 min 46 s**, no undocumented step. |
| **Week 8 Slice 8C — tests** *(merged, PR #36)* | 44 new in `tests/test_operational_logs.py` (1549 total) — request-count completeness across seven paths, error-record content, the Slice 8A regression, the generation boundary verified on the syntax tree, and a fourteen-marker privacy sweep. 32/32 mutations caught. |
| **Week 7 Slice 7B — tests** *(merged, PR #28)* | 98 new (1358 total); five merged assertions re-aimed and strengthened after the provider interface grew, none weakened. 54/54 mutations caught; Slice 7A's 42/42 preserved. ADR-025's failure-semantics wording was corrected by docs-only PR #29 (`234dabf`) before the merge, not during implementation. |

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
| Truthfulness validator (deterministic service, no endpoint) | 7 | **COMPLETE** — PR #24, Slice 7A (ADR-025); no checkpoint of its own — covered by Checkpoint 7 |
| Application preparation endpoint (`POST /api/v1/applications/prepare`) | 7 | **COMPLETE** — PR #28, Slice 7B, Checkpoint 7 (ADR-025); mock generation only, live Gemini deferred |
| Caching, AI cost logging | 8 | **COMPLETE** — PR #34 (8A cost/usage accounting) + PR #35 (8B corpus cache) + PR #36 (8C operational logs), Checkpoint 8 (ADR-026). **Cost coverage excludes the generation path, by design (D8); live Gemini application generation was NOT implemented and remains deferred.** |
| Documentation and local production readiness | 9A | **COMPLETE** — Checkpoint 9A (`95a1187`); seven slices merged or verified (ADR-027) |
| Deployment and sharing (Render/Railway, hosted PostgreSQL, access control) | 9B | **OPTIONAL — NOT STARTED.** Not required for ordinary use; seven owner decisions open (ADR-027) |

**Week 6 is the declared safe stopping point** — at that line the system is complete and
demoable. Weeks 7–10 are enhancement.

---

## Next approved phase

**None. Week 9B — Deployment and Sharing — is OPTIONAL, owner-triggered and NOT started.** It is
not required for ordinary use of EligiCore and may never be performed. Week 6 remains the dossier's
declared safe stopping point (§15). **Nothing is deployed: there is no hosted instance, no public
URL and no Checkpoint 9.**

### Week 9A — Local production readiness · COMPLETE (Checkpoint 9A)

Ruled by **ADR-027** (PR #38, `1afd4e5`), which records that EligiCore is primarily a locally run
personal application and splits Week 9 into two stages. That is a **deliberate, owner-approved
deviation** from dossier §15 row 9 and §17, which required a live public API; the deviation is
recorded in the ADR rather than reinterpreted away, and the dossier is unmodified.

Seven slices, all merged or verified and each audited post-merge:

| Slice | Outcome |
|---|---|
| **9A-1** OpenAPI currency (PR #39) | Status corrected to Weeks 1–8; document byte-identical apart from that text |
| **9A-2** PostgreSQL compatibility (PR #40 + verification) | Driver added; the existing chain validated against PostgreSQL 18.6 by execution |
| **9A-3** production configuration (PR #41) | Production mode pinned; suppression shown to be unconditional |
| **9A-4** secret handling (PR #42) | No secret in the tree or in any historical blob; key transport pinned |
| **9A-5** privacy and logging (PR #43) | The 8C guarantees re-verified under production |
| **9A-6** local end-to-end (verification only) | Real server, real PostgreSQL, all ten routes, rollback executed |
| **9A-7** documentation (PR #44) | README current; fresh clone to a running API in 2 min 46 s |

**What Checkpoint 9A does not mean.** It does not mean a public API exists. **Local execution is
the normal operating mode and localhost is sufficient for ordinary personal use.** Deployment is
optional and owner-triggered.

**Seven Week 9B decisions remain open and none has been made:** Render vs Railway · hosted
PostgreSQL choice · rate-limiting mechanism and values · deployed AI provider · hosted catalogue
seeding strategy · `/docs` exposure · shared-instance access control.

**Known limitations carried forward:** no hosted deployment · no public URL · no platform-log
verification · no live Gemini call · no authentication (Phase 4) · no rate limiting (QG-007 item 10
unmet) · uvicorn's own stderr tracebacks during a database outage, which carry file paths but no
credentials or candidate data and are a hosted-logging consideration for 9B · one unexplained,
unreproduced failure of a merged 9A-5 test whose assertion text was not captured, which remains an
**open diagnostic item** rather than something later green runs have closed.

### Week 8 — Refinement, caching and cost logging · COMPLETE (Checkpoint 8)

Design gate approved 2026-09-23 and recorded as **ADR-026** (PR #32, `ca338f2`); ADR-020 §5's
partial supersession was recorded separately in PR #33 (`dc0a759`) so the historical wording is
preserved rather than rewritten. Three **behaviour-preserving** slices (D1) — no endpoint, route,
schema, contract, verdict, score or response body changed:

- **Slice 8A — cost and usage accounting.** **Merged** as PR #34 (`e5d6d36`). `extract_resume` and
  `assess_field_relatedness` log token usage and a derived cost. Usage travels on a **per-call
  sink** rather than provider state, so `eligibility_ai`'s `asyncio.gather` fan-out cannot
  mis-attribute cost (D3). Retried calls accumulate (D4). Pricing is configuration with an empty
  default, so **no external provider price is hard-coded** (D5), and cost is integer micro-units.
  Accounting can never change an AI outcome (D6). Operational logs only — **no table, no migration,
  no `candidate_id` in any cost record** (D9).
- **Slice 8B — candidate-free corpus vectorizer cache.** **Merged** as PR #35 (`f3fbf35`). A
  process-local, bounded, in-memory LRU of capacity 4, keyed by `corpus_fingerprint`, holding only
  the catalogue-derived fitted artifacts. **The candidate's transform is never cached** — that
  single boundary is the whole privacy argument, and ADR-020's rule that the candidate is
  transformed and never fitted is preserved exactly (D7).
- **Slice 8C — operational-log completeness.** **Merged** as PR #36 (`9aba1f2`) and recorded as
  **Checkpoint 8**. "Refinement" was ruled to mean closing the three operational logging categories
  the dossier §10.2 names — request counts, AI usage/cost, error records (D10). The audit found one
  gap: an unhandled exception escaped the request middleware, so the request count missed exactly
  the requests an operator most needs. Eight lines closed it.

**Cost coverage is deliberately partial.** `generate_application_content` is **excluded
structurally** — no usage sink is threaded through it and no setting could enable one — because
ADR-025's merged generation-logging rule stands verbatim and a token count is a length that could
characterize one candidate's content (D8). **Week 8 is not complete AI cost coverage**, and the
generation path becomes material only when live application generation is separately approved and
receives its own explicit privacy decision.

**Week 8 has no intermediate checkpoint.** None of the three slices recorded one, so there is no
Checkpoint 8A, 8B or 8C, and Checkpoint 8 covers Week 8 as a whole.

### Week 7 — Application preparation · COMPLETE (Checkpoint 7)

Design gate approved 2026-09-20 and recorded as **ADR-025** (PR #23, `c205770`), amended by
PR #25 (`5e90636`) so the ruling states the evidence boundary exactly and by PR #29 (`234dabf`)
so the failure semantics match the owner's ruling. Two slices:

- **Slice 7A — truthfulness validator.** **Merged** as PR #24 (`365e7a4`) and verified
  post-merge. `app/services/truthfulness_validator.py` and `app/schemas/application.py`: deterministic
  and AI-free, with no FastAPI, database, filesystem or network dependency; remove-by-default with a
  structured removal list; evidence is the provider-visible structured profile only — never
  `resume_raw_text` (ADR-025 D11, D12). No route, model, migration, dependency or AI change, and
  **no checkpoint of its own**. Docs-only PR #26 (`f5b81f0`) then corrected a stale `_Evidence`
  docstring. It remains byte-identical after Slice 7B.
- **Slice 7B — `POST /api/v1/applications/prepare`.** **Merged** as PR #28 (`6c269a0`) and
  verified post-merge; recorded as **Checkpoint 7**. `app/services/application_prep.py` reads one
  catalogue job, projects the request profile into a narrow evidence object, asks the AI provider
  for a draft, and passes every generated string through the 7A validator so only sanitized text
  is ever returned — with the full removal list, a package status, per-item confidence and an
  explicit no-submission notice. The provider sees five evidence fields and never the candidate's
  identity, contact details, employers, languages, grades, backlog count or `resume_raw_text`
  (D10–D12). Generation runs on the mandatory mock only; the Gemini method is a stub and **live
  generation is deferred to Week 8/9** (D13). No persistence, cache, migration, table or
  dependency.

**Week 7 has no intermediate checkpoint.** Slice 7A deliberately recorded none, so there is no
Checkpoint 7A and Checkpoint 7 covers Week 7 as a whole.

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

**One tracked documentation divergence, not a contradiction.** The published OpenAPI "Current
status" string still reads *"Weeks 1–6 of a 10-week build are complete."* while Week 7 is complete
here. This is deliberate: two merged tests pin that sentence and reject Week 7-era wording, so
correcting it touches application code and is out of scope for a documentation-only checkpoint
record. It is the same handling C-32 received at Checkpoint 6, and is listed under Next actions.


---

## Recent decisions

Full index in `context/decisions.md`.

| ADR | Title | Date |
|---|---|---|
| ADR-026 | Week 8 refinement, caching and cost logging (W8-A..W8-H; partially supersedes ADR-020 §5) | 2026-09-23 |
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
| **6** | Week 6 — MVP (final) | `13eb832` | PR #17 + PR #19, merged 2026-09-20 | **Stable** |
| **7** | Week 7 — Application Preparation (final) | `6c269a0` | PR #24 + PR #28, merged 2026-09-22 | **Stable** |
| **8** | Week 8 — Refinement, Caching and Cost Logging (final) | `9aba1f2` | PR #34 + PR #35 + PR #36, merged 2026-09-24 | **Stable** |
| **9A** | Week 9A — Local Production Readiness | `95a1187` | PR #39 + #40 + #41 + #42 + #43 + #44, merged 2026-09-26 | **Stable — current** |

**Checkpoint 1 full SHA:** `2e79454f787019ff29af39fcfd285aee59c8bc77`
**Checkpoint 2 full SHA:** `91dd31d50e7749ad37acf14babd5d1ee90141abd`
**Checkpoint 3 full SHA:** `2cfd4f0276b60de393ec604afc10b3c52f483ca7`
**Checkpoint 4A full SHA:** `4a5cb844d1aa4ca4aa3e0906481d0d91c8fc67d4`
**Checkpoint 4 full SHA:** `f56d7dfabeeb8a7addac693d2c7552b0c1fc4e76`
**Checkpoint 5A full SHA:** `05534affced482f6bc5e188ac465144dd425f9a7`
**Checkpoint 5 full SHA:** `0aaaa1da6fe643b8164df645113322adc889075d`
**Checkpoint 6A full SHA:** `0125703ad9464216b1622c14941664ec32ac9bac`
**Checkpoint 6 full SHA:** `13eb8325149cab60a039534631265803250b767a`
**Checkpoint 7 full SHA:** `6c269a05ec1a4fdbdc7820d0c6b0b40980ba8fb3`
**Checkpoint 8 full SHA:** `9aba1f2b1007b0931ec9adc39afb88b15eaa2c14`
**Checkpoint 9A full SHA:** `95a1187715851ee7a67fa8cdbc7c6e87f3fa7ec3`

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
  ├── 13eb832  Checkpoint 6 — Week 6 MVP (final)
  |                 ↑  PR #19 (feature/week-6-polish, 9 commits)
  |
  ├── 365e7a4  PR #24 — Week 7 Slice 7A truthfulness validator (NOT a checkpoint: no caller yet)
  |
  ├── 6c269a0  Checkpoint 7 — Week 7 Application Preparation (final)
  |                 ↑  PR #28 (feature/week-7-application-prep, 8 commits)
  |
  ├── e5d6d36  PR #34 — Week 8 Slice 8A cost/usage accounting (NOT a checkpoint)
  |
  ├── f3fbf35  PR #35 — Week 8 Slice 8B corpus vectorizer cache (NOT a checkpoint)
  |
  ├── 9aba1f2  Checkpoint 8 — Week 8 Refinement, Caching and Cost Logging (final)
  |                 ↑  PR #36 (feature/week-8-operational-logs, 3 commits)
  |
  ├── 1afd4e5  PR #38 — ADR-027 Week 9 local-first deployment model
  |
  ├── 65b15bb  PR #39 — 9A-1 OpenAPI status  ·  89b616a  PR #40 — 9A-2 driver
  ├── 229acc1  PR #41 — 9A-3 production config  ·  88c884b  PR #42 — 9A-4 secrets
  ├── 8cd6ad8  PR #43 — 9A-5 privacy and logging
  |
  └── 95a1187  Checkpoint 9A — Week 9A Local Production Readiness  <- current
                    ↑  PR #44 (feature/week-9a7-documentation, 2 commits)
```

Checkpoint 0 is the single commit `e8c68b7` — the state of `main` at the end of Phase 0 — not the
two-commit range that built it. Each checkpoint is declared stable only after the merged `main`
state is verified: merge confirmed on GitHub, tree clean, full suite run from `main`, and CI
green on the merged commit.

**Checkpoint 9A is the current rollback target; Checkpoint 8 is next.** Earlier checkpoints remain
recoverable indefinitely and are not superseded — a regression whose cause predates the newest
checkpoint needs an older target. Recovering from Checkpoint 9A to Checkpoint 8 is code-only: Week 9
introduced no migration and no model. Its one dependency addition is the PostgreSQL driver, which
only a PostgreSQL deployment needs.

Recovery rules are in `context/workflow.md` § Recovery and rollback. In short: never rewrite
`main` history, never `git reset --hard` as recovery, never roll back without human approval.

---

## Next actions

1. **Nothing is pending. Week 9B is optional.** Week 9A is complete and recorded as
   Checkpoint 9A (`95a1187`). **Week 9B — Deployment and Sharing — is not required for ordinary
   use**, begins only when the owner decides to share EligiCore, and has seven open owner
   decisions in front of it (ADR-027). No phase rolls into the next automatically.
2. **Closed.** The OpenAPI "Current status" sentence was corrected in Week 9A-1 (PR #39): it now
   reads "Weeks 1–8 of a 10-week build are complete." and the two merged tests that pinned the old
   wording were re-aimed and strengthened. This tracked item, open since Checkpoint 6, is resolved.
3. **Open diagnostic item.** `test_no_candidate_marker_survives_any_path_under_production` failed
   once during Week 9A-6 and has passed in every run since, but its assertion text was not
   captured. The cause is unknown; the subsequent green runs do not establish that it was benign.
   Investigate if it recurs, and capture pytest output to a file so the next occurrence is
   diagnosable.
4. Before relying on live AI: exercise Gemini's `assess_field_relatedness` (and
   `extract_resume`) against the real service once, and confirm the model identifier. Both now
   carry cost and usage accounting, so a live call would also be the first real measurement of it.
   `generate_application_content` remains a deliberate stub; **live application generation was not
   implemented in Week 8 or Week 9A and is not scheduled by any merged decision.**
5. **Closed.** The migration chain has now been verified against PostgreSQL — Week 9A-2 ran the
   existing three revisions up, down and up again against local PostgreSQL 18.6 with data present,
   and Week 9A-6 executed the same rollback on the assembled application. `batch_alter_table`,
   which had only ever run on SQLite, fell through to plain `ALTER TABLE` as its docstrings claim.
   The dossier §9 precondition for deployment is satisfied.
6. **If live application generation is ever approved, it needs its own explicit privacy decision on
   cost logging.** Week 8 excluded `generate_application_content` from usage accounting
   structurally — no sink is threaded through it and no setting could enable one (ADR-026 D8) — and
   that exclusion is not something a later slice may quietly reverse.
7. **If Week 9B is ever activated, seven owner decisions come first** (ADR-027): Render vs Railway ·
   hosted PostgreSQL choice · rate-limiting mechanism and values · deployed AI provider · hosted
   catalogue seeding strategy · `/docs` exposure · shared-instance access control. None may be
   chosen implicitly, and an unauthenticated public API is not assumed acceptable merely because
   deployment is optional.

**Outstanding integration step:** the Gemini provider — resume extraction and field relatedness —
has never run against the live service. Confirm the model identifier and exercise one real call before
relying on live extraction.

**Weeks 1–8 are complete and Week 9A is complete; Week 9B is optional and Week 10 has not
started.** Nothing is deployed.

Checkpoint 9A (`95a1187`) is the Week 9A record and **Stable — current**; Checkpoint 8
(`9aba1f2`) is the final Week 8 record and now historical; Checkpoint 7 (`6c269a0`) is the final
Week 7 record; Checkpoint 6 (`13eb832`) remains the final Week 6 record and the dossier's declared
safe stopping point, with Checkpoint 6A the intermediate Week 6 one. **Week 8 has no intermediate
checkpoint — there is no Checkpoint 8A, 8B or 8C. There is no Checkpoint 9: it is reserved for the
final Week 9 state and exists only if the owner deliberately deploys.** The published OpenAPI
status now reads **"Weeks 1–8 of a 10-week build are complete."** — corrected in Week 9A-1, closing
the item tracked since Checkpoint 6.
No `/matching/score` route and no `/jobs/ingest` route exists. `POST /api/v1/applications/prepare`
exists and is POST-only, one of exactly ten routes — the same ten as at Checkpoint 7. Application
generation runs on the **mock provider only** — the Gemini generation method is a stub that raises
`AIProviderUnavailableError`, and no live Gemini call has ever been made from this project.
**Nothing is deployed:** no hosted instance, no public URL, no hosting artifact in the repository,
and no authentication or rate limiting.
**Caching and cost logging now exist, and both are bounded exactly as ADR-026 rules them:** one
process-local, in-memory corpus cache of capacity 4 holding catalogue-derived artifacts only, and
operational cost/usage log records for two AI operations. **No candidate-derived cache, no
generated-prose cache, no résumé-content retention, no cost table or ledger, no `candidate_id` in
any cost record, and no persistence, tracking, submission or automation code exists anywhere in
the repository.**

**Doc drift corrected:** the OpenAPI "Current status" string in `app/main.py` said the AI
field-relatedness stage was not yet implemented. The docs-only Checkpoint 4 record PR corrected the
description string; no route, schema, handler or behaviour changed.
