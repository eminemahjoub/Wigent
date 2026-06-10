# ════════════════════════════════════════
# wigent — Output Renderer
# Role: Format and display agent output in the terminal
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Pretty-printing for agent thoughts, tool calls, observations, and errors."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def print_banner() -> None:
    """Display the Wigent ASCII art banner on startup."""
    # TODO: implement
    raise NotImplementedError


def print_tool_call(name: str, args: dict[str, Any]) -> None:
    """Log a tool invocation with name and arguments."""
    # TODO: implement with rich or plain print
    raise NotImplementedError


def print_observation(content: str) -> None:
    """Display a tool observation (stdout, file content, etc.)."""
    # TODO: implement
    raise NotImplementedError


def print_answer(text: str) -> None:
    """Display the agent's final answer."""
    # TODO: implement
    raise NotImplementedError


__all__ = ["print_banner", "print_tool_call", "print_observation", "print_answer"]
