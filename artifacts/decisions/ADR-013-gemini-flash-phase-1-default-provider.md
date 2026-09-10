# ADR-013 — Gemini Flash as the Phase 1 default AI provider

**Status:** Accepted · **Date:** 2026-09-10 · **Decided by:** project owner
**Type:** Provider selection (resolves **C-4** / deferred decision **D-1**)
**Bounded by:** ADR-004 (AI provider abstraction) · **Enforces:** INV-5

---

## Context

ADR-004 established that all AI access goes through one abstract interface, and listed OpenAI,
OpenRouter, Anthropic and local models as interchangeable behind it. It deliberately left the
Phase 1 default undecided, because the abstraction does not need to know.

That decision could not be deferred past Week 2: the resume parser needs a concrete provider,
and one had to be chosen.

## Decision

**Google Gemini Flash is the Phase 1 default AI provider.**

It is the *concrete implementation for Phase 1*, not a permanent architectural dependency. The
provider abstraction from ADR-004 remains mandatory and unchanged.

## Reasoning

Grounded in this project's stated requirements, not in comparative benchmarks — **no benchmark
was run, and none is claimed**:

- **The workload is structured extraction, not open-ended generation.** Resume parsing converts
  text into a fixed schema. A fast, inexpensive model is the right shape for it; ADR-003's
  deterministic-first rule already keeps AI off anything a comparison operator can settle.
- **Cost control is a stated dossier risk** (§16: "AI API costs accumulate"). A Flash-tier model
  is the low-cost option within its family, which matters for a solo project on a free-tier
  deployment.
- **The dossier requires structured output** (§7 step 2 — profile fields with per-field
  confidence). The Gemini API supports a declared response schema, which reduces reliance on
  parsing prose.
- **It is the owner's decision.** This ADR records it; it does not relitigate it.

## Constraints that remain in force

1. **The abstraction is mandatory.** No service, router or schema may import Gemini code or a
   Gemini SDK. All access goes through `app/ai/providers/base.py` (INV-5).
2. **The mock provider is mandatory.** The full test suite runs with no credentials, no network
   and no paid call. This is a dossier success criterion (§17), not a convenience.
3. **Credentials are never committed.** `ELIGICORE_GEMINI_API_KEY` lives in `.env`, which is
   git-ignored. `.env.example` documents the variable name with an empty placeholder.
4. **The model identifier is configuration, not code.** `ELIGICORE_GEMINI_MODEL` is an
   environment variable so the model can change without touching source.
5. **The provider is replaceable.** Swapping to another provider means adding one class and
   changing `ELIGICORE_AI_PROVIDER`. Nothing in the resume-processing or service layer changes.

## Configuration

Following the project's established `ELIGICORE_` prefix (dossier §1):

| Variable | Purpose |
|---|---|
| `ELIGICORE_AI_PROVIDER` | `mock` (default) or `gemini`. Selects the provider at runtime. |
| `ELIGICORE_GEMINI_API_KEY` | API key. Never committed. Absent by default. |
| `ELIGICORE_GEMINI_MODEL` | Model identifier, e.g. `gemini-2.0-flash`. Configurable. |
| `ELIGICORE_AI_TIMEOUT_SECONDS` | Request timeout. |
| `ELIGICORE_AI_MAX_RETRIES` | Retry cap — an unbounded retry loop against a paid API is a financial bug. |

**The default is `mock`, not `gemini`.** An unconfigured checkout, and CI, must never be able to
make a paid call by accident.

## Sub-decision: HTTP client rather than the Google SDK

The provider calls the official Gemini REST API through **httpx**, rather than adding the
`google-genai` SDK.

**Why:** the dossier's approved stack already names httpx for exactly this purpose — "async
capable, needed for calling AI provider APIs efficiently" (§9). Adding an SDK would introduce a
dependency outside the approved stack, which `standards/code_quality.md` §3 requires
justification for. The REST API is officially supported, and calling it directly gives explicit
control over timeouts and retries, which the cost constraints above depend on.

**Cost of this choice:** request and response shapes are hand-maintained, so a breaking API
change would need a code update rather than an SDK bump. That cost is contained — it lives
entirely inside `app/ai/providers/gemini.py`, which is the only file that knows Gemini exists.

This sub-decision is reversible without touching anything outside that one file.

## Unverified

**No live Gemini call has been made from this environment** — no API key is configured, and the
test suite is required to run without one. Consequently:

- The default model identifier `gemini-2.0-flash` is a **configured default, not a verified
  one.** Confirm the current identifier against Google's documentation before first live use.
- The request/response shape follows the documented REST contract but has not been exercised
  against the live service.

Stated plainly rather than glossed: first live use is an integration step that still has to
happen, and it belongs to whoever configures a key.

## Revisit conditions

- A technical blocker making Gemini Flash unusable for structured extraction.
- Extraction quality proving inadequate against real resumes (dossier §16 rates parsing accuracy
  a medium risk).
- A cost or availability change.

Any of these is a configuration change plus one new provider class — not a refactor. That is the
whole point of ADR-004.

## Enforcement

INV-5 · QG-003, QG-008 · `reviewers/ai.md`, `reviewers/security.md` · `standards/ai.md`
