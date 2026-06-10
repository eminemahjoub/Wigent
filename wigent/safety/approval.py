# ════════════════════════════════════════
# wigent — Approval Gate
# Role: Human-in-the-loop approval for sensitive operations
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Optional approval workflow that pauses the agent before executing
high-risk tool calls (destructive commands, bulk file operations)."""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ApprovalGate:
    """Human-in-the-loop gate. When enabled, the agent pauses and asks
    for confirmation before executing medium- or high-risk actions."""

    def __init__(self, require_approval: bool = True) -> None:
        self._require_approval = require_approval

    def assess_risk(self, tool_name: str, args: dict[str, Any]) -> RiskLevel:
        """Classify a tool call by risk level based on the tool and arguments."""
        # TODO: implement risk classification
        raise NotImplementedError

    def request_approval(
        self, tool_name: str, args: dict[str, Any], risk: RiskLevel
    ) -> bool:
        """Prompt the user for approval. Returns True if approved."""
        # TODO: implement terminal prompt
        raise NotImplementedError


__all__ = ["RiskLevel", "ApprovalGate"]
