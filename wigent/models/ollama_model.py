# ════════════════════════════════════════
# wigent — Ollama Model
# Role: Concrete provider for local Ollama inference
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Ollama implementation of ``BaseModel``.

Supports any model served by a local Ollama instance (default
``http://localhost:11434``).  Auto-detects available models on init.

Models
------
- ``llama3.3:70b``, ``llama3.1:8b``, ``mistral:7b``
- ``codellama:34b``, ``deepseek-coder:33b``
- ``qwen2.5-coder:32b``, ``phi-4:14b``
- *any other model pulled locally*

Features
--------
- Streaming
- Function calling (via native Ollama tool support)
- No API key needed
- Auto-detect available models
- Local inference (free, private)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Generator

import requests

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


class OllamaModel(BaseModel):
    """Provider wrapper around the Ollama HTTP API."""

    PROVIDER_NAME = "ollama"

    MODEL_INFO: dict[str, ModelInfo] = {
        "llama3.3:70b": ModelInfo(
            name="llama3.3:70b",
            provider="ollama",
            context_window=32_768,
            max_output_tokens=8_192,
            supports_function_calling=True,
            cost_per_1k_input=0.0,
            cost_per_1k_output=0.0,
        ),
        "llama3.1:8b": ModelInfo(
            name="llama3.1:8b",
            provider="ollama",
            context_window=32_768,
            max_output_tokens=8_192,
            supports_function_calling=True,
            cost_per_1k_input=0.0,
            cost_per_1k_output=0.0,
        ),
        "mistral:7b": ModelInfo(
            name="mistral:7b",
            provider="ollama",
            context_window=32_768,
            max_output_tokens=8_192,
            supports_function_calling=True,
            cost_per_1k_input=0.0,
            cost_per_1k_output=0.0,
        ),
        "codellama:34b": ModelInfo(
            name="codellama:34b",
            provider="ollama",
            context_window=16_384,
            max_output_tokens=4_096,
            supports_function_calling=False,
            cost_per_1k_input=0.0,
            cost_per_1k_output=0.0,
        ),
        "deepseek-coder:33b": ModelInfo(
            name="deepseek-coder:33b",
            provider="ollama",
            context_window=16_384,
            max_output_tokens=4_096,
            supports_function_calling=False,
            cost_per_1k_input=0.0,
            cost_per_1k_output=0.0,
        ),
        "qwen2.5-coder:32b": ModelInfo(
            name="qwen2.5-coder:32b",
            provider="ollama",
            context_window=32_768,
            max_output_tokens=8_192,
            supports_function_calling=True,
            cost_per_1k_input=0.0,
            cost_per_1k_output=0.0,
        ),
        "phi-4:14b": ModelInfo(
            name="phi-4:14b",
            provider="ollama",
            context_window=32_768,
            max_output_tokens=8_192,
            supports_function_calling=True,
            cost_per_1k_input=0.0,
            cost_per_1k_output=0.0,
        ),
    }

    def __init__(self, model: str | None = None, **kwargs: Any) -> None:
        super().__init__(model=model, **kwargs)
        self.base_url = (
            settings.OLLAMA_BASE_URL
            or os.getenv("OLLAMA_BASE_URL")
            or "http://localhost:11434"
        ).rstrip("/")

    def _default_model(self) -> str:
        return "llama3.1:8b"

    def get_model_info(self) -> ModelInfo:
        base = self.MODEL_INFO.get(self.model_name)
        if base is not None:
            return base
        return ModelInfo(
            name=self.model_name,
            provider="ollama",
            context_window=32_768,
            max_output_tokens=8_192,
            supports_function_calling=False,
            cost_per_1k_input=0.0,
            cost_per_1k_output=0.0,
        )

    def validate_api_key(self) -> bool:
        return True

    # ── Token counting ───────────────────────────────────────────────

    def count_tokens(self, messages: list[dict[str, Any]]) -> int:
        try:
            resp = requests.post(
                f"{self.base_url}/api/tokenize",
                json={"model": self.model_name, "messages": messages},
                timeout=10,
            )
            if resp.ok:
                data = resp.json()
                return len(data.get("tokens", []))
        except Exception:
            pass
        return super().count_tokens(messages)

    # ── Auto-detect models ───────────────────────────────────────────

    def list_available_models(self) -> list[str]:
        """Query the Ollama server for locally available models."""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=10)
            if resp.ok:
                data = resp.json()
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            pass
        return list(self.MODEL_INFO.keys())

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

        payload = self._build_payload(messages, tools, stream=stream, **kwargs)

        try:
            if stream:
                return self._handle_streaming_response(payload)

            resp = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=kwargs.pop("timeout", 120),
            )
            resp.raise_for_status()
            return self._build_response(resp.json())

        except requests.exceptions.ConnectionError as exc:
            raise ApiError(
                f"Cannot connect to Ollama at {self.base_url}. "
                f"Is the server running?"
            ) from exc
        except requests.exceptions.Timeout as exc:
            raise ApiError(f"Ollama request timed out: {exc}") from exc
        except requests.exceptions.HTTPError as exc:
            self._classify_http_error(exc, resp)  # noqa: F821

    # ── Streaming ────────────────────────────────────────────────────

    def stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> Generator[str, None, LLMResponse]:
        self._check_context_window(messages)

        payload = self._build_payload(messages, tools, stream=True, **kwargs)

        try:
            resp = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                stream=True,
                timeout=kwargs.pop("timeout", 120),
            )
            resp.raise_for_status()
        except requests.exceptions.ConnectionError as exc:
            raise ApiError(
                f"Cannot connect to Ollama at {self.base_url}."
            ) from exc
        except requests.exceptions.Timeout as exc:
            raise ApiError(f"Ollama request timed out: {exc}") from exc

        full_content: list[str] = []
        finish_reason = "stop"
        usage: dict[str, int] = {}

        for line in resp.iter_lines():
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue

            if chunk.get("done"):
                usage = {
                    "prompt_tokens": chunk.get("prompt_eval_count", 0) or 0,
                    "completion_tokens": chunk.get("eval_count", 0) or 0,
                    "total_tokens": (chunk.get("prompt_eval_count", 0) or 0)
                                    + (chunk.get("eval_count", 0) or 0),
                }
                if chunk.get("done_reason"):
                    finish_reason = chunk["done_reason"]
                continue

            delta = chunk.get("message", {})
            text = delta.get("content", "")
            if text:
                full_content.append(text)
                yield text

        content = "".join(full_content)
        input_t = usage.get("prompt_tokens", 0)
        output_t = usage.get("completion_tokens", 0)

        return LLMResponse(
            content=content or None,
            tool_calls=[],
            finish_reason=finish_reason,
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

    def _build_payload(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = dict(
            model=self.model_name,
            messages=messages,
            stream=stream,
            options={
                "temperature": kwargs.pop("temperature", settings.TEMPERATURE),
                "num_predict": kwargs.pop("max_tokens", settings.MAX_TOKENS),
            },
        )
        if tools:
            payload["tools"] = self._convert_tools(tools)
        payload.update({k: v for k, v in kwargs.items() if k not in payload})
        return payload

    def _convert_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """OpenAI-format tools → Ollama tool format."""
        result = []
        for tool in tools:
            func = tool.get("function", tool)
            result.append({
                "type": "function",
                "function": {
                    "name": func.get("name", ""),
                    "description": func.get("description", ""),
                    "parameters": func.get("parameters", {"type": "object", "properties": {}}),
                },
            })
        return result

    def _handle_streaming_response(self, payload: dict[str, Any]) -> LLMResponse:
        payload["stream"] = True
        resp = requests.post(
            f"{self.base_url}/api/chat",
            json=payload,
            stream=True,
            timeout=120,
        )
        resp.raise_for_status()

        full_content: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        finish_reason = "stop"
        usage: dict[str, int] = {}

        for line in resp.iter_lines():
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue

            if chunk.get("done"):
                usage = {
                    "prompt_tokens": chunk.get("prompt_eval_count", 0) or 0,
                    "completion_tokens": chunk.get("eval_count", 0) or 0,
                    "total_tokens": (chunk.get("prompt_eval_count", 0) or 0)
                                    + (chunk.get("eval_count", 0) or 0),
                }
                if chunk.get("done_reason"):
                    finish_reason = chunk["done_reason"]
                continue

            msg = chunk.get("message", {})
            text = msg.get("content", "")
            if text:
                full_content.append(text)

            tc = msg.get("tool_calls")
            if tc:
                for call in tc:
                    func = call.get("function", {})
                    tool_calls.append({
                        "id": f"call_{len(tool_calls)}",
                        "type": "function",
                        "function": {
                            "name": func.get("name", ""),
                            "arguments": json.dumps(func.get("arguments", {})),
                        },
                    })

        content = "".join(full_content)
        input_t = usage.get("prompt_tokens", 0)
        output_t = usage.get("completion_tokens", 0)

        return LLMResponse(
            content=content or None,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
            model=self.model_name,
            provider=self.PROVIDER_NAME,
            cost=self._calculate_cost(input_t, output_t),
        )

    def _build_response(self, data: dict[str, Any]) -> LLMResponse:
        content = ""
        tool_calls: list[dict[str, Any]] = []
        finish_reason = "stop"

        msg = data.get("message", {})
        content = msg.get("content", "") or ""

        tc = msg.get("tool_calls")
        if tc:
            for call in tc:
                func = call.get("function", {})
                tool_calls.append({
                    "id": f"call_{len(tool_calls)}",
                    "type": "function",
                    "function": {
                        "name": func.get("name", ""),
                        "arguments": json.dumps(func.get("arguments", {})),
                    },
                })

        if data.get("done_reason"):
            finish_reason = data["done_reason"]

        usage = {
            "prompt_tokens": data.get("prompt_eval_count", 0) or 0,
            "completion_tokens": data.get("eval_count", 0) or 0,
            "total_tokens": (data.get("prompt_eval_count", 0) or 0)
                            + (data.get("eval_count", 0) or 0),
        }
        input_t = usage["prompt_tokens"]
        output_t = usage["completion_tokens"]

        return LLMResponse(
            content=content or None,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
            model=self.model_name,
            provider=self.PROVIDER_NAME,
            cost=self._calculate_cost(input_t, output_t),
            raw=data,
        )

    def _classify_http_error(self, exc: Exception, resp: Any) -> None:
        status = resp.status_code if hasattr(resp, "status_code") else 0
        msg = str(exc).lower()

        if status == 401 or status == 403:
            raise AuthError(f"Ollama auth error: {exc}") from exc
        if status == 429:
            raise RateLimitError(f"Ollama rate limit: {exc}") from exc
        if "context" in msg or "max_tokens" in msg or "too long" in msg:
            raise ContextWindowError(f"Ollama context window: {exc}") from exc
        raise ModelError(f"Ollama error (HTTP {status}): {exc}") from exc


__all__ = ["OllamaModel"]
