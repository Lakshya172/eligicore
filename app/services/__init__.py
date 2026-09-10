"""Business logic.

Services are framework-agnostic: no FastAPI imports, no request objects, no HTTP concerns.
Every service here must be importable and callable from a plain script with no server
running (INV-7, ``standards/code_quality.md`` §6).
"""
