# ════════════════════════════════════════
# wigent — Provider Registry
# Role: Central registry mapping provider names to implementations
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Singleton registry for LLM providers. Allows the agent to switch
between OpenAI, Anthropic, or custom providers at runtime."""

from __future__ import annotations

import logging
from typing import Any

from wigent.models.base import LLMProvider

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """Registry that maps provider names to LLMProvider subclasses.

    Usage:
        registry = ProviderRegistry()
        registry.register("openai", OpenAIProvider)
        provider = registry.get("openai")(model="gpt-4o")
    """

    def __init__(self) -> None:
        self._providers: dict[str, type[LLMProvider]] = {}

    def register(self, name: str, provider_cls: type[LLMProvider]) -> None:
        """Register a provider class under a canonical name."""
        # TODO: implement
        raise NotImplementedError

    def get(self, name: str) -> type[LLMProvider]:
        """Retrieve a registered provider class by name."""
        # TODO: implement
        raise NotImplementedError

    def list_providers(self) -> list[str]:
        """Return all registered provider names."""
        # TODO: implement
        raise NotImplementedError


# Module-level singleton for global access.
registry = ProviderRegistry()

__all__ = ["ProviderRegistry", "registry"]
