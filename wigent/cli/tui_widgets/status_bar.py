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
        background: #161b22;
        color: #8b949e;
        padding: 0 2;
        border-top: solid #21262d;
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
        info.append("● ", style="bold #58a6ff")
        info.append(f"{self.mode.upper()}  ", style="bold #58a6ff")
        info.append(f"🧠 {self.model or '—'}  ", style="#3fb950")
        info.append(f"📊 {self.tokens:,} tok  ", style="#d29922")
        info.append(f"💰 ${self.cost:.4f}", style="#a371f7")

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
            keys.append(f" {shortcut} ", style="bold #f0f6fc on #30363d")
            keys.append(f" {label}  ", style="dim #8b949e")
        keys.append("palette", style="italic #484f58")

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
