# ════════════════════════════════════════
# wigent — Prompts Package
# Role: Prompt loader, cache, and composition engine
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Prompt management — loads, caches, and composes system prompts from
markdown files for each agent mode.

Usage:
    from wigent.prompts import load_prompt, combine_prompts

    full_prompt = combine_prompts("base", "coder")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Final

logger = logging.getLogger(__name__)

# ── paths ────────────────────────────────────────────────────────────────

_PROMPT_DIR: Final[Path] = Path(__file__).parent.resolve()

_AVAILABLE_PROMPTS: Final[set[str]] = {
    "base",
    "orchestrator",
    "architect",
    "coder",
    "debugger",
    "reviewer",
    "tool_use",
    "safety",
}

# ── cache ────────────────────────────────────────────────────────────────

_cache: dict[str, str] = {}


def load_prompt(name: str) -> str:
    """Load a prompt from its markdown file, with caching.

    Args:
        name: Prompt name (without ``.md`` suffix). One of:
              ``base``, ``orchestrator``, ``architect``, ``coder``,
              ``debugger``, ``reviewer``, ``tool_use``, ``safety``.

    Returns:
        The full text content of the prompt file.

    Raises:
        FileNotFoundError: If the prompt file does not exist.
        ValueError: If the name is not in the known prompt set.
    """
    if name not in _AVAILABLE_PROMPTS:
        raise ValueError(
            f"Unknown prompt '{name}'. "
            f"Available prompts: {', '.join(sorted(_AVAILABLE_PROMPTS))}"
        )

    if name in _cache:
        return _cache[name]

    filepath = _PROMPT_DIR / f"{name}.md"
    if not filepath.is_file():
        raise FileNotFoundError(
            f"Prompt file not found: {filepath}. "
            f"Expected at {_PROMPT_DIR / f'{name}.md'}"
        )

    content = filepath.read_text(encoding="utf-8")
    _cache[name] = content
    logger.debug("Loaded prompt: %s (%d chars)", name, len(content))
    return content


def combine_prompts(*names: str) -> str:
    """Load multiple prompts and concatenate them with separators.

    The ``base`` prompt is always loaded first (if included in *names*,
    it will not be duplicated). The combined result uses markdown
    ``---`` horizontal rules as separators.

    Args:
        *names: Prompt names to combine, in order.

    Returns:
        A single string with all prompts joined.

    Example:
        >>> combine_prompts("base", "coder", "tool_use")
    """
    parts: list[str] = []
    seen: set[str] = set()

    for name in names:
        if name in seen:
            continue
        seen.add(name)
        content = load_prompt(name)
        parts.append(content)

    return "\n\n---\n\n".join(parts)


def get_available_prompts() -> list[str]:
    """Return the list of all known prompt names."""
    return sorted(_AVAILABLE_PROMPTS)


def clear_cache() -> None:
    """Clear the internal prompt cache (useful for testing / reload)."""
    _cache.clear()


def prompt_stats() -> dict[str, int]:
    """Return a dict mapping prompt name to character count (loaded)."""
    return {name: len(load_prompt(name)) for name in _AVAILABLE_PROMPTS}


# ── convenience: full prompt for a given mode ───────────────────────────

def build_mode_prompt(mode: str) -> str:
    """Build the full system prompt for a given agent mode.

    Composition:
        base.md
        + <mode>.md
        + tool_use.md
        + safety.md

    Args:
        mode: Agent mode name (``orchestrator``, ``architect``, etc.).

    Returns:
        Complete system prompt string.
    """
    mode = mode.lower()
    if mode not in _AVAILABLE_PROMPTS:
        raise ValueError(
            f"Unknown mode '{mode}'. "
            f"Available modes: {', '.join(sorted(_AVAILABLE_PROMPTS))}"
        )
    return combine_prompts("base", mode, "tool_use", "safety")


__all__ = [
    "load_prompt",
    "combine_prompts",
    "get_available_prompts",
    "clear_cache",
    "prompt_stats",
    "build_mode_prompt",
]
