# ════════════════════════════════════════
# wigent — Workspace State
# Role: Track workspace contents and file state between steps
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Lightweight cache of workspace contents to reduce redundant I/O
and inform the agent about what files exist."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class WorkspaceState:
    """Snapshot of the workspace directory tree.

    Can be invalidated and refreshed as the agent creates/modifies files.
    """

    def __init__(self, workspace_root: str) -> None:
        self._root = workspace_root
        self._snapshot: dict[str, Any] = {}

    def refresh(self) -> None:
        """Re-scan the workspace and update the internal snapshot."""
        # TODO: implement
        raise NotImplementedError

    def file_exists(self, path: str) -> bool:
        """Check whether a path exists in the cached snapshot."""
        # TODO: implement
        raise NotImplementedError

    def list_files(self, suffix: str | None = None) -> list[str]:
        """Return all files, optionally filtered by suffix."""
        # TODO: implement
        raise NotImplementedError


__all__ = ["WorkspaceState"]
