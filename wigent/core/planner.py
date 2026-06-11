# ════════════════════════════════════════
# wigent — Planner
# Role: Task breakdown planner with dependency management and execution ordering
# Author: Wigent AI
# Version: 1.0.0
# ════════════════════════════════════════

"""Decomposes PRDs into atomic, verifiable tasks with dependency graphs,
parallel execution groups, and Mermaid visualization.

Usage
-----
    from wigent.core.planner import Planner, Task
    from wigent.models.model_factory import factory as model_factory

    llm = model_factory.get_active_model()
    planner = Planner(llm)
    tasks = planner.create_plan(prd_text, codebase_context)
    order = planner.get_execution_order(tasks)
    parallel = planner.get_parallel_groups(tasks)
"""

from __future__ import annotations

import json
import re
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from wigent.models.base_model import BaseModel


@dataclass(frozen=True)
class Task:
    """A single atomic unit of work with acceptance criteria and dependencies.

    Attributes
    ----------
    id : str
        Unique identifier (e.g. ``"T-1"``, ``"T-2"``).
    description : str
        What this task accomplishes.
    acceptance_criteria : list[str]
        Testable statements that define "done".
    dependencies : list[str]
        Task IDs that must be completed before this one.
    estimated_effort : str
        One of ``XS`` (hours), ``S`` (half-day), ``M`` (1-2 days).
    skill_required : str
        The Wigent skill needed (e.g. ``"incremental-implementation"``).
    mode_required : str
        Agent mode to use (e.g. ``"coder"``, ``"debugger"``).
    status : str
        One of ``pending``, ``in_progress``, ``done``, ``blocked``.
    """

    id: str
    description: str
    acceptance_criteria: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    estimated_effort: str = "M"
    skill_required: str = ""
    mode_required: str = "coder"
    status: str = "pending"

    def __post_init__(self) -> None:
        if self.estimated_effort not in {"XS", "S", "M"}:
            raise ValueError(
                f"Task {self.id}: effort '{self.estimated_effort}' exceeds "
                f"maximum allowed 'M'. Break down further."
            )
        if not self.acceptance_criteria:
            raise ValueError(f"Task {self.id}: must have at least one acceptance criterion")


class Planner:
    """Decomposes PRDs into executable task graphs with dependency resolution.

    Enforces:
    - No task larger than ``M`` effort.
    - Every task has acceptance criteria.
    - Dependencies form a DAG (no cycles).
    - Topological execution order.
    - Parallel group identification.
    """

    MAX_TASKS_PER_PLAN: int = 50
    MAX_DEPENDENCIES: int = 5

    def __init__(self, llm_client: BaseModel) -> None:
        self.llm = llm_client
        self._tasks: dict[str, Task] = {}
        self._execution_order: list[str] = []

    # ── Public API ─────────────────────────────────────────────────────

    def create_plan(self, spec: str, codebase_context: str = "") -> list[Task]:
        """Decompose a PRD into atomic tasks using LLM + validation.

        Args:
            spec: The PRD or specification text.
            codebase_context: Optional AST summary or file listing.

        Returns:
            List of validated ``Task`` objects.

        Raises:
            ValueError: If the LLM returns invalid JSON or tasks fail validation.
        """
        prompt = self._build_planning_prompt(spec, codebase_context)
        response = self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            tools=[],
            temperature=0.2,
        )
        tasks_data = self._parse_llm_response(response.content or "")
        tasks = self._validate_and_build_tasks(tasks_data)

        self._tasks = {t.id: t for t in tasks}
        self._execution_order = self._topological_sort()

        return tasks

    def get_execution_order(self, tasks: list[Task] | None = None) -> list[Task]:
        """Return tasks in dependency-respecting execution order.

        Uses Kahn's algorithm for topological sort.

        Args:
            tasks: Optional task list to sort.  Uses internal registry if omitted.

        Returns:
            Tasks ordered so all dependencies of task N are in positions 0..N-1.
        """
        if tasks is not None:
            self._tasks = {t.id: t for t in tasks}
            self._execution_order = self._topological_sort()
        return [self._tasks[tid] for tid in self._execution_order]

    def get_parallel_groups(self, tasks: list[Task] | None = None) -> list[list[Task]]:
        """Group tasks that can execute simultaneously.

        All tasks in group *N* have all their dependencies satisfied by tasks
        in groups *0..N-1*.

        Args:
            tasks: Optional task list.  Uses internal registry if omitted.

        Returns:
            A list of groups, each group being a list of tasks with no
            inter-dependencies.
        """
        if tasks is not None:
            self._tasks = {t.id: t for t in tasks}
            self._execution_order = self._topological_sort()

        if not self._execution_order:
            return []

        completed: set[str] = set()
        remaining = set(self._execution_order)
        groups: list[list[str]] = []

        while remaining:
            group = [
                tid for tid in remaining
                if all(dep in completed for dep in self._tasks[tid].dependencies)
            ]
            if not group:
                raise ValueError("Dependency cycle detected in parallel grouping")
            groups.append(group)
            completed.update(group)
            remaining -= set(group)

        return [[self._tasks[tid] for tid in group] for group in groups]

    def get_next_task(self) -> Task | None:
        """Return the first pending task whose dependencies are all satisfied."""
        for tid in self._execution_order:
            task = self._tasks[tid]
            if task.status != "pending":
                continue
            deps_satisfied = all(
                self._tasks[dep].status == "done"
                for dep in task.dependencies
                if dep in self._tasks
            )
            if deps_satisfied:
                return task
        return None

    def mark_done(self, task_id: str) -> Task:
        """Mark a task as completed.

        Args:
            task_id: The task to mark.

        Returns:
            The updated ``Task``.
        """
        return self._update_status(task_id, "done")

    def mark_blocked(self, task_id: str, reason: str) -> Task:
        """Mark a task as blocked with a logged reason.

        Args:
            task_id: The task to mark.
            reason: Why the task is blocked (appended to description).

        Returns:
            The updated ``Task``.
        """
        old = self._tasks[task_id]
        new = Task(
            id=old.id,
            description=f"{old.description} [BLOCKED: {reason}]",
            acceptance_criteria=old.acceptance_criteria,
            dependencies=old.dependencies,
            estimated_effort=old.estimated_effort,
            skill_required=old.skill_required,
            mode_required=old.mode_required,
            status="blocked",
        )
        self._tasks[task_id] = new
        return new

    def to_markdown(self, tasks: list[Task] | None = None) -> str:
        """Render the plan as a markdown checklist.

        Args:
            tasks: Optional task list.  Uses execution order if omitted.

        Returns:
            Markdown string with status icons, effort, and acceptance criteria.
        """
        if tasks is None:
            tasks = [self._tasks[tid] for tid in self._execution_order]

        lines = [
            f"# Implementation Plan: {len(tasks)} Tasks\n",
            f"**Total Effort:** {self._estimate_total_effort(tasks)}",
            f"**Parallel Groups:** {len(self.get_parallel_groups(tasks))}\n",
            "## Execution Order\n",
        ]

        for i, task in enumerate(tasks, 1):
            icon = {
                "pending": "\u2b1c",
                "in_progress": "\U0001f504",
                "done": "\u2705",
                "blocked": "\U0001f6ab",
            }.get(task.status, "\u2b1c")
            lines.append(
                f"{i}. {icon} **{task.id}**: {task.description} "
                f"(`{task.estimated_effort}`)"
            )

        lines.append("\n## Tasks\n")
        for task in tasks:
            deps = ", ".join(task.dependencies) if task.dependencies else "None"
            criteria = "\n".join(f"  - [ ] {c}" for c in task.acceptance_criteria)
            lines.extend([
                f"### {task.id}: {task.description}\n",
                f"**Effort:** {task.estimated_effort} | ",
                f"**Skill:** {task.skill_required} | ",
                f"**Mode:** {task.mode_required} | ",
                f"**Status:** {task.status}\n",
                f"**Dependencies:** {deps}\n",
                "**Acceptance Criteria:**\n",
                f"{criteria}\n",
                "---\n",
            ])

        return "\n".join(lines)

    def to_mermaid(self, tasks: list[Task] | None = None) -> str:
        """Output a Mermaid flowchart of the task dependency graph.

        Nodes are colored by status:
        - ``pending``: default
        - ``in_progress``: yellow
        - ``done``: green
        - ``blocked``: red

        Args:
            tasks: Optional task list.  Uses execution order if omitted.

        Returns:
            A Mermaid ``flowchart TD`` string ready to embed.
        """
        if tasks is None:
            tasks = [self._tasks[tid] for tid in self._execution_order]

        lines = ["```mermaid", "flowchart TD"]

        for task in tasks:
            color = {
                "pending": "",
                "in_progress": ":::inProgress",
                "done": ":::done",
                "blocked": ":::blocked",
            }.get(task.status, "")
            safe_desc = task.description[:30].replace('"', "'")
            lines.append(f'    {task.id}["{task.id}<br/>{safe_desc}"]{color}')

        for task in tasks:
            for dep in task.dependencies:
                if dep in self._tasks:
                    lines.append(f"    {dep} --> {task.id}")

        lines.extend([
            "    classDef inProgress fill:#fef3c7,stroke:#f59e0b",
            "    classDef done fill:#d1fae5,stroke:#10b981",
            "    classDef blocked fill:#fee2e2,stroke:#ef4444",
            "```",
        ])
        return "\n".join(lines)

    # ── Internals ──────────────────────────────────────────────────────

    def _build_planning_prompt(self, spec: str, codebase_context: str) -> str:
        """Construct the LLM prompt for task decomposition."""
        context_section = (
            f"\n## Existing Codebase Context\n{codebase_context}\n"
            if codebase_context
            else ""
        )
        return (
            f"You are a principal engineer decomposing a PRD into atomic, "
            f"implementable tasks.\n\n"
            f"## PRD\n{spec}\n"
            f"{context_section}\n"
            f"## Rules\n"
            f"1. Break down into the SMALLEST possible tasks. "
            f"No task larger than \"M\" effort.\n"
            f"2. Each task must have 1-3 clear acceptance criteria "
            f"(testable statements).\n"
            f"3. Dependencies must form a DAG (no cycles). "
            f"Use task IDs for dependencies.\n"
            f"4. Task IDs format: T-1, T-2, etc.\n"
            f"5. Estimated effort: XS (hours), S (half-day), M (1-2 days) "
            f"\u2014 NEVER L or XL.\n"
            f"6. Skill required: one of the 24 Wigent skills "
            f"(e.g., \"incremental-implementation\").\n"
            f"7. Mode required: one of coder, debugger, reviewer, "
            f"architect, frontend, api.\n"
            f"8. Maximum {self.MAX_TASKS_PER_PLAN} tasks. "
            f"If PRD requires more, create an EPIC task that references "
            f"a follow-up plan.\n"
            f"9. Consider existing codebase \u2014 don't duplicate existing "
            f"files unless modifying.\n\n"
            f"## Output Format\n"
            f"Return ONLY a JSON array. No markdown, no explanation.\n\n"
            f"```json\n"
            f'[\n'
            f'  {{\n'
            f'    "id": "T-1",\n'
            f'    "description": "Create User model with email validation",\n'
            f'    "acceptance_criteria": [\n'
            f'      "User model has email field with regex validation",\n'
            f'      "Invalid email raises ValidationError",\n'
            f'      "Password field is write-only"\n'
            f'    ],\n'
            f'    "dependencies": [],\n'
            f'    "estimated_effort": "S",\n'
            f'    "skill_required": "incremental-implementation",\n'
            f'    "mode_required": "coder"\n'
            f'  }}\n'
            f"]\n"
            f"```\n\n"
            f"## Validation\n"
            f"- Is every acceptance criterion testable? If not, rewrite.\n"
            f"- Are dependencies realistic? "
            f"No task should depend on 5+ others.\n"
            f"- Is effort honest? When in doubt, choose the smaller size."
        )

    def _parse_llm_response(self, response: str) -> list[dict[str, Any]]:
        """Extract JSON array from LLM response, handling markdown wrappers."""
        json_match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_match = re.search(r"(\[.*\])", response, re.DOTALL)
            if not json_match:
                raise ValueError(
                    f"Could not extract JSON from LLM response: {response[:200]}"
                )
            json_str = json_match.group(1)

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON from LLM: {e}\nRaw: {json_str[:500]}") from e

        if not isinstance(data, list):
            raise ValueError(f"Expected JSON array, got {type(data).__name__}")
        return data

    def _validate_and_build_tasks(self, tasks_data: list[dict[str, Any]]) -> list[Task]:
        """Validate task data and build ``Task`` objects."""
        tasks: list[Task] = []
        task_ids: set[str] = set()

        for data in tasks_data:
            task_id = data.get("id", f"T-{len(tasks) + 1}")
            description = data.get("description", "")
            if not description:
                raise ValueError(f"Task {task_id}: missing description")

            try:
                task = Task(
                    id=task_id,
                    description=description,
                    acceptance_criteria=data.get("acceptance_criteria", []),
                    dependencies=data.get("dependencies", []),
                    estimated_effort=data.get("estimated_effort", "M"),
                    skill_required=data.get("skill_required", ""),
                    mode_required=data.get("mode_required", "coder"),
                )
            except ValueError as e:
                raise ValueError(f"Task validation failed: {e}") from e

            if task.id in task_ids:
                raise ValueError(f"Duplicate task ID: {task.id}")
            task_ids.add(task.id)

            if len(task.dependencies) > self.MAX_DEPENDENCIES:
                raise ValueError(
                    f"Task {task.id}: too many dependencies "
                    f"({len(task.dependencies)}). Max: {self.MAX_DEPENDENCIES}"
                )
            tasks.append(task)

        for task in tasks:
            for dep in task.dependencies:
                if dep not in task_ids:
                    raise ValueError(
                        f"Task {task.id}: dependency '{dep}' not found in plan"
                    )

        self._detect_cycles(tasks)
        return tasks

    def _detect_cycles(self, tasks: list[Task]) -> None:
        """Detect cycles in the dependency graph using DFS."""
        graph: dict[str, list[str]] = {t.id: list(t.dependencies) for t in tasks}
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = {t.id: WHITE for t in tasks}
        path: list[str] = []

        def dfs(node: str) -> None:
            color[node] = GRAY
            path.append(node)
            for neighbor in graph.get(node, []):
                if color[neighbor] == GRAY:
                    cycle = "\u2192 ".join(
                        path[path.index(neighbor):] + [neighbor]
                    )
                    raise ValueError(f"Dependency cycle detected: {cycle}")
                if color[neighbor] == WHITE:
                    dfs(neighbor)
            path.pop()
            color[node] = BLACK

        for tid in graph:
            if color[tid] == WHITE:
                dfs(tid)

    def _topological_sort(self) -> list[str]:
        """Kahn's algorithm for topological sort."""
        in_degree: dict[str, int] = {tid: 0 for tid in self._tasks}
        adj: dict[str, list[str]] = {tid: [] for tid in self._tasks}

        for task in self._tasks.values():
            for dep in task.dependencies:
                if dep in self._tasks:
                    in_degree[task.id] += 1
                    adj[dep].append(task.id)

        queue = deque([tid for tid, deg in in_degree.items() if deg == 0])
        result: list[str] = []

        while queue:
            node = queue.popleft()
            result.append(node)
            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(result) != len(self._tasks):
            raise ValueError("Topological sort failed \u2014 cycle detected")
        return result

    def _update_status(self, task_id: str, status: str) -> Task:
        """Return a new Task with the status changed (frozen dataclass)."""
        if task_id not in self._tasks:
            raise KeyError(f"Task {task_id} not found")
        old = self._tasks[task_id]
        new = Task(
            id=old.id,
            description=old.description,
            acceptance_criteria=old.acceptance_criteria,
            dependencies=old.dependencies,
            estimated_effort=old.estimated_effort,
            skill_required=old.skill_required,
            mode_required=old.mode_required,
            status=status,
        )
        self._tasks[task_id] = new
        return new

    def _estimate_total_effort(self, tasks: list[Task]) -> str:
        """Calculate total estimated effort from task sizes."""
        effort_map = {"XS": 0.5, "S": 1.0, "M": 2.0}
        total = sum(effort_map.get(t.estimated_effort, 1.0) for t in tasks)
        if total < 1:
            return f"{int(total * 8)} hours"
        if total < 5:
            return f"{total:.1f} days"
        return f"{total / 5:.1f} weeks"


__all__ = ["Task", "Planner"]
