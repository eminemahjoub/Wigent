# ════════════════════════════════════════
# wigent — OpenAI Provider
# Role: Concrete LLM provider for OpenAI models
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""OpenAI / Azure OpenAI implementation of LLMProvider."""

from __future__ import annotations

import logging
from typing import Any

from wigent.models.base import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    """Provider wrapper around the OpenAI Python SDK."""

    def __init__(self, model: str = "gpt-4o", **kwargs: Any) -> None:
        # TODO: initialise OpenAI client
        raise NotImplementedError

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        # TODO: implement chat completion with tool calling
        raise NotImplementedError

    def count_tokens(self, text: str) -> int:
        # TODO: implement with tiktoken
        raise NotImplementedError


__all__ = ["OpenAIProvider"]
