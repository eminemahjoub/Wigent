# ════════════════════════════════════════
# wigent — Anthropic Provider
# Role: Concrete LLM provider for Anthropic Claude models
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Anthropic Claude implementation of LLMProvider."""

from __future__ import annotations

import logging
from typing import Any

from wigent.models.base import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class AnthropicProvider(LLMProvider):
    """Provider wrapper around the Anthropic Python SDK."""

    def __init__(self, model: str = "claude-sonnet-4-20250514", **kwargs: Any) -> None:
        # TODO: initialise Anthropic client
        raise NotImplementedError

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        # TODO: implement message completion with tool calling
        raise NotImplementedError

    def count_tokens(self, text: str) -> int:
        # TODO: implement
        raise NotImplementedError


__all__ = ["AnthropicProvider"]
