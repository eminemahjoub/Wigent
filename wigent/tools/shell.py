# ════════════════════════════════════════
# wigent — Shell Execution
# Role: Run shell commands inside the sandbox workspace
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Safe subprocess execution with timeout and output capture."""

from __future__ import annotations

import subprocess
import logging
from typing import Any

logger = logging.getLogger(__name__)


def run_command(command: str, *, timeout: int = 30, **kwargs: Any) -> str:
    """Execute a shell command inside the workspace and return combined output.

    Args:
        command: Shell command string to execute.
        timeout: Maximum execution time in seconds (default 30).
        **kwargs: Extra arguments passed to subprocess.run.

    Returns:
        Combined stdout + stderr, or an error message on failure.
    """
    # TODO: implement with subprocess.run, cwd=WORKSPACE
    raise NotImplementedError


__all__ = ["run_command"]
