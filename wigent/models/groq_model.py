# ════════════════════════════════════════
# wigent — Groq Model
# Role: Concrete provider for Groq ultra-fast inference
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Groq implementation of ``BaseModel``.

Groq provides ultra-low-latency inference for open-weight models via an
OpenAI-compatible API — this model subclasses the same patterns as
``OpenAIModel``.

Models
------
- ``llama-3.3-70b-versatile``
- ``llama-3.1-8b-instant``
- ``mixtral-8x7b-32768``
- ``deepseek-r1-distill-llama-70b``
- ``gemma2-9b-it``

Features
--------
- Streaming (OpenAI-compatible chunks)
- Function / tool calling
- Ultra-low latency
"""

from __future__ import annotations

import logging
import os
from typing import Any, Generator

from wigent.config import settings
from wigent.models.base_model import (
    ApiError,
    AuthError,
    BaseModel,
    ContextWindowError,
    LLMResponse,
    ModelError,
    ModelInfo,
    RateLimitError,
    retry_on_rate_limit,
)

logger = logging.getLogger(__name__)


class GroqModel(BaseModel):
    """Provider wrapper around the Groq Python SDK (OpenAI-compatible)."""

    PROVIDER_NAME = "groq"

    MODEL_INFO: dict[str, ModelInfo] = {
        "llama-3.3-70b-versatile": ModelInfo(
            name="llama-3.3-70b-versatile",
            provider="groq",
            context_window=32_768,
            max_output_tokens=8_192,
            cost_per_1k_input=0.00059,
            cost_per_1k_output=0.00079,
        ),
        "llama-3.1-8b-instant": ModelInfo(
            name="llama-3.1-8b-instant",
            provider="groq",
            context_window=32_768,
            max_output_tokens=8_192,
            cost_per_1k_input=0.00005,
            cost_per_1k_output=0.00008,
        ),
        "mixtral-8x7b-32768": ModelInfo(
            name="mixtral-8x7b-32768",
            provider="groq",
            context_window=32_768,
            max_output_tokens=8_192,
            cost_per_1k_input=0.00024,
            cost_per_1k_output=0.00024,
        ),
        "deepseek-r1-distill-llama-70b": ModelInfo(
            name="deepseek-r1-distill-llama-70b",
            provider="groq",
            context_window=32_768,
            max_output_tokens=8_192,
            cost_per_1k_input=0.00075,
            cost_per_1k_output=0.00099,
        ),
        "gemma2-9b-it": ModelInfo(
            name="gemma2-9b-it",
            provider="groq",
            context_window=8_192,
            max_output_tokens=4_096,
            cost_per_1k_input=0.00005,
            cost_per_1k_output=0.00008,
        ),
    }

    def __init__(self, model: str | None = None, **kwargs: Any) -> None:
        super().__init__(model=model, **kwargs)
        from groq import Groq

        api_key = settings.GROQ_API_KEY or os.getenv("GROQ_API_KEY") or ""
        self._client = Groq(api_key=api_key)

    def _default_model(self) -> str:
        return "llama-3.3-70b-versatile"

    def get_model_info(self) -> ModelInfo:
        base = self.MODEL_INFO.get(self.model_name)
        if base is not None:
            return base
        return ModelInfo(
            name=self.model_name,
            provider="groq",
            context_window=32_768,
            max_output_tokens=8_192,
        )

    def validate_api_key(self) -> bool:
        return bool(settings.GROQ_API_KEY or os.getenv("GROQ_API_KEY"))

    def count_tokens(self, messages: list[dict[str, Any]]) -> int:
        """Estimate tokens for Groq models (no native tokeniser)."""
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

        params: dict[str, Any] = dict(
            model=self.model_name,
            messages=messages,
            temperature=kwargs.pop("temperature", settings.TEMPERATURE),
            max_tokens=kwargs.pop("max_tokens", settings.MAX_TOKENS),
        )
        if tools:
            params["tools"] = tools
            params["tool_choice"] = kwargs.pop("tool_choice", "auto")
        params.update(kwargs)

        try:
            if stream:
                return self._handle_streaming_response(params)

            response = self._client.chat.completions.create(**params)
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

        params: dict[str, Any] = dict(
            model=self.model_name,
            messages=messages,
            temperature=kwargs.pop("temperature", settings.TEMPERATURE),
            max_tokens=kwargs.pop("max_tokens", settings.MAX_TOKENS),
            stream=True,
        )
        if tools:
            params["tools"] = tools
            params["tool_choice"] = kwargs.pop("tool_choice", "auto")
        params.update(kwargs)

        try:
            stream = self._client.chat.completions.create(**params)
        except Exception as exc:
            self._classify_error(exc)

        full_content: list[str] = []
        tool_calls: dict[int, dict[str, Any]] = {}
        finish_reason = "stop"
        usage: dict[str, int] = {}

        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is None:
                if chunk.usage:
                    usage = {
                        "prompt_tokens": getattr(chunk.usage, "prompt_tokens", 0) or 0,
                        "completion_tokens": getattr(chunk.usage, "completion_tokens", 0) or 0,
                        "total_tokens": getattr(chunk.usage, "total_tokens", 0) or 0,
                    }
                continue

            if delta.content:
                full_content.append(delta.content)
                yield delta.content

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls:
                        tool_calls[idx] = {
                            "id": tc.id or "",
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        }
                    if tc.function:
                        if tc.function.name:
                            tool_calls[idx]["function"]["name"] += tc.function.name
                        if tc.function.arguments:
                            tool_calls[idx]["function"]["arguments"] += tc.function.arguments

            if chunk.choices and chunk.choices[0].finish_reason:
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

    def _handle_streaming_response(self, params: dict[str, Any]) -> LLMResponse:
        params["stream"] = True
        stream = self._client.chat.completions.create(**params)
        full_content: list[str] = []
        tool_calls: dict[int, dict[str, Any]] = {}
        finish_reason = "stop"
        usage: dict[str, int] = {}

        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is None:
                if chunk.usage:
                    usage = {
                        "prompt_tokens": getattr(chunk.usage, "prompt_tokens", 0) or 0,
                        "completion_tokens": getattr(chunk.usage, "completion_tokens", 0) or 0,
                        "total_tokens": getattr(chunk.usage, "total_tokens", 0) or 0,
                    }
                continue
            if delta.content:
                full_content.append(delta.content)
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls:
                        tool_calls[idx] = {
                            "id": tc.id or "",
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        }
                    if tc.function:
                        if tc.function.name:
                            tool_calls[idx]["function"]["name"] += tc.function.name
                        if tc.function.arguments:
                            tool_calls[idx]["function"]["arguments"] += tc.function.arguments
            if chunk.choices and chunk.choices[0].finish_reason:
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
        )

    def _build_response(self, response: Any) -> LLMResponse:
        choice = response.choices[0]
        msg = choice.message
        content = msg.content
        finish_reason = choice.finish_reason or "stop"

        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                })

        usage_raw = response.usage
        usage = {}
        input_tokens = 0
        output_tokens = 0
        if usage_raw:
            input_tokens = usage_raw.prompt_tokens or 0
            output_tokens = usage_raw.completion_tokens or 0
            usage = {
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": usage_raw.total_tokens or 0,
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

        if "auth" in exc_name or "api_key" in msg or "unauthorized" in msg or "forbidden" in msg:
            raise AuthError(f"Groq auth error: {exc}") from exc
        if "rate" in exc_name or "rate" in msg or "429" in msg or "quota" in msg:
            raise RateLimitError(f"Groq rate limit: {exc}") from exc
        if "context" in msg or "max_tokens" in msg or "too many tokens" in msg:
            raise ContextWindowError(f"Groq context window: {exc}") from exc
        if "connection" in exc_name or "timeout" in msg or "connect" in msg:
            raise ApiError(f"Groq API error: {exc}") from exc
        raise ModelError(f"Groq error: {exc}") from exc


__all__ = ["GroqModel"]
