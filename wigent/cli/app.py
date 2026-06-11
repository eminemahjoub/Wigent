from __future__ import annotations

import logging
import os
import sys
from typing import Any, NoReturn

from wigent.config import settings

from wigent.cli.cli_args import parse_args
from wigent.cli.commands import CommandHandler
from wigent.cli.diff_display import DiffDisplay
from wigent.cli.input_handler import InputHandler
from wigent.cli.ui_components import UIComponents

logger = logging.getLogger(__name__)
ui = UIComponents()


def display_workspace_banner(info: dict[str, Any]) -> None:
    """Legacy wrapper — delegates to UIComponents."""
    ui.print_workspace_banner(info)


def _determine_mode(args: dict[str, Any]) -> str:
    return args.get("mode") or settings.DEFAULT_MODE


def _determine_provider(args: dict[str, Any]) -> str:
    return args.get("provider") or settings.DEFAULT_PROVIDER


def run_interactive(agent: Any) -> None:
    cmd_handler = CommandHandler(agent, ui)
    input_handler = InputHandler(cmd_handler.get_all_commands(), console=ui.console)
    mode = agent._mode

    ui.console.print()
    ui.print_divider("Ready")

    while True:
        user_input = input_handler.get_input(mode=mode)

        if user_input == "__INTERRUPT__":
            ui.print_interrupt_message()
            continue

        if user_input == "__EXIT__":
            n = len(agent.messages) if agent.messages else 0
            ui.console.print(f"[yellow]Goodbye! {n} messages in session.[/yellow]")
            break

        if not user_input:
            continue

        if user_input.startswith("/"):
            result = cmd_handler.execute(user_input)
            ui.print_command_result(result.to_dict())
            if result.data.get("should_exit"):
                break
            continue

        ui.print_user_message(user_input)

        with ui.console.status(f"[{ui.THINKING_COLOR}]Thinking...[/{ui.THINKING_COLOR}]"):
            try:
                state = agent.run(user_input)
                result_text = state.get("result", "") if state else ""
                if result_text:
                    ui.print_agent_message(result_text, mode=agent._mode)
            except Exception as exc:
                ui.print_error(str(exc), recoverable=True)

        status = agent.get_status()
        ui.print_status_bar({
            "mode": status.get("mode", mode),
            "model": status.get("model", "unknown"),
            "tokens_used": status.get("memory_tokens", 0),
            "tokens_max": 200_000,
            "cost": status.get("last_run_cost", 0.0),
        })
        mode = agent._mode


def main(argv: list[str] | None = None) -> NoReturn:
    args = parse_args(argv)

    log_level = logging.DEBUG if args.get("debug") else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s  %(name)s  %(message)s")

    if args.get("yes"):
        os.environ["AUTO_APPROVE"] = "true"

    version = args.get("version", "0.6.0")
    mode = _determine_mode(args)
    provider = _determine_provider(args)

    if not args.get("no_banner"):
        ui.print_banner(version=version, model=provider, mode=mode)

    from wigent.core.agent import WigentAgent

    agent = WigentAgent(
        mode=args.get("mode"),
        provider=args.get("provider"),
    )

    workspace_path = args.get("workspace") or os.getcwd()
    with ui.console.status(f"[{ui.THINKING_COLOR}]Loading project context...[/{ui.THINKING_COLOR}]"):
        workspace_info = agent.load_workspace(workspace_path)

    ui.print_workspace_banner(workspace_info)

    if args.get("session"):
        try:
            session = agent._memory.sessions.load_session(args["session"])
            if session:
                agent._current_session_id = session.session_id
                ui.console.print(f"[green]Loaded session: {args['session']}[/green]")
        except Exception:
            ui.console.print(f"[yellow]Session '{args['session']}' not found.[/yellow]")

    if args.get("prompt"):
        prompt = args["prompt"]
        ui.print_user_message(prompt)
        with ui.console.status(f"[{ui.THINKING_COLOR}]Thinking...[/{ui.THINKING_COLOR}]"):
            try:
                state = agent.run(prompt, mode=args.get("mode"))
                result_text = state.get("result", "") if state else ""
                if result_text:
                    ui.print_agent_message(result_text, mode=agent._mode)
            except Exception as exc:
                ui.print_error(str(exc), recoverable=False)
        sys.exit(0)

    run_interactive(agent)
    sys.exit(0)


if __name__ == "__main__":
    main()

__all__ = ["main", "display_workspace_banner"]
