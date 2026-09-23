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
| [ADR-014](../artifacts/decisions/ADR-014-job-status-model.md) | Job status: dossier enum stored, `is_active` derived — **reconciles C-5** | §10.2 | Accepted 2026-09-10 |
| [ADR-015](../artifacts/decisions/ADR-015-ingestion-state-one-row-per-source.md) | `ingestion_state`: one row per source, no run log, no hash ledger — **resolves C-6 / D-4** | §10.2 | Accepted 2026-09-10 |
| [ADR-016](../artifacts/decisions/ADR-016-local-personal-data-store.md) | Phase 1 local personal-data store at `~/.eligicore/` — **recorded, not implemented** | §8.1a, §10.1 | Accepted 2026-09-10 |
| [ADR-017](../artifacts/decisions/ADR-017-eligibility-states-and-verdict-precedence.md) | Eligibility states and verdict precedence — **rules on C-9, C-13, R-2, R-4** | §7, §10.1, §12.1 | Accepted 2026-09-17 |
| [ADR-019](../artifacts/decisions/ADR-019-ai-assisted-field-relatedness.md) | AI-assisted field-of-study relatedness — the only AI eligibility stage; cannot produce `NOT_ELIGIBLE`; fails closed; minimum input — **implements A-3, R-2; applies C-14** | §7, §12.1 | Accepted 2026-09-17 |
| [ADR-020](../artifacts/decisions/ADR-020-match-scoring.md) | Match scoring — narrow inputs, skill/text namespaces, custom tokenizer, TF-IDF fitted on the whole catalogue (never the candidate), cosine 0–100 or null, separate skill coverage, template explanations, `MATCHING_VERSION` 1 | §7, §9, §12.2 | Accepted 2026-09-17 |
| [ADR-021](../artifacts/decisions/ADR-021-skill-comparison-for-matching.md) | Skill comparison for matching — canonical lookup key, alias table only, aliases on skill lists never prose, no splitting, `.NET` correction | §12.2 | Accepted 2026-09-17 |
| [ADR-022](../artifacts/decisions/ADR-022-recommendation-orchestration.md) | Recommendation orchestration — reuses Week 4 eligibility and Week 5A matching unchanged; corpus is the whole catalogue, scope is ACTIVE+UNKNOWN (≤50) or explicit ids; groups `ranked` / `needs_review` / `not_eligible` / `not_open` (precedence); no score in `not_eligible`, full match result but no rank in `not_open`; composed explanations; corpus fingerprint — **rules on C-19..C-22** | §7, §11, §12.2 | Accepted 2026-09-19 |
| [ADR-023](../artifacts/decisions/ADR-023-tracker-export-contract.md) | Tracker export contract — client-supplied rows rendered in memory to `.xlsx`; no database, AI or enrichment; 1–500 rows, unique `job_id`; five `ApplicationStatus` values; nullable score as an empty cell; optional Requirements sheet; formula-injection defence; fixed metadata and filename; binary 200 as the one documented API exception; `/matching/score` and `/jobs/ingest` deferred — **rules on C-23..C-29** | §7, §9, §10.1, §11, §15 | Accepted 2026-09-19 |
| [ADR-024](../artifacts/decisions/ADR-024-week-6-mvp-scope.md) | Week 6 MVP scope — local `seed-catalogue` command instead of HTTP ingestion, Alembic-head guard, 40 synthetic curated jobs with the original five preserved, ACTIVE-only curated source (no `RawJob` status; ADR-014 enum kept), three catalogue-coupled test changes, offline full-flow test over two profiles, local quickstart — **rules on C-30..C-34** | §6, §7, §8.2, §11, §15, §16, §17 | Accepted 2026-09-20 |
| [ADR-025](../artifacts/decisions/ADR-025-week-7-application-preparation.md) | Week 7 application preparation and truthfulness validation — one catalogue `job_id`, client-supplied questions (≤5), remove-by-default validation with a structured audit list, deterministic AI-free validator, an eleven-field provider allow-list with `resume_raw_text` never leaving the service, knowledge-boundary removals, unaddressed and unsigned letters, no eligibility coupling, no caching, no persistence and no migration; live provider generation deferred to Week 8/9 — **rules on C-3, C-35..C-40, A-53..A-70** | §6, §7, §8.2, §11, §12.3, §15, §17 | Accepted 2026-09-20 |
| [ADR-026](../artifacts/decisions/ADR-026-week-8-refinement-caching-and-cost-logging.md) | Week 8 refinement, caching and cost logging — cost/usage accounting for `extract_resume` and `assess_field_relatedness` only, through a per-call usage sink with configuration-driven pricing, retry accumulation and unknown-means-unknown degradation; a candidate-free corpus vectorizer cache keyed by `corpus_fingerprint` (bounded in-memory LRU, candidate transform never cached); "refinement" ruled to mean operational-log completeness per §10.2; generation-path token/length/cost logging excluded and ADR-025 unamended; operational logs only — no table, migration, dependency, route or schema change; live Gemini application generation stays deferred — **rules on W8-A..W8-H; supersedes ADR-020 §5 in part** | §9, §9.2, §10.2, §15, §16 | Accepted 2026-09-23 |
| [ADR-018](../artifacts/decisions/ADR-018-eligibility-requirement-inputs.md) | Eligibility requirement inputs: same-scale grades, qualification selection, `min_degree_level`, exact-match fields — **rules on C-10, C-12, A-1, A-2, A-4** | §10.2, §12.1, §17 | Accepted 2026-09-17 |

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
| ~~D-4~~ | ~~Whether `ingestion_state` needs its own deduplication-hash ledger~~ | ~~Week 3~~ | **RESOLVED 2026-09-10 — no ledger. See ADR-015.** `jobs.content_hash` stays the single dedup index; a second hash store would be a copy with its own chance to drift. |

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
