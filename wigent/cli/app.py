from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Any, NoReturn

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from wigent.config import settings


logger = logging.getLogger(__name__)
console = Console()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wigent",
        description="Autonomous AI coding agent",
        epilog="Visit https://wigent.dev for documentation.",
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        help="Task prompt (single-shot mode). Omit for interactive mode.",
    )
    parser.add_argument(
        "--mode", "-m",
        default=None,
        help="Agent mode (orchestrator, architect, coder, debugger, reviewer)",
    )
    parser.add_argument(
        "--provider", "-p",
        default=None,
        help="LLM provider (openai, anthropic, gemini, groq, ollama, etc.)",
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        default=False,
        help="Auto-approve all actions (bypass safety gates)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=False,
        help="Enable debug logging",
    )
    return parser


def display_workspace_banner(info: dict[str, Any]) -> None:
    if not info or info.get("project_type", "unknown") == "unknown":
        console.print(
            Panel(
                "[yellow]No project detected. Working in current directory.[/yellow]",
                title="📁 Workspace",
                border_style="yellow",
            )
        )
        return

    ptype = info.get("project_type", "unknown")
    framework = info.get("framework")
    lang = info.get("language", "unknown")
    pm = info.get("package_manager")
    has_git = info.get("has_git", False)

    type_str = f"{ptype}" + (f" ({framework})" if framework else "")
    type_color = "cyan" if ptype != "unknown" else "yellow"
    lang_color = "green" if lang != "unknown" else "white"

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold")
    grid.add_column()

    grid.add_row("📁 Project", f"[bright_cyan]{os.path.basename(info.get('path', ''))}[/bright_cyan]")
    grid.add_row("⚡ Type", f"[{type_color}]{type_str}[/{type_color}]")
    grid.add_row("🔤 Language", f"[{lang_color}]{lang}[/{lang_color}]")
    grid.add_row("📦 Package Manager", pm or "[dim]none[/dim]")

    if has_git:
        git_color = "green"
        git_status = "✓ git repository"
        try:
            import subprocess
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, timeout=3,
                cwd=info.get("path", ""),
            )
            if result.returncode == 0:
                branch = result.stdout.strip()
                dirty = subprocess.run(
                    ["git", "status", "--porcelain"],
                    capture_output=True, text=True, timeout=3,
                    cwd=info.get("path", ""),
                )
                dirty_flag = " [+dirty]" if dirty.stdout.strip() else ""
                git_status = f"🌿 {branch}{dirty_flag}"
                git_color = "red" if dirty.stdout.strip() else "green"
        except Exception:
            pass
        grid.add_row("🌿 Git", f"[{git_color}]{git_status}[/{git_color}]")
    else:
        grid.add_row("🌿 Git", "[dim]no repo[/dim]")

    if info.get("has_tests"):
        grid.add_row("🧪 Tests", "[green]detected[/green]")
    if info.get("has_docker"):
        grid.add_row("🐳 Docker", "[blue]detected[/blue]")

    console.print(Panel(grid, title="📁 Workspace Loaded", border_style="bright_blue"))


def run_interactive(agent: Any) -> None:
    console.print("[bold green]✅ Agent ready. Enter your task (or /help for commands).[/bold green]")
    console.print()
    while True:
        try:
            prompt = console.input("[bold cyan]>> [/bold cyan]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Goodbye![/yellow]")
            break

        if not prompt:
            continue
        if prompt.startswith("/"):
            _handle_command(agent, prompt)
            continue

        with console.status("[cyan]Thinking...[/cyan]"):
            try:
                state = agent.run(prompt)
                result = state.get("result", "") if state else ""
                if result:
                    console.print(result)
            except Exception as exc:
                console.print(f"[red]Error: {exc}[/red]")


def _handle_command(agent: Any, cmd: str) -> None:
    cmd = cmd.lower().strip()
    if cmd == "/help":
        console.print("[bold]Commands:[/bold]")
        console.print("  /help       - Show this help")
        console.print("  /status     - Show agent status")
        console.print("  /workspace  - Show workspace info")
        console.print("  /reload     - Reload workspace")
        console.print("  /reset      - Reset agent state")
        console.print("  /exit       - Exit")
    elif cmd == "/status":
        status = agent.get_status()
        console.print(Panel(str(status), title="Status"))
    elif cmd == "/workspace":
        ws = agent.get_workspace_info()
        display_workspace_banner(ws)
    elif cmd == "/reload":
        with console.status("[cyan]Reloading workspace...[/cyan]"):
            ws = agent.reload_workspace()
        display_workspace_banner(ws)
    elif cmd == "/reset":
        agent.reset()
        console.print("[green]Agent reset.[/green]")
    elif cmd in ("/exit", "/quit"):
        console.print("[yellow]Goodbye![/yellow]")
        sys.exit(0)
    else:
        console.print(f"[red]Unknown command: {cmd}. Type /help for commands.[/red]")


def main(argv: list[str] | None = None) -> NoReturn:
    parser = build_parser()
    args = parser.parse_args(argv)

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s  %(name)s  %(message)s")

    if args.yes:
        os.environ["AUTO_APPROVE"] = "true"

    from wigent.core.agent import WigentAgent

    agent = WigentAgent(
        mode=args.mode,
        provider=args.provider,
    )

    workspace_path = os.getcwd()
    with console.status("[cyan]Loading project context...[/cyan]"):
        workspace_info = agent.load_workspace(workspace_path)

    display_workspace_banner(workspace_info)

    if args.prompt:
        with console.status("[cyan]Thinking...[/cyan]"):
            try:
                state = agent.run(args.prompt, mode=args.mode)
                result = state.get("result", "") if state else ""
                if result:
                    console.print(result)
            except Exception as exc:
                console.print(f"[red]Error: {exc}[/red]")
        sys.exit(0)

    run_interactive(agent)
    sys.exit(0)


if __name__ == "__main__":
    main()

__all__ = ["main"]
