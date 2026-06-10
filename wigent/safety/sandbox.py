# ════════════════════════════════════════
# wigent — Sandbox Security
# Role: Command classification, blacklist, whitelist, and resource limits
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Sandbox security layer — classifies commands into BLOCKED / WARN / SAFE
categories, enforces path boundaries, and sets resource limits.

Every shell command MUST pass through ``classify_command()`` before
execution.  Blocked commands are rejected immediately; warned commands
require explicit user approval.
"""

from __future__ import annotations

import os
import re
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Final

from wigent.config import settings

logger = logging.getLogger(__name__)


# ── risk categories ──────────────────────────────────────────────────────

class CommandCategory(Enum):
    """Risk category assigned to a command after classification."""

    BLOCKED = "blocked"
    """Never execute — blocked immediately with an error message."""
    WARN = "warn"
    """Requires explicit user approval before execution."""
    SAFE = "safe"
    """Allowed with full logging."""


# ── classification result ────────────────────────────────────────────────

@dataclass(frozen=True)
class Classification:
    """Result of classifying a command."""

    category: CommandCategory
    reason: str = ""
    """Human-readable explanation of the classification."""


# ── BLOCKED patterns ─────────────────────────────────────────────────────
# These are NEVER executed under any condition.

BLOCKED_PATTERNS: Final[list[re.Pattern]] = [
    # ── filesystem destruction ───────────────────────────────────────────
    re.compile(r"\brm\s+(-rf|--recursive)\s+/(?:$|\s|/)"),
    re.compile(r"\brm\s+(-rf|--recursive)\s+/\*"),
    re.compile(r"\brm\s+(-rf|--recursive)\s+~"),
    re.compile(r"\bmv\s+/\s+/dev/null"),
    re.compile(r"\bdd\s+if=/dev/"),
    re.compile(r"\bmkfs\b"),
    re.compile(r"\bmkswap\b"),
    re.compile(r"\bfdisk\b"),
    re.compile(r"\bparted\b"),
    # ── privilege escalation ────────────────────────────────────────────
    re.compile(r"\bsudo\b"),
    re.compile(r"\bsu\s+"),
    re.compile(r"\bchmod\s+777\b"),
    re.compile(r"\bchown\s"),
    re.compile(r"\bpasswd\b"),
    re.compile(r"\busermod\b"),
    re.compile(r"\bgroupmod\b"),
    # ── system modification ─────────────────────────────────────────────
    re.compile(r">\s*/etc/"),
    re.compile(r">\s*/sys/"),
    re.compile(r">\s*/proc/"),
    re.compile(r"\bwrit(e|ing)\s+/sys/"),
    re.compile(r"\bwrit(e|ing)\s+/proc/"),
    re.compile(r"\bexportfs\b"),
    re.compile(r"\bmount\b"),
    re.compile(r"\bumount\b"),
    # ── network exfiltration ────────────────────────────────────────────
    re.compile(r"\bcurl\s+.*\||\|.*\bcurl\b"),
    re.compile(r"\bwget\s+.*\||\|.*\bwget\b"),
    re.compile(r"\bbash\s*<[\s]*\("),
    # ── fork bombs / resource exhaustion ─────────────────────────────────
    re.compile(r":\(\)\s*\{"),
    re.compile(r":\(\)\s*\|"),
    re.compile(r"\bfork\s*bomb"),
    re.compile(r"\bwhile\s+true\s*;.*\bfi\b.*\bdone\b"),  # infinite fork
    # ── service management ──────────────────────────────────────────────
    re.compile(r"\bsystemctl\s+(stop|restart|start|enable|disable)\b"),
    re.compile(r"\bservice\s+\w+\s+(stop|restart|start)\b"),
    # ── firewall / network config ───────────────────────────────────────
    re.compile(r"\biptables\b"),
    re.compile(r"\bufw\b"),
    re.compile(r"\bifconfig\s+\w+\s+(down|up)\b"),
    re.compile(r"\bip\s+link\s+set\b"),
    # ── package management ──────────────────────────────────────────────
    re.compile(r"\bapt\s+(install|remove|purge|upgrade)\b"),
    re.compile(r"\bapt-get\s+(install|remove|purge|upgrade)\b"),
    re.compile(r"\bdnf\s+(install|remove|erase|upgrade)\b"),
    re.compile(r"\byum\s+(install|remove|erase|update)\b"),
    re.compile(r"\bpip\s+(install|uninstall)\b"),
    re.compile(r"\bnpm\s+(install|uninstall|rm)\b"),
    re.compile(r"\bbrew\s+(install|uninstall|upgrade)\b"),
    # ── git destructive ─────────────────────────────────────────────────
    re.compile(r"\bgit\s+reset\s+--hard\b"),
    re.compile(r"\bgit\s+clean\s+-fd"),
    re.compile(r"\bgit\s+push\s+--force\b"),
    re.compile(r"\bgit\s+push\s+-f\b"),
    # ── kill signal ─────────────────────────────────────────────────────
    re.compile(r"\bkill\s+-9\b"),
    re.compile(r"\bpkill\s+-9\b"),
    # ── /dev/ access ────────────────────────────────────────────────────
    re.compile(r">\s*/dev/(sda|sdb|sdc|sdd|nvme|zero|null)"),
    re.compile(r"\bdd\s+of=/dev/"),
]

# ── WARN patterns ────────────────────────────────────────────────────────
# These need explicit user approval.

WARN_PATTERNS: Final[list[re.Pattern]] = [
    # ── destructive file operations ──────────────────────────────────────
    re.compile(r"\brm\s+(-rf|--recursive)\b"),
    re.compile(r"\brmdir\b"),
    re.compile(r"\bmv\s+\S+\s+\S+"),
    re.compile(r"\bcp\s+\S+\s+\S+"),
    re.compile(r"\btruncate\b"),
    re.compile(r"\bshred\b"),
    # ── network operations ──────────────────────────────────────────────
    re.compile(r"\bcurl\b"),
    re.compile(r"\bwget\b"),
    re.compile(r"\bssh\b"),
    re.compile(r"\bscp\b"),
    re.compile(r"\brsync\b"),
    re.compile(r"\bnc\b"),
    re.compile(r"\bncat\b"),
    re.compile(r"\btelnet\b"),
    re.compile(r"\bftp\b"),
    re.compile(r"\bsocat\b"),
    # ── process manipulation ────────────────────────────────────────────
    re.compile(r"\bkill\b"),
    re.compile(r"\bpkill\b"),
    re.compile(r"\bnohup\b"),
    re.compile(r"\bdisown\b"),
    # ── environment / config ────────────────────────────────────────────
    re.compile(r"\bexport\s+\w+="),
    re.compile(r"\bunset\b"),
    re.compile(r"\balias\b"),
    re.compile(r"\bunalias\b"),
    # ── docker (can delete containers/images) ───────────────────────────
    re.compile(r"\bdocker\s+(rm|rmi|system\s+prune)\b"),
    re.compile(r"\bdocker\s+exec\b"),
    # ── file redirection to important paths ─────────────────────────────
    re.compile(r">>\s*/\w+"),
    re.compile(r">\s*/\w+"),
    # ── background execution ────────────────────────────────────────────
    re.compile(r"&\s*$"),
    re.compile(r"\s&\s"),
]

# ── SAFE command prefixes (whitelist) ────────────────────────────────────
# Commands starting with these are automatically SAFE.

SAFE_PREFIXES: Final[list[str]] = [
    # navigation & reading
    "ls", "ll", "la", "pwd", "cat", "head", "tail", "less", "more",
    "echo", "printf", "which", "whereis", "type", "command",
    "realpath", "readlink", "basename", "dirname",
    # searching
    "grep", "rg", "ripgrep", "ag", "ack", "find", "locate",
    # file info
    "file", "stat", "wc", "du", "df", "lsblk", "lscpu", "uname",
    "arch", "date", "cal", "uptime", "whoami", "id", "logname",
    "env", "printenv",
    # git read-only
    "git status", "git log", "git diff", "git show", "git branch",
    "git blame", "git stash list",
    # python
    "python", "python3", "pytest", "ruff", "mypy", "black", "flake8",
    # compilers / interpreters
    "node", "npm run", "tsc", "gcc", "g++", "rustc", "cargo check",
    "cargo build", "cargo test", "cargo clippy", "go build", "go test",
    "go fmt",
    # utilities
    "sort", "uniq", "cut", "tr", "tee", "diff", "comm", "cmp",
    "md5sum", "sha256sum", "sha1sum", "sum", "cksum",
    "tar", "gzip", "gunzip", "zipinfo", "unzip -l", "zcat",
    # system info
    "top", "htop", "ps", "jobs", "free", "vmstat", "iostat",
    "ss -tlnp", "ss -tuln",
]


# ── command classifier ───────────────────────────────────────────────────

def classify_command(command: str) -> Classification:
    """Classify a shell command into BLOCKED / WARN / SAFE.

    The classification is based on static pattern matching against
    known dangerous patterns and safe prefix lists.

    Args:
        command: Raw shell command string to classify.

    Returns:
        A ``Classification`` dataclass with the result.
    """
    stripped = command.strip()
    if not stripped:
        return Classification(CommandCategory.BLOCKED, "Empty command")

    # ── BLOCKED check (highest priority) ────────────────────────────────
    for pattern in BLOCKED_PATTERNS:
        if pattern.search(stripped):
            # Mask the matched pattern for logging (prevent log injection).
            match_text = pattern.pattern[:60]
            logger.warning("BLOCKED command matched pattern: %s", match_text)
            return Classification(
                CommandCategory.BLOCKED,
                f"Command matched blocked pattern: {pattern.pattern[:80]}",
            )

    # ── SAFE prefix check ───────────────────────────────────────────────
    first_word = stripped.split(maxsplit=1)[0] if stripped else ""
    for prefix in SAFE_PREFIXES:
        if stripped.startswith(prefix):
            return Classification(CommandCategory.SAFE, "")

    # ── WARN check ──────────────────────────────────────────────────────
    for pattern in WARN_PATTERNS:
        if pattern.search(stripped):
            return Classification(
                CommandCategory.WARN,
                f"Command matched warn pattern: {pattern.pattern[:80]}",
            )

    # ── Default: commands not matching any pattern are WARN ─────────────
    return Classification(
        CommandCategory.WARN,
        f"Unknown command '{first_word}' — requires approval",
    )


# ── path safety ──────────────────────────────────────────────────────────

def validate_sandbox_path(path: str, workspace_root: str) -> str | None:
    """Check that a resolved path is inside the workspace.

    Returns ``None`` if the path is safe, or an error message string
    if the path tries to escape the sandbox.

    Args:
        path: The user-supplied path to validate.
        workspace_root: The absolute workspace root path.

    Returns:
        ``None`` on success, error message on failure.
    """
    resolved = os.path.abspath(os.path.normpath(os.path.join(workspace_root, path)))
    if not resolved.startswith(os.path.abspath(workspace_root)):
        return (
            f"Path '{path}' resolves outside workspace ({resolved}). "
            f"All operations are restricted to {workspace_root}."
        )
    return None


# ── env sanitization ─────────────────────────────────────────────────────

_ENV_BLOCKLIST: Final[frozenset[str]] = frozenset({
    "LD_PRELOAD", "LD_LIBRARY_PATH", "LD_AUDIT", "LD_DEBUG",
    "LD_OPENCL", "LD_PATH", "SHELL", "BASH_ENV", "ENV",
})

_DEFAULT_PATH: Final[str] = "/usr/local/bin:/usr/bin:/bin"


def sanitize_env(original: dict[str, str] | None = None) -> dict[str, str]:
    """Return a sanitised environment dict safe for subprocess execution.

    Removes environment variables that could be used for injection
    (``LD_PRELOAD``, etc.) and sets a safe ``PATH``.

    Args:
        original: Optional original environment. If ``None``, uses ``os.environ``.

    Returns:
        A cleaned environment dictionary.
    """
    env = dict(original or os.environ)

    for key in _ENV_BLOCKLIST:
        env.pop(key, None)

    # Ensure a safe PATH.
    env["PATH"] = env.get("PATH", _DEFAULT_PATH)

    return env


# ── approval helper ──────────────────────────────────────────────────────

def format_approval_request(
    command: str,
    category: CommandCategory,
    reason: str,
) -> str:
    """Format a user approval prompt for a command.

    Args:
        command: The command requiring approval.
        category: Its classification category.
        reason: The reason it was flagged.

    Returns:
        A formatted approval request string ready to display.
    """
    lines = [
        "⚠️  **Command requires approval**",
        "",
        f"**Command:** `{command}`",
        f"**Category:** {category.value.upper()}",
        f"**Reason:** {reason}",
        "",
        "Approve? (y/N): ",
    ]
    return "\n".join(lines)


@dataclass
class SafetyResult:
    level: str = "SAFE"
    reason: str = ""
    suggestion: str | None = None


class Sandbox:
    def __init__(self, workspace_root: str | None = None) -> None:
        self._workspace_root = os.path.abspath(
            workspace_root or settings.WORKSPACE_DIR
        )

    def is_path_safe(self, path: str) -> bool:
        resolved = os.path.abspath(os.path.normpath(
            os.path.join(self._workspace_root, path)
        ))
        return resolved.startswith(self._workspace_root)

    def sanitize_path(self, path: str) -> str:
        resolved = os.path.abspath(os.path.normpath(
            os.path.join(self._workspace_root, path)
        ))
        if resolved.startswith(self._workspace_root):
            return resolved
        msg = f"Path '{path}' escapes workspace (resolved: {resolved})"
        logger.warning(msg)
        raise PermissionError(msg)

    def enforce_boundary(self, path: str) -> str:
        error = validate_sandbox_path(path, self._workspace_root)
        if error:
            raise PermissionError(error)
        return os.path.abspath(os.path.normpath(
            os.path.join(self._workspace_root, path)
        ))

    def is_command_safe(self, command: str) -> SafetyResult:
        classification = classify_command(command)
        if classification.category == CommandCategory.BLOCKED:
            return SafetyResult(
                level="BLOCKED",
                reason=classification.reason,
                suggestion="This command is never allowed. Use a safer alternative.",
            )
        if classification.category == CommandCategory.WARN:
            return SafetyResult(
                level="WARN",
                reason=classification.reason,
                suggestion="This command requires approval before execution.",
            )
        return SafetyResult(level="SAFE", reason="", suggestion=None)

    def sanitize_command(self, command: str) -> str | None:
        classification = classify_command(command)
        if classification.category == CommandCategory.BLOCKED:
            logger.warning("Blocked command rejected: %s", command[:120])
            return None
        return command

    def get_workspace_root(self) -> str:
        return self._workspace_root

    def get_blocked_reason(self, command: str) -> str | None:
        classification = classify_command(command)
        if classification.category == CommandCategory.BLOCKED:
            return classification.reason
        return None


__all__ = [
    "CommandCategory",
    "Classification",
    "classify_command",
    "validate_sandbox_path",
    "sanitize_env",
    "format_approval_request",
    "BLOCKED_PATTERNS",
    "WARN_PATTERNS",
    "SAFE_PREFIXES",
    "SafetyResult",
    "Sandbox",
]
