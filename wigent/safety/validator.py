# ════════════════════════════════════════
# wigent — Path & Command Validator
# Role: Sandbox confinement enforcement
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Validates that file paths stay within the workspace and shell commands
do not contain dangerous patterns."""

from __future__ import annotations

import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# TODO: load from config
WORKSPACE_ROOT: str = os.path.abspath(
    os.path.join(os.getcwd(), "agent_workspace")
)

# Commands that are always blocked regardless of context.
BLOCKED_COMMANDS: list[str] = [
    "rm -rf /",
    "rm -rf /*",
    ":(){ :|:& };:",  # fork bomb
    "dd if=/dev/",
    "> /dev/",
    "mkfs.",
    "fdisk",
]


def validate_path(path: str) -> str | None:
    """Check that the resolved absolute path stays inside WORKSPACE_ROOT.

    Returns None if valid, or an error message string if rejected.
    """
    # TODO: implement with os.path.abspath + startswith check
    raise NotImplementedError


def validate_command(command: str) -> str | None:
    """Check a shell command against the blocklist and safety rules.

    Returns None if safe, or an error message string if rejected.
    """
    # TODO: implement blocklist matching
    raise NotImplementedError


__all__ = ["validate_path", "validate_command"]
