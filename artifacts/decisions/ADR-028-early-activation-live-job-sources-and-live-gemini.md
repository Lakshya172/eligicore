# ADR-028 — Early Activation of Live Job Sources and Live Gemini

**Status:** Accepted · **Date:** 2026-09-30 · **Type:** Design ruling (live-data transition gate)
**Source:** dossier §6, §9.3, §10.2, §12.1, §15, §16, §18 (Phase 3)
**Decided by:** project owner, live-data transition design gate
**Enforces:** INV-1, INV-3, INV-4, INV-5, INV-7, INV-10, INV-12
**Refines:** ADR-005, ADR-013, ADR-014, ADR-015
**Supersedes in part:** dossier §6 ("does not scrape live portals in Phase 1") and §18 Phase 3
sequencing (see § Roadmap deviation) — **no earlier ADR is amended or superseded**
**Rules on:** D1–D22 · **Leaves open:** OD-1 … OD-7

---

## Context

EligiCore is at **Checkpoint 9A** (`95a1187715851ee7a67fa8cdbc7c6e87f3fa7ec3`), with `main` at
`e5a2f6ea17b1f43c3da2b456d09a9027e8d0cae6`, 1567 tests passing and Alembic head `b3e8d2c61a47`.
Everything downstream of job data is built, tested and merged: the eligibility engine with its
per-requirement breakdowns, the matching engine, recommendations, application preparation with
truthfulness validation, and the Excel tracker export.

**Two things upstream of all that are still synthetic.** The catalogue is 40 curated jobs read from
a JSON file, and the AI provider default is `mock` — **no live Gemini request has ever been made
from this project.** The system is therefore complete and correct against data that nobody actually
applies to.

The dossier anticipated this exact moment. §9.3 states the purpose of the adapter pattern plainly:
*"The hardest unsolved problem (real data acquisition) is isolated behind a stable boundary."* §16
rates *"Job data acquisition at scale is legally and technically hard"* as High severity, mitigated
by *"Phase 1 uses manually curated data. The adapter boundary isolates this problem so it can be
solved independently without touching the rest of the system."*

That isolation held. A design-gate inspection of the merged implementation found the adapter
boundary and the ingestion pipeline already fit for live data without interface change:

- `JobSourceAdapter` is two members plus `fetch()` — `source_name`, `is_authoritative`.
- `is_authoritative` **defaults to `False`**, with the docstring recording why: a paginated live API
  returning page one must not be read as evidence that the rest of the catalogue is closed.
- `AdapterError`'s docstring already anticipates live sources — *"a future live source's error body
  could quote the content it was fetching"* — and requires sanitized messages.
- `job_ingestion` already matches on `(source, source_job_id)` first and `content_hash` second,
  scoped within source; collapses duplicates inside one fetch; isolates per-adapter failures in
  `ingest_all`; closes rather than deletes; and writes one `ingestion_state` row per source.
- `job_normalizer.compute_content_hash` already hashes the canonicalized field set from §10.2 —
  never raw posting text.

**One gap was found.** `JobStatus.EXPIRED` is defined and documented as *"the stated deadline has
passed"*, but **nothing in the codebase ever assigns it**, and `deadline` is stored and exported
without ever being compared against the current date. With 40 curated jobs this is inert. With live
data, where freshness is the main thing being bought, it is a correctness gap. D14 and D15 below
rule on the semantics; the threshold work is deferred to the next gate.

---

## Roadmap deviation

**This ADR authorizes live job sources earlier than the dossier sequences them, and records that as
a deviation rather than reinterpreting the dossier into agreement.**

The dossier says two things that this decision moves past:

- **§6:** *"It does not scrape live portals in Phase 1. The initial dataset is manually curated."*
- **§18, Phase 3:** *"Live job sources. Real adapters for portals and ATS platforms, built within
  Terms of Service constraints. The adapter interface already accommodates this."*

The 10-week roadmap in §15 contains no live-source week: Week 9 is documentation and deployment,
Week 10 is buffer. Live sources were always a *later phase*, not a *later week*.

**What changes is sequencing. What does not change is architecture.** The dossier did not defer live
sources because the design could not support them — it deferred them because data acquisition is the
hardest unsolved problem and everything else needed to be built and validated first. That
precondition is now met. The dossier's own sentence — *"The adapter interface already accommodates
this"* — is the justification for the sequence moving, and the design-gate inspection confirmed it
empirically: no interface change is required.

**The dossier is not modified.** As with ADR-027's local-first revision, the deviation lives here so
that a later reader finds a recorded decision rather than a roadmap phase quietly reordered.

**Note on §6's wording.** §6's stated objection is to *scraping* live portals. Nothing authorized
here is scraping: D5 selects only sources that publish a sanctioned, documented, machine-readable
feed, and D6 excludes scraping and scraping intermediaries by name. The deviation is therefore
narrower than §6's sentence suggests — but it is still a deviation from "the initial dataset is
manually curated", and is recorded as one rather than argued away.

---

## Decision

### Catalogue model

**D1 — The curated catalogue is retained, not replaced.** The 40-job curated/synthetic catalogue
remains a first-class source. It is the only source that reliably carries structured hard
requirements (CGPA, permitted fields, backlog limits, graduation-year windows), and it is what the
deterministic eligibility test suite evaluates against. Removing it would delete the project's
regression baseline.

**D2 — The target is a hybrid catalogue.** Live sources are added *alongside* the curated one. Both
populate the same `jobs` table through the same ingestion pipeline. Nothing downstream distinguishes
them beyond the `source` column that already exists.

**D3 — Every job stays attributed to its originating source.** `source` and, where the source
supplies one, `source_job_id` are recorded on every row and already exposed on `JobRead`.

**D4 — No cross-source deduplication at ingestion time.** The same posting reachable through two
sources is legitimately two rows with two apply links, and collapsing them would discard one —
possibly the canonical employer URL. This confirms the behaviour `job_ingestion.find_existing_job`
already implements: matching is scoped within a single source. Presentation-level grouping, if ever
wanted, is a separate concern and is not authorized here.

### Source selection

**D5 — The initial live implementation targets are ATS public job-board feeds:**

| Source | Basis |
|---|---|
| **Greenhouse** public job-board feeds | Board data is public; read endpoints require no authentication. Only application submission requires credentials, and EligiCore never calls it. |
| **Lever** public postings | Every Lever customer exposes a public postings endpoint; no authentication for reads. |
| **Ashby** public job-posting feeds | Same category of sanctioned public board feed. |

These are chosen because they are **sanctioned, documented, unauthenticated for reads, and return
the employer's own canonical application URL** rather than an aggregator redirect — which matters
directly for the human-submission boundary in D18. They are per-company rather than per-market: an
operator supplies the board identifiers.

**Their known weakness is recorded rather than glossed:** ATS feeds publish requirements as
free-text, so structured eligibility fields will frequently be absent. D9 rules on what happens
then. OD-6 keeps the broader consequence open.

**D6 — Excluded, and not to be reintroduced without a new decision:** generic web scraping ·
LinkedIn · Internshala · Naukri · Unstop · Indeed · JSearch · SerpApi · Apify actors or any
equivalent scraping intermediary. A paid intermediary whose data is obtained by scraping does not
launder the underlying Terms-of-Service problem; it relocates it. This exclusion is on principle,
not on price.

**D7 — Adzuna is not selected for the initial implementation, and is not rejected.** Its
integration, attribution and licensing requirements need further verification and do not fit the
current headless, local-first architecture cleanly: its terms require a rendered, pixel-sized
attribution badge with a hyperlinked logo, which a backend-only API has no surface to display, and
commercial/government/academic use is governed by a separately negotiated licence. **Adzuna remains
a legitimate future option contingent on a separate legal/ToS decision** (OD-7). Nothing here
forecloses it.

**D8 — Every future source requires its own validation before implementation**, covering technical
access, authentication, rate limits, Terms of Service, and whether an official application URL is
preserved. Adding a source is never a matter of writing an adapter and switching it on. This applies
to the three sources named in D5 as well: D5 records the direction, and the per-source technical and
ToS confirmation happens at the implementation gate for that adapter.

### Data fidelity

**D9 — Missing eligibility criteria stay missing.** A live job with no published CGPA cutoff, branch
restriction, backlog limit or graduation-year window is ingested with those fields `None`, and the
existing evaluation semantics apply unchanged: the verdict falls to `UNKNOWN` / `NEEDS_REVIEW` with
its reason exposed. **No requirement may be invented, inferred, defaulted or AI-extracted into
existence.** This is ADR-007's no-fabrication rule applied to the job side of the ledger, and it is
the single most important constraint in this ADR: a fabricated eligibility criterion is worse than
an absent one, because it produces a confident wrong answer instead of an honest unknown.

**D10 — A deadline is never inferred.** A source that publishes no deadline yields `deadline=None`.
Not "30 days from posting", not "end of quarter", not any other convention. This confirms the
existing normalizer behaviour, whose docstring already states *"an absent deadline stays absent"*.

**D11 — Every adapter preserves, where the source supplies it:** `source` · `source_job_id` ·
company · role/title · location · job type · description · requirements · official application URL ·
explicit deadline · posted/updated timestamps · source provenance. Where the source does not supply
a field, it is absent — D9 and D10 govern.

> **Clarification, added 2026-10-02 (D11a).** `source_job_id` holds the source's own
> identifier **at the scope the source itself addresses it**. Where a source namespaces its
> identifiers, the stored value is the stable source-qualified form, not the bare id.
>
> **Greenhouse must use `board_token + ":" + job_post_id`.** Every documented Greenhouse
> endpoint addresses a post through its board — `/v1/boards/{board_token}/jobs/{id}` — and
> Greenhouse nowhere guarantees that `id` is unique across boards. Storing the bare id was
> an undocumented assumption, and it failed silently: two employers whose boards share a
> post id resolved to one `(source, source_job_id)`, so ingestion collapsed or overwrote
> one and a real job disappeared with no error. Confirmed against the real pipeline before
> the correction.
>
> This changes no contract. `source` stays `"greenhouse"` for every board, so ADR-015's one
> `ingestion_state` row per source and the `?source=` filter are untouched, and
> `(source, source_job_id)` remains the identity. No schema change and no migration follow
> from it — the existing column and unique constraint already express it.
>
> A source whose ids are genuinely global keeps using the bare id. The rule is to match the
> source's documented scope, not to qualify for its own sake.

### Adapter contract

**D12 — `JobSourceAdapter` remains unchanged.** The interface is not modified unless a later
implementation gate demonstrates a concrete compatibility problem, which must then be recorded
rather than worked around. The design-gate inspection found no such problem.

**D13 — One new source is one new adapter class.** This is the dossier's own §9.3 and §17
Engineering criterion — *"New job source addable by writing one class"* — and it is the test of
whether this transition was done correctly. Shared HTTP infrastructure (client, timeouts, bounded
retries, rate limiting, pagination, sanitized error translation) **may** be introduced later as its
own implementation PR; it is a convenience for adapter authors, not a change to the contract.

### Job lifecycle

**D14 — Live adapters are non-authoritative unless explicitly proven otherwise.** They keep
`is_authoritative = False`. A job absent from one live fetch is **not** evidence the posting is
gone — it may be a page boundary, a filter, a rate-limited window or a transient failure.
Consequently `_close_disappeared` does nothing for them, which is the intended safe behaviour.

**D15 — A missing job must not immediately close an existing job**, and **jobs are never deleted as
part of normal ingestion.** A closed posting stays retrievable with its status explaining why
(ADR-006, ADR-014).

**D16 — A passed explicit deadline may be represented as `EXPIRED`.** This closes the gap identified
in Context: the status exists and is documented but is never assigned. Whether expiry is computed at
ingest or derived at read is an implementation-gate question, not settled here.

**D17 — Stale-job closure semantics are deferred.** A non-authoritative source's jobs would
otherwise accumulate indefinitely, so a closure rule is needed — but **no numeric threshold and no
algorithm is chosen in this ADR.** It must be defined explicitly at the next implementation gate
(OD-1). Implementing closure before the rule is agreed is prohibited.

### AI

**D18 — Live Gemini is approved as the next AI runtime direction; implementation is a separate PR.**
Nothing in this ADR changes runtime behaviour. The provider default remains `mock`.

**D19 — The target model identifier is `gemini-2.5-flash`**, as Google's currently documented stable
model, decided by the owner at this gate. This resolves the identifier question ADR-013 § Unverified
left open and supersedes nothing: ADR-013's finding that `gemini-2.0-flash` was *"a configured
default, not a verified one"* stands as the record of what was true then. **The configured default
in `app/config.py` is still `gemini-2.0-flash` and is deliberately not changed by this
documentation-only ADR** — updating it belongs to the live-enablement PR.

**D20 — The provider abstraction and the mock default are preserved.** `AIProvider` stays the only
thing the service layer knows about (INV-5). The mock provider **remains the default for tests and
for any unconfigured environment**, so an unconfigured checkout and CI can never make a paid call by
accident. This property is not a convenience; it is what makes the first live call safe.

**D21 — The first live Gemini request is a controlled, owner-performed smoke test**, never an
automated CI call. No test, fixture, hook or scheduled job may issue a live request.

**D22 — Deterministic eligibility authority is unchanged.** A verified hard-constraint failure
yields `NOT_ELIGIBLE` with **zero AI calls and zero provider construction**. AI remains confined to
the single already-approved question — field-of-study relatedness on an exact-match miss with no
hard failure (ADR-019) — capped at MEDIUM confidence, never producing `ELIGIBLE` or `NOT_ELIGIBLE`.
Live inference does not widen this by one field. Dossier §12.1 and §17 (*"No AI-reasoned verdict
overrides a verified deterministic hard-constraint failure"*) are restated here because live AI is
exactly the circumstance under which such a rule erodes.

---

## Application flow

The target real-world flow, with the boundary made explicit:

```
[LOCAL DEVICE]   resume / profile              stored only on the user's device
        │
        ▼
[ELIGICORE]      curated catalogue + live sources   ingested with no candidate present
        │
        ▼        deterministic eligibility     hard failure → NOT_ELIGIBLE, zero AI calls
        │
        ▼        AI, only for permitted ambiguity   field relatedness, capped MEDIUM
        │
        ▼        recommendations → application preparation → truthfulness validation
        │
        ▼        official apply URL returned
        │
[HUMAN]          opens the external employer/ATS page
                 reviews, edits, fills, uploads
                 ── SUBMITS ──
        │
[LOCAL DEVICE]   tracker records the outcome, locally
```

**EligiCore does not** open a browser · authenticate as the user · fill external forms
automatically · bypass CAPTCHA · bypass OTP · bypass anti-bot controls · bypass identity
verification · click submit.

**The human remains responsible for the final submission decision and the submission action.** Live
job data changes where the URL came from. It does not move this boundary by one step (ADR-008,
INV-10, dossier §6).

---

## Alternatives considered

**Replace the curated catalogue with live sources.** Rejected. The curated set is the only source
carrying structured hard requirements and is the deterministic test suite's baseline; replacing it
would delete the regression evidence for the project's central capability while simultaneously
reducing eligibility signal. D1 keeps both.

**Deduplicate across sources at ingestion.** Rejected. Two sources listing one posting give two
apply links, and only one may be the employer's canonical page. Collapsing them silently discards
information that D11 exists to preserve.

**Start with an aggregator (Adzuna) for breadth.** Deferred, not rejected (D7). Breadth including
India is genuinely attractive, and the ATS-feed choice pays for canonical URLs and clean terms with
a curated company list. The blocking issue is the rendered-attribution requirement against a
headless architecture, which is a licensing judgement rather than an engineering one (OD-7).

**Use a scraping intermediary (JSearch, SerpApi, Apify).** Rejected outright (D6). It would obtain
data from sources whose terms prohibit automated access, with a vendor in between. The dossier's §6
reasoning about Terms of Service applies to the data's origin, not to who performed the request.

**AI-extract structured eligibility criteria from free-text descriptions.** Rejected here, and it is
the most tempting alternative because it would close the gap D9 leaves open. It is rejected because
ADR-019 authorizes AI to answer exactly one eligibility question, and extracting a CGPA cutoff from
prose is a second one — with the failure mode being a fabricated hard constraint applied as though
it were verified. Reopening this needs its own ADR, not an implementation decision (OD-6).

**Change `JobSourceAdapter` pre-emptively to suit live sources.** Rejected (D12). The inspection
found no required change, and widening an interface for a hypothetical need is how a boundary starts
leaking the shape of whichever source was implemented first — the precise failure `base_adapter.py`
was written to avoid.

---

## Consequences

**Positive.** The system becomes genuinely useful: real, currently-open postings with real
application URLs. The dossier's central architectural bet — that data acquisition could be solved
later behind a stable boundary — is validated by an integration that requires no interface change.
The `EXPIRED` gap is put on a path to closure.

**Negative, and recorded rather than minimised.**

- **Eligibility signal per job will fall.** ATS feeds rarely publish structured criteria, so many
  live jobs will evaluate to `UNKNOWN` / `NEEDS_REVIEW`. The product will hold more jobs it can say
  less about. D9 makes this honest rather than hidden, but it does not make it go away (OD-6).
- **Catalogue growth changes matching behaviour.** TF-IDF IDF weights are catalogue-dependent; going
  from 40 jobs to a larger live set will change every match score. Not a defect, but the Week 8
  corpus cache and the recommendation expectations will need re-examination at the relevant gate.
- **A curated company list is itself a curation burden** — smaller than curating jobs, but not zero.
- **Untrusted third-party text enters the database.** See § Security and privacy impact.
- **Live AI introduces real cost and real latency**, neither yet measured.

---

## Security and privacy impact

**Live job ingestion introduces no candidate-specific server persistence.** Ingestion takes no
candidate parameter — structurally, not by convention: no function in `app/services/job_ingestion.py`
accepts one, and `ingestion_state` holds no user identifier. Live sources change where `RawJob`
originates and nothing else.

**The server must not persist** resumes · candidate profiles · evaluations · application history ·
notes · chat history · AI memory or context · any other user-specific personal information (INV-1,
ADR-001, ADR-011, ADR-016, dossier §8.1a, §10.2). Live data does not create an exception.

**Live job responses must never be written to raw debug files or logs.** Parse, normalize, discard.
Ingestion logging stays at counts, source name, status category and timing.

**API credentials must never appear in a URL, a response body, a log line, an exception message, or
`ingestion_state.last_error`.** Several job APIs invite key-in-query-string; that is prohibited here,
as it already is for the Gemini key, which travels as a header. Adapter errors must be sanitized
*before* the exception escapes, because 9A-6 established that uvicorn writes its own tracebacks to
stderr.

**New risk — untrusted description text becomes an active surface.** A live job description is
third-party-influenceable in a way a curated file is not, and it already reaches the AI provider
during application generation. ADR-025 anticipated this: the job description is passed as a
**labelled data block, never as instructions**. That mitigation moves from precautionary to
load-bearing and must be re-verified with adversarial fixtures at the relevant gate.

**Ingestion must remain candidate-free.** A future "search live jobs for this candidate" call would
send candidate-derived terms to a third party and correlate a request to a person. Nothing here
authorizes that; it would need its own privacy decision.

**What reaches Gemini is unchanged by this ADR:** field relatedness sends exactly a field-of-study
string and the job's permitted-fields list, enforced by the method signature; extraction sends
resume text, unavoidably; generation remains unimplemented (see Non-goals).

---

## Operational impact

**No runtime behaviour changes on merge of this ADR.** No source is enabled, no key is configured,
the provider default remains `mock`, and the catalogue remains the 40 curated jobs.

**Later, when adapters land:** ingestion gains outbound network dependence and therefore new failure
modes — timeout, rate limit, quota exhaustion, partial fetch. `ingest_all` already isolates
per-adapter failure, so one source failing must not stop the others. Sources that impose persistent
quotas may require durable accounting, but only if the chosen sources actually impose them (OD-3).

**No migration is required by this ADR.** Later lifecycle and provenance work may require one; that
is assessed at its own gate. No dependency is added.

**Trigger surface is unchanged.** Ingestion remains CLI-only. `POST /api/v1/jobs/ingest` stays
deferred (ADR-024, C-25); whether it is ever needed is OD-5.

---

## Explicit non-goals

Not authorized by this ADR, and not to be inferred from it:

- Implementing any live adapter, including for the three sources named in D5
- Implementing `LiveHTTPAdapter` or any shared HTTP infrastructure
- Making any live Gemini request
- Changing the configured Gemini model default, or any other configuration value
- Implementing live Gemini **application generation** — still a deliberate stub, and enabling it
  reopens ADR-026 D8's *structural* exclusion of generation from cost accounting, which requires its
  own privacy decision (OD-4)
- Creating an HTTP refresh/ingest endpoint
- Creating a scheduler, cron entry or background job
- Adding Adzuna or any source outside D5
- Any scraping, browser automation, CAPTCHA/OTP/anti-bot handling or identity-verification bypass
- Auto-submission of an application, in any form
- Deployment, hosting or sharing — Week 9B remains optional, owner-triggered and unstarted
- Modifying `EligiCore_Dossier_update.md`
- Choosing a stale-job threshold
- Any new server-side persistence of personal data

---

## Testing and quality gates

**All existing tests must be green before and after every subsequent implementation PR.** The suite
stands at **1567 passing** at `main` `e5a2f6e`; no implementation PR in this sequence may reduce that
or leave it red.

**The offline default must remain safe and deterministic.** The full suite must continue to pass
with **no API key configured and no network access**. Any test that would issue a live request to a
job source or to an AI provider is prohibited (D21). Live sources are exercised through
`httpx.MockTransport` against captured, sanitized payloads — the pattern the Gemini tests already
use.

QG-001, QG-003, QG-005, QG-006 and QG-008 apply per slice as usual. QG-007 remains relevant only if
Week 9B is ever activated.

---

## Owner decisions still open

Recorded as open. **None may be chosen implicitly by an implementation PR.**

| # | Decision |
|---|---|
| **OD-1** | **Exact stale-job threshold and closure algorithm** — how many consecutive unseen runs, measured how, and what status results (D17). |
| **OD-2** | **Refresh cadence** — how often ingestion runs, and what happens to a run that partially fails. |
| **OD-3** | **Quota/rate-limit persistence design** — whether durable accounting is needed at all, and where it lives if so. Required only if a chosen source imposes a persistent quota. |
| **OD-4** | **Live Gemini application generation and its cost accounting** — reopens ADR-026 D8's structural exclusion; needs its own privacy decision. |
| **OD-5** | **Whether an authenticated or shared-instance ingestion endpoint is ever needed** — reopens ADR-024's C-25 deferral. |
| **OD-6** | **Response to the structured-eligibility gap** — accept mostly-`None` live requirements, rely on the curated tier for structured evaluation, or authorize something new. AI extraction of criteria is **not** authorized (see Alternatives). |
| **OD-7** | **Adzuna's attribution and licensing terms** — a separate legal/ToS decision before it could ever be adopted (D7). |

Week 9B's seven deployment decisions (ADR-027) remain separately open and are untouched by this ADR.

---

## Implementation sequencing

The intended order after this ADR. **None is authorized by it**; each needs its own gate.

| PR | Objective | Migration |
|---|---|---|
| **1** | `LiveHTTPAdapter` infrastructure — offline-testable, **no concrete source** | No |
| **2** | First concrete live source adapter | No |
| **3** | Source configuration and credential handling | No |
| **4** | Freshness / expiry / lifecycle improvements | Likely |
| **5** | Persistent quota and rate-limit accounting — **only if required by the chosen sources** | Likely |
| **6** | Refresh CLI command | No |
| **7** | Adversarial job-description hardening | No |
| **8** | Live Gemini enablement | No |
| **9** | **Verification-only** real end-to-end run | No |

Each PR must leave the suite green, must leave the offline default safe, and must not enable a live
source or a live provider by default.

---

## Revisit conditions

Revisit this ADR if: a D5 source withdraws or restricts its public feed · a source's Terms of
Service change materially · the structured-eligibility gap (OD-6) proves severe enough to change the
catalogue strategy · live AI cost or latency proves unacceptable · Week 9B is activated and hosted
operation changes the ingestion or credential model.

---

## Enforcement

Every subsequent PR in this sequence is checked against this ADR at review: no invented requirement
or deadline (D9, D10), no cross-source dedup (D4), no interface change without a recorded
compatibility problem (D12), non-authoritative live adapters (D14), no deletion (D15), no threshold
chosen without an owner decision (D17), mock default preserved (D20), no automated live call (D21),
and deterministic authority intact (D22).
