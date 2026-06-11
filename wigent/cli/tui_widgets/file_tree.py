# ════════════════════════════════════════
# wigent — File Tree Widget
# Role: Project file tree for TUI sidebar
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""File tree widget for the Wigent TUI sidebar."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from textual.widgets import DirectoryTree


class WigentFileTree(DirectoryTree):
    """File tree showing project structure with sensible filtering."""

    DEFAULT_CSS = """
    WigentFileTree {
        background: transparent;
        border: none;
        padding: 0;
    }
    WigentFileTree > .tree--cursor {
        background: $accent;
        color: $text;
    }
    """

    def __init__(self, path: str = ".") -> None:
        super().__init__(path)
        self.show_root = False
        self.show_guides = True

    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        """Filter out hidden files and common ignored folders."""
        ignored = {
            "__pycache__", ".git", "node_modules",
            "venv", ".venv", ".pytest_cache", ".agent",
            "agent_workspace", ".egg-info", "dist", "build",
        }
        return [
            p for p in paths
            if p.name not in ignored and not p.name.startswith(".")
        ]
