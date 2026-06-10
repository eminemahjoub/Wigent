# ════════════════════════════════════════
# wigent — File Lister
# Role: Directory listing, tree view, and glob-based file discovery
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""List files and directories inside the sandbox workspace."""

from __future__ import annotations

import fnmatch
import glob
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from wigent.tools._safe_path import resolve_path

logger = logging.getLogger(__name__)


# ── tree view ────────────────────────────────────────────────────────────


def list_directory(path: str = ".", depth: int = -1) -> dict[str, Any]:
    """Produce a tree‑formatted listing of a directory.

    Args:
        path: Relative or absolute path inside the workspace.
        depth: Maximum recursion depth (``-1`` = unlimited, ``0`` = top‑level only).

    Returns:
        A dict with keys: ``success`` (bool), ``path`` (str),
        ``tree`` (str — indented text tree), ``entries`` (int),
        ``error`` (str | None).

    Raises:
        ValueError: If the path escapes the workspace.
    """
    resolved, err = resolve_path(path)
    if err:
        raise ValueError(err)

    if not os.path.isdir(resolved):
        return {
            "success": False,
            "path": path,
            "tree": "",
            "entries": 0,
            "error": f"Not a directory: {path}",
        }

    lines: list[str] = []
    entry_count = [0]

    def _walk(current: str, current_depth: int) -> None:
        if depth != -1 and current_depth > depth:
            return
        try:
            entries = sorted(os.listdir(current))
        except PermissionError:
            lines.append(f"{'  ' * current_depth}[permission denied]")
            return
        except OSError as exc:
            lines.append(f"{'  ' * current_depth}[error: {exc}]")
            return

        for entry in entries:
            full = os.path.join(current, entry)
            prefix = "  " * current_depth
            if os.path.isdir(full):
                lines.append(f"{prefix}📁 {entry}/")
                entry_count[0] += 1
                _walk(full, current_depth + 1)
            else:
                size = os.path.getsize(full) if os.path.isfile(full) else 0
                lines.append(f"{prefix}📄 {entry}  ({_human_size(size)})")
                entry_count[0] += 1

    _walk(resolved, 0)
    tree = "\n".join(lines) if lines else "(empty)"

    return {
        "success": True,
        "path": path,
        "tree": tree,
        "entries": entry_count[0],
        "error": None,
    }


def get_project_structure(root: str = ".") -> dict[str, Any]:
    """Produce a full project structure tree.

    This is a convenience wrapper around ``list_directory`` with
    unlimited depth, but always starts from the workspace root.

    Args:
        root: Relative subdirectory (default ``"."``).

    Returns:
        Same structure as ``list_directory``.
    """
    return list_directory(path=root, depth=-1)


# ── filtered listing ─────────────────────────────────────────────────────


def list_files(
    path: str = ".",
    pattern: str = "*",
    recursive: bool = True,
) -> dict[str, Any]:
    """List files matching a glob pattern.

    Args:
        path: Base directory inside the workspace.
        pattern: Glob pattern (e.g. ``"*.py"``, ``"**/*.ts"``).
        recursive: If True, search subdirectories (allows ``**`` in pattern).

    Returns:
        A dict with keys: ``success``, ``files`` (list of str), ``count`` (int),
        ``error``.
    """
    resolved, err = resolve_path(path)
    if err:
        raise ValueError(err)

    if not os.path.isdir(resolved):
        return {"success": False, "files": [], "count": 0, "error": f"Not a directory: {path}"}

    search_path = os.path.join(resolved, pattern) if recursive else os.path.join(resolved, pattern)
    matched = sorted(glob.glob(search_path, recursive=recursive))

    # Filter to files only (skip directories unless pattern explicitly requests them).
    files = [m for m in matched if os.path.isfile(m)]

    # Normalise to relative paths for cleaner output.
    from wigent.config import settings
    root = settings.workspace_path
    rel_files: list[str] = []
    for f in files:
        try:
            rel_files.append(os.path.relpath(f, root))
        except ValueError:
            rel_files.append(f)

    return {"success": True, "files": rel_files, "count": len(rel_files), "error": None}


def find_files(pattern: str, root: str = ".") -> dict[str, Any]:
    """Find files matching a pattern via recursive glob.

    Args:
        pattern: Glob pattern (supports ``**`` for recursion).
        root: Base directory inside the workspace.

    Returns:
        Results dict with ``success``, ``files``, ``count``, ``error``.
    """
    return list_files(path=root, pattern=pattern, recursive=True)


def get_recent_files(root: str = ".", n: int = 10) -> dict[str, Any]:
    """Return the *n* most recently modified files.

    Args:
        root: Base directory inside the workspace.
        n: Maximum number of files to return.

    Returns:
        A dict with keys: ``success``, ``files`` (list of dicts with
        ``path``, ``modified_iso``, ``size_bytes``), ``error``.
    """
    resolved, err = resolve_path(root)
    if err:
        raise ValueError(err)

    if not os.path.isdir(resolved):
        return {"success": False, "files": [], "error": f"Not a directory: {root}"}

    all_files: list[dict[str, Any]] = []
    for dirpath, _, filenames in os.walk(resolved):
        for fname in filenames:
            full = os.path.join(dirpath, fname)
            try:
                stat = os.stat(full)
                from wigent.config import settings
                rel = os.path.relpath(full, settings.workspace_path)
                all_files.append({
                    "path": rel,
                    "modified_iso": datetime.fromtimestamp(stat.st_mtime, tz=__import__("zoneinfo").ZoneInfo("UTC")).isoformat(),
                    "size_bytes": stat.st_size,
                })
            except OSError:
                continue

    all_files.sort(key=lambda x: x["modified_iso"], reverse=True)

    return {"success": True, "files": all_files[:n], "error": None}


# ── helpers ──────────────────────────────────────────────────────────────


def _human_size(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f}{unit}" if unit != "B" else f"{size}B"
        size /= 1024
    return f"{size:.1f}TB"


__all__ = [
    "list_directory",
    "get_project_structure",
    "list_files",
    "find_files",
    "get_recent_files",
]
