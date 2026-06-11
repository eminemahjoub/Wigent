# ════════════════════════════════════════
# wigent — Settings
# Role: Central configuration object loaded from env / .env / defaults
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Application settings loaded with pydantic-settings and python-dotenv.

Usage:
    from wigent.config import settings

    provider = settings.DEFAULT_PROVIDER
    model    = settings.get_model_name()
    mode     = settings.DEFAULT_MODE
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import ClassVar, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ── supported provider names ────────────────────────────────────────────
ProviderName = Literal[
    "openai", "anthropic", "gemini", "groq", "ollama", "openrouter",
    "mistral", "cohere", "litellm"
]

# ── supported agent modes ───────────────────────────────────────────────
AgentMode = Literal["orchestrator", "architect", "coder", "debugger", "reviewer"]

# ── log levels ──────────────────────────────────────────────────────────
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Settings(BaseSettings):
    """Central configuration for Wigent.

    All values are read from environment variables or a ``.env`` file,
    with sensible defaults for every field.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── LLM provider selection ───────────────────────────────────────────
    DEFAULT_PROVIDER: ProviderName = Field(
        default="openai",
        description="Default LLM provider. One of: openai, anthropic, gemini, groq, ollama, mistral, cohere, litellm",
    )

    DEFAULT_MODE: AgentMode = Field(
        default="orchestrator",
        description="Default agent mode. One of: orchestrator, architect, coder, debugger, reviewer",
    )

    LLM_MODEL: str = Field(
        default="",
        description="LLM model name override. If empty, the provider's default model is used.",
    )

    # ── API keys ─────────────────────────────────────────────────────────
    OPENAI_API_KEY: str = Field(default="", description="OpenAI API key")
    ANTHROPIC_API_KEY: str = Field(default="", description="Anthropic API key")
    GEMINI_API_KEY: str = Field(default="", description="Google Gemini API key")
    GROQ_API_KEY: str = Field(default="", description="Groq API key")
    MISTRAL_API_KEY: str = Field(default="", description="Mistral API key")
    OPENROUTER_API_KEY: str = Field(default="", description="OpenRouter API key (300+ models)")
    COHERE_API_KEY: str = Field(default="", description="Cohere API key")

    # ── Local provider config ────────────────────────────────────────────
    OLLAMA_BASE_URL: str = Field(
        default="http://localhost:11434",
        description="Ollama server base URL",
    )
    LITELLM_BASE_URL: str = Field(
        default="http://localhost:4000",
        description="LiteLLM proxy base URL",
    )

    # ── Generation parameters ────────────────────────────────────────────
    MAX_TOKENS: int = Field(
        default=4096,
        ge=1,
        le=131072,
        description="Maximum tokens per LLM response",
    )

    TEMPERATURE: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="LLM temperature (0.0 = deterministic, 2.0 = very creative)",
    )

    MAX_ITERATIONS: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Maximum think-act-observe iterations before forcing a stop",
    )

    # ── Token / context budget ───────────────────────────────────────────
    MAX_CONTEXT_TOKENS: int = Field(
        default=128_000,
        ge=1024,
        le=2_000_000,
        description="Soft limit for total context window (messages are trimmed when exceeded)",
    )

    # ── Behaviour flags ──────────────────────────────────────────────────
    AUTO_APPROVE: bool = Field(
        default=False,
        description="If True, skip human-in-the-loop approval for all actions",
    )

    SHOW_DIFFS: bool = Field(
        default=True,
        description="Show diffs before applying file changes",
    )

    SANDBOX_MODE: bool = Field(
        default=True,
        description="Restrict file operations to WORKSPACE_DIR",
    )

    ENABLE_VECTOR_MEMORY: bool = Field(
        default=False,
        description="Enable persistent vector memory (semantic search across sessions)",
    )

    # ── Paths ────────────────────────────────────────────────────────────
    WORKSPACE_DIR: str = Field(
        default_factory=lambda: os.path.join(os.getcwd(), "agent_workspace"),
        description="Sandbox directory for all file operations",
    )

    SESSION_DIR: str = Field(
        default_factory=lambda: os.path.join(os.getcwd(), ".agent", "sessions"),
        description="Directory for session logs and checkpoints",
    )

    # ── Logging ──────────────────────────────────────────────────────────
    LOG_LEVEL: LogLevel = Field(
        default="INFO",
        description="Root log level",
    )

    # ── Internal (not from env) ──────────────────────────────────────────
    _workspace_abs: str | None = None

    # ── Field validators ─────────────────────────────────────────────────

    @field_validator("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY", "MISTRAL_API_KEY", "OPENROUTER_API_KEY", "COHERE_API_KEY")
    @classmethod
    def warn_empty_api_key(cls, v: str, info) -> str:
        """Warn if an API key field is empty but the matching provider is selected."""
        provider_map = {
            "OPENAI_API_KEY": "openai",
            "ANTHROPIC_API_KEY": "anthropic",
            "GEMINI_API_KEY": "gemini",
            "GROQ_API_KEY": "groq",
            "MISTRAL_API_KEY": "mistral",
            "OPENROUTER_API_KEY": "openrouter",
            "COHERE_API_KEY": "cohere",
        }
        # Warning only logged at runtime, not during pydantic init.
        return v

    @field_validator("WORKSPACE_DIR")
    @classmethod
    def resolve_workspace(cls, v: str) -> str:
        if not v:
            v = os.path.join(os.getcwd(), "agent_workspace")
        return os.path.abspath(v)

    @field_validator("SESSION_DIR")
    @classmethod
    def resolve_session_dir(cls, v: str) -> str:
        if not v:
            v = os.path.join(os.getcwd(), ".agent", "sessions")
        return os.path.abspath(v)

    # ── Property helpers ─────────────────────────────────────────────────

    @property
    def model_name(self) -> str:
        """Return the resolved model name.

        If ``LLM_MODEL`` is set explicitly, return it.
        Otherwise return the default model for ``DEFAULT_PROVIDER``.
        """
        if self.LLM_MODEL:
            return self.LLM_MODEL
        from wigent.config.models_config import PROVIDER_CONFIGS
        config = PROVIDER_CONFIGS.get(self.DEFAULT_PROVIDER)
        return config.default_model if config else "gpt-4o"

    @property
    def active_api_key(self) -> str:
        """Return the API key for the currently selected provider."""
        key_map = {
            "openai": self.OPENAI_API_KEY,
            "anthropic": self.ANTHROPIC_API_KEY,
            "gemini": self.GEMINI_API_KEY,
            "groq": self.GROQ_API_KEY,
            "mistral": self.MISTRAL_API_KEY,
            "cohere": self.COHERE_API_KEY,
            "ollama": "",
            "openrouter": self.OPENROUTER_API_KEY,
            "litellm": "",
        }
        return key_map.get(self.DEFAULT_PROVIDER, "")

    @property
    def workspace_path(self) -> str:
        """Return the absolute workspace directory path (creates it if needed)."""
        if self._workspace_abs is None:
            self._workspace_abs = os.path.abspath(self.WORKSPACE_DIR)
            os.makedirs(self._workspace_abs, exist_ok=True)
        return self._workspace_abs

    @property
    def supported_providers(self) -> list[str]:
        """Return list of all supported provider names."""
        return ["openai", "anthropic", "gemini", "groq", "ollama",
                "openrouter", "mistral", "cohere", "litellm"]

    def provider_base_url(self, provider: str | None = None) -> str | None:
        """Return the base URL for a local provider, or None for cloud providers."""
        urls = {
            "ollama": self.OLLAMA_BASE_URL,
            "litellm": self.LITELLM_BASE_URL,
        }
        return urls.get(provider or self.DEFAULT_PROVIDER)


settings = Settings()

__all__ = ["settings", "Settings", "ProviderName", "AgentMode", "LogLevel"]
