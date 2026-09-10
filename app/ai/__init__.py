"""AI provider abstraction layer.

Everything vendor-specific lives under ``app/ai/providers/``. Nothing outside this package
may import a vendor SDK or reference a provider by name (INV-5, ADR-004).

The dependency direction is one way:

    services  ->  ai_service  ->  AIProvider (abstract)  ->  concrete provider

A service that knows which provider is configured has broken the abstraction.
"""
