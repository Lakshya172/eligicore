# Standard — AI Integration

> **Binding ADRs:** ADR-003, ADR-004, ADR-007 · **Invariants:** INV-2, INV-5, INV-9

---

## 1. Provider abstraction is absolute

**Business logic never imports a vendor SDK.** All AI access goes through
`app/ai/providers/base.py`.

- Concrete providers live only in `app/ai/providers/`.
- Provider selection is configuration (`ELIGICORE_AI_PROVIDER`), never a code branch in a
  service.
- A vendor import anywhere under `app/services/` is a review failure, no exceptions.
- The interface expresses the least common denominator across providers. Resist leaking a
  provider-specific feature through it; that is how lock-in returns.

## 2. The mock provider is mandatory

It ships **in the same change as the interface**, not later.

- The full test suite runs with **no network and no API key**. This is a stated dossier success
  criterion, not a convenience.
- The mock returns deterministic, controllable responses — including malformed ones, so error
  paths are testable.
- The mock counts calls. Several required tests assert that *no* AI call was made (INV-2).

## 3. AI is called only where deterministic code cannot decide

Before adding an AI call, answer: *what exactly can code not determine here?*

- Comparing numbers, dates, or enum values → deterministic. Always.
- Extracting predictable patterns — emails, phone numbers, dates → spaCy fallback first.
- Interpreting genuinely ambiguous natural language → AI.

Spending an AI call on a comparison is slower, costlier and less reliable than `>=`.

## 4. AI output is untrusted input

Provider responses can be malformed, truncated, contain values outside the allowed enum, or
ignore the requested schema entirely.

- **Validate every response against a Pydantic model before it touches business logic.**
- A response failing validation yields `NEEDS_REVIEW` — never a silent pass, never an unhandled
  crash, never a default that happens to be permissive.
- Never `eval`, never trust a returned value as a control-flow decision without validation.
- Constrain the model to a structured output format; do not parse prose with regex.

## 5. AI may never override deterministic verdicts

Restating INV-2 because it is the rule most likely to erode: the AI stage must be
**structurally unable** to reach a requirement that already failed deterministically.

Enforce it in control flow. A prompt instruction saying "do not override hard failures" is not
an implementation — it is a hope. Assert it with a test on the mock's call count.

## 6. Prompts are files

Under `app/ai/prompts/`, one prompt per file, loaded by name.

Inline prompt strings are undiffable, untestable, and get edited by accident during unrelated
refactors. Version prompts alongside the code; a prompt change is a behaviour change and gets
reviewed as one.

**Prompts populated with profile data are sensitive** — they must not be logged (INV-4).

## 7. Cost control

- Rules run before AI (ADR-003). This is the primary cost control.
- Cache results where inputs are stable.
- Log AI usage and cost in **one place** — the service layer wrapper, not at each call site.
  Log token counts and cost, never prompt or response content.
- Batch where the provider supports it.
- Cap retries. An unbounded retry loop against a paid API is a financial bug.

## 8. Truthfulness (ADR-007)

Generated application content is checked **claim by claim** against the candidate profile
supplied in the request.

- A claim about a skill, project, duration or achievement must be traceable to real profile
  data.
- Untraceable claims are flagged or removed **before the content is returned** — not surfaced
  as a warning for the caller to ignore.
- Validation is part of the generation pipeline, not an optional post-step.
- Reasonable paraphrase of real data is acceptable; new facts are not. Getting this line right
  is the hard part — err toward removal, and test both directions.

## 9. Confidence reporting

Every AI-produced verdict carries `method: "ai_reasoning"` and an explicit confidence level.

Confidence reflects how much the system trusts the determination — not how strongly the model
phrased its answer. A model is fluent at every confidence level; do not read certainty from
tone. Where the provider offers no calibrated signal, MEDIUM is the honest default for an
interpretive judgment.
