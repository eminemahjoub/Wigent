# ════════════════════════════════════════
# wigent — CLI Package
# Role: Terminal interface for the agent
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Command-line interface — entry point for interactive and non-interactive modes."""


def main(argv: list[str] | None = None) -> None:
    """Lazily import and run the CLI to avoid triggering model chain at import time."""
    from wigent.cli.app import main as _main
    _main(argv)


from wigent.cli.config import ConfigManager, config_manager  # noqa: E402

__all__ = ["main", "ConfigManager", "config_manager"]
