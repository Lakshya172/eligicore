# ADR-030 — Verified Job Requirement Extraction

**Status:** Accepted — **design only, nothing implemented** · **Date:** 2026-10-02 · **Type:** Design ruling (architectural gate)
**Source:** dossier §7 step 5, §10.2, §12.1, §13 · the first live Greenhouse fetch (2026-10-02)
**Decided by:** project owner, across the ADR-030 design gate, owner-decision gate, sub-decision gate and decision lock
**Enforces:** INV-1, INV-3, INV-4, INV-5, INV-10, INV-12 · **Refines:** ADR-003, ADR-004, ADR-006, ADR-007, ADR-017, ADR-018, ADR-019, ADR-026, ADR-028
**Supersedes:** nothing directly — **ADR-028 D9 and D19 require a later additive amendment (§ Relationship to earlier ADRs); no ADR is amended by this document**
**Rules on:** D1–D27 and D23a · **Resolves:** ADR-028 open **OD-6** · **Owner decisions:** OD-1 … OD-10 and the storage decision, **all resolved** (see § Owner decisions)

---

## Context

ADR-028 activated live job sources early and named Greenhouse as the first. PR #52 merged the
adapter; the first real fetch ran on 2026-10-02 against a public board and returned **seven jobs**.
Every one of them produced the same result:

| Structured criterion | Live jobs carrying a value |
|---|---|
| CGPA (`min_cgpa`, `min_cgpa_scale`) | **0 / 7** |
| Field / branch (`allowed_fields`) | **0 / 7** |
| Degree level (`min_degree_level`) | **0 / 7** |
| Backlogs (`max_backlogs`) | **0 / 7** |
| Graduation year (`min_grad_year`, `max_grad_year`) | **0 / 7** |
| Required skills | **0 / 7** |
| Deadline | **0 / 7** |
| Employment type | **0 / 7** — the field does not exist upstream (ADR-029) |

Everything an employer states lives in 3,090–5,913 characters of free-text HTML per posting. The
adapter maps that text to `description` and leaves every criterion `None`, which is exactly what
ADR-028 D9 requires of it.

### What that does to the product, measured rather than assumed

ADR-028's Consequences section predicted that live jobs would *"evaluate to `UNKNOWN` /
`NEEDS_REVIEW`"*. **That prediction is wrong, and the real behaviour is worse.** ADR-017's
precedence rule 1 states that a job with zero structured requirements is `ELIGIBLE`. Running the
merged engine on a Greenhouse-shaped job whose description states *"minimum CGPA 7.5/10 · B.Tech
CSE or IT · graduating 2026 · no active backlogs"*, against a candidate with **CGPA 5.0, Mechanical
Engineering, graduated 2024, nine backlogs**:

```
eligibility_state    : ELIGIBLE
requirement_breakdown: []
summary              : Eligible: this job states no structured eligibility requirements.
```

The engine is behaving exactly as specified. The **premise** of rule 1 is what live data broke:
R-4 assumed a job with no structured fields genuinely states no gate. True of the curated
catalogue, whose criteria live in typed columns. False of every live source, whose criteria live
in prose.

An eligibility-first product that tells every candidate they are eligible for every live job has
inverted its own value proposition. ADR-003 names this failure mode precisely: *"telling a
candidate they qualify for something a recruiter will reject them from."*

### What has already been done, and what this ADR is not

**Phase 0 shipped separately.** PR #54 (`85d574d`) corrected the disclosure half: a job carrying
description text is no longer summarised as stating no requirements. That fix parses nothing —
`job.description` appears once in the whole engine, in a truthiness test — and it is **not part of
this ADR**. It removed a misleading statement; it did not make a single live job evaluable.

This ADR answers the remaining question, which is ADR-028's own open **OD-6**: *"Response to the
structured-eligibility gap — accept mostly-`None` live requirements, rely on the curated tier for
structured evaluation, or authorize something new."*

### The precedent this decision follows

Three merged patterns make the answer here conservative rather than novel:

- **ADR-007** already treats AI output as untrusted and verifies it claim-by-claim against source
  data before release. This ADR applies the same move to a different artifact: a job's text instead
  of a candidate's profile.
- **ADR-019 §4** already caps an AI judgement below hard authority — an AI `FAIL` yields
  `NEEDS_REVIEW`, never `NOT_ELIGIBLE`, *"because a probabilistic judgement about whether two fields
  are related is not strong enough evidence to tell a person they may not apply."*
- **`application_content.txt`** already passes an adapter-sourced job description to a model inside
  a labelled `BEGIN … END` data block, with explicit instructions that its contents are data and
  never instructions.

What is genuinely new is a **third provenance class**: until now, every requirement in `jobs` came
from a source that stated it structurally.

---

## Problem

Stated as the decision this ADR makes:

> May a job's free-text description produce structured eligibility requirements, and if so, under
> what conditions, with what authority, stored where, and produced when?

ADR-028 D9 currently answers *no* — *"No requirement may be invented, inferred, defaulted or
AI-extracted into existence."* Keeping that answer unchanged leaves the measured behaviour above in
place permanently for every live source. Changing it without a verification contract reintroduces
exactly the fabrication D9 exists to prevent, in the one place where fabrication causes a person to
act on it.

---

## Decision

> **This document is design only. Nothing in it is implemented.** Every `D` below describes
> approved architecture, not present behaviour. The repository at the time of writing contains no
> verifier, no extractor, no `extracted_requirements` table, no provider method and no fixture
> corpus, and `app/config.py` is unchanged.

### Provenance and authority

**D1 — Two provenance classes, and only two.**

| Class | Meaning |
|---|---|
| `SOURCE_STATED` | The source published the value in a structured field the adapter read directly. Everything in `jobs` today. |
| `PROSE_DERIVED` | The value was produced by reading a job's free text, by any means. |

A requirement is one or the other. There is no third class and no "mostly structured" middle.

**D2 — A `PROSE_DERIVED` requirement may never independently produce `NOT_ELIGIBLE`.**
`NOT_ELIGIBLE` continues to require at least one `SOURCE_STATED` deterministic `FAIL`. This is
ADR-019's R-2 reasoning applied to a second kind of probabilistic input, and it preserves ADR-017's
auditability guarantee in a strictly stronger form: a candidate told they may not apply is always
being told so on the basis of something the employer published structurally.

**D3 — Authority is a function of provenance, never of extraction technology.** A value read by a
regular expression and a value read by Gemini are both `PROSE_DERIVED` and carry identical
authority. Authority is **not** tied to regex-versus-AI, Gemini-versus-mock, provider identity,
model version, or reported confidence.

This is the single most important structural choice in this ADR, and it is deliberate. Tying
authority to the extractor makes the policy expire every time the extractor changes, and invites
the argument that *this* extractor is reliable enough to be promoted. Tying it to provenance makes
the rule stable across every future extractor, and makes "is this safe?" a question about evidence
rather than about implementation.

**D4 — Precedence, amended minimally.** ADR-017's six ordered rules become:

```
1. Zero structured requirements                                  → ELIGIBLE
2. Any SOURCE_STATED deterministic FAIL                          → NOT_ELIGIBLE      (narrowed)
3. Every requirement UNKNOWN                                     → UNKNOWN
4. Any UNKNOWN, any AI-reasoned FAIL, or any PROSE_DERIVED FAIL  → NEEDS_REVIEW      (widened)
5. All PASS, at least one by AI reasoning or PROSE_DERIVED       → LIKELY_ELIGIBLE   (widened)
6. All PASS, all deterministic and SOURCE_STATED                 → ELIGIBLE          (narrowed)
```

Rules 1 and 3 are untouched. The changes to 2, 4 and 5 are the whole of the amendment.

**Rule 5 is widened deliberately, and it closes a specific failure.** `has_verified_hard_failure`
keys on `method is EvaluationMethod.DETERMINISTIC`, and rule 5 keys on `AI_REASONING`. If a
deterministically-extracted requirement were labelled `DETERMINISTIC` and nothing else changed,
an all-`PASS` evaluation built entirely from prose-derived requirements would return plain
**`ELIGIBLE`** — asserting the strongest verdict the system has, on requirements no employer stated
structurally. Widening rule 5 prevents exactly that: such an evaluation returns
`LIKELY_ELIGIBLE`, whose existing meaning — *every stated requirement passed, at least one by
something other than a deterministic source-stated check* — already fits without alteration.

**D5 — No new eligibility state.** The five states of ADR-017 are unchanged in number, name and
meaning. Adding one would still require its own ADR (ADR-017, QG-002 item 15).

### The safety contract

**D6 — A proposal becomes a verified derived requirement only when all eight conditions hold.**

| # | Condition |
|---|---|
| 1 | The source text explicitly contains the requirement. |
| 2 | The extractor identifies the requirement. |
| 3 | Supporting evidence text is returned with it. |
| 4 | That evidence exists in the **pinned normalized source text** (D9). |
| 5 | A **deterministic verifier** confirms the extracted value and type are supported by that evidence. |
| 6 | The semantic requirement type is one the engine recognises (ADR-018's five). |
| 7 | The strength classification is `REQUIRED` (D10). |
| 8 | No contradicting or qualifying text within the contradiction window invalidates the proposal (D9). |

Any condition failing means the proposal **does not become a requirement**. It is discarded, not
downgraded, not retried with a lower bar, and not surfaced as a weaker constraint. The job's
criterion stays absent, which is the pre-existing behaviour and is never a failure for the
candidate (ADR-003: absence of evidence is not evidence of ineligibility).

The verifier is the authority. The extractor — regex or model — produces a **proposal**.

**D7 — Model confidence is never evidence.** A reported confidence may **lower** trust: a low-confidence
proposal may be discarded. It may never **raise** it, never substitute for a failed condition, and
never appear as an input to conditions 1–8. ADR-019 §4 already establishes the direction —
confidence is capped downward and never raised — and this extends it.

A confidence score is a model's opinion of its own output. Admitting it as evidence would make the
verifier a rubber stamp wearing a verifier's name, which is worse than having no verifier, because
it would be reported as verification.

**D8 — The worked case: "CGPA 7.5 preferred, 7.0 required".**

This sentence is the reason conditions 7 and 8 exist, and it must be in the test corpus.

An extractor proposing `min_cgpa = 7.5` with the evidence *"CGPA 7.5 preferred"* passes conditions
1–6 **cleanly**. The text exists. The span is locatable. The value 7.5 genuinely appears in it.
`MIN_CGPA` is a recognised type. Nothing about the proposal is fabricated.

- **Condition 7 refuses it.** The evidence says *preferred*, so strength is `PREFERRED`, which does
  not gate (D10). The proposal is discarded.
- **Condition 8 refuses it independently**, because *"7.0 required"* sits inside the contradiction
  window and qualifies it.

The correct hard requirement is `min_cgpa = 7.0`, and the system may adopt it **only if an
extractor proposes 7.0 with the evidence "7.0 required" and that proposal passes all eight
conditions on its own merits.** The system never "corrects" 7.5 to 7.0; it either receives a
well-evidenced 7.0 proposal or it has no CGPA requirement for that job.

**If both proposals arrive, or the strength reading is ambiguous or contradictory, neither is
promoted.** A job with no CGPA requirement is honest. A job with the wrong CGPA requirement tells a
qualified candidate not to apply.

**Why confidence cannot solve this.** A model reporting HIGH confidence in `min_cgpa = 7.5` is not
wrong about its own reasoning — the phrase really does say 7.5, and the extraction really is
faithful to it. The error is not in the model's certainty; it is in which clause was read. No
confidence value distinguishes "I read this sentence correctly" from "I read the correct sentence",
and only the second matters here. Conditions 7 and 8 test the thing confidence cannot see.

**D9 — The pinned normalized text and the contradiction window, defined deterministically.**

Both conditions 4 and 8 need a definition, and the repository's actual normalization constrains it.
`collapse_whitespace` is `re.sub(r"\s+", " ", value).strip()`, applied to the description during
normalization. **Paragraph structure does not survive into the stored text** — `\n\n` becomes a
single space — and Greenhouse content is HTML, so markup survives as literal characters. Two
consequences follow and are normative:

- **The pinned normalized text is `jobs.description` as stored** — the post-`collapse_whitespace`
  string, not the raw fetched payload. Evidence is located in that string and nowhere else. A
  verifier that located evidence in the raw payload would pass on text the system does not hold.
- **"Nearby" is defined as a character window, not as paragraphs or sentences.** Paragraphs do not
  exist in the pinned text, and sentence splitting over collapsed HTML is unreliable. The
  contradiction window is a **symmetric character window centred on the evidence span, clamped to
  the text bounds**, with a single documented constant shared by every requirement type.

The window must be wide enough for both canonical cases: *"CGPA 7.5 preferred, 7.0 required"*
(~30 characters apart) and *"CGPA 7.5"* followed shortly by *"This requirement is waived for …"*
(one or two sentences later). A **default of 300 characters each side** satisfies both with margin;
the exact constant is an open implementation note (§ Open implementation notes), to be fixed with
evidence from the corpus rather than guessed here.

**The contradiction scan within the window is deterministic and pattern-based.** It is never a model
judgement. Asking a model whether its own extraction is contradicted reintroduces the authority this
ADR removes.

**Offsets are not authoritative provenance** (OD-3). An offset is valid only against one exact
normalized string; a re-normalization or a source edit silently invalidates it. Offsets may be
computed and used at verification time. **Evidence text is what is persisted** (D18).

### Requirement strength

**D10 — Only `REQUIRED` affects eligibility.**

**Two outcomes exist for an extracted statement, and they must not be confused:**

- **Verified derived eligibility requirement** — a statement that passed all eight conditions of
  D6. It enters the requirement set, is evaluated, and appears in the breakdown under the capped
  authority of D2 and D4.
- **Disclosed / observed** — a statement the system noticed in the source text but did **not**
  promote. It is never evaluated, never appears as a requirement, and contributes nothing to the
  verdict. At most it is shown to a reader as something the posting says.

| Strength | Effect |
|---|---|
| `REQUIRED` | The **only** strength that satisfies D6 condition 7. May become a verified derived requirement and participate in evaluation under D2/D4. |
| `PREFERRED` | **Disclosed / observed only.** Never a gate, never a requirement, never evaluated. |
| `CONDITIONAL` | **Disclosed / observed only within ADR-030.** Fails D6 condition 7, so it is **not promoted** and never enters the verified requirement set. It must not bypass condition 7, must not reach evaluation through any other path, and can therefore never produce a deterministic hard failure. |
| `INFORMATIONAL` | **Disclosed / observed only.** |

**On `CONDITIONAL` specifically.** The owner's decision (OD-5) is that a conditional statement
never creates a deterministic hard failure and is limited to disclosure or `NEEDS_REVIEW`
semantics. Within this ADR that resolves to **disclosure only**, because condition 7 admits
`REQUIRED` and nothing else: there is no promotion path a conditional statement could take, and
**this ADR creates none.** A conditional statement may be *retained as non-authoritative extracted
metadata* if the future schema explicitly supports that, but retention is not promotion and
confers no evaluation effect whatever.

Routing a conditional statement to `NEEDS_REVIEW` would require a mechanism that does not exist
here and would need its own decision. It is deliberately **not** invented by this ADR — a second
execution path into the requirement set is exactly the kind of bypass D6 exists to prevent.

*"Students from CS/IT or related backgrounds preferred"* must never become an authoritative
exclusion. A recruiter's soft wish converted into a system-stated barrier produces a candidate who
self-deselects from a role the employer never excluded them from — a harm the system causes and the
employer never intended.

### Deterministic first

**D11 — Phase 1 is deterministic extraction; Phase 2 is AI extraction, and only afterwards.**

Phase 1 scope, and nothing beyond it:

- CGPA **and its scale**
- graduation year
- backlog count

These are the criteria ADR-003 already assigns to plain code — *"anything numerically or
categorically comparable is evaluated in plain code"* — and routing them through a model first
would weaken deterministic-before-probabilistic rather than apply it.

Phase 2 may begin only once the verifier and the Phase 1 path are proven in the repository, under
the go conditions in § Implementation sequencing.

**D12 — Excluded from deterministic extraction, permanently or pending a separate decision:**

| Excluded | Why |
|---|---|
| Field / branch ontology | Requires the synonym table ADR-018 A-2 forbids as *"an ontology in disguise, and a source of silent false passes."* |
| Required skills | ADR-018 assigns skills to matching, not eligibility; see D20's note on double counting. |
| Requirement strength classification | Needs discourse understanding; the hardest and most safety-critical judgement in the capability. |
| Degree-level mapping from a degree name | ADR-018 is explicit: *"A level is never guessed from a degree name."* |
| Deadlines | Out of scope entirely (D23a). |

**A deterministic extraction is not self-evidently correct and is not exempt from anything.** A
regular expression locates a number; it does not establish that the number is a CGPA requirement
rather than *"7.5 years of experience"*. Every Phase 1 value passes the same eight conditions as
every Phase 2 value, and carries the same `PROSE_DERIVED` provenance and the same capped authority.

### AI provider boundary

**D13 — A dedicated provider operation, conceptually `extract_job_requirements(description, *, usage)`.
`extract_resume(...)` must never be overloaded to carry job text.**

`AIProvider` currently declares exactly three operations, each taking only what its task needs
(ADR-004). `extract_resume`'s own contract calls its input *"Sensitive — must never be logged."*
Routing public job text through it would destroy the property ADR-019 §7 and ADR-025 D10 both rely
on: **the signature is the privacy boundary.** A dedicated operation takes a description and
nothing else, so no candidate identifier, profile, grade, year or resume has a parameter to travel
in — the exclusion is structural, not a filter someone must remember to apply.

The `usage` sink is included, unlike `generate_application_content`, which deliberately has none:
job text is not candidate content, so ADR-025's length-disclosure concern does not apply and
ADR-026's cost accounting does (D22).

**D14 — The mock provider remains mandatory, default, and silent.** `MockAIProvider` must implement
the operation and **return no extractions unless explicitly configured**, following the
conservative-default pattern ADR-019 §9 established for relatedness. An unconfigured deployment —
which is every deployment today, `ai_provider: mock` — therefore behaves exactly as it does now and
can never fabricate a requirement.

**Field relatedness stays separate.** ADR-019 answers one bounded question with three enumerated
answers and cannot create a requirement. Extraction creates requirements and never sees a
candidate. They are different operations on different inputs with different risk, and merging them
would be precisely the silent expansion ADR-028 warns against.

**D15 — The approved model for future live use is `gemini-3.8-flash`.**

`gemini-2.0-flash`, the value currently in `app/config.py`, **was shut down on 2026-06-01** and must
not be used when Gemini is enabled. The configuration is **not changed by this ADR** and remains a
separate implementation step. The provider migration must account for the current API contract,
verified against Google's documentation at this gate:

- **Remove `temperature`, `top_p`, `top_k`, `candidate_count`** — ignored by the backend on this
  model generation. The provider currently sends `temperature: 0.0` on **both existing calls**, so
  this migration affects resume extraction and field relatedness as well as extraction, and their
  determinism control is inert until it lands.
- **Use the current documented thinking configuration** (`thinking_level`) where applicable.
- **Preserve structured JSON output** — a response schema plus a JSON response type. The output
  schema must have no free-form explanatory field; unrestricted prose is the channel an injected
  instruction or an unverifiable rationalisation travels through.

### Storage

**D16 — Verified derived requirements live in a separate operational table, `extracted_requirements`.**
They are **never** written into the existing source-owned job fields.

Two hazards in the merged code make this mandatory rather than stylistic, and both were found by
inspection at the design gate:

1. **`requirements` participates in `content_hash`.** `compute_content_hash` hashes company, role
   title, location, apply link, `source_job_id`, `description`, the `requirements` JSON and source.
   Writing derived values into `requirements` changes the hash, so the job presents as changed on
   the next ingestion, which triggers re-extraction, which changes the hash. A self-sustaining loop.
2. **`_apply_updates` overwrites every source-owned requirement field on every run.** Its
   `_UPDATABLE_FIELDS` tuple contains `min_cgpa`, `min_cgpa_scale`, `allowed_fields`,
   `min_degree_level`, `max_backlogs`, `min_grad_year`, `max_grad_year`, `required_skills`,
   `deadline`, `requirements`, `description` and `content_hash`. A live adapter supplies `None` for
   all of them, so a derived value written into any of those columns is **erased on the next
   ingestion**, and the job is counted `updated` every run forever.

Hazard 2 is the broader one: it applies to the typed columns as well as to `requirements`, so
"write it into `min_cgpa`" is not a safe alternative to "write it into `requirements`".

**D17 — Derived data is outside the source content hash and outside the source update path.**
`compute_content_hash` must not read it; `_apply_updates` must not touch it. Both must be asserted
by test, not assumed (§ Testing implications).

**D18 — Persisted per verified derived requirement** (OD-3):

- the verified structured requirement — type and normalized value
- the **evidence text**
- the extractor / provider identity
- the model identifier and version, where applicable
- the extraction timestamp

Character offsets are **not** authoritative provenance (D9) and must not be the mechanism by which
a stored requirement is re-verified. No candidate identifier, and no candidate data of any kind, is
persisted here or anywhere in this pipeline.

Exact columns, types and constraints are **not** decided by this ADR and belong to the
implementation PR that writes the migration.

**D19 — `(job_id, content_hash)` is the derivation boundary to evaluate at implementation.** A
derived requirement is derived *from a specific version of a job's source text*. Keying on the job
plus the hash of the text it was derived from makes staleness detectable by join rather than by
bookkeeping, and makes invalidation on a source change automatic. `jobs.id` is a UUID assigned once
at creation and stable across updates, and `content_hash` is already indexed
(`ix_jobs_content_hash`), so both halves exist today. This is recorded as the direction to evaluate,
not as a final schema.

`ingestion_state` (ADR-015) is the existing precedent for a second operational table holding
job-side operational data.

### How derived requirements reach evaluation

**D20 — Derived requirements are supplied to the eligibility engine as an explicit, separate input
alongside the job — never merged into `JobRead`'s source-owned fields.**

The engine's entry point today is `evaluate_job(profile, job: JobRead)`, and `JobRead` is built
from `jobs` columns. The boundary this ADR fixes is:

- `JobRead` **keeps its current shape**, so `GET /api/v1/jobs` and every existing client contract
  are unaffected (ADR-010).
- Verified derived requirements are passed to evaluation as a **distinct, typed collection**, each
  entry carrying its provenance, strength and evidence. The engine receives source-stated data and
  derived data as two separate things and can therefore apply D2 and D4 **structurally**, rather
  than by remembering which fields happen to be derived.
- The engine stays pure and framework-independent: no session, no repository, no router types. The
  caller — the eligibility service or router — is responsible for loading derived requirements and
  handing them in.
- A test can supply derived requirements directly, with no database and no extractor, which keeps
  the precedence and authority rules unit-testable in isolation.
- `RequirementResult` gains **provenance** and **evidence** so the breakdown can show *why* a
  requirement exists and where it came from. This is the ADR-017 amendment described below, and it
  is what makes D2 auditable from the response rather than merely true internally.

**This is an explainability change, and ADR-006 governs it.** ADR-006 fixes the breakdown entry at
`requirement`, `candidate_value`, `status`, `confidence`, `method` and an optional `note`, and says
of `method` that it *"is how a reader knows which evaluation stage produced a verdict, and it makes
ADR-003 auditable from the output."* Provenance does the same job for D2: without it, a reader
cannot tell whether a requirement was published by the employer or read out of prose, and the
authority rule is true internally but invisible externally — which ADR-006 treats as a failure, not
a result. Evidence text extends the same principle, letting a reader see the sentence a derived
requirement rests on. ADR-006's accepted cost applies unchanged: payloads grow, and a rule change
that does not update its explanation is a defect. Its INV-4 caution also applies — evidence is job
text, never candidate text, and is still never logged. **ADR-006 itself is not modified.**

**Three alternatives are rejected explicitly, so a later PR cannot choose one silently:**

| Rejected | Why |
|---|---|
| Merge derived values into `JobRead`'s existing typed fields | Erases provenance at the exact point where D2 needs it. The engine could no longer distinguish a stated cutoff from a derived one, making the authority rule unenforceable. |
| Add derived twin fields to `JobRead` | Churns the public job contract and leaks derived data into `GET /api/v1/jobs`, which is a catalogue endpoint, not an eligibility one. |
| Have the engine load derived requirements itself | Gives the engine a database dependency, breaking the framework-independence every current engine test relies on. |

**Matching is untouched.** ADR-020's job document is already `required_skills + role_title +
description`, so live job prose *already* participates in match scoring. Feeding extracted skills
into `required_skills` would double-count terms already present and silently reweight every score,
which is why D12 excludes skills and why this ADR changes no matching behaviour at all.

### Ingestion and re-extraction

**D21 — Extraction runs at ingestion time only.** Never during an eligibility request, never per
candidate, and never once per evaluation. Cost then scales with catalogue **churn**, which
`content_hash` already measures, rather than with `jobs × candidates × requests`. The second smoke
run produced `7 unchanged`, which under this policy is zero extraction calls.

**No multi-job batching initially.** One job per request: a malformed reply loses one job rather
than a batch, and an injected instruction inside job A cannot reach job B's extraction.

**D22 — Re-extraction is hybrid.**

| Trigger | Behaviour |
|---|---|
| Source content changed (new job, or changed `content_hash`) | Eligible for extraction at the next ingestion. |
| Extractor or model version changed | Requires an **explicit re-extraction operation**. Ordinary ingestion never silently re-extracts the catalogue. |

Prior extractions persist until explicitly replaced; persisted provenance (D18) makes stale model
versions detectable; and a configuration rollback does not destroy stored derived data merely
because a setting changed.

The operational surface follows the existing CLI convention — `python -m app.cli <kebab-case-command>`,
as `seed-catalogue` does — and is named at implementation. It belongs with ADR-028's refresh/CLI
slice, not with this capability's first PR.

**Failure fails closed.** An extraction failure yields no requirement, never a partial or guessed
one, and **must not fail the ingestion run**. This mirrors ADR-019 §5: the request still succeeds,
and no exception text reaches a response or a log beyond an error type.

**Cost and usage accounting** follow the existing mechanism (ADR-026); extraction is a counted,
logged AI operation.

### Fixture corpus

**D23 — One bounded live Greenhouse fetch is authorized; complete third-party descriptions are not
committed.**

The fetch is a single public-board GET, no application endpoint, no authentication, no candidate
data, no production mutation. **It is not performed by this ADR.**

**The authorization is for exactly one fetch and is consumed by it.** Once that fetch has been
performed, this ADR authorizes no further live Greenhouse request: **any additional fetch, retry
for a better corpus, or refresh of the corpus requires a new owner decision.** No repeated
polling, scheduled fetching or re-fetching is implicitly authorized by OD-7 or by anything in this
document. Raw and full fetched job text remains **local-only and uncommitted** under this ADR, and
the committed artifact remains limited to the derived-corpus shape below.

A consequence follows and is accepted deliberately: because the raw corpus is never committed and
the authorization is single-use, **a lost local corpus cannot be recreated without a new owner
decision.** That is the price of not redistributing third-party text, and it argues for capturing
the derived artifact promptly once the fetch is made.

The committed artifact is a **derived corpus**:

- structural metadata
- requirement-span metadata
- **short verbatim requirement fragments only**
- the minimum exact wording needed to exercise evidence verification
- provenance sufficient to explain the fixture's origin, **without unnecessarily publishing
  employer-specific operational identifiers**

The raw, full fetched corpus stays **local-only and uncommitted**.

The reason is not privacy — a job description is public employer text, not personal data — it is
**licensing**. The repository is MIT-licensed, which grants recipients rights the project cannot
grant over a third party's creative text, and every clone, fork and mirror would redistribute it.
There is no precedent for committed third-party content: the entire existing catalogue is synthetic,
with `Example …` employers and descriptions of 0–132 characters against the 3,090–5,913 characters
a real posting carries.

**A consequence to carry into implementation, recorded honestly:** a committed fragment must include
enough surrounding text to exercise the contradiction window (D9), which bounds how short "short"
can be. Where a real case needs more context than the artifact policy permits, it is tested with
synthetic text and the real case is exercised against the local corpus only.

### Deadlines

**D23a — Deadline extraction and freshness are outside ADR-030.** They belong to ADR-028's
freshness slice, remain deterministic, and are not part of this capability. Greenhouse exposes
`application_deadline` as a real API field — null on all seven observed jobs, but present — so a
source may simply supply it, and routing a solved problem through a model and an eight-condition
gate buys nothing.

*Numbered `D23a` rather than `D28` following the repository's additive convention (ADR-028 D11a),
so D1–D27 stay contiguous. It is a decision in its own right, not a sub-clause of the fixture
corpus decision above.*

### Privacy and security

**D24 — The pipeline is candidate-free by construction.**

- No candidate data, profile, identifier or resume content enters job requirement extraction. The
  signature is the boundary (D13); there is no parameter for it to arrive in.
- No candidate identifier is persisted with an extracted requirement (D18).
- The input is public job text already persisted in `jobs.description` under dossier §10.2
  (*"Original posting text"*), so no new data category enters the system.
- No PII in logs. Logging follows the existing operational pattern: counts, outcome, provider,
  model, timing — never prompt, response, evidence or description content.
- Extracted requirements are **job-derived operational data** and remain categorically distinct
  from candidate data. INV-1 and ADR-011 are untouched: nothing here moves the system toward
  server-side candidate persistence.

**D25 — The job description is untrusted third-party input and must be treated as data, never as
instructions.**

The prompt boundary reuses the merged pattern from `application_content.txt`: system rules first,
then the description inside an explicitly labelled `BEGIN … END` data block, with the standing
instruction that text inside may look like a command, a system message or a request to ignore the
rules, and is none of those.

**The structural claim is the one that matters, and it is what tests must assert:** a successful
injection still cannot produce a requirement, because any proposal it induces must still satisfy all
eight conditions of D6 against the real source text. Prompt hardening reduces noise; the verifier is
what makes injection non-exploitable.

**D26 — Failure and rollback semantics.**

| Situation | Behaviour |
|---|---|
| Extractor unavailable, errors, or times out | No requirement produced. Ingestion succeeds. Existing `AI_ASSESSMENT_UNAVAILABLE`-style semantics apply at evaluation. |
| Malformed or schema-invalid output | Discarded whole. No partial adoption of a reply. |
| Any of conditions 1–8 fails | Proposal discarded. The criterion stays absent — never a `FAIL`, never a guess. |
| Mock provider configured (the default) | Zero extractions, zero requests, behaviour identical to today. |

**D27 — The capability is reversible.** Because derived data lives in its own table (D16) and the
engine receives it as a separate input (D20), disabling extraction and ignoring or dropping the
table returns the system exactly to its pre-ADR-030 behaviour. No source-owned column, no
`content_hash`, and no public contract is mutated, so there is nothing to migrate back.

---

## Non-goals

Explicitly excluded, and not reintroducible by an implementation PR:

- **Automatic application submission**, in any form (ADR-008, INV-10).
- **CAPTCHA, OTP, anti-bot or identity-verification bypass.**
- **Browser automation.**
- **Candidate-data persistence** of any kind (ADR-011, INV-1).
- **Extracting required skills into eligibility** (D12; ADR-018 assigns skills to matching).
- **Deadline handling** as part of this capability (D23a).
- **Unrestricted AI eligibility judgement.** AI never evaluates a candidate against a requirement
  here; it reads a job (ADR-019 §2 remains in force).
- **Model confidence as authority** (D7).
- **Per-candidate AI requirement extraction** (D21).
- Any change to matching, recommendation ranking or application preparation.

---

## Alternatives considered

**Accept the gap — no extraction at all.** Honest at the field level and actively misleading at the
verdict level, since this is the option that produced the measured `ELIGIBLE` above. Phase 0 (PR
#54) removed the misleading sentence, but a live catalogue that cannot be evaluated is an
eligibility-first product that does not perform its one function on live data. Rejected as an end
state; retained as the behaviour whenever verification fails.

**Deterministic extraction only, no AI ever.** Attractive — auditable, free, offline, testable to
100%. Rejected as a complete answer because ADR-018 A-2 forbids the machinery the remaining fields
need: a branch extractor mapping *"CSE/IT or related"* onto `allowed_fields` **is** the synonym
table that ADR is written against. Adopted for what it does handle, as Phase 1 (D11).

**AI extraction without evidence verification.** Rejected outright. This is D9's fabricated hard
constraint with extra steps, and it is the failure ADR-003 names as the worst available to this
system.

**Trust the model's confidence score instead of a verifier.** Rejected (D7). Confidence cannot
distinguish reading a sentence correctly from reading the correct sentence, which is exactly the
D8 case.

**Let verified extraction create `NOT_ELIGIBLE` immediately.** Rejected for now (D2). It would make
the first person told "you may not apply" to a live posting the subject of an unmeasured extraction
precision. Revisitable with measured precision (§ Revisit conditions).

**Tie authority to the extractor — regex authoritative, AI capped.** Rejected (D3). It expires every
time the extractor changes, invites per-extractor special pleading, and contradicts D11's own
requirement that deterministic extraction pass the same contract.

**Write derived values into the existing job columns.** Rejected (D16). Erased by `_apply_updates`
on the next ingestion, and in the `requirements` case also a `content_hash` feedback loop.

**Extract during eligibility evaluation instead of ingestion.** Rejected (D21). Turns an
`O(churn)` cost into `O(jobs × candidates × requests)` and puts model latency on the request path.

**Batch several jobs per extraction request.** Rejected initially (D21). One malformed reply loses
a batch, and an injection in one job reaches another's extraction.

**Overload `extract_resume` rather than add an operation.** Rejected (D13). Destroys the
signature-as-privacy-boundary property that two merged ADRs depend on.

**Commit the raw fetched descriptions as fixtures.** Rejected (D23) on licensing, not privacy.

---

## Consequences

**Positive.**

- Live jobs become evaluable for the first time, through a path that cannot fabricate a requirement.
- `NOT_ELIGIBLE` becomes a *stronger* guarantee than it is today: explicitly backed by something the
  employer published structurally (D2).
- Explainability improves beyond the current baseline — a derived requirement can show the source
  sentence it came from, which **no curated requirement can do today** (D20).
- The authority rule survives every future change of extraction technology (D3).
- The capability is reversible with no migration back (D27).

**Negative, and accepted deliberately.**

- **Recall is unmeasurable without labelled data.** A missed requirement yields `UNKNOWN`, which is
  indistinguishable from "the job stated nothing". Safe, and silently incomplete.
- **Condition 5 carries most of the risk.** Locating a span proves the extractor did not invent
  text; it does not prove the text was read correctly. Most of the engineering difficulty lives here.
- **More verdicts move to `NEEDS_REVIEW` and `LIKELY_ELIGIBLE`.** Under D2 and D4, a live job with a
  derived failing requirement produces `NEEDS_REVIEW` rather than a crisp rejection. That is the
  honest reading of the evidence available, and it is a worse user experience than a wrong
  certainty would be.
- **Real cost and real latency at ingestion**, neither yet measured.
- **A third provenance class is a permanent increase in system complexity.** Every future
  requirement type now needs a provenance answer, not just a parsing answer.
- **The committed fixture corpus is deliberately weaker than the real data** (D23), so some
  contradiction cases are exercised only locally.

---

## Testing implications

Required before the capability is enabled. The project's established discipline applies: pin the
behaviour, then mutate to prove the test has teeth.

**Evidence verification**

- evidence span exists in the proposal
- evidence located in the **pinned normalized text** (D9), not the raw payload
- value ↔ evidence agreement — including the `7.5` inside *"7.5 years of experience"*, which must be
  refused
- semantic requirement type recognised; an unknown type discarded
- `REQUIRED` strength gate — *"CGPA 7.5 preferred"* refused, with the strength reason
- contradiction detection within the window — both D8 cases and the *"this requirement is waived
  for …"* case
- confidence cannot bypass verification: a HIGH-confidence proposal failing any condition is still
  refused
- contradictory proposals for the same type on the same job → neither promoted

**Authority and precedence**

- a `PROSE_DERIVED` `FAIL` never produces `NOT_ELIGIBLE` — the direct D2 test
- **an all-`PASS` evaluation built only from derived requirements does not return plain `ELIGIBLE`**
  — the D4 rule-5 test
- a `SOURCE_STATED` deterministic `FAIL` still produces `NOT_ELIGIBLE`, unchanged
- no new eligibility state appears in any response

**Boundary and privacy**

- no candidate data reaches the extraction path, asserted on the signature
- the mock provider extracts nothing by default
- a **literal zero-call test** for the mock path, in the style QG-002 item 4 already uses
- prompt-injection corpus — *"ignore previous instructions"*, a fake system prompt, an instruction
  embedded inside a requirement sentence, HTML and script content — asserting that **no requirement
  is produced**, not merely that the model resisted

**Storage and ingestion**

- `content_hash` does not include derived extraction output (D17)
- a source refresh does not overwrite derived extraction (D17) — the `_apply_updates` regression
- stale model versions remain detectable from persisted provenance (D18, D22)
- no extraction occurs during an eligibility request (D21)
- an extraction failure does not fail the ingestion run (D26)

**Mutation coverage** — every safety-critical verifier condition must be shown to fail the suite
when removed: drop span location → evidence tests red · drop the value↔evidence check → the
*"7.5 years"* test red · drop the strength gate → the *"preferred"* tests red · drop the
contradiction window → the D8 test red · trust reported confidence → the hallucination tests red ·
remove the data-block markers → the injection tests red.

---

## Implementation sequencing

Documentation only; none of this is built. Each step is mergeable with the capability off, so
nothing changes behaviour until the last.

| # | Step |
|---|---|
| 1 | **ADR-028 D9a amendment** (see below) — the authorization everything else depends on |
| 2 | **ADR-017 additive amendment** — provenance, authority, precedence, and the R-4 wording |
| 3 | **Evidence and provenance types + the deterministic verifier** — pure functions, no AI, no persistence, mutation-tested. Built *before* anything produces input for it |
| 4 | **`extracted_requirements` storage** and its migration (D16–D19) |
| 5 | **Deterministic extractors** (D11) behind the verifier |
| 6 | **Engine boundary** (D20) and the amended precedence (D4) |
| 7 | **Provider operation + mock** (D13, D14), with the zero-call test |
| 8 | **Gemini provider migration** to `gemini-3.8-flash` (D15), prompt and injection corpus — still disabled by default |
| 9 | **Fixture fetch and derived corpus** (D23) |
| 10 | **Enable on live Greenhouse** behind explicit configuration, with a measured first run |

**Go conditions before step 8 or any live extraction:** steps 1–3 merged · the verifier pure and
mutation-tested · the pinned-text rule tested against `collapse_whitespace` · mock extracts nothing
and the zero-call test passes · the model resolved and the deprecated sampling parameters removed ·
the injection corpus red before the data-block boundary exists.

**No-go, at any point:** extraction per eligibility request · confidence admitted as evidence ·
unverified extraction creating a hard failure · candidate data in the extraction request · skills or
deadlines folded in · ADR-028 D9 modified silently or "clarified" by an implementation PR · derived
values written into a hashed or source-updatable field · `gemini-2.0-flash` still configured when
Gemini is enabled.

---

## Relationship to earlier ADRs

**Nothing in this document amends another ADR.** The two amendments below are required, additive,
and belong to their own PRs.

### ADR-028 — a later additive **D9a** amendment is required

D9 currently reads, in part: *"No requirement may be invented, inferred, defaulted or AI-extracted
into existence."* Only the fourth verb is reached.

- **`invented`, `inferred` and `defaulted` are preserved verbatim.** Evidence verification does not
  weaken any of them, and an unverifiable reading remains an inference.
- **`AI-extracted` is narrowed** to *AI-extracted **without verified source evidence***, with D6's
  eight conditions named as the qualifying contract.
- **ADR-028 open OD-6 is resolved by this ADR.**
- The Alternatives entry rejecting prose extraction is **marked superseded, with its reasoning
  retained** — it is the record of why the bar sits where D6 sets it.
- **D19's `gemini-2.5-flash` selection is superseded by `gemini-3.8-flash`** (D15).
- The Consequences statement predicting that live jobs *"will evaluate to `UNKNOWN` /
  `NEEDS_REVIEW`"* is **factually wrong** and should be corrected to `ELIGIBLE`, independently of
  everything above.

### ADR-017 — a later additive amendment is required

- **Source-stated versus prose-derived authority**, and `NOT_ELIGIBLE` requiring a `SOURCE_STATED`
  deterministic `FAIL` (D2).
- **Precedence rules 2, 4 and 5** as set out in D4.
- **`RequirementResult` gains provenance and evidence** so D2 is auditable from the response (D20).
- **R-4's disclosure wording**, which names only *"free-text requirement notes"* and is already
  narrower than the merged PR #54 behaviour covering description text. This half is independent of
  ADR-030 and could ship alone.

### Unchanged and reaffirmed

**ADR-003** — deterministic before probabilistic, strengthened: Phase 1 routes comparable numbers
through plain code, and AI is reserved for what rules genuinely cannot resolve. **ADR-007** — the
no-fabrication rule, whose verify-against-source mechanism this ADR reuses. **ADR-018** — the five
requirement types and the anti-ontology boundary, both intact (D12). **ADR-019** — unchanged; field
relatedness remains the only eligibility question AI answers, and extraction is not an eligibility
question. **ADR-020 / ADR-022** — matching and recommendation behaviour unchanged (D20).
**ADR-011 / INV-1** — no candidate persistence (D24). **ADR-026** — cost accounting applies; the
candidate-free caching rule is satisfied, since nothing here derives from a candidate.
**ADR-029** — employment type is never inferred, including by this capability.

---

## Open implementation notes

**These are not owner decisions.** They are consequences of decisions already made, to be fixed by
the implementing PR with evidence rather than guessed here.

1. **The contradiction-window constant.** A default of 300 characters each side satisfies both D8
   cases; the final value should be set from the corpus (D9).
2. **Exact schema** for `extracted_requirements` — columns, types, constraints, and whether
   `(job_id, content_hash)` becomes the key or an index (D19).
3. **The typed shape** of the derived-requirement collection passed to evaluation, and of
   `RequirementResult`'s new provenance and evidence fields (D20).
4. **The re-extraction CLI command name**, following the `seed-catalogue` convention (D22).
5. **How much context travels with each committed fixture fragment**, bounded by D23's artifact
   policy and by the contradiction window.
6. **Whether a deterministic extractor's result is labelled `DETERMINISTIC` or a new
   `EvaluationMethod` value** — immaterial to authority under D3, which keys on provenance, but it
   must be chosen deliberately and must not re-enable the rule-5 failure D4 closes.

---

## Revisit conditions

- **Measured extraction precision exists** on a labelled corpus — reopens D2, the `NEEDS_REVIEW`
  cap.
- **A source begins publishing structured criteria** that were previously derived — needs a
  precedence rule for source-stated superseding derived.
- **A second live source** (Lever, Ashby) with materially different prose conventions — may reopen
  D11's deterministic scope.
- **The configured model changes again** — reopens D15 and triggers D22's explicit re-extraction.
- **Condition 5 proves unachievable to a useful standard** — reopens the whole of D6, and with it
  OD-1.

---

## Owner decisions

**All resolved.** Decided by the project owner across the ADR-030 gates, 2026-10-02.

| # | Decision | Resolution |
|---|---|---|
| **OD-1** | Authorize extraction from prose | **APPROVED**, only through the evidence-verification contract (D6). ADR-028 D9 must not be weakened implicitly; a D9a amendment is required. |
| **OD-2** | May extraction create `NOT_ELIGIBLE`? | **PROVENANCE-BASED AUTHORITY.** Any prose-derived requirement is capped, equally for deterministic and AI extraction (D1–D4). No new state. |
| **OD-3** | Persistence of provenance | **PERSIST** requirement, evidence text, extractor identity, model/version, timestamp. Offsets are not authoritative (D18, D9). |
| **OD-4** | Deadlines | **SEPARATE** — outside ADR-030 (D23a). |
| **OD-5** | Strength | **ONLY `REQUIRED` gates**, and it is the only strength D6 condition 7 admits. `PREFERRED` and `INFORMATIONAL` are disclosed only. `CONDITIONAL` never creates a deterministic hard failure and, because no promotion path admits it, resolves within this ADR to **disclosed only**; any `NEEDS_REVIEW` routing would need its own decision (D10). |
| **OD-6** | Gemini model | **`gemini-3.8-flash`**, with the deprecated sampling parameters removed. No configuration change here (D15). |
| **OD-7** | Fixture corpus | **ONE controlled live fetch authorized; DERIVED CORPUS committed**, raw stays local (D23). |
| **OD-8** | Trigger and re-extraction | **INGESTION-TIME ONLY; HYBRID re-extraction** — content change routine, version change explicit (D21, D22). |
| **OD-9** | Phase-0 disclosure | **CONFIRMED** shipped in PR #54 (`85d574d`). Not modified by this ADR. |
| **OD-10** | Deterministic first | **APPROVED.** CGPA + scale, graduation year, backlogs. Same contract applies (D11, D12). |
| **Storage** | Where derived requirements live | **SEPARATE `extracted_requirements` TABLE**, outside the source update path and the content hash (D16–D19). |

**No new owner decision is created by this ADR.** ADR-028's remaining open decisions and Week 9B's
seven remain open and untouched.

> **Numbering note.** These OD numbers belong to the ADR-030 gates and are **not** ADR-028's
> OD-1 … OD-7. ADR-028's own **OD-6** — the structured-eligibility gap — is resolved by this ADR as
> OD-1 above. ADR-030's OD-6 is the Gemini model.

---

## Enforcement

Every PR in the sequence above is checked against this ADR at review: no requirement promoted
without all eight conditions (D6), no confidence admitted as evidence (D7), no `PREFERRED` or
`CONDITIONAL` statement gating eligibility (D10), no prose-derived `NOT_ELIGIBLE` (D2), **no
all-`PASS` derived evaluation returning plain `ELIGIBLE`** (D4), no new eligibility state (D5), no
authority tied to extractor technology (D3), no ontology, skill or degree-level inference (D12), no
`extract_resume` overload (D13), a mock that extracts nothing with a literal zero-call test (D14),
no derived value in a hashed or source-updatable field (D16, D17), no extraction during an
eligibility request (D21), no candidate data anywhere in the path (D24), the description always a
labelled untrusted data block (D25), and an ingestion run that survives an extraction failure (D26).
