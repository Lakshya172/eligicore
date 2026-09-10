# Project State — EligiCore

> **MANDATORY first read for every session.**
> **Rule:** nothing is marked complete because the dossier plans it. Only because it exists,
> runs, and is tested. Planned ≠ done.
> **Update:** at the end of every session that changes the repository.

---

## Snapshot

| Field | Value |
|---|---|
| **Date** | 2026-09-10 |
| **Phase** | **Week 3 — Job Schema, Adapters and Ingestion · implementation complete, PR open** |
| **Roadmap position** | Weeks 1–2 merged. Week 3 implemented, awaiting review. **Week 4 NOT started.** |
| **Health** | 🟢 GREEN — 318 tests passing, no open blockers |
| **Stable branch** | `main` |
| **Stable branch** | `main` |
| **Current checkpoint** | **Checkpoint 2** — `91dd31d50e7749ad37acf14babd5d1ee90141abd` |
| **Produced by** | PR #4, **MERGED** 2026-09-10 |
| **Rollback target** | Checkpoint 2 first; Checkpoint 1 (`2e79454`) remains available |
| **Next milestone** | Week 4: eligibility engine — **not started, not authorized** |
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
| **Week 3 — tests** | 115 new (318 total). Weeks 1–2's 203 unchanged. Three mutations verified. |
| **QG-008** | New quality gate for resume processing and AI extraction |

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
| Eligibility engine (deterministic stage) | 4 | NOT STARTED |
| Eligibility engine (AI ambiguity stage) | 4 | NOT STARTED |
| Matching engine (skill normalization, TF-IDF, cosine) | 5 | NOT STARTED |
| Excel export (openpyxl) | 6 | NOT STARTED |
| Deterministic **eligibility** test suite (boundary/missing/invalid per constraint) | 4 | NOT STARTED |
| Application preparation + truthfulness validator | 7 | NOT STARTED |
| Caching, AI cost logging | 8 | NOT STARTED |
| Deployment (Render/Railway), README, docs | 9 | NOT STARTED |

**Week 6 is the declared safe stopping point** — at that line the system is complete and
demoable. Weeks 7–10 are enhancement.

---

## Next approved phase

**Week 4 — Eligibility Engine.** **Not started, and not authorized to start.**

This is the phase the whole project exists for, and the one with the least room for error:
deterministic hard constraints evaluated first with final authority, AI only for genuine
ambiguity, and `UNKNOWN`/`NEEDS_REVIEW` wherever evidence is absent (ADR-003, INV-2, INV-3).

Week 3 deliberately left it the raw material rather than pre-empting it: `min_cgpa_scale` is
stored exactly as a source states it and is never inferred, so a job with an unstated scale
must resolve to `UNKNOWN` rather than an assumed 10-point comparison.

Gates: QG-001, QG-002 (no warning tier), QG-004. Reviewers: architect + ai + qa.

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

### Still open — not to be resolved without instruction

| # | Contradiction | Where | Status |
|---|---|---|---|
| C-3 | §12.3 says generated content is checked "against the **stored** candidate profile." Under local-first nothing is stored server-side; §11 confirms the profile travels in the request body. Wording predates the local-first revision. | dossier §12.3 vs §8.1a/§11 | **OPEN — low impact, not urgent.** Reads as stale wording rather than a design conflict. Relevant at Week 7. |


---

## Recent decisions

Full index in `context/decisions.md`.

| ADR | Title | Date |
|---|---|---|
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
| **2** | Week 2 — Resume Parser and Gemini Flash AI Service Layer | `91dd31d` | PR #4, merged 2026-09-10 | **Stable — current** |

**Checkpoint 1 full SHA:** `2e79454f787019ff29af39fcfd285aee59c8bc77`
**Checkpoint 2 full SHA:** `91dd31d50e7749ad37acf14babd5d1ee90141abd`

```
main
  |
  ├── e8c68b7  Checkpoint 0 — Phase 0 (AgentOS engineering layer)
  |
  ├── 2e79454  Checkpoint 1 — Week 1 Foundation
  |                 ↑  PR #2  (feature/week-1-foundation, 11 commits)
  |
  └── 91dd31d  Checkpoint 2 — Week 2 Resume Parser + Gemini Flash AI  <- current
                    ↑  PR #4  (feature/week-2-resume-ai, 16 commits)
```

Checkpoint 0 is the single commit `e8c68b7` — the state of `main` at the end of Phase 0 — not the
two-commit range that built it. Each checkpoint is declared stable only after the merged `main`
state is verified: merge confirmed on GitHub, tree clean, full suite run from `main`, and CI
green on the merged commit.

**Checkpoint 2 is the current rollback target. Checkpoint 1 remains recoverable indefinitely**
and is not superseded — a regression whose cause predates Week 2 needs a target older than the
newest checkpoint.

Recovery rules are in `context/workflow.md` § Recovery and rollback. In short: never rewrite
`main` history, never `git reset --hard` as recovery, never roll back without human approval.

---

## Next actions

1. **Human: review the Week 3 PR.** It must not be merged without explicit authorization,
   regardless of CI status.
2. On merge: verify `main`, then record **Checkpoint 3** with its exact commit SHA.
3. **Await explicit instruction to begin Week 4.** No phase rolls into the next automatically.

**Outstanding integration step, not blocking the PR:** the Gemini provider has never run
against the live service. Confirm the model identifier and exercise one real call before
relying on live extraction.

**Weeks 4–10 have not started.** No Week 4 branch exists. No eligibility, matching, recommendations or application
preparation code exists anywhere in the repository.
