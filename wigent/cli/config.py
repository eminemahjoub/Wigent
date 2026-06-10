# ════════════════════════════════════════
# wigent — CLI Config Manager
# Role: Runtime configuration manager for the CLI
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Runtime configuration that merges file‑based settings, environment
variables, CLI flags, and interactive user overrides.

Usage:
    from wigent.cli.config import config_manager

    config_manager.set_mode("coder")
    token_budget = config_manager.max_context_tokens
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from wigent.config import settings
from wigent.config.modes import MODES, AgentModeConfig, get_mode
from wigent.config.models_config import PROVIDER_CONFIGS, get_provider_config

logger = logging.getLogger(__name__)


class ConfigManager:
    """Runtime configuration that overlays CLI flags and interactive choices
    on top of the static ``Settings`` singleton.

    The manager is stateful — it tracks the currently active mode and
    any runtime overrides (e.g. ``--model``, ``--temperature``).
    """

    def __init__(self) -> None:
        self._mode_override: str | None = None
        self._model_override: str | None = None
        self._temperature_override: float | None = None
        self._max_iterations_override: int | None = None
        self._provider_override: str | None = None

    # ── active mode ──────────────────────────────────────────────────────

    @property
    def active_mode(self) -> AgentModeConfig:
        """Return the current mode config.

        Precedence: runtime override > settings.DEFAULT_MODE.
        """
        mode_name = self._mode_override or settings.DEFAULT_MODE
        return get_mode(mode_name)

    def set_mode(self, name: str) -> None:
        """Switch the active mode at runtime."""
        if name not in MODES:
            raise ValueError(
                f"Unknown mode '{name}'. "
                f"Available: {', '.join(MODES)}"
            )
        self._mode_override = name
        logger.info("Switched to mode: %s (%s)", name, MODES[name].emoji)

    # ── active provider ──────────────────────────────────────────────────

    @property
    def active_provider(self) -> str:
        return self._provider_override or settings.DEFAULT_PROVIDER

    def set_provider(self, name: str) -> None:
        if name not in PROVIDER_CONFIGS:
            raise ValueError(
                f"Unknown provider '{name}'. "
                f"Available: {', '.join(PROVIDER_CONFIGS)}"
            )
        self._provider_override = name
        logger.info("Switched to provider: %s", name)

    # ── model ────────────────────────────────────────────────────────────

    @property
    def model_name(self) -> str:
        """Return the resolved model name.

        Precedence: runtime override > settings.LLM_MODEL > provider default.
        """
        if self._model_override:
            return self._model_override
        if settings.LLM_MODEL:
            return settings.LLM_MODEL
        config = get_provider_config(self.active_provider)
        return config.default_model

    def set_model(self, name: str) -> None:
        self._model_override = name

    # ── temperature ──────────────────────────────────────────────────────

    @property
    def temperature(self) -> float:
        if self._temperature_override is not None:
            return self._temperature_override
        mode_temp = self.active_mode.temperature
        if mode_temp is not None:
            return mode_temp
        return settings.TEMPERATURE

    def set_temperature(self, value: float) -> None:
        self._temperature_override = value

    # ── max iterations ───────────────────────────────────────────────────

    @property
    def max_iterations(self) -> int:
        if self._max_iterations_override is not None:
            return self._max_iterations_override
        mode_max = self.active_mode.max_iterations
        if mode_max is not None:
            return mode_max
        return settings.MAX_ITERATIONS

    def set_max_iterations(self, value: int) -> None:
        self._max_iterations_override = value

    # ── delegated settings (pass-through to global settings) ─────────────

    @property
    def max_tokens(self) -> int:
        return settings.MAX_TOKENS

    @property
    def max_context_tokens(self) -> int:
        return settings.MAX_CONTEXT_TOKENS

    @property
    def auto_approve(self) -> bool:
        return settings.AUTO_APPROVE

    @property
    def show_diffs(self) -> bool:
        return settings.SHOW_DIFFS

    @property
    def sandbox_mode(self) -> bool:
        return settings.SANDBOX_MODE

    @property
    def enable_vector_memory(self) -> bool:
        return settings.ENABLE_VECTOR_MEMORY

    @property
    def workspace_dir(self) -> str:
        return settings.workspace_path

    @property
    def session_dir(self) -> str:
        return settings.SESSION_DIR

    @property
    def log_level(self) -> str:
        return settings.LOG_LEVEL

    @property
    def active_api_key(self) -> str | None:
        """Return the API key for the active provider, or None for local providers."""
        key = settings.active_api_key
        return key if key else None

    # ── summary ──────────────────────────────────────────────────────────

    def summary(self) -> dict[str, Any]:
        """Return a snapshot of the current configuration for display."""
        mode = self.active_mode
        provider_cfg = get_provider_config(self.active_provider)
        return {
            "mode": mode.name,
            "mode_emoji": mode.emoji,
            "provider": provider_cfg.name,
            "provider_emoji": provider_cfg.emoji,
            "model": self.model_name,
            "temperature": self.temperature,
            "max_iterations": self.max_iterations,
            "max_tokens": self.max_tokens,
            "max_context_tokens": self.max_context_tokens,
            "auto_approve": self.auto_approve,
            "show_diffs": self.show_diffs,
            "sandbox_mode": self.sandbox_mode,
            "vector_memory": self.enable_vector_memory,
            "workspace": self.workspace_dir,
            "log_level": self.log_level,
            "has_api_key": self.active_api_key is not None,
        }


# Module-level singleton for global access.
config_manager = ConfigManager()

__all__ = ["ConfigManager", "config_manager"]
