# ════════════════════════════════════════
# wigent — Conversation History
# Role: Manage message history with token tracking and summarization
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Thread-safe conversation buffer with token accounting and automatic
context-window management (truncation / summarization)."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ConversationHistory:
    """Maintains the ordered list of messages sent to the LLM.

    Features (planned):
    - Append messages (system, user, assistant, tool)
    - Token counting per message and in total
    - Automatic summarization when approaching context limit
    - Bounded growth via sliding window
    """

    def __init__(self, max_tokens: int = 128_000) -> None:
        self._messages: list[dict[str, Any]] = []
        self._max_tokens = max_tokens

    def add(self, role: str, content: str, **kwargs: Any) -> None:
        """Append a message and optionally enforce the token budget."""
        # TODO: implement
        raise NotImplementedError

    @property
    def messages(self) -> list[dict[str, Any]]:
        """Return the current message list (read-only view)."""
        return list(self._messages)

    @property
    def token_count(self) -> int:
        """Return the estimated total token count."""
        # TODO: implement
        raise NotImplementedError

    def trim(self) -> None:
        """Trim oldest messages when the token budget is exceeded."""
        # TODO: implement
        raise NotImplementedError


__all__ = ["ConversationHistory"]
