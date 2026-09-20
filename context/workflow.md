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
| **6** | Week 6 — MVP (final: PR 6A + PR 6B) | `13eb832` | PR #17 (`0125703`) + PR #19 (`feature/week-6-polish`), merged 2026-09-20 | ✅ `test` success on `13eb832` | 1133 passed | **Stable — current** |

**Checkpoint 1 full SHA:** `2e79454f787019ff29af39fcfd285aee59c8bc77`
**Checkpoint 2 full SHA:** `91dd31d50e7749ad37acf14babd5d1ee90141abd`
**Checkpoint 3 full SHA:** `2cfd4f0276b60de393ec604afc10b3c52f483ca7`
**Checkpoint 4A full SHA:** `4a5cb844d1aa4ca4aa3e0906481d0d91c8fc67d4`
**Checkpoint 4 full SHA:** `f56d7dfabeeb8a7addac693d2c7552b0c1fc4e76`
**Checkpoint 5A full SHA:** `05534affced482f6bc5e188ac465144dd425f9a7`
**Checkpoint 5 full SHA:** `0aaaa1da6fe643b8164df645113322adc889075d`
**Checkpoint 6A full SHA:** `0125703ad9464216b1622c14941664ec32ac9bac`
**Checkpoint 6 full SHA:** `13eb8325149cab60a039534631265803250b767a`

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
| **1st** | Checkpoint 6 — Week 6 MVP (final) | `13eb832` | **Current stable point.** If Week 7 introduces a regression, this is the immediate rollback reference. |
| **2nd** | Checkpoint 6A — Week 6 Excel Export (intermediate) | `0125703` | The export without the demo path. Reached by reverting the PR #19 merge; no database step. |
| **3rd** | Checkpoint 5 — Week 5 Matching Engine (final) | `0aaaa1d` | Last state before any Week 6 code. Reached by also reverting the PR #17 merge; no database step (`openpyxl` and `et-xmlfile` leave `requirements.txt` with it). |
| **4th** | Checkpoint 5A — Week 5 deterministic matching engine | `05534af` | Matching engine without the recommendations endpoint. Reached by also reverting the PR #15 merge; no database step. |
| **5th** | Checkpoint 4 — Week 4 Eligibility Intelligence | `f56d7df` | Last state before any matching code. Reached by also reverting the PR #13 merge; no database step (scikit-learn leaves `requirements.txt` with it). |
| **6th** | Checkpoint 4A — Week 4 deterministic engine | `4a5cb84` | Deterministic eligibility without the AI stage. Reached by also reverting the PR #11 merge; no database step. |
| **7th** | Checkpoint 3 — Week 3 | `2cfd4f0` | Last state before any eligibility code. |
| **8th** | Checkpoint 2 — Week 2 | `91dd31d` | Known-good state before the job catalogue. |
| **9th** | Checkpoint 1 — Week 1 | `2e79454` | Remains available indefinitely as a historical recovery point. |
| **10th** | Checkpoint 0 — Phase 0 | `e8c68b7` | Engineering layer only, no product code. |

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
