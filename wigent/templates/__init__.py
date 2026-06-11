# ════════════════════════════════════════
# wigent — Templates Package
# Role: Template rendering utilities for Wigent planner output
# Author: Wigent AI
# Version: 1.0.0
# ════════════════════════════════════════

"""Provides Jinja2 environment with custom filters for task plan rendering.

Usage
-----
    from wigent.templates import render_master_plan, render_task_card

    plan_md = render_master_plan("MyApp", tasks, parallel_groups, metadata)
    card_md = render_task_card(task)
    checklist = render_checklist(tasks)
    standup = render_standup(tasks, "2026-06-11")
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

__all__ = [
    "create_template_env",
    "render_master_plan",
    "render_task_card",
    "render_checklist",
    "render_standup",
]


def create_template_env() -> Environment:
    """Create a Jinja2 environment with Wigent custom filters.

    Returns:
        Configured Jinja2 ``Environment``.
    """
    template_dir = Path(__file__).parent
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    env.filters["sum_effort"] = _sum_effort_filter
    env.filters["format_effort"] = _format_effort_filter
    env.filters["status_icon"] = _status_icon_filter
    env.filters["dependency_chain"] = _dependency_chain_filter

    return env


def render_master_plan(
    project_name: str,
    tasks: list[dict[str, Any]],
    parallel_groups: list[list[dict[str, Any]]],
    metadata: dict[str, Any] | None = None,
) -> str:
    """Render a complete master plan from task data.

    Args:
        project_name: Name of the project or feature.
        tasks: List of task dictionaries.
        parallel_groups: List of parallel task groups.
        metadata: Optional metadata (timestamp, version, risks, etc.).

    Returns:
        Rendered markdown string.
    """
    env = create_template_env()
    macro_template = env.from_string(
        "{% from \"task.md\" import render_master_plan %}\n"
        "{{ render_master_plan(project_name, tasks, parallel_groups, metadata) }}"
    )
    return macro_template.render(
        project_name=project_name,
        tasks=tasks,
        parallel_groups=parallel_groups,
        metadata=metadata or {},
    )


def render_task_card(task: dict[str, Any]) -> str:
    """Render a single task card.

    Args:
        task: A task dictionary.

    Returns:
        Rendered markdown task card.
    """
    env = create_template_env()
    macro_template = env.from_string(
        "{% from \"task.md\" import render_task_card %}\n"
        "{{ render_task_card(task) }}"
    )
    return macro_template.render(task=task)


def render_checklist(tasks: list[dict[str, Any]]) -> str:
    """Render a compact checklist view.

    Args:
        tasks: List of task dictionaries.

    Returns:
        Rendered markdown checklist.
    """
    env = create_template_env()
    macro_template = env.from_string(
        "{% from \"task.md\" import render_checklist %}\n"
        "{{ render_checklist(tasks) }}"
    )
    return macro_template.render(tasks=tasks)


def render_standup(tasks: list[dict[str, Any]], date: str = "Today") -> str:
    """Render a daily standup summary.

    Args:
        tasks: List of task dictionaries.
        date: Date string for the standup header.

    Returns:
        Rendered markdown standup summary.
    """
    env = create_template_env()
    macro_template = env.from_string(
        "{% from \"task.md\" import render_standup %}\n"
        "{{ render_standup(tasks, date) }}"
    )
    return macro_template.render(tasks=tasks, date=date)


# ── Custom Jinja2 Filters ──────────────────────────────────────────────


def _sum_effort_filter(tasks: list[dict[str, Any]]) -> str:
    """Sum effort values across tasks and return a human-readable string."""
    values = {"XS": 0.5, "S": 1.0, "M": 2.0}
    total = sum(values.get(t.get("estimated_effort", "S"), 1.0) for t in tasks)

    if total < 1:
        return f"{int(total * 8)}h"
    if total < 5:
        return f"{total:.1f}d"
    return f"{total / 5:.1f}w"


def _format_effort_filter(effort: str) -> str:
    """Format a single effort value with a description."""
    descriptions = {
        "XS": "XS (~4 hours)",
        "S": "S (~1 day)",
        "M": "M (~2 days)",
    }
    return descriptions.get(effort, effort)


def _status_icon_filter(status: str) -> str:
    """Return the emoji icon for a given status."""
    icons = {
        "pending": "\u2b1c",
        "in_progress": "\U0001f504",
        "done": "\u2705",
        "blocked": "\U0001f6ab",
    }
    return icons.get(status, "\u2b1c")


def _dependency_chain_filter(
    task: dict[str, Any],
    all_tasks: list[dict[str, Any]],
) -> str:
    """Return a formatted dependency chain for a task.

    Args:
        task: The task to inspect.
        all_tasks: All tasks in the plan for cross-referencing.

    Returns:
        Indented bullet list of dependency chains.
    """
    task_map = {t["id"]: t for t in all_tasks}
    chain: list[str] = []

    def _build_chain(task_id: str, depth: int = 0) -> None:
        if task_id not in task_map or depth > 10:
            return
        t = task_map[task_id]
        indent = "  " * depth
        chain.append(f"{indent}- {task_id}: {t['description']}")
        for dep in t.get("dependencies", []):
            _build_chain(dep, depth + 1)

    for dep in task.get("dependencies", []):
        _build_chain(dep)

    return "\n".join(chain) if chain else "None"
