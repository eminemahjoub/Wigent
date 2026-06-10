from __future__ import annotations

import difflib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

logger = logging.getLogger(__name__)
console = Console()


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class ChangeStats:
    lines_added: int = 0
    lines_removed: int = 0
    lines_changed: int = 0
    files_affected: int = 0
    risk_level: RiskLevel = RiskLevel.LOW


@dataclass
class Diff:
    file_path: str
    hunks: list[list[str]]
    stats: ChangeStats
    original: str = ""
    modified: str = ""
    unified_diff: str = ""


class DiffViewer:
    def compute_diff(
        self,
        original: str,
        modified: str,
        file_path: str = "",
    ) -> Diff:
        original_lines = original.splitlines(keepends=True)
        modified_lines = modified.splitlines(keepends=True)

        diff_lines = list(
            difflib.unified_diff(
                original_lines,
                modified_lines,
                fromfile=f"a/{file_path}" if file_path else "a/original",
                tofile=f"b/{file_path}" if file_path else "b/modified",
                lineterm="",
            )
        )
        unified = "\n".join(diff_lines)

        hunks: list[list[str]] = []
        current_hunk: list[str] = []
        for line in diff_lines:
            if line.startswith("@@"):
                if current_hunk:
                    hunks.append(current_hunk)
                current_hunk = [line]
            elif current_hunk:
                current_hunk.append(line)
        if current_hunk:
            hunks.append(current_hunk)

        stats = self._compute_stats(diff_lines, file_path)
        return Diff(
            file_path=file_path,
            hunks=hunks,
            stats=stats,
            original=original,
            modified=modified,
            unified_diff=unified,
        )

    def _compute_stats(self, diff_lines: list[str], file_path: str) -> ChangeStats:
        added = 0
        removed = 0
        for line in diff_lines:
            if line.startswith("+"):
                added += 1
            elif line.startswith("-"):
                removed += 1

        changed = min(added, removed)
        files = 1 if file_path else 0
        total_changes = added + removed

        if total_changes > 50:
            risk = RiskLevel.HIGH
        elif total_changes > 10:
            risk = RiskLevel.MEDIUM
        else:
            risk = RiskLevel.LOW

        if risk != RiskLevel.HIGH:
            for line in diff_lines:
                stripped = line.strip()
                if stripped.startswith("-") and ("def " in stripped or "class " in stripped):
                    risk = RiskLevel.HIGH
                    break

        return ChangeStats(
            lines_added=added,
            lines_removed=removed,
            lines_changed=changed,
            files_affected=files,
            risk_level=risk,
        )

    def display_diff(self, diff: Diff, title: str | None = None) -> Panel:
        header = title or f"Diff: {diff.file_path or 'unknown'}"

        stats = diff.stats
        color = {"low": "green", "medium": "yellow", "high": "red"}.get(
            stats.risk_level.value, "yellow"
        )

        stat_lines = [
            f"[bold]File:[/] {diff.file_path or 'N/A'}",
            f"[bold]Added:[/] [green]+{stats.lines_added}[/green]  "
            f"[bold]Removed:[/] [red]-{stats.lines_removed}[/red]  "
            f"[bold]Changed:[/] {stats.lines_changed}",
            f"[bold]Risk:[/] [{color}]{stats.risk_level.value.upper()}[/{color}]",
        ]

        if not diff.hunks:
            content = "\n".join(stat_lines) + "\n\n[dim]No changes — files are identical.[/dim]"
        else:
            diff_text = self._render_diff_text(diff)
            content = "\n".join(stat_lines) + "\n\n" + diff_text

        return Panel(
            content,
            title=f"📝 {header}",
            border_style=color,
        )

    def _render_diff_text(self, diff: Diff) -> str:
        rendered: list[str] = []
        for hunk in diff.hunks:
            for line in hunk:
                if line.startswith("@@"):
                    rendered.append(f"[cyan]{line}[/cyan]")
                elif line.startswith("+"):
                    rendered.append(f"[green]{line}[/green]")
                elif line.startswith("-"):
                    rendered.append(f"[red]{line}[/red]")
                elif line.startswith("\\"):
                    rendered.append(f"[dim]{line}[/dim]")
                else:
                    rendered.append(f"[dim]{line}[/dim]")
        return "\n".join(rendered)

    def format_for_approval(self, diff: Diff) -> str:
        stats = diff.stats
        lines = [
            f"File: {diff.file_path or 'N/A'}",
            f"Changes: +{stats.lines_added}/-{stats.lines_removed}",
            f"Risk: {stats.risk_level.value.upper()}",
            "",
        ]
        if diff.hunks:
            lines.append("Changes:")
            for hunk in diff.hunks:
                for line in hunk:
                    if line.startswith("+"):
                        lines.append(f"  + {line[1:]}")
                    elif line.startswith("-"):
                        lines.append(f"  - {line[1:]}")
                    elif line.startswith("@@"):
                        lines.append(f"  {line}")
        return "\n".join(lines)

    def save_diff(self, diff: Diff, path: str) -> str:
        resolved = os.path.abspath(path)
        os.makedirs(os.path.dirname(resolved), exist_ok=True)
        with open(resolved, "w") as f:
            f.write(diff.unified_diff)
        logger.info("Diff saved to %s", resolved)
        return resolved

    def get_change_stats(self, diff: Diff) -> ChangeStats:
        return diff.stats


__all__ = [
    "RiskLevel", "ChangeStats", "Diff",
    "DiffViewer",
]
