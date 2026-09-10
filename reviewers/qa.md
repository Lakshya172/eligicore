# Reviewer — qa

**Question:** is it actually tested — including the cases that matter, not just the happy path?

**Triggered by:** anything containing logic. The default reviewer.

**Reads:** `standards/testing.md` · `standards/eligibility.md`

---

## Responsibilities

- Verify tests exist, and that they would fail if the code were wrong.
- Verify boundary, missing-data and invalid-data coverage for eligibility logic.
- Verify the INV-2 precedence test exists where relevant.
- Verify privacy behaviours are tested, not merely asserted in prose.
- Verify regression tests accompany bug fixes.
- Verify the suite runs offline and free.

## Not responsible for

Architecture (→ architect) · security analysis (→ security) · prompt design (→ ai).

## Binary questions

1. Do tests exist for this change, and would they actually fail if the logic were wrong?
2. For every hard constraint touched: are there tests **at** the boundary, just below, and just
   above?
3. For every hard constraint touched: does a missing value yield `UNKNOWN`/`NEEDS_REVIEW` rather
   than `FAIL`, with a test proving it?
4. Same for invalid or unparseable values?
5. Are grading-scale mismatches tested, including an absent scale?
6. Is there a test asserting `NOT_ELIGIBLE` on a hard failure **and** that no AI call was made?
   (INV-2)
7. Are privacy behaviours tested — no persistence after a request, temp-file cleanup on the
   failure path, no PII in logs?
8. Do error and failure paths have tests, or only the success path?
9. Does the suite pass with no network and no API key?
10. Are fixtures obviously synthetic, with no real personal data committed?
11. If this fixes a bug, is there a regression test named for it?
12. Was any existing assertion weakened to make the suite pass?

## Output

`PASS` / `CONDITIONAL PASS` / `FAIL`, naming the specific untested case — "no test for
`grad_year` at the upper window boundary," not "needs more tests."

## Automatic FAIL

- New eligibility logic with no boundary tests
- Missing-data handling with no test proving it yields `UNKNOWN` rather than `FAIL`
- An eligibility assertion weakened to make the suite green
- A bug fix with no regression test
- The suite requiring network or credentials
