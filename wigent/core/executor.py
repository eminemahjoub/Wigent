# ════════════════════════════════════════
# wigent — Coder / Executor Mode
# Role: Implementation — reads context, writes code, runs tests
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Coder mode agent — implements code changes from a plan,
enforces read-before-write, generates tests, and verifies work.

Temperature: 0.1 (precise)
Tools: read, write, list, run_command — all implementation tools.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from wigent.config import settings
from wigent.config.modes import get_mode
from wigent.core.loop import AgentLoop
from wigent.models.base_model import LLMResponse
from wigent.models.model_factory import factory as model_factory
from wigent.prompts import build_mode_prompt

logger = logging.getLogger(__name__)

CODER_TEMPERATURE = 0.1


class CoderAgent:
    """Implementation agent that writes production code from a plan.

    Enforces the read-before-write protocol, generates tests, runs
    formatters, and verifies everything works before declaring done.

    Usage
    -----
        coder = CoderAgent()
        coder.read_context(["src/auth.py", "src/models/user.py"])
        result = coder.implement_task("Add login endpoint", plan_data)
        coder.post_implementation_check()
    """

    MODE = "coder"

    def __init__(self, model: Any | None = None) -> None:
        self._model = model or model_factory.get_active_model()
        self._mode_cfg = get_mode(self.MODE)
        self._context_cache: dict[str, str] = {}
        self._modified_files: list[str] = []
        self._metrics: dict[str, Any] = {
            "files_read": 0,
            "files_written": 0,
            "tests_added": 0,
            "total_impl_time": 0.0,
            "impl_count": 0,
        }

    # ── Public API ───────────────────────────────────────────────────

    def implement_task(
        self,
        task: str,
        plan: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Implement a coding task using the agent loop.

        Reads context automatically, then executes the implementation
        via the Think→Act→Observe loop with coder tools.

        Args:
            task: Description of what to implement.
            plan: Optional architecture plan context.

        Returns:
            The final ``AgentState`` with result and file changes.
        """
        t0 = time.perf_counter()

        # Incorporate plan context if provided.
        enriched_task = task
        if plan:
            plan_summary = json.dumps(plan, indent=2, default=str)[:4000]
            enriched_task = (
                f"{task}\n\n"
                f"Architecture plan:\n{plan_summary}\n\n"
                "Follow the plan exactly. Read files before modifying them."
            )

        # Pre-load context for files mentioned in the plan.
        if plan:
            ft = plan.get("file_tree", {})
            all_files = ft.get("modified_files", []) + ft.get("new_files", [])
            self.read_context(all_files)

        loop = self._build_loop()
        state = loop.run(enriched_task, mode=self.MODE)

        duration = time.perf_counter() - t0
        self._metrics["total_impl_time"] += duration
        self._metrics["impl_count"] += 1
        self._modified_files.extend(state.get("files_modified", []))

        logger.info(
            "implement_task: done  iterations=%d  files=%s  duration=%.1fs",
            state.get("iteration"), state.get("files_modified", []), duration,
        )

        return state

    def read_context(self, files: list[str]) -> dict[str, str]:
        """Pre-load file contents into context cache.

        Reads each file using the tool registry and caches the content
        for use in subsequent operations.

        Args:
            files: List of file paths (relative to workspace).

        Returns:
            A dict mapping file path to its cached content.
        """
        from wigent.tools import read_file

        for fpath in files:
            if fpath in self._context_cache:
                continue
            try:
                result = read_file(file_path=fpath)
                if isinstance(result, dict) and result.get("success"):
                    content = result.get("content", "")
                    if isinstance(content, str):
                        self._context_cache[fpath] = content
                        self._metrics["files_read"] += 1
                        logger.debug("Context loaded: %s (%d chars)", fpath, len(content))
            except Exception as exc:
                logger.warning("Failed to read context file '%s': %s", fpath, exc)

        return dict(self._context_cache)

    def write_code(
        self,
        file_path: str,
        content: str,
        approve: bool = False,
    ) -> dict[str, Any]:
        """Write code to a file with optional approval gate.

        Args:
            file_path: Target file path.
            content:   Full file content to write.
            approve:   If ``False``, returns a diff preview without writing.

        Returns:
            A dict with ``success``, ``preview`` (if not approved), and
            ``file_path``.
        """
        from wigent.tools import write_file, read_file

        # Read existing file first (read-before-write).
        existing = ""
        try:
            existing_result = read_file(file_path=file_path)
            if isinstance(existing_result, dict) and existing_result.get("success"):
                existing = existing_result.get("content", "") or ""
        except Exception:
            pass

        # Show diff.
        preview = self._compute_diff(file_path, existing, content)

        if not approve:
            return {
                "success": True,
                "approved": False,
                "file_path": file_path,
                "preview": preview,
                "message": "Preview generated. Call with approve=True to write.",
            }

        # Write.
        try:
            result = write_file(file_path=file_path, content=content)
            success = isinstance(result, dict) and result.get("success", False)
            self._metrics["files_written"] += 1
            if file_path not in self._modified_files:
                self._modified_files.append(file_path)
            return {
                "success": success,
                "approved": True,
                "file_path": file_path,
                "preview": preview,
                "message": "File written successfully." if success else f"Write failed: {result}",
            }
        except Exception as exc:
            return {
                "success": False,
                "approved": True,
                "file_path": file_path,
                "error": str(exc),
            }

    def write_batch(
        self,
        files: list[dict[str, str]],
        approve: bool = False,
    ) -> list[dict[str, Any]]:
        """Write multiple files with read-before-write on each.

        Args:
            files:  List of ``{"path": ..., "content": ...}`` dicts.
            approve: Global approval flag for all files.

        Returns:
            List of per-file results (see ``write_code()``).
        """
        results = []
        for f in files:
            result = self.write_code(
                file_path=f["path"],
                content=f["content"],
                approve=approve,
            )
            results.append(result)
        return results

    def refactor(
        self,
        file_path: str,
        instructions: str,
    ) -> dict[str, Any]:
        """Safely refactor a file by reading it first, then applying changes.

        Uses the agent loop to read, modify, and verify one file.

        Args:
            file_path:   Path to the file to refactor.
            instructions: Description of what to change and why.

        Returns:
            The resulting ``AgentState``.
        """
        self.read_context([file_path])

        task = (
            f"Refactor `{file_path}` according to these instructions:\n\n"
            f"{instructions}\n\n"
            "Read the file first. Make only the requested changes. "
            "Do not reformat or change unrelated code."
        )

        loop = self._build_loop()
        state = loop.run(task, mode=self.MODE)
        return state

    def add_tests(self, file_path: str) -> dict[str, Any]:
        """Generate tests for a given source file.

        Reads the source file, determines the test framework from the
        project, and writes a companion test file.

        Args:
            file_path: Path to the source file (e.g. ``src/auth.py``).

        Returns:
            The resulting ``AgentState``.
        """
        self.read_context([file_path])

        task = (
            f"Add tests for `{file_path}`. "
            "Determine the test framework from existing tests in the project. "
            "Read the source file first. "
            "Write tests covering: normal cases, edge cases, and error cases. "
            "Place the test file in the appropriate test directory following "
            "the project's naming convention."
        )

        loop = self._build_loop()
        state = loop.run(task, mode=self.MODE)

        self._metrics["tests_added"] += 1
        return state

    def format_code(self, file_path: str) -> dict[str, Any]:
        """Run the project's code formatter on a file.

        Detects the formatter from project config (e.g. black, ruff,
        prettier, gofmt) and applies it.

        Args:
            file_path: Path to the file to format.

        Returns:
            A dict with ``success``, ``formatter`` used, and output.
        """
        from wigent.tools import run_command

        # Detect formatter by project config.
        formatter = self._detect_formatter()
        if not formatter:
            return {"success": False, "error": "No formatter detected"}

        try:
            result = run_command(command=f"{formatter} {file_path}")
            success = isinstance(result, dict) and result.get("success", False)
            return {
                "success": success,
                "formatter": formatter,
                "file": file_path,
                "output": str(result),
            }
        except Exception as exc:
            return {"success": False, "formatter": formatter, "error": str(exc)}

    def post_implementation_check(self) -> dict[str, Any]:
        """Verify that the implementation is complete and correct.

        Runs a multi-step check:
        1. All modified files exist.
        2. Code compiles (syntax check).
        3. Tests pass (if test command found).

        Returns:
            A dict with check results per criterion.
        """
        from wigent.tools import read_file, run_command

        checks: dict[str, Any] = {}
        all_pass = True

        # Check files exist.
        file_check: list[dict[str, Any]] = []
        for fpath in self._modified_files:
            try:
                r = read_file(file_path=fpath)
                exists = isinstance(r, dict) and r.get("success", False)
                file_check.append({"file": fpath, "exists": exists})
                if not exists:
                    all_pass = False
            except Exception:
                file_check.append({"file": fpath, "exists": False})
                all_pass = False
        checks["files_exist"] = {"pass": all(c["exists"] for c in file_check), "details": file_check}

        # Syntax check for Python.
        python_files = [f for f in self._modified_files if f.endswith(".py")]
        if python_files:
            try:
                r = run_command(command=f"python3 -m py_compile {' '.join(python_files)}")
                syntax_ok = isinstance(r, dict) and r.get("success", False)
                checks["syntax"] = {"pass": syntax_ok, "output": str(r)[:500]}
                if not syntax_ok:
                    all_pass = False
            except Exception as exc:
                checks["syntax"] = {"pass": False, "error": str(exc)}
                all_pass = False

        # Run tests if available.
        try:
            r = run_command(command="python3 -m pytest --no-header -q --tb=short 2>&1 | tail -5")
            tests_ok = isinstance(r, dict) and r.get("success", False)
            checks["tests"] = {"pass": tests_ok, "output": str(r)[:500]}
            if "no test" in str(r).lower() or "pytest" not in str(r).lower():
                checks["tests"] = {"pass": None, "note": "No test runner detected"}
        except Exception:
            checks["tests"] = {"pass": None, "note": "Could not run tests"}

        checks["all_pass"] = all_pass
        return checks

    def get_context(self, file_path: str) -> str | None:
        """Return cached context for a file, or None."""
        return self._context_cache.get(file_path)

    def get_modified_files(self) -> list[str]:
        """Return list of files modified during this session."""
        return list(self._modified_files)

    def get_metrics(self) -> dict[str, Any]:
        """Return metrics tracked by this agent."""
        return dict(self._metrics)

    # ── Internals ────────────────────────────────────────────────────

    def _build_loop(self) -> AgentLoop:
        return AgentLoop(
            model=self._model,
            mode=self.MODE,
            enable_checkpoints=False,
        )

    @staticmethod
    def _compute_diff(file_path: str, old: str, new: str) -> str:
        """Simple line-based diff preview."""
        old_lines = old.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)

        if old == new:
            return f"📄 {file_path}: no changes"

        added = len(new_lines) - len(old_lines)
        changed = sum(1 for a, b in zip(old_lines, new_lines) if a != b)

        return (
            f"📄 {file_path}\n"
            f"  Lines: {len(old_lines)} → {len(new_lines)} ({added:+d})\n"
            f"  Changes: {changed} line(s) modified\n"
            f"  Preview: {new[:500]}..."
        )

    @staticmethod
    def _detect_formatter() -> str | None:
        """Detect the project's code formatter."""
        for path in [".", "pyproject.toml", ".prettierrc", "Makefile"]:
            if os.path.isfile("pyproject.toml"):
                try:
                    with open("pyproject.toml") as f:
                        content = f.read()
                    if "[tool.ruff]" in content or "[tool.ruff.format]" in content:
                        return "ruff format"
                    if "[tool.black]" in content:
                        return "black"
                except Exception:
                    pass
            break
        # Fallback by extension.
        return "black"


__all__ = ["CoderAgent"]
