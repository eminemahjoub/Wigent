# ════════════════════════════════════════
# wigent — Agent Modes
# Role: Define agent operational modes (orchestrator, architect, coder, etc.)
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Agent mode definitions that control behaviour, tool access, and persona.

Each mode is a dataclass with:
    - name, description, emoji
    - allowed_tools list
    - system_prompt_file
    - temperature override
    - max_iterations override
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final


@dataclass(frozen=True)
class AgentModeConfig:
    """Immutable configuration for a single agent mode."""

    name: str
    description: str
    emoji: str
    allowed_tools: tuple[str, ...] = field(default_factory=tuple)
    system_prompt_file: str = ""
    temperature: float | None = None
    max_iterations: int | None = None


# ── tool sets ────────────────────────────────────────────────────────────

_GIT_READ_TOOLS: tuple[str, ...] = (
    "check_is_git_repo", "get_repo_root", "get_status", "get_diff",
    "get_log", "get_current_branch", "list_branches", "get_blame",
    "get_file_history", "list_stashes",
)

_GIT_WRITE_TOOLS: tuple[str, ...] = (
    "stage_files", "unstage_files", "commit", "create_branch",
    "stash_changes", "pop_stash",
)

_ALL_TOOLS: tuple[str, ...] = (
    "write_file", "read_file", "list_files", "get_file_summary",
    "run_command", "search_codebase",
) + _GIT_READ_TOOLS + _GIT_WRITE_TOOLS

_PLANNING_TOOLS: tuple[str, ...] = (
    "read_file", "list_files", "search_codebase", "get_file_summary",
) + _GIT_READ_TOOLS

_CODING_TOOLS: tuple[str, ...] = (
    "write_file", "read_file", "list_files", "get_file_summary",
    "run_command",
) + _GIT_READ_TOOLS + _GIT_WRITE_TOOLS

_DEBUG_TOOLS: tuple[str, ...] = (
    "read_file", "run_command", "search_codebase", "get_file_summary",
) + _GIT_READ_TOOLS + _GIT_WRITE_TOOLS

_REVIEW_TOOLS: tuple[str, ...] = (
    "read_file", "list_files", "search_codebase", "get_file_summary",
) + _GIT_READ_TOOLS


# ── mode registry ───────────────────────────────────────────────────────

ORCHESTRATOR: Final[AgentModeConfig] = AgentModeConfig(
    name="orchestrator",
    description="Full‑autonomy mode — analyses, codes, tests, and iterates until the task is complete",
    emoji="🧠",
    allowed_tools=_ALL_TOOLS,
    system_prompt_file="orchestrator.md",
    temperature=0.7,
    max_iterations=50,
)

ARCHITECT: Final[AgentModeConfig] = AgentModeConfig(
    name="architect",
    description="Planning‑only mode — reads the codebase, designs architecture, produces a plan without writing code",
    emoji="🏛️",
    allowed_tools=_PLANNING_TOOLS,
    system_prompt_file="architect.md",
    temperature=0.5,
    max_iterations=30,
)

CODER: Final[AgentModeConfig] = AgentModeConfig(
    name="coder",
    description="Implementation mode — writes code, runs tests, fixes compilation errors. No architectural decisions",
    emoji="💻",
    allowed_tools=_CODING_TOOLS,
    system_prompt_file="coder.md",
    temperature=0.6,
    max_iterations=40,
)

DEBUGGER: Final[AgentModeConfig] = AgentModeConfig(
    name="debugger",
    description="Bug‑fixing mode — reads error output, identifies root cause, applies targeted fixes",
    emoji="🔍",
    allowed_tools=_DEBUG_TOOLS,
    system_prompt_file="debugger.md",
    temperature=0.3,
    max_iterations=30,
)

REVIEWER: Final[AgentModeConfig] = AgentModeConfig(
    name="reviewer",
    description="Code‑review mode — reads files, identifies issues, suggests improvements, writes no code",
    emoji="👁️",
    allowed_tools=_REVIEW_TOOLS,
    system_prompt_file="reviewer.md",
    temperature=0.4,
    max_iterations=20,
)

# ── lookup ───────────────────────────────────────────────────────────────

MODES: Final[dict[str, AgentModeConfig]] = {
    "orchestrator": ORCHESTRATOR,
    "architect": ARCHITECT,
    "coder": CODER,
    "debugger": DEBUGGER,
    "reviewer": REVIEWER,
}


def get_mode(name: str) -> AgentModeConfig:
    """Look up a mode by name. Raises KeyError if unknown."""
    if name not in MODES:
        raise KeyError(
            f"Unknown mode '{name}'. "
            f"Available modes: {', '.join(MODES)}"
        )
    return MODES[name]


def list_modes() -> list[dict[str, str | list[str]]]:
    """Return a list of mode summaries (useful for CLI --help)."""
    return [
        {
            "name": cfg.name,
            "emoji": cfg.emoji,
            "description": cfg.description,
            "tools": list(cfg.allowed_tools),
        }
        for cfg in MODES.values()
    ]


__all__ = [
    "AgentModeConfig",
    "ORCHESTRATOR",
    "ARCHITECT",
    "CODER",
    "DEBUGGER",
    "REVIEWER",
    "MODES",
    "get_mode",
    "list_modes",
]
