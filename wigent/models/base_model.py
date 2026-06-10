# ════════════════════════════════════════
# wigent — Base Model
# Role: Abstract interface for all LLM providers
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Abstract base class that all LLM providers must implement.

Provides the canonical ``BaseModel`` interface — every provider (OpenAI,
Anthropic, Gemini, Groq, Ollama, LiteLLM) subclasses this.

Error types
-----------
- ``AuthError``: invalid / missing API key
- ``RateLimitError``: 429 or provider-side quota exhaustion
- ``ContextWindowError``: prompt exceeds model context limit
- ``ModelError``: model returned an unexpected error
- ``ApiError``: network / connectivity failure
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Any, Callable, Generator, TypeVar

logger = logging.getLogger(__name__)


# ── Error types ──────────────────────────────────────────────────────────


class ErrorType(str, Enum):
    AUTH = "authentication_error"
    RATE_LIMIT = "rate_limit_error"
    CONTEXT_WINDOW = "context_window_error"
    MODEL = "model_error"
    API = "api_error"
    UNKNOWN = "unknown_error"


class AuthError(Exception):
    """Raised when the API key is missing, invalid, or expired."""


class RateLimitError(Exception):
    """Raised on 429 / rate-limit / quota-exhaustion responses."""


class ContextWindowError(Exception):
    """Raised when the combined message tokens exceed the model limit."""


class ModelError(Exception):
    """Raised when the model returns an unexpected or malformed response."""


class ApiError(Exception):
    """Raised for network / connectivity / server errors."""


# ── Data classes ─────────────────────────────────────────────────────────


@dataclass
class ModelInfo:
    """Read-only metadata describing a single model."""

    name: str
    provider: str
    context_window: int = 128_000
    max_output_tokens: int = 4_096
    supports_streaming: bool = True
    supports_function_calling: bool = True
    supports_vision: bool = False
    supports_extended_thinking: bool = False
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0


@dataclass
class LLMResponse:
    """Standardised response from any LLM provider."""

    content: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict[str, int] = field(default_factory=dict)
    model: str = ""
    provider: str = ""
    cost: float = 0.0
    raw: Any = None


# ── Retry decorator ──────────────────────────────────────────────────────


F = TypeVar("F", bound=Callable[..., Any])


def retry_on_rate_limit(max_retries: int = 3, base_delay: float = 1.0):
    """Decorator: retry the wrapped coroutine on ``RateLimitError``.

    Uses exponential backoff (1 s, 2 s, 4 s by default).  Non-rate-limit
    errors are re-raised immediately.
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Exception | None = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except RateLimitError as exc:
                    last_exc = exc
                    if attempt < max_retries:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(
                            "Rate limited (attempt %d/%d).  "
                            "Retrying in %.1f s …",
                            attempt + 1, max_retries + 1, delay,
                        )
                        time.sleep(delay)
            raise RateLimitError(
                f"Exceeded max retries ({max_retries}) for rate-limited call."
            ) from last_exc
        return wrapper  # type: ignore[return-value]
    return decorator


# ── Base model ───────────────────────────────────────────────────────────


class BaseModel(ABC):
    """Abstract LLM provider.

    Every provider in the system must subclass ``BaseModel`` and implement
    ``chat()``, ``stream_chat()``, and ``count_tokens()`` at a minimum.
    """

    # Provider identifier used for cost lookups via PROVIDER_CONFIGS.
    PROVIDER_NAME: str = ""

    def __init__(self, model: str | None = None, **kwargs: Any) -> None:
        self.model_name: str = model or self._default_model()
        self._kwargs: dict[str, Any] = kwargs

    # ── Abstract interface ───────────────────────────────────────────

    @abstractmethod
    def _default_model(self) -> str:
        """Return the provider's default model name."""
        ...

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> LLMResponse:
        """Send messages to the LLM and return a structured response.

        Args:
            messages: Conversation history in OpenAI-format
                      ``[{"role": …, "content": …}, …]``.
            tools:    Optional OpenAI-format tool definitions.
            stream:   If ``True``, ``chat()`` still returns an ``LLMResponse``
                      but will internally consume the stream.  Prefer using
                      ``stream_chat()`` for streaming callers.

        Returns:
            ``LLMResponse`` with content, tool_calls, usage, and cost.
        """
        ...

    @abstractmethod
    def stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> Generator[str, None, LLMResponse]:
        """Stream tokens from the LLM one string chunk at a time.

        Yields:
            Each text delta as it arrives from the wire.

        Returns:
            The final ``LLMResponse`` (with full content, usage, and cost)
            after the generator is exhausted.
        """
        ...
        yield  # make it a generator in the abstract contract

    # ── Token counting ───────────────────────────────────────────────

    def count_tokens(self, messages: list[dict[str, Any]]) -> int:
        """Estimate the combined token count of a message list.

        The base implementation uses a rough character-based heuristic.
        Subclasses that have native tokenisers (e.g. ``tiktoken`` for
        OpenAI, ``claude.tokenize`` for Anthropic) **should** override.
        """
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += len(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        txt = block.get("text", "")
                        if isinstance(txt, str):
                            total += len(txt)
        return total // 4  # ~4 chars per token

    # ── Model metadata ───────────────────────────────────────────────

    @abstractmethod
    def get_model_info(self) -> ModelInfo:
        """Return metadata about the active model."""
        ...

    # ── API key validation ───────────────────────────────────────────

    @abstractmethod
    def validate_api_key(self) -> bool:
        """Return ``True`` if a valid API key is configured."""
        ...

    # ── Error classification ─────────────────────────────────────────

    @staticmethod
    def handle_error(error: Exception) -> ErrorType:
        """Classify an exception into a structured ``ErrorType``.

        Subclasses can override to add provider-specific error detection.
        """
        if isinstance(error, AuthError):
            return ErrorType.AUTH
        if isinstance(error, RateLimitError):
            return ErrorType.RATE_LIMIT
        if isinstance(error, ContextWindowError):
            return ErrorType.CONTEXT_WINDOW
        if isinstance(error, ModelError):
            return ErrorType.MODEL
        if isinstance(error, ApiError):
            return ErrorType.API
        return ErrorType.UNKNOWN

    # ── Cost helpers ─────────────────────────────────────────────────

    def _calculate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """Compute the dollar cost of a call using upstream config.

        Uses ``PROVIDER_CONFIGS`` from ``wigent.config.models_config``.
        """
        from wigent.config.models_config import PROVIDER_CONFIGS
        cfg = PROVIDER_CONFIGS.get(self.PROVIDER_NAME)
        if cfg is None:
            return 0.0
        cost = cfg.cost_per_1k_tokens
        return (input_tokens * cost.input + output_tokens * cost.output) / 1000


__all__ = [
    "ErrorType", "AuthError", "RateLimitError", "ContextWindowError",
    "ModelError", "ApiError",
    "ModelInfo", "LLMResponse",
    "retry_on_rate_limit",
    "BaseModel",
]
