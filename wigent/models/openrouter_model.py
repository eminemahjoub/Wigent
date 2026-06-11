# ════════════════════════════════════════
# wigent — OpenRouter Model
# Role: Concrete provider for OpenRouter (300+ models, one key)
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""OpenRouter implementation of ``BaseModel``.

OpenRouter is an OpenAI-compatible unified gateway to 300+ models.
One API key gives access to Claude, GPT-4, Gemini, Llama, Qwen, Mistral,
DeepSeek, and many more — including free-tier models.

Models
------
Premium : anthropic/claude-3.5-sonnet, openai/gpt-4o, google/gemini-2.0-flash-exp
Coding  : qwen/qwen-2.5-coder-32b-instruct, deepseek/deepseek-coder
Free    : meta-llama/llama-3.2-3b-instruct:free, google/gemma-2-9b-it:free
          mistralai/mistral-7b-instruct:free, qwen/qwen-2.5-7b-instruct:free

Documentation: https://openrouter.ai/docs
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


class OpenRouterModel(BaseModel):
    """Provider wrapper around OpenRouter's OpenAI-compatible API."""

    PROVIDER_NAME = "openrouter"

    API_BASE_URL: str = "https://openrouter.ai/api/v1"
    DEFAULT_MODEL: str = "anthropic/claude-3.5-sonnet"
    APP_NAME: str = "Wigent"
    APP_URL: str = "https://github.com/eminemahjoub/Wigent"

    # Popular models with metadata
    MODEL_INFO: dict[str, ModelInfo] = {
        # Premium
        "anthropic/claude-3.5-sonnet": ModelInfo(
            name="anthropic/claude-3.5-sonnet",
            provider="openrouter",
            context_window=200_000,
            max_output_tokens=8_192,
            cost_per_1k_input=0.0030,
            cost_per_1k_output=0.0150,
        ),
        "openai/gpt-4o": ModelInfo(
            name="openai/gpt-4o",
            provider="openrouter",
            context_window=128_000,
            max_output_tokens=16_384,
            supports_vision=True,
            cost_per_1k_input=0.0025,
            cost_per_1k_output=0.0100,
        ),
        "openai/gpt-4o-mini": ModelInfo(
            name="openai/gpt-4o-mini",
            provider="openrouter",
            context_window=128_000,
            max_output_tokens=16_384,
            supports_vision=True,
            cost_per_1k_input=0.00015,
            cost_per_1k_output=0.00060,
        ),
        "google/gemini-2.0-flash-exp": ModelInfo(
            name="google/gemini-2.0-flash-exp",
            provider="openrouter",
            context_window=1_000_000,
            max_output_tokens=8_192,
            supports_vision=True,
            cost_per_1k_input=0.00125,
            cost_per_1k_output=0.00500,
        ),
        # Coding specialists
        "qwen/qwen-2.5-coder-32b-instruct": ModelInfo(
            name="qwen/qwen-2.5-coder-32b-instruct",
            provider="openrouter",
            context_window=32_000,
            max_output_tokens=8_192,
            cost_per_1k_input=0.0,
            cost_per_1k_output=0.0,
        ),
        "deepseek/deepseek-coder": ModelInfo(
            name="deepseek/deepseek-coder",
            provider="openrouter",
            context_window=32_000,
            max_output_tokens=8_192,
            cost_per_1k_input=0.0,
            cost_per_1k_output=0.0,
        ),
        # Free tier (no cost)
        "meta-llama/llama-3.2-3b-instruct:free": ModelInfo(
            name="meta-llama/llama-3.2-3b-instruct:free",
            provider="openrouter",
            context_window=128_000,
            max_output_tokens=8_192,
            cost_per_1k_input=0.0,
            cost_per_1k_output=0.0,
        ),
        "meta-llama/llama-3.3-70b-instruct:free": ModelInfo(
            name="meta-llama/llama-3.3-70b-instruct:free",
            provider="openrouter",
            context_window=128_000,
            max_output_tokens=8_192,
            cost_per_1k_input=0.0,
            cost_per_1k_output=0.0,
        ),
        "google/gemma-2-9b-it:free": ModelInfo(
            name="google/gemma-2-9b-it:free",
            provider="openrouter",
            context_window=8_000,
            max_output_tokens=4_096,
            cost_per_1k_input=0.0,
            cost_per_1k_output=0.0,
        ),
        "mistralai/mistral-7b-instruct:free": ModelInfo(
            name="mistralai/mistral-7b-instruct:free",
            provider="openrouter",
            context_window=32_000,
            max_output_tokens=8_192,
            cost_per_1k_input=0.0,
            cost_per_1k_output=0.0,
        ),
        "qwen/qwen-2.5-7b-instruct:free": ModelInfo(
            name="qwen/qwen-2.5-7b-instruct:free",
            provider="openrouter",
            context_window=32_000,
            max_output_tokens=8_192,
            cost_per_1k_input=0.0,
            cost_per_1k_output=0.0,
        ),
    }

    def __init__(self, model: str | None = None, **kwargs: Any) -> None:
        super().__init__(model=model, **kwargs)
        import openai

        api_key = settings.OPENROUTER_API_KEY or os.getenv("OPENROUTER_API_KEY") or ""
        self._client = openai.OpenAI(
            api_key=api_key,
            base_url=self.API_BASE_URL,
            default_headers={
                "HTTP-Referer": self.APP_URL,
                "X-Title": self.APP_NAME,
            },
        )

    def _default_model(self) -> str:
        return self.DEFAULT_MODEL

    def get_model_info(self) -> ModelInfo:
        base = self.MODEL_INFO.get(self.model_name)
        if base is not None:
            return base
        return ModelInfo(
            name=self.model_name,
            provider="openrouter",
            context_window=128_000,
            max_output_tokens=8_192,
        )

    def validate_api_key(self) -> bool:
        return bool(settings.OPENROUTER_API_KEY or os.getenv("OPENROUTER_API_KEY"))

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

        import openai

        try:
            if stream:
                return self._handle_streaming_response(params)

            response = self._client.chat.completions.create(**params)
            return self._build_response(response)

        except openai.APIConnectionError as exc:
            raise ApiError(f"OpenRouter connection error: {exc}") from exc
        except openai.RateLimitError as exc:
            raise RateLimitError(f"OpenRouter rate limited: {exc}") from exc
        except openai.AuthenticationError as exc:
            raise AuthError(f"OpenRouter auth error (check OPENROUTER_API_KEY): {exc}") from exc
        except openai.BadRequestError as exc:
            msg = str(exc).lower()
            if "context_length_exceeded" in msg or "maximum context" in msg:
                raise ContextWindowError(
                    f"Context window exceeded for {self.model_name}: {exc}"
                ) from exc
            raise ModelError(f"OpenRouter bad request: {exc}") from exc
        except openai.APIStatusError as exc:
            raise ModelError(f"OpenRouter API error ({exc.status_code}): {exc}") from exc

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
            stream_options={"include_usage": True},
        )
        if tools:
            params["tools"] = tools
            params["tool_choice"] = kwargs.pop("tool_choice", "auto")
        params.update(kwargs)

        import openai

        try:
            stream = self._client.chat.completions.create(**params)
        except openai.APIConnectionError as exc:
            raise ApiError(f"OpenRouter connection error: {exc}") from exc
        except openai.RateLimitError as exc:
            raise RateLimitError(f"OpenRouter rate limited: {exc}") from exc
        except openai.AuthenticationError as exc:
            raise AuthError(f"OpenRouter auth error: {exc}") from exc
        except openai.BadRequestError as exc:
            msg = str(exc).lower()
            if "context_length_exceeded" in msg or "maximum context" in msg:
                raise ContextWindowError(
                    f"Context window exceeded for {self.model_name}: {exc}"
                ) from exc
            raise ModelError(f"OpenRouter bad request: {exc}") from exc

        full_content: list[str] = []
        tool_calls: dict[int, dict[str, Any]] = {}
        finish_reason = "stop"
        usage: dict[str, int] = {}

        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is None:
                if chunk.usage:
                    usage = {
                        "prompt_tokens": chunk.usage.prompt_tokens or 0,
                        "completion_tokens": chunk.usage.completion_tokens or 0,
                        "total_tokens": chunk.usage.total_tokens or 0,
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

    def _handle_streaming_response(self, params: dict[str, Any]) -> LLMResponse:
        """Consume a streaming response internally and return the full result."""
        params["stream"] = True
        import openai

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
                        "prompt_tokens": chunk.usage.prompt_tokens or 0,
                        "completion_tokens": chunk.usage.completion_tokens or 0,
                        "total_tokens": chunk.usage.total_tokens or 0,
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

    def list_available_models(self) -> list[dict[str, Any]]:
        """Query OpenRouter for all available models."""
        try:
            import httpx
            response = httpx.get(
                f"{self.API_BASE_URL}/models",
                headers={"Authorization": f"Bearer {self._client.api_key}"},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])
        except Exception as exc:
            logger.warning("Failed to list OpenRouter models: %s", exc)
            return []

    def test_connection(self) -> bool:
        """Quick connectivity test using a free model."""
        try:
            self._client.chat.completions.create(
                model="meta-llama/llama-3.2-3b-instruct:free",
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=5,
            )
            return True
        except Exception:
            return False

    @staticmethod
    def handle_error(error: Exception) -> str:
        from wigent.models.base_model import ErrorType, handle_error as classify
        return classify(error).value


__all__ = ["OpenRouterModel"]
