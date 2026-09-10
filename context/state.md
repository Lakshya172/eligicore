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
| **Phase** | **Phase 0 — initialization complete / Week 1 ready** |
| **Roadmap position** | Pre-Week-1. Zero product code written. |
| **Health** | 🟢 GREEN — no code, therefore no defects; scope and architecture settled; no open blockers |
| **Next milestone** | Week 1: running API + operational DB + candidate profile schema |
| **Repository** | Git initialized 2026-09-10. Branch `master`. No commits yet, no remote configured. |
| **Python available** | 3.12.10 (dossier requires 3.11+ — satisfied) |

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

## Partial

*Nothing. There is no partially-built product code.*

## Missing — i.e. everything in the product

| Component | Roadmap week | Status |
|---|---|---|
| `app/` package, `main.py`, `config.py` | 1 | NOT STARTED |
| `database.py`, SQLAlchemy base/session | 1 | NOT STARTED |
| Candidate Pydantic schemas + validate/normalize endpoints | 1 | NOT STARTED |
| Alembic setup and first migration | 1 | NOT STARTED |
| Resume parser (pdfplumber / python-docx / spaCy) | 2 | NOT STARTED |
| AI provider abstraction + first concrete provider + mock | 2 | NOT STARTED |
| Job model, base adapter, manual adapter, ingestion, dedup | 3 | NOT STARTED |
| Eligibility engine (deterministic stage) | 4 | NOT STARTED |
| Eligibility engine (AI ambiguity stage) | 4 | NOT STARTED |
| Matching engine (skill normalization, TF-IDF, cosine) | 5 | NOT STARTED |
| Excel export (openpyxl) | 6 | NOT STARTED |
| Test suite (pytest), deterministic eligibility suite | 1–6, continuous | NOT STARTED |
| Application preparation + truthfulness validator | 7 | NOT STARTED |
| Caching, AI cost logging | 8 | NOT STARTED |
| Deployment (Render/Railway), README, docs | 9 | NOT STARTED |

**Week 6 is the declared safe stopping point** — at that line the system is complete and
demoable. Weeks 7–10 are enhancement.

---

## Next approved phase

**Week 1 — Foundation and Candidate Profile Schema.** Approved as the next phase. **Not started,
and not authorized to start** — implementation begins only on explicit instruction.

Scope, expected files, tests, reviewers (api + qa + security + architect) and gates
(QG-001, QG-004, QG-005) are as reported in the Phase 0 session and must be re-confirmed before
implementation begins.

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

## Next actions

1. **Await instruction to begin Week 1.** Phase 0 is complete; nothing is blocked.
2. At Week 1 start: confirm scope, then implement Foundation and Candidate Profile Schema.
3. Before Week 2: settle C-4 / D-1 — which AI provider is the Phase 1 default.
4. Open question for the owner, non-blocking: whether to make an initial commit of the Phase 0
   engineering layer. `git init` was run as instructed; **no commit was made**, because none was
   requested. 46 files are currently untracked.
