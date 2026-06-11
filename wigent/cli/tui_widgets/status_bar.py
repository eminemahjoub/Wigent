# ════════════════════════════════════════
# wigent — Status Bar Widget
# Role: Status bar showing mode, model, tokens, cost
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Status bar widget for the Wigent TUI."""

from __future__ import annotations

from typing import Any

from textual.widgets import Static
from rich.text import Text


class StatusBar(Static):
    """Unified status + key-hint dock bar. Replaces Footer."""

    DEFAULT_CSS = """
    StatusBar {
        height: 2;
        background: $surface-darken-2;
        color: $text;
        padding: 0 1;
        border-top: solid $primary-darken-2;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__("", **kwargs)
        self.mode = "orchestrator"
        self.model = ""
        self.tokens = 0
        self.cost = 0.0

    def render(self) -> Text:
        """Render two-line status bar."""
        # Line 1: Info
        info = Text()
        info.append("● ", style="bold cyan")
        info.append(f"{self.mode.upper()}  ", style="bold cyan")
        info.append(f"🧠 {self.model or '—'}  ", style="green")
        info.append(f"📊 {self.tokens:,} tok  ", style="yellow")
        info.append(f"💰 ${self.cost:.4f}", style="magenta")

        # Line 2: Key bindings
        keys = Text()
        binds = [
            ("^Q", "Quit"),
            ("^L", "Clear"),
            ("^M", "Mode"),
            ("F1", "Help"),
            ("F2", "Model"),
            ("F3", "Files"),
            ("Esc", "Input"),
        ]
        for shortcut, label in binds:
            keys.append(f" {shortcut} ", style="bold white on rgb(40,40,40)")
            keys.append(f" {label}  ", style="dim")
        keys.append("palette", style="italic dim")

        # Combine
        text = Text()
        text.append_text(info)
        text.append("\n")
        text.append_text(keys)
        return text

    def update_info(
        self,
        mode: str | None = None,
        model: str | None = None,
        tokens: int | None = None,
        cost: float | None = None,
    ) -> None:
        """Update status info and refresh."""
        if mode is not None:
            self.mode = mode
        if model is not None:
            self.model = model
        if tokens is not None:
            self.tokens = tokens
        if cost is not None:
            self.cost = cost
        self.refresh()
