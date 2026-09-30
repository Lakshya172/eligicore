# ADR-029 — Explicit Unknown Employment Type

**Status:** Accepted · **Date:** 2026-09-30 · **Type:** Design ruling (architectural gate)
**Source:** dossier §10.2, §11, §12.1, §13 · ADR-028 D9
**Decided by:** project owner, architectural decision gate opened by the PR #50 blocker
**Enforces:** INV-1, INV-3, INV-4, INV-12 · **Refines:** ADR-005, ADR-010, ADR-014, ADR-028
**Supersedes:** nothing — **no earlier ADR is amended or superseded**
**Rules on:** D1–D16 · **Owner decisions:** OD-1 … OD-4 **all resolved 2026-09-30** (see § Owner decisions)

---

## Context

PR #50 — the Greenhouse public Job Board adapter, the first concrete live source authorized by
ADR-028 D5 — **stopped before implementation** on a contract collision.

`RawJob.job_type` is **required** and typed `JobType`, whose only members are `INTERNSHIP` and
`FULL_TIME`. The Greenhouse Job Board API publishes **no employment-type field at all.** Verified
against Greenhouse's own published API schema, a list-jobs record carries exactly `id`,
`internal_job_id`, `title`, `updated_at`, `requisition_id`, `location.name`, `absolute_url`,
`language`, `metadata`, plus `content`, `departments` and `offices` under `content=true`. The
single-job endpoint adds `company_name`, `first_published` and `application_deadline`. Employment
type appears in neither.

So the adapter had exactly three options, and ADR-028 forbids all three: infer the type from the
title or description, fabricate one, or change the schema. **ADR-028 D9 is the rule that makes this
a real blocker rather than an inconvenience:** *"Missing eligibility criteria stay missing … No
requirement may be invented, inferred, defaulted or AI-extracted into existence."* `job_type` is
currently the one field in the job contract that refuses to let a source say nothing.

**This is not a Greenhouse problem.** Lever publishes `categories.commitment` and would satisfy
`job_type`, but publishes no company name; Ashby must be assessed separately. Any source that omits
employment type hits the same wall. Resolving it unblocks the ATS category, not one adapter.

### What the repository actually does with `job_type` today

Inspected before drafting, because the answer changes the ruling substantially:

| Location | Use |
|---|---|
| `app/models/job.py:91` | `Mapped[JobType]`, `SAEnum(native_enum=False, length=20, create_constraint=True)`, `nullable=False`; indexed `ix_jobs_job_type` |
| `app/schemas/job.py:64,112,147` | required on `RawJob`, `NormalizedJob`, `JobRead` |
| `app/schemas/candidate.py:222` | `CandidatePreferences.job_types: list[JobType]` |
| `app/routers/jobs.py:98,113` | the `GET /api/v1/jobs?job_type=` filter — `Job.job_type == job_type`, exact match |
| `app/services/job_normalizer.py:192` | verbatim passthrough |
| `app/services/job_ingestion.py:44` | listed in `_UPDATABLE_FIELDS` |
| `alembic/54a85d64881e` | column created as VARCHAR(20), `NOT NULL`, **no constraint** |
| `alembic/7c2f1a9b4d30` | CHECK `jobtype`: `job_type IN ('INTERNSHIP', 'FULL_TIME')`, via `batch_alter_table` |

**`job_type` appears zero times in `eligibility_engine.py`, `eligibility_ai.py`,
`matching_engine.py` and `recommendations.py`.** It is not an eligibility criterion, not a hard
constraint, and not a scoring input. It is a catalogue filter and a declared preference.

**`CandidatePreferences.job_types` is consumed nowhere in `app/`.** It is validated, echoed by
`/candidates/validate` and `/candidates/normalize`, and read by no service. **There is no
server-side preference filtering by employment type today.** Any "preference matrix" is therefore a
forward-looking ruling for a filter that does not yet exist, not a description of current
behaviour — and this ADR says so rather than implying the code already does something it does not.

### The precedent this decision follows

ADR-014 already faced this exact question for job *status* and answered it:

> `UNKNOWN` in particular carries the same semantics INV-3 depends on everywhere else in this
> system — absence of evidence is not evidence of a specific state.

`JobStatus` has carried `UNKNOWN` as a first-class member since Week 3. `DegreeLevel` carries both
`UNKNOWN` *and* nullability, and `RawJob.min_degree_level`'s docstring draws the distinction
precisely: *"Null when the posting states none — which means no requirement, not an unknown one."*

That distinction is the key to this ruling. For degree level, "no requirement" and "unknown
requirement" are genuinely different facts. **For employment type they are not:** every job *is*
some employment type. There is no such thing as a posting with no employment type. The only fact a
source can fail to supply is *which one* — which is exactly what `UNKNOWN` means and exactly what
`None` would fail to mean.

---

## Decision

### Domain semantics

**D1 — Add `JobType.UNKNOWN`.**

**D2 — `UNKNOWN` means exactly one thing: *the source did not explicitly provide the employment
type.*** **Approved by the owner as OD-4.**

It does **not** mean, and must never be read, stored, filtered or rendered as meaning:

- unrestricted, or "any employment type"
- `INTERNSHIP`, or `FULL_TIME`, or a value that may be resolved to either
- an employment type that was inferred, guessed or defaulted
- **evidence of eligibility**, or evidence of anything else about a candidate's fit
- eligible for, or matching, every employment preference
- **a wildcard in a candidate's stated preference** (D15, OD-2)
- a data-quality defect to be cleaned up by assigning a real type later

`UNKNOWN` is a **statement about EligiCore's knowledge**, not about the job. A job whose type is
`UNKNOWN` has a real employment type in the world; this system has not been told it. Anything that
converts `UNKNOWN` into `INTERNSHIP` or `FULL_TIME` without the source saying so is fabrication
under ADR-028 D9 and ADR-007, whoever writes it and whatever the justification.

**D3 — No inference, ever.** No adapter, service, migration, backfill or AI call may derive
employment type from a job title, description, department, office, URL, board token or any other
prose or metadata. Deriving it from a source field that *explicitly states* employment type — such
as Lever's `categories.commitment` — is not inference and is permitted.

### Contract shape

**D4 — `RawJob.job_type: JobType = JobType.UNKNOWN`. Optional is rejected.**

The field stays non-nullable at every layer and gains a default, so an adapter that cannot supply a
type omits the field rather than passing a sentinel. Reasons, in order of weight:

1. **`None` and `UNKNOWN` would mean the same thing here, so having both is a defect.** As set out
   in Context, employment type has no "not applicable" case. `min_degree_level` needs both because
   "no degree requirement" is a real state; `job_type` has no analogue. Two spellings of one fact
   is how inconsistent data gets written — some adapters would send `None`, others `UNKNOWN`, and
   every consumer would need `if x is None or x is UNKNOWN`.
2. **It keeps the column `NOT NULL`.** `Optional` forces a nullable `jobs.job_type`, which is a
   heavier migration, weakens the schema, and makes the index sparser.
3. **It matches the repository's own precedent.** `JobStatus.UNKNOWN` (ADR-014) models exactly this
   and is non-nullable.
4. **It keeps the domain three-valued rather than four-valued.** Every consumer handles three
   enum members; nothing handles an absent value.

**D5 — Propagation is verbatim and lossless.** `RawJob.job_type` → `NormalizedJob.job_type` →
`Job.job_type` → `JobRead.job_type`, non-null at every layer, carried unchanged. **The normalizer
must not translate, default or "repair" `UNKNOWN`.** `job_normalizer.normalize_job` already does a
verbatim passthrough (`job_type=raw.job_type`) and must keep doing so.

### Eligibility, matching and recommendation

**D6 — `job_type` is not an eligibility criterion, and must not become one in this work.**
Verified: zero occurrences across the eligibility engine, the AI stage, the matching engine and
recommendations. The requirement that *"`UNKNOWN` must never cause an employment-type hard
failure"* is therefore **already satisfied structurally** — there is no code path by which any
`job_type` value can produce a verdict. This ADR's job is to **preserve** that, not to implement
it.

Concretely: `UNKNOWN` cannot produce `NOT_ELIGIBLE`, cannot contribute to a hard-constraint
failure, and cannot alter a verdict or a confidence level. A candidate evaluated against an
`UNKNOWN`-type job receives exactly the verdict the job's actual eligibility criteria produce.

**D7 — `job_type` is not a matching or ranking input, and `UNKNOWN` must not become a scoring
penalty.** Match scoring is TF-IDF over text (ADR-020, ADR-021) and does not read `job_type`.
Introducing `UNKNOWN` must not silently down-rank a job for the sole reason that its source was
less forthcoming — that would punish the candidate for a gap in the data.

### Preference and catalogue filtering

**D8 — `GET /api/v1/jobs?job_type=` keeps exact-match semantics, unchanged.** A filter naming a
known type returns **only** jobs of that known type. `?job_type=INTERNSHIP` returns internships and
nothing else; `?job_type=FULL_TIME` returns full-time roles and nothing else. **Neither ever
returns an unknown-type job.** The existing implementation — `Job.job_type == job_type` — stands
exactly as merged, and the published meaning of both filters is untouched.

**D9 — The default, unfiltered listing surfaces unknown-type jobs; explicit typed filters do
not.** **OD-1 is resolved: surface, do not silently hide** — and that surfacing is scoped to the
**default listing**, where a client has expressed no type constraint. `GET /api/v1/jobs` with no
`job_type` parameter returns internships, full-time roles and unknown-type jobs together, each
carrying its own `job_type` so a client can see exactly what it is being given.

A client that wants unknown-type jobs specifically asks for them with **`?job_type=UNKNOWN`**,
which returns only those. That, plus the default listing, covers both needs without touching the
two existing filters.

**No new query parameter is introduced.** An earlier draft proposed an `include_unknown_type`
toggle to widen typed filters; it is rejected. It would have changed what `?job_type=INTERNSHIP`
means, which ADR-010 classes as breaking, in exchange for a capability the default listing and
`?job_type=UNKNOWN` already provide. Keeping the API surface as it is was the better answer, and
it is also the simpler one — the jobs router's filters are described as *"deliberately minimal"*
and stay that way.

**The complete deterministic matrix.** Rows are the filter the client sends; columns are the stored
job type:

| Client filter | `INTERNSHIP` job | `FULL_TIME` job | `UNKNOWN` job |
|---|---|---|---|
| **no `job_type` parameter** | returned | returned | **returned** |
| `?job_type=INTERNSHIP` | returned | excluded | **excluded** |
| `?job_type=FULL_TIME` | excluded | returned | **excluded** |
| `?job_type=UNKNOWN` | excluded | excluded | **returned** |

Every cell is exact match, with the single exception of the unfiltered row, which returns
everything. In every cell where an `UNKNOWN` job is returned it is returned **as `UNKNOWN`** — never
relabelled, never folded into another type, and never omitted from the response body's `job_type`
field.

**D10 — Any future server-side preference filtering inherits this matrix.** When
`CandidatePreferences.job_types` is eventually consumed — it is consumed by nothing today — an
`UNKNOWN` job must never be treated as satisfying a stated preference, and must never be treated as
a hard exclusion either. It is a third outcome: *shown, marked uncertain.* This mirrors how the
eligibility engine already treats missing data as `NEEDS_REVIEW` rather than `FAIL` (INV-3).

**D15 — `UNKNOWN` is not a valid candidate preference, and is rejected deterministically.**
**OD-2 is resolved.** `UNKNOWN` describes what EligiCore was told about a *job*; it is meaningless
as a statement of what a *person* wants. A client sending
`preferences.job_types: ["UNKNOWN"]` must receive a **deterministic validation failure** — the
same 422 shape every other invalid profile value produces — and must never have it silently
accepted, dropped, or treated as a wildcard matching every job.

Two mechanisms satisfy this and the implementation gate picks between them; both must produce the
same observable outcome, so this is a means, not a further decision:

* a field validator on `CandidatePreferences.job_types` rejecting `UNKNOWN`. Smallest change, and
  keeps the single shared enum that `app/schemas/job.py` deliberately reuses — but the published
  OpenAPI schema would still advertise three values for a field that accepts two, so the
  description must state the restriction.
* a separate preference-side enum holding only the two real types. The published schema is then
  self-describing, at the cost of the second enum `app/schemas/job.py` warns will drift.

The first is expected to be preferable for exactly the reason that comment gives; the
documentation gap it leaves is the thing the implementation gate must not forget.

### Persistence

**D11 — The existing 40 curated jobs are untouched.** Every curated posting states its type and
keeps it. **No existing row is converted to `UNKNOWN`, and no backfill runs.** `UNKNOWN` exists for
genuinely missing source data arriving from live adapters. `tests/test_curated_catalogue.py`'s
assertion that the catalogue holds at least 10 of each real type remains true and must stay
asserted.

**D12 — One new migration, widening the CHECK constraint.** The column is already
`VARCHAR(20) NOT NULL`, so `'UNKNOWN'` (7 characters) needs no type change. The work is to replace
the `jobtype` CHECK created by `7c2f1a9b4d30` with a three-value predicate. Details in § Migration
implications.

### Sources

**D13 — Greenhouse maps `job_type = UNKNOWN`,** with no inference from title, description,
department or office, unblocking PR #50.

**D14 — A source that explicitly publishes employment type must use it.** `UNKNOWN` is the honest
answer when a source is silent, never a shortcut past a field the source does supply. Lever's
`categories.commitment` is a stated value and must be mapped, subject to its own gate.

---

## Alternatives considered

**`Optional[JobType]` / nullable column.** Rejected — see D4. It creates two spellings of one fact
in a domain with no "not applicable" case, forces a nullable column, and diverges from the
`JobStatus.UNKNOWN` precedent. It would be the right answer for a field like `min_degree_level`,
where absence and ignorance are genuinely different; it is the wrong answer here.

**Keep the enum at two members and have Greenhouse pick one per board.** Rejected. It asserts a
value Greenhouse never published, and is simply wrong for any board carrying both internships and
graduate roles. Because `job_type` feeds the catalogue filter, a wrong value silently removes real
jobs from a candidate's view — the failure mode ADR-028 D9 exists to prevent.

**Keep the enum at two members and skip jobs whose type is unknown.** Rejected. Every Greenhouse
job would be skipped, so the adapter would ingest nothing, and the "live source" would be a source
of zero jobs presented as a successful run.

**Infer the type from the title or description.** Rejected — ADR-028 D9, ADR-007, and D3 above. A
title is prose. "Intern" appears in "Internal Audit Manager"; "Graduate" appears in both graduate
schemes and senior roles. A wrong confident answer is worse than an honest unknown.

**Use AI to extract employment type from the description.** Rejected, and specifically so, because
it is the most plausible-sounding option. ADR-019 authorizes AI to answer exactly one eligibility
question — field-of-study relatedness. Employment-type extraction is a second one, with the failure
mode being a fabricated attribute presented as verified. Reopening this needs its own ADR.

**Start with Lever instead, since it publishes `categories.commitment`.** Rejected as a solution,
though noted as a real observation. It trades this blocker for the company-name one: Lever
publishes no company name and has no board-name endpoint. Fixing `job_type` properly unblocks all
three ATS sources; reordering unblocks none of them cleanly.

---

## Persistence and API impact

**Model.** `app/models/job.py` gains the member through the shared `JobType` enum; the column stays
`SAEnum(JobType, native_enum=False, length=20, create_constraint=True)`, `nullable=False`. Because
`create_constraint=True` is already set, SQLAlchemy's own generated constraint widens with the
enum — but the *database's* constraint is the one created by migration `7c2f1a9b4d30`, and only a
migration changes that.

**API.** **The existing `INTERNSHIP` and `FULL_TIME` filter semantics are unchanged (D8), so
nothing about this change is breaking for them.** A client filtering by either known type receives
exactly what it received before; the only way to see an unknown-type job is to omit the filter or
to ask for `?job_type=UNKNOWN` explicitly. The change is therefore a pure enum widening, which
ADR-010 classes as additive.

`JobType` is published in OpenAPI as
`{"type": "string", "enum": ["INTERNSHIP", "FULL_TIME"]}` and is referenced by **two** schemas:

- **`JobRead`** — a **response** widening. Additive under ADR-010: *"Adding a state is additive;
  changing what one means is breaking."*
- **`CandidatePreferences`** — a **request** widening, and the one genuinely awkward consequence of
  reusing a single enum for both sides. A client could otherwise send `job_types: ["UNKNOWN"]`,
  which reads as "I prefer jobs whose type nobody told us" and is meaningless as a preference.
  **OD-2 resolves this: it is rejected with a deterministic validation error (D15)**, never
  accepted as a wildcard. Note that `app/schemas/job.py` deliberately reuses this enum, with the
  comment *"A second JobType with the same members would drift from this one the first time either
  changed."* — so if the implementation keeps the shared enum and enforces D15 with a validator,
  the published schema will advertise a value the endpoint refuses, and the field's description
  must say so.

**Existing test exposure.** `tests/test_tracker_export_endpoint.py` pins 58 OpenAPI **schema
names**, not enum values, and pins enum values only for `ApplicationStatus` — so adding a `JobType`
member does not break it. `tests/test_jobs_endpoints.py::test_schema_and_model_status_enums_agree`
compares `JobStatusSchema` against `JobStatus` and does not touch `JobType`, which is a single
shared enum with no mirror to keep in step.

---

## Migration implications

**Exact work.** A new revision on head `b3e8d2c61a47` that drops the `jobtype` CHECK and recreates
it as `job_type IN ('INTERNSHIP', 'FULL_TIME', 'UNKNOWN')`, following `7c2f1a9b4d30`'s existing
pattern exactly — `batch_alter_table`, a module-level tuple of literals, and the `_in_clause`
helper's approach.

**Existing rows.** Unaffected. The change is a strict widening: every value that satisfied the old
predicate satisfies the new one. No data migration, no backfill, no rewrite (D11).

**SQLite.** `batch_alter_table` recreates the table — create new, copy rows, drop old, rename —
because SQLite cannot `ALTER TABLE ... DROP CONSTRAINT`. Indexes (`ix_jobs_job_type`,
`ix_jobs_status`, `ix_jobs_source`, `ix_jobs_content_hash`) and the
`uq_jobs_source_source_job_id` unique constraint must survive the recreation; `7c2f1a9b4d30` and
`b3e8d2c61a47` already exercise this path and are the templates.

**PostgreSQL parity.** Batch mode falls through to plain `ALTER TABLE ... DROP CONSTRAINT` /
`ADD CONSTRAINT`. Note that `ADD CONSTRAINT` **validates existing rows** on PostgreSQL. For the
upgrade this is safe (strict widening). For the downgrade it is not — see below. Week 9A-2
validated the existing three-migration chain against PostgreSQL 18.6 by execution; **this migration
has not been, and the implementation gate must run the same upgrade → data → downgrade → re-upgrade
→ `alembic check` sequence against PostgreSQL before it is considered done.**

**Downgrade — the one genuine hazard, and it must be addressed explicitly.**

Narrowing the CHECK back to two values **fails, or corrupts, if any row holds `'UNKNOWN'`:**

- **PostgreSQL:** `ADD CONSTRAINT` validates existing rows and raises on the first `UNKNOWN` row.
  The downgrade aborts. Loud, and recoverable.
- **SQLite:** `batch_alter_table` copies rows into a new table that carries the narrowed CHECK. The
  copy violates it. Depending on how the constraint is applied during recreation this either
  raises or — the worse case — leaves a table whose contents contradict its own constraint.

This is not hypothetical: the entire purpose of this ADR is to put `UNKNOWN` rows in that column.

**D16 — the downgrade fails safely. OD-3 is resolved.**

The downgrade must **detect `UNKNOWN` rows before attempting to narrow the constraint** and abort
with a clear, actionable message naming the count of offending rows — never the rows' contents. It
must **not delete them, not convert them, and not reinterpret them**. Deleting contradicts
ADR-006 and ADR-014's "jobs are closed, never deleted"; converting is fabrication under D2 and D3;
and either would mean a rollback silently changed what the catalogue asserts about real postings.

Failing loudly is also the only option that leaves the operator's choices intact: once the rows are
gone or rewritten, the information is unrecoverable, whereas an aborted downgrade loses nothing and
tells the operator precisely what to resolve first.

**The downgrade must be tested with `UNKNOWN` rows actually present**, on both SQLite and
PostgreSQL, asserting that it aborts, that the message carries a count rather than data, and that
**every row is still present and unmodified afterwards**. A downgrade tested only on an empty
database is not a tested rollback path, and the recovery ladder in `context/workflow.md` exists
precisely for the moment when it is needed. The empty-database case must also be tested, and must
succeed.

---

## Security and privacy impact

**None.** This changes one enum member on a job posting — public, non-personal operational data
(dossier §10.2). It introduces:

- no candidate-data persistence: the server-side table set remains exactly `jobs` and
  `ingestion_state` (INV-1, ADR-011)
- no new personal-data field, and no field correlating a job to a candidate
- no new logging surface — `job_type` is not logged, and `UNKNOWN` carries no information about
  anyone
- no new outbound data flow, no new credential, no AI involvement

`CandidatePreferences.job_types` remains client-side data echoed by a stateless endpoint and
persisted nowhere (ADR-002, ADR-016).

---

## Testing implications

Designed here; **implemented at the implementation gate, not now.** Everything runs offline against
mocked transport.

**Enum and serialization** — `UNKNOWN` is a member of `JobType`; it serializes as the string
`"UNKNOWN"`; the OpenAPI `JobType` enum lists exactly three values; the 58 pinned schema names are
unchanged.

**Persistence** — a job with `job_type=UNKNOWN` round-trips through create, read and update; the
CHECK constraint **accepts** `'UNKNOWN'` after the migration; the constraint still **rejects** a
value outside the three members (the guarantee `7c2f1a9b4d30` exists to provide, which a widening
must not quietly drop); the index still covers the column.

**Migration** — upgrade on a populated database preserves every row and its type; `alembic check`
is clean; **downgrade with `UNKNOWN` rows present aborts, leaves every row unmodified, and reports
a count rather than data (D16)** — this is the test that matters most, and it must run on both
SQLite and PostgreSQL; downgrade on a database with no `UNKNOWN` rows succeeds.

**Existing types unaffected** — the 40 curated jobs still carry their real types after the
migration; the catalogue still holds ≥10 of each; no row changed type.

**Eligibility** — a candidate evaluated against an `UNKNOWN`-type job gets the same verdict, reason
breakdown and confidence as against an otherwise identical typed job; **`UNKNOWN` never appears in
a reason, never produces `NOT_ELIGIBLE`, and never triggers an AI call it would not otherwise
trigger.** An AST or import-level guard asserting that the eligibility engine does not reference
`job_type` at all is the strongest available form of this test (D6).

**Matching and recommendation** — match scores for an `UNKNOWN`-type job are identical to those for
the same job with a real type; ranking position is unchanged; `UNKNOWN` is not a penalty (D7).

**Filter matrix** — all twelve cells of the D9 table asserted explicitly. The three that matter
most are the exclusions: **`?job_type=INTERNSHIP` must not return an `UNKNOWN`-type job**,
**`?job_type=FULL_TIME` must not either**, and **`?job_type=UNKNOWN` must return only those**.
Also asserted: the unfiltered listing returns all three types, and a returned `UNKNOWN` job is
reported **as** `UNKNOWN` in the response body rather than relabelled.

**Preference rejection (D15)** — `preferences.job_types: ["UNKNOWN"]` returns a deterministic
validation failure; `["INTERNSHIP", "UNKNOWN"]` is rejected too rather than silently filtered down
to the valid member; the two real types still validate; and the rejection is asserted through the
public endpoints, not only at the model, so the observable contract is what is pinned.

**API** — `JobRead.job_type` serializes `UNKNOWN`; `?job_type=UNKNOWN` filters to exactly those
jobs; an invalid `job_type` value is still rejected with 422.

**Greenhouse mapping** — a Greenhouse fixture maps to `job_type=UNKNOWN`; **a fixture whose title
contains "Intern" and whose description contains "internship" still maps to `UNKNOWN`.** That
negative test is the direct, executable statement of D3 and is worth more than the positive one.

---

## Implementation sequencing

Neither is authorized by this ADR; each needs its own gate.

| PR | Objective | Migration |
|---|---|---|
| **A** | `JobType.UNKNOWN` — enum, `RawJob` default, model, API contract (**no new query parameter**), the migration widening the CHECK, and the D16 downgrade behaviour, with the full test set above including PostgreSQL execution | **Yes** |
| **B** | Greenhouse adapter (the blocked PR #50), mapping `job_type=UNKNOWN` | No |

PR A must leave the suite green and the 40 curated jobs byte-identical in type. PR B then lands as
originally scoped, with the board-name lookup supplying `company_name`.

---

## Consequences

**Positive.** Live ATS sources become representable without fabricating an attribute. The blocker
is resolved for Greenhouse, Lever and Ashby at once rather than per adapter. `job_type` joins
`status` and `min_degree_level` in being able to say "not known", which is what the rest of the
system already does everywhere else (INV-3). The system gains the ability to be honest about a gap
instead of silently filling it.

**Negative, recorded rather than minimised.**

- **A three-valued `job_type` is more to reason about** than two, for every future consumer.
- **`UNKNOWN` is visible in the `CandidatePreferences` schema but invalid as a value** (D15). The
  published enum and the accepted values diverge unless the implementation splits the enum, and
  that divergence has to be documented rather than left for a client to discover by 422.
- **Unknown-type jobs are invisible to a client that always filters by a known type** (D8, D9).
  That is the deliberate cost of keeping the existing filters exact: such a client sees them only
  by dropping the filter or asking for `?job_type=UNKNOWN`. **The existing `INTERNSHIP` and
  `FULL_TIME` filters keep their meaning, so nothing here is a breaking change to them.**
- **The downgrade path becomes conditional** on the data present, and will now refuse outright once
  any live unknown-type job has been ingested (D16). That is the correct behaviour and it still
  makes rollback harder than it was.
- **Candidates will see jobs whose type is unknown**, which is a worse experience than knowing —
  but a better one than not seeing real, open jobs at all, and an honest one.
- **A future temptation to "clean up" `UNKNOWN` rows** by backfilling a guessed type. D2 and D3
  exist to be cited when that is proposed.

---

## Revisit conditions

Revisit if: a chosen source begins publishing employment type, making `UNKNOWN` rare enough to
reconsider the filter default · the proportion of `UNKNOWN` jobs makes the catalogue less useful
rather than more · server-side preference filtering is implemented and D10's ruling proves wrong in
practice · a second field develops the same "source is silent" problem, suggesting a general
pattern rather than three one-off enum members.

---

## Owner decisions

**All four are resolved. Decided by the project owner at this gate on 2026-09-30.**

| # | Decision | Resolution |
|---|---|---|
| **OD-1** | Filter default on `GET /api/v1/jobs` | **SURFACE, in the default listing.** With no `job_type` parameter, unknown-type jobs are returned rather than silently hidden and are **visibly labelled `UNKNOWN`**. **This does not alter the existing explicit type filters:** `?job_type=INTERNSHIP` and `?job_type=FULL_TIME` remain exact and never include `UNKNOWN`, which is queried explicitly with `?job_type=UNKNOWN`. No new query parameter (D8, D9). |
| **OD-2** | `UNKNOWN` in `CandidatePreferences.job_types` | **REJECT.** `UNKNOWN` is **not** a valid candidate employment-type preference. A client sending it receives a **deterministic validation error**, never a wildcard and never a silent drop (D15). |
| **OD-3** | Downgrade when `UNKNOWN` rows exist | **FAIL SAFELY.** The downgrade detects `UNKNOWN` rows and aborts. It must **not** delete, convert or reinterpret them. The downgrade test must include existing `UNKNOWN` rows (D16). |
| **OD-4** | The core semantics in D2 | **APPROVED.** `JobType.UNKNOWN` is the explicit representation of missing source employment-type information, and nothing else. |

**No further owner decision is created by this ADR.** ADR-028's seven open decisions and Week 9B's
seven remain open and untouched.

---

## Enforcement

Every PR in this sequence is checked against this ADR at review: no inference of employment type
from prose (D3), no `Optional[JobType]` (D4), no normalizer translation of `UNKNOWN` (D5), no
`job_type` reference introduced into the eligibility or matching engines (D6, D7), **an explicit
`?job_type=INTERNSHIP` or `?job_type=FULL_TIME` filter that returns an `UNKNOWN`-type job** (D8),
no new query parameter widening those filters (D9), the unfiltered listing still returning all
three types (D9), `UNKNOWN` rejected as a candidate preference (D15), no curated row converted
(D11), and a downgrade that aborts with every row intact, tested with `UNKNOWN` rows actually
present (D16).
