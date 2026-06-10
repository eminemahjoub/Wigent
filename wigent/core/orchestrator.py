# ════════════════════════════════════════
# wigent — Orchestrator
# Role: Mode router — analyses tasks, routes agents, coordinates modes
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Intelligent mode routing for multi-agent task orchestration.

The ``Orchestrator`` analyses a user's task, selects the best agent mode
(or sequence of modes), and manages transitions between them.

Modes
-----
- ``orchestrator`` — full autonomy: plans, codes, tests, iterates.
- ``architect``    — reads codebase, designs architecture, produces a plan.
- ``coder``        — writes code, runs tests, fixes errors.
- ``debugger``     — reads errors, finds root cause, applies fixes.
- ``reviewer``     — reads files, finds issues, suggests improvements.

Usage
-----
    orchestrator = Orchestrator()
    mode = orchestrator.analyze_request("Fix the login bug")
    # → "debugger"

    plan = orchestrator.route("Add user authentication")
    # → {"mode": "architect", "subtasks": [...]}
"""

from __future__ import annotations

import json
import logging
from typing import Any

from wigent.config.modes import MODES, AgentModeConfig, get_mode, list_modes
from wigent.models.base_model import LLMResponse
from wigent.models.model_factory import factory as model_factory
from wigent.prompts import build_mode_prompt

logger = logging.getLogger(__name__)

# ── Task classification keywords ──────────────────────────────────────

_MODE_SIGNALS: dict[str, list[str]] = {
    "orchestrator": [
        "full stack", "complete", "from scratch", "build", "create project",
        "implement feature", "end to end", "comprehensive", "multi-step",
        "complex", "large", "significant",
    ],
    "architect": [
        "design", "architecture", "plan", "how should", "structure",
        "blueprint", "proposal", "diagram", "organise", "organize",
        "component", "module", "system design",
    ],
    "coder": [
        "implement", "code", "write", "program", "function", "method",
        "class", "unit test", "add feature", "module", "script",
    ],
    "debugger": [
        "bug", "fix", "error", "crash", "exception", "fail", "broken",
        "issue", "problem", "not working", "unexpected", "wrong",
        "incorrect", "regression",
    ],
    "reviewer": [
        "review", "audit", "inspect", "quality", "style", "convention",
        "refactor", "improve", "optimise", "optimize", "feedback",
        "code smell", "best practice",
    ],
}


class Orchestrator:
    """Routes tasks to the appropriate agent mode(s) and coordinates execution.

    Attributes
    ----------
    _mode_chain : list[str]
        When running multi-step plans, records the sequence of modes used.
    _results : dict[str, Any]
        Stores the result of each completed mode in a multi-step execution.
    """

    def __init__(self) -> None:
        self._mode_chain: list[str] = []
        self._results: dict[str, Any] = {}

    # ── Public API ───────────────────────────────────────────────────

    def analyze_request(self, task: str) -> str:
        """Analyse a user's task string and suggest the best agent mode.

        Uses keyword matching first, then falls back to an LLM call if
        the keywords are ambiguous.

        Args:
            task: The user's raw task description.

        Returns:
            One of ``"orchestrator"``, ``"architect"``, ``"coder"``,
            ``"debugger"``, ``"reviewer"``.
        """
        task_lower = task.lower()

        # Score by keyword matches.
        scores: dict[str, int] = {}
        for mode, signals in _MODE_SIGNALS.items():
            scores[mode] = sum(1 for s in signals if s in task_lower)

        # If one mode clearly dominates, return it.
        if scores:
            best = max(scores, key=scores.get)
            if scores[best] >= 2:
                logger.info(
                    "analyze_request: keyword match → %s  (score=%d)",
                    best, scores[best],
                )
                return best

        # Ambiguous — ask the LLM.
        return self._llm_classify(task, scores)

    def route(self, task: str, preferred_mode: str | None = None) -> dict[str, Any]:
        """Analyse a task and produce an execution plan.

        Returns a structured plan with the chosen mode, subtasks (if
        applicable), and any context the agent will need.

        Args:
            task:            The user's goal description.
            preferred_mode:  Optional mode override.

        Returns:
            A dict with keys: ``mode``, ``subtasks``, ``context``.
        """
        mode = preferred_mode or self.analyze_request(task)

        # For complex tasks, optionally break into subtasks via LLM.
        subtasks = self._decompose_task(task, mode) if mode == "orchestrator" else []

        plan: dict[str, Any] = {
            "mode": mode,
            "subtasks": subtasks,
            "context": {
                "mode_description": get_mode(mode).description,
                "allowed_tools": list(get_mode(mode).allowed_tools),
                "max_iterations": get_mode(mode).max_iterations,
            },
        }

        logger.info("route: task=%s  mode=%s  subtasks=%d", task[:60], mode, len(subtasks))
        return plan

    def coordinate_modes(self, plan: dict[str, Any]) -> Any:
        """Execute a multi-mode plan sequentially.

        Each entry in ``plan["subtasks"]`` can specify a different mode.
        Results are accumulated and passed as context to subsequent steps.

        Args:
            plan: A plan dict from ``route()`` — must contain at least
                  a ``mode`` key.

        Returns:
            The final result after all modes have run, or the result
            of a single-mode execution.
        """
        subtasks = plan.get("subtasks", [])

        if not subtasks:
            # Single-mode execution.
            from wigent.core.loop import AgentLoop
            mode = plan.get("mode", "orchestrator")
            loop = AgentLoop(mode=mode)
            context = plan.get("context", {})
            task = context.get("task_description", plan.get("mode", ""))
            result = loop.run(task, mode=mode)
            self._results[mode] = result
            self._mode_chain = [mode]
            return result

        # Multi-mode: run each subtask in order, passing accumulated context.
        accumulated_context: dict[str, Any] = {}
        final_result = None

        for i, subtask in enumerate(subtasks):
            mode = subtask.get("mode", "coder")
            description = subtask.get("description", "")
            enriched_task = self._build_subtask_prompt(subtask, accumulated_context)

            from wigent.core.loop import AgentLoop
            loop = AgentLoop(mode=mode)
            result = loop.run(enriched_task, mode=mode)

            self._results[f"{mode}_{i}"] = result
            self._mode_chain.append(mode)

            accumulated_context[f"step_{i}_result"] = result.get("result", "")
            accumulated_context[f"step_{i}_files"] = result.get("files_modified", [])
            final_result = result

        return final_result

    def handle_mode_switch(self, from_mode: str, to_mode: str) -> str:
        """Prepare a transition message when switching agent modes.

        Returns a system-prompt fragment that tells the LLM about the
        mode change and any context that should carry over.

        Args:
            from_mode: The previous mode name.
            to_mode:   The new mode name.

        Returns:
            A string to inject into the message history.
        """
        from_cfg = get_mode(from_mode)
        to_cfg = get_mode(to_mode)

        transition = (
            f"[MODE SWITCH] You have switched from **{from_cfg.emoji} {from_cfg.name}** "
            f"to **{to_cfg.emoji} {to_cfg.name}**.\n\n"
            f"{to_cfg.description}\n\n"
            f"Your available tools are now:\n"
            + "\n".join(f"  - `{t}`" for t in to_cfg.allowed_tools)
        )

        logger.info("mode switch: %s → %s", from_mode, to_mode)
        return transition

    def track_overall_progress(self) -> dict[str, Any]:
        """Return a status report of all modes executed so far.

        Returns:
            A dict with ``mode_chain``, ``results``, and a summary.
        """
        return {
            "mode_chain": self._mode_chain,
            "results": self._results,
            "summary": self._build_summary(),
        }

    # ── Internals ────────────────────────────────────────────────────

    def _llm_classify(self, task: str, keyword_scores: dict[str, int]) -> str:
        """Ask the LLM to classify the task into a mode."""
        modes_json = json.dumps([
            {"mode": name, "description": cfg.description, "keywords": _MODE_SIGNALS.get(name, [])}
            for name, cfg in MODES.items()
        ], indent=2)

        prompt = (
            "You are a task router. Given a user request, choose the single best "
            "agent mode from the list below. Respond with ONLY the mode name.\n\n"
            f"Available modes:\n{modes_json}\n\n"
            f"User request: {task}\n\n"
            "Mode:"
        )

        try:
            response: LLMResponse = model_factory.chat(
                messages=[{"role": "user", "content": prompt}],
                tools=[],
                temperature=0.0,
            )
            mode = (response.content or "").strip().lower()
            if mode in MODES:
                return mode
        except Exception as exc:
            logger.warning("LLM classification failed: %s", exc)

        # Fallback to highest-scored keyword mode.
        fallback = max(keyword_scores, key=keyword_scores.get) if keyword_scores else "orchestrator"
        if keyword_scores.get(fallback, 0) == 0:
            return "orchestrator"
        return fallback

    def _decompose_task(self, task: str, mode: str) -> list[dict[str, Any]]:
        """For 'orchestrator' mode, optionally break the task into subtasks."""
        if mode != "orchestrator":
            return []

        prompt = (
            "You are a project planner. Break the following task into a sequence "
            "of subtasks, each assigned to the best agent mode.\n"
            "Modes available: architect (planning), coder (implementation), "
            "debugger (bug fixing), reviewer (code review).\n\n"
            "Respond with a JSON array of objects, each with keys:\n"
            '  - "mode": the agent mode\n'
            '  - "description": what this subtask should accomplish\n'
            '  - "context_hints": any relevant information to pass forward\n\n'
            f"Task: {task}\n\n"
            "Subtasks (JSON array):"
        )

        try:
            response: LLMResponse = model_factory.chat(
                messages=[{"role": "user", "content": prompt}],
                tools=[],
                temperature=0.3,
            )
            content = response.content or ""
            # Extract JSON from the response.
            if "[" in content:
                json_str = content[content.index("["):]
                if "]" in json_str:
                    json_str = json_str[:json_str.rindex("]") + 1]
                    subtasks = json.loads(json_str)
                    if isinstance(subtasks, list) and len(subtasks) <= 10:
                        return subtasks
        except Exception as exc:
            logger.warning("Task decomposition failed: %s", exc)

        return []

    def _build_subtask_prompt(self, subtask: dict[str, Any], context: dict[str, Any]) -> str:
        """Enrich a subtask description with accumulated context."""
        parts = [subtask.get("description", "")]
        if context:
            ctx_lines = []
            for key, value in context.items():
                if isinstance(value, str) and value:
                    ctx_lines.append(f"[{key}]\n{value[:2000]}")
            if ctx_lines:
                parts.append("Context from previous steps:\n" + "\n\n".join(ctx_lines))
        return "\n\n".join(parts)

    def _build_summary(self) -> str:
        """Create a human-readable summary of all modes executed."""
        if not self._mode_chain:
            return "No modes have been executed yet."
        parts = [f"Execution chain: {' → '.join(self._mode_chain)}"]
        for mode, result in self._results.items():
            result_text = result.get("result", "") if isinstance(result, dict) else str(result)
            parts.append(f"{mode}: {result_text[:100]}")
        return "\n".join(parts)


__all__ = ["Orchestrator"]
