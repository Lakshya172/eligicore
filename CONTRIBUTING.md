# Contributing to EligiCore

EligiCore is a solo portfolio project, but it is maintained to a standard that assumes an
external engineer will read the history and need to understand it. This document is the working
agreement.

---

## Source of truth

```
EligiCore_Dossier_update.md      ← product, architecture, scope
            ↓
context/ + artifacts/decisions/  ← engineering context and ADRs
            ↓
context/state.md                 ← what actually exists right now
```

`AGENTOS.md` explains the engineering layer. **Read `context/state.md` before starting
anything** — it is the only file that describes reality rather than intent.

If the dossier and the engineering context disagree, or the dossier disagrees with itself:
**stop and report it.** Do not silently resolve it. Two such contradictions have already been
ruled on ([ADR-011](artifacts/decisions/ADR-011-no-server-side-candidate-or-application-persistence.md),
[ADR-012](artifacts/decisions/ADR-012-ingestion-state-operational-model.md)); two remain open
and are tracked in `context/state.md`.

---

## Architectural invariants

Twelve invariants are listed in full in [`context/architecture.md`](context/architecture.md) §9.
**Breaking one is a defect even if every test passes.** Breaking one deliberately requires a new
ADR and explicit approval. The ones most likely to be broken by accident:

| | |
|---|---|
| **INV-1** | No server-side persistence of candidate personal data. No `candidates`, `applications` or `evaluations` table. The dossier §8.2 folder listing that shows `models/candidate.py` is **stale** — see ADR-011. |
| **INV-2** | AI never overrides a verified deterministic hard-constraint failure. Enforce in control flow, not by prompt instruction. |
| **INV-3** | Missing or invalid data yields `UNKNOWN`/`NEEDS_REVIEW`, never automatic `NOT_ELIGIBLE`. Absence of evidence is not evidence of ineligibility. |
| **INV-4** | No PII in logs — including via stack traces and captured request bodies. |
| **INV-7** | Routers hold no business logic. Services must be importable and testable without FastAPI. |

---

## Privacy rules

These are not style preferences. Local-first personal data is the project's differentiator.

- **Never commit:** `.env`, secrets, API keys, credentials, real resumes, real candidate data,
  generated PII-bearing artifacts, local databases, caches.
- **Never log:** resume contents, candidate payloads, PII, generated content containing personal
  information, prompts populated with profile data.
- **Never persist server-side:** candidate profiles, resumes, evaluations, application records.
- Test fixtures must be **obviously synthetic**. No real names, emails, phone numbers or
  institutions.

Full detail: [`standards/security_privacy.md`](standards/security_privacy.md).

---

## Branching

`main` is the latest reviewed, stable state and is **always a known-good checkpoint**. No feature
development happens directly on `main`.

| Purpose | Pattern | Example |
|---|---|---|
| Phase work | `feature/week-N-<slug>` | `feature/week-1-foundation` |
| Bug fix | `fix/<short-description>` | `fix/cgpa-scale-comparison` |
| Docs only | `docs/<short-description>` | `docs/api-examples` |
| CI / tooling | `chore/<short-description>` | `chore/pin-dependencies` |

One branch per approved phase. Branch from an up-to-date `main`.

---

## Commits

Conventional commits, used consistently:

```
feat:     new product capability
fix:      bug fix
test:     tests only
docs:     documentation only
chore:    tooling, config, dependencies
refactor: behaviour-preserving restructuring
ci:       CI configuration
```

**Focused and incremental.** One coherent logical change per commit — not one giant commit
containing unrelated work. A reader should be able to follow the reasoning from the history
alone, and a bisect should land on something meaningful.

Good:

```
chore: establish application foundation and configuration
feat: add candidate profile schemas
feat: add candidate normalization service
test: add candidate schema coverage
docs: update AgentOS project state for Week 1
```

Do not squash away useful engineering history if doing so destroys the ability to understand
intermediate changes.

---

## The development loop

This loop is mandatory. **No phase automatically rolls into the next.**

```
Human approves phase → branch → implement → test → review → quality gates
   → context update → commit → push → PR → human review → merge → checkpoint
```

Stop at the checkpoint. Wait for the next explicit approval.

---

## Testing

- `pytest`, written alongside features rather than at the end.
- **The suite must run with no network and no API key.** All AI goes through a mock provider.
  A test requiring credentials is a broken test.
- Eligibility logic needs boundary, missing-value and invalid-value coverage — see
  [`standards/testing.md`](standards/testing.md) §3.
- A test that cannot fail is not a test.
- **Never weaken an eligibility assertion to make a suite green.**

Run before every PR:

```bash
pytest -q
```

---

## Review

Reviewers are lenses, not people — see [`reviewers/README.md`](reviewers/README.md). Select by
change impact; do not run all eight on every change.

| Change touches | Reviewers |
|---|---|
| Eligibility engine | architect + ai + qa |
| AI provider or prompts | ai + security + qa |
| API endpoint | api + qa |
| Database model or migration | architect + security + qa |
| Anything touching personal data | **security** (always) |
| Deployment | security + release |

Each returns `PASS` / `CONDITIONAL PASS` / `FAIL` with **file:line evidence**. "Looks fine" is
not a review result. A `FAIL` blocks the change.

---

## Quality gates

Applied by change size — see [`checklists/README.md`](checklists/README.md). A gate is passed by
**evidence**, not by assertion.

| Gate | When |
|---|---|
| QG-001 | Any finished unit of work |
| QG-002 | Eligibility logic changes — **no warning tier** |
| QG-003 | AI provider, prompts, generated content |
| QG-004 | Endpoint or schema changes |
| QG-005 | Anything touching personal data — **no warning tier, non-negotiable** |
| QG-006 | Database model or migration |
| QG-007 | Deployment |

---

## Pull requests

Every phase is delivered through a PR. The description must let another engineer understand
exactly what changed and why — sections for Summary, Scope, Out of Scope, Architecture Impact,
Data & Privacy, Tests, Reviewers, Quality Gates, Risks, Rollback, and Next Step.

Before opening a PR: tests pass, the app starts, gates pass, context is updated, no secrets or
candidate data are committed, and the working tree is clean.

---

## Checkpoints and rollback

Every merged PR is a project checkpoint. `main` must always be recoverable.

If a later phase introduces a regression:

1. Identify the regression.
2. Identify the last known-good checkpoint.
3. Investigate the cause.
4. Propose a rollback or revert strategy.
5. **Wait for human approval.**
6. Perform the approved recovery.

**Never** `git reset --hard` on a shared branch, and never rewrite published history as a
routine recovery mechanism. Prefer explicit `git revert` commits — recovery should be visible in
the history, not hidden from it.

---

## Scope discipline

Scope creep is the highest-rated risk in the dossier (§16).

- The feature set is fixed in advance. Additions need approval, not initiative.
- **Week 6 is the declared safe stopping point.** Everything after is enhancement.
- Out of scope until an explicit later phase: auto-submit, CAPTCHA/OTP/anti-bot handling,
  browser automation, frontend, authentication, live portal scraping.
- Out of scope permanently at this scale: microservices, Kubernetes, message brokers, event
  buses, multiple databases, autonomous agent graphs.

If a task appears to require one of these, it is a misunderstood task. Report it.
