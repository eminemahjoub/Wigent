# ════════════════════════════════════════
# wigent — Config Package
# Role: Settings and configuration management
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Configuration loading — environment variables, .env files, defaults,
agent modes, and provider model definitions."""

from wigent.config.settings import settings, Settings, ProviderName, AgentMode, LogLevel
from wigent.config.modes import (
    AgentModeConfig,
    MODES,
    ORCHESTRATOR,
    ARCHITECT,
    CODER,
    DEBUGGER,
    REVIEWER,
    get_mode,
    list_modes,
)
from wigent.config.models_config import (
    ProviderConfig,
    ModelCost,
    PROVIDER_CONFIGS,
    OPENAI,
    ANTHROPIC,
    GEMINI,
    GROQ,
    OLLAMA,
    MISTRAL,
    COHERE,
    LITELLM,
    get_provider_config,
    list_providers,
)

__all__ = [
    "settings",
    "Settings",
    "ProviderName",
    "AgentMode",
    "LogLevel",
    "AgentModeConfig",
    "MODES",
    "ORCHESTRATOR",
    "ARCHITECT",
    "CODER",
    "DEBUGGER",
    "REVIEWER",
    "get_mode",
    "list_modes",
    "ProviderConfig",
    "ModelCost",
    "PROVIDER_CONFIGS",
    "OPENAI",
    "ANTHROPIC",
    "GEMINI",
    "GROQ",
    "OLLAMA",
    "MISTRAL",
    "COHERE",
    "LITELLM",
    "get_provider_config",
    "list_providers",
]
