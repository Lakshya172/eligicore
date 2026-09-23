"""Token usage and cost accounting for AI calls (ADR-026 D3–D6).

Three small, framework-free pieces:

* :class:`AIUsage` — what one AI call consumed, with every field independently optional.
  ``None`` means **unknown**, never zero. A provider that cannot report usage, a reply whose
  metadata is missing or malformed, and a call that never reached a provider all yield
  ``None`` rather than a number that would read as a measurement.
* :class:`UsageSink` — **one per AI call**, created by
  :class:`~app.ai.ai_service.AIService` and handed to the provider for that call alone. It is
  never shared, never stored on a provider and never reused, so concurrent calls — which
  :mod:`app.services.eligibility_ai` makes through ``asyncio.gather`` — cannot contaminate
  each other's totals (D3).
* :func:`cost_micros` — tokens times a configured rate, in integer micro-units.

**Accounting is best-effort and inert.** Nothing here raises on bad input: an unusable value
is recorded as unknown. A defect in cost accounting must never turn a working AI call into a
failed one (D6), so there is no failure mode to propagate.

**Nothing here sees content.** A sink holds counts; it is never given prompt text, reply
text, a profile field or an identifier, and there is no parameter through which one could
arrive (INV-4).

This module has no counterpart for application generation. ``generate_application_content``
is excluded from usage accounting by ADR-026 D8, and the exclusion is structural: that method
takes no sink, so there is nothing here for it to use.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Rates are quoted per this many tokens. Thousands, because per-token prices are fractions
#: too small to express as integers and integers are what keep the arithmetic exact.
TOKENS_PER_RATE_UNIT = 1000


@dataclass(frozen=True)
class AIUsage:
    """What one AI call consumed. ``None`` means unknown, never zero.

    Immutable: a sink builds the totals, then reports them once as this.
    """

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None

    @property
    def is_unknown(self) -> bool:
        """True when nothing at all could be determined."""
        return (
            self.prompt_tokens is None
            and self.completion_tokens is None
            and self.total_tokens is None
        )


def _usable(value: object) -> int | None:
    """Return ``value`` as a token count, or ``None`` if it cannot be one.

    Rejects non-integers, booleans (``bool`` is an ``int`` subclass and a ``True`` token
    count is malformed data, not one token) and negatives.
    """
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


class UsageSink:
    """Collects token counts for exactly one AI call.

    Created per call and passed down; never held by a provider between calls. Providers write
    to it with :meth:`record` for each attempt that produced a response, and
    :meth:`record_unreadable` when a response arrived whose usage could not be read.

    An attempt that produced **no** response — a timeout, a transport failure, a rejected
    request — records nothing: no tokens were reported, and inventing a figure for them would
    be a guess presented as accounting. Attempts that do report are **summed**, so a call that
    succeeded on its third try reports what all three reported (D4).

    A field becomes unknown as soon as any contributing response failed to report it.
    Reporting the readable part of a total as if it were the whole would under-report cost,
    which is the failure this accumulation exists to prevent. Fields degrade independently.
    """

    __slots__ = ("_completion", "_prompt", "_seen", "_total", "_unreadable")

    def __init__(self) -> None:
        self._prompt = 0
        self._completion = 0
        self._total = 0
        #: Fields at least one response reported usably.
        self._seen: set[str] = set()
        #: Fields at least one response failed to report usably.
        self._unreadable: set[str] = set()

    def record(
        self,
        *,
        prompt_tokens: object = None,
        completion_tokens: object = None,
        total_tokens: object = None,
    ) -> None:
        """Add one response's reported usage.

        Accepts ``object`` deliberately: the values come from a provider's JSON and are
        untrusted. Anything that is not a non-negative integer marks its field unknown
        instead of raising.
        """
        for name, raw in (
            ("_prompt", prompt_tokens),
            ("_completion", completion_tokens),
            ("_total", total_tokens),
        ):
            usable = _usable(raw)
            if usable is None:
                self._unreadable.add(name)
                continue
            setattr(self, name, getattr(self, name) + usable)
            self._seen.add(name)

    def record_unreadable(self) -> None:
        """Note that a response arrived carrying no usage this sink could read.

        Distinct from recording nothing: a response that omits its usage block still consumed
        tokens, so the total becomes unknown rather than staying at whatever else was seen.
        """
        self._unreadable.update({"_prompt", "_completion", "_total"})

    @property
    def usage(self) -> AIUsage:
        """The accumulated totals, with unreadable or unreported fields as ``None``."""

        def value(name: str) -> int | None:
            if name in self._unreadable or name not in self._seen:
                return None
            return int(getattr(self, name))

        return AIUsage(
            prompt_tokens=value("_prompt"),
            completion_tokens=value("_completion"),
            total_tokens=value("_total"),
        )


def cost_micros(
    usage: AIUsage,
    prompt_micros_per_1k: int | None,
    completion_micros_per_1k: int | None,
) -> int | None:
    """Cost of ``usage`` in integer micro-units of currency, or ``None`` if unknowable.

    ``None`` — never a fallback number — whenever either rate is unconfigured or either token
    count is unknown (D5). Prompt and completion tokens are priced differently, so a known
    ``total_tokens`` with an unknown split cannot be priced either: the answer depends on a
    ratio nobody reported.

    Integer arithmetic throughout, truncating toward zero. A cost is an accounting figure and
    must not accumulate float drift; sub-micro precision is below anything worth reporting.
    """
    if prompt_micros_per_1k is None or completion_micros_per_1k is None:
        return None
    if usage.prompt_tokens is None or usage.completion_tokens is None:
        return None
    if prompt_micros_per_1k < 0 or completion_micros_per_1k < 0:
        return None
    prompt = usage.prompt_tokens * prompt_micros_per_1k // TOKENS_PER_RATE_UNIT
    completion = usage.completion_tokens * completion_micros_per_1k // TOKENS_PER_RATE_UNIT
    return prompt + completion
