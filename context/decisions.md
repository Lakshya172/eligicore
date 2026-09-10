# Decision Index — EligiCore

> Full records live in `artifacts/decisions/`. This file is the index and the rejected-options
> register. Every ADR here is **derived from a decision already made in the dossier** — none
> were invented during initialization.

---

## Accepted

| ADR | Title | Dossier source | Status |
|---|---|---|---|
| [ADR-001](../artifacts/decisions/ADR-001-local-first-personal-data.md) | Local-first personal data | §8.1a, §10 | Accepted |
| [ADR-002](../artifacts/decisions/ADR-002-stateless-candidate-apis.md) | Stateless candidate APIs | §11 | Accepted |
| [ADR-003](../artifacts/decisions/ADR-003-deterministic-eligibility-precedence.md) | Deterministic eligibility precedence | §12.1, §13.3 | Accepted |
| [ADR-004](../artifacts/decisions/ADR-004-ai-provider-abstraction.md) | AI provider abstraction | §9.2 | Accepted (Phase 1 default now set by ADR-013) |
| [ADR-005](../artifacts/decisions/ADR-005-pluggable-job-source-adapters.md) | Pluggable job-source adapters | §9.3, §6 | Accepted |
| [ADR-006](../artifacts/decisions/ADR-006-explainable-eligibility.md) | Explainable eligibility and matching | §12.2, §13.4 | Accepted |
| [ADR-007](../artifacts/decisions/ADR-007-truthfulness-validation.md) | Truthfulness validation | §12.3, §6 | Accepted |
| [ADR-008](../artifacts/decisions/ADR-008-no-auto-submit.md) | No auto-submit in current scope | §6 | Accepted |
| [ADR-009](../artifacts/decisions/ADR-009-database-strategy.md) | Database strategy: SQLite → PostgreSQL via SQLAlchemy + Alembic | §9, §10.2 | Accepted |
| [ADR-010](../artifacts/decisions/ADR-010-api-versioning.md) | API versioning under `/api/v1/` | §1, §11 | Accepted |
| [ADR-011](../artifacts/decisions/ADR-011-no-server-side-candidate-or-application-persistence.md) | No server-side candidate or application persistence — **ruling on C-1** | §8.2 vs §10.2 | Accepted 2026-09-10 |
| [ADR-012](../artifacts/decisions/ADR-012-ingestion-state-operational-model.md) | `ingestion_state` as an operational model — **ruling on C-2** | §8.2 vs §10.2 | Accepted 2026-09-10 |
| [ADR-013](../artifacts/decisions/ADR-013-gemini-flash-phase-1-default-provider.md) | Gemini Flash as the Phase 1 default AI provider — **resolves C-4 / D-1** | §9.2 | Accepted 2026-09-10 |

> **ADR-011 and ADR-012 are contradiction rulings.** They resolve internal inconsistencies in
> the dossier by owner decision. They do not overrule the dossier — they determine which of two
> conflicting dossier statements governs. In both cases the local-first architecture won.

---

## Deferred decisions

| # | Decision | Needed by | Note |
|---|---|---|---|
| ~~D-1~~ | ~~Which AI provider is the Phase 1 default~~ | ~~Week 2~~ | **RESOLVED 2026-09-10 — Google Gemini Flash. See ADR-013.** Concrete Phase 1 implementation only; the ADR-004 abstraction is unchanged and mandatory. |
| ~~D-2~~ | ~~Whether `models/candidate.py` / `models/application.py` exist at all~~ | ~~Week 1~~ | **RESOLVED 2026-09-10 — they must not exist. See ADR-011.** |
| D-3 | Hosting target — Render vs Railway | Week 9 | Either satisfies the dossier. No impact on application code. |
| D-4 | Whether `ingestion_state` needs its own deduplication-hash ledger, given `jobs.content_hash` is already the canonical dedup index | Week 3 | Opened by ADR-012. Deliberately not settled during Phase 0 — deciding it would mean designing the ingestion engine before it is approved. |

---

## Rejected — AgentOS framework concepts

Recorded so the reasoning is not relitigated. These come from evaluating Raptor's Way
(`github.com/Rexy-5097/raptors-way`) for adoption here.

| Concept | Verdict | Reason |
|---|---|---|
| `runtime/harness/`, `runtime/loop/`, `runtime/kernel/` Python modules | **Rejected** | Inspected directly: 14–96 lines each, keyword-matching and `print()` statements, no LLM invocation anywhere. `quality_evaluator.py` carries a literal `# Mock confidence formula` comment. These simulate an agent runtime; Claude Code *is* the runtime. Copying them would add code that does nothing. |
| `tools/scripts/simulate_agent_runtime.py` | **Rejected** | Simulates routing against a hardcoded trigger map. Useful for validating that framework's own docs; no value to a product codebase. |
| `validation/scenarios/` + `validation/runner/` (21 VS-xxx scenarios) | **Rejected** | These validate the simulator's keyword routing against expectations about the simulator — self-referential. EligiCore's equivalent is a real pytest suite against real eligibility logic. |
| `tools/scripts/validate_agentos.py` (1161 lines) | **Rejected as-is** | A documentation-integrity linter tightly coupled to that repo's own file inventory (it checks for harness, loop, certification and distribution artifacts EligiCore will never have). The *idea* — CI that fails when docs and reality drift — is worth revisiting later at a fraction of the size. |
| `orchestrator` agent as a routing intermediary | **Rejected** | It routes reviews to reviewers. In a solo project with one session, that is a hop with no decision in it. Reviewers are selected directly from the trigger map. |
| Per-agent token budgets and context-size targets | **Rejected** | Manual token accounting maintained by hand goes stale immediately and buys nothing here. |
| `metrics/` dashboards, `production_certification/`, `production_validation/` | **Rejected** | Release-theatre for a team product. This is a solo 10-week portfolio backend. |
| Authority levels (L1/L2/L3) and the escalation ladder | **Rejected** | Escalation targets are other agents. With one human and one session, escalation is "ask the human." |
| 8 profiles (`isro.yaml`, `hackathon.yaml`, `ml.yaml`, …) | **Rejected** | EligiCore has exactly one profile: itself. |
| `.github/` templates, CODEOWNERS, PR templates | **Rejected for now** | No collaborators, and no git repository yet. Revisit if the project gains contributors. |

## Adapted — concepts kept, but simplified

| Concept | How it was adapted |
|---|---|
| `context/` seven-file layer | **Kept wholesale** — the strongest idea in the framework, and it matches the requested structure exactly. Filled with real EligiCore content rather than templates. |
| Agent contract format (identity, responsibilities, non-responsibilities, inputs, outputs, escalation) | Adapted into `reviewers/` — kept responsibilities, non-responsibilities, the binary question list and the PASS/CONDITIONAL/FAIL model. Dropped lifecycle state machines, token budgets and authority levels. |
| Quality gates as checklists with entry criteria, evidence and an exit decision model | **Kept** — the evidence column is the valuable part. Reduced from 8 generic gates to 7 EligiCore-specific ones, including gates the framework had no equivalent of (eligibility, privacy). |
| ADR-per-decision in `artifacts/decisions/` | **Kept.** The framework's own 56 ADRs are mostly about the framework, but the pattern is right. |
| Reviewer trigger map keyed on changed paths | **Kept**, as a table in `reviewers/README.md` and `.agentos/config.yml`, rather than as executable routing code. |
| `standards/` per domain | Kept, retargeted. Dropped `ui_ux.md` and `research.md` (no UI, no research). Added `eligibility.md`, which has no counterpart in the framework and encodes EligiCore's actual core. |
| Master workflow lifecycle | Compressed into `context/workflow.md`. The framework's five domain workflows are all explicit placeholders ("will be populated in Phase 2") — there was nothing to adopt. |
