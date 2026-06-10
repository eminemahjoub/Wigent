# ════════════════════════════════════════
# wigent — Safety Package
# Role: Command validation, approval gates, and sandbox enforcement
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Safety layer — validates tool calls before execution and enforces
workspace confinement policies."""

from wigent.safety.validator import validate_path, validate_command
from wigent.safety.approval import ApprovalGate

__all__ = ["validate_path", "validate_command", "ApprovalGate"]
