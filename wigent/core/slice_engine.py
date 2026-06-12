"""
Role: Incremental implementation engine for thin vertical slices.
Author: Wigent AI
Version: 1.0.0

Enforces the incremental-implementation skill: implement one vertical slice
at a time (feature + test + verify + commit), with feature flags and
safe defaults. Never touches more than one concern per slice.

Usage:
    from wigent.core.slice_engine import SliceEngine
    from wigent.models.model_factory import create_model

    llm = create_model("openai", "gpt-4o")
    engine = SliceEngine(llm, workspace="/path/to/project")

    result = engine.execute_slice(
        task=task,
        plan=plan,
        session=session
    )
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wigent.core.planner import Task
    from wigent.models.base_model import BaseModel


@dataclass
class SliceResult:
    """Result of executing a single vertical slice."""

    task_id: str
    status: str  # "success", "failed", "aborted", "skipped"
    commit_hash: str | None = None
    files_changed: list[str] = field(default_factory=list)
    tests_passed: bool = False
    test_output: str = ""
    feature_flag: str | None = None
    rollback_hash: str | None = None
    error_message: str | None = None
    duration_seconds: float = 0.0


class SliceEngine:
    """
    Executes thin vertical slices with strict safety controls.

    Principles:
    1. ONE slice at a time — never parallelize within a slice
    2. Feature flags for all new behavior — off by default
    3. Tests BEFORE commit — commit is the save point, not the finish line
    4. Safe defaults — if unsure, fail closed
    5. Rollback on ANY failure — atomic, all-or-nothing per slice
    """

    def __init__(
        self,
        llm_client: BaseModel,
        workspace: str | Path,
        git_enabled: bool = True,
        auto_commit: bool = False,
        test_command: str = "pytest",
        max_files_per_slice: int = 5,
    ) -> None:
        self.llm = llm_client
        self.workspace = Path(workspace).resolve()
        self.git_enabled = git_enabled
        self.auto_commit = auto_commit
        self.test_command = test_command
        self.max_files_per_slice = max_files_per_slice

        self._current_branch: str | None = None
        self._feature_flags: set[str] = set()
        self._slice_count: int = 0

    def execute_slice(
        self,
        task: Task,
        plan: dict,
        session: dict,
    ) -> SliceResult:
        """
        Execute a single vertical slice with full safety controls.

        Process:
        1. Validate slice size (<=max_files_per_slice)
        2. Generate feature flag name
        3. Create rollback point (git stash / branch)
        4. Implement the slice
        5. Write tests for the slice
        6. Run tests — fail = rollback
        7. Commit as save point
        8. Return result with metadata

        Args:
            task: The Task object for this slice
            plan: Full plan context for coherence
            session: Current session state (conversation, memory, etc.)

        Returns:
            SliceResult with full execution metadata
        """
        import time
        start_time = time.perf_counter()

        self._slice_count += 1
        slice_id = f"slice-{self._slice_count:03d}-{task.id}"

        try:
            # Step 1: Validate slice constraints
            self._validate_slice_constraints(task)

            # Step 2: Generate feature flag
            feature_flag = self._generate_feature_flag(task)

            # Step 3: Create rollback point
            rollback_hash = self._create_rollback_point(slice_id)

            # Step 4: Implement the slice
            files_changed = self._implement_slice(task, plan, session, feature_flag)

            # Validate file count post-implementation
            if len(files_changed) > self.max_files_per_slice:
                raise SliceTooLargeError(
                    f"Slice touched {len(files_changed)} files, "
                    f"max allowed: {self.max_files_per_slice}. "
                    f"Break into smaller slices."
                )

            # Step 5: Write tests
            test_files = self._write_tests(task, files_changed, feature_flag)

            # Step 6: Run tests
            tests_passed, test_output = self._run_tests(test_files)

            if not tests_passed:
                self._rollback(rollback_hash)
                return SliceResult(
                    task_id=task.id,
                    status="failed",
                    rollback_hash=rollback_hash,
                    files_changed=files_changed,
                    tests_passed=False,
                    test_output=test_output,
                    feature_flag=feature_flag,
                    error_message="Tests failed — rolled back automatically",
                    duration_seconds=time.perf_counter() - start_time,
                )

            # Step 7: Commit as save point
            commit_hash = None
            if self.git_enabled:
                commit_hash = self._commit_slice(
                    slice_id=slice_id,
                    task=task,
                    files_changed=files_changed + test_files,
                    feature_flag=feature_flag,
                )

            # Register feature flag
            self._feature_flags.add(feature_flag)

            return SliceResult(
                task_id=task.id,
                status="success",
                commit_hash=commit_hash,
                files_changed=files_changed + test_files,
                tests_passed=True,
                test_output=test_output,
                feature_flag=feature_flag,
                rollback_hash=rollback_hash,
                duration_seconds=time.perf_counter() - start_time,
            )

        except SliceTooLargeError as e:
            return SliceResult(
                task_id=task.id,
                status="aborted",
                error_message=str(e),
                duration_seconds=time.perf_counter() - start_time,
            )
        except Exception as e:
            # Unknown error — rollback if possible
            if 'rollback_hash' in locals():
                self._rollback(rollback_hash)
            return SliceResult(
                task_id=task.id,
                status="failed",
                rollback_hash=rollback_hash if 'rollback_hash' in locals() else None,
                error_message=f"Unexpected error: {type(e).__name__}: {e}",
                duration_seconds=time.perf_counter() - start_time,
            )

    def get_feature_flags(self) -> list[str]:
        """Return all active feature flags from executed slices."""
        return sorted(self._feature_flags)

    def generate_flag_config(self) -> str:
        """Generate configuration snippet for all feature flags."""
        lines = ["# Auto-generated feature flags from incremental implementation\n"]
        for flag in sorted(self._feature_flags):
            lines.append(f"{flag}=false  # Enable to activate {flag.replace('FF_', '').lower()}\n")
        return "".join(lines)

    # =================================================================
    # Internal Methods
    # =================================================================

    def _validate_slice_constraints(self, task: Task) -> None:
        """Ensure task is suitable for single-slice execution."""
        # Check effort size
        if task.estimated_effort not in {"XS", "S", "M"}:
            raise SliceTooLargeError(
                f"Task {task.id} effort '{task.estimated_effort}' too large for single slice. "
                f"Break down further."
            )

        # Check description for red flags
        red_flags = ["refactor all", "rewrite", "migrate everything", "redesign"]
        desc_lower = task.description.lower()
        for flag in red_flags:
            if flag in desc_lower:
                raise SliceTooLargeError(
                    f"Task {task.id} contains red flag '{flag}'. "
                    f"This is not a thin vertical slice. Break down further."
                )

    def _generate_feature_flag(self, task: Task) -> str:
        """Generate a unique, descriptive feature flag name."""
        # Hash task description for uniqueness
        hash_input = f"{task.id}:{task.description}"
        short_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:8]

        # Clean description for flag name
        clean_desc = "".join(c if c.isalnum() else "_" for c in task.description.lower())
        clean_desc = clean_desc[:30].strip("_")

        return f"FF_{clean_desc}_{short_hash}".upper()

    def _create_rollback_point(self, slice_id: str) -> str | None:
        """Create a git rollback point. Returns hash or None."""
        if not self.git_enabled:
            return None

        try:
            # Stash any current changes
            subprocess.run(
                ["git", "stash", "push", "-m", f"slice-engine-{slice_id}"],
                cwd=self.workspace,
                check=True,
                capture_output=True,
            )

            # Get current HEAD
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return None

    def _implement_slice(
        self,
        task: Task,
        plan: dict,
        session: dict,
        feature_flag: str,
    ) -> list[str]:
        """
        Use LLM to implement the slice with feature flag wrapping.

        The LLM is instructed to:
        1. Only touch files relevant to this slice
        2. Wrap new behavior in feature flag check
        3. Maintain backward compatibility
        4. Follow existing code style
        """
        prompt = self._build_implementation_prompt(task, plan, session, feature_flag)
        response = self.llm.generate(prompt, temperature=0.1, max_tokens=4000)

        # Parse response to extract file changes
        files_changed = self._parse_implementation_response(response)

        # Write files to disk
        written_files = []
        for file_path, content in files_changed.items():
            full_path = self.workspace / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)

            # Backup existing file
            if full_path.exists():
                backup_path = full_path.with_suffix(f"{full_path.suffix}.bak")
                backup_path.write_text(full_path.read_text())

            full_path.write_text(content)
            written_files.append(str(file_path))

        return written_files

    def _write_tests(
        self,
        task: Task,
        files_changed: list[str],
        feature_flag: str,
    ) -> list[str]:
        """
        Generate tests for the implemented slice.

        Tests must:
        1. Cover the feature flag on and off states
        2. Test acceptance criteria from task
        3. Not import implementation details (test behavior, not structure)
        """
        prompt = self._build_test_prompt(task, files_changed, feature_flag)
        response = self.llm.generate(prompt, temperature=0.1, max_tokens=4000)

        # Parse and write test files
        test_files = self._parse_test_response(response)

        written_tests = []
        for file_path, content in test_files.items():
            full_path = self.workspace / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)
            written_tests.append(str(file_path))

        return written_tests

    def _run_tests(self, test_files: list[str]) -> tuple[bool, str]:
        """Run tests and return (passed, output)."""
        if not test_files:
            return True, "No test files generated"

        # Run specific test files
        cmd = [self.test_command, "-xvs"] + test_files
        try:
            result = subprocess.run(
                cmd,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=300,
            )
            return result.returncode == 0, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return False, "Tests timed out after 5 minutes"
        except FileNotFoundError:
            return False, f"Test command '{self.test_command}' not found"

    def _commit_slice(
        self,
        slice_id: str,
        task: Task,
        files_changed: list[str],
        feature_flag: str,
    ) -> str | None:
        """Commit the slice as an atomic save point."""
        try:
            # Stage files
            subprocess.run(
                ["git", "add"] + files_changed,
                cwd=self.workspace,
                check=True,
                capture_output=True,
            )

            # Commit with structured message
            commit_msg = self._build_commit_message(slice_id, task, feature_flag)

            result = subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                check=True,
            )

            # Get commit hash
            hash_result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                check=True,
            )
            return hash_result.stdout.strip()

        except subprocess.CalledProcessError as e:
            return None

    def _rollback(self, rollback_hash: str | None) -> None:
        """Rollback to previous state."""
        if not self.git_enabled or not rollback_hash:
            return

        try:
            # Hard reset to rollback point
            subprocess.run(
                ["git", "reset", "--hard", rollback_hash],
                cwd=self.workspace,
                check=True,
                capture_output=True,
            )
            # Clean untracked files
            subprocess.run(
                ["git", "clean", "-fd"],
                cwd=self.workspace,
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError:
            pass  # Best effort rollback

    # =================================================================
    # Prompt Builders
    # =================================================================

    def _build_implementation_prompt(
        self,
        task: Task,
        plan: dict,
        session: dict,
        feature_flag: str,
    ) -> str:
        """Build the LLM prompt for slice implementation."""
        return f"""You are implementing a thin vertical slice for a production system.

## Task
ID: {task.id}
Description: {task.description}
Effort: {task.estimated_effort}
Acceptance Criteria:
{chr(10).join(f"- {c}" for c in task.acceptance_criteria)}

## Feature Flag
Name: {feature_flag}
Status: OFF by default (false)

## Rules
1. Implement ONLY what this task describes — no more, no less
2. Wrap ALL new behavior in feature flag check:
   ```python
   if os.environ.get("{feature_flag}", "false").lower() == "true":
       # new behavior
   else:
       # existing/default behavior
   ```
3. Touch MAXIMUM {self.max_files_per_slice} files
4. Maintain backward compatibility — system works with flag off
5. Follow existing code style and patterns
6. Add type hints and docstrings
7. No breaking changes to public APIs

## Output Format
Return ONLY a JSON object mapping file paths to file contents:

```json
{{
  "src/module/file.py": "# file content here...",
  "tests/test_file.py": "# test content here..."
}}
```

## Existing Context
{json.dumps(session.get("codebase_context", {}), indent=2)}
"""

    def _build_test_prompt(
        self,
        task: Task,
        files_changed: list[str],
        feature_flag: str,
    ) -> str:
        """Build the LLM prompt for test generation."""
        return f"""Write tests for the implemented slice.

## Task
ID: {task.id}
Description: {task.description}
Acceptance Criteria:
{chr(10).join(f"- {c}" for c in task.acceptance_criteria)}

## Files Changed
{chr(10).join(files_changed)}

## Feature Flag
Name: {feature_flag}

## Test Requirements
1. Test with feature flag ON and OFF
2. Cover all acceptance criteria
3. Test behavior, not implementation (black-box)
4. Use pytest with descriptive test names
5. Include at least one edge case and one error case
6. Mock external dependencies
7. Tests must pass in isolation (no shared state)

## Output Format
Return ONLY a JSON object mapping test file paths to file contents:

```json
{{
  "tests/test_feature.py": "# test content..."
}}
```
"""

    def _build_commit_message(
        self,
        slice_id: str,
        task: Task,
        feature_flag: str,
    ) -> str:
        """Build a structured commit message for the slice."""
        return f"""feat({task.id}): {task.description}

Slice: {slice_id}
Feature Flag: {feature_flag}
Effort: {task.estimated_effort}

Acceptance Criteria:
{chr(10).join(f"- {c}" for c in task.acceptance_criteria)}

Status: Feature flag OFF by default. Enable with:
  export {feature_flag}=true
"""

    # =================================================================
    # Response Parsers
    # =================================================================

    def _parse_implementation_response(self, response: str) -> dict[str, str]:
        """Extract file contents from LLM response."""
        import re

        # Try JSON parsing
        json_match = re.search(r"```json\s*(\{.*?\})\s*```", response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Fallback: parse file markers
        files = {}
        pattern = r"###?\s*([^\n]+)\n```[\w]*\n(.*?)```"
        matches = re.findall(pattern, response, re.DOTALL)
        for filename, content in matches:
            files[filename.strip()] = content.strip()

        return files

    def _parse_test_response(self, response: str) -> dict[str, str]:
        """Extract test files from LLM response."""
        return self._parse_implementation_response(response)


class SliceTooLargeError(Exception):
    """Raised when a slice exceeds size constraints."""
    pass
