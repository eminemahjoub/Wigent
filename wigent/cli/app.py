# ════════════════════════════════════════
# wigent — CLI Application
# Role: Main entry point — argument parsing, config loading, agent launch
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""CLI entry point that parses arguments, loads configuration, and launches
the agent in interactive or single-shot mode."""

from __future__ import annotations

import argparse
import logging
import sys
from typing import NoReturn

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser."""
    parser = argparse.ArgumentParser(
        prog="wigent",
        description="Autonomous AI coding agent",
        epilog="Visit https://wigent.dev for documentation.",
    )
    # TODO: add --model, --workspace, --verbose, --yes, --version flags
    return parser


def run_interactive() -> None:
    """Run the agent in interactive mode — prompts the user for tasks."""
    # TODO: implement interactive REPL
    raise NotImplementedError


def run_single(prompt: str) -> None:
    """Run the agent once with a given prompt."""
    # TODO: implement single-shot mode
    raise NotImplementedError


def main(argv: list[str] | None = None) -> NoReturn:
    """Parse arguments and dispatch to the appropriate mode."""
    # TODO: wire up argparse, logging, config load, then run
    raise NotImplementedError


__all__ = ["main"]
