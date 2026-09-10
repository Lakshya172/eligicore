# ADR-008 — No auto-submit in current scope

**Status:** Accepted · **Date:** 2026-09-10 · **Source:** dossier §6, §13.5

## Context

The obvious commercial direction for a tool that finds eligible jobs is to apply to them
automatically. Most tools in this space do exactly that. It is also the single most requested
feature such a tool receives.

## Decision

**EligiCore does not submit applications.** It produces reviewable packages. The human submits.

Also out of scope, for the same reasons: browser automation for form submission, CAPTCHA
solving or bypass, OTP bypass, anti-bot circumvention, and identity-verification bypass.

## Rationale

Four independent reasons, each sufficient on its own:

**Terms of Service.** Most major job portals explicitly prohibit automated submission. Building
on that is legally fragile and can get user accounts permanently banned — the cost lands on the
candidate, not the tool.

**Reliability.** Application forms differ wildly between companies. CAPTCHAs, login walls,
multi-step wizards and file-upload quirks mean automation breaks constantly. Maintenance cost is
enormous and the success rate is poor.

**Quality.** Mass-applying lowers response rates and wastes recruiter time. Filtering to fewer,
better-matched applications produces better outcomes for everyone in the loop.

**Accountability.** An application submitted in your name should be one you saw and approved.
Automated submission removes that, and the consequences of a bad automated application are
borne by the candidate.

## Positioning

This is stated openly as a design decision, not apologized for as a missing feature. Mature
tools in this space have independently reached the same conclusion — external validation of the
call, noted in dossier §14.

## Consequences

The system is a filter and decision-support tool, not a bulk applier. Phase 2 may add a browser
extension that autofills forms **within the candidate's own session**, which preserves the
constraint: the human still reviews and still clicks submit.

## Revisit conditions

None currently foreseen for portal submission. A future integration with an employer-sanctioned
API that explicitly permits programmatic submission would be a different decision requiring its
own ADR — it would not be covered by amending this one.

## Enforcement

INV-10 · `reviewers/security.md`, `reviewers/architect.md`
