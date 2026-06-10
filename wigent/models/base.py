# ════════════════════════════════════════
# wigent — LLM Provider Base
# Role: Abstract interface for LLM backends
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Abstract base class that all LLM providers must implement."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMResponse:
    """Standardised response from any LLM provider."""

    content: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict[str, int] = field(default_factory=dict)
    raw: Any = None


class LLMProvider(ABC):
    """Abstract interface for LLM providers.

    Subclasses must implement `complete()` which returns an LLMResponse
    given a conversation history and optional tool definitions.
    """

    @abstractmethod
    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Send messages to the LLM and return a structured response."""
        ...

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Estimate the number of tokens in a text string."""
        ...


__all__ = ["LLMResponse", "LLMProvider"]
