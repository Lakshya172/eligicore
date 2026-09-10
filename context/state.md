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
| **Phase** | **Week 1 — Foundation and Candidate Profile Schema · COMPLETE** |
| **Roadmap position** | Week 1 of 10 complete and merged. **Week 2 NOT started.** |
| **Health** | 🟢 GREEN — 86 tests passing on `main`, CI green, no open blockers |
| **Stable branch** | `main` |
| **Current checkpoint** | **Checkpoint 1** — `2e79454f787019ff29af39fcfd285aee59c8bc77` |
| **Produced by** | PR #2, **MERGED** 2026-09-10 |
| **Next milestone** | Week 2: resume parser + AI service layer — awaiting explicit approval |
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

## Partial

| Item | State |
|---|---|
| Skill alias map (`app/services/candidate_normalizer.py`) | A deliberate **seed** of ~60 common variants, not an ontology. Extend it as real resumes reveal real variants. Unknown skills pass through with their casing intact. |
| Operational database | Foundation only — engine, session factory, `Base`. No models, no migrations. First table is the job catalogue in Week 3. |
| `get_db()` dependency | Written and exercised by no endpoint. Week 1 endpoints are stateless by design; it exists so Week 3 has a session source. |

## Missing — i.e. everything in the product

| Component | Roadmap week | Status |
|---|---|---|
| First Alembic **migration** (none needed yet — no tables until Week 3) | 3 | NOT STARTED |
| Resume parser (pdfplumber / python-docx / spaCy) | 2 | NOT STARTED |
| AI provider abstraction + first concrete provider + mock | 2 | NOT STARTED |
| Job model, base adapter, manual adapter, ingestion, dedup | 3 | NOT STARTED |
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

**Week 2 — Resume Parser and AI Service Layer.** **Not started, and not authorized to start** —
implementation begins only on explicit instruction.

Expected scope: `app/services/resume_parser.py` (pdfplumber, python-docx, spaCy fallback),
`app/ai/providers/base.py` plus a mock provider and one concrete provider, `app/ai/ai_service.py`,
`app/ai/prompts/`, and `POST /api/v1/resumes/parse`.

**Blocking decision before Week 2 starts:** C-4 / D-1 — which AI provider is the Phase 1 default.
The abstraction is provider-agnostic by construction, but a concrete provider cannot be written
until this is settled.

Reviewers: ai + security + qa (+ api for the parse endpoint). Gates: QG-001, QG-003, QG-004,
QG-005.

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
| **C-2** | §8.2 lists no model for `ingestion_state`, but §10.2 requires that table for ingestion to work across runs. | dossier §8.2 vs §10.2 | **RESOLVED 2026-09-10 — [ADR-012](../artifacts/decisions/ADR-012-ingestion-state-operational-model.md).** Same staleness, opposite direction. Ingestion is server-side operational functionality, so `app/models/ingestion_state.py` is legitimate — bounded to adapter identity, run history, timestamps, outcome counts and status. Never a `candidate_id`, never personal data. **Not yet implemented — Week 3 work.** |

### Still open — not to be resolved without instruction

| # | Contradiction | Where | Status |
|---|---|---|---|
| C-3 | §12.3 says generated content is checked "against the **stored** candidate profile." Under local-first nothing is stored server-side; §11 confirms the profile travels in the request body. Wording predates the local-first revision. | dossier §12.3 vs §8.1a/§11 | **OPEN — low impact, not urgent.** Reads as stale wording rather than a design conflict. Relevant at Week 7. |
| C-4 | §8.2 shows only `openai_provider.py` as a concrete provider; §9.2 names OpenAI, OpenRouter, Anthropic and local models as swappable. Which is the Phase 1 default is unstated. | dossier §8.2 vs §9.2 | **OPEN — needs a decision before Week 2.** Not a design conflict; an unmade choice. Recorded in `ADR-004` as deferred, and as D-1 in `context/decisions.md`. |

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

**Checkpoint 1 full SHA:** `2e79454f787019ff29af39fcfd285aee59c8bc77`

```
main
  |
  ├── e8c68b7  Checkpoint 0 — Phase 0 (AgentOS engineering layer)
  |
  └── 2e79454  Checkpoint 1 — Week 1 Foundation
                    ↑
                  PR #2  (feature/week-1-foundation, 11 commits)
```

Checkpoint 0 is the single commit `e8c68b7` — the state of `main` at the end of Phase 0 — not the
two-commit range that built it. Checkpoint 1 was declared stable only after the merged `main`
state was verified: merge confirmed on GitHub, tree clean, 86 tests passing from `main`, and CI
green on `2e79454`.

Recovery rules are in `context/workflow.md` § Recovery and rollback. In short: never rewrite
`main` history, never `git reset --hard` as recovery, never roll back without human approval.

---

## Next actions

1. **Human: settle C-4 / D-1** — which AI provider is the Phase 1 default. **Blocks Week 2.**
   The provider abstraction (ADR-004) is provider-agnostic by construction, but no concrete
   provider can be written until this is chosen.
2. **Await explicit instruction to begin Week 2.** No phase rolls into the next automatically.

**Week 2 has not started.** No Week 2 branch exists. No resume parsing, AI provider integration,
job ingestion, eligibility, matching or application preparation code exists anywhere in the
repository.
