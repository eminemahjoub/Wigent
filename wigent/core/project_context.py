from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


IGNORE_TREE_DIRS = {
    ".git", "__pycache__", "node_modules", "venv", ".venv",
    ".env", "dist", "build", ".next", ".nuxt", ".turbo",
    "target", ".gradle", ".mvn", ".idea", ".vscode",
    ".agent", ".pytest_cache", ".ruff_cache", ".mypy_cache",
}

IGNORE_TREE_FILES = {
    ".DS_Store", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "poetry.lock", "*.pyc", "*.pyo",
}


class ProjectContext:
    def __init__(self) -> None:
        self._workspace_path: Path | None = None
        self._context_sources: dict[str, str] = {}
        self._file_tree: str = ""
        self._recent_commits: list[str] = []
        self._project_type: str = "unknown"
        self._language: str = "unknown"
        self._framework: str | None = None
        self._package_manager: str | None = None
        self._loaded = False

    def load_context(
        self,
        workspace_path: str | Path,
        project_type: str = "unknown",
        language: str = "unknown",
        framework: str | None = None,
        package_manager: str | None = None,
    ) -> str:
        self._workspace_path = Path(workspace_path).resolve()
        self._project_type = project_type
        self._language = language
        self._framework = framework
        self._package_manager = package_manager
        self._context_sources = {}

        rules = self.read_agent_rules()
        self._context_sources.update(rules)

        for name, path in [
            ("AGENTS.md", self._workspace_path / "AGENTS.md"),
            ("CLAUDE.md", self._workspace_path / "CLAUDE.md"),
            ("README.md", self._workspace_path / "README.md"),
        ]:
            if path.is_file() and name not in self._context_sources:
                try:
                    content = path.read_text(encoding="utf-8")[:5000]
                    if content.strip():
                        self._context_sources[name] = content
                except OSError:
                    pass

        self._file_tree = self.get_file_tree(max_depth=4)
        self._recent_commits = self.get_recent_commits(n=5)
        self._loaded = True

        return self.get_project_summary()

    def read_agent_rules(self) -> dict[str, str]:
        rules: dict[str, str] = {}
        if not self._workspace_path:
            return rules

        rules_dir = self._workspace_path / ".agent" / "rules"
        if not rules_dir.is_dir():
            return rules

        priority = ["context.md", "brief.md", "standards.md"]
        for name in priority:
            path = rules_dir / name
            if path.is_file():
                try:
                    content = path.read_text(encoding="utf-8").strip()
                    if content:
                        key = name.replace(".md", "")
                        rules[key] = content
                except OSError:
                    pass

        for path in sorted(rules_dir.iterdir()):
            if path.suffix == ".md" and path.stem not in [p.replace(".md", "") for p in priority]:
                try:
                    content = path.read_text(encoding="utf-8").strip()
                    if content:
                        rules[path.stem] = content
                except OSError:
                    pass

        return rules

    def get_project_summary(self) -> str:
        if not self._loaded or not self._workspace_path:
            return ""

        lines: list[str] = []
        lines.append("# PROJECT CONTEXT")
        lines.append("")
        lines.append("## Project Type")
        framework_str = f": {self._framework}" if self._framework else ""
        lines.append(f"{self._project_type}{framework_str}")
        lines.append(f"Language: {self._language}")
        lines.append(f"Root: {self._workspace_path}")
        if self._package_manager:
            lines.append(f"Package Manager: {self._package_manager}")
        lines.append("")

        brief = self._context_sources.get("brief", "")
        if brief:
            lines.append("## Project Brief")
            lines.append(brief)
            lines.append("")

        standards = self._context_sources.get("standards", "")
        if standards:
            lines.append("## Coding Standards")
            lines.append(standards)
            lines.append("")

        context = self._context_sources.get("context", "")
        if context:
            lines.append("## Custom Context")
            lines.append(context)
            lines.append("")

        agent_rules = [v for k, v in self._context_sources.items()
                       if k not in ("brief", "standards", "context",
                                    "AGENTS.md", "CLAUDE.md", "README.md")]
        if agent_rules:
            lines.append("## Agent Rules")
            for rule in agent_rules:
                lines.append(rule[:500])
            lines.append("")

        for name in ("AGENTS.md", "CLAUDE.md"):
            content = self._context_sources.get(name, "")
            if content:
                lines.append(f"## {name}")
                lines.append(content[:1000])
                lines.append("")

        if self._file_tree:
            lines.append("## File Structure (top 50 files)")
            lines.append(self._file_tree)
            lines.append("")

        if self._recent_commits:
            lines.append("## Recent Commits")
            lines.extend(self._recent_commits)
            lines.append("")

        lines.append("# END PROJECT CONTEXT")
        return "\n".join(lines)

    def inject_into_prompt(self, base_prompt: str) -> str:
        summary = self.get_project_summary()
        if not summary:
            return base_prompt
        return f"{base_prompt}\n\n---\n\n{summary}"

    def get_file_tree(self, max_depth: int = 4) -> str:
        if not self._workspace_path:
            return ""

        root = self._workspace_path
        lines: list[str] = []
        max_files = 50

        def walk(dirpath: Path, depth: int = 0) -> None:
            if depth > max_depth or len(lines) >= max_files:
                return
            try:
                entries = sorted(dirpath.iterdir())
            except PermissionError:
                return

            for entry in entries:
                if len(lines) >= max_files:
                    return
                name = entry.name
                if name in IGNORE_TREE_DIRS or name.startswith("."):
                    continue
                if name in IGNORE_TREE_FILES:
                    continue
                indent = "  " * depth
                if entry.is_dir():
                    lines.append(f"{indent}{name}/")
                    walk(entry, depth + 1)
                elif entry.is_file():
                    lines.append(f"{indent}{name}")

        walk(root)
        return "\n".join(lines[:50])

    def get_recent_commits(self, n: int = 5) -> list[str]:
        if not self._workspace_path:
            return []
        try:
            result = subprocess.run(
                ["git", "log", f"--max-count={n}", "--oneline", "--no-color"],
                capture_output=True, text=True, timeout=5,
                cwd=str(self._workspace_path),
            )
            if result.returncode == 0 and result.stdout.strip():
                return [f"  {line}" for line in result.stdout.strip().split("\n")]
        except (OSError, subprocess.TimeoutExpired, subprocess.SubprocessError):
            pass
        return []

    def refresh(self) -> bool:
        if not self._workspace_path:
            return False
        try:
            self.load_context(
                self._workspace_path,
                project_type=self._project_type,
                language=self._language,
                framework=self._framework,
                package_manager=self._package_manager,
            )
            return True
        except Exception as exc:
            logger.warning("Failed to refresh project context: %s", exc)
            return False


__all__ = [
    "ProjectContext",
]
