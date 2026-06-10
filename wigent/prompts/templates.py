# ════════════════════════════════════════
# wigent — Prompt Templates
# Role: Reusable prompt fragments and few-shot examples
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Reusable prompt components that can be composed into the system prompt
or injected dynamically based on the task."""

from __future__ import annotations

from typing import Final

TOOL_DESCRIPTIONS: Final[dict[str, str]] = {
    "write_file": "Write content to a file inside the workspace.",
    "read_file": "Read the full content of a file inside the workspace.",
    "run_command": "Execute a shell command in the workspace directory.",
    "list_files": "Recursively list files and directories in the workspace.",
    "search_codebase": "Search for a string across all workspace files.",
    "get_file_summary": "Read the first 2000 characters of a file.",
}

# TODO: add few-shot examples for multi-step coding workflows
# TODO: add task-specific instruction fragments

__all__ = ["TOOL_DESCRIPTIONS"]
