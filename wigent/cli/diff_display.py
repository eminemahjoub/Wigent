from __future__ import annotations

import difflib
from typing import Any

from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from wigent.cli.ui_components import UIComponents


def _risk_border_style(risk: str) -> str:
    return {"low": "green", "medium": "yellow", "high": "red"}.get(risk.lower(), "yellow")


def _diff_stat_lines(diff_lines: list[str]) -> tuple[int, int]:
    added = sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---"))
    return added, removed


class DiffDisplay:
    def __init__(self, ui: UIComponents | None = None) -> None:
        self._ui = ui or UIComponents()

    def render_diff(self, diff: str, filename: str, risk: str = "low") -> Panel:
        added, removed = _diff_stat_lines(diff.splitlines(True))
        summary = Text.assemble(
            (f"+{added} ", "green"),
            (f"-{removed} ", "red"),
            ("│ ", "grey50"),
            (f"Risk: {risk.upper()}", _risk_border_style(risk)),
        )
        syntax = Syntax(
            diff, "diff", theme="monokai", line_numbers=True, word_wrap=True
        )
        return Panel(
            syntax,
            title=f"[bold]📄 {filename}[/bold]",
            subtitle=summary,
            border_style=_risk_border_style(risk),
            padding=(0, 1),
        )

    def render_change_summary(self, stats: dict[str, Any]) -> Table:
        table = Table(
            title="Change Summary",
            border_style="bright_blue",
            show_header=True,
            header_style="bold white",
        )
        table.add_column("File", style="bold")
        table.add_column("Added", style="green")
        table.add_column("Removed", style="red")
        table.add_column("Risk", style="yellow")

        for entry in stats.get("files", []):
            table.add_row(
                entry.get("file", ""),
                str(entry.get("added", 0)),
                str(entry.get("removed", 0)),
                entry.get("risk", "low").upper(),
            )

        total_added = sum(f.get("added", 0) for f in stats.get("files", []))
        total_removed = sum(f.get("removed", 0) for f in stats.get("files", []))
        table.add_row(
            "[bold]Total[/bold]",
            f"[bold green]+{total_added}[/bold green]",
            f"[bold red]-{total_removed}[/bold red]",
            "",
        )
        return table

    def render_side_by_side(self, original: str, modified: str, filename: str) -> Panel:
        orig_lines = original.splitlines()
        mod_lines = modified.splitlines()
        max_lines = max(len(orig_lines), len(mod_lines))
        line_num_width = len(str(max_lines))

        grid = Table.grid(padding=(0, 1, 0, 1))
        grid.add_column(style="red", width=40)
        grid.add_column(style="green", width=40)

        for i in range(max_lines):
            left = orig_lines[i] if i < len(orig_lines) else ""
            right = mod_lines[i] if i < len(mod_lines) else ""
            line_num = str(i + 1).rjust(line_num_width)
            left_changed = (i < len(orig_lines) and i >= len(mod_lines)) or \
                           (i < len(orig_lines) and i < len(mod_lines) and orig_lines[i] != mod_lines[i])
            right_changed = (i >= len(orig_lines) and i < len(mod_lines)) or \
                            (i < len(orig_lines) and i < len(mod_lines) and orig_lines[i] != mod_lines[i])
            left_prefix = "- " if left_changed else "  "
            right_prefix = "+ " if right_changed else "  "
            grid.add_row(
                f"{line_num}{left_prefix}{left}",
                f"{line_num}{right_prefix}{right}",
            )

        return Panel(
            grid,
            title=f"[bold]📄 {filename} (side by side)[/bold]",
            border_style="bright_blue",
            padding=(0, 1),
        )

    def render_unified_diff(self, diff: str) -> str:
        syntax = Syntax(diff, "diff", theme="monokai", word_wrap=True)
        return str(syntax)

    def render_inline_diff(self, text_diff: str) -> str:
        syntax = Syntax(text_diff, "diff", theme="monokai", word_wrap=True)
        return str(syntax)

    def compute_diff(self, original: str, modified: str, filename: str) -> str:
        lines = list(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                modified.splitlines(keepends=True),
                fromfile=f"a/{filename}",
                tofile=f"b/{filename}",
            )
        )
        return "".join(lines)


__all__ = ["DiffDisplay"]
