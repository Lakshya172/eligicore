# Standard — Python Code Quality

> **Invariants:** INV-7 · Target: Python 3.11+ (local 3.12.10)
> The dossier's audience for this code includes a stranger reviewing it as portfolio evidence.
> Readability is a functional requirement here, not a preference.

---

## 1. Type hints

- Every function signature is fully annotated — parameters and return type.
- Prefer precise types: `list[EducationEntry]` over `list`, `Decimal | None` over `Any`.
- `Any` requires a comment explaining why nothing narrower works.
- Domain enums are `enum.Enum` subclasses, not string literals scattered through the code.

## 2. Modularity and layer discipline

- One module, one responsibility. `eligibility_engine.py` evaluates eligibility; it does not
  also parse resumes or call adapters.
- **Dependency direction is one-way and downward:** routers → services → (ai | adapters) →
  models. Services never import routers. AI and adapters never import services.
- No circular imports. A circular import is a signal that a responsibility sits in the wrong
  module, not a problem to solve with a deferred import.
- Business logic never imports FastAPI (INV-7) and never imports a vendor AI SDK (INV-5).

## 3. Minimal unnecessary abstraction

The dossier's abstractions — AI provider, job adapter — exist because they are load-bearing for
stated goals. **Do not add more by reflex.**

- No base class with one subclass and no second in sight.
- No dependency-injection framework. FastAPI's `Depends` is sufficient.
- No factory that returns one thing. No manager that manages one object.
- Three occurrences before extracting a shared helper, not two.

This is a solo 10-week project. Every layer of indirection is time not spent on eligibility
correctness.

## 4. Naming

- Names state what a thing is or does. `evaluate_hard_constraints`, not `process`. `job_id`,
  not `jid`.
- Domain vocabulary is fixed by the dossier and is used consistently: *candidate*, *job*,
  *eligibility state*, *requirement breakdown*, *match score*, *adapter*, *provider*. Do not
  introduce synonyms — "applicant", "posting", "verdict score" all cost the reader.
- Booleans read as assertions: `is_eligible`, `has_backlogs`.
- Avoid negated names: `is_valid`, not `is_not_invalid`.

## 5. Functions

- A function does one thing at one level of abstraction.
- Prefer early returns to nested conditionals — eligibility logic nests badly otherwise.
- Pure functions wherever possible; they are the ones worth unit-testing cheaply.
- If a function needs a comment to explain *what* it does, rename or split it. Comments explain
  *why*.

## 6. Testability

Write the code so it can be tested without ceremony:

- Services take their inputs as arguments rather than reaching for globals or config at call
  time.
- No I/O buried inside pure logic. Fetch, then compute.
- Time and randomness are injected, never called directly inside logic under test.
- If testing something requires standing up a server or a database, it is in the wrong layer.

## 7. Comments and docstrings

- Docstrings on every public module, class and function. Say what it does, what it returns, and
  what it raises.
- Comments explain intent and non-obvious decisions — especially anything enforcing an
  invariant. Mark those explicitly, e.g. `# INV-2: AI is not consulted once a hard rule fails.`
- Delete commented-out code. Git is the history — once the repository is under version control
  (Blocker 1).

## 8. Error handling

- Catch specific exceptions. A bare `except:` or a broad `except Exception:` that swallows and
  continues is a defect.
- Never silently default on failure. A parse failure yields `UNKNOWN`, not `0.0`
  (`standards/eligibility.md` §3).
- Cleanup belongs in `finally`, not on the success path (INV-11).
- Exception messages must not embed PII (INV-4).

## 9. Configuration

- All configuration via environment variables with the `ELIGICORE_` prefix, loaded through
  `config.py`. No `os.getenv` scattered across modules.
- No magic numbers in logic. Thresholds and limits are named constants or configuration.
- Paths use `pathlib`, never string concatenation — development is Windows, deployment is Linux.

## 10. Formatting

Pick a formatter and linter in Week 1 and apply them from the first commit rather than
retrofitting later. Consistency matters more than which tools are chosen.
