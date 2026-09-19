# Project State — EligiCore

> **MANDATORY first read for every session.**
> **Rule:** nothing is marked complete because the dossier plans it. Only because it exists,
> runs, and is tested. Planned ≠ done.
> **Update:** at the end of every session that changes the repository.

---

## Snapshot

| Field | Value |
|---|---|
| **Date** | 2026-09-17 |
| **Phase** | **Week 5 — Matching Engine · IN PROGRESS** — PR 5A merged and verified (Checkpoint 5A); PR 5B (recommendations) implemented, **in review, not merged** |
| **Roadmap position** | Weeks 1–4 complete and merged. Week 5 PR 5A **merged and verified** (Checkpoint 5A). PR 5B open on `feature/week-5-recommendations`, **not merged**. |
| **Health** | 🟢 GREEN — 736 tests on `main`; 833 on the PR 5B branch; no open blockers |
| **Stable branch** | `main` |
| **Current checkpoint** | **Checkpoint 5A** (intermediate, matching engine) — `05534affced482f6bc5e188ac465144dd425f9a7` |
| **Produced by** | PR #13 (`feature/week-5-matching-engine`), **MERGED** 2026-09-17 |
| **Rollback target** | Checkpoint 5A first; Checkpoint 4 by reverting PR #13 (no database step); Checkpoint 4A by also reverting PR #11; Checkpoint 3 also needs `alembic downgrade 7c2f1a9b4d30`; below Checkpoint 3 also needs `alembic downgrade base`. |
| **Next milestone** | PR 5B external review and merge decision. **Checkpoint 5 not established.** |
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

## Partial

| Item | State |
|---|---|
| Skill alias map (`app/services/candidate_normalizer.py`) | A deliberate **seed** of ~60 common variants, not an ontology. Extend it as real resumes reveal real variants. Unknown skills pass through with their casing intact. |
| Operational database | Foundation only — engine, session factory, `Base`. No models, no migrations. First table is the job catalogue in Week 3. |
| `get_db()` dependency | Written and exercised by no endpoint. Week 1 and 2 endpoints are stateless by design; it exists so Week 3 has a session source. |
| **Jobs API trigger for ingestion** | `POST /api/v1/jobs/ingest` is in dossier §11 but **not** in the approved Week 3 API scope. Ingestion is implemented and tested as a service; no trigger endpoint is exposed. Deferred, not dropped. |
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
| Recommendations (eligibility + matching, `POST /api/v1/recommendations`) | 5 | **IN REVIEW** — PR 5B, not merged (ADR-022) |
| Excel export (openpyxl) | 6 | NOT STARTED |
| Deterministic **eligibility** test suite (boundary/missing/invalid per constraint) | 4 | **COMPLETE** — PR #9 |
| Application preparation + truthfulness validator | 7 | NOT STARTED |
| Caching, AI cost logging | 8 | NOT STARTED |
| Deployment (Render/Railway), README, docs | 9 | NOT STARTED |

**Week 6 is the declared safe stopping point** — at that line the system is complete and
demoable. Weeks 7–10 are enhancement.

---

## Next approved phase

**Week 5 — Matching Engine.** Design gate approved 2026-09-17; split into PR 5A and PR 5B.

- **PR 5A — deterministic matching foundation.** **Merged** as PR #13 (`05534af`) and verified
  post-merge; recorded as intermediate **Checkpoint 5A**. Service only: `app/services/matching_engine.py`
  (narrow inputs, skill comparison, custom tokenizer, TF-IDF fitted on the whole catalogue,
  cosine 0–100 or null, skill coverage, top terms, template explanations, ordering key),
  `scikit-learn==1.7.2`, the `.NET` normalizer correction, ADR-020 and ADR-021. No router, no
  endpoint, no eligibility, AI or database change.
- **PR 5B — recommendations.** Implemented on `feature/week-5-recommendations`, open for
  external review, **not merged**. `POST /api/v1/recommendations`: one catalogue query, one
  Week 4 eligibility pass, one Week 5A matching pass over the whole catalogue; default scope
  ACTIVE + UNKNOWN capped at 50 with disclosure; explicit ids of any status; groups `ranked`,
  `needs_review`, `not_eligible`, `not_open` (precedence); no score for `NOT_ELIGIBLE`;
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

### Still open — not to be resolved without instruction

| # | Contradiction | Where | Status |
|---|---|---|---|
| C-3 | §12.3 says generated content is checked "against the **stored** candidate profile." Under local-first nothing is stored server-side; §11 confirms the profile travels in the request body. Wording predates the local-first revision. | dossier §12.3 vs §8.1a/§11 | **OPEN — low impact, not urgent.** Reads as stale wording rather than a design conflict. Relevant at Week 7. |


---

## Recent decisions

Full index in `context/decisions.md`.

| ADR | Title | Date |
|---|---|---|
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
| **5A** | Week 5 — Deterministic Matching Engine (**intermediate**) | `05534af` | PR #13, merged 2026-09-17 | **Stable — current** |

**Checkpoint 1 full SHA:** `2e79454f787019ff29af39fcfd285aee59c8bc77`
**Checkpoint 2 full SHA:** `91dd31d50e7749ad37acf14babd5d1ee90141abd`
**Checkpoint 3 full SHA:** `2cfd4f0276b60de393ec604afc10b3c52f483ca7`
**Checkpoint 4A full SHA:** `4a5cb844d1aa4ca4aa3e0906481d0d91c8fc67d4`
**Checkpoint 4 full SHA:** `f56d7dfabeeb8a7addac693d2c7552b0c1fc4e76`
**Checkpoint 5A full SHA:** `05534affced482f6bc5e188ac465144dd425f9a7`

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
  └── 05534af  Checkpoint 5A — Week 5 deterministic matching engine (intermediate)  <- current
                    ↑  PR #13 (feature/week-5-matching-engine, 5 commits)
```

Checkpoint 0 is the single commit `e8c68b7` — the state of `main` at the end of Phase 0 — not the
two-commit range that built it. Each checkpoint is declared stable only after the merged `main`
state is verified: merge confirmed on GitHub, tree clean, full suite run from `main`, and CI
green on the merged commit.

**Checkpoint 5A is the current rollback target; Checkpoint 4 is next.** Earlier checkpoints remain
recoverable indefinitely and are not superseded — a regression whose cause predates the newest
checkpoint needs an older target.

Recovery rules are in `context/workflow.md` § Recovery and rollback. In short: never rewrite
`main` history, never `git reset --hard` as recovery, never roll back without human approval.

---

## Next actions

1. **PR 5B awaits external review.** Do not merge it, and do not create Checkpoint 5 or start
   any further work, without explicit instruction.
2. Before relying on live AI: exercise Gemini's `assess_field_relatedness` (and
   `extract_resume`) against the real service once, and confirm the model identifier.
3. Before deployment (Week 9 / QG-007): verify the migration chain against PostgreSQL.
   `batch_alter_table` has only ever run on SQLite.

**Outstanding integration step:** the Gemini provider — resume extraction and field relatedness —
has never run against the live service. Confirm the model identifier and exercise one real call before
relying on live extraction.

**Week 5 is in progress; Weeks 6–10 have not started.** PR 5A (matching engine, service only) is
merged as Checkpoint 5A. PR 5B (recommendations endpoint) is in review on
`feature/week-5-recommendations`. No `/matching/score` or
application preparation code exists anywhere in the repository.

**Doc drift corrected:** the OpenAPI "Current status" string in `app/main.py` said the AI
field-relatedness stage was not yet implemented. The docs-only Checkpoint 4 record PR corrected the
description string; no route, schema, handler or behaviour changed.
