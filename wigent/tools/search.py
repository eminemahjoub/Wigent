# ════════════════════════════════════════
# wigent — Codebase Search
# Role: Full-text search across workspace files
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Search for strings in the workspace using ripgrep or a Python fallback."""

from __future__ import annotations

import logging
from typing import Iterable

logger = logging.getLogger(__name__)


def search_codebase(query: str) -> str:
    """Search for a string across all files in the workspace.

    Uses ripgrep if available, otherwise falls back to a pure-Python
    file scan. Returns matching lines prefixed with filename and line number.
    """
    # TODO: implement with rg then pure-Python fallback
    raise NotImplementedError


__all__ = ["search_codebase"]
