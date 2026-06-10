# ════════════════════════════════════════
# wigent — Agent Loop
# Role: Think-act-observe orchestration loop
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Core agent loop — manages conversation, dispatches tool calls, drives the
think-act-observe cycle until a final answer is produced."""

from __future__ import annotations

import json
import logging
from typing import Any

# TODO: import model providers once models/ is implemented
# TODO: import tool registry once tools/ is implemented

logger = logging.getLogger(__name__)


class Agent:
    """Encapsulates the agent's state and the main interaction loop.

    Attributes:
        messages: Full conversation history sent to the LLM.
        model: Underlying LLM provider instance.
        tools: Tool registry mapping names to callables.
    """

    def __init__(self, model: Any, tools: dict[str, Any]) -> None:
        self.messages: list[dict[str, Any]] = []
        self.model = model
        self.tools = tools

    def add_message(self, role: str, content: str, **kwargs: Any) -> None:
        """Append a message to the conversation history."""
        # TODO: implement with proper message schema
        raise NotImplementedError

    def step(self) -> str | None:
        """Run one iteration: think -> act -> observe.

        Returns the final answer string when the agent stops, or None if
        the loop should continue (tool call was dispatched).
        """
        # TODO: implement the core loop
        raise NotImplementedError

    def run(self, user_prompt: str) -> str:
        """Entry point — run the agent until completion and return the answer."""
        # TODO: wire up the full loop
        raise NotImplementedError


def run_agent(user_prompt: str) -> str:
    """Convenience function — instantiate a default Agent and run it."""
    # TODO: replace with real wiring
    raise NotImplementedError


__all__ = ["Agent", "run_agent"]
