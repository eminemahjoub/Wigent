# ════════════════════════════════════════
# wigent — Gemini Model
# Role: Concrete provider for Google Gemini
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Google Gemini implementation of ``BaseModel``.

Models
------
- ``gemini-2.5-pro-exp-03-25`` (1M context)
- ``gemini-2.5-flash-preview-04-17``
- ``gemini-2.0-flash``
- ``gemini-2.0-flash-lite``

Features
--------
- Streaming
- Function calling
- 1M token context window (Gemini 2.5 Pro)
- Token counting via ``client.count_tokens()``
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Generator

import google.generativeai as genai

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


class GeminiModel(BaseModel):
    """Provider wrapper around the Google Generative AI SDK."""

    PROVIDER_NAME = "gemini"

    MODEL_INFO: dict[str, ModelInfo] = {
        "gemini-2.5-pro-exp-03-25": ModelInfo(
            name="gemini-2.5-pro-exp-03-25",
            provider="gemini",
            context_window=1_000_000,
            max_output_tokens=8_192,
            supports_function_calling=True,
            cost_per_1k_input=0.00125,
            cost_per_1k_output=0.00500,
        ),
        "gemini-2.5-flash-preview-04-17": ModelInfo(
            name="gemini-2.5-flash-preview-04-17",
            provider="gemini",
            context_window=1_000_000,
            max_output_tokens=8_192,
            supports_function_calling=True,
            cost_per_1k_input=0.00015,
            cost_per_1k_output=0.00060,
        ),
        "gemini-2.0-flash": ModelInfo(
            name="gemini-2.0-flash",
            provider="gemini",
            context_window=1_048_576,
            max_output_tokens=8_192,
            supports_function_calling=True,
            cost_per_1k_input=0.00010,
            cost_per_1k_output=0.00040,
        ),
        "gemini-2.0-flash-lite": ModelInfo(
            name="gemini-2.0-flash-lite",
            provider="gemini",
            context_window=1_048_576,
            max_output_tokens=8_192,
            supports_function_calling=True,
            cost_per_1k_input=0.000075,
            cost_per_1k_output=0.00030,
        ),
    }

    def __init__(self, model: str | None = None, **kwargs: Any) -> None:
        super().__init__(model=model, **kwargs)
        api_key = settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY") or ""
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(self.model_name)

    def _default_model(self) -> str:
        return "gemini-2.5-pro-exp-03-25"

    def get_model_info(self) -> ModelInfo:
        base = self.MODEL_INFO.get(self.model_name)
        if base is not None:
            return base
        return ModelInfo(
            name=self.model_name,
            provider="gemini",
            context_window=1_000_000,
            max_output_tokens=8_192,
        )

    def validate_api_key(self) -> bool:
        return bool(settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY"))

    # ── Token counting ───────────────────────────────────────────────

    def count_tokens(self, messages: list[dict[str, Any]]) -> int:
        """Count tokens using the Gemini SDK."""
        try:
            contents = self._to_gemini_contents(messages)
            response = self._model.count_tokens(contents)
            return response.total_tokens or 0
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

        contents = self._to_gemini_contents(messages)
        system_prompt = self._extract_system(messages)
        gemini_tools = self._convert_tools(tools) if tools else None

        gen_config = genai.types.GenerationConfig(
            temperature=kwargs.pop("temperature", settings.TEMPERATURE),
            max_output_tokens=kwargs.pop("max_tokens", settings.MAX_TOKENS),
        )

        safety_settings = kwargs.pop("safety_settings", None)

        try:
            if stream:
                return self._handle_streaming_response(
                    contents, gemini_tools, system_prompt, gen_config, safety_settings, **kwargs
                )

            model = self._get_model(system_prompt)
            response = model.generate_content(
                contents,
                tools=gemini_tools,
                generation_config=gen_config,
                safety_settings=safety_settings,
                **kwargs,
            )
            return self._build_response(response)

        except Exception as exc:
            self._classify_error(exc)

    def _get_model(self, system_prompt: str | None = None) -> genai.GenerativeModel:
        if system_prompt:
            return genai.GenerativeModel(self.model_name, system_instruction=system_prompt)
        return genai.GenerativeModel(self.model_name)

    # ── Streaming ────────────────────────────────────────────────────

    def stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> Generator[str, None, LLMResponse]:
        self._check_context_window(messages)

        contents = self._to_gemini_contents(messages)
        system_prompt = self._extract_system(messages)
        gemini_tools = self._convert_tools(tools) if tools else None

        gen_config = genai.types.GenerationConfig(
            temperature=kwargs.pop("temperature", settings.TEMPERATURE),
            max_output_tokens=kwargs.pop("max_tokens", settings.MAX_TOKENS),
        )

        try:
            model = self._get_model(system_prompt)
            stream = model.generate_content(
                contents,
                tools=gemini_tools,
                generation_config=gen_config,
                stream=True,
                **kwargs,
            )
        except Exception as exc:
            self._classify_error(exc)

        full_content: list[str] = []
        usage: dict[str, int] = {}

        for chunk in stream:
            if chunk.text:
                full_content.append(chunk.text)
                yield chunk.text
            if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
                meta = chunk.usage_metadata
                usage = {
                    "prompt_tokens": meta.prompt_token_count or 0,
                    "completion_tokens": meta.candidates_token_count or 0,
                    "total_tokens": meta.total_token_count or 0,
                }

        content = "".join(full_content)
        input_t = usage.get("prompt_tokens", 0)
        output_t = usage.get("completion_tokens", 0)

        return LLMResponse(
            content=content or None,
            tool_calls=[],
            finish_reason="stop",
            usage=usage,
            model=self.model_name,
            provider=self.PROVIDER_NAME,
            cost=self._calculate_cost(input_t, output_t),
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

    def _handle_streaming_response(
        self,
        contents: list[Any],
        tools: list[dict[str, Any]] | None,
        system_prompt: str | None,
        gen_config: Any,
        safety_settings: Any = None,
        **kwargs: Any,
    ) -> LLMResponse:
        model = self._get_model(system_prompt)
        stream = model.generate_content(
            contents,
            tools=tools,
            generation_config=gen_config,
            stream=True,
            safety_settings=safety_settings,
            **kwargs,
        )
        full_content: list[str] = []
        usage: dict[str, int] = {}
        for chunk in stream:
            if chunk.text:
                full_content.append(chunk.text)
            if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
                meta = chunk.usage_metadata
                usage = {
                    "prompt_tokens": meta.prompt_token_count or 0,
                    "completion_tokens": meta.candidates_token_count or 0,
                    "total_tokens": meta.total_token_count or 0,
                }
        content = "".join(full_content)
        input_t = usage.get("prompt_tokens", 0)
        output_t = usage.get("completion_tokens", 0)
        return LLMResponse(
            content=content or None,
            tool_calls=[],
            finish_reason="stop",
            usage=usage,
            model=self.model_name,
            provider=self.PROVIDER_NAME,
            cost=self._calculate_cost(input_t, output_t),
        )

    def _to_gemini_contents(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert OpenAI-format messages to Gemini content parts."""
        contents = []
        for msg in messages:
            role = msg.get("role", "user")
            if role == "system":
                continue
            if role == "assistant":
                role_g = "model"
            else:
                role_g = "user"

            content = msg.get("content", "")
            parts: list[dict[str, Any]] = []
            if isinstance(content, str):
                parts.append({"text": content})
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        btype = block.get("type", "text")
                        if btype == "text":
                            parts.append({"text": block.get("text", "")})
                        elif btype == "image_url":
                            url = ""
                            iu = block.get("image_url", {})
                            if isinstance(iu, dict):
                                url = iu.get("url", "")
                            parts.append(self._make_inline_image(url))

            tool_calls = msg.get("tool_calls")
            if tool_calls:
                for tc in tool_calls:
                    func = tc.get("function", {})
                    parts.append({
                        "function_call": {
                            "name": func.get("name", ""),
                            "args": json.loads(func.get("arguments", "{}")),
                        },
                    })

            contents.append({"role": role_g, "parts": parts})

        return contents

    def _extract_system(self, messages: list[dict[str, Any]]) -> str | None:
        parts = [
            m["content"] for m in messages
            if m.get("role") == "system" and isinstance(m.get("content"), str)
        ]
        return "\n\n".join(parts) if parts else None

    def _convert_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """OpenAI-format → Gemini FunctionDeclaration list."""
        result = []
        for tool in tools:
            func = tool.get("function", tool)
            result.append({
                "function_declarations": [{
                    "name": func.get("name", ""),
                    "description": func.get("description", ""),
                    "parameters": func.get("parameters", {"type": "object", "properties": {}}),
                }],
            })
        return result

    def _make_inline_image(self, url: str) -> dict[str, Any]:
        """Convert an image URL to a Gemini inline data part."""
        if url.startswith("data:"):
            import base64
            header, _, encoded = url.partition(",")
            media_type = header.replace("data:", "").replace(";base64", "") or "image/png"
            return {
                "inline_data": {
                    "mime_type": media_type,
                    "data": encoded,
                },
            }
        return {"text": f"[Image: {url}]"}

    def _build_response(self, response: Any) -> LLMResponse:
        content = ""
        tool_calls: list[dict[str, Any]] = []
        finish_reason = "stop"
        input_tokens = 0
        output_tokens = 0

        try:
            content = response.text or ""
        except (ValueError, AttributeError):
            content = ""

        if hasattr(response, "candidates") and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, "content") and candidate.content:
                for part in candidate.content.parts:
                    if hasattr(part, "function_call") and part.function_call:
                        tool_calls.append({
                            "id": part.function_call.name,
                            "type": "function",
                            "function": {
                                "name": part.function_call.name,
                                "arguments": json.dumps(
                                    part.function_call.args,
                                    default=str,
                                ) if hasattr(part.function_call, "args") else "{}",
                            },
                        })
            if hasattr(candidate, "finish_reason"):
                finish_reason = str(candidate.finish_reason)

        if hasattr(response, "usage_metadata") and response.usage_metadata:
            meta = response.usage_metadata
            input_tokens = meta.prompt_token_count or 0
            output_tokens = meta.candidates_token_count or 0

        usage = {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }

        return LLMResponse(
            content=content or None,
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
        if "api_key" in msg or "permission" in msg or "not found" in msg:
            raise AuthError(f"Gemini auth error: {exc}") from exc
        if "rate" in msg or "quota" in msg or "429" in msg:
            raise RateLimitError(f"Gemini rate limit: {exc}") from exc
        if "maximum context" in msg or "too long" in msg or "token count" in msg:
            raise ContextWindowError(f"Gemini context window: {exc}") from exc
        if "deadline exceeded" in msg or "unavailable" in msg or "connection" in msg:
            raise ApiError(f"Gemini API error: {exc}") from exc
        raise ModelError(f"Gemini error: {exc}") from exc


__all__ = ["GeminiModel"]
