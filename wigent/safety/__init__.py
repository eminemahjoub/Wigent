# ════════════════════════════════════════
# wigent — Safety Package
# Role: Command validation, sandbox, approval gates, and workspace enforcement
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Safety layer — classifies commands, validates paths, manages approvals,
and enforces sandbox boundaries."""

from wigent.safety.sandbox import (
    CommandCategory,
    Classification,
    classify_command,
    validate_sandbox_path,
    sanitize_env,
    format_approval_request,
    BLOCKED_PATTERNS,
    WARN_PATTERNS,
    SAFE_PREFIXES,
)
from wigent.safety.approval import ApprovalGate, RiskLevel

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
    "ApprovalGate",
    "RiskLevel",
]
