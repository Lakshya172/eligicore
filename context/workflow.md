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

## Checkpoint registry

**This table is the canonical definition of every checkpoint.** Where any other document
mentions a checkpoint, this one governs.

A **checkpoint** is one exact commit on `main` at which the project was verified healthy. It is
not a release, not a version, and not a tag. A phase may take many commits; the checkpoint is
the single commit on `main` where that phase's merge landed.

| # | Checkpoint | Commit on `main` | Produced by | CI | Tests | State |
|---|---|---|---|---|---|---|
| **0** | Phase 0 — AgentOS engineering layer | `e8c68b7` | Direct commits to `main` before branch protection (`7f7abbb` then `e8c68b7`) | n/a — CI did not exist yet | n/a — no product code | **Stable** |
| **1** | Week 1 — Foundation and Candidate Profile Schema | `2e79454` | PR #2 (`feature/week-1-foundation`), merged 2026-09-10 | ✅ `test` success on `2e79454` | 86 passed | **Stable** |
| **2** | Week 2 — Resume Parser and Gemini Flash AI Service Layer | `91dd31d` | PR #4 (`feature/week-2-resume-ai`), merged 2026-09-10 | ✅ `test` success on `91dd31d` | 203 passed | **Stable** |
| **3** | Week 3 — Job Schema, Adapters and Ingestion | `2cfd4f0` | PR #6 (`f538015`) + PR #7 (`2cfd4f0`), merged 2026-09-10 | ✅ `test` success on `2cfd4f0` | 328 passed | **Stable** |
| **4A** | Week 4 — Deterministic Eligibility Engine (PR 4A) · **intermediate** | `4a5cb84` | PR #9 (`feature/week-4-eligibility-engine`), merged 2026-09-17 | ✅ `test` success on `4a5cb84` | 524 passed | **Stable** |
| **4** | Week 4 — Eligibility Intelligence (final: PR 4A + PR 4B) | `f56d7df` | PR #9 (`4a5cb84`) + PR #11 (`feature/week-4-eligibility-ai`), merged 2026-09-17 | ✅ `test` success on `f56d7df` | 615 passed | **Stable — current** |

**Checkpoint 1 full SHA:** `2e79454f787019ff29af39fcfd285aee59c8bc77`
**Checkpoint 2 full SHA:** `91dd31d50e7749ad37acf14babd5d1ee90141abd`
**Checkpoint 3 full SHA:** `2cfd4f0276b60de393ec604afc10b3c52f483ca7`
**Checkpoint 4A full SHA:** `4a5cb844d1aa4ca4aa3e0906481d0d91c8fc67d4`
**Checkpoint 4 full SHA:** `f56d7dfabeeb8a7addac693d2c7552b0c1fc4e76`

**Checkpoint 4A is intermediate, not Checkpoint 4.** Week 4 is delivered in two PRs. 4A marks the
verified deterministic engine; **Checkpoint 4 is reserved for Week 4 as a whole** and is
established only after PR 4B (the AI field-relatedness stage) is merged and verified. 4A does not
replace or renumber any earlier checkpoint.

**Checkpoint 4 established 2026-09-17** at `f56d7df`, after PR 4B was merged and verified. 4A remains
recorded as the intermediate deterministic checkpoint.

### Checkpoint 4 — verification record (final Week 4)

**Phase:** Week 4 — Eligibility Intelligence
**Commit on `main`:** `f56d7df` — the PR #11 merge commit, parents `d739783` (previous `main`,
the Checkpoint 4A record) and `9e3007a` (PR 4B branch head). Real merge; the six PR 4B commits
are preserved.
**Merged by:** `Lakshya172` on GitHub at 2026-09-17T11:03:02Z, after the PR 4B audit was approved and
before the post-merge gate began. The gate confirmed the merged tree is identical to the reviewed
head `9e3007a` and verified that state rather than re-merging.

**Week 4 capability at this checkpoint:** deterministic eligibility engine · typed
`min_degree_level` · five-state verdict · deterministic hard-failure authority · AI-assisted
ambiguous field relatedness · provider abstraction with a Gemini implementation · conservative
mock provider · AI fail-closed behaviour · request-scoped AI de-duplication · AI privacy boundary
· no candidate or evaluation persistence · `POST /api/v1/eligibility/check`.

| Check | Result |
|---|---|
| PR #11 merged on GitHub | `merged: true`, `merge_commit_sha` = `f56d7dfabeeb8a7addac693d2c7552b0c1fc4e76` |
| Tree on `main` vs reviewed PR head `9e3007a` | **Identical** |
| Scope | 20 files, 6 commits: AI contract, mock, Gemini, AI stage, router wiring, tests, docs. No migration, model, adapter, dependency or CI change. |
| Working tree / `origin/main` | Clean; local `main` = `origin/main` = `f56d7df` |
| Full suite from `main` | **615 passed**, 0 skipped, offline (no `ELIGICORE_*`, proxies to a dead port) |
| Regression groups | Weeks 1–3 **328**; PR 4A deterministic **196** |
| CI on `f56d7df` | `test` completed, conclusion `success` |
| Mutation testing from `main` | **27/27 caught** — 13 deterministic-engine + 14 AI-boundary |
| Migration chain | `<base>` → `54a85d64881e` → `7c2f1a9b4d30` → `b3e8d2c61a47` (head); no PR 4B migration; all three files byte-identical to the checkpoints that introduced them |
| Upgrade / downgrade→base / re-upgrade / `alembic check` | ✅ clean; existing row preserved across up/down/up |
| Constraints | `min_degree_level='PHD'`, `status='NOT_A_STATE'`, `job_type='PART_TIME'` rejected |
| Tables / registered models | Exactly `jobs`, `ingestion_state` (+ `alembic_version`); no candidate, evaluation, application, AI-result, prompt or cache table; `is_active` not a column |
| **Post-merge AI-boundary checks** | **61/61** independent checks match the approved contract: hard FAIL (CGPA, year, backlogs, degree) → `NOT_ELIGIBLE` with 0 AI calls, 0 provider builds, no AI input; exact match and missing field → 0 calls; empty `allowed_fields` omitted, 0 calls, no build; RELATED → AI PASS, `LIKELY_ELIGIBLE`; NOT_RELATED → FAIL, `NEEDS_REVIEW` (never `NOT_ELIGIBLE`); invalid, error, LOW, UNCERTAIN, default mock, no provider → `UNKNOWN` with no error text exposed; identical questions → 1 call, no cross-request cache |
| **AI privacy (captured Gemini request)** | Only the prompt file plus `{candidate_field_of_study, allowed_fields}`; no candidate id, name, email, phone, resume, CGPA, degree, degree level, graduation year, backlogs, institution, skills, job id, description, company, notes or role; key not in body |
| **Logs** | No prompt, AI reason, AI result value, AI inputs, candidate values, provider/config error text or key; only metadata and counts |
| **Live API (uvicorn, Gemini to a dead port)** | HTTP 200; ambiguous job → `AI_ASSESSMENT_UNAVAILABLE`, `NEEDS_REVIEW`; 50 ids 200, 51 and 0 → 422; 422 does not echo; `GET` → 405; only `POST /api/v1/eligibility/check` (no AI route, no `/jobs/ingest`); 14 log markers, 0 hits; database dump identical |
| Final gate | No secrets, PII, resume files or local databases tracked; no frontend, auto-submit, browser automation, CAPTCHA/OTP bypass or Week 5 code |

**Gates:** QG-001 PASS · QG-002 PASS (item 4 evidenced by literal zero-call tests) · QG-003 PASS ·
QG-004 PASS · QG-005 PASS · QG-006 N/A (no schema change in PR 4B; chain re-verified) · QG-007 N/A
(deployment) · QG-008 N/A.

**Known limitations:**
- **Gemini's live relatedness call remains unverified** — exercised only through `httpx.MockTransport`;
  the model identifier is still unconfirmed against the live service (ADR-013 § Unverified).
- PostgreSQL has not been verified; migrations have run on SQLite only.
- With the default mock provider, ambiguous fields stay `UNKNOWN` (`AI_ASSESSMENT_INCONCLUSIVE`).
- AI relatedness is an interpretation: labelled `ai_reasoning`, capped at MEDIUM, never `ELIGIBLE`
  or `NOT_ELIGIBLE`. Prompt injection is mitigated (JSON data block, constrained schema), not eliminated.
- At `f56d7df` the OpenAPI "Current status" text in `app/main.py` still described the AI stage as
  not yet implemented. Corrected by the docs-only Checkpoint 4 record PR (description string only;
  no route, schema, handler, dependency or behaviour change).
- Five synthetic curated jobs; multi-entry profiles with unset levels resolve per-qualification
  requirements to `UNKNOWN` (ADR-018).

### Checkpoint 4A — verification record (intermediate)

**Phase:** Week 4, PR 4A — Deterministic Eligibility Engine
**Commit on `main`:** `4a5cb84` — the PR #9 merge commit, parents `151dbf8` (previous `main`)
and `924efcb` (branch head). Real merge; the six PR 4A commits are preserved.
**Merged by:** `Lakshya172` on GitHub at 2026-09-17T10:02:49Z, after external architecture review,
before the post-merge gate began. The gate confirmed the merged tree is identical to the reviewed
branch head and verified that state rather than re-merging.

| Check | Result |
|---|---|
| PR #9 merged on GitHub | `merged: true`, `merge_commit_sha` = `4a5cb844d1aa4ca4aa3e0906481d0d91c8fc67d4` |
| Tree on `main` vs reviewed PR head `924efcb` | **Identical** (`git diff` empty) |
| Scope | 26 files, 6 commits, all approved PR 4A work. No change to `app/ai`, adapters, resume parsing, candidate router, dependencies or CI. |
| Working tree on `main` | Clean, in sync with `origin/main` |
| Full suite from `main` | **524 passed**, 0 skipped, offline (no `ELIGICORE_*`, proxies to a dead port) |
| Weeks 1–3 regression | **328 passed**; regression test files unmodified since `151dbf8` |
| CI on `4a5cb84` | `test` completed, conclusion `success` (run `35208405213`) |
| **Migration chain** | `<base>` → `54a85d64881e` → `7c2f1a9b4d30` → `b3e8d2c61a47` (head) |
| Merged migrations unchanged | `54a85d64881e`, `7c2f1a9b4d30` byte-identical to Checkpoint 3 (sha256) |
| Fresh upgrade / downgrade→base / re-upgrade / `alembic check` | ✅ all clean; `alembic_version` only after base |
| Upgrade over existing data | Rows at `7c2f1a9b4d30` preserved; `min_degree_level` NULL; downgrade and re-upgrade preserve rows |
| `min_degree_level` | Nullable `VARCHAR(20)`; all 7 `DegreeLevel` members + NULL accepted; `PHD` and `bachelors` rejected by CHECK `degreelevel` |
| Existing constraints | `status='NOT_A_STATE'` and `job_type='PART_TIME'` still rejected |
| `is_active` a DB column | **No** — derived (ADR-014) |
| Personal-data tables | **None.** Tables: `jobs`, `ingestion_state` (+ `alembic_version`) |
| **Deterministic rules** | 50/50 independent rule checks match the approved contract (CGPA, graduation year, backlogs, degree level, fields, qualification selection, verdicts) |
| Mutation re-run on `main` | 13/13 deliberate breakages caught |
| **API (live uvicorn)** | 1–50 ids (0 and 51 → 422); duplicates removed in first-seen order; unknown ids in `not_found_job_ids`; CLOSED job evaluated; invalid bodies → 422 with no echo; `GET` → 405; only `POST /api/v1/eligibility/check`; no `/jobs/ingest` |
| Response | No profile, no `match_score`/score/rank; only explanatory `candidate_value`s |
| **Privacy (live)** | 11 planted markers, 0 hits in a DEBUG server log; database dump byte-identical before and after all requests; log line carries counts and timing only |
| Performance | 50-job engine check: mean 0.87 ms, p95 0.85 ms over 500 runs; one `IN` query |

**Supported requirements:** `MIN_CGPA` (same scale only) · `GRAD_YEAR_WINDOW` (inclusive) ·
`MAX_BACKLOGS` · `MIN_DEGREE_LEVEL` · `ALLOWED_FIELDS` (exact normalized match; never FAIL).

**Verdict semantics (ADR-017):** zero structured requirements → `ELIGIBLE` · deterministic FAIL →
`NOT_ELIGIBLE` · all UNKNOWN → `UNKNOWN` · any UNKNOWN or AI FAIL → `NEEDS_REVIEW` · all PASS with
AI → `LIKELY_ELIGIBLE` · all PASS deterministically → `ELIGIBLE`. No AI exists at this checkpoint,
so `LIKELY_ELIGIBLE` is unreachable in practice and AI composition is covered only by hand-built
entries in unit tests.

**Gates:** QG-001 PASS · QG-002 PASS for the deterministic scope, **item 4 (mock provider
call-count assertion) deferred to PR 4B** — no AI call path exists to count; the structural
equivalent is tested · QG-004 PASS · QG-005 PASS · QG-006 PASS (SQLite) · QG-003 N/A · QG-007 N/A.

**Known limitations:** no AI stage (non-exact fields stay `UNKNOWN`); multi-entry profiles with
unset levels resolve per-qualification requirements to `UNKNOWN`; free-text notes disclosed, not
evaluated; migrations verified on SQLite only; 5 synthetic curated jobs.

**PR 4B has not started. Checkpoint 4 is not established.**

### Checkpoint 3 — verification record

**Phase:** Week 3 — Job Schema + Adapters + Ingestion
**Produced by two merges, not one:**

| PR | Merge SHA | Contents |
|---|---|---|
| **#6** | `f538015` | Week 3 implementation. Merged externally during final verification. |
| **#7** | `2cfd4f0` | Verification repairs found *after* #6 merged. **The checkpoint is here**, not at `f538015`. |

`f538015` is deliberately **not** a checkpoint: at that commit the database accepted
`status='NOT_A_STATE'`, so ADR-014's four states were a convention rather than a guarantee,
and the failed-ingestion path was untested. Recording it would have marked a state we had
already found defects in.

Verified before being declared stable:

| Check | Result |
|---|---|
| PR #7 merged on GitHub | `merged: true`, `merge_commit_sha` = `main` HEAD |
| Merge shape | Two parents (`f538015`, `314beea`). Real merge; history preserved. |
| Working tree on `main` | Clean, in sync with `origin/main` |
| Full suite from `main` | **328 passed** |
| Weeks 1–2 regression | **203 passed**, unchanged |
| CI on `2cfd4f0` | `test` completed, conclusion `success` |
| **Migration chain** | `<base>` → `54a85d64881e` → `7c2f1a9b4d30` (head) |
| `54a85d64881e` unchanged since merge | **Yes — byte-identical.** A shipped migration must never be amended. |
| Upgrade / downgrade→base / re-upgrade | ✅ all clean |
| `alembic check` | No new upgrade operations detected |
| **Enum CHECK constraints** | `status IN ('ACTIVE','EXPIRED','CLOSED','UNKNOWN')`, `job_type IN (...)`, `last_status IN (...)` |
| Invalid status rejected | `IntegrityError` on `status='NOT_A_STATE'` |
| All four states accepted | ACTIVE/EXPIRED/CLOSED/UNKNOWN, `is_active` derived correctly for each |
| `is_active` a DB column | **No** — derived, per ADR-014 |
| Personal-data tables | **None**. Server tables: `jobs`, `ingestion_state`. |
| Ingestion — new / unchanged / changed / duplicate / disappeared | ✅ all five verified against a real database |
| **Failed ingestion** | 0 jobs deactivated, catalogue byte-identical, state `FAILED`, `last_success_at` preserved |
| **Empty successful authoritative fetch** | 5 deactivated → `CLOSED`, rows retained, state `SUCCESS` — correctly distinct from a failure |
| `ingestion_state` rows | 1 per source; no run log; no hash ledger |
| API | `GET /jobs`, `GET /jobs/{id}`; filters exactly `is_active, job_type, source, limit, offset`; `POST /jobs/ingest` absent by design |
| Normalized schema, not raw payload | ✅ no `raw`/`payload`/`source_data` field |
| Privacy | No candidate/eligibility/match/profile/resume/email string in any response; server log clean |

**Known limitations carried into this checkpoint** — see `context/state.md` § Partial for the
full list. Chiefly: no PostgreSQL run (QG-007); `batch_alter_table` verified on SQLite only;
CHECK constraints are not autogenerate-detected, so a future enum member needs a hand-written
migration; `EXPIRED` and `UNKNOWN` are modelled but unset by any code path; and
`POST /api/v1/jobs/ingest` remains deferred.

**Week 4 had not started at this checkpoint.**

### Checkpoint 2 — verification record

Merged 2026-09-10 by PR #4. Declared stable only after every check below:

| Check | Result |
|---|---|
| PR #4 merged on GitHub | `merged: true`, `merged_by: Lakshya172` |
| `merge_commit_sha` vs `main` HEAD | `91dd31d50e7749ad37acf14babd5d1ee90141abd` — identical |
| Merge commit shape | Two parents — `9409f50` and `b770d90`. Real merge, not squashed; the 16 Week 2 commits are preserved. |
| Working tree on `main` | Clean, in sync with `origin/main` |
| Full suite from `main` | **203 passed** |
| Week 1 regression in isolation | **86 passed**, unchanged |
| CI on the merged commit | `test` completed, conclusion `success` |
| `Base.metadata.tables` | `[]` — no personal-data table registered (INV-1) |
| Database tables | `alembic_version` only (Alembic's own revision pointer) |
| `alembic check` | No new upgrade operations detected |
| Default AI provider | `mock` — an unconfigured checkout cannot make a paid call |
| Secrets / PII | No `.env`, no credential patterns, no `.pdf`/`.docx`/`.db` committed |
| Week 3 scope | Absent — no adapters, models, migrations, eligibility or matching |

**Known limitation carried into this checkpoint:** the Gemini Flash provider has **not** been
exercised against the live Gemini API. No key is configured and the suite is required to run
without one. The provider contract is covered through a mocked httpx transport; a live smoke
test remains pending, and the default model identifier should be confirmed before first real
provider use. **This checkpoint is a verified stable development state, not a production-ready
system.**

### Checkpoint 1 — verification record

Verified before being declared stable:

| Check | Result |
|---|---|
| PR #2 merged on GitHub | `merged: true`, `merge_commit_sha` matches `main` HEAD |
| Merge commit shape | Two parents — `e8c68b7` (Checkpoint 0) and `6814dad` (branch HEAD). Real merge, not squashed; implementation history preserved. |
| Working tree on `main` | Clean, up to date with `origin/main` |
| Full suite from `main` | 86 passed |
| CI on the merged commit | `test` completed, conclusion `success` |
| `Base.metadata.tables` | `[]` — no personal-data table registered (INV-1) |
| `alembic check` | No new upgrade operations detected |

Notes that remove the ambiguities this registry exists to close:

- **Checkpoint 0 is the commit `e8c68b7`, not a range.** Phase 0 was built over two commits; the
  checkpoint is the state of `main` at the end of it. `7f7abbb` is an intermediate commit, not a
  checkpoint of its own. There is exactly one Phase 0 checkpoint.
- **Checkpoint 0 has no CI or test result** because Phase 0 contained no product code and CI was
  introduced in Week 1. Recording "n/a" is accurate; recording "passing" would not be.
- **A checkpoint is only declared stable after the merged `main` state has been verified** —
  merge confirmed on GitHub, working tree clean, full suite run from `main`, and CI green on the
  merged commit. Until then it reads *pending*, and its commit column stays empty rather than
  carrying a guess.

---

## Recovery and rollback

`main` must always be recoverable to a checkpoint in this registry.

### Current recovery targets

| Priority | Checkpoint | Commit | Role |
|---|---|---|---|
| **1st** | Checkpoint 4 — Week 4 Eligibility Intelligence | `f56d7df` | **Current stable point.** If Week 5 introduces a regression, this is the immediate rollback reference. |
| **2nd** | Checkpoint 4A — Week 4 deterministic engine | `4a5cb84` | Deterministic eligibility without the AI stage. Reached by reverting the PR #11 merge; no database step. |
| **3rd** | Checkpoint 3 — Week 3 | `2cfd4f0` | Last state before any eligibility code. |
| **4th** | Checkpoint 2 — Week 2 | `91dd31d` | Known-good state before the job catalogue. |
| **5th** | Checkpoint 1 — Week 1 | `2e79454` | Remains available indefinitely as a historical recovery point. |
| **6th** | Checkpoint 0 — Phase 0 | `e8c68b7` | Engineering layer only, no product code. |

**Recovering from Checkpoint 4A to Checkpoint 3 requires `alembic downgrade 7c2f1a9b4d30`**,
which drops only `jobs.min_degree_level` (verified with existing rows preserved and the existing
CHECK constraints intact).

**Recovering past Checkpoint 3 requires a database step.** Checkpoints 0–2 predate any table,
so reverting to them is code-only. Checkpoint 3 introduced the schema, so a rollback below it
also needs `alembic downgrade base`. No personal data is at risk either way — the catalogue is
public job postings.

Checkpoint 1 is **not** superseded by Checkpoint 2 — it stays recoverable. A regression whose
cause turns out to predate Week 2 needs a target older than the newest checkpoint, and deleting
history to tidy the registry would remove exactly the option you would want.

Do not confuse `ea383c4`/`9409f50` (PR #3, the documentation-only checkpoint record) with
Checkpoint 1 itself. Checkpoint 1 is the Week 1 *implementation* merge, `2e79454`.

If a future phase introduces a regression:

1. **Identify the regression** — what broke, and which commit introduced it.
2. **Identify the last known stable checkpoint** from the registry above.
3. **Investigate the cause.** A revert without a diagnosis usually means reverting again later.
4. **Propose a recovery strategy** — normally `git revert` of the offending merge commit.
5. **Wait for explicit human approval.** Recovery is never automatic.
6. **Perform the approved recovery**, producing a visible revert commit.

Hard rules:

- **Never rewrite `main` history.** No rebase, no amend, no force-push to `main`.
- **Never use `git reset --hard` as a production recovery mechanism.** It discards work silently
  and leaves no record that anything happened.
- **Never roll back automatically.** Detecting a regression means reporting it, not acting on it.

Recovery should be visible in the history, not hidden from it. A revert commit tells the next
reader that something went wrong and was addressed; a rewritten history tells them nothing.

---

## Session start and end

**Start:** read `context/state.md`, `context/vision.md`, `context/workflow.md`,
`context/memory.md`. Then load conditionally per the table in `AGENTOS.md`.

**End:** update `context/state.md` honestly. A state file that overstates progress is worse
than no state file, because the next session will build on a false premise.
