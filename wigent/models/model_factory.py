# ════════════════════════════════════════
# wigent — Model Factory
# Role: Central factory and registry for all LLM providers
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Factory pattern for creating and managing LLM provider instances.

Usage
-----
>>> from wigent.models.model_factory import ModelFactory
>>>
>>> factory = ModelFactory()
>>> llm = factory.get_model("openai", "gpt-4o")
>>> response = llm.chat([{"role": "user", "content": "Hello!"}])
>>>
>>> # Hot-swap providers
>>> factory.switch_model("anthropic", "claude-sonnet-4-20250514")
>>> llm = factory.get_active_model()
>>>
>>> # Find the best model for a specific task
>>> model = factory.get_best_model_for_task("code_generation")
"""

from __future__ import annotations

import logging
import os
from typing import Any

from wigent.config import settings
from wigent.config.models_config import PROVIDER_CONFIGS, get_provider_config, list_providers
from wigent.models.base_model import BaseModel, LLMResponse, ModelInfo
from wigent.models.anthropic_model import AnthropicModel
from wigent.models.gemini_model import GeminiModel
from wigent.models.groq_model import GroqModel
from wigent.models.litellm_proxy import LiteLLMProxy
from wigent.models.openrouter_model import OpenRouterModel
from wigent.models.ollama_model import OllamaModel
from wigent.models.openai_model import OpenAIModel

logger = logging.getLogger(__name__)

# ── Registry mapping provider names to implementation classes ────────────

PROVIDER_CLASSES: dict[str, type[BaseModel]] = {
    "openai": OpenAIModel,
    "anthropic": AnthropicModel,
    "gemini": GeminiModel,
    "groq": GroqModel,
    "ollama": OllamaModel,
    "openrouter": OpenRouterModel,
    "litellm": LiteLLMProxy,
}


class ModelFactory:
    """Singleton factory for creating and managing LLM provider instances.

    Attributes
    ----------
    active_provider : str
        Name of the currently active provider.
    active_model : BaseModel
        The currently active model instance.
    """

    _instance: ModelFactory | None = None

    def __new__(cls, *args: Any, **kwargs: Any) -> ModelFactory:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

        self.active_provider: str = settings.DEFAULT_PROVIDER
        self.active_model_name: str = settings.model_name
        self._instances: dict[str, BaseModel] = {}
        self._active_instance: BaseModel | None = None

    # ── Public API ───────────────────────────────────────────────────

    def get_model(
        self,
        provider: str | None = None,
        model_name: str | None = None,
        **kwargs: Any,
    ) -> BaseModel:
        """Get (or create) a model instance for a given provider.

        Args:
            provider:  Provider name (e.g. ``"openai"``, ``"anthropic"``).
                       Defaults to ``DEFAULT_PROVIDER`` from settings.
            model_name: Specific model (e.g. ``"gpt-4o"``).  Defaults to
                        the provider's default model.
            **kwargs:  Extra arguments forwarded to the model constructor.

        Returns:
            A ready-to-use ``BaseModel`` instance.
        """
        provider = provider or self.active_provider
        model_name = model_name or self._get_default_model(provider)
        cache_key = f"{provider}:{model_name}"

        if cache_key in self._instances:
            return self._instances[cache_key]

        provider_cls = PROVIDER_CLASSES.get(provider)
        if provider_cls is None:
            raise ValueError(
                f"Unknown provider '{provider}'. "
                f"Available: {', '.join(PROVIDER_CLASSES)}"
            )

        instance = provider_cls(model=model_name, **kwargs)
        self._instances[cache_key] = instance
        return instance

    def list_available_models(self) -> list[dict[str, Any]]:
        """Return metadata for all known providers and their models.

        Returns:
            A list of dicts — each containing the provider summary from
            ``config.models_config.list_providers()``, extended with the
            implementation class name.
        """
        result = []
        for prov in list_providers():
            cls = PROVIDER_CLASSES.get(prov["name"])
            result.append({
                **prov,
                "class": cls.__name__ if cls else None,
            })
        return result

    def get_default_model(self, provider: str | None = None) -> BaseModel:
        """Return a model instance using the provider's default model.

        Args:
            provider: Provider name.  Defaults to ``DEFAULT_PROVIDER``.

        Returns:
            A ``BaseModel`` instance initialised with the default model.
        """
        provider = provider or self.active_provider
        default = self._get_default_model(provider)
        return self.get_model(provider=provider, model_name=default)

    def switch_model(
        self,
        provider: str,
        model_name: str | None = None,
    ) -> BaseModel:
        """Hot-swap the active provider / model at runtime.

        This updates ``active_provider`` and ``active_model_name`` so that
        subsequent calls to ``get_active_model()`` use the new settings.

        Args:
            provider:   New provider name.
            model_name: Optional model override.  Uses the provider's
                        default if omitted.

        Returns:
            The newly active ``BaseModel`` instance.
        """
        self.active_provider = provider
        self.active_model_name = model_name or self._get_default_model(provider)
        self._active_instance = None  # force re-resolve on next get_active_model
        return self.get_active_model()

    def get_active_model(self) -> BaseModel:
        """Return the currently active model instance.

        Respects ``settings.DEFAULT_PROVIDER``, ``settings.LLM_MODEL``,
        and any runtime overrides via ``switch_model()``.
        """
        if self._active_instance is not None:
            return self._active_instance

        provider = self.active_provider
        model_name = self.active_model_name or settings.model_name
        self._active_instance = self.get_model(
            provider=provider,
            model_name=model_name,
        )
        return self._active_instance

    def test_connection(self, provider: str | None = None) -> dict[str, Any]:
        """Ping a provider by listing its models or validating its API key.

        Args:
            provider: Provider name.  Defaults to active provider.

        Returns:
            A dict with ``success``, ``provider``, and optionally
            ``models`` (for Ollama) or ``error``.
        """
        provider = provider or self.active_provider
        try:
            instance = self.get_model(provider=provider)
            if provider == "ollama":
                models = instance.list_available_models()  # type: ignore[union-attr]
                return {
                    "success": True,
                    "provider": provider,
                    "models": models,
                }
            key_valid = instance.validate_api_key()
            return {
                "success": key_valid,
                "provider": provider,
                "api_key_valid": key_valid,
            }
        except Exception as exc:
            return {
                "success": False,
                "provider": provider,
                "error": str(exc),
            }

    def get_best_model_for_task(self, task_type: str) -> str:
        """Recommend the best model identifier for a given task type.

        Task types
        ----------
        - ``"code_generation"`` → models with strong code training
        - ``"reasoning"``       → high-reasoning models (o1, o3, Sonnet 4)
        - ``"fast"``            → low-latency models (gpt-4o-mini, Haiku)
        - ``"vision"``          → models with vision support
        - ``"long_context"``    → largest context window (Gemini 2.5 Pro)
        - ``"cheap"``           → lowest-cost models
        - ``"local"``           → local models (Ollama)

        Returns:
            A string like ``"openai/gpt-4o"`` (``"provider/model"``).
        """
        recommendations: dict[str, list[str]] = {
            "code_generation": [
                "openai/gpt-4o",
                "anthropic/claude-sonnet-4-20250514",
                "groq/llama-3.3-70b-versatile",
                "ollama/qwen2.5-coder:32b",
            ],
            "reasoning": [
                "openai/o3",
                "openai/o1",
                "anthropic/claude-sonnet-4-20250514",
                "gemini/gemini-2.5-pro-exp-03-25",
            ],
            "fast": [
                "openai/gpt-4o-mini",
                "anthropic/claude-3.5-haiku-20241022",
                "groq/llama-3.1-8b-instant",
            ],
            "vision": [
                "openai/gpt-4o",
                "anthropic/claude-sonnet-4-20250514",
                "gemini/gemini-2.5-pro-exp-03-25",
            ],
            "long_context": [
                "gemini/gemini-2.5-pro-exp-03-25",
                "openai/gpt-4.1",
                "anthropic/claude-sonnet-4-20250514",
            ],
            "cheap": [
                "openai/gpt-4o-mini",
                "groq/llama-3.1-8b-instant",
                "ollama/llama3.1:8b",
            ],
            "local": [
                "ollama/qwen2.5-coder:32b",
                "ollama/llama3.1:8b",
                "ollama/deepseek-coder:33b",
            ],
        }

        candidates = recommendations.get(task_type)
        if not candidates:
            candidates = ["openai/gpt-4o"]

        # Return the first candidate whose provider is configured.
        for candidate in candidates:
            provider, _, model = candidate.partition("/")
            cls = PROVIDER_CLASSES.get(provider)
            if cls is None:
                continue
            return candidate

        return "openai/gpt-4o"

    # ── Convenience ──────────────────────────────────────────────────

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> LLMResponse:
        """Send a chat message using the active model.

        Shorthand for ``factory.get_active_model().chat(...)``.
        """
        return self.get_active_model().chat(
            messages=messages, tools=tools, stream=stream, **kwargs
        )

    def stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Stream a chat response using the active model."""
        return self.get_active_model().stream_chat(
            messages=messages, tools=tools, **kwargs
        )

    # ── Internals ────────────────────────────────────────────────────

    @staticmethod
    def _get_default_model(provider: str) -> str:
        """Resolve the default model name for a provider."""
        try:
            cfg = get_provider_config(provider)
            return cfg.default_model
        except KeyError:
            return "gpt-4o"


# Global singleton for application-wide use.
factory = ModelFactory()


__all__ = ["ModelFactory", "factory", "PROVIDER_CLASSES"]
