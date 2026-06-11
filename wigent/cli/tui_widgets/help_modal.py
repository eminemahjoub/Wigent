# ════════════════════════════════════════
# wigent — Help Modal
# Role: Help screen showing commands and shortcuts
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Help modal screen for the Wigent TUI."""

from __future__ import annotations

from textual.screen import ModalScreen
from textual.widgets import Static
from textual.containers import Vertical, VerticalScroll


class HelpModal(ModalScreen[None]):
    """Help screen showing all keyboard shortcuts and commands."""

    DEFAULT_CSS = """
    HelpModal {
        align: center middle;
    }
    #help-container {
        width: 80;
        height: auto;
        max-height: 90%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    #help-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        height: 1;
        margin-bottom: 1;
    }
    #help-content {
        color: $text;
    }
    """

    HELP_TEXT = """
[bold cyan]🤖 Wigent — Keyboard Shortcuts[/]

[bold]Navigation[/]
  [yellow]F1[/]          Show this help
  [yellow]F2[/]          Settings  
  [yellow]F3[/]          Toggle file tree sidebar
  [yellow]Esc[/]         Focus input / dismiss dialog

[bold]Actions[/]
  [yellow]Ctrl+L[/]      Clear chat history
  [yellow]Ctrl+M[/]      Switch agent mode
  [yellow]Ctrl+S[/]      Save session
  [yellow]Ctrl+C[/]      Quit wigent

[bold]Slash Commands[/]
  [green]/mode[/]       Switch agent mode
  [green]/model[/]      Change LLM model
  [green]/clear[/]      Clear conversation
  [green]/save[/]       Save session
  [green]/load[/]       Load session
  [green]/help[/]       Show this help
  [green]/exit[/]       Quit wigent

[bold]Agent Modes[/]
  🎯 [cyan]Orchestrator[/]   Default, routes tasks
  📐 [cyan]Architect[/]      Planning only
  💻 [cyan]Coder[/]          Implementation
  🔧 [cyan]Debugger[/]       Bug fixing
  🔍 [cyan]Reviewer[/]       Code review

[dim]Press Esc to close[/]
"""

    def compose(self) -> None:
        with Vertical(id="help-container"):
            yield Static("🆘 Wigent Help", id="help-title")
            with VerticalScroll():
                yield Static(self.HELP_TEXT, id="help-content")

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss()
