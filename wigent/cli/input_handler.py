from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import Completer, Completion, WordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.lexers import PygmentsLexer
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.prompt import Confirm, Prompt

logger = logging.getLogger(__name__)

PROMPT_STYLE = Style.from_dict(
    {
        "prompt": "ansicyan bold",
        "mode": "ansiyellow",
    }
)


class CommandCompleter(Completer):
    def __init__(self, commands: list[dict[str, str]]) -> None:
        self._commands = commands
        self._command_names = [cmd["name"].split()[0] for cmd in commands]
        self._mode_names = ["orchestrator", "architect", "coder", "debugger", "reviewer"]
        self._provider_names = ["openai", "anthropic", "gemini", "groq", "ollama", "mistral", "cohere", "litellm"]

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        words = text.split()
        word = words[-1] if words else ""
        is_first_word = len(words) <= 1

        if is_first_word:
            for cmd_name in self._command_names:
                if cmd_name.startswith(word):
                    yield Completion(cmd_name, start_position=-len(word))

        elif words[0] == "/mode":
            for name in self._mode_names:
                if name.startswith(word):
                    yield Completion(name, start_position=-len(word))

        elif words[0] == "/model":
            for name in self._provider_names:
                if name.startswith(word):
                    yield Completion(name, start_position=-len(word))


class InputHandler:
    def __init__(
        self,
        commands: list[dict[str, str]],
        console: Console | None = None,
    ) -> None:
        self._console = console or Console(highlight=False)

        history_dir = Path.home() / ".wigent"
        history_dir.mkdir(parents=True, exist_ok=True)
        history_path = str(history_dir / "history")

        self._completer = CommandCompleter(commands)
        self._history = FileHistory(history_path)
        self._bindings = self._setup_keybindings()

        self._session: PromptSession | None = None

    def _setup_keybindings(self) -> KeyBindings:
        kb = KeyBindings()

        @kb.add("c-c")
        def _(event):
            event.app.exit(result="__INTERRUPT__")

        @kb.add("c-d")
        def _(event):
            event.app.exit(result="__EXIT__")

        @kb.add("c-l")
        def _(event):
            event.app.renderer.clear()
            self._console.print()

        return kb

    def get_input(self, mode: str = "orchestrator") -> str:
        if self._session is None:
            self._session = PromptSession(
                history=self._history,
                completer=self._completer,
                key_bindings=self._bindings,
                auto_suggest=AutoSuggestFromHistory(),
                style=PROMPT_STYLE,
                enable_history_search=True,
                complete_while_typing=True,
            )

        prompt_text = [
            ("class:prompt", "wigent "),
            ("class:mode", f"[{mode}]"),
            ("class:prompt", " ❯ "),
        ]

        try:
            result = self._session.prompt(prompt_text)
        except KeyboardInterrupt:
            return "__INTERRUPT__"

        if result is None:
            return "__EXIT__"

        return result.strip()

    def get_confirmation(self, message: str, default: bool = False) -> bool:
        return Confirm.ask(f"[yellow]{message}[/yellow]", default=default, console=self._console)

    def get_choice(self, message: str, options: list[str]) -> str:
        return Prompt.ask(
            f"[yellow]{message}[/yellow]",
            choices=options,
            console=self._console,
        )


__all__ = ["InputHandler", "CommandCompleter"]
