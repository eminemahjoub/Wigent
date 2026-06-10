# ════════════════════════════════════════
# wigent — File Reader
# Role: Read files with encoding detection and batch support
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Safe file reading — single, ranged, batch, and metadata operations."""

from __future__ import annotations

import os
import logging
from datetime import datetime
from typing import Any

from wigent.tools._safe_path import resolve_path

logger = logging.getLogger(__name__)


# ── public helpers (used externally and by other tools) ──────────────────

ENCODING_PRIORITIES: list[str] = [
    "utf-8",
    "utf-8-sig",
    "ascii",
    "latin-1",
    "cp1252",
    "iso-8859-1",
]


def detect_encoding(path: str) -> str:
    """Detect the likely encoding of a file by trying common codecs.

    Args:
        path: Absolute path to the file.

    Returns:
        A codec name (e.g. ``"utf-8"``).  Falls back to ``"utf-8"``.
    """
    for enc in ENCODING_PRIORITIES:
        try:
            with open(path, "r", encoding=enc) as f:
                f.read(256)
            return enc
        except (UnicodeDecodeError, LookupError):
            continue
    return "utf-8"


def get_file_info(path: str) -> dict[str, Any]:
    """Return metadata about a file or directory.

    Args:
        path: Relative or absolute path inside the workspace.

    Returns:
        A dict with keys: ``path``, ``exists``, ``is_file``, ``is_dir``,
        ``size_bytes``, ``modified_iso``, ``encoding`` (files only).

    Raises:
        ValueError: If the path escapes the workspace.
    """
    resolved, err = resolve_path(path)
    if err:
        raise ValueError(err)

    info: dict[str, Any] = {
        "path": resolved,
        "exists": os.path.exists(resolved),
        "is_file": False,
        "is_dir": False,
        "size_bytes": 0,
        "modified_iso": "",
        "encoding": None,
    }

    if not info["exists"]:
        return info

    info["is_file"] = os.path.isfile(resolved)
    info["is_dir"] = os.path.isdir(resolved)

    try:
        stat = os.stat(resolved)
        info["size_bytes"] = stat.st_size
        info["modified_iso"] = datetime.fromtimestamp(
            stat.st_mtime, tz=__import__("zoneinfo").ZoneInfo("UTC")
        ).isoformat()
    except OSError:
        pass

    if info["is_file"] and info["size_bytes"] > 0:
        info["encoding"] = detect_encoding(resolved)

    return info


# ── core reading functions ───────────────────────────────────────────────


def read_file(path: str) -> dict[str, Any]:
    """Read the full content of a file and return it with metadata.

    Args:
        path: Relative or absolute path inside the workspace.

    Returns:
        A dict with keys: ``success`` (bool), ``content`` (str),
        ``encoding`` (str), ``line_count`` (int), ``size_bytes`` (int),
        ``error`` (str, only on failure).

    Raises:
        ValueError: If the path escapes the workspace.
    """
    resolved, err = resolve_path(path, require_existing=True)
    if err:
        raise ValueError(err)

    if not os.path.isfile(resolved):
        return {
            "success": False,
            "content": "",
            "encoding": "",
            "line_count": 0,
            "size_bytes": 0,
            "error": f"Not a file: {path}",
        }

    encoding = detect_encoding(resolved)

    try:
        with open(resolved, "r", encoding=encoding) as f:
            content = f.read()
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("Failed to read %s with %s, trying fallback encodings", resolved, encoding)
        for fallback in [e for e in ENCODING_PRIORITIES if e != encoding]:
            try:
                with open(resolved, "r", encoding=fallback) as f:
                    content = f.read()
                encoding = fallback
                break
            except (OSError, UnicodeDecodeError):
                continue
        else:
            return {
                "success": False,
                "content": "",
                "encoding": encoding,
                "line_count": 0,
                "size_bytes": 0,
                "error": f"Failed to read '{path}': {exc}",
            }

    return {
        "success": True,
        "content": content,
        "encoding": encoding,
        "line_count": content.count("\n") + (1 if content and not content.endswith("\n") else 0),
        "size_bytes": os.path.getsize(resolved),
        "error": None,
    }


def read_file_lines(path: str, start: int = 1, end: int | None = None) -> dict[str, Any]:
    """Read a range of lines from a file (1‑indexed).

    Args:
        path: Relative or absolute path inside the workspace.
        start: First line number (1‑indexed, default 1).
        end: Last line number (inclusive).  If ``None``, reads to EOF.

    Returns:
        A dict with keys: ``success``, ``lines`` (list of str), ``start``,
        ``end``, ``total_lines``, ``error``.

    Raises:
        ValueError: If the path escapes the workspace.
    """
    resolved, err = resolve_path(path, require_existing=True)
    if err:
        raise ValueError(err)

    if not os.path.isfile(resolved):
        return {"success": False, "lines": [], "start": start, "end": end, "total_lines": 0, "error": "Not a file"}

    encoding = detect_encoding(resolved)

    try:
        with open(resolved, "r", encoding=encoding) as f:
            all_lines = f.readlines()
    except (OSError, UnicodeDecodeError) as exc:
        return {"success": False, "lines": [], "start": start, "end": end, "total_lines": 0, "error": str(exc)}

    total = len(all_lines)

    # Clamp to valid ranges.
    lo = max(1, start)
    hi = len(all_lines) if end is None else min(end, len(all_lines))

    if lo > hi:
        return {
            "success": True,
            "lines": [],
            "start": start,
            "end": end,
            "total_lines": total,
            "error": None,
        }

    selected = all_lines[lo - 1 : hi]

    return {
        "success": True,
        "lines": [line.rstrip("\n").rstrip("\r") for line in selected],
        "start": lo,
        "end": hi,
        "total_lines": total,
        "error": None,
    }


def read_multiple_files(paths: list[str]) -> dict[str, dict[str, Any]]:
    """Batch‑read multiple files in a single call.

    Args:
        paths: List of relative or absolute paths inside the workspace.

    Returns:
        A dict mapping each input path to its ``read_file()`` result dict.
    """
    results: dict[str, dict[str, Any]] = {}
    for p in paths:
        try:
            results[p] = read_file(p)
        except (ValueError, OSError) as exc:
            results[p] = {
                "success": False,
                "content": "",
                "encoding": "",
                "line_count": 0,
                "size_bytes": 0,
                "error": str(exc),
            }
    return results


__all__ = [
    "read_file",
    "read_file_lines",
    "read_multiple_files",
    "get_file_info",
    "detect_encoding",
]
