# ════════════════════════════════════════
# wigent — File Writer
# Role: Write, edit, diff, and backup files safely
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Safe file writing with automatic backup, line editing, and diff application."""

from __future__ import annotations

import os
import re
import shutil
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from wigent.tools._safe_path import resolve_path, ensure_parent

logger = logging.getLogger(__name__)

_BACKUP_DIRNAME = ".wigent_backups"


# ── helpers ──────────────────────────────────────────────────────────────

def _backup_root() -> str:
    """Return the backup directory path (created lazily)."""
    from wigent.config import settings
    root = os.path.join(settings.workspace_path, _BACKUP_DIRNAME)
    os.makedirs(root, exist_ok=True)
    return root


def _timestamp() -> str:
    return datetime.utcnow().strftime("%Y%m%dT%H%M%S")


def _rel_path(abs_path: str) -> str:
    """Return the path relative to the workspace root for display."""
    from wigent.config import settings
    try:
        return os.path.relpath(abs_path, settings.workspace_path)
    except ValueError:
        return abs_path


# ── core writing functions ───────────────────────────────────────────────


def write_file(path: str, content: str) -> dict[str, Any]:
    """Write content to a file, creating a backup of the previous version.

    If the file already exists a timestamped backup is saved under
    ``.wigent_backups/`` before overwriting.  Parent directories are
    created automatically.

    Args:
        path: Relative or absolute path inside the workspace.
        content: Text content to write.

    Returns:
        A dict with keys: ``success`` (bool), ``path`` (str),
        ``action`` (``"created"`` | ``"updated"`` | ``"skipped"``),
        ``backup_path`` (str | None), ``error`` (str | None).

    Raises:
        ValueError: If the path escapes the workspace.
    """
    resolved, err = resolve_path(path)
    if err:
        raise ValueError(err)

    # Create parent dirs.
    parent_err = ensure_parent(resolved)
    if parent_err:
        return {"success": False, "path": path, "action": None, "backup_path": None, "error": parent_err}

    action = "created"
    backup_path: str | None = None

    if os.path.isfile(resolved):
        action = "updated"
        # Create backup.
        rel = _rel_path(resolved).replace("/", "_").replace("\\", "_")
        backup_dir = _backup_root()
        backup_path = os.path.join(backup_dir, f"{rel}.{_timestamp()}.bak")
        try:
            shutil.copy2(resolved, backup_path)
        except OSError as exc:
            logger.warning("Backup failed for %s: %s", resolved, exc)
            backup_path = None

    try:
        with open(resolved, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError as exc:
        return {"success": False, "path": path, "action": action, "backup_path": backup_path, "error": str(exc)}

    logger.info("File %s (%s)", action, path)
    return {"success": True, "path": path, "action": action, "backup_path": backup_path, "error": None}


def create_file(path: str, content: str) -> dict[str, Any]:
    """Create a new file.  Fails if the file already exists.

    Args:
        path: Relative or absolute path inside the workspace.
        content: Text content to write.

    Returns:
        A dict with keys: ``success``, ``path``, ``error``.

    Raises:
        ValueError: If the path escapes the workspace.
    """
    resolved, err = resolve_path(path)
    if err:
        raise ValueError(err)

    if os.path.isfile(resolved):
        return {
            "success": False,
            "path": path,
            "error": f"File already exists: {path}. Use write_file() to overwrite.",
        }

    parent_err = ensure_parent(resolved)
    if parent_err:
        return {"success": False, "path": path, "error": parent_err}

    try:
        with open(resolved, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError as exc:
        return {"success": False, "path": path, "error": str(exc)}

    logger.info("File created: %s", path)
    return {"success": True, "path": path, "error": None}


def append_to_file(path: str, content: str) -> dict[str, Any]:
    """Append text to an existing file.

    Args:
        path: Relative or absolute path inside the workspace.
        content: Text to append.

    Returns:
        A dict with keys: ``success``, ``path``, ``error``.

    Raises:
        ValueError: If the path escapes the workspace.
    """
    resolved, err = resolve_path(path, require_existing=True)
    if err:
        raise ValueError(err)

    if not os.path.isfile(resolved):
        return {"success": False, "path": path, "error": f"File does not exist: {path}"}

    try:
        with open(resolved, "a", encoding="utf-8") as f:
            f.write(content)
    except OSError as exc:
        return {"success": False, "path": path, "error": str(exc)}

    return {"success": True, "path": path, "error": None}


def edit_file_lines(path: str, start: int, end: int, new_content: str) -> dict[str, Any]:
    """Replace a range of lines in a file.

    Lines are 1‑indexed.  The range ``[start, end]`` is replaced with
    ``new_content``.  A backup of the original file is created.

    Args:
        path: Relative or absolute path inside the workspace.
        start: First line to replace (1‑indexed).
        end: Last line to replace (inclusive).
        new_content: Replacement text (may contain multiple lines).

    Returns:
        A dict with keys: ``success``, ``path``, ``backup_path``, ``error``.

    Raises:
        ValueError: If the path escapes the workspace.
    """
    resolved, err = resolve_path(path, require_existing=True)
    if err:
        raise ValueError(err)

    # Read existing content.
    try:
        with open(resolved, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except (OSError, UnicodeDecodeError) as exc:
        return {"success": False, "path": path, "backup_path": None, "error": str(exc)}

    total = len(lines)

    # Clamp.
    lo = max(1, start)
    hi = min(end, total)

    if lo > hi:
        return {"success": False, "path": path, "backup_path": None, "error": f"Invalid line range: {start}–{end} (file has {total} lines)"}

    # Backup.
    rel = _rel_path(resolved).replace("/", "_").replace("\\", "_")
    backup_dir = _backup_root()
    backup_path = os.path.join(backup_dir, f"{rel}.{_timestamp()}.bak")
    try:
        shutil.copy2(resolved, backup_path)
    except OSError:
        backup_path = None

    # Rebuild.
    before = lines[: lo - 1]
    after = lines[hi:]
    new_lines = new_content.splitlines(keepends=True) or [""]
    result_lines = before + new_lines + after

    try:
        with open(resolved, "w", encoding="utf-8") as f:
            f.writelines(result_lines)
    except OSError as exc:
        return {"success": False, "path": path, "backup_path": backup_path, "error": str(exc)}

    logger.info("Edited lines %d–%d in %s", start, end, path)
    return {"success": True, "path": path, "backup_path": backup_path, "error": None}


# ── diff application ─────────────────────────────────────────────────────

_DIFF_HUNK_RE = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@.*\n"
    r"((?:[ \-+].*\n?)*)",
    re.MULTILINE,
)


def apply_diff(path: str, diff_string: str) -> dict[str, Any]:
    """Apply a unified‑diff string to a file.

    Only hunks that match the current file content are applied.
    A backup is created before any changes.

    Args:
        path: Relative or absolute path inside the workspace.
        diff_string: A valid unified diff (``diff -u`` format).

    Returns:
        A dict with keys: ``success``, ``path``, ``hunks_applied`` (int),
        ``hunks_total`` (int), ``backup_path`` (str | None), ``error``.
    """
    resolved, err = resolve_path(path, require_existing=True)
    if err:
        raise ValueError(err)

    try:
        with open(resolved, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except (OSError, UnicodeDecodeError) as exc:
        return {"success": False, "path": path, "hunks_applied": 0, "hunks_total": 0, "backup_path": None, "error": str(exc)}

    hunks = list(_DIFF_HUNK_RE.finditer(diff_string))
    if not hunks:
        return {"success": False, "path": path, "hunks_applied": 0, "hunks_total": 0, "backup_path": None, "error": "No valid diff hunks found"}

    applied = 0

    # Try each hunk in reverse order so line numbers stay valid.
    for hunk in reversed(hunks):
        old_start = int(hunk.group(1))
        old_count = int(hunk.group(2)) if hunk.group(2) else 1
        hunk_body = hunk.group(5)

        # Parse hunk lines.
        old_lines: list[str] = []
        new_lines: list[str] = []
        for hline in hunk_body.splitlines(keepends=True):
            if hline.startswith(" "):
                old_lines.append(hline[1:])
                new_lines.append(hline[1:])
            elif hline.startswith("-"):
                old_lines.append(hline[1:])
            elif hline.startswith("+"):
                new_lines.append(hline[1:])

        # Check if old_lines match the file at old_start.
        file_slice = lines[old_start - 1 : old_start - 1 + old_count]
        if [l.rstrip("\n").rstrip("\r") for l in file_slice] == [l.rstrip("\n").rstrip("\r") for l in old_lines]:
            # Apply.
            before = lines[: old_start - 1]
            after = lines[old_start - 1 + old_count :]
            lines = before + new_lines + after
            applied += 1

    # Backup only if at least one hunk matched.
    backup_path: str | None = None
    if applied > 0:
        rel = _rel_path(resolved).replace("/", "_").replace("\\", "_")
        backup_dir = _backup_root()
        backup_path = os.path.join(backup_dir, f"{rel}.{_timestamp()}.bak")
        try:
            shutil.copy2(resolved, backup_path)
        except OSError:
            backup_path = None

        try:
            with open(resolved, "w", encoding="utf-8") as f:
                f.writelines(lines)
        except OSError as exc:
            return {
                "success": False,
                "path": path,
                "hunks_applied": applied,
                "hunks_total": len(hunks),
                "backup_path": backup_path,
                "error": str(exc),
            }

    return {
        "success": applied > 0,
        "path": path,
        "hunks_applied": applied,
        "hunks_total": len(hunks),
        "backup_path": backup_path,
        "error": None if applied > 0 else "No hunks matched the current file content",
    }


# ── backup / restore ─────────────────────────────────────────────────────


def backup_file(path: str) -> dict[str, Any]:
    """Create a timestamped backup of a file.

    Args:
        path: Relative or absolute path inside the workspace.

    Returns:
        A dict with keys: ``success``, ``backup_path`` (str), ``error``.
    """
    resolved, err = resolve_path(path, require_existing=True)
    if err:
        raise ValueError(err)

    if not os.path.isfile(resolved):
        return {"success": False, "backup_path": None, "error": f"Not a file: {path}"}

    rel = _rel_path(resolved).replace("/", "_").replace("\\", "_")
    backup_dir = _backup_root()
    backup_path = os.path.join(backup_dir, f"{rel}.{_timestamp()}.bak")

    try:
        shutil.copy2(resolved, backup_path)
    except OSError as exc:
        return {"success": False, "backup_path": None, "error": str(exc)}

    return {"success": True, "backup_path": backup_path, "error": None}


def restore_backup(path: str) -> dict[str, Any]:
    """Restore the most recent backup of a file.

    Args:
        path: Relative or absolute path inside the workspace.

    Returns:
        A dict with keys: ``success``, ``path``, ``restored_from`` (str),
        ``error``.
    """
    resolved, err = resolve_path(path, require_existing=True)
    if err:
        raise ValueError(err)

    rel = _rel_path(resolved).replace("/", "_").replace("\\", "_")
    backup_dir = _backup_root()

    pattern = f"{rel}.*.bak"
    backups = sorted(Path(backup_dir).glob(pattern), key=os.path.getmtime, reverse=True)

    if not backups:
        return {"success": False, "path": path, "restored_from": None, "error": "No backups found"}

    latest = str(backups[0])
    try:
        shutil.copy2(latest, resolved)
    except OSError as exc:
        return {"success": False, "path": path, "restored_from": latest, "error": str(exc)}

    logger.info("Restored %s from backup %s", path, latest)
    return {"success": True, "path": path, "restored_from": latest, "error": None}


__all__ = [
    "write_file",
    "create_file",
    "append_to_file",
    "edit_file_lines",
    "apply_diff",
    "backup_file",
    "restore_backup",
]
