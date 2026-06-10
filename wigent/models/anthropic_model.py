# ════════════════════════════════════════
# wigent — Anthropic Model
# Role: Concrete provider for Anthropic Claude
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Anthropic Claude implementation of ``BaseModel``.

Models
------
- ``claude-sonnet-4-20250514`` (Claude Sonnet 4)
- ``claude-3.5-sonnet-20241022``
- ``claude-3.5-haiku-20241022``
- ``claude-opus-4-20250514``

Features
--------
- Streaming
- Tool use / function calling
- Vision (image inputs in messages)
- Extended thinking (Sonnet 4 / Opus 4, 200 K context)
- Token counting via ``client.count_tokens()``
"""

from __future__ import annotations

import json
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


class AnthropicModel(BaseModel):
    """Provider wrapper around the Anthropic Python SDK."""

    PROVIDER_NAME = "anthropic"

    MODEL_INFO: dict[str, ModelInfo] = {
        "claude-sonnet-4-20250514": ModelInfo(
            name="claude-sonnet-4-20250514",
            provider="anthropic",
            context_window=200_000,
            max_output_tokens=8_192,
            supports_vision=True,
            supports_extended_thinking=True,
            cost_per_1k_input=0.0030,
            cost_per_1k_output=0.0150,
        ),
        "claude-3.5-sonnet-20241022": ModelInfo(
            name="claude-3.5-sonnet-20241022",
            provider="anthropic",
            context_window=200_000,
            max_output_tokens=8_192,
            supports_vision=True,
            supports_extended_thinking=False,
            cost_per_1k_input=0.0030,
            cost_per_1k_output=0.0150,
        ),
        "claude-3.5-haiku-20241022": ModelInfo(
            name="claude-3.5-haiku-20241022",
            provider="anthropic",
            context_window=200_000,
            max_output_tokens=8_192,
            supports_vision=True,
            supports_extended_thinking=False,
            cost_per_1k_input=0.00080,
            cost_per_1k_output=0.0040,
        ),
        "claude-opus-4-20250514": ModelInfo(
            name="claude-opus-4-20250514",
            provider="anthropic",
            context_window=200_000,
            max_output_tokens=8_192,
            supports_vision=True,
            supports_extended_thinking=True,
            cost_per_1k_input=0.0150,
            cost_per_1k_output=0.0750,
        ),
    }

    def __init__(self, model: str | None = None, **kwargs: Any) -> None:
        super().__init__(model=model, **kwargs)
        import anthropic

        api_key = settings.ANTHROPIC_API_KEY or os.getenv("ANTHROPIC_API_KEY") or ""
        self._client = anthropic.Anthropic(api_key=api_key)

    def _default_model(self) -> str:
        return "claude-sonnet-4-20250514"

    def get_model_info(self) -> ModelInfo:
        base = self.MODEL_INFO.get(self.model_name)
        if base is not None:
            return base
        return ModelInfo(
            name=self.model_name,
            provider="anthropic",
            context_window=200_000,
            max_output_tokens=8_192,
        )

    def validate_api_key(self) -> bool:
        return bool(settings.ANTHROPIC_API_KEY or os.getenv("ANTHROPIC_API_KEY"))

    # ── Token counting ───────────────────────────────────────────────

    def count_tokens(self, messages: list[dict[str, Any]]) -> int:
        """Count tokens via the Anthropic SDK."""
        try:
            formatted = self._format_messages(messages)
            system = self._extract_system(messages)
            response = self._client.count_tokens(
                model=self.model_name,
                messages=formatted,
                system=system or "",
            )
            return response.input_tokens or 0
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

        if stream:
            return self._consume_stream(messages, tools, **kwargs)

        formatted = self._format_messages(messages)
        system = self._extract_system(messages)
        anthropic_tools = self._convert_tools(tools) if tools else None

        params: dict[str, Any] = dict(
            model=self.model_name,
            messages=formatted,
            max_tokens=kwargs.pop("max_tokens", settings.MAX_TOKENS),
            temperature=kwargs.pop("temperature", settings.TEMPERATURE),
        )
        if system:
            params["system"] = system
        if anthropic_tools:
            params["tools"] = anthropic_tools

        use_extended_thinking = kwargs.pop(
            "extended_thinking",
            self.get_model_info().supports_extended_thinking,
        )
        if use_extended_thinking and anthropic_tools:
            params["thinking"] = {
                "type": "enabled",
                "budget_tokens": int(settings.MAX_TOKENS * 0.8),
            }

        params.update(kwargs)

        import anthropic

        try:
            response = self._client.messages.create(**params)
            return self._build_response(response)
        except anthropic.APIConnectionError as exc:
            raise ApiError(f"Anthropic connection error: {exc}") from exc
        except anthropic.RateLimitError as exc:
            raise RateLimitError(f"Anthropic rate limited: {exc}") from exc
        except anthropic.AuthenticationError as exc:
            raise AuthError(f"Anthropic auth error: {exc}") from exc
        except anthropic.BadRequestError as exc:
            msg = str(exc).lower()
            if "too many tokens" in msg or "max_tokens" in msg:
                raise ContextWindowError(
                    f"Context window exceeded for {self.model_name}: {exc}"
                ) from exc
            raise ModelError(f"Anthropic bad request: {exc}") from exc
        except anthropic.APIStatusError as exc:
            raise ModelError(f"Anthropic API error ({exc.status_code}): {exc}") from exc

    # ── Streaming ────────────────────────────────────────────────────

    def stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> Generator[str, None, LLMResponse]:
        self._check_context_window(messages)

        formatted = self._format_messages(messages)
        system = self._extract_system(messages)
        anthropic_tools = self._convert_tools(tools) if tools else None

        params: dict[str, Any] = dict(
            model=self.model_name,
            messages=formatted,
            max_tokens=kwargs.pop("max_tokens", settings.MAX_TOKENS),
            temperature=kwargs.pop("temperature", settings.TEMPERATURE),
            stream=True,
        )
        if system:
            params["system"] = system
        if anthropic_tools:
            params["tools"] = anthropic_tools
        params.update(kwargs)

        import anthropic

        try:
            stream = self._client.messages.create(**params)
        except anthropic.APIConnectionError as exc:
            raise ApiError(f"Anthropic connection error: {exc}") from exc
        except anthropic.RateLimitError as exc:
            raise RateLimitError(f"Anthropic rate limited: {exc}") from exc
        except anthropic.AuthenticationError as exc:
            raise AuthError(f"Anthropic auth error: {exc}") from exc

        full_content: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        tool_call_in_progress: dict[str, Any] | None = None
        finish_reason = "stop"
        usage: dict[str, int] = {}
        input_tokens = 0
        output_tokens = 0

        for event in stream:
            if event.type == "content_block_start":
                if event.content_block.type == "tool_use":
                    tool_call_in_progress = {
                        "id": event.content_block.id,
                        "type": "function",
                        "function": {
                            "name": event.content_block.name,
                            "arguments": "",
                        },
                    }

            elif event.type == "content_block_delta":
                if event.delta.type == "text_delta":
                    full_content.append(event.delta.text)
                    yield event.delta.text
                elif event.delta.type == "input_json_delta":
                    if tool_call_in_progress is not None:
                        tool_call_in_progress["function"]["arguments"] += event.delta.partial_json

            elif event.type == "content_block_stop":
                if tool_call_in_progress is not None:
                    tool_calls.append(tool_call_in_progress)
                    tool_call_in_progress = None

            elif event.type == "message_delta":
                if event.delta.stop_reason:
                    finish_reason = event.delta.stop_reason
                if event.usage:
                    output_tokens = event.usage.output_tokens or 0

            elif event.type == "message_start":
                if event.message.usage:
                    input_tokens = event.message.usage.input_tokens or 0

        usage = {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }
        content = "".join(full_content)

        return LLMResponse(
            content=content or None,
            tool_calls=tool_calls,
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

    def _consume_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Call stream_chat internally and consume it into a single response."""
        gen = self.stream_chat(messages=messages, tools=tools, **kwargs)
        full_content: list[str] = []
        try:
            while True:
                chunk = next(gen)
                if isinstance(chunk, str):
                    full_content.append(chunk)
        except StopIteration as exc:
            response = exc.value if hasattr(exc, "value") else gen.close()
            if isinstance(response, LLMResponse):
                response.content = "".join(full_content) or response.content
                return response
            return LLMResponse(content="".join(full_content) or None)
        except Exception:
            raise

    def _format_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert OpenAI-format messages to Anthropic format."""
        formatted = []
        for msg in messages:
            role = msg.get("role", "user")
            if role == "system":
                continue
            if role == "assistant":
                content = self._format_assistant_content(msg)
                formatted.append({"role": "assistant", "content": content})
                continue
            content = msg.get("content", "")
            if isinstance(content, str):
                formatted.append({"role": "user", "content": content})
            elif isinstance(content, list):
                blocks = []
                for block in content:
                    if isinstance(block, dict):
                        btype = block.get("type", "text")
                        if btype == "text":
                            blocks.append({"type": "text", "text": block.get("text", "")})
                        elif btype == "image_url":
                            image_url = block.get("image_url", {})
                            url = image_url.get("url", "") if isinstance(image_url, dict) else ""
                            blocks.append(self._make_image_block(url))
                formatted.append({"role": "user", "content": blocks})
        return formatted

    def _format_assistant_content(self, msg: dict[str, Any]) -> list[dict[str, Any]]:
        content = msg.get("content", "")
        tool_calls = msg.get("tool_calls")
        blocks: list[dict[str, Any]] = []
        if content:
            blocks.append({"type": "text", "text": content if isinstance(content, str) else str(content)})
        if tool_calls:
            for tc in tool_calls:
                func = tc.get("function", {})
                blocks.append({
                    "type": "tool_use",
                    "id": tc.get("id", ""),
                    "name": func.get("name", ""),
                    "input": json.loads(func.get("arguments", "{}")),
                })
        return blocks if blocks else [{"type": "text", "text": ""}]

    def _extract_system(self, messages: list[dict[str, Any]]) -> str:
        parts = [m["content"] for m in messages if m.get("role") == "system" and isinstance(m.get("content"), str)]
        return "\n\n".join(parts)

    def _convert_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """OpenAI-format → Anthropic tool format."""
        result = []
        for tool in tools:
            func = tool.get("function", tool)
            result.append({
                "name": func.get("name", ""),
                "description": func.get("description", ""),
                "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
            })
        return result

    def _make_image_block(self, url: str) -> dict[str, Any]:
        """Convert an image URL to an Anthropic image content block."""
        if url.startswith("data:"):
            import base64
            header, _, encoded = url.partition(",")
            media_type = header.replace("data:", "").replace(";base64", "") or "image/png"
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": encoded,
                },
            }
        return {
            "type": "image",
            "source": {
                "type": "url",
                "url": url,
            },
        }

    def _build_response(self, response: Any) -> LLMResponse:
        content = ""
        tool_calls: list[dict[str, Any]] = []
        finish_reason = "stop"
        input_tokens = 0
        output_tokens = 0

        if response.usage:
            input_tokens = response.usage.input_tokens or 0
            output_tokens = response.usage.output_tokens or 0

        for block in response.content:
            if block.type == "text":
                content = block.text
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "type": "function",
                    "function": {
                        "name": block.name,
                        "arguments": json.dumps(block.input) if hasattr(block.input, "model_dump") else json.dumps(block.input),
                    },
                })

        if hasattr(response, "stop_reason") and response.stop_reason:
            finish_reason = response.stop_reason

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


__all__ = ["AnthropicModel"]
