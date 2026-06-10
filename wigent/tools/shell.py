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

from wigent.config import settings

logger = logging.getLogger(__name__)


def run_command(command: str, *, timeout: int = 30, **kwargs: Any) -> dict[str, Any]:
    """Execute a shell command inside the workspace and return combined output.

    Args:
        command: Shell command string to execute.
        timeout: Maximum execution time in seconds (default 30).
        **kwargs: Extra arguments passed to ``subprocess.run``.

    Returns:
        A dict with keys: ``success`` (bool), ``stdout`` (str),
        ``stderr`` (str), ``output`` (str — combined), ``returncode`` (int),
        ``timed_out`` (bool), ``error`` (str | None).
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=settings.workspace_path,
            capture_output=True,
            text=True,
            timeout=timeout,
            **kwargs,
        )
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        return {
            "success": result.returncode == 0,
            "stdout": stdout,
            "stderr": stderr,
            "output": stdout + stderr,
            "returncode": result.returncode,
            "timed_out": False,
            "error": None,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": "",
            "output": f"Command timed out after {timeout}s.",
            "returncode": -1,
            "timed_out": True,
            "error": f"Timed out after {timeout}s",
        }
    except Exception as exc:
        logger.exception("Command failed: %s", command[:120])
        return {
            "success": False,
            "stdout": "",
            "stderr": "",
            "output": str(exc),
            "returncode": -1,
            "timed_out": False,
            "error": str(exc),
        }


__all__ = ["run_command"]
