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
| **4** | Week 4 — Eligibility Intelligence (final: PR 4A + PR 4B) | `f56d7df` | PR #9 (`4a5cb84`) + PR #11 (`feature/week-4-eligibility-ai`), merged 2026-09-17 | ✅ `test` success on `f56d7df` | 615 passed | **Stable** |
| **5A** | Week 5 — Deterministic Matching Engine (PR 5A) · **intermediate** | `05534af` | PR #13 (`feature/week-5-matching-engine`), merged 2026-09-17 | ✅ `test` success on `05534af` | 736 passed | **Stable** |
| **5** | Week 5 — Matching Engine (final: PR 5A + PR 5B) | `0aaaa1d` | PR #13 (`05534af`) + PR #15 (`feature/week-5-recommendations`), merged 2026-09-19 | ✅ `test` success on `0aaaa1d` | 850 passed | **Stable** |
| **6A** | Week 6 — Excel Export (PR 6A) · **intermediate** | `0125703` | PR #17 (`feature/week-6-excel-export`), merged 2026-09-19 | ✅ `test` success on `0125703` | 1075 passed | **Stable** |
| **6** | Week 6 — MVP (final: PR 6A + PR 6B) | `13eb832` | PR #17 (`0125703`) + PR #19 (`feature/week-6-polish`), merged 2026-09-20 | ✅ `test` success on `13eb832` | 1133 passed | **Stable** |
| **7** | Week 7 — Application Preparation (final: Slice 7A + Slice 7B) | `6c269a0` | PR #24 (`365e7a4`, Slice 7A) + PR #28 (`feature/week-7-application-prep`), merged 2026-09-22 | ✅ `test` success on `6c269a0` | 1358 passed | **Stable** |
| **8** | Week 8 — Refinement, Caching and Cost Logging (final: Slice 8A + Slice 8B + Slice 8C) | `9aba1f2` | PR #34 (`e5d6d36`, Slice 8A) + PR #35 (`f3fbf35`, Slice 8B) + PR #36 (`feature/week-8-operational-logs`), merged 2026-09-24 | ✅ `test` success on `9aba1f2` | 1549 passed | **Stable — current** |

**Checkpoint 1 full SHA:** `2e79454f787019ff29af39fcfd285aee59c8bc77`
**Checkpoint 2 full SHA:** `91dd31d50e7749ad37acf14babd5d1ee90141abd`
**Checkpoint 3 full SHA:** `2cfd4f0276b60de393ec604afc10b3c52f483ca7`
**Checkpoint 4A full SHA:** `4a5cb844d1aa4ca4aa3e0906481d0d91c8fc67d4`
**Checkpoint 4 full SHA:** `f56d7dfabeeb8a7addac693d2c7552b0c1fc4e76`
**Checkpoint 5A full SHA:** `05534affced482f6bc5e188ac465144dd425f9a7`
**Checkpoint 5 full SHA:** `0aaaa1da6fe643b8164df645113322adc889075d`
**Checkpoint 6A full SHA:** `0125703ad9464216b1622c14941664ec32ac9bac`
**Checkpoint 6 full SHA:** `13eb8325149cab60a039534631265803250b767a`
**Checkpoint 7 full SHA:** `6c269a05ec1a4fdbdc7820d0c6b0b40980ba8fb3`
**Checkpoint 8 full SHA:** `9aba1f2b1007b0931ec9adc39afb88b15eaa2c14`

**Checkpoint 4A is intermediate, not Checkpoint 4.** Week 4 is delivered in two PRs. 4A marks the
verified deterministic engine; **Checkpoint 4 is reserved for Week 4 as a whole** and is
established only after PR 4B (the AI field-relatedness stage) is merged and verified. 4A does not
replace or renumber any earlier checkpoint.

**Checkpoint 4 established 2026-09-17** at `f56d7df`, after PR 4B was merged and verified. 4A remains
recorded as the intermediate deterministic checkpoint.

**Checkpoint 5A is intermediate, not Checkpoint 5.** Week 5 is delivered in two PRs. 5A marks the
verified deterministic matching engine (service only); **Checkpoint 5 is reserved for Week 5 as a
whole** and is established only after PR 5B (recommendations) is merged and verified.

**Checkpoint 5 established 2026-09-19** at `0aaaa1d`, after PR 5B was merged and verified. 5A
remains recorded as the intermediate matching-engine checkpoint.

**Checkpoint 6A is intermediate, not Checkpoint 6.** Week 6 is delivered in two PRs. 6A marks the
verified Excel tracker export; **Checkpoint 6 is reserved for the final Week 6 MVP** and is
established only after PR 6B (polish, catalogue, demo command, full-flow test) is merged and
verified. A checkpoint is not a release, version or tag (C-28). Checkpoint 5 remains the final
Week 5 checkpoint.

**Checkpoint 6 established 2026-09-20** at `13eb832`, after PR 6B was merged and verified. 6A
remains recorded as the intermediate Excel-export checkpoint. **This is the dossier's declared
safe stopping point (§15): the Phase 1 product is complete and demoable.** It is still a
checkpoint — no release, version or tag was created.

**Week 7 has no intermediate checkpoint.** Week 6 and every week before it were recorded with an
intermediate checkpoint plus a final one. Week 7 is not: Slice 7A (the deterministic truthfulness
validator, PR #24) was merged and verified post-merge but deliberately recorded **no checkpoint**,
because a validator with no caller is not a state worth rolling back to. There is therefore no
Checkpoint 7A, and **Checkpoint 7 covers Week 7 as a whole** — both slices.

**Checkpoint 7 established 2026-09-22** at `6c269a0`, after Slice 7B (PR #28) was merged and
verified. It is a checkpoint, not a release, version or tag (C-28). **Checkpoint 6 (`13eb832`)
remains the dossier's declared safe stopping point (§15)** and stays recorded as the final Week 6
checkpoint; Week 7 is the first enhancement week on top of it.

**Week 8 has no intermediate checkpoint either.** It is delivered in three slices — 8A, 8B and 8C
— and **none of them recorded a checkpoint of its own**. There is no Checkpoint 8A, 8B or 8C, and
**Checkpoint 8 covers Week 8 as a whole**. Each slice is behaviour-preserving (ADR-026 D1), so the
intermediate states differ from one another only in internal instrumentation and are not distinct
rollback destinations.

**Checkpoint 8 established 2026-09-24** at `9aba1f2`, after Slice 8C (PR #36) was merged and
verified. It is a checkpoint, not a release, version or tag (C-28). **Checkpoint 6 (`13eb832`)
remains the dossier's declared safe stopping point (§15)**; Checkpoint 7 remains the final Week 7
record and is now historical rather than current.

### Checkpoint 8 — verification record (final Week 8)

**Checkpoint:** Checkpoint 8 — Week 8 Refinement, Caching and Cost Logging (final: Slice 8A +
Slice 8B + Slice 8C)
**Phase:** Week 8 — Refinement, caching and cost logging (ADR-026)
**Commit on `main`:** `9aba1f2` — the PR #36 merge commit, parents `f3fbf35` (previous `main`, the
Slice 8B merge) and `db16c1e` (PR #36 branch head). Real merge; the three PR #36 commits are
preserved.
**Merged by:** `Lakshya172` on GitHub at 2026-09-24T04:21:22Z, after a pre-merge audit. The
post-merge gate confirmed the merged tree is **identical** to the reviewed head `db16c1e`.

**Git history of Week 8:**

| Step | Merge on `main` |
|---|---|
| Week 8 design gate — ADR-026 (PR #32) | `ca338f2ea51540ba3f00e9c9cb5e783d1526039b` |
| ADR-020 §5 partial-supersession record (PR #33) | `dc0a759ef21a811ac750587c93f85b88eaa65768` |
| Slice 8A implementation (PR #34) — **no checkpoint** | `e5d6d36bdd3c4f5a05bdb1dcf6425f87cab2ff98` |
| Slice 8B implementation (PR #35) — **no checkpoint** | `f3fbf3506365e8df238747866014c03fb1398d84` |
| Slice 8C implementation (PR #36) — **Checkpoint 8** | `9aba1f2b1007b0931ec9adc39afb88b15eaa2c14` |

Week 8's own recovery-target documentation fix (PR #31, `62fb2f2`) and the Checkpoint 7 record
(PR #30, `7d683d9`) landed before the design gate and belong to the Week 7 close-out.

**Week 8 capability at this checkpoint.**

*8A — cost and usage accounting* (`app/ai/usage.py`, ADR-026 D2–D6, D9): `extract_resume` and
`assess_field_relatedness` now log token usage and a derived cost alongside the existing operation
record. Usage travels on a **per-call sink** the provider may write to — no abstract method was
added, no provider return type changed, and a provider that reports nothing remains valid and logs
`unknown` (D3). One sink per call means `eligibility_ai`'s `asyncio.gather` fan-out cannot
mis-attribute cost between concurrent assessments. **Retried calls accumulate** (D4): a Gemini call
that fails twice and succeeds on the third consumed tokens three times, and the usage on a
retryable error body is read before the error is translated. Pricing is `ELIGICORE_` configuration
with an **empty default** — no external provider price is hard-coded (D5) — and cost is held in
integer micro-units so no float drift enters an accounting figure. Prompt, completion and total
tokens degrade **independently** to `unknown`, and accounting is wrapped so that it can never
change an AI outcome (D6).

*8B — candidate-free corpus vectorizer cache* (`app/services/matching_engine.py`, ADR-026 D7): the
fitted vectorizer, the job matrix, the feature names and the catalogue row mapping are cached in a
**process-local, bounded, in-memory LRU of capacity 4**, keyed by the existing `corpus_fingerprint`
— an exact determinant of the fit, not a heuristic. **The candidate is never cached**:
`vectorizer.transform(candidate_terms(...))` stays per-request, every time. No Redis, no disk, no
external cache service, no new dependency and **no cache configuration key** — the bound is a
module constant. Output is identical cold, warm and after invalidation.

*8C — operational-log completeness* (`app/main.py`, ADR-026 D10): the audit found **exactly one**
production gap and closed it in eight lines. Starlette's `ServerErrorMiddleware` sits outside the
request middleware, so an unhandled exception travelled back through `call_next` and the request
record never ran — the request count was systematically blind to precisely the requests an
operator most needs to see. A request that ends in an unhandled exception now emits its request
record before the exception propagates. Nothing about the exception is logged there: its type is
the error record's business, and its message can carry candidate data. Every other §10.2 category
was already satisfied and is re-evidenced rather than redesigned.

**Architecture at this checkpoint.** Unchanged in direction: `router → service → existing domain
engines`, with the provider reached only through `AIService` and the ADR-004 abstraction (INV-5).
Week 8 added no endpoint, route, schema, contract, model, table, migration or dependency, and no
response body changed. `generate_application_content` is untouched.

**Algorithmic state preserved.** Eligibility keeps deterministic final authority (ADR-017,
ADR-019). Matching keeps deterministic skill normalization, TF-IDF and cosine similarity, and
ADR-020's rule that the candidate is transformed and never fitted is preserved exactly — Slice 8B
caches only the fit (ADR-020 §5 is superseded in part by ADR-026, recorded explicitly in PR #33).
Recommendations, export and preparation are byte-identical in behaviour.

| Check | Result |
|---|---|
| PR #36 merged on GitHub | `merged: true`, `merge_commit_sha` = `9aba1f2b1007b0931ec9adc39afb88b15eaa2c14` |
| Tree on `main` vs reviewed PR head `db16c1e` | **Identical** |
| Scope of Week 8 | 22 files across three implementation PRs and two documentation PRs: `app/ai/usage.py` (new), `app/config.py`, the provider base/Gemini/mock, `AIService`, `app/services/matching_engine.py`, `app/main.py`, four new test files, two re-aimed merged test files, ADR-026 (new), the ADR-020 amendment note and current-state documentation. **No `alembic/`, no `requirements.txt`, no schema, no router and no new endpoint** |
| Working tree / `origin/main` | Clean; local `main` = `origin/main` = `9aba1f2` |
| Full suite from `main` | **1549 total — 1549 passed, 0 failed, 0 skipped**, offline with no credentials |
| Regression | Up from 1358 at Checkpoint 7 (**+191**); no merged test was weakened, and the two re-aimed files were strengthened when the provider signature grew a keyword-only `usage` parameter |
| CI | `test` success on `e5d6d36` (8A), `f3fbf35` (8B) and `9aba1f2` (8C) |
| Mutation testing from `main` | **230/230 caught** — 8C **32/32** · 8B **34/34** · 8A **68/68** · 7B **54/54** · 7A **42/42**. Re-run in one guarded harness from a verified-clean tree on the project interpreter, with the tree and every mutated source's blob checked before and after each mutant; all eleven target files restored byte-identical; no scratch tooling committed or left untracked |
| API surface | Exactly **10 routes**, unchanged from Checkpoint 7; OpenAPI contract unchanged; `/api/v1/matching/score` and `/api/v1/jobs/ingest` still absent |
| Migration chain | Unchanged — three migrations, head `b3e8d2c61a47`; **no Week 8 migration**; models unchanged |
| Tables | Exactly `jobs`, `ingestion_state` (+ `alembic_version`); **no cost, usage, ledger, candidate, application, evaluation or package table** |
| Persistence | None added. Cost and usage are operational log records only (D9) |
| Caching | Exactly one cache exists: the Slice 8B corpus artifact cache. Catalogue-derived only, bounded at 4, in-memory and process-local, keyed by `corpus_fingerprint`; **no candidate-derived cache, no generated-prose cache, no résumé-content retention** |
| Privacy | No `candidate_id` in any cost or usage record; no PII in any log line; the generation path emits no token, length or cost field |
| Dependencies | `requirements.txt` untouched across all three slices |

**Gates:** QG-001 PASS · QG-003 PASS (AI change: usage accounting on two operations) · QG-005 PASS
(privacy and personal data) · QG-002 N/A (no eligibility change) · QG-004 N/A — **proved**, not
assumed: the OpenAPI document is byte-identical to Checkpoint 7 and the route count is unchanged ·
QG-006 N/A — **proved** by `alembic check` ("No new upgrade operations detected") · QG-007 N/A (no
deployment) · QG-008 N/A (no resume-processing change).

**Reviewers:** ai, security, qa, architect, performance, documentation PASS — the AI-provider,
personal-data and performance-path triggers. api was not triggered beyond the unchanged-contract
proof; release was not triggered (nothing deployed or tagged).

**Cost-coverage limitation — explicit.** **Week 8's cost and usage accounting deliberately does
not cover `generate_application_content`.** Two AI operations are instrumented —
`extract_resume` and `assess_field_relatedness` — and the generation path is excluded
**structurally**: no usage sink is threaded through that call, and there is no setting that could
enable it, because a setting would be a latent violation waiting for a future default change
(ADR-026 D8, W8-F). ADR-025's merged generation-logging rule stands verbatim and unamended: a token
count is a length that could characterize one candidate's content. **Week 8 therefore must not be
described as having complete AI cost coverage.** That coverage becomes material only when live
application generation is separately approved, and it will need its own explicit privacy decision
at that point — it is not implied by, and cannot be inherited from, ADR-026.

**Live Gemini remains deferred.** No live-generation implementation was added in Week 8. The Gemini
`generate_application_content` method is still a stub that raises `AIProviderUnavailableError` and
holds no transport, prompt load or key; application generation still runs on the mandatory mock
provider only. The existing provider paths are as previously designed, and **no claim of live
generation is made anywhere** in the codebase or the documentation. Gemini's live calls and model
identifier remain unverified.

**Known limitations:**
- **AI cost coverage excludes the generation path**, by structural design — see above.
- **No benchmarked numeric speed-up is claimed for the corpus cache.** Slice 8B is an
  output-identical optimization verified for equivalence cold, warm and after invalidation; it was
  not benchmarked, and no latency or throughput figure is recorded for it.
- **The cache holds at most four fitted catalogues per process** and is process-local, so a
  fifth distinct catalogue evicts the least recently used one, and nothing is shared between
  worker processes. This is the intended bound, not a defect.
- **Cost is `unknown` unless a rate is configured.** The default rate table is empty by design (D5),
  so a deployment that configures no rates logs tokens and `cost=unknown`. No external provider
  price is hard-coded anywhere.
- **The Slice 8C fix depends on the middleware ordering that caused the gap.** If FastAPI ever
  moves `ServerErrorMiddleware` inside user middleware, the `except` branch becomes dead rather
  than wrong — and the tests would still pass. A latent staleness, not a correctness risk.
- **The OpenAPI "Current status" text still reads "Weeks 1–6 of a 10-week build are complete."**
  Two merged tests pin that sentence, so correcting it touches `app/main.py` and both tests and is
  out of scope for a documentation-only checkpoint record — the same handling C-32 received at
  Checkpoint 6 and Checkpoint 7.
- Carried forward: Gemini's live calls and model identifier are unverified, and the migration chain
  has never run against PostgreSQL (both Week 9).

**Deferred, explicitly:** live Gemini application generation · generation-path token, length or
cost logging · a cost table, ledger or metrics endpoint · any candidate-keyed cost record · spaCy
deterministic fallback extraction · résumé extraction-accuracy measurement · recommendation or
matching algorithm tuning · a persistent, shared or distributed cache · `/api/v1/matching/score` ·
`/api/v1/jobs/ingest` · application tracking/status endpoints · submission, autofill and browser
automation · authentication · rate limiting · frontend · deployment. No stub routes exist.

**Week 9 has not started.** No Week 9 branch, no deployment work, no documentation-and-deployment
implementation, and no Checkpoint 9.

### Checkpoint 7 — verification record (final Week 7)

**Checkpoint:** Checkpoint 7 — Week 7 Application Preparation (final: Slice 7A + Slice 7B)
**Phase:** Week 7 — Application preparation and truthfulness validation (ADR-025)
**Commit on `main`:** `6c269a0` — the PR #28 merge commit, parents `234dabf` (previous `main`, the
PR #29 ADR-025 correction) and `37275e5` (PR #28 branch head). Real merge; the eight PR #28
commits are preserved.
**Merged by:** `Lakshya172` on GitHub at 2026-09-22T12:39:36Z, after an independent 21-section
pre-merge audit that returned APPROVED TO MERGE. The post-merge gate confirmed the merged tree is
identical to the reviewed head `37275e5` in all fifteen changed files; the one further difference,
`artifacts/decisions/ADR-025-week-7-application-preparation.md`, is the PR #29 correction that
`main` gained after PR #28 branched, and is expected.

**Git history of Week 7:**

| Step | Merge on `main` |
|---|---|
| Week 7 design gate — ADR-025 (PR #23) | `c20577093b97b89469f585ac3e6b020ab0ba03c7` |
| ADR-025 evidence-boundary correction (PR #25) | `5e906361db9680718cdc7dccdfac993ab9e96bcf` |
| Slice 7A implementation (PR #24) — **no checkpoint** | `365e7a46737b0a1bf59334703c2a5bdd9e8e0803` |
| Slice 7A docstring correction (PR #26) | `f5b81f0de65d28b8418b7ba0283e20a9a295cf44` |
| Current-state documentation refresh (PR #27) | `ee9207ffdc4ebb3cfe87f7301779dad637eb4abd` |
| ADR-025 answer-outcome correction (PR #29) | `234dabff42e6540c3ee96934c41a5d1190b6d8df` |
| Slice 7B implementation (PR #28) — **Checkpoint 7** | `6c269a05ec1a4fdbdc7820d0c6b0b40980ba8fb3` |

**Week 7 capability at this checkpoint.**

*7A — truthfulness validator* (`app/services/truthfulness_validator.py`, ADR-025 D3–D9):
deterministic and AI-free, with no FastAPI, database, filesystem or network dependency.
Remove-by-default — a sentence survives only if every claim in it traces to the structured profile
the caller supplied — with a structured removal list naming what was removed and why. Evidence is
the provider-visible structured profile only, **never `resume_raw_text`** (D11, D12). Unchanged by
Slice 7B: the merged blob `4a8572ed4428f0e8e658ee663c266cf5cea0eaf6` is byte-identical before and
after this merge, and its six enums and `RemovedClaim` kept every member and field.

*7B — application preparation* (`POST /api/v1/applications/prepare`, ADR-025 D1, D2, D10–D14):

- **Stateless orchestration.** `app/services/application_prep.py` reads one catalogue job by id,
  projects the request profile into an evidence object, asks the AI provider for a draft, passes
  every generated string through the 7A validator, and returns only sanitized text. Nothing is
  written: no candidate, application, evaluation or package row, no file, no cache.
- **Contract.** One `job_id`; at most five client-supplied questions with bounded ids and text;
  optional cover letter; word limits bounded at both ends; unknown fields rejected at every level.
  The response carries the sanitized cover letter, one `PreparedAnswer` per question, the full
  `removed_claims` audit list, a package `status`, a per-item confidence and an explicit
  no-submission notice. An unknown `job_id` is a 404 carrying no profile data.
- **Evidence boundary (D10–D12).** `build_evidence` is written field by field — no `model_dump`,
  no `**` unpacking, no attribute iteration — so a new profile field cannot reach a provider by
  accident. The provider sees exactly `skills`, `experience`, `projects`, `certifications` and
  `education`; `experience` carries only `title`, `duration` and `description`, `education` only
  `degree`, `level`, `field_of_study` and `grad_year`, and a certification only its `name`.
  Employer names, languages, contact details, location, institution, grades, backlog count,
  `candidate_id` and `resume_raw_text` never leave the service. Verified structurally (syntax
  tree) and at runtime (captured provider calls against fourteen marker values).
- **Failure semantics (ADR-025 § Failure semantics, as corrected by PR #29).** A provider error, an
  invalid reply shape, a duplicate or unknown answer id, or an empty draft degrades the package
  rather than failing the request. `RemovalReason.ANSWER_REQUIRES_EXCLUDED_DATA` remains defined in
  the enum and **unused by the service**; the `REQUIRES_EXCLUDED_DATA` answer outcome is derived
  only from actual validator output — an `EXCLUDED_DATA` removal that leaves nothing behind —
  never guessed from the question text.
- **Generation (D13).** The mandatory mock provider is the only implementation: deterministic,
  conservative, and injectable into fabricating, over-length and empty modes so the sanitization
  path is exercised. `app/ai/prompts/application_content.txt` records the reviewed prompt, with an
  explicit BEGIN/END convention marking every data block as data and not instruction. **Live Gemini
  generation is deferred to Week 8/9**: the Gemini method is a stub that raises
  `AIProviderUnavailableError` and holds no transport, prompt load or key.
- **No submission (INV-10, ADR-008).** The package is a draft. Nothing is sent, scheduled,
  autofilled or committed on the candidate's behalf, and the notice in every response says so.

**Architecture at this checkpoint:** `router → application_prep service → AI provider boundary →
truthfulness validator`. The router holds no business logic and the service imports no FastAPI
(INV-7); the provider is reached only through `AIService` and the ADR-004 abstraction, never a
vendor SDK (INV-5); the validator stays the final sanitization boundary, and no path returns raw
generated text. No new algorithm, no eligibility, matching, recommendation, ingestion or export
change, no new model, migration, table or dependency.

| Check | Result |
|---|---|
| PR #28 merged on GitHub | `merged: true`, `merge_commit_sha` = `6c269a05ec1a4fdbdc7820d0c6b0b40980ba8fb3` |
| Tree on `main` vs reviewed PR head `37275e5` | **Identical** in all fifteen changed files; ADR-025 differs only by the PR #29 correction `main` already carried |
| Scope | 15 files, +2828/−34: application schemas, the provider boundary, the mock generator, the Gemini stub, `AIService` logging, the prep service, the prompt file, the router, the OpenAPI description, one new test file and five re-aimed merged tests. No `artifacts/`, `context/`, `CHANGELOG.md`, `alembic/` or `requirements.txt` change |
| Working tree / `origin/main` | Clean; local `main` = `origin/main` = `6c269a0`, 0 ahead / 0 behind |
| Full suite from `main` | **1358 total — 1358 passed, 0 failed, 0 skipped**, offline |
| Regression | The 1259 tests of Slice 7A unchanged and passing; 98 new in `tests/test_application_prep.py`; Slice 7A's own 124 intact; full flow 9 passed |
| CI on `6c269a0` | `test` completed, conclusion `success` (run `106748013483`) |
| Mutation testing from `main` | Week 7B **54/54** · Week 7A **42/42**; sources restored byte-identical; neither scratch suite committed |
| API surface | Exactly **10 routes**; `POST /api/v1/applications/prepare` present once and POST-only; `/api/v1/matching/score` and `/api/v1/jobs/ingest` still absent; `/api/v1/applications/export` remains the only binary response |
| Evidence boundary (D10–D12) | Evidence fields exactly `{skills, experience, projects, certifications, education}`; `build_evidence` has zero attribute calls and zero `*`/`**` nodes in executable code; `resume_raw_text` appears only in docstrings |
| Slice 7A integrity | `truthfulness_validator.py` blob `4a8572ed4428f0e8e658ee663c266cf5cea0eaf6` identical before and after the merge; all six enums and `RemovedClaim` unchanged |
| Migration chain | Unchanged — three migrations, head `b3e8d2c61a47`; no Week 7 migration; models unchanged; fresh `upgrade head` + `alembic check` clean ("No new upgrade operations detected") |
| Tables | Exactly `jobs`, `ingestion_state` (+ `alembic_version`); no candidate, application, evaluation or package table |
| Persistence | No `session.add/commit/flush/delete` in the prep service; database file byte-identical across a live prepare request |
| Caching | None — no `lru_cache`, no `open(`, no cache identifier or literal in executable code (the word occurs once, in a docstring stating that nothing is cached) |
| Privacy | Two counts-only log lines and nothing else. Name, email, phone, location, institution, CGPA, backlog count, employer, language, résumé text, question text, generated prose, removed-claim text, project name and target company all absent from every log line; the 404 body carries no profile data |
| Dependencies | `requirements.txt` untouched; no new package |
| Performance (local, synthetic) | p95 for a five-question package with the mock provider, pinned by test — not a production capacity claim |

**Gates:** QG-001 PASS · QG-003 PASS (AI change: provider boundary, mock generation, prompt file) ·
QG-004 PASS (new endpoint and contract) · QG-005 PASS (privacy and personal data) · QG-002 N/A (no
eligibility change) · QG-006 N/A (no model or migration) · QG-007 N/A (no deployment) · QG-008 N/A
(no resume-processing change).

**Reviewers:** ai, security, qa, api, architect, documentation PASS — the `application_prep`
trigger plus the API and personal-data triggers. release was not triggered (nothing deployed or
tagged); performance was not triggered by the map (benchmark recorded above).

**Known limitations:**
- **The OpenAPI "Current status" text still reads "Weeks 1–6 of a 10-week build are complete."**
  and two merged tests pin that sentence and reject Week 7-era wording. Correcting it touches
  `app/main.py` and both tests, so it is deliberately kept out of this documentation-only record
  and tracked as the next small approved change — the same handling C-32 received at Checkpoint 6.
  The endpoint-level OpenAPI documentation for `/applications/prepare` is accurate and complete.
- **Generation runs on the mock provider only.** The package contract, the sanitization path and
  the failure semantics are fully exercised, but no draft has ever been produced by a live model.
  Live Gemini generation is Week 8/9 work, and the quality of real generated prose is unverified.
- The validator's remove-by-default rule is deliberately blunt: a true claim phrased in a way the
  validator cannot trace to the structured profile is removed rather than reworded, so a
  well-formed package can still come back thin. The removal list discloses every such case.
- Carried forward: Gemini's live calls and model identifier are unverified, and the migration
  chain has never run against PostgreSQL (both Week 9).

**Deferred, explicitly:** live Gemini application generation · caching · AI cost/token logging ·
a second AI call · AI claim extraction · résumé tailoring · PDF/DOCX rendering ·
`/api/v1/matching/score` · `/api/v1/jobs/ingest` · application tracking/status endpoints ·
submission, autofill and browser automation · authentication · frontend · deployment. No stub
routes exist.

**Week 8 has not started.** No branch, no caching or cost-logging code, no new provider behaviour,
no new endpoint, and no Checkpoint 8.

### Checkpoint 6 — verification record (final Week 6 MVP)

**Checkpoint:** Checkpoint 6 — Week 6 MVP (final)
**Phase:** Week 6 — Polish, Excel export, testing (final: PR 6A + PR 6B)
**Commit on `main`:** `13eb832` — the PR #19 merge commit, parents `fca776c` (previous `main`, the
Checkpoint 6A record) and `ed68d47` (PR 6B branch head). Real merge; the nine PR 6B commits are
preserved.
**Merged by:** `Lakshya172` on GitHub at 2026-09-20T10:03:31Z, after review and an integrity check.
The post-merge gate confirmed the merged tree is identical to the reviewed head `ed68d47`.

**Git history of Week 6:**

| Step | Merge on `main` |
|---|---|
| Week 6A implementation (PR #17) — Checkpoint 6A | `0125703ad9464216b1622c14941664ec32ac9bac` |
| Week 6A checkpoint record (PR #18) | `fca776c957093bcbd3c126c789a9e83e7b1c236b` |
| Week 6B implementation (PR #19) — **Checkpoint 6** | `13eb8325149cab60a039534631265803250b767a` |

**Week 6 capability at this checkpoint.**

*6A — Excel tracker export* (`POST /api/v1/applications/export`, ADR-023): stateless, in-memory
workbook generation from client-supplied tracker rows — at most 500 records, duplicate `job_id`
rejected, nullable `match_score` written as an empty cell, optional `Requirements` worksheet,
formula-injection protection (leading `= + - @`, tab and carriage return neutralised and every text
cell pinned to the string type, which also keeps Excel error codes literal), deterministic workbook
content, fixed non-personal metadata, fixed filename `eligicore-tracker.xlsx`. No candidate
persistence, no database write, no AI. The binary 200 is the one documented exception to the
`response_model` convention (C-23, ADR-023 §8); errors keep the standard envelope. Verified in
Microsoft Excel 16.0 at Checkpoint 6A: opened without repair, 23/23 checks.

*6B — demoability* (ADR-024):

- **Curated catalogue** — exactly 40 synthetic jobs; the original five byte-identical and still
  first; 40 unique source ids and 40 unique content hashes; fictional companies and
  `example.com` links with no real contacts; the approved diversity (14+ role families,
  internships and full-time, `SCALE_10`/`SCALE_4`/`PERCENTAGE` and a scale-less cutoff, graduation
  windows across 2025–2029 including open-ended, no-degree/`BACHELORS`/`MASTERS`,
  exact/ambiguous/unrestricted permitted fields, backlog limits 0/1/2 and unstated, representative
  skills including C++, C#, `.NET`, React.js and Node.js, and one listing with no job terms).
  **ACTIVE-only:** the curated source states no status (C-30).
- **Local seed command** — `python -m app.cli seed-catalogue`: uses `CuratedJobAdapter`, reuses
  `ingest_all`, idempotent, no reset behaviour, no arbitrary dataset input, no candidate input, no
  HTTP ingestion route, no automatic migrations, requires the Alembic head, writes only `jobs` and
  `ingestion_state`, and prints counts only.
- **Full-flow test** — résumé parse → step-3 profile completion → validation → normalization →
  eligibility → recommendations → tracker export, over real HTTP boundaries, with synthetic
  candidates, the existing mock AI, a socket guard against external connections, and the exported
  workbook reopened and checked.
- **Quickstart** — a fresh clone creates a virtual environment, installs dependencies, runs
  migrations, seeds the catalogue, starts the server, opens `/docs`, runs the recommendation flow
  and generates an Excel export. Verified end to end in **about 72 seconds**.

**Architecture at this checkpoint.** `CLI → existing ingestion service → existing curated adapter`,
and `HTTP/TestClient → existing application APIs/services`, with the product direction unchanged:
`router → service → existing domain engines`. No duplicated ingestion, eligibility or matching
logic; no new AI runtime; no new persistence model; no AgentOS product runtime; no frontend; no
server-side candidate, evaluation or application storage.

**Algorithmic state preserved (Weeks 4–6).** Eligibility: deterministic hard constraints keep final
authority, AI handles only approved ambiguous field-of-study cases, and a verified hard failure
remains `NOT_ELIGIBLE` (ADR-017, ADR-019). Matching: deterministic skill normalization, TF-IDF,
cosine similarity as a 0–100 score, corpus fingerprint, candidate never in the corpus (ADR-020,
ADR-021). Recommendations: eligibility-first orchestration into `ranked`, `needs_review`,
`not_eligible` and `not_open`, deterministic ranking and explanations, no combined score (ADR-022).
Export: rendering only — no eligibility or matching recalculation (ADR-023). No new algorithm.

| Check | Result |
|---|---|
| PR #19 merged on GitHub | `merged: true`, `merge_commit_sha` = `13eb8325149cab60a039534631265803250b767a` |
| Tree on `main` vs reviewed PR head `ed68d47` | **Identical** |
| Scope | 16 files: catalogue data, `app/cli.py`, OpenAPI status text, three new test files, three C-31 assertions, ADR-024 and documentation. Week 1–5 services, schemas, routers, models, adapters, `app/ai/**`, `alembic/**`, `requirements.txt` and CI untouched. |
| Working tree / `origin/main` | Clean; local `main` = `origin/main` = `13eb832` |
| Full suite from `main` | **1133 total — 1133 passed, 0 failed, 0 skipped**, offline (no `ELIGICORE_*`, proxies to a dead port) |
| CI on `13eb832` | `test` completed, conclusion `success` |
| Mutation testing from `main` | Week 6B **23/23** · Week 6A **30/30** · Week 5B **40/40** · Week 5A **36/36** · Week 4 **27/27**; sources restored byte-identical |
| Live verification | **33/33** checks: nine routes and no stubs; CLI reuses the adapter and ingestion service, seeds 40 and repeats unchanged, refuses a database behind head or missing without creating a file, rejects `--reset`/`--dataset`/`--profile`/unknown/no-args, counts-only output, only operational tables written |
| Catalogue verification | **18/18** checks (size, preservation, uniqueness, synthetic data, every diversity dimension) |
| Quickstart | Fresh clone of `main` → working Excel export in **72 s** |
| Migration chain | Unchanged — three migrations, head `b3e8d2c61a47`; no Week 6 migration; models unchanged; fresh `upgrade head` + `alembic check` clean |
| Tables | Exactly `jobs`, `ingestion_state` (+ `alembic_version`); no candidate, evaluation, application or tracker table |
| Privacy | No candidate persistence; no candidate PII in logs, errors, metadata, filenames or the database; no unexpected files and no temporary workbook files; formula injection mitigated; no hyperlinks, external links, macros or custom XML; synthetic catalogue only; network guard in the full-flow test and no live external AI call anywhere in the suite |
| Performance (local, synthetic) | Seed 40 jobs ≈ 0.7 s including interpreter start (idempotent rerun the same); full-flow file ≈ 0.9 s; the three new test files ≈ 9.6 s — not a production capacity claim |

**Gates:** QG-001 PASS · QG-005 PASS · QG-004 PASS (OpenAPI accuracy items only) · QG-002 N/A (no
eligibility change) · QG-003 N/A (no AI change) · QG-006 N/A (no model or migration) · QG-007 N/A ·
QG-008 N/A.

**Reviewers:** architect, qa, performance, security, documentation PASS. The ai reviewer was not
triggered (no AI change); release was not triggered (nothing deployed or tagged).

**Final Week 6 status against the dossier (§15, §17).** The Phase 1 product is demoable end to end
from a fresh clone; recommendations differ sensibly across two distinct candidate profiles; the
Excel export is clean and opens in Microsoft Excel without repair; a full-flow integration test
exists and runs offline; the mock AI path is used and tested, and the provider stays swappable by
configuration; local setup is documented and verified. Scope remained bounded to the approved work.
**No claim is made about production deployment, live external job sources or authentication** —
those remain Week 9 and later phases.

**Known limitations:**
- The OpenAPI "Current status" text still reads *"Weeks 1–5 … Week 6 is underway"*. Correcting it
  touches `app/main.py` and the two tests that pin the sentence, so it was deliberately kept out of
  this documentation-only record and is tracked as the next small approved change.
- Golden expectations in the full-flow test are tied to the catalogue's content; a catalogue edit
  must update them in the same change.
- Static deadlines and graduation windows age; status is never inferred from a deadline.
- Carried forward: Gemini's live calls and model identifier are unverified, and the migration chain
  has never run against PostgreSQL (both Week 9).

**Week 7 has not started.** No branch, no application-preparation or truthfulness code, no caching
or cost logging, and no `/api/v1/applications/prepare`, `/api/v1/matching/score` or
`/api/v1/jobs/ingest` route.

### Checkpoint 6A — verification record (intermediate)

**Checkpoint:** Checkpoint 6A — Week 6 Excel Export (intermediate)
**Phase:** Week 6, PR 6A — Excel tracker export
**Commit on `main`:** `0125703` — the PR #17 merge commit, parents `b39937a` (previous `main`, the
Checkpoint 5 record) and `c56d1d8` (PR 6A branch head). Real merge; the ten PR 6A commits are
preserved.
**Merged by:** `Lakshya172` on GitHub at 2026-09-19T18:47:26Z, after review and a real Microsoft
Excel compatibility check of the PR head. The post-merge gate confirmed the merged tree
(`d50f570`) is identical to the reviewed head `c56d1d8` and verified that state.

**Git history of Week 6 so far:**

| Step | Merge on `main` |
|---|---|
| Week 6A implementation (PR #17) — **Checkpoint 6A** | `0125703ad9464216b1622c14941664ec32ac9bac` |

**Week 6 capability at this checkpoint — Excel tracker export** (`POST /api/v1/applications/export`,
ADR-023):

- **Stateless renderer.** The client supplies complete tracker records; the server renders them to
  `.xlsx` in memory and returns the file. No database lookup, no persistence, no server-side
  tracker storage, no cache, no AI, no recalculation of eligibility or matching, no enrichment.
- **Contract.** 1–500 records; duplicate `job_id` rejected; unknown fields rejected at every
  level; `ApplicationStatus` = `NOT_APPLIED` · `APPLIED` · `INTERVIEW` · `REJECTED` · `OFFER`;
  nullable `match_score`; optional `requirement_breakdown`; rows written in request order.
- **Workbook.** Sheet `Tracker` (13 fixed columns) and, only when breakdown data exists, sheet
  `Requirements` (10 fixed columns, each row tied to its parent by `Tracker Row` and `Job ID`).
  A null score is an empty cell, never 0; `deadline` is a real Excel date; `evaluated_at` a real
  Excel datetime in UTC; Unicode preserved; apply links are plain text, never hyperlinks.
- **Formula-injection defence.** Text starting with `=`, `+`, `-`, `@`, tab or carriage return is
  prefixed with an apostrophe, and every text cell is pinned to the string type — which also keeps
  `#N/A`, `#REF!` and the other error codes as literal text.
- **Identity and metadata.** No candidate field in the request; fixed metadata (creator and
  last-modified-by `EligiCore`, title `EligiCore application tracker`); fixed filename
  `eligicore-tracker.xlsx` with no candidate data or timestamp; `Cache-Control: no-store`.
- **No temporary file.** openpyxl's own save spools worksheets through temporary files; the
  service serialises them in memory instead (ADR-023 §9, memory D-31).
- **API contract exception (C-23).** The successful 200 is a deliberate binary response — the one
  documented exception to the JSON/Pydantic `response_model` convention. The request is still a
  Pydantic model, and 405/422/500 still use the standard error envelope without echoing input.
- **Also in PR 6A:** the stale OpenAPI status text is corrected — Weeks 1–5 complete, Week 6
  underway (C-29).

**Architecture at this checkpoint:** `router → tracker_export service`. The export service imports
only the standard library, openpyxl and schema types — no FastAPI, Starlette, SQLAlchemy, database,
models, AI, eligibility, matching, recommendations or filesystem module (AST and fresh-interpreter
tests). Nothing but `app/main.py` and its router imports it. The Week 1–5 architecture is unchanged:
no Week 1–5 service, schema, router, model, migration, adapter, AI module or CI file was modified.

| Check | Result |
|---|---|
| PR #17 merged on GitHub | `merged: true`, `merge_commit_sha` = `0125703ad9464216b1622c14941664ec32ac9bac` |
| Tree on `main` vs reviewed PR head `c56d1d8` | **Identical** |
| Scope | 16 files: tracker schema, export service, applications router, `app/main.py` (registration + C-29 text), `requirements.txt`, ADR-023, `standards/api_design.md` pointer, context, CHANGELOG, README, config, two test files |
| Working tree / `origin/main` | Clean; local `main` = `origin/main` = `0125703` |
| Full suite from `main` | **1075 total — 1075 passed, 0 failed, 0 skipped**, offline (no `ELIGICORE_*`, proxies to a dead port) |
| Regression | The 850 tests of Checkpoint 5 unchanged and passing; 225 new |
| CI on `0125703` | `test` completed, conclusion `success` (run `35462320893`) |
| Mutation testing from `main` | Week 6A **30/30** · Week 5B **40/40** · Week 5A **36/36** · Week 4 **27/27**; sources identical to `HEAD` afterwards |
| Live API (uvicorn, migrated file database) | **46/46** checks: 200 with the XLSX type, fixed filename, `no-store` and `X-Request-ID`; `GET` → 405; malformed, wrong-type, empty, duplicate-id, 501-row, bad-status, bad-score, oversized and unknown-field bodies → 422 in the standard envelope without echo; `/api/v1/matching/score` → 404; `/api/v1/jobs/ingest` absent; exactly nine routes; workbook structure, values, types and XML |
| Microsoft Excel 16.0 | Opened without repair (a deliberately corrupted control copy was refused under the same settings); **23/23** checks: sheets and headers, row order, text/number/date/empty types and display, UTC datetimes, Unicode, dangerous strings and error codes as literal text, no formula or error cells, no hyperlinks, comments, hidden rows/columns, external links, defined names or VBA project, metadata `EligiCore` only |
| Workbook XML | No `<f>` element or `calcChain`; no hyperlink element or relationship; no external targets or links; no macros, custom XML, comments, drawings, connections or hidden state |
| Privacy | No database write — database file byte-identical; no candidate data in DEBUG logs or errors; one counts-only `tracker_export` log line; no project files, no openpyxl or temporary workbook files |
| Dependencies | `openpyxl==3.1.5`, `et-xmlfile==2.0.0` pinned and installed; `pip check` clean; no other pin changed |
| Migration chain | Unchanged — three migrations, head `b3e8d2c61a47`; no Week 6 migration; models unchanged; fresh `upgrade head` + `alembic check` clean |
| Tables | Exactly `jobs`, `ingestion_state` (+ `alembic_version`); no tracker, application, evaluation or candidate table |
| Performance (local, synthetic) | 500 rows ≈ 39 ms; 500 rows + 2,500 requirement rows ≈ 244 ms; schema maximum ≈ 0.7 s, 37 MiB peak — not a production capacity claim |

**Gates:** QG-001 PASS · QG-004 PASS (binary 200 recorded as the item-3 exception, ADR-023 §8) ·
QG-005 PASS · QG-002 N/A (no eligibility change) · QG-003 N/A (no AI change) · QG-006 N/A (no model
or migration) · QG-007 N/A (no deployment) · QG-008 N/A (no resume change).

**Reviewers:** api, qa, architect, security, documentation PASS (architect note: the in-memory
writer relies on openpyxl internals — pinned exactly and guarded by the no-file and equivalence
tests). performance not triggered by the map (benchmark recorded above); ai and release not
triggered.

**Known limitations:**
- The server cannot vouch for a row: a client can export stale or edited verdicts (accepted, A-27).
- A neutralised value visibly keeps its leading apostrophe (`'=1+1`) — by design.
- The in-memory writer overrides openpyxl internals; re-run the no-file tests on any upgrade.
- Carried from Checkpoint 5: 5-job curated catalogue (expansion is PR 6B), Gemini's live calls and
  model identifier unverified, PostgreSQL unverified.

**Deferred, explicitly:** `/api/v1/matching/score` · `/api/v1/jobs/ingest` ·
`/api/v1/applications/prepare` · catalogue expansion · local setup/demo command · full-flow Week 6B
test · application preparation · truthfulness validator · caching · cost logging · deployment ·
frontend · authentication · new AI. No stub routes exist.

**PR 6B has not started. Checkpoint 6 is not established.** No 6B branch or PR, no catalogue
expansion, no demo command, no full-flow test, no further Week 6 feature work.

### Checkpoint 5 — verification record (final Week 5)

**Phase:** Week 5 — Matching Engine (final: PR 5A + PR 5B)
**Commit on `main`:** `0aaaa1d` — the PR #15 merge commit, parents `4ee8e0c` (previous `main`, the
Checkpoint 5A record) and `f761588` (PR 5B branch head). Real merge; the nine PR 5B commits are
preserved.
**Merged by:** `Lakshya172` on GitHub at 2026-09-19T17:22:56Z, after review and a correction pass.
The post-merge gate confirmed the merged tree is identical to the reviewed head `f761588`.

**Git history of Week 5:**

| Step | Merge on `main` |
|---|---|
| Week 5A implementation (PR #13) — Checkpoint 5A | `05534affced482f6bc5e188ac465144dd425f9a7` |
| Week 5A checkpoint record (PR #14) | `4ee8e0c0bacdecbbf7c224bf5fded63a7c20ac14` |
| Week 5B implementation (PR #15) — **Checkpoint 5** | `0aaaa1da6fe643b8164df645113322adc889075d` |

**Week 5 capability at this checkpoint:**

- **5A — deterministic matching engine** (`app/services/matching_engine.py`, ADR-020, ADR-021):
  skill normalization and comparison by canonical key, skill coverage, custom tokenizer with a
  separate `skill:` namespace, TF-IDF fitted on the whole catalogue with the candidate never in
  the corpus, cosine similarity reported as a 0–100 score (or `null` when there is nothing to
  compare), deterministic ordering, template explanations, no persistence, framework-independent.
- **5B — recommendation orchestration** (`POST /api/v1/recommendations`, ADR-022):
  eligibility-first reuse of Week 4 eligibility and Week 5A matching; groups `ranked`,
  `needs_review`, `not_eligible`, `not_open`; 50-job cap; default ACTIVE + UNKNOWN scope;
  explicit CLOSED/EXPIRED retrieval; deterministic truncation disclosure; corpus fingerprint;
  composed explanations; no new AI, no database change, no persistence.

**Invariants recorded at this checkpoint:**

- **Eligibility authority.** Deterministic hard failures remain `NOT_ELIGIBLE`; AI cannot override
  them (ADR-017, ADR-019). Recommendation grouping never rewrites a verdict — each item embeds the
  Week 4 `JobEligibility` unchanged.
- **`not_open`.** Explicitly requested CLOSED/EXPIRED jobs enter `not_open`, which takes precedence
  over every eligibility state. `not_open` is unranked, ordered by `job_id`, and keeps its match
  score and match data whatever its verdict. Only the `not_eligible` group withholds the score.
- **Corpus.** The TF-IDF corpus is the whole catalogue; recommendation scope is separate; candidate
  data never enters the corpus.
- **Fingerprint.** Deterministic SHA-256 over the ordered public job matching documents:
  candidate-independent, sensitive to job content and catalogue order, insensitive to
  `last_verified_at`, never persisted.
- **Ranking.** `ranked` and `needs_review`: score descending, null scores last, `job_id` ascending.
  `not_eligible` and `not_open`: `rank = null`, `job_id` ascending. No combined eligibility/matching
  score.
- **Architecture.** `router → recommendation service → eligibility + matching`; neither the
  matching engine nor eligibility imports recommendations.

| Check | Result |
|---|---|
| PR #15 merged on GitHub | `merged: true`, `merge_commit_sha` = `0aaaa1da6fe643b8164df645113322adc889075d` |
| Tree on `main` vs reviewed PR head `f761588` | **Identical** |
| Scope | 17 files: recommendation schemas, service, router, corpus fingerprint, tests, ADR-022, ADR-020 amendment, context. Week 4 eligibility engine and AI stage, eligibility schemas, `app/ai/**`, models, migrations, adapters, `requirements.txt` and CI untouched. |
| Working tree / `origin/main` | Clean; local `main` = `origin/main` = `0aaaa1d` |
| Full suite from `main` | **850 total — 850 passed, 0 failed, 0 skipped**, offline (no `ELIGICORE_*`, proxies to a dead port) |
| Regression | Test files as of Checkpoint 5A: **747 passed** (the 736 unchanged plus 11 fingerprint additions); no test removed or weakened |
| CI on `0aaaa1d` | `test` completed, conclusion `success` (run `35457917009`) |
| Mutation testing from `main` | Week 5B **40/40** · Week 5A **36/36** · Week 4 **27/27**; sources restored byte-identical |
| Live API (uvicorn, file database) | **61/61** checks: 200; `GET` → 405; `/api/v1/matching/score` → 404; malformed, empty and 51-id bodies → 422 without echo; duplicates, unknown and mixed ids; all 13 response fields; grouping, `not_open`, scope, corpus, fingerprint A–E, ranking, explanations, privacy |
| Migration chain | Unchanged — head `b3e8d2c61a47`; no Week 5 migration; models unchanged; fresh `upgrade head` + `alembic check` clean |
| Tables | Exactly `jobs`, `ingestion_state` (+ `alembic_version`); no candidate, evaluation or recommendation table |
| Privacy | No candidate or recommendation persistence, no cache, no file writes; database byte-identical across recommendation requests; no candidate PII in logs or errors; counts-only recommendation log with no terms or per-job scores |
| Performance (local, synthetic, mock AI) | 50 catalogue jobs ≈ 27 ms, 500 ≈ 194 ms median — not a production capacity claim |

**Gates:** QG-001 PASS · QG-004 PASS · QG-005 PASS · QG-002 N/A (no eligibility change) · QG-003 N/A
(no AI change) · QG-006 N/A (no model or migration) · QG-007 N/A · QG-008 N/A.

**Reviewers:** api, qa, architect, security, documentation PASS; performance CONDITIONAL PASS
(whole catalogue loaded per request — re-measure before an order-of-magnitude catalogue growth).

**Known limitations:**
- The whole catalogue is loaded and fitted per recommendation request; bounded at Phase 1 scale.
- Recommendations inherit Week 4 AI cost and latency for ambiguous fields (≤ 50 jobs per request,
  including explicitly requested closed jobs).
- A 5-job curated catalogue gives coarse IDF; scores and the fingerprint change when the catalogue
  changes.
- English stop words only, no stemming; projects and certifications are not matched.
- Carried from Checkpoint 4: Gemini's live calls and model identifier unverified; PostgreSQL
  unverified.

**Week 5C has not started.** No `/api/v1/matching/score`, no Week 5C branch or PR, no further
matching features.

### Checkpoint 5A — verification record (intermediate)

**Phase:** Week 5, PR 5A — Deterministic Matching Engine
**Commit on `main`:** `05534af` — the PR #13 merge commit, parents `98b225d` (previous `main`, the
Checkpoint 4 record) and `80521f4` (PR 5A branch head). Real merge; the five PR 5A commits are
preserved.
**Merged by:** `Lakshya172` on GitHub at 2026-09-17T16:13:50Z, after independent verification. The
post-merge gate confirmed the merged tree is identical to the reviewed head `80521f4` and verified
that state.

**Week 5 capability at this checkpoint (service only):** `app/services/matching_engine.py` —
narrow matching inputs · skill comparison by canonical key (ADR-021) · `.NET` normalization
correction · custom tokenizer · `skill:` namespace separate from prose · TF-IDF fitted on the whole
catalogue, never on the candidate · cosine score `round(clamp(100·cos, 0, 100), 1)` · `null` with
`NO_JOB_TERMS` / `NO_CANDIDATE_TERMS` when there is nothing to compare · skill coverage (no
percentage) · top five shared terms · deterministic template explanations · ordering key (score
desc, nulls last, `job_id` asc) · `MATCHING_VERSION` 1 · `scikit-learn==1.7.2`. **No endpoint calls
it yet.**

| Check | Result |
|---|---|
| PR #13 merged on GitHub | `merged: true`, `merge_commit_sha` = `05534affced482f6bc5e188ac465144dd425f9a7` |
| Tree on `main` vs reviewed PR head `80521f4` | **Identical** |
| Scope | 14 files, 5 commits: matching engine, normalizer `.NET` fix and `skill_comparison_key`, scikit-learn pin, tests, ADR-020/021, context docs. No router, model, migration, schema, AI, eligibility, `app/main.py` or CI change. |
| Working tree / `origin/main` | Clean; local `main` = `origin/main` = `05534af` |
| Full suite from `main` | **736 passed**, 0 skipped, offline (no `ELIGICORE_*`, proxies to a dead port) |
| Regression | Test files as of Checkpoint 4: **628 passed** — the 615 existing tests unchanged, plus 13 new `.NET`/comparison-key tests added to `test_candidate_schema.py` |
| CI on `05534af` | `test` completed, conclusion `success` (run `35245284840`) |
| Mutation testing from `main` | **36/36 caught** (matching engine and normalizer); Week 4 suite re-run **27/27 caught**; sources restored byte-identical |
| Architecture boundary | AST and fresh-interpreter tests pass: the engine imports no FastAPI, Starlette, SQLAlchemy, database, models, routers, AI, httpx, eligibility, logging or file/IO module and calls no `open`/`print`; eligibility does not import matching; only `candidate_match_input` receives a `CandidateProfile` |
| Privacy | Markers in 16 non-approved profile fields absent from the narrowed input and result; unscoped DEBUG log capture clean; no file written; no log statement in the engine |
| Routes | Unchanged: no `/api/v1/recommendations`, no `/api/v1/matching/score` |
| Migration chain | `<base>` → `54a85d64881e` → `7c2f1a9b4d30` → `b3e8d2c61a47` (head); all three byte-identical to Checkpoint 4; fresh `upgrade head` + `alembic check` clean |
| Tables / registered models | Exactly `jobs`, `ingestion_state` (+ `alembic_version`); no candidate, evaluation, recommendation or score table |
| Dependency | `scikit-learn==1.7.2` pinned and installed; clean virtualenv from `requirements.txt` passed 736 |
| Final gate | No secrets, PII (only the synthetic `example.com` test marker), resume files or local databases tracked; no recommendation service, endpoint, AI change, frontend, submission logic or persistence |

**Reviewers:** architect PASS · qa PASS · security PASS · documentation PASS · performance
CONDITIONAL PASS (50 jobs × ~700-word descriptions 85 ms; ~1.5 s cold import of scikit-learn;
non-blocking notes for PR 5B). The ai reviewer was not triggered — no AI change.

**Gates:** QG-001 PASS · QG-005 PASS (applicable items) · QG-002 N/A (no eligibility change) ·
QG-003 N/A (no AI change) · QG-004 N/A (no endpoint or API schema) · QG-006 N/A (no model or
migration; chain re-verified) · QG-007 N/A · QG-008 N/A.

**Known limitations:**
- Service only — no endpoint uses the engine; recommendations are PR 5B.
- A 5-job catalogue gives coarse IDF; scores change when the catalogue changes.
- English stop words only, no stemming ("pipeline" ≠ "pipelines").
- A candidate whose terms are all outside the catalogue vocabulary gets `null`, not `0.0`.
- Projects and certifications are not used; weak seed aliases (`node`, `rest`, `express`, `vue`)
  apply to skill lists.
- The `.NET` fix changes `/candidates/normalize` output for skills written with a leading dot.
- Carried from Checkpoint 4: Gemini's live relatedness call and model identifier unverified;
  PostgreSQL unverified.

**PR 5B has not started. Checkpoint 5 is not established.**

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
| **1st** | Checkpoint 8 — Week 8 Refinement, Caching and Cost Logging (final) | `9aba1f2` | **Current stable point.** If a future phase introduces a regression, this is the immediate rollback reference. |
| **2nd** | Checkpoint 7 — Week 7 Application Preparation (final) | `6c269a0` | **Historical fallback.** Week 7 without any Week 8 instrumentation or caching. Reached by reverting the Week 8 merges as appropriate — PR #36, then PR #35, then PR #34; **no database step** (Week 8 introduced no migration and no dependency). |
| **3rd** | Checkpoint 6 — Week 6 MVP (final) | `13eb832` | **Historical fallback — the dossier's declared safe stopping point (§15).** The complete demoable MVP without application preparation. Reached by also reverting the PR #28 merge; no database step. |
| **4th** | Checkpoint 6A — Week 6 Excel Export (intermediate) | `0125703` | The export without the demo path. Reached by also reverting the PR #19 merge; no database step. |
| **5th** | Checkpoint 5 — Week 5 Matching Engine (final) | `0aaaa1d` | Last state before any Week 6 code. Reached by also reverting the PR #17 merge; no database step (`openpyxl` and `et-xmlfile` leave `requirements.txt` with it). |
| **6th** | Checkpoint 5A — Week 5 deterministic matching engine | `05534af` | Matching engine without the recommendations endpoint. Reached by also reverting the PR #15 merge; no database step. |
| **7th** | Checkpoint 4 — Week 4 Eligibility Intelligence | `f56d7df` | Last state before any matching code. Reached by also reverting the PR #13 merge; no database step (scikit-learn leaves `requirements.txt` with it). |
| **8th** | Checkpoint 4A — Week 4 deterministic engine | `4a5cb84` | Deterministic eligibility without the AI stage. Reached by also reverting the PR #11 merge; no database step. |
| **9th** | Checkpoint 3 — Week 3 | `2cfd4f0` | Last state before any eligibility code. |
| **10th** | Checkpoint 2 — Week 2 | `91dd31d` | Known-good state before the job catalogue. |
| **11th** | Checkpoint 1 — Week 1 | `2e79454` | Remains available indefinitely as a historical recovery point. |
| **12th** | Checkpoint 0 — Phase 0 | `e8c68b7` | Engineering layer only, no product code. |

**The Week 8 rollback chain needs no database step.** Week 8 added no migration, no model and no
dependency, so recovering from Checkpoint 8 to Checkpoint 7 is code-only: revert the PR #36, #35
and #34 merges as appropriate, in reverse order. Each slice is independently revertible because
each is behaviour-preserving on its own (ADR-026 D1). The first database step still appears no
higher than Checkpoint 4A → Checkpoint 3.

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
