# ════════════════════════════════════════
# wigent — Status Bar Widget
# Role: Status bar showing mode, model, tokens, cost
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Status bar widget for the Wigent TUI."""

from __future__ import annotations

from textual.widgets import Static
from rich.text import Text


class StatusBar(Static):
    """Status bar showing mode, model, tokens, and cost."""

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: $primary-darken-2;
        color: $text;
        padding: 0 1;
    }
    """

    def __init__(self) -> None:
        super().__init__("")
        self.mode = "orchestrator"
        self.model = "claude-3.5-sonnet"
        self.tokens = 0
        self.cost = 0.0

    def render(self) -> Text:
        """Render the status bar."""
        text = Text()

        # Mode
        text.append(f"🎯 {self.mode.upper()}", style="bold cyan")
        text.append(" │ ", style="dim")

        # Model
        text.append(f"🧠 {self.model}", style="green")
        text.append(" │ ", style="dim")

        # Tokens
        text.append(f"📊 {self.tokens:,} tokens", style="yellow")
        text.append(" │ ", style="dim")

        # Cost
        text.append(f"💰 ${self.cost:.4f}", style="magenta")

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
