"""Application-level AI errors.

Provider-specific exceptions are translated into these at the provider boundary, so no
service, router or error handler ever sees an httpx exception or a vendor error type
(ADR-004, ADR-013).

**No exception in this module may carry candidate data, prompt text, or a raw provider
payload in its message** (INV-4). Messages describe the failure category; the offending
content stays out of the string, out of logs, and out of API responses.
"""

from __future__ import annotations


class AIError(Exception):
    """Base class for every AI-layer failure."""


class AIConfigurationError(AIError):
    """The provider is not usable because it is misconfigured.

    Raised at construction — a missing API key, an empty model identifier. Distinct from a
    runtime failure because the fix is operator action, not a retry.
    """


class AIProviderUnavailableError(AIError):
    """The provider could not be reached, timed out, or returned a transport-level error.

    Retryable in principle. Covers connection failures, timeouts and 5xx responses.
    """


class AIProviderRejectedError(AIError):
    """The provider rejected the request — bad key, quota exhausted, content blocked.

    Not retryable: repeating the same request produces the same rejection.
    """


class AIResponseInvalidError(AIError):
    """The provider replied, but the reply could not be validated into the expected schema.

    Covers malformed JSON, a truncated response, missing required fields, and values
    outside an allowed enum. Provider output is untrusted input (``standards/ai.md`` §4);
    this is the expected outcome when it fails validation, not an unhandled crash.
    """
