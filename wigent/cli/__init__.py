# ════════════════════════════════════════
# wigent — CLI Package
# Role: Terminal interface for the agent
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Command-line interface — entry point for interactive and non-interactive modes."""

from wigent.cli.app import main
from wigent.cli.config import ConfigManager, config_manager

__all__ = ["main", "ConfigManager", "config_manager"]
