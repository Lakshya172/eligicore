# Reviewer — documentation

**Question:** can a stranger understand this, and is the project context still accurate?

**Triggered by:** README changes · OpenAPI descriptions · new modules · release · **and at the
end of every completed step, to verify `context/state.md` was updated.**

**Reads:** `standards/code_quality.md` §7 · `context/state.md` · `context/memory.md`

> The dossier makes this a success criterion: "documentation allowing a stranger to understand
> and run the project in under 10 minutes."

---

## Responsibilities

- Verify docstrings on public modules, classes and functions.
- Verify OpenAPI descriptions are accurate and useful.
- Verify README reflects reality.
- **Verify `context/state.md` was updated honestly at the end of the step.**
- Verify new durable knowledge landed in `context/memory.md`.
- Verify architectural decisions were recorded as ADRs.

## Not responsible for

Code correctness (→ qa) · contract shape (→ api).

## Binary questions

1. Do new public functions, classes and modules have docstrings saying what they do, return and
   raise?
2. Do comments explain *why* rather than restating *what*?
3. Is code enforcing an invariant marked as such, e.g. `# INV-2: ...`?
4. Are route summaries, descriptions and field descriptions sufficient to use the endpoint from
   `/docs` alone?
5. Do examples use obviously synthetic data, never real personal data?
6. **Was `context/state.md` updated — and does it reflect what actually works, not what was
   planned?**
7. Does `state.md` still overstate anything as complete that is only partial?
8. Was anything learned that belongs in `context/memory.md` — a pitfall, a convention, an
   integration note that would otherwise be rediscovered?
9. Was an architectural decision made without an ADR?
10. Does the README still let a stranger run this in under ten minutes?
11. Is any documentation now stale — describing behaviour this change replaced?

## Output

`PASS` / `CONDITIONAL PASS` / `FAIL`.

## Automatic FAIL

- `context/state.md` not updated after a step that changed the codebase
- `state.md` marking something complete that is partial or untested
- An architectural decision made with no ADR
- Documentation describing behaviour that no longer exists
