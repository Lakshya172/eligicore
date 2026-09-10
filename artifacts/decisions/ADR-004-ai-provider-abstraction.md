# ADR-004 — AI provider abstraction

**Status:** Accepted (default provider deferred) · **Date:** 2026-09-10 · **Source:** dossier §9.2

## Context

EligiCore needs a language model for resume structuring, ambiguous-requirement reasoning, and
application content generation. The obvious implementation — calling a vendor SDK directly
wherever AI is needed — spreads vendor-specific code through business logic and makes the test
suite depend on network access and a paid API key.

## Decision

**All AI calls route through a single abstract interface** (`app/ai/providers/base.py`) with
concrete provider implementations behind it. Business logic never imports a vendor SDK.

Prompts live as files under `app/ai/prompts/`, not as inline strings.

Interchangeable providers named by the dossier: OpenAI, OpenRouter, Anthropic, or a local model.
**A mock provider is mandatory and is not optional tooling** — it lands in the same change as
the interface itself.

## Consequences

**Positive.** Switching providers is a configuration change, not a refactor. No vendor lock-in.
AI is mockable, so the test suite runs fast, offline and free. Cost and usage logging happens
in exactly one place rather than at every call site.

**Negative / accepted costs.** The abstraction must express the least common denominator across
providers, so provider-specific features are awkward to reach. Structured-output support differs
between vendors and the interface has to absorb that difference.

## AI response handling

Provider output is **untrusted input**. Every response is validated against a Pydantic model
before it reaches business logic. A response that fails validation yields `NEEDS_REVIEW` — never
a silent pass, and never an unhandled crash.

## Deferred: which provider is the Phase 1 default

The dossier's §8.2 folder listing shows only `openai_provider.py`, while §9.2 names four
options. **The Phase 1 default is not decided** — tracked as contradiction C-4 in
`context/state.md` and deferred decision D-1 in `context/decisions.md`.

This does not block the interface, which is provider-agnostic by construction. It must be
settled before Week 2 implementation of a concrete provider.

## Enforcement

INV-5 · QG-003 · `reviewers/ai.md` · `standards/ai.md`
