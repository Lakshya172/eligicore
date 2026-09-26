# Changelog

All notable changes to EligiCore are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). This project is in
active pre-release development and does **not** yet follow semantic versioning — there is no
released version. Development progresses through **checkpoints**, one per completed and merged
phase.

The **Week 6 MVP checkpoint** (Checkpoint 6) is the point at which the dossier considers the
system complete and demoable. Per ruling C-28 it is a checkpoint, not a release: no version or
tag is created for it.

---

## [Unreleased]

No work is pending. **Week 9B — Deployment and Sharing — is optional, owner-triggered and not
started.** It is not required for ordinary use of EligiCore and may never be performed. Week 9A is
complete and closed at **Checkpoint 9A** (`95a1187`).

### Known, tracked — after Checkpoint 9A

- **Nothing is deployed.** No hosted instance, no public URL, no platform account, no hosting
  artifact in the repository. **Local execution is the normal operating mode.**
- **No platform-log verification.** Week 9A verified application-controlled logs only.
- **No live Gemini call, no authentication, no rate limiting.** QG-007 item 10 (rate limiting on
  AI-cost-exposed endpoints) is unmet by design, because it governs a public deployment.
- **Seven Week 9B owner decisions are open** and none has been made: Render vs Railway · hosted
  PostgreSQL choice · rate-limiting mechanism and values · deployed AI provider · hosted catalogue
  seeding strategy · `/docs` exposure · shared-instance access control.
- **Uvicorn writes its own tracebacks to stderr** when an unhandled exception occurs — observed
  during the deliberate database outage in Week 9A-6. They carry repository and library file paths
  but **no credentials, no DSN, no database name and no candidate data**, and never reach the HTTP
  response. This is a hosted-logging consideration for 9B, **not an application privacy failure**.
- **One unexplained test failure remains an open diagnostic item.**
  `test_no_candidate_marker_survives_any_path_under_production` failed once during Week 9A-6 and
  has passed in every run since, but its assertion text was not captured. **The subsequent green
  runs do not establish that the original cause was benign** — the cause is unknown.

### Closed since Checkpoint 8

- **The stale OpenAPI "Current status" sentence**, tracked since Checkpoint 6, was corrected in
  Week 9A-1: it now reads "Weeks 1–8 of a 10-week build are complete."
- **PostgreSQL migration compatibility**, unverified since Week 3, was validated by execution in
  Week 9A-2 and again as part of the Week 9A-6 end-to-end run.

### Known, tracked — carried from Checkpoint 8

- **AI cost coverage excludes the application-generation path, by design.** Week 8 instruments
  `extract_resume` and `assess_field_relatedness` only. `generate_application_content` is excluded
  **structurally** — no usage sink is threaded through it and there is no setting that could
  enable one (ADR-026 D8) — because ADR-025's merged generation-logging rule stands verbatim and a
  token count is a length that could characterize one candidate's content. **Week 8 is not
  complete cost coverage.** That path becomes material only when live application generation is
  separately approved, and it will need its own explicit privacy decision then.
- **Live Gemini application generation remains deferred.** Nothing was added in Week 8; the Gemini
  generation method is still a stub, and no claim of live generation is made anywhere.
- **No benchmarked speed-up is claimed for the corpus cache.** Slice 8B is verified
  output-identical cold, warm and after invalidation; it was not benchmarked, and no latency
  figure is recorded.
- **The OpenAPI "Current status" string still reads "Weeks 1–6 of a 10-week build are complete."**
  while Weeks 7 and 8 are complete. Two merged tests pin that sentence, so correcting it touches
  `app/main.py` and both tests and was deliberately kept out of the documentation-only Checkpoint 8
  record — the same handling C-32 received at Checkpoint 6 and Checkpoint 7. It is tracked as the
  next small approved change. The endpoint-level documentation is accurate.

---

## Checkpoint 9A — Week 9A: Local Production Readiness

**Date:** 2026-09-26 · **Commit on `main`:** `95a1187` · **Status:** Stable — current
**Produced by:** PR #39 (`65b15bb`, 9A-1) + PR #40 (`89b616a`, 9A-2 prerequisite) + PR #41
(`229acc1`, 9A-3) + PR #42 (`88c884b`, 9A-4) + PR #43 (`8cd6ad8`, 9A-5) + PR #44 (`95a1187`, 9A-7),
on **ADR-027** (PR #38, `1afd4e5`). 9A-2's migration validation and 9A-6's end-to-end run were
verification-only and produced no commit.
**Full SHA:** `95a1187715851ee7a67fa8cdbc7c6e87f3fa7ec3` · **CI:** `test` success ·
**Tests:** 1567 passing from `main` (0 failed, 0 skipped) · **Alembic head:** `b3e8d2c61a47`

**This checkpoint records a verified local product, not a deployment.** EligiCore runs from a
terminal on `localhost`, and that is the normal operating mode — **localhost is sufficient for
ordinary personal use.** There is no hosted instance and no public URL. **Week 9B — Deployment and
Sharing — is optional and owner-triggered**, and may never happen.

**This is a checkpoint, not a release. No tag and no version bump.**

**Checkpoint 9A is a stage checkpoint.** Week 9 is two stages under ADR-027. **Checkpoint 9 remains
reserved for the final Week 9 state** and is established only if the owner deliberately deploys.

### What Week 9A verified

- **9A-1 — OpenAPI currency (PR #39).** Status corrected from Weeks 1–6 to Weeks 1–8. **The
  document is byte-identical once `info.description` is removed** — 10 paths, 58 schemas, all
  status codes unchanged. No route or schema contract change.
- **9A-2 — PostgreSQL compatibility (PR #40 + verification).** `psycopg2-binary==2.9.10` added,
  closing a real gap: ADR-009 names PostgreSQL for production but no driver was declared. The
  existing three-migration chain was then run against **local PostgreSQL 18.6** — upgrade,
  representative data, constraint probes, stepwise downgrade, re-upgrade, and `alembic check`
  executed against PostgreSQL. **`batch_alter_table`, used by all three migrations and never
  before run outside SQLite, fell through to plain `ALTER TABLE` as documented.** No migration
  modified; head unchanged.
- **9A-3 — Production configuration (PR #41).** Production mode had no test coverage at all.
  Seven tests now pin it. The finding: **traceback suppression is unconditional**, not caused by
  the environment setting — a stronger guarantee, because it cannot be lost by misconfiguration.
- **9A-4 — Secret handling (PR #42).** Tree and full-history scans — 162 files, 412 reachable
  blobs, 190 commits, every historical revision of the environment and CI files, all commit
  messages — found **no real secret**. **`.env` has zero historical revisions: it was never
  committed.** The API key is read in exactly one place, the request header.
- **9A-5 — Privacy and logging (PR #43).** The Week 8C guarantees re-verified **under
  production**, which no merged test had done. Sixteen markers, every candidate-carrying endpoint,
  a controlled 500, cost records and a full database dump — all clean.
- **9A-6 — Local end-to-end (verification only).** A real `uvicorn` process against local
  PostgreSQL under production: 40 jobs seeded, **all ten routes exercised from the live OpenAPI
  inventory, every one 200**, a genuine 500 from stopping the database, and the **rollback
  executed** — 41 rows preserved through both data-preserving downgrades, every constraint and
  index restored, and the application restarted against the restored schema.
- **9A-7 — Documentation (PR #44).** README made current against the live application in both
  directions. **Two fresh clones from GitHub reached a running API in 3 min 7 s and 2 min 46 s**,
  with no undocumented step.

### Privacy and boundaries

Unchanged and re-verified: no candidate, application, evaluation or package persistence; no PII in
logs, errors or cost records; no `candidate_id` in any cost record; no candidate-derived cache; no
submission, browser automation or CAPTCHA/OTP handling. Tables remain exactly `jobs` and
`ingestion_state`.

### Not included

No deployment, hosting, hosted database, public URL, authentication, rate limiting or live Gemini
work. **No Week 9 migration, model, API, schema or business-logic change.** One dependency across
all of Week 9A: the PostgreSQL driver. **None of the seven Week 9B owner decisions was made.**

---

## Checkpoint 8 — Week 8: Refinement, Caching and Cost Logging (final)

**Date:** 2026-09-24 · **Commit on `main`:** `9aba1f2` · **Status:** Stable
**Produced by:** PR #34 (`e5d6d36`, cost/usage accounting — Slice 8A, no checkpoint of its own)
+ PR #35 (`f3fbf35`, corpus vectorizer cache — Slice 8B, no checkpoint of its own)
+ PR #36 (`9aba1f2`, operational-log completeness — Slice 8C)
**Full SHA:** `9aba1f2b1007b0931ec9adc39afb88b15eaa2c14` · **CI:** `test` success on all three
merges · **Tests:** 1549 passing from `main` (0 failed, 0 skipped) ·
**Mutations:** 230/230 — 8C 32/32 · 8B 34/34 · 8A 68/68 · 7B 54/54 · 7A 42/42

Week 8 as a whole: EligiCore now knows what its AI calls cost, stops re-fitting the same job
catalogue on every request, and records every inbound request — including the ones that end in an
unhandled exception, which it had been silently missing. Ruled by **ADR-026** and delivered in
three slices, **every one of them behaviour-preserving**: no endpoint, route, schema, contract,
verdict, score or response body changed, and every existing response stays byte-identical.

**This is a checkpoint, not a release. No tag and no version bump.**

**Week 8 has no intermediate checkpoint.** None of the three slices recorded one — each is
behaviour-preserving on its own, so the intermediate states are not distinct rollback destinations
— and there is no Checkpoint 8A, 8B or 8C.

### Slice 8A — cost and usage accounting (PR #34)

#### Added

- **`app/ai/usage.py`** — `AIUsage`, a per-call `UsageSink`, and cost arithmetic in integer
  micro-units. **One sink per call, never provider state**: `eligibility_ai` fans assessments out
  through `asyncio.gather`, and shared mutable provider state would race and mis-attribute cost on
  exactly the path this slice covers (ADR-026 D3).
- **Token and cost logging on `extract_resume` and `assess_field_relatedness`**, on both the
  success and the error path — provider, model, operation, outcome, prompt/completion/total tokens,
  cost and duration.
- **Usage accumulation across retries** (D4). A Gemini call that fails twice and succeeds on the
  third consumed tokens three times. The usage on a retryable error body is read *before* the error
  is translated. Discovered by a post-merge audit and fixed in `0d2689c`: the first implementation
  raised on 429/5xx before reading the body, so three attempts reported one attempt's tokens.
- **`ModelCostRate` configuration** keyed `provider:model`, with an **empty default table** — no
  external provider price is hard-coded anywhere (D5). Published pricing is a third-party fact that
  changes, and a stale constant in source would be a fabricated figure presented as a measurement.
- **Deterministic synthetic usage from the mock provider**, switchable off, so the unknown path is
  exercised rather than asserted.

#### Behaviour

- **Unknown means unknown.** An unknown provider or model, a missing rate, or absent, partial or
  malformed usage yields `unknown` — and prompt, completion and total tokens each degrade
  **independently**.
- **Accounting can never change an AI outcome** (D6). Every accounting path is wrapped; a defect in
  it logs `unknown` and is otherwise inert.
- **Operational log records only** (D9). No cost table, no ledger, no migration, and **no
  `candidate_id` in any cost record** — a per-candidate cost ledger would be candidate persistence
  wearing an accounting hat.

#### Not included

- **No cost or usage accounting on `generate_application_content`** — see the limitation above and
  ADR-026 D8. The exclusion is structural: the call has no usage parameter at all.

### Slice 8B — candidate-free corpus vectorizer cache (PR #35)

#### Added

- **A process-local, bounded, in-memory LRU of capacity 4** in `app/services/matching_engine.py`,
  holding the fitted vectorizer, the job matrix, the feature names and the catalogue row mapping —
  every one of them derived from the catalogue alone.
- **Keyed by the existing `corpus_fingerprint`**, which is an exact determinant of the fit rather
  than a heuristic: it hashes each catalogue job's id and terms in order, precisely the inputs that
  decide the fit and the row mapping.

#### Behaviour

- **The candidate is never cached.** `vectorizer.transform(candidate_terms(...))` stays
  per-request, every time. The fit is cached; the candidate's transform is not — that single
  boundary is the whole privacy argument for this slice, and ADR-020's rule that the candidate is
  transformed and never fitted is preserved exactly.
- **Output-identical**: cold, warm and after invalidation. A catalogue change produces a different
  fingerprint and a miss.
- No Redis, no disk, no external cache service, **no new dependency and no cache configuration
  key** — the bound is a module constant, so there is no setting whose default could later be
  widened into a policy change.

#### Recorded

- **ADR-020 §5 is superseded in part** by ADR-026, recorded explicitly in PR #33 (`dc0a759`) as an
  owner-ruled supersession that preserves the original historical wording rather than rewriting it.

### Slice 8C — operational-log completeness (PR #36)

#### Fixed

- **A request that ends in an unhandled exception now emits its request record.** Starlette's
  `ServerErrorMiddleware` — which turns an unhandled exception into the 500 — sits *outside* the
  request middleware, so the exception travelled back through `call_next` and the log call after it
  never ran. The request count was systematically blind to exactly the requests an operator most
  needs to see. Eight lines, in `app/main.py`; it handles nothing, changes no response, and leaves
  the 500 to the existing handler.
- **Nothing about the exception is logged there.** Its type is the error record's business, and its
  message can carry candidate data.

#### Verified, not changed

- Request counts on success, 404, 405 and 422; error records for validation failures and unhandled
  exceptions; the Slice 8A cost records through a real endpoint. A 4xx `HTTPException` deliberately
  gets no second, dedicated error line — its request record carries the status.
- **AI provider retries are outbound and never reach the middleware**: three retry attempts produce
  zero inbound request records.

### Privacy and boundaries (all three slices)

- **No `candidate_id` in any cost, usage or error record.** No PII in any log line — fourteen
  markers asserted absent across seven paths.
- **No candidate-derived cache, no generated-prose cache, no résumé-content retention.**
- **No persistence added.** No cost, usage, ledger, candidate, application, evaluation or package
  table; tables remain exactly `jobs` and `ingestion_state` (plus `alembic_version`).
- **The generation path emits no token, length or cost field** — verified structurally on the
  syntax tree, and at runtime through a live prepare request.
- **No submission, autofill, browser automation or CAPTCHA/OTP handling** (ADR-008, INV-10).
- Deterministic eligibility authority is unchanged (ADR-017, ADR-019); so are matching,
  recommendations, export and preparation.

### Not included

- No live Gemini application generation, and no new AI provider.
- No endpoint, route, schema or contract change — **10 routes, OpenAPI byte-identical**.
- No new model, migration, table or dependency — `requirements.txt` untouched across all three
  slices.
- No spaCy fallback, no résumé extraction-accuracy measurement, no matching or recommendation
  tuning, no metrics or admin endpoint, no frontend, no deployment, no authentication, no rate
  limiting.
- **These PRs did not record the checkpoint**; Checkpoint 8 was recorded separately.

---

## Checkpoint 7 — Week 7: Application Preparation (final)

**Date:** 2026-09-22 · **Commit on `main`:** `6c269a0` · **Status:** Stable
**Produced by:** PR #24 (`365e7a4`, truthfulness validator — Slice 7A, no checkpoint of its own)
+ PR #28 (`6c269a0`, application preparation — Slice 7B)
**Full SHA:** `6c269a05ec1a4fdbdc7820d0c6b0b40980ba8fb3` · **CI:** `test` success ·
**Tests:** 1358 passing from `main` (0 failed, 0 skipped) · **Mutations:** 7B 54/54 · 7A 42/42 ·
6B 23/23 · 6A 30/30 · 5B 40/40 · 5A 36/36 · Week 4 27/27

Week 7 as a whole: a candidate can now ask EligiCore to prepare application material for one
catalogue job, and gets back a draft in which **every claim that could not be traced to the
profile they supplied has been removed rather than reworded**, with an audit list of what went and
why. Ruled by **ADR-025** and delivered in two slices — the deterministic validator first, the
endpoint that uses it second. **Week 6 remains the dossier's declared safe stopping point;**
Week 7 is the first enhancement week on top of it.

**This is a checkpoint, not a release. No tag and no version bump.**

**Week 7 has no intermediate checkpoint.** Slice 7A deliberately recorded none — a validator with
no caller is not a state worth rolling back to — so there is no Checkpoint 7A.

### Slice 7B — application preparation (PR #28)

#### Added

- **`POST /api/v1/applications/prepare`** — takes one catalogue `job_id`, the candidate profile in
  the request body and at most five client-supplied questions, and returns a sanitized cover letter
  and per-question answers, the full `removed_claims` audit list, a package status, per-item
  confidence and an explicit notice that **EligiCore never submits on the candidate's behalf**.
  Stateless: nothing is written, cached or retained. An unknown `job_id` is a 404 carrying no
  profile data.
- **`app/services/application_prep.py`** — the orchestration: one catalogue read, one provider
  generation call, then the Slice 7A validator on every generated string. Raw generated text never
  reaches the response; the only paths that touch it are an emptiness check, a word count and the
  validator call.
- **Provider boundary `generate_application_content`** on `AIProvider` and `AIService` (ADR-004),
  with a counts-only logging wrapper and a reply-shape guard.
- **Deterministic conservative mock generation** — the mandatory mock provider can be injected into
  fabricating, over-length and empty modes so the sanitization and degradation paths are exercised
  by tests rather than asserted.
- **`app/ai/prompts/application_content.txt`** — the reviewed prompt, kept as a file and not an
  inline string, with a BEGIN/END convention marking every data block as data and never
  instruction.
- **Application preparation request/response contracts** in `app/schemas/application.py` — bounded
  question count, id pattern and text length, bounded word limits at both ends, `extra="forbid"`
  throughout.
- **98 tests** in `tests/test_application_prep.py`, plus a preparation leg in the offline
  full-flow test. 54/54 mutants caught.

#### Changed

- Five merged assertions were re-aimed after the provider interface grew a method — the AI
  interface-surface test, the eligibility spy provider, the export router-dependency test, the
  deferred-endpoints test and the full-flow status assertion. **Each was strengthened, none
  weakened**: the deferred-endpoints test now asserts `/applications/prepare` is present rather
  than absent, and the router-dependency test became signature-based.
- The OpenAPI description gained the preparation endpoints and a new **"Application packages are
  drafts"** section. The top-level "Current status" sentence was deliberately left unchanged.

#### Privacy and boundaries

- **The provider sees five evidence fields** — `skills`, `experience`, `projects`,
  `certifications`, `education` — and nothing else. `experience` carries only title, duration and
  description; `education` only degree, level, field of study and graduation year; a certification
  only its name. **Employer names, languages, contact details, location, institution, grades,
  backlog count, `candidate_id` and `resume_raw_text` never leave the service** (ADR-025 D10–D12).
  The projection is written field by field — no `model_dump`, no `**` unpacking, no attribute
  iteration — so a new profile field cannot reach a provider by accident.
- **Two counts-only log lines.** No candidate data, question text, generated prose or removed-claim
  text is logged anywhere.
- **No persistence.** No candidate, application, evaluation or package table; the database file is
  byte-identical across a prepare request.

#### Not included

- **No live Gemini generation** — the Gemini method is a stub that raises
  `AIProviderUnavailableError` and holds no transport, prompt or key. Deferred to Week 8/9
  (ADR-025 D13).
- No caching, no AI cost or token logging, no second AI call, no AI claim extraction.
- No eligibility, matching, recommendation, ingestion or export change. No résumé tailoring, no
  PDF/DOCX rendering, no application tracking or status endpoint.
- **No submission, autofill, browser automation, or CAPTCHA/OTP handling** (ADR-008, INV-10).
- No new model, migration, table or dependency. No `/matching/score`, no `/jobs/ingest`.
- **This PR did not itself record the checkpoint**; Checkpoint 7 was recorded separately.

### Slice 7A — truthfulness validator (PR #24)

Merged and verified ahead of 7B and deliberately recorded **no checkpoint**. Covered here as part
of Week 7 as a whole.

#### Added

- **`app/services/truthfulness_validator.py`** — deterministic, AI-free claim validation with no
  FastAPI, database, filesystem or network dependency. Remove-by-default: a sentence survives only
  if every claim in it traces to the structured profile the caller supplied, and what does not
  survive is reported as a structured removal with a reason.
- The Slice 7A half of `app/schemas/application.py` — the removal vocabulary and `RemovedClaim`.
- **124 tests**; 42/42 mutants caught.

#### Unchanged by Slice 7B

The validator blob `4a8572ed4428f0e8e658ee663c266cf5cea0eaf6` is byte-identical before and after
the Slice 7B merge, and every enum member and `RemovedClaim` field survives. The validator remains
the **final sanitization boundary**: it is the last thing any generated string passes through.

### ADR-025 corrections merged during Week 7

- **PR #25** (`5e90636`) stated the evidence boundary exactly.
- **PR #26** (`f5b81f0`) corrected a stale `_Evidence` docstring — no executable change.
- **PR #29** (`234dabf`) corrected the failure-semantics wording so it matches the owner's ruling:
  `RemovalReason.ANSWER_REQUIRES_EXCLUDED_DATA` stays defined in the enum and **unused by the
  service**, and the `REQUIRES_EXCLUDED_DATA` answer outcome is derived only from actual validator
  output — an `EXCLUDED_DATA` removal that leaves nothing behind — never guessed from the question
  text. The divergence was reported rather than silently resolved: the owner's decision was
  implemented, and the ADR was corrected only once that correction was separately authorized.

---

## Checkpoint 6 — Week 6: MVP (final)

**Date:** 2026-09-20 · **Commit on `main`:** `13eb832` · **Status:** Stable
**Produced by:** PR #17 (`0125703`, Excel tracker export — see Checkpoint 6A) + PR #19
(`13eb832`, demo path and full-flow test)
**Full SHA:** `13eb8325149cab60a039534631265803250b767a` · **CI:** `test` success ·
**Tests:** 1133 passing from `main` (0 failed, 0 skipped) · **Mutations:** 6B 23/23 · 6A 30/30 ·
5B 40/40 · 5A 36/36 · Week 4 27/27 · **Live:** 33/33 · **Quickstart:** fresh clone in ~72 s

Week 6 as a whole: the Excel tracker export plus the demo path that makes the system runnable
by a stranger. **This is the dossier's declared safe stopping point (§15)** — the Phase 1
product is complete and demoable. The implementation was merged and verified post-merge: the
demo path works from a fresh clone, the catalogue holds 40 synthetic jobs, the local seed CLI
and the offline full-flow test are in place, and the Excel export is unchanged from 6A. **No
database or AI architecture was expanded.**

**This is a checkpoint, not a release. No tag and no version bump.**

### PR 6B — demo path and full-flow test

#### Added

- **Curated catalogue expanded to 40 synthetic jobs.** The original five entries are preserved
  byte-for-byte; 35 were appended covering 14 role families, internships and full-time roles,
  `SCALE_10`/`SCALE_4`/`PERCENTAGE` and scale-less cutoffs, graduation windows across 2025–2029,
  no-degree/`BACHELORS`/`MASTERS`, exact/ambiguous/unrestricted permitted fields, backlog limits
  0/1/2 and unstated, and one listing with no matching terms. Fictional companies,
  `example.com` links, no contacts.
- **`python -m app.cli seed-catalogue`** — local setup command that loads the catalogue through
  the existing adapter and ingestion service. Idempotent, deletes nothing, refuses a database
  that is missing or behind the Alembic head, never migrates or creates tables, takes no
  candidate input, prints counts only. **No HTTP equivalent is added.**
- **`tests/test_full_flow.py`** — the Phase 1 journey end to end and offline: résumé parse →
  profile completion → validate → normalize → eligibility → recommendations → Excel export,
  for two distinct synthetic profiles, with a socket guard and golden group expectations.
- **README quickstart** — clone to working export in four commands; verified from a fresh clone
  in 87 seconds.
- **ADR-024** Week 6 MVP scope (C-30..C-34).

#### Changed

- Three catalogue-coupled assertions now derive their counts from the dataset and scope the
  golden verdict map to the original five ids (C-31). No golden expectation changed.
- The OpenAPI status now names the curated catalogue and the seed command. As merged in this PR
  it still read "Week 6 is underway": correcting that sentence touches application code and the
  two tests that pin it, so it was deliberately kept outside the documentation-only checkpoint
  record and tracked as the next small change (C-32). **C-32 has since been completed** — PR #21
  (`932d719`, merged 2026-09-20, after Week 6 was closed at Checkpoint 6) set the final wording,
  *"Weeks 1–6 of a 10-week build are complete."*

#### Not included

- No new endpoint, AI, provider, prompt, model, migration or dependency. No `/matching/score`,
  `/jobs/ingest` or `/applications/prepare`. No eligibility or matching logic change, no status
  inference from deadlines, no candidate persistence. **This PR did not itself record the
  checkpoint**; Checkpoint 6 was recorded separately in PR #20 (`151df06`).

---

## Checkpoint 6A — Week 6 Excel Export (intermediate)

**Date:** 2026-09-19 · **Commit on `main`:** `0125703` · **Status:** Stable — intermediate
**Produced by:** PR #17 (`feature/week-6-excel-export`)
**Full SHA:** `0125703ad9464216b1622c14941664ec32ac9bac` · **CI:** `test` success ·
**Tests:** 1075 passing from `main` (0 failed, 0 skipped) · **Mutations:** 6A 30/30 · 5B 40/40 ·
5A 36/36 · Week 4 27/27 · **Live API:** 46/46 · **Microsoft Excel:** opened without repair, 23/23

An intermediate checkpoint — **not a release, version or tag**, and not the final Week 6 MVP.
Checkpoint 6 is reserved for Week 6 as a whole, after PR 6B. Checkpoint 5 remains the final
Week 5 checkpoint.

### PR 6A — Excel tracker export

#### Added

- **`POST /api/v1/applications/export`** — renders application-tracking rows supplied by the
  client as an `.xlsx` workbook: sheet `Tracker` (one row per record, request order) and, when
  breakdowns are supplied, sheet `Requirements`. 1–500 rows, unique `job_id`. A null
  `match_score` is an empty cell, never 0; dates are real Excel dates. Text that could run as a
  formula is prefixed with an apostrophe and stored as text. Fixed filename
  `eligicore-tracker.xlsx`, `Cache-Control: no-store`. Built entirely in memory; nothing stored.
- `ApplicationStatus`: `NOT_APPLIED`, `APPLIED`, `INTERVIEW`, `REJECTED`, `OFFER`.
- **ADR-023** tracker export contract (C-23..C-29).
- Dependencies: `openpyxl==3.1.5`, `et-xmlfile==2.0.0`.

#### Fixed

- The OpenAPI description no longer says Week 5 is in progress (C-29).

#### Not included

- No `/matching/score`, `/jobs/ingest` or `/applications/prepare` (deferred, C-25), no database
  change or migration, no AI, no persistence or cache, no Week 6B polish. **PR 6B has not
  started.**

#### Verified at this checkpoint

- Stateless and in memory: no database query or write (database byte-identical), no temporary
  workbook file, no project file, no candidate data in logs or errors, counts-only log line.
- The successful 200 is a deliberate binary response (ADR-023 §8); errors keep the standard
  envelope.
- Microsoft Excel opened the workbook without repair: correct sheets, values and types; no
  formulas, hyperlinks, external links or hidden content; metadata `EligiCore` only.
- Migration chain unchanged (three migrations); `alembic check` clean.

---

## Checkpoint 5 — Week 5: Matching Engine (final)

**Date:** 2026-09-19 · **Commit on `main`:** `0aaaa1d` · **Status:** Stable
**Produced by:** PR #13 (`05534af`, matching engine — see Checkpoint 5A) + PR #15 (`0aaaa1d`,
recommendations)
**Full SHA:** `0aaaa1da6fe643b8164df645113322adc889075d` · **CI:** `test` success ·
**Tests:** 850 passing from `main` (0 failed, 0 skipped) · **Mutations:** 5B 40/40 · 5A 36/36 ·
Week 4 27/27

Week 5 as a whole: a deterministic, explainable matching engine and a recommendations endpoint that
puts Week 4 eligibility verdicts and relevance scores side by side — grouped, never combined, and
never able to override eligibility. Checkpoint 5A below records the matching-engine half.

### PR 5B — Recommendations endpoint

#### Added

- **`POST /api/v1/recommendations`** — eligibility verdicts and relevance scores side by side.
  Groups: `ranked` (`ELIGIBLE`, `LIKELY_ELIGIBLE`), `needs_review` (`NEEDS_REVIEW`, `UNKNOWN`),
  `not_eligible` (unranked, no score), `not_open` (requested `CLOSED`/`EXPIRED`, unranked, takes
  precedence; keeps its match score). Ranked groups ordered by `match_score` descending, nulls
  last, then id. Default
  scope ACTIVE + UNKNOWN, at most 50 by `last_verified_at` then id, remainder disclosed in
  `jobs_not_considered`; explicit `job_ids` (1–50) of any status; unknown ids in
  `not_found_job_ids`.
- `app/services/recommendations.py` — orchestrates one Week 4 eligibility pass and one Week 5A
  matching pass over the whole catalogue; embeds each `JobEligibility` unchanged; composes
  explanations from the eligibility summary and the matching explanation.
- `app/schemas/matching.py` — request, response, item and match schemas;
  `MAX_RECOMMENDATION_JOBS = 50`; `MatchScoreBasis.WITHHELD_NOT_ELIGIBLE`.
- `MatchingResult.corpus_fingerprint` — SHA-256 of the catalogue's job ids and matching terms.
- **114 new tests** (850 total) and a 40-mutation run, all caught.

#### Decided

- **ADR-022** recommendation orchestration (C-19..C-22); ADR-020 §5 amended for the fingerprint.

#### Not in this change

- No `/matching/score`, new AI, database change, persistence, frontend, auto-apply or browser
  automation. Week 4 eligibility and the matching algorithm are unchanged.

---

## Checkpoint 5A — Week 5, PR 5A: Deterministic Matching Engine *(intermediate)*

**Date:** 2026-09-17 · **Commit on `main`:** `05534af` · **Status:** Stable — intermediate
**Produced by:** PR #13 (`feature/week-5-matching-engine`, 5 commits)
**Full SHA:** `05534affced482f6bc5e188ac465144dd425f9a7` · **CI:** `test` success ·
**Tests:** 736 passing from `main` (the existing 615 unchanged) · **Mutations:** 36/36 caught

This is **not Checkpoint 5**. Checkpoint 5 is reserved for Week 5 as a whole and follows PR 5B.

#### Added

- **`app/services/matching_engine.py`** — service only, no endpoint. Narrow inputs (candidate
  skills plus experience titles and descriptions; job role title, description and required
  skills), skill comparison by canonical key, a custom tokenizer, TF-IDF fitted on the whole
  catalogue and never on the candidate, cosine similarity reported as a 0–100 score with one
  decimal or `null` when there is nothing to compare, separate skill coverage, the top five
  shared terms, deterministic template explanations and a score/null/job-id ordering key.
  `MATCHING_VERSION` 1.
- `skill_comparison_key` in the candidate normalizer.
- **`scikit-learn==1.7.2`** (approved stack, §9), pinned exactly.
- **121 new tests** (736 total) and a 36-mutation run, all caught.

#### Fixed

- `normalize_skill(".NET")` returned `"NET"`. A dot is now trimmed from the end only, and
  `NET`/`dotnet` canonicalize to `.NET`, so `POST /api/v1/candidates/normalize` returns `.NET`.

#### Decided

- **ADR-020** match scoring · **ADR-021** skill comparison for matching.

#### Not in this change

- No recommendation endpoint, no `/matching/score`, no eligibility, AI or database change.

#### Known limitations

- Service only: no endpoint uses the engine yet.
- Coarse IDF with a 5-job catalogue; scores change when the catalogue changes.
- English stop words only and no stemming; an all-out-of-vocabulary candidate scores `null`.
- Gemini's live calls and model identifier, and PostgreSQL, remain unverified (from Checkpoint 4).

---

## Checkpoint 4 — Week 4: Eligibility Intelligence

**Date:** 2026-09-17 · **Commit on `main`:** `f56d7df` · **Status:** Stable
**Produced by:** PR #9 (`4a5cb84`, deterministic engine — see Checkpoint 4A) + PR #11 (`f56d7df`,
AI-assisted field relatedness)
**Full SHA:** `f56d7dfabeeb8a7addac693d2c7552b0c1fc4e76` · **CI:** `test` success ·
**Tests:** 615 passing from `main` (Weeks 1–3's 328 and PR 4A's 196 unchanged) · **Mutations:** 27/27 caught

Week 4 as a whole: deterministic eligibility with final authority, a typed degree-level
requirement, five-state verdicts, and an AI stage that may only resolve an ambiguous field of
study — failing closed, never producing `NOT_ELIGIBLE`, and never receiving or persisting
candidate data beyond the field string. Checkpoint 4A below records the deterministic half.

### PR 4B — AI-assisted field relatedness

#### Added

- **`AIProvider.assess_field_relatedness(field_of_study, allowed_fields)`** returning a strictly
  validated `FieldRelatednessAssessment` (`RELATED` / `NOT_RELATED` / `UNCERTAIN`, confidence,
  reason). Implemented by the mock — `UNCERTAIN`/LOW by default — and by Gemini through the
  existing httpx transport with a new prompt file.
- **`app/services/eligibility_ai.py`** — the second stage. Consults AI only for a non-exact field
  of study on a job with no verified hard failure; de-duplicates identical questions per request;
  at most 4 concurrent calls. `POST /api/v1/eligibility/check` uses it; the API shape is unchanged.
- **Lazy AI service** (`AIService(builder=...)`, `get_lazy_ai_service`) — requests needing no AI
  never construct a provider.
- Reason codes `AI_FIELD_RELATED`, `AI_FIELD_NOT_RELATED`, `AI_ASSESSMENT_INCONCLUSIVE`,
  `AI_ASSESSMENT_UNAVAILABLE`.
- **91 new tests** (615 total), including literal zero-call and zero-construction assertions and
  captured-request privacy checks. 27 mutations, all caught.

#### Changed

- `ENGINE_VERSION` 1 → 2: an ambiguous field may now resolve to `LIKELY_ELIGIBLE` or
  `NEEDS_REVIEW` with an AI-reasoned entry.

#### Decided

- **ADR-019** AI-assisted field relatedness. **C-14:** empty `allowed_fields` stays omitted.

#### Known limitations

- Gemini's relatedness call has not been exercised against the live service, and the Gemini model
  identifier is unconfirmed.
- The default mock provider stays conservative (`UNCERTAIN`/LOW), so ambiguous fields remain `UNKNOWN`.
- AI "related" judgements are the provider's interpretation; they are labelled `ai_reasoning`,
  capped at MEDIUM, and never make a verdict `ELIGIBLE`.
- PostgreSQL has not been verified; migrations have run on SQLite only.

#### Documentation

- The OpenAPI "Current status" text in `app/main.py`, stale at `f56d7df`, now describes the Week 4
  implementation. Description string only; no behaviour change.

---

## Checkpoint 4A — Week 4, PR 4A: Deterministic Eligibility Engine *(intermediate)*

**Date:** 2026-09-17 · **Commit on `main`:** `4a5cb84` · **Status:** Stable — intermediate
**Produced by:** PR #9 (`feature/week-4-eligibility-engine`, 6 commits)
**Full SHA:** `4a5cb844d1aa4ca4aa3e0906481d0d91c8fc67d4` · **CI:** `test` success ·
**Tests:** 524 passing from `main` (Weeks 1–3's 328 unchanged)

This is **not Checkpoint 4**. Checkpoint 4 is reserved for Week 4 as a whole and follows PR 4B.

#### Added

- **`POST /api/v1/eligibility/check`** — evaluates a supplied profile against up to 50 catalogue
  jobs and returns, per job, a five-state verdict with a per-requirement breakdown and a summary.
  Stateless: the catalogue is read, nothing is written, the profile is not echoed.
- **Deterministic engine** — `app/services/eligibility_engine.py`. `MIN_CGPA` (same scale only),
  `GRAD_YEAR_WINDOW` (inclusive), `MAX_BACKLOGS`, `MIN_DEGREE_LEVEL`, and the exact-match portion
  of `ALLOWED_FIELDS`. Missing or invalid data is `UNKNOWN`, never `FAIL`, never defaulted.
- **`jobs.min_degree_level`** — nullable, typed with `DegreeLevel`; additive migration
  `b3e8d2c61a47` with a CHECK constraint. Two curated jobs now require `BACHELORS`.
- **196 new tests** (524 total; the existing 328 unchanged), mutation-verified against 13
  deliberate breakages.

#### Decided

- **ADR-017** Eligibility states and verdict precedence (C-9, C-13, R-2, R-4)
- **ADR-018** Requirement inputs: same-scale grades, qualification selection, degree level,
  exact-match fields, batch cap (C-10, C-12, A-1, A-2, A-4)

#### Fixed

- The Week 1 `NormalizedGrade` docstring claimed a linear `cgpa / max` fraction made
  cross-scale grade comparison possible. It does not; the docstring is corrected (C-12).

#### Known limitations

- No AI stage yet: a field of study that is not an exact match stays `UNKNOWN`, so such jobs
  resolve to `NEEDS_REVIEW` at best. PR 4B is approved and not started.
- Multi-entry profiles whose education levels were never set resolve per-qualification
  requirements to `UNKNOWN` (ADR-018 accepted cost).
- Free-text `requirements.notes` are disclosed as not evaluated, never interpreted.
- Migration `b3e8d2c61a47` verified on SQLite only.
- QG-002 item 4 (mock provider call count is zero after a hard failure) is deferred to PR 4B: no
  AI call path exists yet. The structural guard is tested and mutation-verified.

---

## Checkpoint 3 — Week 3: Job Schema, Adapters and Ingestion

**Date:** 2026-09-10 · **Commit on `main`:** `2cfd4f0` · **Status:** Stable
**Produced by:** PR #6 (`f538015`, implementation) + PR #7 (`2cfd4f0`, verification repairs)
**Full SHA:** `2cfd4f0276b60de393ec604afc10b3c52f483ca7` · **CI:** `test` success ·
**Tests:** 328 passing from `main` (Weeks 1–2's 203 unchanged)

The checkpoint is at PR #7, not PR #6. At `f538015` the database still accepted
`status='NOT_A_STATE'`, so the four-state job status was a convention rather than a guarantee,
and the failed-ingestion path was untested.

### Added

- **Operational models** — `Job` and `IngestionState`, the first tables in the project
- **Migration `54a85d64881e`** — the entire server-side schema; verified upgrade, downgrade,
  re-upgrade, and upgrade against a database holding data
- **Adapter layer** — `JobSourceAdapter` interface and `CuratedJobAdapter`, with 5 synthetic
  curated jobs
- **Normalization and canonical hashing** — `app/services/job_normalizer.py`, implementing the
  dossier §10.2 deduplication rule over canonicalized fields rather than raw posting text
- **Ingestion** — `app/services/job_ingestion.py`: dedup, upsert, authoritative-disappearance
  handling, and one `ingestion_state` row per source
- **Jobs API** — `GET /api/v1/jobs` and `GET /api/v1/jobs/{id}`, with only the filters Weeks 4–5
  justify
- 115 new tests

### Decided

- **ADR-014** Job status: the dossier's four-state enum is stored, `is_active` is derived
- **ADR-015** `ingestion_state`: one row per source, no run log, no hash ledger (closes D-4)
- **ADR-016** Phase 1 local personal-data store at `~/.eligicore/` — **recorded, not implemented**

### Changed

- Privacy guards moved from "zero tables" to an **allowlist**. The old assertion held only
  because no table existed; an allowlist is stricter, catching a personal-data table under any
  unanticipated name.

### Fixed (PR #7)

- **The four-state job status was not enforced by the database.** SQLAlchemy 2.0 defaults
  `create_constraint=False`, so the enum columns were bare `VARCHAR`. Repair migration
  `7c2f1a9b4d30` adds CHECK constraints; `54a85d64881e` is left byte-identical because amending
  a shipped migration would leave already-migrated databases unconstrained.
- **The failed-ingestion path was untested.** A failed fetch must never be read as "this source
  has no jobs" — otherwise a network blip closes the whole catalogue, silently.

### Known limitations

- `POST /api/v1/jobs/ingest` is in the dossier but not in the approved Week 3 API scope.
  Ingestion is implemented and tested as a service; no trigger endpoint is exposed.
- No PostgreSQL run yet — the migration chain is portable by construction but verified only on
  SQLite. `batch_alter_table` in particular has never run against PostgreSQL.
- CHECK constraints are not autogenerate-detected, so a future enum member added to a model
  will not be caught by `alembic check` and needs a hand-written migration.
- `EXPIRED` and `UNKNOWN` job statuses are modelled but set by no code path.

### Not included

Eligibility, matching, recommendations, application preparation, export, frontend, scraping,
authentication.

---

## Checkpoint 2 — Week 2: Resume Parser and Gemini Flash AI Service Layer

**Date:** 2026-09-10 · **Commit on `main`:** `91dd31d` · **Status:** Stable
**Produced by:** PR #4 (`feature/week-2-resume-ai`, 16 commits), merged 2026-09-10
**Full SHA:** `91dd31d50e7749ad37acf14babd5d1ee90141abd` · **CI:** `test` success ·
**Tests:** 203 passing from `main` (Week 1's 86 unchanged)

### Added

- **AI provider abstraction** — `app/ai/providers/base.py`, plus `errors.py`, `ai_service.py`
  (provider selection and the single point of usage logging), and `prompts/` as files
- **Mock provider** — mandatory and the runtime default, so an unconfigured checkout cannot
  make a paid call. Deterministic, with injectable failure modes.
- **Gemini Flash provider** — the Phase 1 concrete implementation (ADR-013), via the official
  REST API through httpx. The only file that knows Gemini exists.
- **Resume parser** — `app/services/resume_parser.py`: magic-byte format detection, PDF and
  DOCX extraction including table cells, temp-file lifecycle, traceability checking, and
  deterministic confidence rules
- **`POST /api/v1/resumes/parse`** — stateless; the uploaded file is deleted after processing
  on both the success and failure paths
- **QG-008** — quality gate for resume processing and AI extraction
- 117 new tests, none of which make a network call or need an API key

### Decided

- **ADR-013** Google Gemini Flash as the Phase 1 default AI provider, resolving contradiction
  C-4 / decision D-1. Concrete implementation only — ADR-004's abstraction is unchanged.

### Fixed

- **pdfminer logged the literal resume text at DEBUG level.** Found by a privacy test, not by
  inspection: no application log statement was involved, so raising the root log level would
  have dumped candidate data into the logs. Library loggers are now pinned at WARNING with
  propagation disabled.

### Known limitations

- The Gemini provider has **never been executed against the live service** — no API key exists
  in this environment. The default model identifier is a configured default, not a verified one.
- Traceability checking covers skills only; free-text fields are legitimately paraphrased and
  cannot be verified by substring matching.
- The spaCy deterministic fallback is not implemented, so every parse currently makes an AI call.

### Not included

Job ingestion, job adapters, eligibility, matching, recommendations, application preparation,
frontend, authentication, deployment.

---

## Checkpoint 1 — Week 1: Foundation and Candidate Profile Schema

**Date:** 2026-09-10 · **Commit on `main`:** `2e79454` · **Status:** Stable
**Produced by:** PR #2 (`feature/week-1-foundation`, 11 commits), merged 2026-09-10
**Full SHA:** `2e79454f787019ff29af39fcfd285aee59c8bc77` · **CI:** `test` success · **Tests:** 86 passing from `main`

First product implementation phase. A running FastAPI application, the operational database
foundation, the universal candidate profile schema, and two stateless candidate endpoints.

### Added

- **Application foundation** — `app/config.py` (`ELIGICORE_`-prefixed settings via
  pydantic-settings), `app/database.py` (engine, session factory, declarative `Base`),
  `app/main.py` (application, request-context middleware, sanitized error handlers)
- **Candidate profile schema** — `app/schemas/candidate.py`. Multiple education entries, each
  carrying its own `GradeScale`. `UNKNOWN` is a first-class scale value, never inferred.
- **Normalization service** — `app/services/candidate_normalizer.py`. Skill canonicalization,
  scale-independent grade fractions, gap reporting. No web-framework dependency.
- **Endpoints** — `POST /api/v1/candidates/validate`, `POST /api/v1/candidates/normalize`,
  `GET /api/v1/health`
- **Alembic** — environment initialized and wired to application settings. No migration, because
  Week 1 creates no tables.
- **Tests** — 86, including 9 privacy tests. The unknown-scale rule and the PII-echo guard were
  mutation-verified: deliberately breaking each makes the relevant tests fail.
- **CI** — GitHub Actions: install → import check → no-personal-data-table guard →
  `alembic check` → `pytest`. Runs with no credentials configured.
- **Repository** — `.gitattributes`, `.env.example`, `requirements.txt`, `pytest.ini`

### Privacy

- No `candidates`, `applications` or `evaluations` table exists or is registered, verified by test
- The 422 handler drops Pydantic's `input` and `ctx`, which would otherwise echo submitted
  candidate values back to the caller
- Request logs carry request id, method, path, status and duration only

### Fixed

- `GradeScale` validator moved to `mode="before"` so an explicit `"scale": null` resolves to
  `UNKNOWN` instead of raising a 422. Semantically identical to omitting the field.

### Not included

Resume parsing, AI providers, job ingestion, eligibility evaluation, matching, application
preparation, frontend, authentication, deployment.

---

## Checkpoint 0 — Phase 0: Engineering environment initialized

**Date:** 2026-09-10 · **Commit on `main`:** `e8c68b7` · **Status:** Stable
Built over two commits (`7f7abbb`, then `e8c68b7`). The checkpoint is the end state,
`e8c68b7` — a single commit, not the range. CI and tests read n/a: neither existed yet,
because Phase 0 contained no product code.

The AgentOS engineering layer, the repository standard, and the two architectural contradiction
rulings. **No product code.**

### Added

- `AGENTOS.md` — engineering layer entry point, authority hierarchy, session protocol
- `context/` — vision, state, architecture, tech stack, decisions, workflow, memory
- `standards/` — eligibility, security & privacy, AI, API design, code quality, testing
- `reviewers/` — architect, api, security, ai, qa, performance, documentation, release
- `checklists/` — quality gates QG-001 through QG-007
- `artifacts/decisions/` — ADR-001 through ADR-012
- `.agentos/config.yml` — reviewer routing, context loading, the 12 architectural invariants
- `.gitignore` — secrets, personal data, databases, caches
- `README.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `LICENSE`

### Decided

- **ADR-001** Local-first personal data — the backend is a processing service, not a
  personal-data store
- **ADR-002** Stateless candidate APIs — no server-held candidate record
- **ADR-003** Deterministic eligibility precedence — AI never overrides a verified hard failure
- **ADR-004** AI provider abstraction
- **ADR-005** Pluggable job-source adapters
- **ADR-006** Explainable eligibility and matching
- **ADR-007** Truthfulness validation
- **ADR-008** No auto-submit in current scope
- **ADR-009** Database strategy — SQLite → PostgreSQL via SQLAlchemy and Alembic
- **ADR-010** API versioning under `/api/v1/`
- **ADR-011** No server-side candidate or application persistence — **ruling on dossier
  contradiction C-1**; the §8.2 folder listing showing `models/candidate.py` and
  `models/application.py` is stale and those models must not exist
- **ADR-012** `ingestion_state` as an operational model — **ruling on dossier contradiction
  C-2**; ingestion state is legitimate server-side operational data, bounded to adapter run
  history and never holding a `candidate_id`

### Known open questions

- **C-3** — dossier §12.3 refers to a "stored candidate profile"; stale wording under
  local-first. Low impact, relevant at Week 7.
- **C-4 / D-1** — which AI provider is the Phase 1 default. Needed before Week 2.
- **D-4** — whether `ingestion_state` needs its own deduplication-hash ledger given
  `jobs.content_hash`. Deferred to Week 3.
