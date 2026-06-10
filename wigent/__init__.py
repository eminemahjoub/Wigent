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

from wigent.config import settings


def run_agent(user_prompt: str, **kwargs: str) -> str:
    """Lazily import and run the agent to avoid triggering model chain at import time."""
    from wigent.core.agent import run_agent as _run
    return _run(user_prompt, **kwargs)


__all__ = ["run_agent", "settings"]
__version__ = "0.5.5"
