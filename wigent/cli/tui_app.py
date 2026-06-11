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

import json
import logging
import os
import re
from typing import Any

from textual.app import App, ComposeResult, on
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Header, Input, Label, RichLog
from textual.worker import Worker, WorkerState
from rich.console import Console
from rich.syntax import Syntax
from rich.text import Text

from wigent.cli.tui_widgets.file_tree import WigentFileTree
from wigent.cli.tui_widgets.help_modal import HelpModal
from wigent.cli.tui_widgets.model_picker import ModelPickerModal
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
        self._history_path = os.path.expanduser("~/.wigent/tui_history.json")
        self._history: list[dict[str, str]] = []

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

        # Load previous conversation history
        self._load_history()

        # Welcome banner (only if no history)
        if not self._history:
            self._write_chat(
                "[bold #58a6ff]╔════════════════════════════════════════════════╗[/]\n"
                "[bold #58a6ff]║                                                ║[/]\n"
                "[bold #58a6ff]║[/]  [bold #f0f6fc]██╗    ██╗██╗ ██████╗ ███████╗███╗  ██╗[/]  [bold #58a6ff]║[/]\n"
                "[bold #58a6ff]║[/]  [bold #f0f6fc]██║    ██║██║██╔════╝ ██╔════╝████╗ ██╔╝[/]  [bold #58a6ff]║[/]\n"
                "[bold #58a6ff]║[/]  [bold #f0f6fc]██║ █╗ ██║██║██║  ███╗█████╗  ██╔██╗██║ [/]  [bold #58a6ff]║[/]\n"
                "[bold #58a6ff]║[/]  [bold #f0f6fc]╚███╔███╔╝██║╚██████╔╝███████╗██║ ╚███╗ [/]  [bold #58a6ff]║[/]\n"
                "[bold #58a6ff]║[/]  [bold #f0f6fc] ╚══╝╚══╝ ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚══╝ [/]  [bold #58a6ff]║[/]\n"
                "[bold #58a6ff]║                                                ║[/]\n"
                "[bold #58a6ff]║[/]          [dim #8b949e]AI Coding Agent — type a message[/]          [bold #58a6ff]║[/]\n"
                "[bold #58a6ff]║                                                ║[/]\n"
                "[bold #58a6ff]╚════════════════════════════════════════════════╝[/]\n"
                "[dim #8b949e]Press[/] [bold #58a6ff]F2[/] [dim #8b949e]to pick a model,[/] [bold #58a6ff]F1[/] [dim #8b949e]for help[/]"
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
        self._history.append({"role": "user", "content": message})
        self._write_chat(f"[bold #3fb950]▶ You[/]  {message}")

        if message.startswith("/"):
            self._handle_command(message)
        else:
            self._send_to_agent(message)

    def _send_to_agent(self, message: str) -> None:
        """Dispatch message to the agent in a background worker."""
        if self._agent is None:
            self._write_chat("[bold #f85149]⚠[/]  [bold #f85149]Agent not initialized[/]")
            return

        self._write_chat("[dim #8b949e]● 🤖 Wigent is thinking...[/]")
        self._stream_steps: list[str] = []

        def _on_step(status: str, snapshot: Any) -> None:
            step_label = self._step_label(status, snapshot)
            if step_label and step_label not in self._stream_steps:
                self._stream_steps.append(step_label)
                self.call_from_thread(self._write_chat, f"  [dim #8b949e]→ {step_label}[/]")

        def _do_run() -> Any:
            try:
                return self._agent.run_streaming(
                    task=message,
                    on_step=_on_step,
                )
            except Exception as exc:
                return {"_error": str(exc)}

        self.run_worker(_do_run, thread=True)

    def _step_label(self, status: str, snapshot: Any) -> str | None:
        """Build a human-readable step label from agent state."""
        labels = {
            "thinking": "thinking...",
            "acting": "using tools...",
            "observing": "processing results...",
            "done": "finishing up...",
        }
        # Show latest tool call if available
        if isinstance(snapshot, dict):
            tool_calls = snapshot.get("tool_calls_made", [])
            if tool_calls and status == "acting":
                last_tool = tool_calls[-1]
                tool_name = last_tool.get("tool", "tool") if isinstance(last_tool, dict) else "tool"
                return f"using tool: {tool_name}"
        return labels.get(status)

    @on(Worker.StateChanged)
    def _on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Handle background worker completion."""
        if event.state != WorkerState.SUCCESS:
            return

        result = event.worker.result
        if result is None:
            return

        # Check for error result from worker
        if isinstance(result, dict) and "_error" in result:
            msg = result["_error"]
            if "Missing credentials" in msg or "api_key" in msg.lower():
                self._write_chat(
                    "[bold #f85149]⚠[/]  [bold #f85149]Add your API key[/]  [dim #8b949e](F2 to configure)[/]"
                )
            elif "No endpoints found that support tool use" in msg:
                self._write_chat(
                    "[bold #f85149]⚠[/]  [bold #f85149]Model doesn't support tools[/]  [dim #8b949e](F2 to switch)[/]"
                )
            elif "404" in msg and "openrouter" in msg.lower():
                self._write_chat(
                    "[bold #f85149]⚠[/]  [bold #f85149]Model unavailable[/]  [dim #8b949e](F2 to switch)[/]"
                )
            else:
                self._write_chat(
                    f"[bold #f85149]⚠[/]  [bold #f85149]{msg}[/]"
                )
            return

        # Extract result text
        result_text = ""
        if isinstance(result, dict):
            result_text = result.get("result", "")
        elif isinstance(result, str):
            result_text = result

        if result_text:
            self._history.append({"role": "assistant", "content": result_text})
            self._write_chat(f"[bold #58a6ff]● Wigent[/]  {result_text}")
        else:
            self._write_chat("[dim #8b949e]● (no response)[/]")

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
        """Open model/provider picker."""
        def _on_pick(result: tuple[str, str, str | None] | None) -> None:
            if result is None:
                return
            provider, model, api_key = result

            # Save API key to .env if provided
            if api_key:
                try:
                    from wigent.config.models_config import PROVIDER_CONFIGS
                    cfg = PROVIDER_CONFIGS.get(provider)
                    env_key = cfg.env_key if cfg and cfg.env_key else f"{provider.upper()}_API_KEY"

                    env_path = os.path.expanduser("~/.wigent/.env")
                    lines = []
                    if os.path.exists(env_path):
                        with open(env_path, "r") as f:
                            lines = f.readlines()

                    # Update or append the key
                    key_line = f"{env_key}={api_key}\n"
                    found = False
                    for i, line in enumerate(lines):
                        if line.startswith(f"{env_key}="):
                            lines[i] = key_line
                            found = True
                            break
                    if not found:
                        lines.append(key_line)

                    with open(env_path, "w") as f:
                        f.writelines(lines)

                    os.environ[env_key] = api_key
                    self._write_chat(f"[green]Saved {env_key} to ~/.wigent/.env[/]")
                except Exception as exc:
                    self._write_chat(f"[yellow]Warning: couldn't save key: {exc}[/]")

            try:
                if self._agent is not None:
                    self._agent.set_model(provider, model)
                    self.current_model = model
                    self._write_chat(f"[green]Switched to {provider} / {model}[/]")
            except Exception as exc:
                self._write_chat(f"[red]Failed to switch: {exc}[/]")

        self.push_screen(
            ModelPickerModal(
                current_provider=self._agent._provider if self._agent else "",
                current_model=self._agent._model_name if self._agent else "",
            ),
            _on_pick,
        )

    def on_unmount(self) -> None:
        """Save conversation history on exit."""
        self._save_history()

    # ── Helpers ──────────────────────────────────────────────────

    def _load_history(self) -> None:
        """Load conversation history from disk."""
        if not os.path.exists(self._history_path):
            return
        try:
            with open(self._history_path, "r", encoding="utf-8") as f:
                self._history = json.load(f)
            for item in self._history[-50:]:  # show last 50
                role = item.get("role", "")
                content = item.get("content", "")
                if role == "user":
                    self._write_chat(f"[bold #3fb950]▶ You[/]  {content}")
                elif role == "assistant":
                    self._write_chat(f"[bold #58a6ff]● Wigent[/]  {content}")
        except Exception as exc:
            logger.warning("Failed to load history: %s", exc)

    def _save_history(self) -> None:
        """Save conversation history to disk."""
        try:
            os.makedirs(os.path.dirname(self._history_path), exist_ok=True)
            with open(self._history_path, "w", encoding="utf-8") as f:
                json.dump(self._history[-200:], f, indent=2, ensure_ascii=False)
        except Exception as exc:
            logger.warning("Failed to save history: %s", exc)

    def _write_chat(self, text: str) -> None:
        """Write text to the chat log, rendering code blocks with syntax highlighting."""
        chat_log = self.query_one("#chat-log", RichLog)

        # Check for fenced code blocks
        pattern = r'```(\w+)?\n(.*?)\n```'
        if re.search(pattern, text, re.DOTALL):
            # Split and render code blocks with syntax highlighting
            parts = re.split(r'(```(?:\w+)?\n.*?\n```)', text, flags=re.DOTALL)
            for part in parts:
                match = re.match(r'```(\w+)?\n(.*?)\n```', part, re.DOTALL)
                if match:
                    lang = match.group(1) or "text"
                    code = match.group(2)
                    # Render syntax highlighted code
                    syntax = Syntax(
                        code,
                        lang,
                        theme="github-dark",
                        background_color="#161b22",
                        padding=(1, 2),
                    )
                    chat_log.write(syntax)
                else:
                    if part.strip():
                        chat_log.write(part)
        else:
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
