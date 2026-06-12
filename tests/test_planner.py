"""
Role: Comprehensive tests for Wigent's task planner.
Author: Wigent AI
Version: 1.0.0

Tests task creation, LLM decomposition, validation, topological sorting,
parallel group detection, Mermaid generation, and markdown rendering.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from wigent.core.planner import Planner, Task


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_llm():
    """Create a mock LLM client with configurable JSON responses."""
    llm = MagicMock()
    llm.generate.return_value = json.dumps([
        {
            "id": "T-1",
            "description": "Create User model with email validation",
            "acceptance_criteria": [
                "User model has email field with regex validation",
                "Invalid email raises ValidationError",
                "Password field is write-only"
            ],
            "dependencies": [],
            "estimated_effort": "S",
            "skill_required": "incremental-implementation",
            "mode_required": "coder"
        },
        {
            "id": "T-2",
            "description": "Implement password hashing with bcrypt",
            "acceptance_criteria": [
                "Passwords hashed with bcrypt cost factor 12",
                "Hash verification succeeds for valid password",
                "Hash verification fails for invalid password"
            ],
            "dependencies": ["T-1"],
            "estimated_effort": "S",
            "skill_required": "incremental-implementation",
            "mode_required": "coder"
        },
        {
            "id": "T-3",
            "description": "Build JWT token generation service",
            "acceptance_criteria": [
                "Tokens contain user_id and expiry claims",
                "Tokens signed with HS256 and 256-bit secret",
                "Token expiry is 24 hours from issuance"
            ],
            "dependencies": ["T-1"],
            "estimated_effort": "M",
            "skill_required": "api-and-interface-design",
            "mode_required": "api"
        },
        {
            "id": "T-4",
            "description": "Create login endpoint with validation",
            "acceptance_criteria": [
                "POST /auth/login accepts email and password",
                "Valid credentials return 200 with JWT token",
                "Invalid credentials return 401 with generic message"
            ],
            "dependencies": ["T-2", "T-3"],
            "estimated_effort": "M",
            "skill_required": "incremental-implementation",
            "mode_required": "coder"
        }
    ])
    return llm


@pytest.fixture
def planner(mock_llm):
    """Create a Planner instance with mocked LLM."""
    from wigent.core.planner import Planner
    return Planner(llm_client=mock_llm)


@pytest.fixture
def sample_tasks():
    """Return manually created valid tasks for isolated testing."""
    from wigent.core.planner import Task
    
    return [
        Task(
            id="T-1",
            description="Setup project structure",
            acceptance_criteria=["Directory structure matches spec"],
            dependencies=[],
            estimated_effort="XS",
            skill_required="incremental-implementation",
            mode_required="coder"
        ),
        Task(
            id="T-2",
            description="Implement database schema",
            acceptance_criteria=["Tables created", "Indexes defined"],
            dependencies=["T-1"],
            estimated_effort="S",
            skill_required="incremental-implementation",
            mode_required="coder"
        ),
        Task(
            id="T-3",
            description="Build API controllers",
            acceptance_criteria=["Routes registered", "Handlers implemented"],
            dependencies=["T-1"],
            estimated_effort="S",
            skill_required="api-and-interface-design",
            mode_required="api"
        ),
        Task(
            id="T-4",
            description="Write integration tests",
            acceptance_criteria=["All endpoints tested", "Coverage >80%"],
            dependencies=["T-2", "T-3"],
            estimated_effort="M",
            skill_required="test-driven-development",
            mode_required="coder"
        ),
    ]


@pytest.fixture
def cyclic_tasks():
    """Return tasks with a dependency cycle for error testing."""
    from wigent.core.planner import Task
    
    return [
        Task(id="T-A", description="A", acceptance_criteria=["A"], dependencies=["T-C"], estimated_effort="XS"),
        Task(id="T-B", description="B", acceptance_criteria=["B"], dependencies=["T-A"], estimated_effort="XS"),
        Task(id="T-C", description="C", acceptance_criteria=["C"], dependencies=["T-B"], estimated_effort="XS"),
    ]


# =============================================================================
# Test: Task Creation & Validation
# =============================================================================

class TestTaskValidation:
    """Tests for Task dataclass validation."""

    def test_task_creation_with_valid_data(self):
        """Given valid task data, create Task successfully."""
        from wigent.core.planner import Task
        
        task = Task(
            id="T-1",
            description="Test task",
            acceptance_criteria=["Criterion 1"],
            dependencies=[],
            estimated_effort="S",
            skill_required="test",
            mode_required="coder"
        )
        
        assert task.id == "T-1"
        assert task.estimated_effort == "S"
        assert task.status == "pending"

    def test_task_requires_acceptance_criteria(self):
        """Given empty acceptance criteria, raise ValueError."""
        from wigent.core.planner import Task
        
        with pytest.raises(ValueError, match="must have at least one acceptance criterion"):
            Task(
                id="T-1",
                description="Test task",
                acceptance_criteria=[],
                dependencies=[],
                estimated_effort="S"
            )

    def test_task_rejects_large_effort(self):
        """Given effort 'L' or 'XL', raise ValueError."""
        from wigent.core.planner import Task
        
        with pytest.raises(ValueError, match="exceeds maximum allowed"):
            Task(
                id="T-1",
                description="Test task",
                acceptance_criteria=["Criterion"],
                dependencies=[],
                estimated_effort="L"
            )

        with pytest.raises(ValueError, match="exceeds maximum allowed"):
            Task(
                id="T-1",
                description="Test task",
                acceptance_criteria=["Criterion"],
                dependencies=[],
                estimated_effort="XL"
            )

    @pytest.mark.parametrize("effort", ["XS", "S", "M"])
    def test_task_accepts_valid_effort_sizes(self, effort):
        """Given valid effort sizes XS/S/M, create Task successfully."""
        from wigent.core.planner import Task
        
        task = Task(
            id="T-1",
            description="Test",
            acceptance_criteria=["Criterion"],
            dependencies=[],
            estimated_effort=effort
        )
        
        assert task.estimated_effort == effort

    def test_task_default_values(self):
        """Given minimal required fields, verify defaults."""
        from wigent.core.planner import Task
        
        task = Task(
            id="T-1",
            description="Test",
            acceptance_criteria=["Criterion"]
        )
        
        assert task.dependencies == []
        assert task.estimated_effort == "M"
        assert task.skill_required == ""
        assert task.mode_required == "coder"
        assert task.status == "pending"

    def test_task_immutability(self):
        """Given frozen dataclass, verify fields cannot be modified."""
        from wigent.core.planner import Task
        
        task = Task(
            id="T-1",
            description="Test",
            acceptance_criteria=["Criterion"]
        )
        
        with pytest.raises(AttributeError):
            task.id = "T-2"


# =============================================================================
# Test: Plan Creation from LLM
# =============================================================================

class TestPlanCreation:
    """Tests for LLM-based task decomposition."""

    def test_create_plan_returns_tasks(self, planner, mock_llm):
        """
        Given a PRD and mocked LLM,
        When create_plan is called,
        Then return list of Task objects.
        """
        tasks = planner.create_plan("Build auth system", codebase_context="")
        
        assert isinstance(tasks, list)
        assert len(tasks) > 0
        assert all(isinstance(t, Task) for t in tasks)

    def test_create_plan_parses_llm_json(self, planner, mock_llm):
        """
        Given LLM returns JSON array,
        When parsed,
        Then extract all task fields correctly.
        """
        tasks = planner.create_plan("Build auth system")
        
        assert len(tasks) == 4
        assert tasks[0].id == "T-1"
        assert tasks[0].description == "Create User model with email validation"
        assert len(tasks[0].acceptance_criteria) == 3

    def test_create_plan_stores_tasks_internally(self, planner, mock_llm):
        """
        Given successful plan creation,
        Then store tasks in internal registry.
        """
        tasks = planner.create_plan("Build auth system")
        
        assert len(planner._tasks) == 4
        assert "T-1" in planner._tasks
        assert "T-4" in planner._tasks

    def test_create_plan_computes_execution_order(self, planner, mock_llm):
        """
        Given tasks with dependencies,
        When plan is created,
        Then pre-compute topological sort.
        """
        planner.create_plan("Build auth system")
        
        assert len(planner._execution_order) == 4
        # T-1 has no dependencies, should be first
        assert planner._execution_order[0] == "T-1"

    def test_create_plan_with_codebase_context(self, planner, mock_llm):
        """
        Given codebase context,
        When plan is created,
        Then include context in LLM prompt.
        """
        planner.create_plan("Build auth system", codebase_context="Existing: Flask app")
        
        call_args = mock_llm.generate.call_args
        prompt = call_args[0][0] if call_args[0] else call_args[1].get("prompt", "")
        
        assert "Existing: Flask app" in prompt

    def test_create_plan_raises_on_invalid_json(self, planner, mock_llm):
        """
        Given LLM returns invalid JSON,
        When create_plan is called,
        Then raise ValueError with helpful message.
        """
        mock_llm.generate.return_value = "not json {{{"
        
        with pytest.raises(ValueError, match="Invalid JSON"):
            planner.create_plan("Build auth system")

    def test_create_plan_raises_on_missing_required_fields(self, planner, mock_llm):
        """
        Given LLM returns JSON missing required fields,
        When parsed,
        Then raise ValueError.
        """
        mock_llm.generate.return_value = json.dumps([
            {"id": "T-1"}  # Missing description, acceptance_criteria
        ])
        
        with pytest.raises(ValueError):
            planner.create_plan("Build auth system")

    def test_create_plan_raises_on_duplicate_ids(self, planner, mock_llm):
        """
        Given LLM returns duplicate task IDs,
        When parsed,
        Then raise ValueError.
        """
        mock_llm.generate.return_value = json.dumps([
            {"id": "T-1", "description": "Task 1", "acceptance_criteria": ["A"]},
            {"id": "T-1", "description": "Task 2", "acceptance_criteria": ["B"]}
        ])
        
        with pytest.raises(ValueError, match="Duplicate task ID"):
            planner.create_plan("Build auth system")

    def test_create_plan_raises_on_missing_dependencies(self, planner, mock_llm):
        """
        Given task references non-existent dependency,
        When parsed,
        Then raise ValueError.
        """
        mock_llm.generate.return_value = json.dumps([
            {
                "id": "T-1",
                "description": "Task 1",
                "acceptance_criteria": ["A"],
                "dependencies": ["T-NONEXISTENT"]
            }
        ])
        
        with pytest.raises(ValueError, match="dependency.*not found"):
            planner.create_plan("Build auth system")

    def test_create_plan_raises_on_cycle(self, planner, mock_llm):
        """
        Given LLM returns tasks with circular dependencies,
        When parsed,
        Then raise ValueError with cycle description.
        """
        mock_llm.generate.return_value = json.dumps([
            {"id": "T-A", "description": "A", "acceptance_criteria": ["A"], "dependencies": ["T-C"]},
            {"id": "T-B", "description": "B", "acceptance_criteria": ["B"], "dependencies": ["T-A"]},
            {"id": "T-C", "description": "C", "acceptance_criteria": ["C"], "dependencies": ["T-B"]}
        ])
        
        with pytest.raises(ValueError, match="cycle"):
            planner.create_plan("Build auth system")

    def test_create_plan_raises_on_too_many_dependencies(self, planner, mock_llm):
        """
        Given task with >5 dependencies,
        When parsed,
        Then raise ValueError.
        """
        mock_llm.generate.return_value = json.dumps([
            {
                "id": "T-1",
                "description": "Task 1",
                "acceptance_criteria": ["A"],
                "dependencies": ["T-2", "T-3", "T-4", "T-5", "T-6", "T-7"]
            }
        ])
        
        with pytest.raises(ValueError, match="too many dependencies"):
            planner.create_plan("Build auth system")

    def test_create_plan_enforces_max_tasks(self, planner, mock_llm):
        """
        Given PRD requiring >50 tasks,
        When created,
        Then raise ValueError or create epic tasks.
        """
        many_tasks = [
            {
                "id": f"T-{i}",
                "description": f"Task {i}",
                "acceptance_criteria": [f"Criterion {i}"],
                "dependencies": []
            }
            for i in range(60)
        ]
        mock_llm.generate.return_value = json.dumps(many_tasks)
        
        with pytest.raises(ValueError):
            planner.create_plan("Huge project")


# =============================================================================
# Test: Execution Order (Topological Sort)
# =============================================================================

class TestExecutionOrder:
    """Tests for Kahn's algorithm topological sorting."""

    def test_execution_order_respects_dependencies(self, planner, sample_tasks):
        """
        Given tasks with dependencies,
        When get_execution_order is called,
        Then dependencies appear before dependent tasks.
        """
        order = planner.get_execution_order(sample_tasks)
        ids = [t.id for t in order]
        
        # T-2 depends on T-1, so T-1 before T-2
        assert ids.index("T-1") < ids.index("T-2")
        # T-3 depends on T-1, so T-1 before T-3
        assert ids.index("T-1") < ids.index("T-3")
        # T-4 depends on T-2 and T-3, so both before T-4
        assert ids.index("T-2") < ids.index("T-4")
        assert ids.index("T-3") < ids.index("T-4")

    def test_execution_order_independent_tasks_any_order(self, planner, sample_tasks):
        """
        Given independent tasks (T-2 and T-3 both depend on T-1),
        Then their relative order is not constrained.
        """
        order = planner.get_execution_order(sample_tasks)
        ids = [t.id for t in order]
        
        # Both valid: T-2 before T-3, or T-3 before T-2
        assert ids.index("T-1") < ids.index("T-2")
        assert ids.index("T-1") < ids.index("T-3")

    def test_execution_order_with_no_dependencies(self, planner):
        """
        Given tasks with no dependencies,
        When sorted,
        Then any order is valid.
        """
        from wigent.core.planner import Task
        
        tasks = [
            Task(id="T-1", description="A", acceptance_criteria=["A"]),
            Task(id="T-2", description="B", acceptance_criteria=["B"]),
            Task(id="T-3", description="C", acceptance_criteria=["C"]),
        ]
        
        order = planner.get_execution_order(tasks)
        
        assert len(order) == 3
        assert {t.id for t in order} == {"T-1", "T-2", "T-3"}

    def test_execution_order_single_task(self, planner):
        """Given single task, return it."""
        from wigent.core.planner import Task
        
        tasks = [Task(id="T-1", description="Only task", acceptance_criteria=["A"])]
        order = planner.get_execution_order(tasks)
        
        assert len(order) == 1
        assert order[0].id == "T-1"

    def test_execution_order_detects_cycle(self, planner, cyclic_tasks):
        """
        Given cyclic dependencies,
        When sorted,
        Then raise ValueError.
        """
        with pytest.raises(ValueError, match="cycle"):
            planner.get_execution_order(cyclic_tasks)

    def test_execution_order_empty_list(self, planner):
        """Given empty task list, return empty list."""
        order = planner.get_execution_order([])
        
        assert order == []


# =============================================================================
# Test: Parallel Groups
# =============================================================================

class TestParallelGroups:
    """Tests for parallel execution group detection."""

    def test_parallel_groups_identify_independent_tasks(self, planner, sample_tasks):
        """
        Given tasks with some independent dependencies,
        When get_parallel_groups is called,
        Then group tasks that can run simultaneously.
        """
        groups = planner.get_parallel_groups(sample_tasks)
        
        # Group 1: T-1 (no dependencies)
        assert len(groups[0]) == 1
        assert groups[0][0].id == "T-1"
        
        # Group 2: T-2 and T-3 (both depend only on T-1, so parallel)
        assert len(groups[1]) == 2
        group_2_ids = {t.id for t in groups[1]}
        assert group_2_ids == {"T-2", "T-3"}
        
        # Group 3: T-4 (depends on T-2 and T-3)
        assert len(groups[2]) == 1
        assert groups[2][0].id == "T-4"

    def test_parallel_groups_all_sequential(self, planner):
        """
        Given fully sequential dependencies,
        Then each group has exactly one task.
        """
        from wigent.core.planner import Task
        
        tasks = [
            Task(id="T-1", description="A", acceptance_criteria=["A"], dependencies=[]),
            Task(id="T-2", description="B", acceptance_criteria=["B"], dependencies=["T-1"]),
            Task(id="T-3", description="C", acceptance_criteria=["C"], dependencies=["T-2"]),
        ]
        
        groups = planner.get_parallel_groups(tasks)
        
        assert len(groups) == 3
        assert all(len(g) == 1 for g in groups)

    def test_parallel_groups_all_independent(self, planner):
        """
        Given no dependencies at all,
        Then all tasks in single group.
        """
        from wigent.core.planner import Task
        
        tasks = [
            Task(id="T-1", description="A", acceptance_criteria=["A"]),
            Task(id="T-2", description="B", acceptance_criteria=["B"]),
            Task(id="T-3", description="C", acceptance_criteria=["C"]),
        ]
        
        groups = planner.get_parallel_groups(tasks)
        
        assert len(groups) == 1
        assert len(groups[0]) == 3

    def test_parallel_groups_empty_list(self, planner):
        """Given empty task list, return empty list."""
        groups = planner.get_parallel_groups([])
        
        assert groups == []

    def test_parallel_groups_detects_cycle(self, planner, cyclic_tasks):
        """Given cyclic dependencies, raise ValueError."""
        with pytest.raises(ValueError, match="cycle"):
            planner.get_parallel_groups(cyclic_tasks)


# =============================================================================
# Test: Next Task Selection
# =============================================================================

class TestNextTask:
    """Tests for get_next_task with dependency tracking."""

    def test_next_task_returns_first_pending(self, planner, sample_tasks):
        """
        Given all tasks pending,
        When get_next_task is called,
        Then return first task with satisfied dependencies.
        """
        planner.get_execution_order(sample_tasks)
        
        next_task = planner.get_next_task()
        
        assert next_task.id == "T-1"  # No dependencies

    def test_next_task_skips_done_tasks(self, planner, sample_tasks):
        """
        Given first task is done,
        When get_next_task is called,
        Then return next ready task.
        """
        planner.get_execution_order(sample_tasks)
        planner.mark_done("T-1")
        
        next_task = planner.get_next_task()
        
        # T-2 and T-3 both ready, return first in order
        assert next_task.id in ["T-2", "T-3"]

    def test_next_task_returns_none_when_all_done(self, planner, sample_tasks):
        """
        Given all tasks done,
        When get_next_task is called,
        Then return None.
        """
        planner.get_execution_order(sample_tasks)
        for task in sample_tasks:
            planner.mark_done(task.id)
        
        next_task = planner.get_next_task()
        
        assert next_task is None

    def test_next_task_returns_none_when_blocked(self, planner, sample_tasks):
        """
        Given all remaining tasks blocked,
        When get_next_task is called,
        Then return None.
        """
        planner.get_execution_order(sample_tasks)
        planner.mark_blocked("T-2", "Waiting for design")
        planner.mark_blocked("T-3", "Waiting for design")
        planner.mark_done("T-1")
        
        next_task = planner.get_next_task()
        
        assert next_task is None

    def test_next_task_after_dependencies_done(self, planner, sample_tasks):
        """
        Given T-1 and T-2 done, T-3 pending,
        When get_next_task is called,
        Then return T-4 (dependencies satisfied).
        """
        planner.get_execution_order(sample_tasks)
        planner.mark_done("T-1")
        planner.mark_done("T-2")
        planner.mark_done("T-3")
        
        next_task = planner.get_next_task()
        
        assert next_task.id == "T-4"


# =============================================================================
# Test: Task Status Management
# =============================================================================

class TestTaskStatusManagement:
    """Tests for mark_done and mark_blocked."""

    def test_mark_done_updates_status(self, planner, sample_tasks):
        """
        Given pending task,
        When mark_done is called,
        Then status changes to done.
        """
        planner.get_execution_order(sample_tasks)
        
        task = planner.mark_done("T-1")
        
        assert task.status == "done"
        assert planner._tasks["T-1"].status == "done"

    def test_mark_done_returns_task(self, planner, sample_tasks):
        """Verify mark_done returns the updated Task object."""
        planner.get_execution_order(sample_tasks)
        
        result = planner.mark_done("T-1")
        
        assert isinstance(result, Task)
        assert result.id == "T-1"

    def test_mark_done_raises_for_unknown_task(self, planner):
        """Given unknown task ID, raise KeyError."""
        with pytest.raises(KeyError, match="not found"):
            planner.mark_done("T-UNKNOWN")

    def test_mark_blocked_updates_status(self, planner, sample_tasks):
        """
        Given pending task,
        When mark_blocked is called,
        Then status changes to blocked with reason.
        """
        planner.get_execution_order(sample_tasks)
        
        task = planner.mark_blocked("T-2", "Waiting for API contract")
        
        assert task.status == "blocked"
        assert "Waiting for API contract" in task.description

    def test_mark_blocked_raises_for_unknown_task(self, planner):
        """Given unknown task ID, raise KeyError."""
        with pytest.raises(KeyError, match="not found"):
            planner.mark_blocked("T-UNKNOWN", "reason")


# =============================================================================
# Test: Markdown Rendering
# =============================================================================

class TestMarkdownRendering:
    """Tests for to_markdown output."""

    def test_markdown_contains_all_tasks(self, planner, sample_tasks):
        """
        Given tasks,
        When to_markdown is called,
        Then output contains all task IDs.
        """
        markdown = planner.to_markdown(sample_tasks)
        
        for task in sample_tasks:
            assert task.id in markdown

    def test_markdown_contains_checkboxes(self, planner, sample_tasks):
        """Verify markdown contains checkbox syntax for acceptance criteria."""
        markdown = planner.to_markdown(sample_tasks)
        
        assert "- [ ]" in markdown

    def test_markdown_shows_status_icons(self, planner, sample_tasks):
        """Verify markdown uses status emojis."""
        planner.get_execution_order(sample_tasks)
        planner.mark_done("T-1")
        
        markdown = planner.to_markdown()
        
        assert "✅" in markdown  # Done
        assert "⬜" in markdown  # Pending

    def test_markdown_contains_dependencies(self, planner, sample_tasks):
        """Verify markdown shows dependency information."""
        markdown = planner.to_markdown(sample_tasks)
        
        assert "Dependencies:" in markdown
        assert "T-1" in markdown  # T-2 depends on T-1

    def test_markdown_contains_effort_estimates(self, planner, sample_tasks):
        """Verify markdown shows effort sizes."""
        markdown = planner.to_markdown(sample_tasks)
        
        for task in sample_tasks:
            assert f"`{task.estimated_effort}`" in markdown

    def test_markdown_contains_execution_order(self, planner, sample_tasks):
        """Verify markdown includes numbered execution order."""
        markdown = planner.to_markdown(sample_tasks)
        
        assert "Execution Order" in markdown
        assert "1." in markdown

    def test_markdown_empty_tasks(self, planner):
        """Given empty tasks, return minimal markdown."""
        markdown = planner.to_markdown([])
        
        assert "0 Tasks" in markdown or "Tasks" in markdown


# =============================================================================
# Test: Mermaid Rendering
# =============================================================================

class TestMermaidRendering:
    """Tests for to_mermaid output."""

    def test_mermaid_starts_with_flowchart(self, planner, sample_tasks):
        """
        Given tasks,
        When to_mermaid is called,
        Then output starts with mermaid flowchart.
        """
        mermaid = planner.to_mermaid(sample_tasks)
        
        assert mermaid.startswith("```mermaid")
        assert "flowchart TD" in mermaid

    def test_mermaid_contains_all_nodes(self, planner, sample_tasks):
        """Verify all task IDs appear as nodes."""
        mermaid = planner.to_mermaid(sample_tasks)
        
        for task in sample_tasks:
            assert task.id in mermaid

    def test_mermaid_contains_dependencies(self, planner, sample_tasks):
        """Verify dependency arrows exist."""
        mermaid = planner.to_mermaid(sample_tasks)
        
        assert "T-1 --> T-2" in mermaid or "T-1 --> T-3" in mermaid

    def test_mermaid_contains_style_definitions(self, planner, sample_tasks):
        """Verify CSS class definitions for status colors."""
        mermaid = planner.to_mermaid(sample_tasks)
        
        assert "classDef done" in mermaid
        assert "classDef inProgress" in mermaid
        assert "classDef blocked" in mermaid

    def test_mermaid_ends_with_backticks(self, planner, sample_tasks):
        """Verify proper markdown code block closing."""
        mermaid = planner.to_mermaid(sample_tasks)
        
        assert mermaid.endswith("```")

    def test_mermaid_escapes_quotes(self, planner):
        """
        Given task description with quotes,
        Then mermaid escapes them safely.
        """
        from wigent.core.planner import Task
        
        tasks = [
            Task(
                id="T-1",
                description='Say "hello" to users',
                acceptance_criteria=["A"]
            )
        ]
        
        mermaid = planner.to_mermaid(tasks)
        
        # Should not break mermaid syntax
        assert "flowchart TD" in mermaid
        assert "```" in mermaid

    def test_mermaid_truncates_long_descriptions(self, planner, sample_tasks):
        """Verify long descriptions are truncated in node labels."""
        mermaid = planner.to_mermaid(sample_tasks)
        
        # Node labels should not be excessively long
        lines = mermaid.split("\n")
        node_lines = [l for l in lines if "[" in l and "]" in l]
        
        for line in node_lines:
            # Extract content between brackets
            content = line.split("[")[1].split("]")[0]
            assert len(content) < 100, f"Node label too long: {content}"


# =============================================================================
# Test: Edge Cases
# =============================================================================

class TestEdgeCases:
    """Tests for boundary conditions."""

    def test_single_task_no_dependencies(self, planner):
        """Given single task with no dependencies, all operations work."""
        from wigent.core.planner import Task
        
        task = Task(id="T-1", description="Only task", acceptance_criteria=["A"])
        
        order = planner.get_execution_order([task])
        groups = planner.get_parallel_groups([task])
        markdown = planner.to_markdown([task])
        mermaid = planner.to_mermaid([task])
        
        assert len(order) == 1
        assert len(groups) == 1
        assert "T-1" in markdown
        assert "T-1" in mermaid

    def test_deep_dependency_chain(self, planner):
        """Given chain of 10 dependent tasks, compute order correctly."""
        from wigent.core.planner import Task
        
        tasks = []
        for i in range(10):
            deps = [f"T-{i}"] if i > 0 else []
            tasks.append(Task(
                id=f"T-{i+1}",
                description=f"Task {i+1}",
                acceptance_criteria=[f"C{i+1}"],
                dependencies=deps
            ))
        
        order = planner.get_execution_order(tasks)
        ids = [t.id for t in order]
        
        for i in range(10):
            assert ids[i] == f"T-{i+1}"

    def test_diamond_dependency_pattern(self, planner):
        """
        Given diamond pattern: A → B → D, A → C → D
        Then B and C parallel, D after both.
        """
        from wigent.core.planner import Task
        
        tasks = [
            Task(id="A", description="A", acceptance_criteria=["A"], dependencies=[]),
            Task(id="B", description="B", acceptance_criteria=["B"], dependencies=["A"]),
            Task(id="C", description="C", acceptance_criteria=["C"], dependencies=["A"]),
            Task(id="D", description="D", acceptance_criteria=["D"], dependencies=["B", "C"]),
        ]
        
        groups = planner.get_parallel_groups(tasks)
        
        assert len(groups[0]) == 1  # A
        assert len(groups[1]) == 2  # B and C parallel
        assert len(groups[2]) == 1  # D

    def test_effort_calculation_total(self, planner, sample_tasks):
        """Verify total effort calculation."""
        markdown = planner.to_markdown(sample_tasks)
        
        # XS=0.5, S=1, M=2 → 0.5 + 1 + 1 + 2 = 4.5 days
        assert "4.5d" in markdown or "4.5 days" in markdown

    def test_llm_json_in_markdown_code_block(self, planner, mock_llm):
        """Given LLM wraps JSON in markdown, parse correctly."""
        mock_llm.generate.return_value = """```json
        [{"id": "T-1", "description": "Test", "acceptance_criteria": ["A"]}]
        ```"""
        
        tasks = planner.create_plan("Test")
        
        assert len(tasks) == 1
        assert tasks[0].id == "T-1"

    def test_llm_json_without_code_block(self, planner, mock_llm):
        """Given raw JSON without markdown wrapper, parse correctly."""
        mock_llm.generate.return_value = '[{"id": "T-1", "description": "Test", "acceptance_criteria": ["A"]}]'
        
        tasks = planner.create_plan("Test")
        
        assert len(tasks) == 1
        assert tasks[0].id == "T-1"
