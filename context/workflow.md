# Development Workflow — EligiCore

> **The controlling rule of this project:** work proceeds one human-approved step at a time.
> Claude understands → reports → human reviews → approves a step → Claude implements → tests →
> reviews → human audits → next approved step.
>
> **Never blindly implement a task without first understanding its architectural impact.**

---

## The loop

```
   Understand  →  Plan  →  Implement  →  Test  →  Review  →  Validate
                                                                │
                                          Commit  ←  Update Context
```

Each stage has an exit condition. Skipping a stage is not a shortcut; it is how invariants get
broken quietly.

---

## 1. Understand

Before writing any code:

- Read `context/state.md`. It is the ground truth for what exists.
- Read the relevant dossier section. The dossier outranks everything in this layer.
- Identify which architectural invariants (`context/architecture.md` §9) the task touches.
- Identify which ADRs constrain the task.

**Exit:** you can state what the task changes, which layer it belongs in, and which invariants
apply. If the task appears to require breaking an invariant → **stop and report**, do not
proceed.

## 2. Plan

- State scope: what is IN and what is OUT.
- List expected files — created and modified.
- List expected tests, including the failure and boundary cases, not only the happy path.
- Choose reviewers by impact (`reviewers/README.md`).
- Choose quality gates by change size (`checklists/`).
- Flag anything that would be an architectural change (see § below).

**Exit:** human approves the plan. For anything beyond a trivial fix, this approval is
explicit and required.

## 3. Implement

- Stay inside the approved scope. Discovering adjacent work is normal; doing it unasked is not
  — note it and raise it.
- Follow `standards/`.
- Keep layer boundaries intact: routers thin, services framework-free, AI behind the interface.

**Exit:** the approved scope is implemented. Nothing extra is.

## 4. Test

- Unit tests for service logic, without starting a server.
- Integration tests for endpoint contracts.
- Boundary tests wherever a comparison exists (CGPA exactly at cutoff, graduation year at both
  window edges, backlogs exactly at limit).
- Missing-data and invalid-data tests — these must yield `UNKNOWN`/`NEEDS_REVIEW`, not failure.
- AI is exercised through the mock provider. The suite must run with no network and no API key.

**Exit:** tests pass, and the new tests would actually fail if the code were wrong. A test that
cannot fail is not a test.

## 5. Review

Apply only the reviewers the change warrants (`reviewers/README.md`). Each produces
`PASS` / `CONDITIONAL PASS` / `FAIL` with specific evidence — file and line, not vibes.

## 6. Validate

Run the applicable quality gates from `checklists/`. A gate is not passed by assertion; it is
passed by evidence.

## 7. Update context

- `context/state.md` — move the item from Missing to Partial or Completed. Update blockers,
  risks, next step. **This is not optional bookkeeping; the next session depends on it.**
- `context/memory.md` — record anything that cost time and would cost time again.
- `artifacts/decisions/` — add an ADR if an architectural decision was made.

## 8. Commit

- Small, incremental, meaningful messages. The history is portfolio evidence (dossier §17).
- Never commit `.env`, secrets, resume fixtures containing real personal data, or generated
  content containing PII.
- Commit only when the human asks, or when committing was part of the approved step.

---

## Architectural change protocol

A change is architectural if it alters a layer boundary, a data-ownership rule, an interface
contract, the eligibility evaluation order, the persistence model, or the API contract.

Before making one:

1. **Identify** the change precisely.
2. **Explain** why it is necessary — what specifically fails without it.
3. **Check the dossier.** Does it already rule on this?
4. **Check existing ADRs.** Does this contradict one?
5. **Identify affected modules** and the blast radius.
6. **Get human approval.**
7. **Record the ADR** — including what was superseded.

**Never silently change the architecture.** Discovering mid-implementation that the plan
requires an architectural change means stopping and reporting, not improvising.

---

## Contradiction protocol

If the dossier and this AgentOS layer disagree, or the dossier disagrees with itself:

1. **Stop.**
2. Record it in `context/state.md` § Open Contradictions with both sources cited.
3. Report it to the human.
4. **Do not silently resolve it.** If work must continue, state the working assumption
   explicitly and confine it to planning — never bake it into code.

The dossier is the source of truth for the product. This layer records implementation reality.

---

## Scope discipline

Dossier §16 names scope creep as the highest-severity risk to this project. Concretely:

- The feature set is fixed in advance. Additions need approval, not initiative.
- **Week 6 is the declared safe stopping point.** Everything after it is enhancement.
- Out of scope until an explicit future phase: auto-submit, CAPTCHA/OTP/anti-bot handling,
  browser automation, frontend, authentication, multi-user isolation, live portal scraping.
- Out of scope permanently at this scale: microservices, Kubernetes, message brokers,
  distributed systems, event buses, multiple databases, autonomous agent graphs, dashboards.

If a task seems to require one of these, that is a signal the task is misunderstood. Report it.

---

## Session start and end

**Start:** read `context/state.md`, `context/vision.md`, `context/workflow.md`,
`context/memory.md`. Then load conditionally per the table in `AGENTOS.md`.

**End:** update `context/state.md` honestly. A state file that overstates progress is worse
than no state file, because the next session will build on a false premise.
