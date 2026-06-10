from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from typing import Any, Generator

from rich.align import Align
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.rule import Rule
from rich.spinner import Spinner
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

logger = logging.getLogger(__name__)

STATUS_EMOJI_MAP: dict[str, str] = {
    "thinking": "💭",
    "writing": "✍",
    "reading": "📖",
    "searching": "🔎",
    "executing": "⚡",
    "done": "✅",
    "error": "❌",
    "warning": "⚠️",
    "info": "ℹ️",
    "tool": "🔧",
    "code": "📝",
    "approve": "🛡️",
}


class UIComponents:
    AGENT_COLOR = "cyan"
    USER_COLOR = "white"
    SUCCESS_COLOR = "green"
    ERROR_COLOR = "red"
    WARNING_COLOR = "yellow"
    THINKING_COLOR = "blue"
    TOOL_COLOR = "magenta"
    DIM_COLOR = "grey50"
    BORDER_COLOR = "bright_blue"
    HIGHLIGHT_COLOR = "bright_cyan"

    MODE_EMOJIS: dict[str, str] = {
        "orchestrator": "🎯",
        "architect": "📐",
        "coder": "💻",
        "debugger": "🔧",
        "reviewer": "🔍",
    }

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console(highlight=False)

    # ── Banner ─────────────────────────────────────────────────────────

    def print_banner(self, version: str, model: str, mode: str) -> None:
        logo_lines = [
            "██╗    ██╗██╗ ██████╗ ███████╗███╗     ████████╗",
            "██║    ██║██║██╔════╝ ██╔════╝████╗       ██╔══╝",
            "██║ █╗ ██║██║██║  ███╗█████╗  ██╔██╗      ██║   ",
            "██║███╗██║██║██║   ██║██╔══╝  ██║╚██╗     ██║   ",
            "╚███╔███╔╝██║╚██████╔╝███████╗██║ ╚██╗    ██║   ",
            " ╚══╝╚══╝ ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝    ╚═╝   ",
        ]
        mode_emoji = self.MODE_EMOJIS.get(mode, "🤖")
        logo_text = Text("\n".join(logo_lines), style=self.AGENT_COLOR, no_wrap=True)

        info = Text.assemble(
            (f"  {mode_emoji} ", self.AGENT_COLOR),
            ("AI Coding Agent ", "bold white"),
            (f"v{version}", self.DIM_COLOR),
            "\n",
            (f"  {model}", self.HIGHLIGHT_COLOR),
            ("  │  ", self.DIM_COLOR),
            (mode.title(), self.WARNING_COLOR),
            ("  │  Ready", self.SUCCESS_COLOR),
        )

        self.console.print(
            Panel(
                Group(Align(logo_text, "center"), Align(info, "center")),
                border_style=self.BORDER_COLOR,
                padding=(1, 2),
                subtitle=f"v{version}",
                subtitle_align="right",
            )
        )

    # ── Messages ───────────────────────────────────────────────────────

    def print_user_message(self, message: str) -> None:
        panel = Panel(
            Markdown(message.strip()),
            title="[bold white]You[/bold white]",
            title_align="left",
            border_style=self.USER_COLOR,
            padding=(1, 2),
        )
        self.console.print(panel)

    def print_agent_message(self, message: str, mode: str) -> None:
        mode_emoji = self.MODE_EMOJIS.get(mode, "🤖")
        title = Text.assemble(
            (f"{mode_emoji} ", self.AGENT_COLOR),
            (f"Wigent ({mode.title()})", f"bold {self.AGENT_COLOR}"),
        )
        panel = Panel(
            Markdown(message.strip()),
            title=title,
            title_align="left",
            border_style=self.AGENT_COLOR,
            padding=(1, 2),
        )
        self.console.print(panel)

    # ── Spinner ────────────────────────────────────────────────────────

    @contextmanager
    def thinking_spinner(self, text: str = "Thinking...") -> Generator:
        spinner = Spinner("dots", text=f"[{self.THINKING_COLOR}]{text}[/{self.THINKING_COLOR}]")
        with self.console.status(spinner):
            yield

    # ── Tool calls ─────────────────────────────────────────────────────

    def print_tool_use(self, tool_name: str, params: dict[str, Any]) -> None:
        param_preview = ", ".join(
            f"{k}={str(v)[:60]}" for k, v in params.items()
        )[:120]
        text = Text.assemble(
            (f"🔧 {tool_name} ", f"bold {self.TOOL_COLOR}"),
            (f"({param_preview})", self.DIM_COLOR),
        )
        self.console.print(Panel(text, border_style=self.TOOL_COLOR, padding=(0, 1)))

    def print_tool_result(self, tool: str, result: Any, success: bool) -> None:
        emoji = "✅" if success else "❌"
        color = self.SUCCESS_COLOR if success else self.ERROR_COLOR
        preview = str(result)[:200] if result else "(no output)"
        text = Text.assemble(
            (f"{emoji} {tool} ", f"bold {color}"),
            (f"— {preview}", self.DIM_COLOR),
        )
        self.console.print(text)

    # ── Diff ───────────────────────────────────────────────────────────

    def print_diff(self, original: str, modified: str, filename: str) -> None:
        import difflib
        diff_lines = list(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                modified.splitlines(keepends=True),
                fromfile=f"a/{filename}",
                tofile=f"b/{filename}",
            )
        )
        diff_text = "".join(diff_lines)
        if diff_text.strip():
            syntax = Syntax(
                diff_text, "diff", theme="monokai", line_numbers=True, word_wrap=True
            )
            added = sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++"))
            removed = sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---"))
            summary = Text.assemble(
                (f"  +{added} ", self.SUCCESS_COLOR),
                (f"-{removed}", self.ERROR_COLOR),
            )
            panel = Panel(
                syntax,
                title=f"[bold]📄 {filename}[/bold]",
                subtitle=summary,
                border_style=self.BORDER_COLOR,
                padding=(0, 1),
            )
            self.console.print(panel)
        else:
            self.console.print(f"[dim]No changes to {filename}[/dim]")

    # ── Approval ───────────────────────────────────────────────────────

    def print_approval_request(self, action: str, details: str, risk: str) -> None:
        risk_color = {"low": "green", "medium": "yellow", "high": "red"}.get(
            risk.lower(), "yellow"
        )
        panel = Panel(
            Group(
                Text(f"Action: {action}", style="bold white"),
                Text(""),
                Text(details, style=self.DIM_COLOR),
            ),
            title=f"[bold {risk_color}]🛡️ Approval Required ({risk.upper()} risk)[/bold {risk_color}]",
            border_style=risk_color,
            padding=(1, 2),
        )
        self.console.print(panel)

    # ── Error ──────────────────────────────────────────────────────────

    def print_error(self, error: str, hint: str | None = None, recoverable: bool = False) -> None:
        lines: list[Text] = [Text(f"❌ {error}", style=f"bold {self.ERROR_COLOR}")]
        if hint:
            lines.append(Text(f"💡 {hint}", style=self.DIM_COLOR))
        if not recoverable:
            lines.append(Text("This error is not recoverable.", style=self.DIM_COLOR))
        panel = Panel(
            Group(*lines),
            title="[bold red]Error[/bold red]",
            border_style=self.ERROR_COLOR,
            padding=(1, 2),
        )
        self.console.print(panel)

    # ── Status bar ─────────────────────────────────────────────────────

    def print_status_bar(self, state: dict[str, Any]) -> None:
        mode = state.get("mode", "unknown")
        model = state.get("model", "unknown")
        mode_emoji = self.MODE_EMOJIS.get(mode, "🤖")
        tokens = state.get("tokens_used", 0)
        max_tokens = state.get("tokens_max", 200_000)
        cost = state.get("cost", 0.0)
        pct = f"{int(tokens / max_tokens * 100) if max_tokens else 0}%"

        bar_width = 20
        filled = int(bar_width * tokens / max_tokens) if max_tokens else 0
        bar = "█" * min(filled, bar_width) + "░" * max(bar_width - min(filled, bar_width), 0)

        text = Text.assemble(
            (f" {mode_emoji} ", self.AGENT_COLOR),
            (f"{mode.title():12}", self.AGENT_COLOR),
            (" │ ", self.DIM_COLOR),
            (f"🤖 {model:20}", self.HIGHLIGHT_COLOR),
            (" │ ", self.DIM_COLOR),
            (f"💰 ${cost:.4f}", self.WARNING_COLOR),
            (" │ ", self.DIM_COLOR),
            (f"📊 {bar} {pct}", "bold white"),
        )
        self.console.print(
            Panel(text, border_style=self.DIM_COLOR, padding=(0, 1))
        )

    # ── Plan ───────────────────────────────────────────────────────────

    def print_plan(self, plan_dict: dict[str, Any]) -> None:
        tree = Tree(f"[bold]{plan_dict.get('goal', 'Plan')}[/bold]")
        steps = plan_dict.get("steps", [])
        for i, step in enumerate(steps, 1):
            branch = tree.add(f"[bold cyan]Step {i}[/bold cyan]: {step.get('action', '')}")
            details = step.get("details", "")
            if details:
                branch.add(f"[dim]{details}[/dim]")

        self.console.print(
            Panel(tree, title="[bold]📋 Execution Plan[/bold]", border_style=self.BORDER_COLOR)
        )

    # ── Code ──────────────────────────────────────────────────────────

    def print_code(self, code: str, language: str, filename: str | None = None) -> None:
        syntax = Syntax(code, language, theme="monokai", line_numbers=True, word_wrap=True)
        title = f"[bold]📝 {filename}[/bold]" if filename else "[bold]Code[/bold]"
        self.console.print(Panel(syntax, title=title, border_style=self.BORDER_COLOR))

    # ── Mode switch ────────────────────────────────────────────────────

    def print_mode_switch(self, from_mode: str, to_mode: str) -> None:
        from_emoji = self.MODE_EMOJIS.get(from_mode, "🤖")
        to_emoji = self.MODE_EMOJIS.get(to_mode, "🤖")
        self.console.print(
            Panel(
                Text.assemble(
                    (f"{from_emoji} {from_mode.title()} ", self.DIM_COLOR),
                    ("→ ", "bold white"),
                    (f"{to_emoji} {to_mode.title()}", f"bold {self.AGENT_COLOR}"),
                ),
                title="[bold]🔄 Mode Switch[/bold]",
                border_style=self.WARNING_COLOR,
                padding=(0, 1),
            )
        )

    # ── Session info ───────────────────────────────────────────────────

    def print_session_info(self, session: dict[str, Any]) -> None:
        grid = Table.grid(padding=(0, 2))
        grid.add_column(style="bold")
        grid.add_column()

        for key, value in session.items():
            label = key.replace("_", " ").title()
            grid.add_row(f"{label}:", str(value))

        self.console.print(
            Panel(grid, title="[bold]📋 Session Info[/bold]", border_style=self.BORDER_COLOR)
        )

    # ── Help ──────────────────────────────────────────────────────────

    def print_help(self, commands: list[dict[str, str]]) -> None:
        table = Table(
            title="[bold]Commands[/bold]",
            border_style=self.BORDER_COLOR,
            show_header=True,
            header_style="bold white",
        )
        table.add_column("Command", style=self.HIGHLIGHT_COLOR)
        table.add_column("Description", style="white")
        table.add_column("Usage", style=self.DIM_COLOR)

        for cmd in commands:
            table.add_row(
                cmd.get("name", ""),
                cmd.get("description", ""),
                cmd.get("usage", ""),
            )

        self.console.print(
            Panel(
                table,
                title="[bold]📖 Help[/bold]",
                border_style=self.BORDER_COLOR,
                padding=(1, 2),
            )
        )

    # ── Workspace banner ───────────────────────────────────────────────

    def print_workspace_banner(self, info: dict[str, Any]) -> None:
        if not info or info.get("project_type", "unknown") == "unknown":
            self.console.print(
                Panel(
                    "[yellow]No project detected. Working in current directory.[/yellow]",
                    title="📁 Workspace",
                    border_style="yellow",
                )
            )
            return

        ptype = info.get("project_type", "unknown")
        framework = info.get("framework")
        lang = info.get("language", "unknown")
        pm = info.get("package_manager")
        has_git = info.get("has_git", False)

        type_str = f"{ptype}" + (f" ({framework})" if framework else "")
        type_color = "cyan" if ptype != "unknown" else "yellow"
        lang_color = "green" if lang != "unknown" else "white"

        grid = Table.grid(padding=(0, 2))
        grid.add_column(style="bold")
        grid.add_column()

        grid.add_row(
            "📁 Project",
            f"[bright_cyan]{os.path.basename(info.get('path', ''))}[/bright_cyan]",
        )
        grid.add_row("⚡ Type", f"[{type_color}]{type_str}[/{type_color}]")
        grid.add_row("🔤 Language", f"[{lang_color}]{lang}[/{lang_color}]")
        grid.add_row("📦 Package Manager", pm or "[dim]none[/dim]")

        if has_git:
            git_color = "green"
            git_status = "✓ git repository"
            try:
                result = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    capture_output=True, text=True, timeout=3,
                    cwd=info.get("path", ""),
                )
                if result.returncode == 0:
                    branch = result.stdout.strip()
                    dirty = subprocess.run(
                        ["git", "status", "--porcelain"],
                        capture_output=True, text=True, timeout=3,
                        cwd=info.get("path", ""),
                    )
                    dirty_flag = " [+dirty]" if dirty.stdout.strip() else ""
                    git_status = f"🌿 {branch}{dirty_flag}"
                    git_color = "red" if dirty.stdout.strip() else "green"
            except Exception:
                pass
            grid.add_row("🌿 Git", f"[{git_color}]{git_status}[/{git_color}]")
        else:
            grid.add_row("🌿 Git", "[dim]no repo[/dim]")

        if info.get("has_tests"):
            grid.add_row("🧪 Tests", "[green]detected[/green]")
        if info.get("has_docker"):
            grid.add_row("🐳 Docker", "[blue]detected[/blue]")

        context_status = "loaded" if info.get("context_loaded") else "none"
        grid.add_row("📚 Context", f"[{'green' if context_status == 'loaded' else 'dim'}]{context_status}[/]")

        self.console.print(
            Panel(grid, title="📁 Workspace Loaded", border_style="bright_blue")
        )

    # ── Cost summary ───────────────────────────────────────────────────

    def print_cost_summary(self, cost_data: dict[str, Any]) -> None:
        table = Table(border_style=self.BORDER_COLOR, show_header=True, header_style="bold white")
        table.add_column("Metric", style="bold")
        table.add_column("Value")

        for key, value in cost_data.items():
            label = key.replace("_", " ").title()
            if isinstance(value, float):
                formatted = f"${value:.6f}"
            else:
                formatted = str(value)
            table.add_row(label, formatted)

        self.console.print(
            Panel(table, title="[bold]💰 Cost Summary[/bold]", border_style=self.WARNING_COLOR)
        )

    # ── Command result ─────────────────────────────────────────────────

    def print_command_result(self, result: dict[str, Any]) -> None:
        status = result.get("status", "ok")
        message = result.get("message", "")
        data = result.get("data")

        color = self.SUCCESS_COLOR if status == "ok" else self.ERROR_COLOR

        panel = Panel(
            Markdown(message.strip()) if message else Text("(no output)"),
            title=f"[bold {color}]Result[/bold {color}]",
            border_style=color,
            padding=(1, 2),
        )
        self.console.print(panel)

        if data and isinstance(data, dict):
            grid = Table.grid(padding=(0, 2))
            grid.add_column(style="bold")
            grid.add_column()
            for k, v in data.items():
                grid.add_row(str(k), str(v))
            self.console.print(grid)

    # ── Interrupt ──────────────────────────────────────────────────────

    def print_interrupt_message(self) -> None:
        self.console.print(
            Panel(
                "[yellow]Task interrupted by user.[/yellow]",
                title="[bold]⏹️ Interrupted[/bold]",
                border_style=self.WARNING_COLOR,
            )
        )

    # ── Progress ───────────────────────────────────────────────────────

    @contextmanager
    def progress_bar(self, description: str = "Working...", total: int = 100) -> Generator:
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=self.console,
        )
        task_id = progress.add_task(description, total=total)
        with progress:
            yield lambda advance=1: progress.update(task_id, advance=advance)

    # ── Search results ─────────────────────────────────────────────────

    def print_search_results(self, results: list[dict[str, Any]]) -> None:
        table = Table(border_style=self.BORDER_COLOR, show_header=True, header_style="bold white")
        table.add_column("#", style=self.DIM_COLOR)
        table.add_column("File", style=self.HIGHLIGHT_COLOR)
        table.add_column("Snippet", style="white")
        table.add_column("Score", style=self.SUCCESS_COLOR)

        for i, r in enumerate(results, 1):
            table.add_row(
                str(i),
                r.get("file", ""),
                r.get("snippet", "")[:80],
                f"{r.get('score', 0):.2f}",
            )

        self.console.print(
            Panel(table, title="[bold]🔎 Search Results[/bold]", border_style=self.BORDER_COLOR)
        )

    # ── Divider ───────────────────────────────────────────────────────

    def print_divider(self, text: str = "") -> None:
        self.console.print(Rule(text, style=self.DIM_COLOR))


__all__ = ["UIComponents"]
