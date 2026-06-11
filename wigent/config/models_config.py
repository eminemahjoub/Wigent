# ════════════════════════════════════════
# wigent — LLM Provider Configurations
# Role: Model metadata, costs, and capabilities for every supported provider
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Provider and model definitions.

Each ``ProviderConfig`` stores the available models, defaults, context
windows, streaming/function-calling support, and per‑token costs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final


@dataclass(frozen=True)
class ModelCost:
    """Cost per 1 000 tokens (input / output) in USD."""

    input: float
    output: float


@dataclass(frozen=True)
class ProviderConfig:
    """Metadata for a single LLM provider."""

    name: str
    emoji: str
    models: tuple[str, ...] = field(default_factory=tuple)
    default_model: str = ""
    max_context_window: int = 128_000
    supports_streaming: bool = True
    supports_function_calling: bool = True
    cost_per_1k_tokens: ModelCost = field(default_factory=lambda: ModelCost(0.0, 0.0))
    base_url: str | None = None
    env_key: str = ""
    docs_url: str = ""


# ── OpenAI ───────────────────────────────────────────────────────────────

OPENAI: Final[ProviderConfig] = ProviderConfig(
    name="openai",
    emoji="🟢",
    models=(
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4o-2025-01-01",
        "gpt-4.1",
        "gpt-4.1-mini",
        "gpt-4.1-nano",
        "o1",
        "o1-mini",
        "o3",
        "o3-mini",
    ),
    default_model="gpt-4o",
    max_context_window=128_000,
    supports_streaming=True,
    supports_function_calling=True,
    cost_per_1k_tokens=ModelCost(input=0.0025, output=0.0100),
    env_key="OPENAI_API_KEY",
    docs_url="https://platform.openai.com/docs/api-reference",
)

# ── Anthropic ────────────────────────────────────────────────────────────

ANTHROPIC: Final[ProviderConfig] = ProviderConfig(
    name="anthropic",
    emoji="🟣",
    models=(
        "claude-sonnet-4-20250514",
        "claude-3.5-sonnet-20241022",
        "claude-3.5-haiku-20241022",
        "claude-opus-4-20250514",
    ),
    default_model="claude-sonnet-4-20250514",
    max_context_window=200_000,
    supports_streaming=True,
    supports_function_calling=True,
    cost_per_1k_tokens=ModelCost(input=0.0030, output=0.0150),
    env_key="ANTHROPIC_API_KEY",
    docs_url="https://docs.anthropic.com/en/api",
)

# ── Google Gemini ────────────────────────────────────────────────────────

GEMINI: Final[ProviderConfig] = ProviderConfig(
    name="gemini",
    emoji="🔵",
    models=(
        "gemini-2.5-pro-exp-03-25",
        "gemini-2.5-flash-preview-04-17",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
    ),
    default_model="gemini-2.5-pro-exp-03-25",
    max_context_window=1_000_000,
    supports_streaming=True,
    supports_function_calling=True,
    cost_per_1k_tokens=ModelCost(input=0.00125, output=0.00500),
    env_key="GEMINI_API_KEY",
    docs_url="https://ai.google.dev/gemini-api/docs",
)

# ── Groq ─────────────────────────────────────────────────────────────────

GROQ: Final[ProviderConfig] = ProviderConfig(
    name="groq",
    emoji="🟠",
    models=(
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "mixtral-8x7b-32768",
        "deepseek-r1-distill-llama-70b",
    ),
    default_model="llama-3.3-70b-versatile",
    max_context_window=32_768,
    supports_streaming=True,
    supports_function_calling=True,
    cost_per_1k_tokens=ModelCost(input=0.00059, output=0.00079),
    env_key="GROQ_API_KEY",
    docs_url="https://console.groq.com/docs",
)

# ── OpenRouter ───────────────────────────────────────────────────────

OPENROUTER: Final[ProviderConfig] = ProviderConfig(
    name="openrouter",
    emoji="🌐",
    models=(
        "anthropic/claude-3.5-sonnet",
        "openai/gpt-4o",
        "google/gemini-2.0-flash-exp",
        "qwen/qwen-2.5-coder-32b-instruct",
        "meta-llama/llama-3.2-3b-instruct:free",
    ),
    default_model="anthropic/claude-3.5-sonnet",
    max_context_window=200_000,
    env_key="OPENROUTER_API_KEY",
    docs_url="https://openrouter.ai/docs",
)

# ── Ollama (local) ───────────────────────────────────────────────────────

OLLAMA: Final[ProviderConfig] = ProviderConfig(
    name="ollama",
    emoji="🦙",
    models=(
        "llama3.3:70b",
        "llama3.1:8b",
        "mistral:7b",
        "codellama:34b",
        "deepseek-coder:33b",
        "qwen2.5-coder:32b",
        "phi-4:14b",
    ),
    default_model="llama3.1:8b",
    max_context_window=32_768,
    supports_streaming=True,
    supports_function_calling=False,
    cost_per_1k_tokens=ModelCost(input=0.0, output=0.0),
    base_url="http://localhost:11434",
    docs_url="https://github.com/ollama/ollama?tab=readme-ov-file#api",
)

# ── Mistral ──────────────────────────────────────────────────────────────

MISTRAL: Final[ProviderConfig] = ProviderConfig(
    name="mistral",
    emoji="🤖",
    models=(
        "mistral-large-2501",
        "mistral-small-2503",
        "codestral-2505",
        "ministral-8b-2410",
    ),
    default_model="mistral-large-2501",
    max_context_window=128_000,
    supports_streaming=True,
    supports_function_calling=True,
    cost_per_1k_tokens=ModelCost(input=0.0020, output=0.0060),
    env_key="MISTRAL_API_KEY",
    docs_url="https://docs.mistral.ai",
)

# ── Cohere ───────────────────────────────────────────────────────────────

COHERE: Final[ProviderConfig] = ProviderConfig(
    name="cohere",
    emoji="🔷",
    models=(
        "command-a-03-2025",
        "command-r-plus-08-2024",
        "command-r-08-2024",
    ),
    default_model="command-a-03-2025",
    max_context_window=128_000,
    supports_streaming=True,
    supports_function_calling=True,
    cost_per_1k_tokens=ModelCost(input=0.0025, output=0.0100),
    env_key="COHERE_API_KEY",
    docs_url="https://docs.cohere.com/reference",
)

# ── LiteLLM (proxy) ─────────────────────────────────────────────────────

LITELLM: Final[ProviderConfig] = ProviderConfig(
    name="litellm",
    emoji="⚡",
    models=(
        "gpt-4o",
        "claude-sonnet-4-20250514",
        "gemini-2.5-pro-exp-03-25",
    ),
    default_model="gpt-4o",
    max_context_window=128_000,
    supports_streaming=True,
    supports_function_calling=True,
    cost_per_1k_tokens=ModelCost(input=0.0, output=0.0),
    base_url="http://localhost:4000",
    docs_url="https://docs.litellm.ai/docs",
)


# ── registry ─────────────────────────────────────────────────────────────

PROVIDER_CONFIGS: Final[dict[str, ProviderConfig]] = {
    "openai": OPENAI,
    "anthropic": ANTHROPIC,
    "gemini": GEMINI,
    "groq": GROQ,
    "ollama": OLLAMA,
    "openrouter": OPENROUTER,
    "mistral": MISTRAL,
    "cohere": COHERE,
    "litellm": LITELLM,
}


def get_provider_config(name: str) -> ProviderConfig:
    """Look up a provider config by name. Raises KeyError if unknown."""
    if name not in PROVIDER_CONFIGS:
        raise KeyError(
            f"Unknown provider '{name}'. "
            f"Available: {', '.join(PROVIDER_CONFIGS)}"
        )
    return PROVIDER_CONFIGS[name]


def list_providers() -> list[dict[str, str | list[str] | float | bool]]:
    """Return a list of provider summaries (useful for CLI --help)."""
    return [
        {
            "name": cfg.name,
            "emoji": cfg.emoji,
            "default_model": cfg.default_model,
            "models": list(cfg.models),
            "max_context_window": cfg.max_context_window,
            "supports_function_calling": cfg.supports_function_calling,
            "cost_input_per_1k": cfg.cost_per_1k_tokens.input,
            "cost_output_per_1k": cfg.cost_per_1k_tokens.output,
        }
        for cfg in PROVIDER_CONFIGS.values()
    ]


__all__ = [
    "ProviderConfig",
    "ModelCost",
    "OPENAI",
    "ANTHROPIC",
    "GEMINI",
    "GROQ",
    "OLLAMA",
    "OPENROUTER",
    "MISTRAL",
    "COHERE",
    "LITELLM",
    "PROVIDER_CONFIGS",
    "get_provider_config",
    "list_providers",
]
