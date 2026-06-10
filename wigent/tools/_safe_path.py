# ════════════════════════════════════════
# wigent — Safe Path Resolution
# Role: Shared path validation utility for all tool modules
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Path resolution with sandbox escape prevention.

All file‑oriented tools must resolve paths through this module to
guarantee no operation escapes the workspace boundary.
"""

from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Tuple

from wigent.config import settings

logger = logging.getLogger(__name__)


def get_workspace() -> str:
    """Return the absolute workspace root path."""
    return settings.workspace_path


def resolve_path(path: str, *, require_existing: bool = False) -> Tuple[str, str | None]:
    """Resolve a user‑supplied path and validate it stays inside the workspace.

    Args:
        path: Relative or absolute path (relative paths are resolved against workspace).
        require_existing: If True, the resolved path must already exist on disk.

    Returns:
        A tuple of ``(absolute_path, error_message)``.
        On success ``error_message`` is ``None`` and ``absolute_path`` is usable.
        On failure ``error_message`` contains the reason and ``absolute_path`` is empty.
    """
    workspace = os.path.abspath(get_workspace())

    # Normalise — join relative paths against workspace, resolve absolute as‑is.
    joined = os.path.join(workspace, path) if not os.path.isabs(path) else path
    resolved = os.path.abspath(os.path.normpath(joined))

    # Sandbox escape guard.
    if not resolved.startswith(workspace):
        return "", (
            f"Path '{path}' resolves outside the workspace ({resolved}). "
            f"All operations are restricted to {workspace}."
        )

    if require_existing and not os.path.exists(resolved):
        return "", f"Path '{path}' does not exist at {resolved}."

    return resolved, None


def ensure_parent(path: str) -> str | None:
    """Create parent directories for *path* if they don't exist.

    Returns ``None`` on success, or an error message string on failure.
    """
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        try:
            os.makedirs(parent, exist_ok=True)
        except OSError as exc:
            return f"Failed to create parent directories for '{path}': {exc}"
    return None


__all__ = ["get_workspace", "resolve_path", "ensure_parent"]
