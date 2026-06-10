# ════════════════════════════════════════
# wigent — Root Package
# Role: Top-level namespace for the wigent AI coding agent
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""wigent — An autonomous AI coding agent.

Sub-packages:
    core      — Agent brain and think-act-observe loop
    tools     — All agent capabilities (file, shell, search, code)
    models    — LLM provider abstraction layer
    memory    — Conversation history and workspace context
    prompts   — System prompts and templates
    safety    — Command validation and approval gates
    cli       — Terminal interface
    config    — Settings and configuration
"""

from wigent.core import run_agent
from wigent.config import settings

__all__ = ["run_agent", "settings"]
__version__ = "0.1.0"
