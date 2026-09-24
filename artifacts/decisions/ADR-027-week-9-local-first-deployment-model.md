# ADR-027 — Week 9 local-first, deploy-when-needed

**Status:** Accepted · **Date:** 2026-09-24 · **Type:** Design ruling (Week 9 design gate, revised)
**Source:** dossier §8.1a, §8.1b, §9, §15 (Week 9), §17, §18
**Decided by:** project owner, Week 9 design gate and one scope revision
**Enforces:** INV-1, INV-4, INV-5, INV-7, INV-10, INV-12 · **Refines:** ADR-009, ADR-016
**Supersedes in part:** dossier §15 row 9 and §17 (see § Dossier deviation) — **no earlier ADR is
amended or superseded**
**Rules on:** W9-D1, W9-D8, W9-D9, W9-D10, W9-D11 · **Leaves open:** W9-D2..W9-D7, W9-D12

---

## Context

Dossier §15 gives Week 9 one row: focus *"Documentation and deployment"*, deliverable *"Live public
API with full documentation"*. §17 lists *"Live, publicly accessible deployed API"* among the
portfolio success criteria, and §9 names **Render / Railway** — *"Free tiers sufficient for this
scale. Produces a live public URL."* Those three statements are the whole of the dossier's
deployment authority. The dossier never mentions rate limiting, HTTPS, a domain, uptime,
monitoring, containers, CI/CD or health-check configuration.

**The owner's actual intended operating model is different, and was stated at the Week 9 design
gate.** EligiCore is primarily a personal application. Its normal operating mode is a terminal, a
`localhost` server, local environment variables, a local SQLite database and local AI-provider
configuration. There is no hosting requirement and no continuous-public-availability requirement
for ordinary personal use. Deployment is something the owner may do later, once, when they want to
show the system to another person.

This is not a reinterpretation of the dossier and is not recorded as one. The dossier says "live
public API"; the owner says "optional". **The gap is real, deliberate and owner-approved**, and
this ADR exists to record it rather than let a later reader discover a roadmap row that was quietly
not done.

**One distinction matters and is easy to get wrong.** Dossier §8.1a's "local-first" is about *where
personal data rests* — on the user's device, with the backend as *"a processing service, not a
personal data store."* It says nothing about where the backend process runs. The ruling below is
about *where the server runs*. The two are different axes. §8.1a does not authorize this decision;
it is merely consistent with it, and citing §8.1a as the justification would be a misreading.

Week 8 is closed at Checkpoint 8 (`9aba1f2b1007b0931ec9adc39afb88b15eaa2c14`), and `main` is
`a0fbfb8a433b0881d6456d5a7b5df6a5892defc5`. This ADR is recorded before any Week 9 implementation
exists.

## Decision

**D1 — EligiCore's normal operating mode is local.** The supported everyday configuration is a
terminal, a `localhost` FastAPI server, local `ELIGICORE_`-prefixed environment variables, a local
SQLite operational database and a locally configured AI provider. **No hosting is required for
personal use, and no public availability is required for normal use.** The terminal is a
first-class operating mode, not a development fallback.

**D2 — Week 9 is two explicit operational stages.** **9A — Local Production Readiness** is the
immediate planned work and produces a stable checkpoint. **9B — Deployment and Sharing** is
optional, owner-triggered, and may be deferred indefinitely or never performed. **9B is not
required for the owner's ordinary use of EligiCore.**

**D3 — 9A scope is fixed to seven objectives.** OpenAPI status correction · PostgreSQL
compatibility validation · production configuration validation · secret-handling validation ·
privacy and logging validation · local production-like end-to-end verification · current
documentation and reproducible deployment instructions. Nothing else is 9A work.

**D4 — 9B scope is fixed to six objectives.** Hosting on a chosen platform · hosted PostgreSQL ·
host environment configuration · a deliberate access and sharing mechanism · deployment
verification against QG-007 · the final deployment checkpoint. Each is blocked on an owner decision
listed under § Open decisions.

**D5 — One application, two execution contexts.** There is **no separate "hosted version"**. Local
and hosted execution run the same FastAPI application, the same services, the same API contracts
and the same provider abstraction. Deployment changes environment variables, the database
connection, the hosting and network layer, secrets and external accessibility — and nothing else.
A code path that exists only when hosted is a defect under this rule.

**D6 — Core behaviour is identical across contexts; operational behaviour is not.** For the same
code revision, configuration values, database contents, AI provider and request, both contexts must
produce the same response body, status code, verdict, score, ordering, OpenAPI document and log
record content. The differences are operational only and are enumerated in § Local versus hosted.
**Localhost does not reproduce hosting perfectly**, and 9A does not claim it does: 9A retires
configuration and compatibility risk, not platform risk. That residue is what 9B verification
exists for.

**D7 — Database architecture is kept unchanged.** `jobs`, `ingestion_state`, Alembic and SQLAlchemy
all stay. **SQLite remains the ordinary personal and local development database.** **PostgreSQL
compatibility is validated during 9A**, locally, satisfying §9's *"Alembic migrations and
PostgreSQL compatibility must still be validated before production deployment"* — and satisfying it
whether or not deployment ever happens. Hosted PostgreSQL is relevant only if 9B is activated.
**No migration is written in Week 9**: the head stays `b3e8d2c61a47` and the three existing
migrations are unchanged. If PostgreSQL validation fails, a corrective migration is new,
unauthorized work: stop and report rather than write one inside 9A.

**D8 — Candidate, application, evaluation and package persistence remains prohibited.** INV-1 and
ADR-011 are untouched, and no Week 9 statement in the dossier authorizes an exception. The CI
registered-table guard stays as written.

**D9 — Live Gemini application generation remains excluded.** It is not in 9A and not in 9B.
`GeminiFlashProvider.generate_application_content` stays the stub it is today: it raises
`AIProviderUnavailableError`, holds no transport, prompt, payload or key, and reads no candidate
data. Selecting Gemini continues to degrade honestly — HTTP 200, `NOTHING_VERIFIABLE`,
`AI_GENERATION_UNAVAILABLE`. **ADR-025 and ADR-026 remain authoritative and unamended**, including
ADR-026 D8's structural exclusion of generation-path token, length and cost logging. Live
generation may enter scope only by a separate owner decision carrying **its own ADR and its own
explicit privacy decision** — ADR-026 makes that privacy decision non-inheritable, because the
current exclusion is the absence of a mechanism rather than a disabled flag.

This resolves **W9-D1**. ADR-025's *"Week 8/9"* pointer expired when Week 8 closed without it; it is
now deferred with no week assigned, rather than left as implied scope.

**D10 — The stale OpenAPI status string is corrected in 9A.** The published *"Weeks 1–6 of a
10-week build are complete."* becomes accurate for Weeks 1–8. This touches `app/main.py` and the two
merged tests that pin the sentence (`tests/test_full_flow.py`,
`tests/test_tracker_export_endpoint.py`), which are re-aimed and **strengthened** to reject stale
and premature wording alike. **No route is added and no schema changes**; the route count stays
**10** and a contract test asserts the OpenAPI document is otherwise structurally identical.
`/api/v1/matching/score` and `/api/v1/jobs/ingest` **remain deferred** (C-25, ADR-023 §11, ADR-024)
and are not revived.

**D11 — §17's "every endpoint" means every implemented endpoint.** *"Interactive API documentation
demonstrating every endpoint"* is read as every endpoint currently implemented and supported by the
project's API surface — not every row of §11's table. Reading it the other way would silently pull
two deliberately deferred endpoints into Week 9. This resolves **W9-D8**.

**D12 — The current documentation structure is kept.** §8.2's folder listing includes a `docs/`
directory that has never existed. **No empty `docs/` directory is created for appearance.** The
substance of §17's documentation criteria is carried by `README.md`, `CONTRIBUTING.md`, `context/`
and the ADR set in `artifacts/decisions/`. If a genuine need for a standalone `docs/` tree appears
later, it is a change with its own justification. This resolves **W9-D9**.

**D13 — Authentication stays deferred to Phase 4.** Dossier §18 assigns *"Authentication, per-user
isolation, notification digests, deadline reminders"* to Phase 4. **No multi-user account system is
invented for 9A**, and none for 9B by default.

**D14 — The normal instance is not public, and sharing needs its own decision.** A locally run
instance is bound to the owner's machine and is not publicly reachable. When sharing is eventually
implemented, **the access-control mechanism is a separate, explicit owner decision**.
**An unauthenticated public API is not assumed acceptable merely because deployment became
optional** — optionality changes when the question is asked, not whether it must be answered. A
shared URL with no access control and a live AI provider is the same exposed budget it would have
been under the original plan.

**D15 — Rate limiting is unresolved and nothing is invented here.** QG-007 item 10 requires
*"Rate limiting active on AI-cost-exposed endpoints"* and QG-007 has **no warning tier**, so an
unmet item is a FAIL. The dossier mentions rate limiting nowhere. ADR-025 D14 and ADR-026 both
assign it parenthetically to "Week 9". **No limit value, window, keying strategy, storage backend
or mechanism is chosen in this ADR.** Because 9A is not publicly reachable, the cost exposure
QG-007 is written against does not exist during 9A; **rate limiting and AI spend bounds must
receive an explicit owner decision before 9B**. QG-007 item 11 is already satisfied:
`/eligibility/check` caps at 50 ids and `/recommendations` caps its default scope at 50 with
disclosure.

**D16 — The deployed AI provider is a separate decision.** Locally, `mock` remains the default —
an unconfigured checkout and CI must never be able to make a paid call by accident — and `gemini`
remains selectable by configuration alone through the existing abstraction (ADR-004, ADR-013,
INV-5). **Production is not switched to Gemini automatically.** Provider selection for any deployed
instance is an owner decision taken at 9B.

**D17 — The catalogue architecture is unchanged.** The operational `jobs` table, the curated
adapter and `python -m app.cli seed-catalogue` all stay. **The database is not replaced by live web
fetching**, `/api/v1/jobs/ingest` is **not** added, and live web job adapters remain deferred to
Phase 3 unless the owner explicitly changes that.

**D18 — Live Gemini smoke testing is optional and not a 9A requirement.** Exercising the two
implemented paths — `extract_resume` and `assess_field_relatedness` — against the real service
needs a real key and real spend, and is an owner and integration activity. It is **not a required
9A implementation item**. The consequence is recorded honestly rather than hidden: until someone
runs one real call, the live AI path and the configured model identifier remain unverified. This
resolves **W9-D10**.

**D19 — Deployment steps that require credentials are owner-performed.** Account creation, entering
host credentials, provisioning third-party hosted services, and storing real production secrets are
**performed by the owner**. An assistant may prepare every artifact, document every step precisely,
and verify the result once it exists, but may not create accounts or enter credentials. Any 9B plan
that assumes otherwise is wrong, and recording it here is cheaper than discovering it at the last
slice.

**D20 — 9A is the immediate work; 9B waits for intent.** Week 9A proceeds now. Week 9B is performed
only when the owner actually wants to share the application. **Week 10 remains buffer and final
polish** — slippage absorption, not a destination for unplanned features. This resolves **W9-D11**.

## Dossier deviation

**This is a deliberate, owner-approved deviation from the dossier, recorded rather than
interpreted.**

| Dossier statement | Effect of this ADR |
|---|---|
| **§15 row 9** — focus *"Documentation and deployment"*, deliverable *"Live public API with full documentation"* | **Partially superseded for Week 9.** "Documentation" stands unchanged and is 9A work. "Live public API" ceases to be a Week 9 exit requirement and becomes optional, owner-triggered 9B work. |
| **§17 Portfolio** — *"Live, publicly accessible deployed API"* | **Superseded as a Week 9 exit criterion.** It remains a valid future criterion the project may satisfy at any time; it no longer gates completion of Week 9A. |
| **§9 stack** — Render / Railway, *"Produces a live public URL."* | **Not contradicted — deferred.** The dossier names the platforms but never says when. They are used in 9B, if 9B happens. |

**Three statements are explicitly not in conflict**, and must not be cited as though they were:

- **§9's PostgreSQL precondition** survives intact and is *strengthened*: validation moves into 9A
  and happens whether or not deployment ever does.
- **§8.1a local-first** concerns where personal data rests, not where the process runs. See
  § Context.
- **§18 Phase 4** keeps authentication deferred; optional deployment does not move it.

**The original criterion is not deleted from history.** §17's live-public-API bullet stays in the
dossier exactly as written, and the dossier is not modified by this ADR. **Deployment can still be
performed later** — 9B exists precisely so that it can be, without renegotiating scope. The honest
consequence, stated plainly: under this ruling the §17 live-public-API criterion can remain unmet
indefinitely without Week 9 being incomplete. That is a genuine reduction against the written
source, it is the owner's call, and it is recorded as a deviation rather than as an interpretation.

## Local versus hosted

**Identical for the same code revision, configuration values, database contents, AI provider and
request:** every response body, status code, verdict, score and ordering; the OpenAPI document; and
the content of every log record.

**Operational differences, expected and non-defects:**

| Dimension | Local | Hosted |
|---|---|---|
| Accessibility | `localhost` only | Externally reachable |
| Transport | Plain HTTP | HTTPS/TLS terminated at the platform edge |
| Address | Loopback and port | A platform domain |
| Logs | Terminal stdout | Platform log stream, plus the platform's own access log — **outside the application's control, therefore checked rather than assumed** (§8.1b) |
| Filesystem | Durable local disk | Ephemeral on free tiers; a SQLite file does not survive a redeploy |
| Process lifecycle | Owner-controlled | Platform-controlled restarts |
| Cold starts | None | Free tiers idle out; the first request may take tens of seconds |
| Network boundary | None | An external boundary with its own failure modes |
| Availability | The owner's machine | The platform's availability |
| Corpus cache (ADR-026 D7) | One process, one bounded cache, exactly as tested | One bounded cache **per worker process**, each correct in isolation — a documented consequence, **not** a licence for a shared or external cache |

## Stage 9A — Local Production Readiness

| Objective | Content | Changes production behaviour |
|---|---|---|
| **9A-1 OpenAPI correction** | D10 above | Response *metadata* only; 10 routes and every operation and schema otherwise byte-identical |
| **9A-2 PostgreSQL validation** | The existing chain `54a85d64881e` → `7c2f1a9b4d30` → `b3e8d2c61a47` against a local PostgreSQL: `upgrade head`, insert representative rows, `downgrade`, re-`upgrade`, `alembic check`, with the table set and CHECK constraints asserted intact. The specific risk is `op.batch_alter_table`, used by all three migrations and never executed against PostgreSQL | No — verification only |
| **9A-3 Production configuration validation** | Evidence, as tests rather than prose, that `ELIGICORE_ENVIRONMENT=production` yields `debug` false and suppressed tracebacks. **No new setting is invented**: a QG-007 item unmeetable with the existing surface is a finding to report, not a licence to add configuration | Configuration behaviour only |
| **9A-4 Secret-handling validation** | Repository **and git-history** secret scan; `.env` ignored; `.env.example` carrying names with placeholder values only; no secret in the OpenAPI document | No |
| **9A-5 Privacy and logging validation** | Re-verify the Slice 8C guarantees under a production-like configuration: no PII across the marker sweep, no `candidate_id` in any cost record, the database byte-identical across a logged request | No |
| **9A-6 Local production-like verification** | Local PostgreSQL → `alembic upgrade head` → seed via the existing CLI → run FastAPI locally → verify every implemented route → `/docs` → `/openapi.json` → logs and privacy → configuration under the production environment setting → AI-provider configuration → failure handling → the rollback and downgrade migration path. **The rollback path is executed, not merely documented** — a rollback path that has never run is a hypothesis | No |
| **9A-7 Documentation** | README current and stranger-runnable in under ten minutes, re-timed from a fresh clone; deployment instructions written and reproducible **without being executed**; the local-first operating model documented as the normal mode | No |

**9A success criteria:** a local production-like environment verified · PostgreSQL compatibility
verified · documentation current · OpenAPI current · configuration and secret handling verified ·
privacy and logging verified · deployment instructions reproducible.

## Stage 9B — Deployment and Sharing (optional)

Hosting on the chosen platform · a shared URL · hosted PostgreSQL · host environment configuration ·
a deliberate access mechanism (D14) · deployment verification · QG-007 satisfied in full.

**9B success criteria:** all 9A requirements complete · the owner deliberately deploys · the hosted
instance is reachable · hosted configuration verified · QG-007 satisfied.

## Checkpoint structure

| Checkpoint | Title | Recorded when | Rollback character |
|---|---|---|---|
| **9A** | **Week 9A — Local Production Readiness** | All 9A objectives verified. **The stable checkpoint for the local-first product** — the state the owner actually runs | Fully revertible by `git revert`; code, tests, configuration evidence and documentation only |
| **9** | **Week 9 — Deployment and Sharing** | Only after the owner deliberately deploys, the hosted instance is verified reachable, hosted configuration is verified, and QG-007 passes in full | **Not a git-only rollback** — recovery means redeploying a previous commit and reverting host configuration |

**Neither checkpoint is created by this ADR.** Checkpoint 8 remains `Stable — current`.

Two rather than one, and the local-first ruling strengthens rather than weakens the case: 9A and 9B
are now separated by time and intent as well as by risk. 9B may never happen, or may happen months
later. A single Checkpoint 9 would leave the local-first product — the thing the owner uses daily —
with no checkpoint of its own. Slice 7A's precedent points the same way: it recorded none because a
validator with no caller is not a state worth rolling back to. The inverse holds here.

## Open decisions

None of these blocks 9A. All of them block 9B.

| # | Decision | Why open | Consequence of each reading |
|---|---|---|---|
| **W9-D2** | Render or Railway | D-3 in `context/decisions.md`, an owner choice | Determines manifest format and database offering; no application code impact |
| **W9-D3** | Hosted PostgreSQL or hosted SQLite | Free-tier Postgres may be time-limited; free-tier filesystems are ephemeral | SQLite on a free tier loses the catalogue on every redeploy and contradicts ADR-009 |
| **W9-D4** | Rate-limiting mechanism and values | QG-007 #10 mandates what the dossier never mentions (D15) | Either supply values with an ADR, or amend QG-007 by explicit decision — never by quiet waiver |
| **W9-D5** | Deployed AI provider (D16) | Not settled by optionality | `mock`: zero cost and zero key exposure, but a shared demo of a mock AI. `gemini`: real, but a shared endpoint spending the owner's budget |
| **W9-D6** | How a hosted catalogue is seeded | `seed-catalogue` is local tooling; an HTTP route is forbidden by C-25 | A one-off release command is simplest; startup seeding is an implicit behaviour change needing authorization |
| **W9-D7** | Is `/docs` public on a shared instance | Currently public by FastAPI default — an unexamined default, not a decision; QG-007 #13 requires deliberation | Either is acceptable *if chosen* |
| **W9-D12** | Access control for a shared instance (D14) | Explicitly separate from Phase 4 authentication | An unauthenticated shared URL is not assumed acceptable |

## Non-goals — deferred or excluded

**Excluded from 9A:** any hosting, public URL or hosted database · account creation or credential
entry · rate-limiting implementation · live Gemini application generation · any live AI call as a
required step · new endpoints · schema changes · new migrations · new dependencies ·
authentication · a standalone `docs/` directory created for appearance.

**Excluded from 9B unless separately decided:** live Gemini application generation ·
authentication (Phase 4) · any access-control mechanism not explicitly ruled · any invented rate
limit.

**Excluded from Week 9 entirely:** `/api/v1/matching/score` · `/api/v1/jobs/ingest` · the spaCy
deterministic fallback · §17 résumé extraction-accuracy measurement · matching or recommendation
tuning · a cost table, ledger, metrics or admin endpoint · Redis or any external cache service ·
`ENGINE_VERSION` or `MATCHING_VERSION` changes · tags and releases · live web fetching in place of
the catalogue.

**Deferred to their existing phases:** frontend and browser-extension autofill (Phase 2) · live
portal and ATS adapters (Phase 3) · authentication, per-user isolation, digests and reminders
(Phase 4) · institutional cohort evaluation (Phase 5).

**Excluded permanently:** auto-submit · browser automation for submission · CAPTCHA, OTP,
anti-bot or identity-verification bypass · server-side candidate, application, evaluation or
package persistence · PII in logs · a generated-prose cache · a candidate-derived cross-request
cache · generation-path token, length or cost logging absent a separate explicit ruling ·
microservices, Kubernetes, message brokers, event buses, multiple databases.

**Not proposed despite being conventional:** monitoring and alerting · uptime SLAs · containers ·
staging environments · load testing · error-telemetry SaaS. The dossier names none of them, and a
locally run personal backend needs none of them.

## Privacy and security invariants

Week 9 introduces **none** of the following, and each is a testable claim rather than an intention:
candidate-data persistence · résumé retention · PII in logs · provider leakage of fields outside the
ADR-025 D10–D12 evidence allow-list · caching of any candidate-derived value · application tracking ·
submission automation · CAPTCHA, OTP or identity bypass.

Every Week 8 boundary remains active and untouched: the ADR-020 §5 cache exception stays narrow and
catalogue-only; the candidate transform stays request-local; the ADR-025 generation boundary remains
authoritative; generation-path usage, length and cost logging remains structurally excluded
(ADR-026 D8); `candidate_id` appears in no cost field and no cache key; the Gemini API key continues
to travel as a header, never in a URL and never in a log.

Dossier §8.1b's deployment-facing rule is the one privacy statement 9A extends rather than merely
preserves: *"Request handling, temporary processing storage, infrastructure-level logs, and error
telemetry must be designed and configured to avoid retaining unnecessary personal data."* Slice 8C
settled the application's own logging; 9A adds evidence for the configuration around it, and 9B
would add the hosting layer.

## Testing and quality gates

**9A testing.** Unit coverage for any configuration helper · the existing offline full-flow test as
the regression anchor with its socket guard intact · an **API contract test** asserting the OpenAPI
document is structurally identical apart from the status string · a **PostgreSQL migration job**
(upgrade, data, downgrade, re-upgrade, `alembic check`, table set and CHECK constraints) runnable in
CI against a service container with no hosted database and no secret · configuration-failure tests
that fail loudly without leaking connection strings · the privacy marker sweep re-run under a
production-like configuration · a repository and git-history secret scan · **executed** rollback
verification · the full suite (currently 1549 passing, 0 failed, 0 skipped) on the release commit.

**Mutation testing.** 9A is largely configuration and documentation, where mutation testing has
little purchase; it applies to genuinely behavioural additions only. If rate limiting is ever ruled
into scope it **is** behavioural and must be mutation-tested — an off-by-one in a limiter is exactly
the defect a passing suite hides. **The existing 230/230 baseline must be re-verified intact, never
assumed.**

**Gates.** QG-001 PASS required · QG-004 PASS required (the OpenAPI description changes; this gate
is what proves nothing else moved) · QG-005 PASS required, no warning tier · QG-006 PASS required
(no new migration, but §9 makes PostgreSQL validation of the existing chain a precondition, and this
gate is where that evidence belongs) · QG-007 **applies to 9B, in full, no warning tier** ·
QG-002 N/A (no eligibility change; `ENGINE_VERSION` untouched) · QG-003 N/A as scoped, and becomes
PASS-required only if live Gemini work is ever authorized · QG-008 N/A. **No QG-009**: QG-007
already covers the deployment surface, including the items the dossier is silent on.

## Migration and dependency impact

**None.** No migration is written; the Alembic head stays `b3e8d2c61a47` with three migrations. No
model changes. No new dependency — `requirements.txt` is untouched by 9A. Tables remain exactly
`jobs` and `ingestion_state`, plus `alembic_version`.

## Rejected alternatives

| Alternative | Why rejected |
|---|---|
| Treat the dossier literally and deploy publicly in Week 9 | Contradicts the owner's actual operating model and incurs hosting and AI-spend exposure for a system nobody else needs to reach yet |
| Silently redefine "deployment" as "runs locally" | The dossier says *"Live public API"*. Reinterpreting that wording to mean localhost would be exactly the silent reconciliation `AGENTOS.md` forbids |
| Edit the dossier to match the new model | The dossier is the authoritative source and is not rewritten to match implementation choices. A deviation is recorded in an ADR; the source keeps its history |
| One combined Checkpoint 9 | Fuses a fully revertible body of work with an irreversible external change, and leaves the product the owner actually runs without a checkpoint of its own |
| Build a separate lightweight "local mode" of the application | Two code paths means two behaviours and a class of defect that only appears in one of them. D5 forbids it |
| Add authentication now, since sharing is foreseeable | §18 places authentication in Phase 4. Building it speculatively is the scope creep §16 rates as the top solo-project risk |
| Pick a default rate limit so QG-007 can pass | An invented limit is a fabricated requirement presented as a decision. D15 keeps it open instead |

## Consequences

**Good.** The work the owner actually needs happens first and completes without depending on a
third-party account, a credential or a spend decision. PostgreSQL compatibility — the oldest
unretired technical risk in the project — is validated earlier than the dossier requires. The
documentation criteria are met on their own merits. Checkpoint 9A gives the daily-use product a
rollback target of its own. Hosting stays available at any later date at the cost of 9B alone.

**Bad, and stated rather than minimized.** §17's live-public-API criterion may remain unmet
indefinitely, so the portfolio claim the dossier envisaged is not yet earned. Platform risk stays
entirely unretired: cold starts, ephemeral filesystems, platform logging and multi-process cache
behaviour are reasoned about here but verified by nothing until 9B runs. The live AI path and the
configured Gemini model identifier remain unverified (D18). And a Week 9 that ends without
deployment will read, to anyone comparing the repository against §15, as an incomplete row — which
is precisely why this ADR exists and why the deviation is recorded in the roadmap-facing documents
as well.

## Revisit conditions

The owner decides to share EligiCore, activating 9B and the seven open decisions · live Gemini
application generation is approved, requiring its own ADR **and** its own privacy decision
(ADR-026 D8) · PostgreSQL validation fails, which is a finding to report rather than a licence to
write a corrective migration · QG-007 item 10 is amended or satisfied, resolving W9-D4 · a genuine
need for a standalone `docs/` tree appears, reopening D12 · Phase 4 begins, at which point
authentication stops being deferred. **None applies today**, and each is recorded here as *not
required* rather than left as implied scope.

## Enforcement

`app/main.py` (OpenAPI status only) · `tests/test_full_flow.py` ·
`tests/test_tracker_export_endpoint.py` · `.env.example` · `README.md` · `alembic/versions/**`
(validated, not modified) · `context/state.md` · `context/workflow.md` ·
QG-001, QG-004, QG-005, QG-006, and QG-007 at 9B · `standards/security_privacy.md` ·
`reviewers/security.md`, `reviewers/qa.md`, `reviewers/documentation.md`, `reviewers/release.md`
