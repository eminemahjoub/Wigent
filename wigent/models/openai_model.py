# ════════════════════════════════════════
# wigent — OpenAI Model
# Role: Concrete provider for OpenAI / Azure OpenAI
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""OpenAI / Azure OpenAI implementation of ``BaseModel``.

Models
------
- ``gpt-4o``, ``gpt-4o-mini``, ``gpt-4.1``
- ``gpt-4.1-mini``, ``gpt-4.1-nano``
- ``o1``, ``o1-mini``, ``o3``, ``o3-mini``

Features
--------
- Streaming (all models except o1/o3 reasoning models)
- Function / tool calling
- Vision (gpt-4o, gpt-4.1 family)
- Token counting via ``tiktoken``
- Azure OpenAI (set ``AZURE_OPENAI_ENDPOINT`` / ``AZURE_OPENAI_KEY``)
"""

from __future__ import annotations

import logging
import os
from typing import Any, Generator

import tiktoken

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


class OpenAIModel(BaseModel):
    """Provider wrapper around the OpenAI Python SDK."""

    PROVIDER_NAME = "openai"

    MODEL_INFO: dict[str, ModelInfo] = {
        "gpt-4o": ModelInfo(
            name="gpt-4o",
            provider="openai",
            context_window=128_000,
            max_output_tokens=16_384,
            supports_vision=True,
            cost_per_1k_input=0.0025,
            cost_per_1k_output=0.0100,
        ),
        "gpt-4o-mini": ModelInfo(
            name="gpt-4o-mini",
            provider="openai",
            context_window=128_000,
            max_output_tokens=16_384,
            supports_vision=True,
            cost_per_1k_input=0.00015,
            cost_per_1k_output=0.00060,
        ),
        "gpt-4.1": ModelInfo(
            name="gpt-4.1",
            provider="openai",
            context_window=1_047_576,
            max_output_tokens=32_768,
            supports_vision=True,
            cost_per_1k_input=0.0020,
            cost_per_1k_output=0.0080,
        ),
        "gpt-4.1-mini": ModelInfo(
            name="gpt-4.1-mini",
            provider="openai",
            context_window=1_047_576,
            max_output_tokens=32_768,
            supports_vision=True,
            cost_per_1k_input=0.00040,
            cost_per_1k_output=0.00160,
        ),
        "gpt-4.1-nano": ModelInfo(
            name="gpt-4.1-nano",
            provider="openai",
            context_window=1_047_576,
            max_output_tokens=32_768,
            supports_vision=True,
            cost_per_1k_input=0.00010,
            cost_per_1k_output=0.00040,
        ),
        "o1": ModelInfo(
            name="o1",
            provider="openai",
            context_window=200_000,
            max_output_tokens=100_000,
            supports_streaming=False,
            supports_function_calling=True,
            cost_per_1k_input=0.0150,
            cost_per_1k_output=0.0600,
        ),
        "o1-mini": ModelInfo(
            name="o1-mini",
            provider="openai",
            context_window=128_000,
            max_output_tokens=65_536,
            supports_streaming=False,
            supports_function_calling=True,
            cost_per_1k_input=0.00110,
            cost_per_1k_output=0.00440,
        ),
        "o3": ModelInfo(
            name="o3",
            provider="openai",
            context_window=200_000,
            max_output_tokens=100_000,
            supports_streaming=False,
            supports_function_calling=True,
            cost_per_1k_input=0.0100,
            cost_per_1k_output=0.0400,
        ),
        "o3-mini": ModelInfo(
            name="o3-mini",
            provider="openai",
            context_window=200_000,
            max_output_tokens=100_000,
            supports_streaming=False,
            supports_function_calling=True,
            cost_per_1k_input=0.00110,
            cost_per_1k_output=0.00440,
        ),
    }

    def __init__(self, model: str | None = None, **kwargs: Any) -> None:
        super().__init__(model=model, **kwargs)
        import openai

        api_key = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY") or ""
        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT") or ""
        azure_key = os.getenv("AZURE_OPENAI_KEY") or ""

        if azure_endpoint and azure_key:
            self._client = openai.AzureOpenAI(
                api_key=azure_key,
                azure_endpoint=azure_endpoint,
                api_version=os.getenv("AZURE_OPENAI_VERSION", "2025-01-01-preview"),
            )
            self._is_azure = True
        else:
            self._client = openai.OpenAI(api_key=api_key)
            self._is_azure = False

        self._tokenizer: tiktoken.Encoding | None = None
        self._init_tokenizer()

    def _init_tokenizer(self) -> None:
        try:
            model_enc = self.model_name
            if model_enc.startswith("o1") or model_enc.startswith("o3"):
                model_enc = "gpt-4o"
            elif model_enc.startswith("gpt-4"):
                model_enc = self.model_name
            self._tokenizer = tiktoken.encoding_for_model(model_enc)
        except KeyError:
            self._tokenizer = tiktoken.get_encoding("cl100k_base")

    def _default_model(self) -> str:
        return "gpt-4o"

    def get_model_info(self) -> ModelInfo:
        base = self.MODEL_INFO.get(self.model_name)
        if base is not None:
            return base
        return ModelInfo(
            name=self.model_name,
            provider="openai",
            context_window=128_000,
            max_output_tokens=16_384,
        )

    def validate_api_key(self) -> bool:
        if self._is_azure:
            return bool(os.getenv("AZURE_OPENAI_KEY"))
        return bool(settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY"))

    # ── Token counting ───────────────────────────────────────────────

    def count_tokens(self, messages: list[dict[str, Any]]) -> int:
        """Count tokens using ``tiktoken`` with the standard chat formula."""
        if self._tokenizer is None:
            return super().count_tokens(messages)
        enc = self._tokenizer
        tokens_per_message = 3
        tokens_per_name = 1
        total = 0
        for msg in messages:
            total += tokens_per_message
            for key, value in msg.items():
                if isinstance(value, str):
                    total += len(enc.encode(value))
                elif isinstance(value, list):
                    for block in value:
                        if isinstance(block, dict):
                            txt = block.get("text", "")
                            if txt:
                                total += len(enc.encode(str(txt)))
                if key == "name":
                    total += tokens_per_name
        total += 3
        return total

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

        model_info = self.get_model_info()
        can_stream = stream and model_info.supports_streaming

        params: dict[str, Any] = dict(
            model=self.model_name,
            messages=messages,
            temperature=kwargs.pop("temperature", settings.TEMPERATURE),
            max_tokens=kwargs.pop("max_tokens", settings.MAX_TOKENS),
        )
        if tools:
            params["tools"] = tools
            params["tool_choice"] = kwargs.pop("tool_choice", "auto")
        if params.get("temperature") is not None and not can_stream:
            params.pop("temperature", None)
        params.update(kwargs)

        try:
            if can_stream:
                return self._handle_streaming_response(params)

            response = self._client.chat.completions.create(**params)
            return self._build_response(response)

        except openai.APIConnectionError as exc:
            raise ApiError(f"OpenAI connection error: {exc}") from exc
        except openai.RateLimitError as exc:
            raise RateLimitError(f"OpenAI rate limited: {exc}") from exc
        except openai.AuthenticationError as exc:
            raise AuthError(f"OpenAI auth error: {exc}") from exc
        except openai.BadRequestError as exc:
            msg = str(exc).lower()
            if "context_length_exceeded" in msg or "maximum context" in msg:
                raise ContextWindowError(
                    f"Context window exceeded for {self.model_name}: {exc}"
                ) from exc
            raise ModelError(f"OpenAI bad request: {exc}") from exc
        except openai.APIStatusError as exc:
            raise ModelError(f"OpenAI API error ({exc.status_code}): {exc}") from exc

    # ── Streaming ────────────────────────────────────────────────────

    def stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> Generator[str, None, LLMResponse]:
        self._check_context_window(messages)

        model_info = self.get_model_info()
        if not model_info.supports_streaming:
            response = self.chat(messages=messages, tools=tools, stream=False, **kwargs)
            yield response.content or ""
            return response

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
            raise ApiError(f"OpenAI connection error: {exc}") from exc
        except openai.RateLimitError as exc:
            raise RateLimitError(f"OpenAI rate limited: {exc}") from exc
        except openai.AuthenticationError as exc:
            raise AuthError(f"OpenAI auth error: {exc}") from exc
        except openai.BadRequestError as exc:
            msg = str(exc).lower()
            if "context_length_exceeded" in msg or "maximum context" in msg:
                raise ContextWindowError(
                    f"Context window exceeded for {self.model_name}: {exc}"
                ) from exc
            raise ModelError(f"OpenAI bad request: {exc}") from exc

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

    @staticmethod
    def handle_error(error: Exception) -> str:
        from wigent.models.base_model import ErrorType, handle_error as classify
        return classify(error).value


__all__ = ["OpenAIModel"]
