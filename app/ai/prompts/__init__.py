"""Prompt templates, stored as files rather than inline strings.

Inline prompts are undiffable, untestable, and get edited by accident during unrelated
refactors (``standards/ai.md`` §6). A prompt change is a behaviour change and is reviewed
as one.

**A rendered prompt contains candidate data and must never be logged** (INV-4).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_PROMPT_DIR = Path(__file__).parent


@lru_cache
def load_prompt(name: str) -> str:
    """Load a prompt template by name, without its extension.

    Args:
        name: Base filename, e.g. ``"resume_extraction"``.

    Raises:
        FileNotFoundError: No such prompt. Raised at call time rather than returning a
            silent empty string, which would send an unprompted request to a paid API.
    """
    path = _PROMPT_DIR / f"{name}.txt"
    if not path.is_file():
        raise FileNotFoundError(f"Prompt template not found: {name}")
    return path.read_text(encoding="utf-8")
