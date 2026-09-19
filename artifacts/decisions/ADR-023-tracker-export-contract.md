# ADR-023 — Tracker export contract

**Status:** Accepted · **Date:** 2026-09-19 · **Type:** Design ruling (Week 6 design gate, PR 6A)
**Source:** dossier §7 step 7 and question 6, §9 (openpyxl), §10.1 `evaluations`, §11 Applications, §15 Week 6, §17
**Decided by:** project owner, Week 6 design gate
**Enforces:** INV-1, INV-4, INV-7, INV-12 · **Refines:** ADR-001, ADR-002, ADR-010, ADR-011, ADR-016, ADR-022
**Rules on:** C-23, C-24, C-25, C-28, C-29, A-27..A-33, A-35, A-36

---

## Context

Dossier §11: `POST /api/v1/applications/export` — *"Generate an Excel tracker from tracking
records supplied by the client and return the file."* Dossier §7 answers question 6, *"Did I
already apply?"*, with the tracker and the Excel export. Dossier §15 puts the export in Week 6,
the declared safe stopping point.

Application tracking data is client-owned (§8.1a, §10.1, ADR-001, ADR-011). There is no
application-status endpoint (ADR-002) and no `applications` or `evaluations` table (ADR-011).
The export therefore cannot read tracking data from the server: the client must send it.

## Decision

### 1. A renderer, not a tracking service (A-27)

`app/services/tracker_export.py` is a pure function: **`TrackerRecord[]` → `.xlsx` bytes**.

The client supplies complete rows — typically copied from the `/recommendations` or
`/eligibility/check` responses it already holds, plus its own application status and notes. The
export does **not**:

- read the job catalogue or any other table — the router has no database dependency;
- recalculate eligibility or match scores, or call recommendations, matching or AI;
- enrich, correct or reconcile a record against the catalogue;
- store, cache or write anything, including temporary files.

What the client sends is what the workbook says. A stale row stays stale; that is the client's
record, not the server's.

### 2. Request contract

`TrackerExportRequest` — `{records: TrackerRecord[]}`, `extra="forbid"` at every level.

| Field | Type | Rule |
|---|---|---|
| `job_id` | string | 1–100 characters; unique within the request |
| `company_name` | string | ≤ 200 |
| `role_title` | string | ≤ 200 |
| `apply_link` | string \| null | ≤ 2048; plain text, never a hyperlink |
| `deadline` | date \| null | written as an Excel date |
| `job_status` | `JobStatusSchema` \| null | existing enum, reused |
| `eligibility_state` | `EligibilityState` \| null | existing enum, reused |
| `match_score` | number 0–100 \| null | **null stays null** (§4) |
| `reason` | string \| null | ≤ 1000 |
| `application_status` | `ApplicationStatus` | default `NOT_APPLIED` |
| `evaluated_at` | timezone-aware datetime \| null | converted to UTC; a naive time is rejected |
| `notes` | string \| null | ≤ 1000; never logged |
| `requirement_breakdown` | `RequirementResult[]` \| null | existing schema, reused; ≤ 20 entries, each text ≤ 1000 |

- **`MAX_TRACKER_ROWS = 500`.** 0 or 501 records → 422.
- **A duplicate `job_id` → 422** (A-31). A tracker has one row per job; silently keeping the first
  or last copy would discard the client's data without telling it.
- Control characters that cannot be stored in a worksheet (everything below U+0020 except tab,
  line feed and carriage return) → 422, rather than a 500 from the spreadsheet library.
- All 422s use the standard error envelope and never echo a submitted value (INV-4).

### 3. `ApplicationStatus` (A-28)

Exactly the five values of dossier §10.1: `NOT_APPLIED`, `APPLIED`, `INTERVIEW`, `REJECTED`,
`OFFER`. It is a schema enum — a data contract for data in flight — not a model, and no status is
stored anywhere on the server. Add values, never rename or remove them (ADR-010).

### 4. Nullable `match_score` (C-24)

Dossier §10.1 lists `match_score` as a 0–100 float. ADR-020 and ADR-022 — later and more specific —
define a null score: `NO_JOB_TERMS`, `NO_CANDIDATE_TERMS`, `WITHHELD_NOT_ELIGIBLE`. **Null is not
zero.** A null score is an **empty cell**, never `0`. The reason, when the client has one, travels
in `reason`. Week 5A score semantics are unchanged.

### 5. Workbook

**Sheet `Tracker`** — one row per record, **in request order**, under a fixed header:

`Row` · `Job ID` · `Company` · `Role` · `Job Status` · `Eligibility` · `Match Score` ·
`Application Status` · `Deadline` · `Apply Link` · `Reason` · `Evaluated At (UTC)` · `Notes`

`Row` is the 1-based record position. `Deadline` is an Excel date; `Evaluated At (UTC)` an Excel
datetime in UTC (Excel has no time zones). `Match Score` is numeric or empty.

**Sheet `Requirements`** (A-29) — present **only** when at least one record carries a non-empty
`requirement_breakdown`. One row per requirement, in record order then breakdown order:

`Tracker Row` · `Job ID` · `Requirement Type` · `Requirement` · `Candidate Value` · `Status` ·
`Confidence` · `Method` · `Reason Code` · `Note`

`Tracker Row` and `Job ID` tie each requirement to its parent row. `Candidate Value` is the value
the requirement was compared against, as in the eligibility response — part of the explanation,
not identity.

Header row bold and frozen; fixed column widths. No comments, hidden cells, defined names,
formulas, hyperlinks, images or macros.

### 6. Formula-injection defence (A-32)

Every text cell — every field the client controls, and for uniformity every other string — goes
through one writer:

1. If the value starts with `=`, `+`, `-`, `@`, tab or carriage return, it is **prefixed with an
   apostrophe** (`=1+1` → `'=1+1`). The value stays readable, and the leading apostrophe is the
   convention spreadsheet users recognise for "this is text".
2. The cell's type is set **explicitly to string**. openpyxl otherwise treats a string starting
   with `=` as a formula; the explicit type is the second, independent guard.

Tests reopen the file, check every cell's type and value, and scan the sheet XML for `<f>`
elements. `apply_link` is plain text: no hyperlink object and no hyperlink relationship is
written.

### 7. Metadata, filename, identity (A-30, A-33)

- Workbook properties are fixed: creator and last-modified-by `EligiCore`, title
  `EligiCore application tracker`. No candidate name, e-mail, phone, `candidate_id` or notes
  anywhere in the properties.
- The request has **no candidate field at all**, so no candidate identity can reach the workbook.
- Filename fixed: `eligicore-tracker.xlsx` — no candidate data, no timestamp.
- The file format embeds creation and modification times, so raw bytes differ between runs.
  Determinism is asserted on the **reopened content**, not on bytes.

### 8. Binary response — the API-standard exception (C-23)

`standards/api_design.md` §3 and QG-004 item 3 require a Pydantic response model on every route.
The dossier requires this endpoint to *return the file*. **This endpoint is the recorded
exception:**

- **200** — the workbook bytes; `Content-Type:
  application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`;
  `Content-Disposition: attachment; filename="eligicore-tracker.xlsx"`; `Cache-Control: no-store`;
  `X-Request-ID` from the existing middleware. Documented in OpenAPI as a binary string of that
  media type.
- **The request stays a Pydantic model**, and **every error stays the standard JSON envelope**
  (422 validation, 405 for `GET`, 500 generic). The exception covers the successful body only.
- A base64 JSON wrapper was rejected: it inflates the file by a third and makes every client
  decode before it can save.

No other endpoint may cite this exception; a future binary response needs its own ruling.

### 9. Privacy

- Stateless. No model, table, migration, cache or file. The router takes no database session.
- One log line, counts only: `tracker_export rows=… requirement_rows=… bytes=… duration_ms=…`.
  Never job ids, companies, roles, links, reasons, notes, requirement text, scores or any
  candidate value.
- `Cache-Control: no-store`, because the body is the user's own tracking data.

### 10. Relationship to Week 6

PR 6A delivers this export. PR 6B (polish: catalogue expansion to 30–50 synthetic jobs, a local
setup and demo command, a README quickstart, a full-flow test) follows after Checkpoint 6A. The
Week 6 checkpoint is a checkpoint, **not a release, tag or version** (C-28).

PR 6A also corrects the stale OpenAPI status text in `app/main.py`, which still described Week 5 as
in progress (C-29).

### 11. Deferred, explicitly (C-25)

- **`POST /api/v1/matching/score`** — dossier §11, deferred to future matching work.
- **`POST /api/v1/jobs/ingest`** — HTTP ingestion stays deferred; an unauthenticated write trigger
  is an abuse surface. PR 6B's local command covers setup.

Neither gets a stub route. Week 6 is not a reason to reopen either.

## Consequences

**Positive.** Question 6 of the dossier gets its answer without the server learning anything:
tracking stays on the device, the export is a pure function, and a workbook cannot execute
anything a client typed.

**Negative / accepted.** One endpoint departs from the JSON response convention. The server
cannot vouch for what a row says — a client can export a stale or edited verdict. Adds one pinned
dependency (`openpyxl`, with `et-xmlfile`).

## Enforcement

`tests/test_tracker_export.py` (schema, workbook, formula injection, metadata, import boundary) ·
`tests/test_tracker_export_endpoint.py` (contract, error envelope, OpenAPI, privacy) · QG-004 ·
QG-005 · `reviewers/security.md`
