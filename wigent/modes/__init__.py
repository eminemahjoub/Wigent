# ════════════════════════════════════════
# wigent — Modes Package
# Role: Structured mode implementations (interview, etc.)
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Standalone mode implementations that run outside the main agent loop."""

from wigent.modes.interview import BaseMode, InterviewMode

__all__ = [
    "BaseMode",
    "InterviewMode",
]
