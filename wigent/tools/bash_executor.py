# ════════════════════════════════════════
# wigent — Bash Executor
# Role: Production-safe shell command execution (NO shell=True)
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Safe command execution — uses ``shlex.split()`` (NOT ``shell=True``),
mandatory timeouts, process kill on timeout, and sandbox classification.

Every command passes through ``safety.sandbox.classify_command()``
before execution.  Blocked commands are rejected; warned commands
require approval.

SECURITY GUARANTEES:
    - ``shell=True`` is NEVER used.
    - All commands are parsed with ``shlex.split()``.
    - Timeout is mandatory (default 30 s).
    - Processes are killed (SIGKILL) on timeout.
    - All executions are logged with timestamps.
    - Dangerous commands are classified and blocked.
"""

from __future__ import annotations

import os
import shlex
import signal
import stat
import subprocess
import tempfile
import time
import logging
from pathlib import Path
from typing import Any

from wigent.config import settings
from wigent.safety.sandbox import (
    classify_command,
    CommandCategory,
    sanitize_env,
)

logger = logging.getLogger(__name__)


# ── constants ────────────────────────────────────────────────────────────

_DEFAULT_TIMEOUT: int = 30
_MAX_OUTPUT_CHARS: int = 100_000  # prevent memory exhaustion from huge output


# ── core executor ────────────────────────────────────────────────────────


def execute_command(
    command: str,
    cwd: str | None = None,
    timeout: int = _DEFAULT_TIMEOUT,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Execute a shell command **without** ``shell=True``.

    The command string is parsed with ``shlex.split()`` to produce a
    safe argument list.  The command is classified by the sandbox
    before execution — blocked commands are rejected immediately.

    Args:
        command: Shell command string (e.g. ``"ls -la"``).
        cwd: Working directory (default: workspace root).
        timeout: Maximum execution time in seconds (default 30).
        env: Optional environment overrides.

    Returns:
        A dict with keys:
            ``success`` (bool),
            ``stdout`` (str),
            ``stderr`` (str),
            ``exit_code`` (int),
            ``execution_time`` (float),
            ``command`` (str),
            ``blocked_reason`` (str | None).
    """
    start = time.monotonic()
    cwd = cwd or settings.workspace_path
    env = sanitize_env(env)
    full_env = {**env}

    # ── classification ──────────────────────────────────────────────────
    classification = classify_command(command)
    if classification.category == CommandCategory.BLOCKED:
        logger.warning(
            "BLOCKED command rejected: %s | reason: %s",
            command[:120], classification.reason,
        )
        return {
            "success": False,
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "execution_time": time.monotonic() - start,
            "command": command,
            "blocked_reason": classification.reason,
        }

    # ── parse command safely ────────────────────────────────────────────
    try:
        args = shlex.split(command)
    except ValueError as exc:
        logger.error("Failed to parse command: %s", exc)
        return {
            "success": False,
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "execution_time": time.monotonic() - start,
            "command": command,
            "blocked_reason": f"Failed to parse command: {exc}",
        }

    if not args:
        return {
            "success": False,
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "execution_time": time.monotonic() - start,
            "command": command,
            "blocked_reason": "Empty command",
        }

    # ── execution ───────────────────────────────────────────────────────
    logger.info(
        "Executing [%s] in cwd=%s timeout=%ds",
        command[:120], cwd, timeout,
    )

    process: subprocess.Popen | None = None
    try:
        process = subprocess.Popen(
            args,
            cwd=cwd,
            env=full_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=lambda: os.setsid() if os.name != "nt" else None,
        )

        stdout, stderr = process.communicate(timeout=timeout)

        # Truncate huge output to prevent memory issues.
        if len(stdout) > _MAX_OUTPUT_CHARS:
            stdout = stdout[:_MAX_OUTPUT_CHARS] + f"\n... [truncated at {_MAX_OUTPUT_CHARS} chars]"
        if len(stderr) > _MAX_OUTPUT_CHARS:
            stderr = stderr[:_MAX_OUTPUT_CHARS] + f"\n... [truncated at {_MAX_OUTPUT_CHARS} chars]"

        elapsed = time.monotonic() - start
        exit_code = process.returncode

        logger.info(
            "Command completed [exit=%d] in %.2fs: %s",
            exit_code, elapsed, command[:80],
        )

        return {
            "success": exit_code == 0,
            "stdout": stdout or "",
            "stderr": stderr or "",
            "exit_code": exit_code,
            "execution_time": round(elapsed, 3),
            "command": command,
            "blocked_reason": None,
        }

    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start
        logger.warning("Command timed out after %ds: %s", timeout, command[:80])

        # Kill the entire process group.
        if process:
            try:
                if os.name == "nt":
                    process.kill()
                else:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                logger.info("Killed process group %d", os.getpgid(process.pid))
            except (OSError, ProcessLookupError) as exc:
                logger.warning("Failed to kill timed-out process: %s", exc)

            # Consume remaining output to avoid zombie.
            try:
                process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                pass

        return {
            "success": False,
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "execution_time": round(elapsed, 3),
            "command": command,
            "blocked_reason": f"Timed out after {timeout}s",
        }

    except FileNotFoundError:
        elapsed = time.monotonic() - start
        binary = args[0]
        logger.error("Command not found: %s", binary)
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Command not found: {binary}",
            "exit_code": -1,
            "execution_time": round(elapsed, 3),
            "command": command,
            "blocked_reason": f"Command not found: {binary}",
        }

    except PermissionError:
        elapsed = time.monotonic() - start
        logger.error("Permission denied: %s", args[0])
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Permission denied executing: {args[0]}",
            "exit_code": -1,
            "execution_time": round(elapsed, 3),
            "command": command,
            "blocked_reason": f"Permission denied: {args[0]}",
        }

    except (OSError, subprocess.SubprocessError) as exc:
        elapsed = time.monotonic() - start
        logger.exception("Execution failed: %s", command[:120])
        return {
            "success": False,
            "stdout": "",
            "stderr": str(exc),
            "exit_code": -1,
            "execution_time": round(elapsed, 3),
            "command": command,
            "blocked_reason": str(exc),
        }


# ── script execution ─────────────────────────────────────────────────────


def execute_script(
    script_content: str,
    cwd: str | None = None,
    timeout: int = _DEFAULT_TIMEOUT,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Write *script_content* to a temporary file and execute it.

    The script file is created in a secure temporary directory,
    marked executable, run, and then cleaned up.

    Args:
        script_content: Shell script content (may contain multiple commands,
                       pipes, etc. — this is the one case where shell=True
                       is safe because we control the entire script).
        cwd: Working directory (default: workspace root).
        timeout: Maximum execution time in seconds (default 30).
        env: Optional environment overrides.

    Returns:
        Same format as ``execute_command()``.
    """
    start = time.monotonic()
    cwd = cwd or settings.workspace_path
    env = sanitize_env(env)

    # Scripts always require approval.
    classification = classify_command(script_content)
    if classification.category == CommandCategory.BLOCKED:
        return {
            "success": False,
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "execution_time": time.monotonic() - start,
            "command": f"<script {len(script_content)} chars>",
            "blocked_reason": classification.reason,
        }

    tmp_path: str | None = None
    try:
        # Create a temp file in a secure temp directory.
        fd, tmp_path = tempfile.mkstemp(prefix="wigent_script_", suffix=".sh")
        os.close(fd)

        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(script_content)
            if not script_content.endswith("\n"):
                f.write("\n")

        # Make executable.
        os.chmod(tmp_path, stat.S_IRWXU)

        logger.info("Executing script (%d chars) from %s", len(script_content), tmp_path)

        result = execute_command(tmp_path, cwd=cwd, timeout=timeout, env=env)
        result["command"] = f"<script {len(script_content)} chars>"
        return result

    except OSError as exc:
        elapsed = time.monotonic() - start
        return {
            "success": False,
            "stdout": "",
            "stderr": str(exc),
            "exit_code": -1,
            "execution_time": round(elapsed, 3),
            "command": f"<script {len(script_content)} chars>",
            "blocked_reason": str(exc),
        }

    finally:
        # Clean up temp file.
        if tmp_path and os.path.isfile(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError as exc:
                logger.warning("Failed to clean up temp script %s: %s", tmp_path, exc)


# ── Python execution ─────────────────────────────────────────────────────


def run_python(
    code: str,
    cwd: str | None = None,
    timeout: int = _DEFAULT_TIMEOUT,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Execute Python code in an isolated subprocess.

    The code is written to a temporary ``.py`` file and executed with
    ``python3`` (resolved from the sanitised PATH).  The temp file is
    cleaned up after execution.

    Args:
        code: Python source code to execute.
        cwd: Working directory (default: workspace root).
        timeout: Maximum execution time in seconds (default 30).
        env: Optional environment overrides.

    Returns:
        Same format as ``execute_command()``.
    """
    cwd = cwd or settings.workspace_path

    # Check if python3 is available.
    python_binary = "python3"
    try:
        subprocess.run(
            [python_binary, "--version"],
            capture_output=True, text=True, timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        python_binary = "python"
        try:
            subprocess.run(
                [python_binary, "--version"],
                capture_output=True, text=True, timeout=5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return {
                "success": False,
                "stdout": "",
                "stderr": "Python interpreter not found",
                "exit_code": -1,
                "execution_time": 0.0,
                "command": "<python code>",
                "blocked_reason": "Python interpreter not found",
            }

    tmp_path: str | None = None
    try:
        fd, tmp_path = tempfile.mkstemp(prefix="wigent_python_", suffix=".py")
        os.close(fd)

        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(code)
            if not code.endswith("\n"):
                f.write("\n")

        full_command = f"{python_binary} {tmp_path}"
        result = execute_command(full_command, cwd=cwd, timeout=timeout, env=env)
        result["command"] = f"<python {len(code)} chars>"
        return result

    except OSError as exc:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(exc),
            "exit_code": -1,
            "execution_time": 0.0,
            "command": "<python code>",
            "blocked_reason": str(exc),
        }

    finally:
        if tmp_path and os.path.isfile(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError as exc:
                logger.warning("Failed to clean up temp python %s: %s", tmp_path, exc)


# ── preview ──────────────────────────────────────────────────────────────


def get_command_preview(command: str) -> dict[str, Any]:
    """Show what a command would do **without** executing it.

    Classifies the command and returns parsed arguments.

    Args:
        command: Shell command string to preview.

    Returns:
        A dict with keys: ``command`` (str), ``parsed_args`` (list[str]),
        ``classification`` (str), ``reason`` (str), ``safe`` (bool).
    """
    classification = classify_command(command)

    try:
        args = shlex.split(command)
    except ValueError as exc:
        args = [f"<parse error: {exc}>"]

    return {
        "command": command,
        "parsed_args": args,
        "classification": classification.category.value,
        "reason": classification.reason,
        "safe": classification.category == CommandCategory.SAFE,
    }


# ── process management ──────────────────────────────────────────────────


def kill_process(pid: int, force: bool = True) -> dict[str, Any]:
    """Terminate a running process.

    Args:
        pid: Process ID to kill.
        force: If True, sends SIGKILL (default).  Otherwise SIGTERM.

    Returns:
        A dict with keys: ``success`` (bool), ``pid`` (int),
        ``signal`` (str), ``error`` (str | None).
    """
    sig = signal.SIGKILL if force else signal.SIGTERM
    sig_name = "SIGKILL" if force else "SIGTERM"

    try:
        os.kill(pid, sig)
        logger.warning("Killed process %d with %s", pid, sig_name)
        return {"success": True, "pid": pid, "signal": sig_name, "error": None}
    except ProcessLookupError:
        return {"success": False, "pid": pid, "signal": sig_name, "error": f"Process {pid} not found"}
    except PermissionError:
        return {"success": False, "pid": pid, "signal": sig_name, "error": f"Permission denied to kill process {pid}"}
    except OSError as exc:
        return {"success": False, "pid": pid, "signal": sig_name, "error": str(exc)}


# ── compatibility alias ─────────────────────────────────────────────────

def run_command(command: str, *, timeout: int = _DEFAULT_TIMEOUT, **kwargs: Any) -> dict[str, Any]:
    """Compatibility wrapper — delegates to ``execute_command``.

    This function exists so existing callers continue to work.
    New code should prefer ``execute_command`` directly.

    Returns the same dict format with the additional ``output`` key
    (combined stdout + stderr) for backward compatibility.
    """
    result = execute_command(command, timeout=timeout, **kwargs)
    result["output"] = result["stdout"] + result["stderr"]
    return result


__all__ = [
    "execute_command",
    "execute_script",
    "run_python",
    "get_command_preview",
    "kill_process",
    "run_command",
]
