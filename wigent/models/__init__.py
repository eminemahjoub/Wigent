# ════════════════════════════════════════
# wigent — Models Package
# Role: LLM provider abstraction layer
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Abstract interface + concrete providers for LLM backends.

Supported providers:
    - OpenAI    (GPT-4o, GPT-4o-mini, GPT-4.1, o1, o3)
    - Anthropic (Claude Sonnet 4, Claude 3.5 Sonnet/Haiku, Opus 4)
    - Gemini    (Gemini 2.5 Pro, 2.5 Flash, 2.0 Flash)
    - Groq      (Llama 3.3, Mixtral, DeepSeek R1)
    - Ollama    (Llama 3.1, CodeLlama, Qwen 2.5 Coder, local)
    - LiteLLM   (Universal proxy for 100+ models)

Usage
-----
    from wigent.models.model_factory import factory

    # Auto-configured from env
    response = factory.chat([{"role": "user", "content": "Hello"}])

    # Explicit provider
    llm = factory.get_model("anthropic", "claude-sonnet-4-20250514")
    response = llm.chat([{"role": "user", "content": "Hi"}])

    # Hot-swap
    factory.switch_model("gemini", "gemini-2.5-pro-exp-03-25")
    llm = factory.get_active_model()
"""

# Base types ────────────────────────────────────────────────────────────
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
)

# Concrete providers ────────────────────────────────────────────────────
from wigent.models.anthropic_model import AnthropicModel
from wigent.models.gemini_model import GeminiModel
from wigent.models.groq_model import GroqModel
from wigent.models.litellm_proxy import LiteLLMProxy
from wigent.models.ollama_model import OllamaModel
from wigent.models.openai_model import OpenAIModel

# Factory ───────────────────────────────────────────────────────────────
from wigent.models.model_factory import PROVIDER_CLASSES, ModelFactory, factory

__all__ = [
    # Base types
    "BaseModel",
    "ModelInfo",
    "LLMResponse",
    "ErrorType",
    "AuthError",
    "RateLimitError",
    "ContextWindowError",
    "ModelError",
    "ApiError",
    # Concrete providers
    "OpenAIModel",
    "AnthropicModel",
    "GeminiModel",
    "GroqModel",
    "OllamaModel",
    "LiteLLMProxy",
    # Factory
    "ModelFactory",
    "factory",
    "PROVIDER_CLASSES",
]
