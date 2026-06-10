# ════════════════════════════════════════
# wigent — Agent Entry Point
# Role: Public API for the Wigent agent
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Main ``WigentAgent`` class.

This is the primary user-facing interface for running tasks, chatting,
switching modes/models, and inspecting agent state.

Usage
-----
    from wigent.core.agent import WigentAgent

    agent = WigentAgent()
    result = agent.run("Refactor the auth module")
    print(result["result"])

    # Chat mode (preserves conversation)
    agent.chat("What files did you change?")

    # Mode switching
    agent.set_mode("debugger")
    agent.run("Fix the login crash")

    # Model switching
    agent.set_model("anthropic", "claude-sonnet-4-20250514")
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from wigent.config import settings
from wigent.config.modes import MODES, get_mode
from wigent.core.loop import AgentLoop, AgentState
from wigent.core.orchestrator import Orchestrator
from wigent.memory import MemorySystem
from wigent.models.model_factory import factory as model_factory
from wigent.safety import SafetySystem

logger = logging.getLogger(__name__)


class WigentAgent:
    """Main agent class — entry point for all user interactions.

    Attributes
    ----------
    mode : str
        Current agent mode (``"orchestrator"``, ``"coder"``, etc.).
    messages : list[dict]
        Full conversation history (persisted across ``chat()`` calls).
    state : AgentState | None
        The state of the most recent ``run()`` invocation.
    """

    def __init__(
        self,
        mode: str | None = None,
        provider: str | None = None,
        model_name: str | None = None,
        enable_checkpoints: bool = True,
    ) -> None:
        self._mode: str = mode or settings.DEFAULT_MODE
        self._provider: str = provider or settings.DEFAULT_PROVIDER
        self._model_name: str = model_name or settings.model_name
        self._enable_checkpoints = enable_checkpoints

        self.messages: list[dict[str, Any]] = []
        self.state: AgentState | None = None
        self._session_started: str | None = None
        self._loop: AgentLoop | None = None
        self._orchestrator: Orchestrator = Orchestrator()
        self._project_context: dict[str, Any] = {}
        self._memory: MemorySystem = MemorySystem()
        self._memory.initialize()
        self._safety: SafetySystem = SafetySystem()
        self._safety.initialize()
        self._current_session_id: str | None = None

        logger.info(
            "WigentAgent initialized  mode=%s  provider=%s  model=%s",
            self._mode, self._provider, self._model_name,
        )

    # ── Public API ───────────────────────────────────────────────────

    def run(
        self,
        task: str,
        mode: str | None = None,
        max_iterations: int | None = None,
    ) -> AgentState:
        """Execute a task to completion.

        This is the primary entry point.  If ``mode`` is ``"auto"``,
        the orchestrator analyses the request and picks the best mode.

        Args:
            task:           The user's goal or instruction.
            mode:           Agent mode override (``"auto"`` for automatic
                            routing, or a specific mode name).
            max_iterations: Cap on loop iterations.

        Returns:
            The final ``AgentState`` with ``result`` and full execution
            trace.
        """
        resolved_mode = self._resolve_mode(task, mode)
        self._session_started = datetime.now(timezone.utc).isoformat()

        logger.info(
            "run  task=%s  mode=%s  provider=%s  model=%s",
            task[:80], resolved_mode, self._provider, self._model_name,
        )

        # Create a session and inject into context.
        session = self._memory.sessions.create_session(
            name=None,
            description=f"{resolved_mode}: {task[:80]}",
            tags=[resolved_mode],
        )
        self._current_session_id = session.session_id
        self._memory.context.add_message("user", task)

        # Auto-checkpoint before running.
        self._memory.checkpoints.auto_checkpoint(
            label=f"before_{resolved_mode}",
            agent_state={"mode": resolved_mode, "task": task},
        )

        model = model_factory.get_model(
            provider=self._provider,
            model_name=self._model_name,
        )

        self._loop = AgentLoop(
            model=model,
            mode=resolved_mode,
            enable_checkpoints=self._enable_checkpoints,
        )

        self.state = self._loop.run(
            task=task,
            mode=resolved_mode,
            max_iterations=max_iterations,
        )

        # Track session.
        session.total_tokens = self.state.get("token_usage", {}).get("total", 0)
        session.total_cost = self.state.get("total_cost", 0.0)
        session.files_modified = self.state.get("files_modified", [])
        session.mode_history.append(resolved_mode)
        self._memory.sessions.save_session(session)

        # Append to conversation history.
        result_text = self.state.get("result") or ""
        self._memory.context.add_message("assistant", result_text)
        self.messages.append({"role": "user", "content": task})
        if result_text:
            self.messages.append({"role": "assistant", "content": result_text})

        return self.state

    def chat(self, message: str) -> str:
        """Send a single message in conversational mode.

        Maintains a persistent message history across calls.  Use this for
        follow-up questions, clarifications, or iterative refinement.

        Args:
            message: The user's message.

        Returns:
            The assistant's text reply.
        """
        self.messages.append({"role": "user", "content": message})

        model = model_factory.get_model(
            provider=self._provider,
            model_name=self._model_name,
        )

        # Build a minimal prompt that includes conversation history.
        system_prompt = (
            f"You are Wigent, an AI coding assistant in **{self._mode}** mode. "
            f"Respond conversationally. If the user asks you to perform a task, "
            f"ask them to use `agent.run(...)` instead."
        )

        chat_messages = [{"role": "system", "content": system_prompt}] + self.messages

        from wigent.models.base_model import LLMResponse

        try:
            response: LLMResponse = model.chat(messages=chat_messages, tools=[], stream=False)
            reply = response.content or ""
        except Exception as exc:
            reply = f"Error: {exc}"
            logger.exception("Chat failed: %s", exc)

        self.messages.append({"role": "assistant", "content": reply})
        return reply

    def set_mode(self, mode: str) -> None:
        """Switch the agent's operational mode.

        Args:
            mode: One of ``"orchestrator"``, ``"architect"``, ``"coder"``,
                  ``"debugger"``, ``"reviewer"``.

        Raises:
            KeyError: If the mode name is unknown.
        """
        get_mode(mode)  # validates
        old_mode = self._mode
        self._mode = mode
        logger.info("Mode changed: %s → %s", old_mode, mode)

        # Add a system message about the mode switch.
        transition = self._orchestrator.handle_mode_switch(old_mode, mode)
        self.messages.append({"role": "system", "content": transition})

    def set_model(self, provider: str, model_name: str | None = None) -> None:
        """Hot-swap the LLM provider and/or model.

        Args:
            provider:  Provider name (``"openai"``, ``"anthropic"``, etc.).
            model_name: Specific model (e.g. ``"gpt-4o"``). Uses provider
                        default if omitted.
        """
        old_provider = self._provider
        old_model = self._model_name
        self._provider = provider
        self._model_name = model_name or model_factory._get_default_model(provider)

        model_factory.switch_model(provider, self._model_name)

        logger.info(
            "Model changed: %s/%s → %s/%s",
            old_provider, old_model, self._provider, self._model_name,
        )
        self.messages.append({
            "role": "system",
            "content": f"[MODEL SWITCH] Provider changed from {old_provider} to {provider}. "
                       f"Model: {self._model_name}.",
        })

    def get_status(self) -> dict[str, Any]:
        """Return a snapshot of the agent's current state.

        Returns:
            A dict with current mode, provider, model, conversation stats,
            memory stats, and the last run result (if any).
        """
        mem_stats = {}
        try:
            mem_stats = self._memory.context.get_stats()
        except RuntimeError:
            pass

        safety_auto = False
        try:
            safety_auto = self._safety.approvals._auto_approve
        except (RuntimeError, AttributeError):
            pass

        return {
            "mode": self._mode,
            "safety_auto_approve": safety_auto,
            "provider": self._provider,
            "model": self._model_name,
            "session_started": self._session_started,
            "session_id": self._current_session_id,
            "messages_count": len(self.messages),
            "memory_tokens": mem_stats.get("estimated_tokens", 0),
            "memory_budget_pct": mem_stats.get("budget_used_pct", 0),
            "memory_message_count": mem_stats.get("total_messages", 0),
            "last_run_status": self.state.get("status") if self.state else None,
            "last_run_iterations": self.state.get("iteration") if self.state else None,
            "last_run_cost": self.state.get("total_cost", 0.0) if self.state else 0.0,
            "last_run_result": self.state.get("result") if self.state else None,
            "files_modified": self.state.get("files_modified", []) if self.state else [],
            "errors": self.state.get("errors_encountered", []) if self.state else [],
            "project_loaded": bool(self._project_context),
        }

    def safe_write(self, file_path: str, content: str, original: str | None = None) -> bool:
        """Write a file through the safety pipeline.

        Validates the path, computes a diff, requests approval, and
        writes only if approved.
        """
        return self._safety.safe_write(file_path, content, original)

    def safe_execute(self, command: str) -> bool:
        """Check a command through the safety pipeline.

        Validates, sandbox-checks, and requests approval if needed.
        Returns True only if the command is safe to run.
        """
        return self._safety.safe_execute(command)

    def reset(self) -> None:
        """Clear the conversation history, memory, and reset agent state.

        Does **not** change the current mode, provider, or model settings.
        """
        self.messages.clear()
        self.state = None
        self._session_started = None
        self._loop = None
        self._current_session_id = None
        try:
            self._memory.context.clear()
        except RuntimeError:
            pass
        try:
            self._safety.approvals.set_auto_approve_mode(settings.AUTO_APPROVE)
        except RuntimeError:
            pass
        logger.info("Agent reset — conversation and memory cleared.")

    def load_project(self, path: str) -> dict[str, Any]:
        """Load project context from a directory.

        Reads key project files (README, pyproject.toml, etc.) to build
        context for future agent runs.

        Args:
            path: Absolute or relative path to the project directory.

        Returns:
            A dict with ``success``, ``path``, ``files_found``, and
            ``error`` (if any).
        """
        abs_path = os.path.abspath(path)
        if not os.path.isdir(abs_path):
            return {"success": False, "path": abs_path, "error": "Directory not found."}

        context: dict[str, Any] = {
            "project_path": abs_path,
            "readme": "",
            "config_files": [],
            "source_summary": "",
        }

        # Try to read README.
        for fname in ("README.md", "README.rst", "README.txt"):
            fpath = os.path.join(abs_path, fname)
            if os.path.isfile(fpath):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        context["readme"] = f.read()[:5000]
                except Exception:
                    pass
                break

        # Find config files.
        for pattern in ("pyproject.toml", "package.json", "Cargo.toml", "go.mod",
                         "Makefile", "Dockerfile", ".env.example"):
            fpath = os.path.join(abs_path, pattern)
            if os.path.isfile(fpath):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        context["config_files"].append({
                            "name": pattern,
                            "content": f.read()[:3000],
                        })
                except Exception:
                    pass

        # Summarise source tree (first 3 levels).
        context["source_summary"] = self._summarise_tree(abs_path)

        self._project_context = context
        context_msg = (
            f"[PROJECT LOADED] {abs_path}\n"
            f"README: {'yes' if context['readme'] else 'no'}\n"
            f"Config files: {len(context['config_files'])}\n"
            f"Tree: {context['source_summary'][:200]}"
        )
        self._memory.context.inject_project_context(context_msg)
        self.messages.append({"role": "system", "content": context_msg})

        logger.info("Project loaded: %s", abs_path)
        return {"success": True, "path": abs_path, "context": context}

    # ── Internals ────────────────────────────────────────────────────

    def _resolve_mode(self, task: str, mode: str | None) -> str:
        """Determine the effective mode for a task."""
        if mode is None or mode == "auto":
            return self._orchestrator.analyze_request(task)
        return mode

    @staticmethod
    def _summarise_tree(root: str, max_depth: int = 3) -> str:
        """Build a shallow directory tree string."""
        lines: list[str] = []

        def walk(dirpath: str, depth: int = 0) -> None:
            if depth > max_depth:
                return
            try:
                entries = sorted(os.listdir(dirpath))
            except PermissionError:
                return
            ignore = {".git", "__pycache__", "node_modules", ".venv", "venv",
                      ".idea", ".vscode", "build", "dist", "target"}
            for entry in entries:
                if entry.startswith(".") or entry in ignore:
                    continue
                full = os.path.join(dirpath, entry)
                indent = "  " * depth
                if os.path.isdir(full):
                    lines.append(f"{indent}{entry}/")
                    walk(full, depth + 1)
                else:
                    lines.append(f"{indent}{entry}")

        walk(root)
        return "\n".join(lines[:100])


# ── Backward-compatible aliases ────────────────────────────────────────

# The old ``Agent`` class is kept for backward compatibility.
Agent = WigentAgent


def run_agent(user_prompt: str, **kwargs: Any) -> str:
    """Convenience function — instantiate a default agent and run a task.

    This matches the original ``wigent.core.agent.run_agent()`` signature.

    Args:
        user_prompt: The task to execute.
        **kwargs:    Passed to ``WigentAgent.run()``.

    Returns:
        The result string (``state["result"]``).
    """
    agent = WigentAgent()
    state = agent.run(user_prompt, **kwargs)
    return state.get("result") or ""


__all__ = ["WigentAgent", "Agent", "run_agent"]
