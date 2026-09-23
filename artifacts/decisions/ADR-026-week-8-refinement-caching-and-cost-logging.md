# ADR-026 — Week 8 refinement, caching and cost logging

**Status:** Accepted · **Date:** 2026-09-23 · **Type:** Design ruling (Week 8 design gate)
**Source:** dossier §9, §9.2, §10.2, §15 (Week 8), §16
**Decided by:** project owner, Week 8 design gate and one revision round
**Enforces:** INV-1, INV-4, INV-5, INV-7 · **Refines:** ADR-004, ADR-013, ADR-019, ADR-022
**Supersedes in part:** ADR-020 §5 (see § Relationship to merged decisions)
**Rules on:** W8-A, W8-B, W8-C, W8-D, W8-E, W8-F, W8-G, W8-H

---

## Context

Dossier §15 gives Week 8 one row: focus *"Refinement, caching, cost logging"*, deliverable
*"Polished, cost-aware system"*. That is the only statement in the dossier that scopes Week 8, and
two of its three words were undefined when the design gate opened.

Three further sections supply the substance. §10.2 lists what operational logs hold —
*"Request counts, AI usage and cost logging, and error records. Kept for system operation and
diagnostics, not as a record of any individual's profile or applications."* §9.2 fixes where that
happens — *"Cost and usage logging happens in one place."* §16 gives the reason — the AI-cost risk
is mitigated because *"Rules run before AI; results are cached; usage is logged."*
`standards/ai.md` §7 restates both obligations, and **QG-003 item 9 has been unmet since Week 2**:
`AIService` logs provider, model, operation, outcome, duration and an input count, but no token
count and no cost anywhere in the repository.

**Live Gemini application generation is not a dossier Week 8 requirement.** The dossier never names
it; the string "Week 8" appears in it exactly once, in the roadmap row above. The deferral comes
from ADR-025 § Deferred, which said *"Week 8/9"* and deliberately left the week open. It is
resolved here as deferred (D10), not assumed in.

Week 7 is closed at Checkpoint 7 (`6c269a05ec1a4fdbdc7820d0c6b0b40980ba8fb3`); this ADR is
recorded before any Week 8 implementation exists.

## Decision

**D1 — Week 8 is exactly three slices.** Slice 8A (cost and usage accounting), Slice 8B
(candidate-free corpus vectorizer cache) and Slice 8C (operational-log completeness). Nothing else
is Week 8 work. Every slice is **behaviour-preserving**: no endpoint, route, schema, contract,
verdict, score or response body changes, and every existing response stays byte-identical.

**D2 — Cost accounting covers two AI operations only (W8-F).** Slice 8A instruments
`extract_resume` and `assess_field_relatedness`. `generate_application_content` is excluded — see
D8. These two are the AI paths that are live-capable today.

**D3 — Usage is reported through a per-call sink, not a return type (W8-F, ADR-004).** `AIService`
passes each provider call a per-call usage sink the provider may write to. No abstract method is
added, no provider return type changes, and the ADR-004 abstraction is untouched: a provider that
cannot report usage remains valid and logs `unknown`. A provider attribute such as `last_usage` is
**rejected** — `eligibility_ai` already fans assessments out through `asyncio.gather`, so shared
mutable provider state would race and mis-attribute cost on exactly the path this slice covers.

**D4 — Retried calls accumulate usage (W8-F).** A Gemini call that fails twice and succeeds on the
third attempt consumed tokens three times. Usage accumulates across attempts so cost is not
under-reported on the expensive path. Accumulation changes no retry behaviour, no retry cap and no
request outcome.

**D5 — Pricing is configuration, and unknown means unknown (W8-H).** Provider and model rates are
`ELIGICORE_`-prefixed configuration. **No external provider price is hard-coded**: published
pricing is a third-party fact that changes, and a stale constant in source would be a fabricated
figure presented as a measurement. An unknown provider or model, a missing rate, or absent, partial
or malformed usage yields `cost=unknown` and `tokens=unknown`, each degrading independently. Cost
is held in integer micro-units, because an accounting figure must not carry float drift.

**D6 — Accounting never changes an AI outcome (W8-F).** Any failure in usage extraction, cost
lookup or arithmetic logs `unknown` and is otherwise inert. An accounting defect must not be able
to turn a working AI call into an error; that would invert the value of the feature.

**D7 — The cache holds corpus-derived matching artifacts only (W8-A).** Slice 8B caches the fitted
vectorizer, the job matrix, the feature names and the catalogue row mapping — every one of them
derived from the catalogue alone. The key is the existing `corpus_fingerprint`, which is an exact
determinant rather than a heuristic: it hashes `[job_id, job_terms(job)]` for each catalogue job in
the order given, precisely the inputs that decide the fit and the row mapping, so equal fingerprint
means identical fitted state. A catalogue change produces a different fingerprint and a miss.

**The candidate is never cached.** `vectorizer.transform(candidate_terms(...))` stays per-request,
outside the cache, every time. **The fit is cached; the candidate's transform is not.** That single
boundary is the whole privacy argument for Slice 8B, and ADR-020's rule that the candidate is
transformed and never fitted is preserved exactly.

The cache is a **process-local, bounded, in-memory LRU**. No Redis, no disk, no external cache
service, no new dependency, and — consistent with ADR-025 D4's posture — **no cache configuration
key**: the bound is a module constant, so there is no setting whose default could later be widened
into a policy change. Output must be identical cold, warm and after invalidation.

**D8 — The generation logging boundary is unchanged, by scope exclusion (W8-F).** ADR-025's merged
rule for `generate_application_content` stands verbatim: *"Never the evidence, the job text, a
question, the draft, or any length that could characterize one candidate's content — counts only."*
A token count **is** such a length. Week 8 therefore does not log tokens, lengths or cost on the
generation path, its log line is unchanged byte for byte, and the usage sink is **not threaded
through that call at all**. The absence is structural, not a disabled flag: there is no setting to
enable generation cost logging, because a setting is a latent violation waiting for a future
default change. **ADR-025 is not amended, reinterpreted or worked around.**

**D9 — Operational logs only; no table, no migration (W8-G).** Cost and usage are operational log
records, which is exactly what §10.2 describes. No cost or usage table exists, no migration is
written, no queryable ledger is built, and **no cost field is keyed by `candidate_id`** — a
per-candidate cost ledger would be candidate persistence wearing an accounting hat, and
`standards/security_privacy.md` already forbids caching a profile or evaluation keyed by
`candidate_id` in any server-side store.

**D10 — "Refinement" means operational-log completeness (W8-C).** §15's undefined third word is
ruled to mean closing the three operational logging categories §10.2 names by title: **request
counts**, **AI usage and cost logging**, and **error records**. Slice 8A delivers the second; Slice
8C verifies and closes gaps in the first and third, within the existing approved logging vocabulary
— request ids, timings, status codes, operation type and safe technical metadata (§8.1b). It adds
no subsystem and no endpoint.

**Refinement is not** the spaCy deterministic fallback, résumé extraction-accuracy measurement
against §17, recommendation or matching algorithm tuning, live Gemini generation, frontend or
IndexedDB work, deployment, authentication or rate limiting. Each was considered at the design gate
and ruled out of Week 8; the first three required inventing specification the dossier does not
supply, and the remainder belong to Week 9 or a later phase.

## Relationship to merged decisions

**ADR-020 §5 is superseded in part.** Its merged text reads: *"Fitted once per call and discarded.
No vocabulary, IDF values, vectorizer, vectors or scores are persisted or cached, and nothing is
shared between calls."* Slice 8B contradicts that final sentence in its letter and is recorded here
as an explicit, owner-ruled supersession rather than an oversight.

What ADR-020 §5 was protecting is preserved intact: the vectorizer is still fitted on **every**
catalogue job rather than a request's subset, the candidate is still transformed and never fitted,
and a score still cannot depend on which jobs a request selected. The staleness risk that motivated
"discarded" is addressed by the key itself — a catalogue change yields a different fingerprint and
therefore a different cache entry. **Only the sharing of catalogue-derived artifacts between calls
changes; no candidate-derived value is shared, persisted or cached.**

An amendment note inside ADR-020 §5 pointing here — matching the precedent ADR-022 set when it
amended the same section for C-19 — requires its own authorization and is **not** made by this ADR.

**ADR-019 is reaffirmed, not changed.** Its rejected alternative *"Persistent relatedness cache —
would store a statement about a candidate's field server-side"* stands. W8-D was ruled the same
way: no cross-request field-relatedness cache. Request-scoped memoization inside a single
eligibility batch is unchanged.

**ADR-025 D4 is honoured and its forward reference resolved.** D4 barred caching in Week 7 and said
*"Caching remains Week 8."* This ADR answers that: the only approved cache is candidate-free, and
D4's own reason — *"Generated prose is derived personal data; caching it server-side would be
hidden persistence"* — continues to forbid a generated-prose cache permanently, not merely in
Week 7.

**ADR-004 and ADR-013 are unchanged.** No abstract method is added, provider selection stays
configuration, and the mandatory mock stays mandatory.

## Contracts

### Cost and usage log record (Slice 8A)

One line per AI call, as today, on the existing single logging point. The existing fields are
unchanged; token and cost fields are added, each independently `unknown` when unavailable.

**Carries:** provider · model · operation · outcome · duration · the existing safe input count ·
prompt, completion and total token counts · cost in integer micro-units.

**Never carries:** prompt or response text · resume text or any résumé-derived value · any profile
field · evidence, question or generated prose · removed-claim text · `candidate_id` or any
candidate identifier · any value on the `generate_application_content` path beyond what that line
already logs (D8).

### Corpus cache entry (Slice 8B)

**Key:** `corpus_fingerprint(catalogue)`.
**Value:** fitted vectorizer · job matrix · feature names · catalogue row mapping · the
has-vocabulary flag.
**Never in the key or the value:** any candidate field, the candidate vector, any score, any
`candidate_id`, any profile-derived term.

Entries are read-only once stored; downstream matching reads the fitted artifacts and must not
mutate them.

## Slices

**8A — cost and usage accounting.** A usage value object and per-call sink; cost rates as
configuration; Gemini usage extraction accumulating across retries; deterministic synthetic mock
usage plus an injectable no-usage mode; the two instrumented log lines; and the tests that pin the
D8 boundary. Gates QG-001, QG-003, QG-005.

**8B — corpus vectorizer cache.** The fingerprint-keyed bounded LRU and the tests that pin
identical output cold, warm and invalidated, plus candidate isolation. Gates QG-001, QG-005.

**8C — operational-log completeness.** Verification and gap-closing for §10.2's request-count and
error-record categories within the existing logging vocabulary. Gates QG-001, QG-005.

**No intermediate checkpoint.** A single **Checkpoint 8** is recorded after the Week 8 merge and
verified post-merge — see § Checkpoint structure.

## Non-goals — deferred or excluded

**Deferred, revisitable:** live Gemini `generate_application_content` and its prompt, payload,
response schema and injection fixtures (D10 below restates this) · generation-path token, length or
cost logging, which requires its own explicit privacy decision · Gemini live smoke testing of the
two implemented paths, which is an owner and integration activity needing a real key and real
spend, not a Week 8 implementation slice · the spaCy deterministic fallback · §17 extraction-
accuracy measurement · recommendation or matching algorithm tuning · rate limiting, documentation
and deployment (Week 9).

**Excluded outright:** any amendment to ADR-025 · a field-relatedness cross-request cache
(ADR-019) · a generated-prose cache (ADR-025 D4) · a résumé-content cache · any candidate-keyed
cache or cost record · a cost or usage database table, migration or queryable ledger · any new API
route or schema, including a cost, usage, metrics or admin endpoint — §11 lists none, and an
unauthenticated operational-data surface is the abuse surface C-25 already deferred `/jobs/ingest`
to avoid · candidate, application, evaluation or package persistence · application tracking or
status endpoints · submission, autofill, browser automation and CAPTCHA/OTP/identity bypass
(ADR-008, INV-10) · authentication and frontend work · Redis or any external cache service · new
dependencies · hard-coded external pricing · `ENGINE_VERSION` or `MATCHING_VERSION` changes · the
OpenAPI "Current status" sentence, which remains a separately tracked limitation · tags and
releases.

**Live Gemini application generation remains deferred.** `GeminiFlashProvider.generate_application_content`
stays the stub it is today: it raises `AIProviderUnavailableError`, holds no transport, prompt,
payload or key, and reads no candidate data. Week 8 neither implements it nor partially prepares
it. Selecting Gemini therefore continues to degrade honestly — HTTP 200, `NOTHING_VERIFIABLE`,
`AI_GENERATION_UNAVAILABLE` — on the path Week 7 already built and tested. When it is approved, it
carries its own ADR **and** its own explicit privacy decision for usage logging (D8).

## Privacy and security invariants

Week 8 introduces **none** of the following, and each is a testable claim rather than an intention:
candidate-data persistence · résumé retention · PII in logs · provider leakage of fields outside
the ADR-025 D10–D12 evidence allow-list · caching of any candidate-derived value · application
tracking · submission automation · CAPTCHA, OTP or identity bypass.

Specifically: no new table, migration, write path or file; the résumé temp-file lifecycle is
untouched; token counts and cost are numbers carrying no content; the evidence allow-list and
`build_evidence` are unchanged; no prompt is modified; `candidate_id` appears in no cost field and
no cache key; and the Gemini API key continues to travel as a header, never in a URL and never in a
log.

## Testing and quality gates

**Gates.** QG-001 for every slice. **QG-003** for Slice 8A — item 9 is the gate this slice exists
to satisfy, with items 1, 3, 4 and 10 re-evidenced; two additional pieces of evidence are required
for item 9 under this ADR: that no cost field is keyed to any candidate identifier, and that the
`generate_application_content` log line is unchanged. **QG-005** for all three slices. QG-004 is
N/A with evidence of no contract change recorded rather than the gate silently skipped. QG-002,
QG-006, QG-007 and QG-008 are N/A; QG-006 is N/A because D9 rules out any table or migration.
**No new quality gate is created** — QG-003 items 9 and 10 and QG-005 already cover this work, and
a duplicate cost gate would add ceremony without coverage.

**Expectations.** Unit coverage of cost arithmetic at every degradation point. Provider tests
through the existing mocked transport for usage present, absent, partial and malformed, and for
accumulation across a retried call. **Boundary tests that make D8 enforced rather than intended:**
the generation log line unchanged, no token or length field on that path, the usage sink
unreachable from it, and no configuration key able to enable it. Response bodies byte-identical
across every existing endpoint, with the route count still ten. A privacy sweep over real requests
asserting that no marker value and no `candidate_id` reaches any log line and that the database
file is byte-identical. For Slice 8B, identical scores, bases, top terms, ordering and fingerprint
cold, warm and invalidated; the candidate never in the cached corpus; fitted artifacts unmutated;
the LRU bounded. Mutation testing at the Week 7 bar — **100% of mutants caught**, with the Week 7A
and 7B suites re-verified unbroken. The offline full-flow test continues to pass with its socket
guard and no golden expectation perturbed.

## Migration and dependency impact

**No migration.** Three migrations, head `b3e8d2c61a47`, `alembic check` clean; tables stay exactly
`alembic_version`, `ingestion_state` and `jobs`.

**No new dependency.** Both approved slices use the standard library and existing pins;
`requirements.txt` is unchanged. Slice 8B adds no caching library — the LRU is process-local and
in-memory.

**No API surface change.** Route count stays ten; no request or response schema changes.

## Checkpoint structure

**One Checkpoint 8, no intermediate checkpoint.** Recorded after the Week 8 merge and verified
post-merge, following the Week 7 precedent: all three slices are behaviour-preserving and none is a
state worth rolling back to on its own. There is no Checkpoint 8A and no Checkpoint 8B.

This is final for the scope in D1. It is revisited **only** if a later, separately approved scope
change materially expands Week 8 — a new dependency or an output-changing algorithm change would
justify an intermediate checkpoint, and neither is in scope here. A checkpoint is not a release,
version or tag (C-28).

## Rejected alternatives

- **Instrumenting the generation path for cost** — contradicts ADR-025's merged logging boundary; a
  token count is a length that characterizes one candidate's content (D8).
- **Amending ADR-025 to permit generation token logging** — would resolve a live privacy question
  inside a scoping ADR. It needs its own decision, made deliberately.
- **A configuration flag to enable generation cost logging** — a disabled flag is a latent
  violation; the exclusion is structural instead.
- **A `last_usage` attribute on the provider** — shared mutable state under concurrent
  `asyncio.gather` fan-out; races and mis-attributes cost (D3).
- **Changing provider return types to `(result, usage)`** — honest, but rewrites four abstract
  signatures and every merged call site and spy for an operational-logging feature.
- **A cost or usage table** — §10.2 says operational logs; a table invites a queryable per-candidate
  ledger and drags a migration and QG-006 behind it (D9).
- **A `/metrics`, `/usage` or admin endpoint** — absent from §11, and an unauthenticated
  operational-data surface.
- **A cross-request field-relatedness cache** — stores a statement about a candidate's field of
  study server-side; already rejected by ADR-019 and re-rejected as W8-D.
- **Caching generated prose** — hidden persistence of derived personal data (ADR-025 D4).
- **Hard-coding Gemini pricing** — an unverified external fact that changes; a stale constant would
  present a wrong number as a measurement (D5).
- **Redis or an external cache** — a distributed component at solo-project scale, explicitly out of
  scope in `context/workflow.md` § Scope discipline.
- **Reading "refinement" as spaCy, accuracy measurement or algorithm tuning** — each would require
  inventing specification the dossier does not supply; §16 names scope creep as the highest-severity
  risk to this project (D10).

## Consequences

**Positive.** QG-003 item 9, unmet since Week 2, is finally satisfied on the paths that can incur
real cost. Cost becomes observable in one place, exactly as §9.2 requires, with no new surface and
no new dependency. The one approved cache removes repeated work on every recommendation request
while remaining provably candidate-free. Week 8 changes no contract, so the whole slice set is
verifiable by asserting that nothing observable changed.

**Negative / accepted.** **Cost data is deliberately incomplete** — it covers resume extraction and
field relatedness but not generation. That gap is theoretical while generation is mock-only and
costs nothing, and becomes material the moment live generation is approved; the Checkpoint 8 record
must state this plainly rather than implying full cost coverage. ADR-020 §5's "nothing is shared
between calls" no longer holds literally, and until its amendment note is separately authorized a
reader of ADR-020 alone will not find the pointer here. Cost figures are only as accurate as the
configured rates, which a human must keep current. Sharing fitted artifacts between requests trades
a little memory and a small correctness surface for repeated work avoided.

## Revisit conditions

Live Gemini application generation and its usage-logging privacy decision (Week 8/9) · the ADR-020
§5 amendment note · a cost store if operational logs prove insufficient for the diagnostics §10.2
intends · the cache bound if catalogue size or churn changes materially · batching, if a provider
gains a genuine multi-prompt API — none applies today, and it is recorded here as **not required**
rather than left as implied scope.

## Enforcement

`app/ai/ai_service.py` · `app/ai/providers/base.py` · `app/ai/providers/gemini.py` ·
`app/ai/providers/mock.py` · `app/config.py` · `app/services/matching_engine.py` ·
Week 8 mutation suite · QG-001, QG-003, QG-005 · `standards/ai.md` §7 ·
`standards/security_privacy.md` · `reviewers/ai.md`, `reviewers/security.md`, `reviewers/qa.md`
