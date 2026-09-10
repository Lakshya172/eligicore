# Reviewer — ai

**Question:** is AI used correctly, bounded, mockable, and structurally unable to override rules?

**Triggered by:** eligibility engine · AI provider or interface · prompts · AI service ·
application preparation · truthfulness validator.

**Reads:** `standards/ai.md` · `standards/eligibility.md` · `ADR-003` · `ADR-004` · `ADR-007`

---

## Responsibilities

- Verify AI cannot override a verified deterministic hard failure (INV-2).
- Verify the provider abstraction holds and no vendor SDK leaks into business logic (INV-5).
- Verify AI responses are validated as untrusted input.
- Verify the mock provider covers the change and the suite runs offline.
- Verify truthfulness validation for generated content (INV-9).
- Verify AI is used only where deterministic code genuinely cannot decide.
- Verify cost controls: caching, retry caps, single-point usage logging.

## Not responsible for

Deterministic rule correctness (→ qa) · endpoint shape (→ api) · secrets (→ security).

## Binary questions

1. Is the AI stage **structurally unable** — in control flow, not by prompt instruction — to
   reach a requirement that already failed deterministically? (INV-2)
2. Is there a test asserting the mock provider was **not called** when a hard constraint fails?
3. Could this AI call have been a deterministic comparison instead?
4. Is every provider response validated against a Pydantic model before touching business logic?
5. Does a malformed, truncated, or out-of-enum response yield `NEEDS_REVIEW` rather than a
   silent pass or a crash?
6. Does the mock provider support this change, and does the full suite pass with **no network
   and no API key**?
7. Are prompts in files under `app/ai/prompts/` rather than inline strings?
8. Are prompts containing profile data kept out of logs? (INV-4)
9. Is every AI-produced verdict marked `method: "ai_reasoning"` with an explicit confidence
   level?
10. For generated content: is every claim traced to supplied profile data, with untraceable
    claims flagged or removed **before return**? (INV-9)
11. Are retries capped, and is usage/cost logging in one place rather than per call site?
12. Does the AI decide only a per-requirement verdict, leaving the engine to compose the final
    eligibility state?

## Output

`PASS` / `CONDITIONAL PASS` / `FAIL`, with file:line evidence.

## Automatic FAIL

- AI able to reach or override a verified hard failure
- A vendor SDK imported in business logic
- Unvalidated AI output reaching business logic
- The suite requiring network or an API key
- Generated content returned without truthfulness validation
- An uncapped retry loop against a paid API
