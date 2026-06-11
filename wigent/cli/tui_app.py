# ════════════════════════════════════════
# wigent — TUI App
# Role: Textual-based Terminal User Interface
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Wigent Terminal User Interface — OpenCode-style full-screen TUI.

Usage
-----
    from wigent.cli.tui_app import WigentTUI
    app = WigentTUI()
    app.run()
"""

from __future__ import annotations

import logging
import os
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import on, reactive
from textual.widgets import Footer, Header, Input, Label, RichLog
from textual.worker import Worker, WorkerState

from wigent.cli.tui_widgets.file_tree import WigentFileTree
from wigent.cli.tui_widgets.help_modal import HelpModal
from wigent.cli.tui_widgets.status_bar import StatusBar

logger = logging.getLogger(__name__)


class WigentTUI(App[None]):
    """Wigent full-screen TUI — OpenCode-inspired interface."""

    CSS_PATH = "tui_styles.tcss"

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=False),
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+l", "clear_chat", "Clear"),
        Binding("ctrl+m", "switch_mode", "Mode"),
        Binding("f1", "help", "Help"),
        Binding("f2", "settings", "Settings"),
        Binding("f3", "toggle_sidebar", "Files"),
        Binding("escape", "focus_input", "Input"),
    ]

    sidebar_visible: reactive[bool] = reactive(True)
    current_mode: reactive[str] = reactive("orchestrator")
    current_model: reactive[str] = reactive("")
    token_count: reactive[int] = reactive(0)
    session_cost: reactive[float] = reactive(0.0)

    def __init__(self, initial_prompt: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._initial_prompt = initial_prompt
        self._agent: Any | None = None
        self._pending_thinking_line: int | None = None

    def compose(self) -> ComposeResult:
        """Compose the TUI layout."""
        yield Header(show_clock=True)

        with Horizontal(id="main-container"):
            # Left sidebar — file tree
            with Vertical(id="sidebar"):
                yield Label("📁 Files", classes="panel-title")
                yield WigentFileTree(".", id="file-tree")

            # Right side — chat + input
            with Vertical(id="content"):
                with Vertical(id="chat-panel"):
                    yield RichLog(
                        id="chat-log",
                        auto_scroll=True,
                        wrap=True,
                        highlight=True,
                        markup=True,
                    )
                with Vertical(id="input-panel"):
                    yield Input(
                        id="user-input",
                        placeholder="Type message or /command... (Esc for help)",
                    )

        yield StatusBar(id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize on startup."""
        self.title = "🤖 Wigent"
        self.sub_title = "AI Coding Agent"

        # Initialize agent (lazy to avoid heavy import at startup)
        try:
            from wigent.core.agent import WigentAgent
            self._agent = WigentAgent()
            workspace_path = os.getcwd()
            self._agent.load_workspace(workspace_path)
            self.current_model = self._agent._model_name
        except Exception as exc:
            logger.exception("Failed to initialize agent: %s", exc)
            self._write_chat("[bold red]⚠ Failed to initialize agent. Check config.[/]")

        # Welcome message
        self._write_chat(
            "[bold cyan]🤖 Wigent ready![/]  "
            "[dim]Type a message to begin. Press F1 for help.[/]"
        )

        # If an initial prompt was passed, run it
        if self._initial_prompt:
            self._submit_message(self._initial_prompt)
        else:
            self.query_one("#user-input", Input).focus()

    # ── Event Handlers ───────────────────────────────────────────

    @on(Input.Submitted)
    def _on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle user pressing Enter in the input field."""
        message = event.value.strip()
        event.input.value = ""
        if message:
            self._submit_message(message)

    def _submit_message(self, message: str) -> None:
        """Process a user message."""
        self._write_chat(f"[bold white]You ▸[/] {message}")

        if message.startswith("/"):
            self._handle_command(message)
        else:
            self._send_to_agent(message)

    def _send_to_agent(self, message: str) -> None:
        """Dispatch message to the agent in a background worker."""
        if self._agent is None:
            self._write_chat("[red]Agent not initialized.[/]")
            return

        # Show thinking indicator
        chat_log = self.query_one("#chat-log", RichLog)
        self._pending_thinking_line = chat_log.line_count
        self._write_chat("[dim italic]🤖 Wigent is thinking...[/]")

        # Run agent in a worker thread
        self.run_worker(self._agent.run, thread=True, kwargs={"task": message})

    @on(Worker.StateChanged)
    def _on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Handle background worker completion."""
        if event.state != WorkerState.SUCCESS:
            return

        result = event.worker.result
        if result is None:
            return

        # Remove thinking line if present
        if self._pending_thinking_line is not None:
            # RichLog doesn't support removing lines directly;
            # we just overwrite by writing the response below.
            self._pending_thinking_line = None

        # Extract result text
        result_text = ""
        if isinstance(result, dict):
            result_text = result.get("result", "")
        elif isinstance(result, str):
            result_text = result

        if result_text:
            self._write_chat(f"[bold cyan]🤖 Wigent ▸[/] {result_text}")
        else:
            self._write_chat("[dim](no response)[/]")

        # Update status bar from agent state
        self._update_status_from_agent()

    # ── Commands ───────────────────────────────────────────────

    def _handle_command(self, command: str) -> None:
        """Handle slash commands."""
        parts = command.split()
        cmd = parts[0].lower()
        args = parts[1:]

        handlers = {
            "/help": self.action_help,
            "/clear": self.action_clear_chat,
            "/mode": lambda: self._cmd_mode(args),
            "/exit": self.action_quit,
            "/quit": self.action_quit,
        }

        handler = handlers.get(cmd)
        if handler:
            handler()
        else:
            self._write_chat(f"[yellow]Unknown command: {cmd}. Try /help[/]")

    def _cmd_mode(self, args: list[str]) -> None:
        """Switch agent mode."""
        if not args:
            self._write_chat(f"[dim]Current mode: {self.current_mode}[/]")
            return
        new_mode = args[0].lower()
        if self._agent is not None:
            try:
                self._agent.set_mode(new_mode)
                self.current_mode = new_mode
                self._write_chat(f"[green]Switched to {new_mode} mode.[/]")
            except Exception as exc:
                self._write_chat(f"[red]Failed to switch mode: {exc}[/]")
        else:
            self._write_chat("[red]Agent not initialized.[/]")

    # ── Actions ────────────────────────────────────────────────

    def action_help(self) -> None:
        """Show help modal."""
        self.push_screen(HelpModal())

    def action_clear_chat(self) -> None:
        """Clear chat log."""
        chat_log = self.query_one("#chat-log", RichLog)
        chat_log.clear()
        self._write_chat("[dim]Chat cleared.[/]")

    def action_switch_mode(self) -> None:
        """Cycle through modes."""
        modes = ["orchestrator", "architect", "coder", "debugger", "reviewer"]
        idx = modes.index(self.current_mode) if self.current_mode in modes else 0
        new_mode = modes[(idx + 1) % len(modes)]
        self._cmd_mode([new_mode])

    def action_toggle_sidebar(self) -> None:
        """Toggle file tree sidebar."""
        self.sidebar_visible = not self.sidebar_visible
        sidebar = self.query_one("#sidebar", Vertical)
        sidebar.display = self.sidebar_visible

    def action_focus_input(self) -> None:
        """Focus the input field."""
        self.query_one("#user-input", Input).focus()

    def action_settings(self) -> None:
        """Placeholder for settings action."""
        self._write_chat("[dim]Settings panel coming soon.[/]")

    # ── Helpers ──────────────────────────────────────────────────

    def _write_chat(self, text: str) -> None:
        """Write a line to the chat log."""
        chat_log = self.query_one("#chat-log", RichLog)
        chat_log.write(text)

    def _update_status_from_agent(self) -> None:
        """Refresh status bar from agent state."""
        if self._agent is None:
            return
        try:
            status = self._agent.get_status()
            self.current_mode = status.get("mode", self.current_mode)
            self.current_model = status.get("model", self.current_model)
            self.token_count = status.get("memory_tokens", 0)
            self.session_cost = status.get("last_run_cost", 0.0)
        except Exception:
            pass

        status_bar = self.query_one("#status-bar", StatusBar)
        status_bar.update_info(
            mode=self.current_mode,
            model=self.current_model,
            tokens=self.token_count,
            cost=self.session_cost,
        )

    def watch_current_mode(self, mode: str) -> None:
        """React to mode changes."""
        self.sub_title = f"Mode: {mode}"


__all__ = ["WigentTUI"]
