# EligiCore — AgentOS Engineering Layer

> **What this is:** the engineering operating layer used to *develop and maintain* EligiCore.
> **What this is NOT:** part of EligiCore's runtime. No agent, reviewer, or workflow described
> here ships inside the product. EligiCore's runtime is a deterministic FastAPI service.

---

## Authority hierarchy

```
EligiCore_Dossier_update.md      ← SOURCE OF TRUTH for product, architecture, scope
            ↓
context/  (vision · architecture · tech_stack)   ← faithful restatement of the dossier
            ↓
artifacts/decisions/  (ADRs)      ← why the architecture is what it is
            ↓
context/state.md · context/memory.md             ← operational implementation reality
```

**If AgentOS context contradicts the dossier → the dossier wins, and the contradiction is
reported to the human. It is never silently resolved.**

Known open contradictions are tracked in `context/state.md` § Open Contradictions.

---

## Session start protocol

Every Claude Code session working on EligiCore reads, in order:

1. `context/state.md` — what is actually built, what is next, what is blocked. **Mandatory.**
2. `context/vision.md` — what EligiCore is and is not.
3. `context/workflow.md` — how work is done here.
4. `context/memory.md` — accumulated gotchas and conventions.

Then, conditionally by task type:

| Task touches | Also read |
|---|---|
| Architecture / new module | `context/architecture.md`, `context/decisions.md` |
| An API endpoint | `context/architecture.md`, `standards/api_design.md` |
| Eligibility engine | `standards/eligibility.md`, `ADR-003`, `ADR-006` |
| AI code | `standards/ai.md`, `ADR-004` |
| Anything touching personal data | `standards/security_privacy.md`, `ADR-001`, `ADR-002` |
| Job adapters | `ADR-005`, `context/architecture.md` |
| DB schema / migration | `standards/security_privacy.md`, `ADR-009` |

---

## Layout

| Path | Purpose |
|---|---|
| `context/` | Persistent project knowledge. Read every session. |
| `standards/` | What "good" means in this codebase. Consulted during implementation and review. |
| `reviewers/` | Review lenses. Applied selectively by change impact — see `reviewers/README.md`. |
| `checklists/` | Quality gates QG-001..QG-007. Applied selectively by change size. |
| `artifacts/decisions/` | ADRs — the durable record of architectural decisions. |
| `artifacts/reviews/` | Completed review notes worth keeping. |
| `artifacts/lessons/` | Post-hoc lessons from things that went wrong. |
| `.agentos/config.yml` | Machine-readable routing map for reviewers and context loading. |

---

## Hard rules for every session

These are restated in full in `context/architecture.md` § Architectural Invariants. Violating
any of them is a defect regardless of whether tests pass.

1. No server-side persistence of candidate personal data.
2. A verified deterministic hard-constraint failure is never overridden by AI.
3. Never log resume contents, profile payloads, or generated PII-bearing content.
4. Business logic never imports an AI vendor SDK directly.
5. Adding a job source is a new adapter class, never a change to eligibility or matching.
6. No auto-submit, no anti-bot circumvention, no browser automation.
7. Every eligibility verdict carries a per-requirement breakdown and a human-readable reason.

---

## Deliberate omissions

This layer is intentionally *smaller* than the framework it was adapted from. EligiCore is a
solo, 10-week, backend-only project. There is no orchestrator agent, no runtime simulator, no
token-budget accounting, no metrics dashboards, and no multi-agent escalation ladder — those
add process cost without adding safety at this scale. See `context/decisions.md` § Rejected
for the reasoning.
