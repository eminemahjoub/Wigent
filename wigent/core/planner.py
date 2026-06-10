# ════════════════════════════════════════
# wigent — Architect / Planner Mode
# Role: Structured planning, tech-stack recommendations, risk analysis
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Architect mode agent — reads the codebase, designs architecture,
produces detailed implementation plans without writing code.

Temperature: 0.3 (creative but structured)
Tools: read, list, search — no write/modify tools.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from wigent.config import settings
from wigent.config.modes import get_mode
from wigent.core.loop import AgentLoop
from wigent.models.base_model import LLMResponse
from wigent.models.model_factory import factory as model_factory
from wigent.prompts import build_mode_prompt

logger = logging.getLogger(__name__)

ARCHITECT_TEMPERATURE = 0.3


class ArchitectAgent:
    """Planning agent that analyses requirements and produces structured plans.

    Uses ``AgentLoop`` under the hood for multi-step codebase exploration
    and provides higher-level methods for analysis, risk assessment, and
    structured plan output.

    Usage
    -----
        architect = ArchitectAgent()
        analysis = architect.analyze_requirements("Add user auth")
        plan = architect.create_plan(analysis)
        print(architect.format_plan_output(plan))
    """

    MODE = "architect"

    def __init__(self, model: Any | None = None) -> None:
        self._model = model or model_factory.get_active_model()
        self._mode_cfg = get_mode(self.MODE)
        self._metrics: dict[str, Any] = {
            "plans_created": 0,
            "risks_identified": 0,
            "total_analysis_time": 0.0,
        }

    # ── Public API ───────────────────────────────────────────────────

    def analyze_requirements(self, task: str) -> dict[str, Any]:
        """Analyse a task and gather context from the codebase.

        Explores the codebase to understand existing structure, then
        produces a structured requirements analysis.

        Args:
            task: The user's task description.

        Returns:
            A dict with ``overview``, ``existing_patterns``,
            ``constraints``, ``affected_areas``.
        """
        t0 = time.perf_counter()

        # Step 1: explore codebase via the agent loop (read-only tools).
        loop = self._build_loop()
        explore_state = loop.run(
            f"Explore the codebase to understand the current structure. "
            f"Read relevant files. Then produce a requirements analysis for:\n\n{task}",
            mode=self.MODE,
            max_iterations=self._mode_cfg.max_iterations,
        )

        # Step 2: extract structured analysis via one-shot LLM call.
        analysis_prompt = (
            "You are a senior software architect. Based on the following "
            "exploration results, produce a structured requirements analysis.\n\n"
            f"Original task: {task}\n\n"
            f"Exploration context:\n{explore_state.get('result', '')[:6000]}\n\n"
            "Respond in this exact JSON format:\n"
            '{\n'
            '  "overview": "2-3 sentence summary",\n'
            '  "existing_patterns": ["pattern1", "pattern2"],\n'
            '  "constraints": ["constraint1"],\n'
            '  "affected_areas": ["area1"],\n'
            '  "key_questions": ["question1"]\n'
            '}'
        )

        analysis = self._llm_json(
            analysis_prompt,
            {"overview": "", "existing_patterns": [], "constraints": [],
             "affected_areas": [], "key_questions": []},
        )

        duration = time.perf_counter() - t0
        self._metrics["total_analysis_time"] += duration
        logger.info("analyze_requirements: %s  duration=%.1fs", task[:60], duration)

        return analysis

    def create_plan(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """Create a structured implementation plan from a requirements analysis.

        Produces a detailed plan with phases, tasks, files affected, risks,
        success criteria, and estimated effort.

        Args:
            analysis: Output from ``analyze_requirements()``.

        Returns:
            A structured plan dict with sections for overview, tech stack,
            phases, risks, success criteria, estimates, and next steps.
        """
        t0 = time.perf_counter()

        prompt = (
            "You are a senior software architect. Create a detailed "
            "implementation plan based on the following analysis.\n\n"
            f"Analysis:\n{json.dumps(analysis, indent=2)}\n\n"
            "Respond in this exact JSON format:\n"
            '{\n'
            '  "overview": "2-3 sentence summary",\n'
            '  "tech_stack": {\n'
            '    "language": "...",\n'
            '    "framework": "...",\n'
            '    "libraries": [{"name": "...", "purpose": "..."}],\n'
            '    "justification": "..."\n'
            '  },\n'
            '  "phases": [\n'
            '    {\n'
            '      "name": "Phase 1: ...",\n'
            '      "description": "...",\n'
            '      "tasks": [\n'
            '        {"action": "...", "file": "...", "type": "create|modify|delete"}\n'
            '      ],\n'
            '      "dependencies": [],\n'
            '      "estimated_minutes": 30\n'
            '    }\n'
            '  ],\n'
            '  "file_tree": {\n'
            '    "new_files": ["path/to/new.py"],\n'
            '    "modified_files": ["path/to/existing.py"]\n'
            '  },\n'
            '  "risks": [\n'
            '    {"risk": "...", "severity": "High|Medium|Low", "mitigation": "..."}\n'
            '  ],\n'
            '  "success_criteria": ["criterion1"],\n'
            '  "estimated_total_minutes": 120,\n'
            '  "next_steps": ["step1"]\n'
            '}'
        )

        plan = self._llm_json(prompt, {
            "overview": "", "tech_stack": {},
            "phases": [], "file_tree": {},
            "risks": [], "success_criteria": [],
            "estimated_total_minutes": 0, "next_steps": [],
        })

        # Enrich with computed metadata.
        plan["complexity_score"] = self._compute_complexity(plan)
        plan["risks_identified"] = len(plan.get("risks", []))

        duration = time.perf_counter() - t0
        self._metrics["plans_created"] += 1
        self._metrics["risks_identified"] += len(plan.get("risks", []))
        logger.info("create_plan: %d phases, %d risks  duration=%.1fs",
                    len(plan.get("phases", [])), len(plan.get("risks", [])), duration)

        return plan

    def estimate_complexity(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Estimate the complexity of a plan on multiple axes.

        Returns scores for scope, technical difficulty, integration
        complexity, and overall rating.

        Args:
            plan: A plan dict from ``create_plan()``.

        Returns:
            A dict with ``scope``, ``technical``, ``integration``,
            ``overall`` (each 1-10), and ``recommendation``.
        """
        prompt = (
            "Evaluate the complexity of the following implementation plan.\n\n"
            f"Plan:\n{json.dumps(plan, indent=2)[:4000]}\n\n"
            "Rate each axis 1-10 (1=trivial, 10=extremely complex):\n\n"
            "Respond in JSON:\n"
            '{\n'
            '  "scope": 5,\n'
            '  "technical": 5,\n'
            '  "integration": 5,\n'
            '  "overall": 5,\n'
            '  "recommendation": "Proceed with caution" | "Safe to implement" | "Needs simplification"\n'
            '}'
        )

        result = self._llm_json(prompt, {
            "scope": 5, "technical": 5, "integration": 5,
            "overall": 5, "recommendation": "Safe to implement",
        })
        return result

    def identify_risks(self, plan: dict[str, Any]) -> list[dict[str, str]]:
        """Identify and rank risks for a given plan.

        Returns a list of risk entries with severity and mitigation
        strategies beyond what was already captured in the plan.

        Args:
            plan: A plan dict from ``create_plan()``.

        Returns:
            List of ``{"risk": ..., "severity": ..., "mitigation": ...}``.
        """
        result = self.estimate_complexity(plan)
        prompt = (
            "Analyse the following plan and identify risks that may not "
            "be immediately obvious. Be thorough.\n\n"
            f"Plan:\n{json.dumps(plan, indent=2)[:4000]}\n\n"
            f"Complexity assessment:\n{json.dumps(result, indent=2)}\n\n"
            "Respond with a JSON array of risk objects:\n"
            '[\n'
            '  {"risk": "description", "severity": "High|Medium|Low", '
            '"mitigation": "strategy", "category": "technical|process|dependency"}\n'
            ']'
        )

        risks = self._llm_json(prompt, [])
        if not isinstance(risks, list):
            risks = []
        self._metrics["risks_identified"] += len(risks)
        return risks

    def recommend_stack(self, requirements: dict[str, Any]) -> dict[str, Any]:
        """Recommend a technology stack based on requirements and existing codebase.

        Args:
            requirements: A dict with task description and constraints.

        Returns:
            A dict with ``language``, ``framework``, ``libraries``,
            ``justification``, and ``alternative``.
        """
        prompt = (
            "You are a senior software architect. Recommend a technology "
            "stack for the following requirements. Prefer what the existing "
            "project already uses.\n\n"
            f"Requirements: {json.dumps(requirements, indent=2)}\n\n"
            "Respond in JSON:\n"
            '{\n'
            '  "language": {"name": "Python", "version": "3.12", "reason": "..."},\n'
            '  "framework": {"name": "...", "reason": "..."},\n'
            '  "libraries": [{"name": "...", "purpose": "...", "critical": true}],\n'
            '  "justification": "2-3 sentence summary of why this stack",\n'
            '  "alternatives": [{"name": "...", "pros": ["..."], "cons": ["..."]}]\n'
            '}'
        )

        return self._llm_json(prompt, {
            "language": {}, "framework": {},
            "libraries": [], "justification": "", "alternatives": [],
        })

    def create_file_tree(self, plan: dict[str, Any]) -> dict[str, list[str]]:
        """Extract the file tree from a plan into a structured format.

        Args:
            plan: A plan dict from ``create_plan()``.

        Returns:
            A dict with ``new_files``, ``modified_files``, and
            ``deleted_files`` lists.
        """
        tree = plan.get("file_tree", {"new_files": [], "modified_files": []})

        # Also extract from phases.
        for phase in plan.get("phases", []):
            for task in phase.get("tasks", []):
                fpath = task.get("file", "")
                ttype = task.get("type", "modify")
                if not fpath:
                    continue
                if ttype == "create" and fpath not in tree.setdefault("new_files", []):
                    tree.setdefault("new_files", []).append(fpath)
                elif ttype == "modify" and fpath not in tree.setdefault("modified_files", []):
                    tree.setdefault("modified_files", []).append(fpath)
                elif ttype == "delete" and fpath not in tree.setdefault("deleted_files", []):
                    tree.setdefault("deleted_files", []).append(fpath)

        return tree

    def validate_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Check a plan for completeness and consistency.

        Verifies that all required fields exist, phases have tasks,
        risks have mitigations, and file references are consistent.

        Args:
            plan: A plan dict from ``create_plan()``.

        Returns:
            A dict with ``valid`` (bool), ``issues`` (list),
            ``warnings`` (list), and ``score`` (0-100).
        """
        issues: list[str] = []
        warnings: list[str] = []
        score = 100

        # Check required top-level keys.
        for key in ("overview", "tech_stack", "phases", "risks", "success_criteria"):
            if key not in plan or not plan[key]:
                issues.append(f"Missing or empty: {key}")
                score -= 20

        # Check phases.
        phases = plan.get("phases", [])
        if not phases:
            issues.append("No phases defined")
        else:
            for i, phase in enumerate(phases):
                if not phase.get("name"):
                    issues.append(f"Phase {i + 1} has no name")
                    score -= 10
                if not phase.get("tasks"):
                    warnings.append(f"Phase {i + 1} has no tasks")
                    score -= 5
                if not phase.get("description"):
                    warnings.append(f"Phase {i + 1} has no description")
                    score -= 5

        # Check risks have mitigations.
        for risk in plan.get("risks", []):
            if not risk.get("mitigation"):
                warnings.append(f"Risk '{risk.get('risk', '?')}' has no mitigation")
                score -= 5

        # Check tech stack.
        ts = plan.get("tech_stack", {})
        if not ts.get("language") and not ts.get("framework"):
            warnings.append("No language or framework specified")
            score -= 10

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "score": max(0, score),
        }

    def format_plan_output(self, plan: dict[str, Any]) -> str:
        """Format a plan into a human-readable markdown string.

        Args:
            plan: A plan dict from ``create_plan()``.

        Returns:
            A formatted markdown string suitable for display or saving.
        """
        lines: list[str] = []
        lines.append(f"# Plan: {plan.get('overview', 'Untitled')[:80]}")

        # Overview.
        lines.append("\n## Overview")
        lines.append(plan.get("overview", "No overview provided."))

        # Tech stack.
        ts = plan.get("tech_stack", {})
        lines.append("\n## Tech Stack")
        lang = ts.get("language", {})
        if isinstance(lang, dict):
            lines.append(f"- **Language:** {lang.get('name', 'N/A')} {lang.get('version', '')}")
        else:
            lines.append(f"- **Language:** {lang}")
        framework = ts.get("framework", {})
        if isinstance(framework, dict):
            lines.append(f"- **Framework:** {framework.get('name', 'N/A')}")
        else:
            lines.append(f"- **Framework:** {framework}")
        for lib in ts.get("libraries", []):
            if isinstance(lib, dict):
                lines.append(f"- **{lib.get('name', '')}:** {lib.get('purpose', '')}")
        justification = ts.get("justification", "")
        if justification:
            lines.append(f"\n*Justification:* {justification}")

        # Phases.
        lines.append("\n## Implementation Plan")
        for i, phase in enumerate(plan.get("phases", []), 1):
            lines.append(f"\n### Phase {i}: {phase.get('name', 'Untitled')}")
            lines.append(phase.get("description", ""))
            deps = phase.get("dependencies", [])
            if deps:
                lines.append(f"\n*Dependencies:* {', '.join(deps)}")
            est = phase.get("estimated_minutes")
            if est:
                lines.append(f"*Estimated:* {est} min")
            tasks = phase.get("tasks", [])
            if tasks:
                lines.append("\n| # | Action | File | Type |")
                lines.append("|---|--------|------|------|")
                for j, task in enumerate(tasks, 1):
                    lines.append(
                        f"| {j} | {task.get('action', '')} | "
                        f"`{task.get('file', '')}` | {task.get('type', '')} |"
                    )

        # Risks.
        risks = plan.get("risks", [])
        if risks:
            lines.append("\n## Risk Register")
            lines.append("| Risk | Severity | Mitigation |")
            lines.append("|------|----------|------------|")
            for risk in risks:
                lines.append(
                    f"| {risk.get('risk', '')} | {risk.get('severity', '')} | "
                    f"{risk.get('mitigation', '')} |"
                )

        # Success criteria.
        criteria = plan.get("success_criteria", [])
        if criteria:
            lines.append("\n## Success Criteria")
            for c in criteria:
                lines.append(f"- [ ] {c}")

        # Estimate.
        est_total = plan.get("estimated_total_minutes")
        if est_total:
            hours = est_total // 60
            mins = est_total % 60
            lines.append(f"\n**Estimated total:** {hours}h {mins}m")

        # Complexity.
        cs = plan.get("complexity_score", {})
        if isinstance(cs, dict) and cs.get("overall"):
            lines.append(f"**Complexity:** {cs['overall']}/10 — {cs.get('recommendation', '')}")

        # File tree.
        ft = plan.get("file_tree", {})
        if ft:
            lines.append("\n## Files")
            for f in ft.get("new_files", []):
                lines.append(f"- `{f}` (new)")
            for f in ft.get("modified_files", []):
                lines.append(f"- `{f}` (modified)")

        # Next steps.
        next_steps = plan.get("next_steps", [])
        if next_steps:
            lines.append("\n## Next Steps")
            for s in next_steps:
                lines.append(f"- {s}")

        return "\n".join(lines)

    def get_metrics(self) -> dict[str, Any]:
        """Return metrics tracked by this agent."""
        return dict(self._metrics)

    # ── Internals ────────────────────────────────────────────────────

    def _build_loop(self) -> AgentLoop:
        """Create an AgentLoop configured for architect mode."""
        return AgentLoop(
            model=self._model,
            mode=self.MODE,
            enable_checkpoints=False,
        )

    def _llm_json(self, prompt: str, default: Any) -> Any:
        """Call the LLM and parse a JSON response.

        Args:
            prompt: The full prompt to send.
            default: Fallback value if JSON parsing fails.

        Returns:
            Parsed JSON object or ``default``.
        """
        try:
            response: LLMResponse = self._model.chat(
                messages=[{"role": "user", "content": prompt}],
                tools=[],
                temperature=ARCHITECT_TEMPERATURE,
            )
            content = (response.content or "").strip()

            # Extract JSON from markdown code blocks if present.
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            return json.loads(content)
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("LLM JSON parse failed: %s  content=%s", exc, content[:200] if 'content' in dir() else "?")
            return default

    @staticmethod
    def _compute_complexity(plan: dict[str, Any]) -> dict[str, Any]:
        """Heuristic complexity scoring without an LLM call."""
        num_phases = len(plan.get("phases", []))
        num_files = len(plan.get("file_tree", {}).get("new_files", [])) + len(plan.get("file_tree", {}).get("modified_files", []))
        num_risks = len(plan.get("risks", []))

        scope = min(10, num_phases * 2 + num_files // 2)
        integration = min(10, num_files)
        overall = min(10, (scope + integration + num_risks * 2) // 3)

        if overall <= 3:
            recommendation = "Safe to implement"
        elif overall <= 6:
            recommendation = "Proceed with caution"
        else:
            recommendation = "Needs simplification"

        return {
            "scope": scope,
            "technical": min(10, num_phases * 2),
            "integration": integration,
            "overall": overall,
            "recommendation": recommendation,
        }


__all__ = ["ArchitectAgent"]
