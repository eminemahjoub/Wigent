from __future__ import annotations

import sys
from typing import Any

import click
from click.exceptions import Exit as ClickExit


@click.command(
    name="wigent",
    help="Autonomous AI coding agent.",
    epilog="https://wigent.dev",
)
@click.argument("prompt", required=False, default=None)
@click.option(
    "--provider", "-p",
    type=click.Choice(["openai", "anthropic", "gemini", "groq", "ollama", "mistral", "cohere", "litellm"]),
    default=None,
    help="LLM provider to use.",
)
@click.option(
    "--model", "-m",
    type=str,
    default=None,
    metavar="MODEL",
    help="Model name override.",
)
@click.option(
    "--mode",
    type=click.Choice(["orchestrator", "architect", "coder", "debugger", "reviewer"]),
    default=None,
    help="Agent operational mode.",
)
@click.option(
    "--session", "-s",
    type=str,
    default=None,
    metavar="NAME",
    help="Load a named session on startup.",
)
@click.option(
    "--workspace", "-w",
    type=str,
    default=None,
    metavar="DIR",
    help="Set the workspace directory.",
)
@click.option(
    "--no-banner",
    is_flag=True,
    default=False,
    help="Skip the startup banner (useful for scripts).",
)
@click.option(
    "--debug", "-d",
    is_flag=True,
    default=False,
    help="Enable debug logging.",
)
@click.option(
    "--yes", "-y",
    is_flag=True,
    default=False,
    help="Auto-approve all actions.",
)
@click.option(
    "--classic",
    is_flag=True,
    default=False,
    help="Use classic line-by-line CLI instead of TUI.",
)
def cli_main(
    prompt: str | None,
    provider: str | None,
    model: str | None,
    mode: str | None,
    session: str | None,
    workspace: str | None,
    no_banner: bool,
    debug: bool,
    yes: bool,
    classic: bool,
) -> dict[str, Any]:
    """Parse CLI arguments and return a config dict."""
    return {
        "prompt": prompt,
        "provider": provider,
        "model": model,
        "mode": mode,
        "session": session,
        "workspace": workspace,
        "no_banner": no_banner,
        "debug": debug,
        "yes": yes,
        "classic": classic,
        "version": "1.0.0",
    }


def parse_args(argv: list[str] | None = None) -> dict[str, Any]:
    """Parse CLI arguments using Click and return a config dict.

    Handles --help and --version automatically via Click.
    Routes 'setup' subcommand to the interactive setup wizard.
    """
    args = argv if argv is not None else sys.argv[1:]

    # Route 'wigent setup' to the interactive wizard.
    if args and args[0] == "setup":
        from wigent.cli.setup_wizard import main as setup_main
        setup_main()
        sys.exit(0)

    # Check for --version explicitly before Click processing.
    if "--version" in args:
        click.echo("wigent, version 1.0.0")
        sys.exit(0)

    try:
        ctx = cli_main.make_context("wigent", args)
        return cli_main.invoke(ctx)
    except ClickExit:
        # Click raises Exit(0) when --help is processed; convert to SystemExit.
        sys.exit(0)


__all__ = ["cli_main", "parse_args"]
