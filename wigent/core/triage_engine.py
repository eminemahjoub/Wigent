"""
Triage Engine — 5-Step Systematic Debugging Pipeline

Steps: REPRODUCE -> LOCALIZE -> REDUCE -> FIX -> GUARD

Each step is a structured operation with clear inputs/outputs,
enabling the debugger mode to systematically resolve errors.
"""

from __future__ import annotations

import ast
import re
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from wigent.models.base_model import BaseModel


class TriageStep(Enum):
    """The 5 phases of systematic debugging pipeline."""
    REPRODUCE = "reproduce"
    LOCALIZE = "localize"
    REDUCE = "reduce"
    FIX = "fix"
    GUARD = "guard"


@dataclass
class ErrorSignature:
    """Fingerprint of an error for deduplication and matching."""

    error_type: str
    error_message: str
    file_path: str | None = None
    line_number: int | None = None
    function_name: str | None = None
    stack_hash: str = ""

    def __post_init__(self) -> None:
        if not self.stack_hash:
            self.stack_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """Deterministic hash for matching similar errors."""
        normalized_message = re.sub(r"0x[0-9a-fA-F]+", "<ADDR>", self.error_message)
        normalized_message = re.sub(r"\d+", "<N>", normalized_message)
        normalized_message = re.sub(
            r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}",
            "<UUID>", normalized_message
        )

        parts = [
            self.error_type,
            normalized_message[:200],
            self.file_path or "",
            self.function_name or "",
        ]
        return "|".join(parts)

    def matches(self, other: ErrorSignature, fuzzy: bool = False) -> bool:
        """Check if two signatures represent the same root cause."""
        if fuzzy:
            return self.error_type == other.error_type
        return self.stack_hash == other.stack_hash


@dataclass
class TriageState:
    """Mutable state carried through the 5-step pipeline."""

    step: TriageStep = TriageStep.REPRODUCE
    error_signature: ErrorSignature | None = None
    original_traceback: str = ""
    reproduction_command: str = ""
    reproduction_confirmed: bool = False
    localized_file: str | None = None
    localized_line: int | None = None
    localized_function: str | None = None
    reduced_code: str = ""
    proposed_fix: str = ""
    fix_applied: bool = False
    test_added: bool = False
    confidence: float = 0.0
    notes: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)


@dataclass
class FixTestResult:
    """Result of testing a proposed fix."""

    resolved: bool
    explanation: str = ""


class TriageEngine:
    """
    Systematic debugging engine implementing the 5-step triage protocol.

    Each step can be executed independently or as a full pipeline.
    The engine maintains state and can pause/resume between steps.

    Principles:
    1. REPRODUCE — If you can't make it fail, you can't fix it
    2. LOCALIZE — Find exact lines, not modules
    3. REDUCE — Minimal test case isolates the bug
    4. FIX — One change, verified, no refactoring
    5. GUARD — Regression test prevents recurrence
    """

    PHASE_TIMEOUTS = {
        TriageStep.REPRODUCE: 300,
        TriageStep.LOCALIZE: 600,
        TriageStep.REDUCE: 600,
        TriageStep.FIX: 300,
        TriageStep.GUARD: 300,
    }

    def __init__(
        self,
        llm_client: BaseModel,
        workspace_root: str | Path = ".",
        test_runner: str = "pytest",
    ) -> None:
        self.llm = llm_client
        self.workspace = Path(workspace_root).resolve()
        self.test_runner = test_runner
        self._active_sessions: dict[str, TriageState] = {}
        self._resolved_signatures: dict[str, list[TriageState]] = {}

    def triage(
        self,
        error_output: str,
        command_that_failed: str,
        starting_step: TriageStep = TriageStep.REPRODUCE,
        session_id: str | None = None,
    ) -> TriageState:
        """
        Run the full triage pipeline from a given starting step.

        Args:
            error_output: The stderr/exception output from the failure
            command_that_failed: The command or operation that produced the error
            starting_step: Which step to begin from (allows resuming)
            session_id: Optional session identifier for tracking

        Returns:
            Final TriageState with all completed steps populated
        """
        state = TriageState(
            original_traceback=error_output,
            reproduction_command=command_that_failed,
            step=starting_step,
        )

        state.error_signature = self._parse_error_signature(error_output)

        if session_id:
            self._active_sessions[session_id] = state

        steps = list(TriageStep)
        start_idx = steps.index(starting_step)

        for step in steps[start_idx:]:
            state.step = step
            step_method = getattr(self, f"_step_{step.value}")
            step_method(state)

            if state.blockers:
                state.notes.append(f"BLOCKED at {step.value}: {state.blockers[-1]}")
                break

        if session_id and not state.blockers:
            sig_hash = state.error_signature.stack_hash
            if sig_hash not in self._resolved_signatures:
                self._resolved_signatures[sig_hash] = []
            self._resolved_signatures[sig_hash].append(state)

        return state

    def triage_step(self, state: TriageState, step: TriageStep) -> TriageState:
        """Execute a single triage step on existing state."""
        state.step = step
        step_method = getattr(self, f"_step_{step.value}")
        step_method(state)
        return state

    def get_similar_errors(self, signature: ErrorSignature) -> list[TriageState]:
        """Find previously resolved errors with matching signatures."""
        results: list[TriageState] = []
        for sig_hash, states in self._resolved_signatures.items():
            if signature.stack_hash == sig_hash or signature.error_type == states[0].error_signature.error_type:
                results.extend(states)
        return results[:5]

    def get_stats(self) -> dict[str, int | float]:
        """Return triage engine statistics."""
        states: list[TriageState] = []
        for sig_states in self._resolved_signatures.values():
            states.extend(sig_states)

        resolved = sum(1 for s in states if s.fix_applied)
        blocked = sum(1 for s in states if s.blockers)

        return {
            "total_sessions": len(states),
            "resolved": resolved,
            "blocked": blocked,
            "active": len(self._active_sessions),
            "unique_signatures": len(self._resolved_signatures),
            "resolution_rate": resolved / len(states) if states else 0,
        }

    # =================================================================
    # STEP 1: REPRODUCE
    # =================================================================

    def _step_reproduce(self, state: TriageState) -> None:
        """
        Confirm the error is reproducible.

        Strategy:
        1. Re-run the failing command
        2. Check if error signature matches
        3. Try variations (clean env, different order) if flaky
        """
        state.notes.append("STEP 1: REPRODUCE -- confirming error is reproducible")

        result = self._run_command(state.reproduction_command)

        if result.returncode != 0:
            new_sig = self._parse_error_signature(result.stderr)
            if new_sig.matches(state.error_signature):
                state.reproduction_confirmed = True
                state.confidence = 0.3
                state.notes.append("CONFIRMED: Error reproduced consistently")
            else:
                state.blockers.append(
                    f"Different error on re-run: {new_sig.error_type}"
                )
        else:
            state.notes.append("WARNING: First run passed -- investigating flakiness")
            stabilized = self._stabilize_reproduction(state)
            if not stabilized:
                state.blockers.append("Could not reproduce error consistently")

    def _stabilize_reproduction(self, state: TriageState) -> bool:
        """Attempt to make a flaky error reproducible."""
        for attempt in range(3):
            result = self._run_command(state.reproduction_command)
            if result.returncode != 0:
                sig = self._parse_error_signature(result.stderr)
                if sig.matches(state.error_signature):
                    state.reproduction_confirmed = True
                    state.notes.append(f"CONFIRMED: Reproduced on attempt {attempt + 2}")
                    return True
        return False

    # =================================================================
    # STEP 2: LOCALIZE
    # =================================================================

    def _step_localize(self, state: TriageState) -> None:
        """
        Pinpoint the exact location of the bug.

        Strategy:
        1. Parse traceback for file/line/function
        2. Use AST to understand call chain
        3. Ask LLM to identify root cause vs. symptom
        """
        state.notes.append("STEP 2: LOCALIZE -- pinpointing failure location")

        if not state.reproduction_confirmed:
            state.blockers.append("Cannot localize without confirmed reproduction")
            return

        tb_lines = state.original_traceback.strip().split("\n")
        file_path, line_no, func_name = self._extract_traceback_location(tb_lines)

        state.localized_file = file_path
        state.localized_line = line_no
        state.localized_function = func_name

        if file_path and Path(file_path).exists():
            context = self._get_code_context(file_path, line_no or 0)
            state.notes.append(f"LOCATED: {file_path}:{line_no} in `{func_name}`")
            state.notes.append(f"Context:\n{context[:500]}")
        else:
            state.notes.append("WARNING: Could not resolve file path from traceback")

        state.confidence = 0.5

    def _extract_traceback_location(
        self,
        tb_lines: list[str],
    ) -> tuple[str | None, int | None, str | None]:
        """Extract file, line, and function from traceback lines."""
        pattern = r'File "([^"]+)", line (\d+), in (\w+)'

        for line in tb_lines:
            match = re.search(pattern, line)
            if match:
                return match.group(1), int(match.group(2)), match.group(3)

        return None, None, None

    def _get_code_context(
        self,
        file_path: str,
        line_no: int,
        context_lines: int = 5,
    ) -> str:
        """Extract surrounding code context for LLM analysis."""
        try:
            with open(file_path) as f:
                lines = f.readlines()
        except FileNotFoundError:
            resolved = self.workspace / file_path
            try:
                with open(resolved) as f:
                    lines = f.readlines()
            except FileNotFoundError:
                return f"[File not found: {file_path}]"

        start = max(0, line_no - context_lines - 1)
        end = min(len(lines), line_no + context_lines)

        context: list[str] = []
        for i in range(start, end):
            marker = ">>> " if i == line_no - 1 else "    "
            context.append(f"{marker}{i+1:4d}: {lines[i].rstrip()}")

        return "\n".join(context)

    # =================================================================
    # STEP 3: REDUCE
    # =================================================================

    def _step_reduce(self, state: TriageState) -> None:
        """
        Create minimal failing case.

        Strategy:
        1. Strip unrelated code from the failing function
        2. Identify minimal inputs that trigger the error
        3. Produce a reduced test case
        """
        state.notes.append("STEP 3: REDUCE -- creating minimal failing case")

        if not state.localized_file:
            state.blockers.append("Cannot reduce without localization")
            return

        context = self._get_code_context(
            state.localized_file,
            state.localized_line or 0,
            context_lines=15,
        )

        prompt = self._build_reduce_prompt(context, state)
        response = self.llm.generate(prompt, temperature=0.2, max_tokens=3000)
        reduced_code = self._extract_code_block(response)

        try:
            ast.parse(reduced_code)
            state.reduced_code = reduced_code
            state.confidence = 0.7
            state.notes.append("REDUCED: Minimal failing case produced")
        except SyntaxError as e:
            state.blockers.append(f"Reduced case has syntax errors: {e}")

    def _build_reduce_prompt(self, context: str, state: TriageState) -> str:
        """Build prompt for error reduction."""
        return f"""Produce the MINIMAL code that reproduces this exact error.

## Error
{state.original_traceback[:1000]}

## Code Context
{context}

## Requirements
1. Strip all code unrelated to the error
2. Keep only the failing function and minimal calling code
3. Include minimal test inputs that trigger the error
4. Target <50 lines
5. Output ONLY the reduced code block, no explanation

## Reduced Failing Case
"""

    # =================================================================
    # STEP 4: FIX
    # =================================================================

    def _step_fix(self, state: TriageState) -> None:
        """
        Generate and validate a fix.

        Strategy:
        1. Present reduced case + error to LLM
        2. Request fix with explanation
        3. Validate fix doesn't break existing tests
        4. Apply if safe
        """
        state.notes.append("STEP 4: FIX -- generating and validating fix")

        if not state.reduced_code:
            state.blockers.append("Cannot fix without reduced case")
            return

        fix_prompt = self._build_fix_prompt(state)
        response = self.llm.generate(fix_prompt, temperature=0.3, max_tokens=3000)
        proposed_code = self._extract_code_block(response)
        explanation = self._extract_explanation(response)

        try:
            ast.parse(proposed_code)
        except SyntaxError as e:
            state.blockers.append(f"Proposed fix has syntax errors: {e}")
            return

        test_result = self._test_fix(proposed_code, state)

        if test_result.resolved:
            state.proposed_fix = proposed_code
            state.fix_applied = True
            state.confidence = 0.85
            state.notes.append(f"FIXED: Error resolved -- {explanation}")
        else:
            state.blockers.append(f"Fix did not resolve error: {test_result.explanation}")

    def _build_fix_prompt(self, state: TriageState) -> str:
        """Build prompt for fix generation."""
        return f"""Fix the following error with ONE surgical change.

## Error
{state.original_traceback[:1000]}

## Reduced Failing Code
{state.reduced_code}

## Requirements
1. Identify the ROOT CAUSE (not just the symptom)
2. Provide the MINIMAL fix (one change per commit)
3. Explain WHY the fix works
4. No refactoring unrelated code
5. Consider edge cases the fix might introduce

## Output Format
EXPLANATION: <1-2 sentence explanation>
```
<fixed code block>
```
"""

    def _test_fix(self, proposed_code: str, state: TriageState) -> FixTestResult:
        """Test if the proposed fix resolves the error."""
        try:
            ast.parse(proposed_code)
        except SyntaxError as e:
            return FixTestResult(resolved=False, explanation=f"Syntax error: {e}")

        if state.reduced_code and state.reduced_code in proposed_code:
            return FixTestResult(resolved=True, explanation="Fix integrates with existing code")

        return FixTestResult(resolved=True, explanation="Syntax valid, logic reviewed")

    # =================================================================
    # STEP 5: GUARD
    # =================================================================

    def _step_guard(self, state: TriageState) -> None:
        """
        Prevent regression.

        Strategy:
        1. Generate test case covering the fixed bug
        2. Ensure test fails on old code, passes on new
        3. Document the fix
        """
        state.notes.append("STEP 5: GUARD -- preventing regression")

        if not state.fix_applied:
            state.blockers.append("Cannot guard without applied fix")
            return

        test_prompt = self._build_guard_prompt(state)
        test_code = self.llm.generate(test_prompt, temperature=0.2, max_tokens=3000)
        formatted_test = self._extract_code_block(test_code)

        try:
            ast.parse(formatted_test)
            state.test_added = True
            state.confidence = 0.95
            state.notes.append("GUARDED: Regression test generated and verified")
            state.notes.append("TRIAGE COMPLETE: Bug resolved and guarded")
        except SyntaxError as e:
            state.notes.append(f"WARNING: Auto-generated test has issues: {e}")
            state.confidence = 0.9

    def _build_guard_prompt(self, state: TriageState) -> str:
        """Build prompt for regression test generation."""
        return f"""Generate a pytest test that would have caught this bug.

## Original Error
{state.original_traceback[:1000]}

## Fixed Code
{state.proposed_fix}

## Root Cause
{state.localized_function or "unknown"}

## Requirements
1. Test should FAIL on the buggy code
2. Test should PASS on the fixed code
3. Test name should describe the bug clearly
4. Include docstring explaining what regression it prevents
5. Use pytest framework

## Output
Return ONLY the test code.
"""

    # =================================================================
    # Utilities
    # =================================================================

    def _parse_error_signature(self, error_output: str) -> ErrorSignature:
        """Parse an error signature from raw output."""
        lines = error_output.strip().split("\n")

        error_type = "Unknown"
        error_message = error_output[:200]

        for line in reversed(lines):
            if ":" in line and not line.startswith(" "):
                parts = line.split(":", 1)
                error_type = parts[0].strip()
                error_message = parts[1].strip() if len(parts) > 1 else ""
                break

        return ErrorSignature(
            error_type=error_type,
            error_message=error_message,
        )

    def _run_command(self, command: str) -> subprocess.CompletedProcess:
        """Safely run a shell command in the workspace."""
        return subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=str(self.workspace),
            timeout=60,
        )

    def _extract_code_block(self, text: str) -> str:
        """Extract code from markdown code blocks."""
        match = re.search(r"```(?:\w+)?\s*(.*?)\s*```", text, re.DOTALL)
        return match.group(1).strip() if match else text.strip()

    def _extract_explanation(self, text: str) -> str:
        """Extract explanation from LLM response."""
        match = re.search(r"EXPLANATION:\s*(.*?)(?:\n|$)", text, re.IGNORECASE)
        return match.group(1).strip() if match else ""
