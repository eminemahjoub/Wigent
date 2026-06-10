# ════════════════════════════════════════
# wigent — LiteLLM Proxy
# Role: Universal fallback router via LiteLLM
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""LiteLLM proxy implementation of ``BaseModel``.

Routes requests to **any** provider supported by LiteLLM (100+ models),
with automatic retries, fallback chains, cost tracking, and usage logging.

This is the universal fallback — when no native provider is configured,
LiteLLM can bridge to OpenAI, Anthropic, Gemini, Groq, and dozens more
through a single interface.

Models
------
- Any model string LiteLLM understands:
  ``gpt-4o``, ``claude-sonnet-4-20250514``,
  ``gemini-2.5-pro-exp-03-25``, ``command-a-03-2025``, etc.

Features
--------
- Streaming
- Function calling
- Automatic retries + fallback chains
- Cost tracking per call
- Usage logging
- Router with multiple models for failover
"""

from __future__ import annotations

import logging
import os
from typing import Any, Generator

import litellm
from litellm import Router

from wigent.config import settings
from wigent.models.base_model import (
    ApiError,
    AuthError,
    BaseModel,
    ContextWindowError,
    ErrorType,
    LLMResponse,
    ModelError,
    ModelInfo,
    RateLimitError,
    retry_on_rate_limit,
)

logger = logging.getLogger(__name__)

# Ensure LiteLLM doesn't suppress our error handling.
litellm.suppress_debug_info = True
litellm.set_verbose = False


class LiteLLMProxy(BaseModel):
    """Universal LLM provider via LiteLLM.

    Can be configured with:
    - A single model (default behaviour)
    - A fallback chain (list of models tried in order on failure)
    - A router with multiple deployments for load balancing / failover
    """

    PROVIDER_NAME = "litellm"

    MODEL_INFO: dict[str, ModelInfo] = {
        "gpt-4o": ModelInfo(
            name="gpt-4o", provider="litellm", context_window=128_000, max_output_tokens=16_384,
            cost_per_1k_input=0.0025, cost_per_1k_output=0.0100,
        ),
        "gpt-4o-mini": ModelInfo(
            name="gpt-4o-mini", provider="litellm", context_window=128_000, max_output_tokens=16_384,
            cost_per_1k_input=0.00015, cost_per_1k_output=0.00060,
        ),
        "claude-sonnet-4-20250514": ModelInfo(
            name="claude-sonnet-4-20250514", provider="litellm", context_window=200_000, max_output_tokens=8_192,
            supports_vision=True, supports_extended_thinking=True,
            cost_per_1k_input=0.0030, cost_per_1k_output=0.0150,
        ),
        "claude-3.5-sonnet-20241022": ModelInfo(
            name="claude-3.5-sonnet-20241022", provider="litellm", context_window=200_000, max_output_tokens=8_192,
            supports_vision=True,
            cost_per_1k_input=0.0030, cost_per_1k_output=0.0150,
        ),
        "gemini-2.5-pro-exp-03-25": ModelInfo(
            name="gemini-2.5-pro-exp-03-25", provider="litellm", context_window=1_000_000, max_output_tokens=8_192,
            cost_per_1k_input=0.00125, cost_per_1k_output=0.00500,
        ),
    }

    def __init__(
        self,
        model: str | None = None,
        fallbacks: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(model=model, **kwargs)
        self._fallbacks: list[str] = fallbacks or []
        self._setup_litellm_config()

        if self._fallbacks:
            self._router = self._build_router()
        else:
            self._router = None

    def _setup_litellm_config(self) -> None:
        """Set API keys from settings so LiteLLM can find them."""
        litellm.api_key = ""
        key_map = {
            "OPENAI_API_KEY": settings.OPENAI_API_KEY,
            "ANTHROPIC_API_KEY": settings.ANTHROPIC_API_KEY,
            "GEMINI_API_KEY": settings.GEMINI_API_KEY,
            "GROQ_API_KEY": settings.GROQ_API_KEY,
            "MISTRAL_API_KEY": settings.MISTRAL_API_KEY,
            "COHERE_API_KEY": settings.COHERE_API_KEY,
        }
        for env_key, value in key_map.items():
            if value:
                os.environ.setdefault(env_key, value)

        base_url = settings.LITELLM_BASE_URL or os.getenv("LITELLM_BASE_URL") or ""
        if base_url:
            litellm.api_base = base_url

    def _build_router(self) -> Router:
        """Build a LiteLLM Router with fallback models."""
        model_list = []

        primary = {
            "model_name": self.model_name,
            "litellm_params": {"model": self.model_name},
        }
        model_list.append(primary)

        for fb in self._fallbacks:
            model_list.append({
                "model_name": fb,
                "litellm_params": {"model": fb},
            })

        return Router(
            model_list=model_list,
            fallbacks=[{self.model_name: self._fallbacks}],
            num_retries=1,
        )

    def _default_model(self) -> str:
        return "gpt-4o"

    def get_model_info(self) -> ModelInfo:
        base = self.MODEL_INFO.get(self.model_name)
        if base is not None:
            return base
        return ModelInfo(
            name=self.model_name,
            provider="litellm",
            context_window=128_000,
            max_output_tokens=16_384,
        )

    def validate_api_key(self) -> bool:
        return True

    def count_tokens(self, messages: list[dict[str, Any]]) -> int:
        try:
            return litellm.token_counter(model=self.model_name, messages=messages)
        except Exception:
            return super().count_tokens(messages)

    # ── Chat ─────────────────────────────────────────────────────────

    @retry_on_rate_limit(max_retries=3, base_delay=1.0)
    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> LLMResponse:
        self._check_context_window(messages)

        completion_kwargs = self._build_completion_kwargs(messages, tools, **kwargs)

        try:
            if stream:
                return self._handle_streaming_response(completion_kwargs)

            if self._router is not None:
                response = self._router.completion(**completion_kwargs)
            else:
                response = litellm.completion(**completion_kwargs)

            return self._build_response(response)

        except Exception as exc:
            self._classify_error(exc)

    # ── Streaming ────────────────────────────────────────────────────

    def stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> Generator[str, None, LLMResponse]:
        self._check_context_window(messages)

        completion_kwargs = self._build_completion_kwargs(messages, tools, stream=True, **kwargs)

        try:
            if self._router is not None:
                response = self._router.completion(**completion_kwargs)
            else:
                response = litellm.completion(**completion_kwargs)
        except Exception as exc:
            self._classify_error(exc)

        full_content: list[str] = []
        tool_calls: dict[int, dict[str, Any]] = {}
        finish_reason = "stop"
        usage: dict[str, int] = {}

        for chunk in response:
            if hasattr(chunk, "choices") and chunk.choices:
                delta = chunk.choices[0].delta if chunk.choices[0].delta else None
                if delta is None:
                    if hasattr(chunk, "usage") and chunk.usage:
                        usage = {
                            "prompt_tokens": getattr(chunk.usage, "prompt_tokens", 0) or 0,
                            "completion_tokens": getattr(chunk.usage, "completion_tokens", 0) or 0,
                            "total_tokens": getattr(chunk.usage, "total_tokens", 0) or 0,
                        }
                    continue

                if getattr(delta, "content", None):
                    full_content.append(delta.content)
                    yield delta.content

                if getattr(delta, "tool_calls", None):
                    for tc in delta.tool_calls:
                        idx = getattr(tc, "index", 0)
                        if idx not in tool_calls:
                            tool_calls[idx] = {
                                "id": getattr(tc, "id", "") or "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }
                        if getattr(tc, "function", None):
                            if tc.function.name:
                                tool_calls[idx]["function"]["name"] += tc.function.name
                            if tc.function.arguments:
                                tool_calls[idx]["function"]["arguments"] += tc.function.arguments

                if chunk.choices[0].finish_reason:
                    finish_reason = chunk.choices[0].finish_reason
            elif hasattr(chunk, "usage") and chunk.usage:
                usage = {
                    "prompt_tokens": getattr(chunk.usage, "prompt_tokens", 0) or 0,
                    "completion_tokens": getattr(chunk.usage, "completion_tokens", 0) or 0,
                    "total_tokens": getattr(chunk.usage, "total_tokens", 0) or 0,
                }

        sorted_calls = [tool_calls[i] for i in sorted(tool_calls)] if tool_calls else []
        content = "".join(full_content)
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)

        return LLMResponse(
            content=content or None,
            tool_calls=sorted_calls,
            finish_reason=finish_reason,
            usage=usage,
            model=self.model_name,
            provider=self.PROVIDER_NAME,
            cost=self._calculate_cost(input_tokens, output_tokens),
            raw=usage,
        )

    # ── Internals ────────────────────────────────────────────────────

    def _check_context_window(self, messages: list[dict[str, Any]]) -> None:
        tokens = self.count_tokens(messages)
        info = self.get_model_info()
        limit = min(info.context_window, settings.MAX_CONTEXT_TOKENS)
        if tokens > limit:
            raise ContextWindowError(
                f"Message token count ({tokens}) exceeds limit ({limit}) "
                f"for model {self.model_name}"
            )

    def _build_completion_kwargs(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        result: dict[str, Any] = dict(
            model=self.model_name,
            messages=messages,
            temperature=kwargs.pop("temperature", settings.TEMPERATURE),
            max_tokens=kwargs.pop("max_tokens", settings.MAX_TOKENS),
            stream=stream,
        )
        if tools:
            result["tools"] = tools
        result.update(kwargs)
        return result

    def _handle_streaming_response(self, kwargs: dict[str, Any]) -> LLMResponse:
        kwargs["stream"] = True
        if self._router is not None:
            response = self._router.completion(**kwargs)
        else:
            response = litellm.completion(**kwargs)

        full_content: list[str] = []
        tool_calls: dict[int, dict[str, Any]] = {}
        finish_reason = "stop"
        usage: dict[str, int] = {}

        for chunk in response:
            if hasattr(chunk, "choices") and chunk.choices:
                delta = chunk.choices[0].delta if chunk.choices[0].delta else None
                if delta is None:
                    if hasattr(chunk, "usage") and chunk.usage:
                        usage = {
                            "prompt_tokens": getattr(chunk.usage, "prompt_tokens", 0) or 0,
                            "completion_tokens": getattr(chunk.usage, "completion_tokens", 0) or 0,
                            "total_tokens": getattr(chunk.usage, "total_tokens", 0) or 0,
                        }
                    continue
                if getattr(delta, "content", None):
                    full_content.append(delta.content)
                if getattr(delta, "tool_calls", None):
                    for tc in delta.tool_calls:
                        idx = getattr(tc, "index", 0)
                        if idx not in tool_calls:
                            tool_calls[idx] = {
                                "id": getattr(tc, "id", "") or "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }
                        if getattr(tc, "function", None):
                            if tc.function.name:
                                tool_calls[idx]["function"]["name"] += tc.function.name
                            if tc.function.arguments:
                                tool_calls[idx]["function"]["arguments"] += tc.function.arguments
                if chunk.choices[0].finish_reason:
                    finish_reason = chunk.choices[0].finish_reason

        sorted_calls = [tool_calls[i] for i in sorted(tool_calls)] if tool_calls else []
        content = "".join(full_content)
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)

        return LLMResponse(
            content=content or None,
            tool_calls=sorted_calls,
            finish_reason=finish_reason,
            usage=usage,
            model=self.model_name,
            provider=self.PROVIDER_NAME,
            cost=self._calculate_cost(input_tokens, output_tokens),
            raw=usage,
        )

    def _build_response(self, response: Any) -> LLMResponse:
        choice = response.choices[0]
        msg = choice.message
        content = getattr(msg, "content", None)
        finish_reason = getattr(choice, "finish_reason", "stop") or "stop"

        tool_calls = []
        if getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                tool_calls.append({
                    "id": getattr(tc, "id", ""),
                    "type": "function",
                    "function": {
                        "name": getattr(tc.function, "name", ""),
                        "arguments": getattr(tc.function, "arguments", ""),
                    },
                })

        usage_raw = getattr(response, "usage", None) or {}
        usage = {}
        input_tokens = 0
        output_tokens = 0
        if usage_raw:
            input_tokens = getattr(usage_raw, "prompt_tokens", 0) or 0
            output_tokens = getattr(usage_raw, "completion_tokens", 0) or 0
            usage = {
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": getattr(usage_raw, "total_tokens", 0) or 0,
            }

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
            model=self.model_name,
            provider=self.PROVIDER_NAME,
            cost=self._calculate_cost(input_tokens, output_tokens),
            raw=response,
        )

    def _classify_error(self, exc: Exception) -> None:
        msg = str(exc).lower()
        exc_name = type(exc).__name__.lower()

        if "auth" in exc_name or "api_key" in msg or "unauthorized" in msg:
            raise AuthError(f"LiteLLM auth error: {exc}") from exc
        if "rate" in msg or "429" in msg or "quota" in msg or "rate_limit" in exc_name:
            raise RateLimitError(f"LiteLLM rate limit: {exc}") from exc
        if "context" in msg or "max_tokens" in msg or "too many tokens" in msg:
            raise ContextWindowError(f"LiteLLM context window: {exc}") from exc
        if "connection" in msg or "timeout" in msg or "connect" in msg or "api" in exc_name:
            raise ApiError(f"LiteLLM API error: {exc}") from exc
        raise ModelError(f"LiteLLM error: {exc}") from exc


__all__ = ["LiteLLMProxy"]
