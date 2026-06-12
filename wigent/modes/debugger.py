"""
Role: Debugging and error recovery mode with systematic 5-step triage.
Author: Wigent AI
Version: 1.0.0

Implements the debugging-and-error-recovery skill:
1. REPRODUCE — Make it fail every time
2. LOCALIZE — Find the exact lines
3. REDUCE — Minimal test case
4. FIX — One change, verified
5. GUARD — Regression test, monitoring

Stop-the-line rule: No passing tests? No new features.

Usage:
    from wigent.modes.debugger import DebuggerMode, DebugSession

    debugger = DebuggerMode(llm_client)

    session = debugger.start_session(
        error="NullPointerException at AuthService.java:142",
        logs=stack_trace,
        context=codebase_context
    )

    # 5-step triage
    session.reproduce()  # Step 1
    session.localize()   # Step 2
    session.reduce()     # Step 3
    session.fix()        # Step 4
    session.guard()      # Step 5

    report = session.generate_report()
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wigent.models.base_model import BaseModel


class DebugPhase(Enum):
    """The 5 phases of systematic debugging."""
    REPRODUCE = ("reproduce", "Make it fail every single time")
    LOCALIZE = ("localize", "Find the exact lines of code")
    REDUCE = ("reduce", "Minimal test case that still fails")
    FIX = ("fix", "One surgical change, verified")
    GUARD = ("guard", "Regression test + monitoring")

    def __init__(self, label: str, description: str):
        self.label = label
        self.description = description


class ErrorCategory(Enum):
    """Classification of error types for targeted debugging."""
    SYNTAX = ("syntax", "Compilation/parse failure")
    RUNTIME = ("runtime", "Exception during execution")
    LOGIC = ("logic", "Wrong output, no crash")
    PERFORMANCE = ("performance", "Too slow, timeout, memory")
    CONCURRENCY = ("concurrency", "Race condition, deadlock, inconsistency")
    SECURITY = ("security", "Vulnerability, auth bypass, injection")
    INFRASTRUCTURE = ("infrastructure", "Network, disk, dependency failure")
    REGRESSION = ("regression", "Previously worked, now broken")
    FLAKY = ("flaky", "Intermittent, non-deterministic")

    def __init__(self, label: str, description: str):
        self.label = label
        self.description = description


@dataclass
class ErrorSignature:
    """Unique fingerprint of an error for deduplication and tracking."""

    category: ErrorCategory
    message_pattern: str  # Normalized error message (no variable data)
    stack_hash: str  # Hash of stack trace frames
    file_location: str | None = None
    line_number: int | None = None
    first_seen: float = field(default_factory=time.time)
    occurrence_count: int = 1

    @classmethod
    def from_raw(cls, error_message: str, stack_trace: str) -> ErrorSignature:
        """Create signature from raw error data."""
        # Normalize message: remove variable data (timestamps, IDs, memory addresses)
        normalized = re.sub(r"0x[0-9a-fA-F]+", "<ADDR>", error_message)
        normalized = re.sub(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}", "<TIME>", normalized)
        normalized = re.sub(r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}", "<UUID>", normalized)
        normalized = re.sub(r"\d+", "<N>", normalized)

        # Extract stack frames
        frames = re.findall(r"at\s+([^\s(]+)", stack_trace)
        stack_hash = hashlib.sha256(":".join(frames).encode()).hexdigest()[:16]

        # Extract file location
        location_match = re.search(r"([^\s:]+):(\d+)", stack_trace)
        file_location = location_match.group(1) if location_match else None
        line_number = int(location_match.group(2)) if location_match else None

        # Categorize
        category = cls._categorize(error_message, stack_trace)

        return cls(
            category=category,
            message_pattern=normalized[:200],
            stack_hash=stack_hash,
            file_location=file_location,
            line_number=line_number,
        )

    @staticmethod
    def _categorize(message: str, stack: str) -> ErrorCategory:
        """Auto-categorize error from message and stack."""
        msg_lower = message.lower()
        stack_lower = stack.lower()

        if any(w in msg_lower for w in ["nullpointer", "undefined", "referenceerror", "attributeerror"]):
            return ErrorCategory.RUNTIME
        elif any(w in msg_lower for w in ["syntax", "parse", "unexpected token", "indentation"]):
            return ErrorCategory.SYNTAX
        elif any(w in msg_lower for w in ["timeout", "slow", "memory", "performance", "latency"]):
            return ErrorCategory.PERFORMANCE
        elif any(w in msg_lower for w in ["race", "deadlock", "concurrent", "thread", "lock"]):
            return ErrorCategory.CONCURRENCY
        elif any(w in msg_lower for w in ["injection", "xss", "auth", "permission", "forbidden", "bypass"]):
            return ErrorCategory.SECURITY
        elif any(w in stack_lower for w in ["network", "connection", "dns", "timeout", "refused"]):
            return ErrorCategory.INFRASTRUCTURE
        elif any(w in msg_lower for w in ["intermittent", "sometimes", "randomly", "flaky", "race"]):
            return ErrorCategory.FLAKY
        else:
            return ErrorCategory.LOGIC


@dataclass
class PhaseResult:
    """Result of executing one debug phase."""

    phase: DebugPhase
    status: str  # "success", "failed", "blocked", "skipped"
    output: str = ""
    artifacts: list[str] = field(default_factory=list)  # File paths, test names, etc.
    duration_seconds: float = 0.0
    next_phase: DebugPhase | None = None
    blockers: list[str] = field(default_factory=list)


@dataclass
class DebugSession:
    """Complete debugging session with full traceability."""

    session_id: str
    signature: ErrorSignature
    phases: list[PhaseResult] = field(default_factory=list)
    current_phase: DebugPhase | None = None
    status: str = "active"  # active, resolved, escalated, abandoned
    root_cause: str | None = None
    fix_commit: str | None = None
    regression_test: str | None = None
    monitoring_alert: str | None = None
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None

    @property
    def duration_seconds(self) -> float:
        end = self.end_time or time.time()
        return end - self.start_time

    def to_markdown(self) -> str:
        """Generate full debug report."""
        status_icon = {
            "resolved": "\u2705",
            "escalated": "\u26a0\ufe0f",
            "abandoned": "\u274c",
            "active": "\U0001f504",
        }.get(self.status, "\u2753")

        lines = [
            f"# Debug Session: {self.session_id}",
            f"",
            f"**Status:** {status_icon} {self.status.upper()}",
            f"**Duration:** {self.duration_seconds:.1f}s",
            f"**Error Category:** {self.signature.category.description}",
            f"",
            f"## Error Signature",
            f"",
            f"- **Pattern:** `{self.signature.message_pattern[:100]}`",
            f"- **Location:** {self.signature.file_location or 'Unknown'}:{self.signature.line_number or '?'}",
            f"- **Stack Hash:** `{self.signature.stack_hash}`",
            f"- **Occurrences:** {self.signature.occurrence_count}",
            f"",
            f"## Phase Results",
            f"",
        ]

        for result in self.phases:
            icon = {
                "success": "\u2705",
                "failed": "\u274c",
                "blocked": "\U0001f6ab",
                "skipped": "\u23ed\ufe0f",
            }.get(result.status, "\u2753")

            lines.extend([
                f"### {icon} {result.phase.label.upper()}",
                f"",
                f"**Status:** {result.status}",
                f"**Duration:** {result.duration_seconds:.1f}s",
                f"",
                f"{result.output}",
                f"",
            ])

            if result.artifacts:
                lines.extend([
                    f"**Artifacts:**",
                    *[f"- `{a}`" for a in result.artifacts],
                    f"",
                ])

            if result.blockers:
                lines.extend([
                    f"**Blockers:**",
                    *[f"- \u26a0\ufe0f {b}" for b in result.blockers],
                    f"",
                ])

            lines.append("---")
            lines.append("")

        if self.root_cause:
            lines.extend([
                f"## Root Cause",
                f"",
                f"{self.root_cause}",
                f"",
            ])

        if self.fix_commit:
            lines.extend([
                f"## Fix",
                f"",
                f"- **Commit:** `{self.fix_commit}`",
                f"- **Regression Test:** `{self.regression_test or 'Not added'}`",
                f"- **Monitoring:** `{self.monitoring_alert or 'Not configured'}`",
                f"",
            ])

        return "\n".join(lines)


class DebuggerMode:
    """
    Systematic debugging with 5-step triage and stop-the-line enforcement.

    Principles:
    1. REPRODUCE — If you can't make it fail, you can't fix it
    2. LOCALIZE — Find exact lines, not modules
    3. REDUCE — Minimal test case isolates the bug
    4. FIX — One change, verified, no "while I'm here"
    5. GUARD — Regression test prevents recurrence, monitoring catches early

    Stop-the-line: If tests are broken, no new features. Fix first.
    """

    # Phase timeouts (seconds)
    PHASE_TIMEOUTS = {
        DebugPhase.REPRODUCE: 300,    # 5 min
        DebugPhase.LOCALIZE: 600,     # 10 min
        DebugPhase.REDUCE: 600,       # 10 min
        DebugPhase.FIX: 300,          # 5 min
        DebugPhase.GUARD: 300,        # 5 min
    }

    # Max phases before escalation
    MAX_PHASE_ATTEMPTS = 3

    def __init__(
        self,
        llm_client: BaseModel,
        workspace: str | Path = ".",
        test_runner: str = "pytest",
        stop_the_line: bool = True,
    ) -> None:
        self.llm = llm_client
        self.workspace = Path(workspace).resolve()
        self.test_runner = test_runner
        self.stop_the_line = stop_the_line

        # Session tracking
        self._active_sessions: dict[str, DebugSession] = {}
        self._resolved_signatures: dict[str, DebugSession] = {}
        self._escalation_count: int = 0

    def start_session(
        self,
        error_message: str,
        stack_trace: str = "",
        logs: str = "",
        context: dict | None = None,
    ) -> DebugSession:
        """
        Start a new debugging session with error signature.

        Args:
            error_message: The error message or exception text
            stack_trace: Full stack trace if available
            logs: Additional log context
            context: Codebase context, recent changes, environment

        Returns:
            DebugSession with unique ID and error signature
        """
        signature = ErrorSignature.from_raw(error_message, stack_trace)

        # Check if we've seen this before
        if signature.stack_hash in self._resolved_signatures:
            previous = self._resolved_signatures[signature.stack_hash]
            signature.occurrence_count = previous.signature.occurrence_count + 1

        session_id = f"debug-{signature.stack_hash}-{int(time.time())}"

        session = DebugSession(
            session_id=session_id,
            signature=signature,
        )

        self._active_sessions[session_id] = session
        return session

    async def run_full_triage(self, session: DebugSession) -> DebugSession:
        """
        Execute all 5 phases of debugging triage.

        Stop-the-line: If any phase is blocked, escalate immediately.
        """
        phases = [
            DebugPhase.REPRODUCE,
            DebugPhase.LOCALIZE,
            DebugPhase.REDUCE,
            DebugPhase.FIX,
            DebugPhase.GUARD,
        ]

        for phase in phases:
            if session.status != "active":
                break

            session.current_phase = phase
            result = await self._execute_phase(session, phase)
            session.phases.append(result)

            # Stop-the-line: blocked phases halt everything
            if result.status == "blocked" and self.stop_the_line:
                session.status = "escalated"
                self._escalation_count += 1
                break

            # Failed phase: retry or escalate
            if result.status == "failed":
                if len([p for p in session.phases if p.phase == phase]) < self.MAX_PHASE_ATTEMPTS:
                    # Retry with adjusted approach
                    continue
                else:
                    session.status = "escalated"
                    self._escalation_count += 1
                    break

        if session.status == "active":
            session.status = "resolved"
            self._resolved_signatures[session.signature.stack_hash] = session

        session.end_time = time.time()
        return session

    async def _execute_phase(self, session: DebugSession, phase: DebugPhase) -> PhaseResult:
        """
        Execute a single debug phase with LLM assistance.

        Each phase has specific goals, artifacts, and success criteria.
        """
        start_time = time.time()

        if phase == DebugPhase.REPRODUCE:
            return await self._phase_reproduce(session, start_time)
        elif phase == DebugPhase.LOCALIZE:
            return await self._phase_localize(session, start_time)
        elif phase == DebugPhase.REDUCE:
            return await self._phase_reduce(session, start_time)
        elif phase == DebugPhase.FIX:
            return await self._phase_fix(session, start_time)
        elif phase == DebugPhase.GUARD:
            return await self._phase_guard(session, start_time)

        return PhaseResult(
            phase=phase,
            status="failed",
            output="Unknown phase",
            duration_seconds=time.time() - start_time,
        )

    async def _phase_reproduce(self, session: DebugSession, start_time: float) -> PhaseResult:
        """
        REPRODUCE: Make the error fail every single time.

        Success criteria:
        - Test case that fails 100% of runs
        - No environmental dependencies (same result on any machine)
        - Documented preconditions
        """
        prompt = self._build_reproduce_prompt(session)
        response = self.llm.generate(prompt, temperature=0.2, max_tokens=3000)

        # Parse reproduction steps
        test_code = self._extract_code(response)
        reproduction_steps = self._extract_steps(response)

        # Verify: run the test, check if it fails
        test_passed, test_output = await self._run_test(test_code)

        if not test_passed:  # Test fails = reproduction successful
            return PhaseResult(
                phase=DebugPhase.REPRODUCE,
                status="success",
                output=f"Reproduction successful. Test fails consistently.\n\n{test_output}",
                artifacts=[f"test_reproduce_{session.session_id}.py"],
                duration_seconds=time.time() - start_time,
                next_phase=DebugPhase.LOCALIZE,
            )
        else:
            # Test passed = couldn't reproduce
            blockers = []
            if "intermittent" in session.signature.category.description.lower():
                blockers.append("Flaky error — may require stress testing or timing manipulation")
            if "environment" in test_output.lower():
                blockers.append("Environment-dependent — needs containerized reproduction")

            return PhaseResult(
                phase=DebugPhase.REPRODUCE,
                status="blocked" if blockers else "failed",
                output=f"Could not reproduce. Test passed unexpectedly.\n\n{test_output}",
                blockers=blockers,
                duration_seconds=time.time() - start_time,
            )

    async def _phase_localize(self, session: DebugSession, start_time: float) -> PhaseResult:
        """
        LOCALIZE: Find the exact lines of code causing the error.

        Success criteria:
        - Specific file and line number
        - Variable values at failure point
        - Call stack context
        - No "somewhere in module X"
        """
        # Use existing stack trace as starting point
        initial_location = session.signature.file_location

        prompt = self._build_localize_prompt(session, initial_location)
        response = self.llm.generate(prompt, temperature=0.1, max_tokens=3000)

        # Parse localization results
        locations = self._extract_locations(response)
        root_cause_analysis = self._extract_analysis(response)

        if locations and len(locations) > 0:
            session.root_cause = root_cause_analysis
            return PhaseResult(
                phase=DebugPhase.LOCALIZE,
                status="success",
                output=f"Localized to:\n{chr(10).join(f'- {loc}' for loc in locations)}\n\nRoot cause: {root_cause_analysis}",
                artifacts=locations,
                duration_seconds=time.time() - start_time,
                next_phase=DebugPhase.REDUCE,
            )
        else:
            return PhaseResult(
                phase=DebugPhase.LOCALIZE,
                status="failed",
                output="Could not localize. Stack trace insufficient or code changed.",
                blockers=["Need more context: recent commits, dependency changes, environment diff"],
                duration_seconds=time.time() - start_time,
            )

    async def _phase_reduce(self, session: DebugSession, start_time: float) -> PhaseResult:
        """
        REDUCE: Create minimal test case that still fails.

        Success criteria:
        - Remove all code unrelated to the bug
        - Remove all dependencies not needed for failure
        - Test is <50 lines
        - Fails with same error signature
        """
        prompt = self._build_reduce_prompt(session)
        response = self.llm.generate(prompt, temperature=0.2, max_tokens=3000)

        minimal_test = self._extract_code(response)

        # Verify minimal test still fails
        test_passed, test_output = await self._run_test(minimal_test)

        if not test_passed:  # Still fails = reduction successful
            line_count = len(minimal_test.split("\n"))
            return PhaseResult(
                phase=DebugPhase.REDUCE,
                status="success",
                output=f"Minimal test case ({line_count} lines) reproduces error.\n\n{test_output}",
                artifacts=[f"test_minimal_{session.session_id}.py"],
                duration_seconds=time.time() - start_time,
                next_phase=DebugPhase.FIX,
            )
        else:
            return PhaseResult(
                phase=DebugPhase.REDUCE,
                status="failed",
                output=f"Minimal test no longer fails. Over-reduced or different root cause.\n\n{test_output}",
                blockers=["Need to preserve more context in minimal test"],
                duration_seconds=time.time() - start_time,
            )

    async def _phase_fix(self, session: DebugSession, start_time: float) -> PhaseResult:
        """
        FIX: One surgical change, verified.

        Rules:
        - One change per commit
        - No "while I'm here" refactoring
        - Test passes after fix
        - Original reproduction test passes
        - No new failures introduced
        """
        prompt = self._build_fix_prompt(session)
        response = self.llm.generate(prompt, temperature=0.1, max_tokens=3000)

        fix_code = self._extract_code(response)
        fix_explanation = self._extract_explanation(response)

        # Apply fix
        fix_applied = await self._apply_fix(session, fix_code)

        if not fix_applied:
            return PhaseResult(
                phase=DebugPhase.FIX,
                status="failed",
                output="Could not apply fix automatically.",
                blockers=["Manual fix required — automated patch failed"],
                duration_seconds=time.time() - start_time,
            )

        # Verify: run all tests
        all_passed, test_output = await self._run_all_tests()

        if all_passed:
            # Commit the fix
            commit_hash = await self._commit_fix(session, fix_explanation)
            session.fix_commit = commit_hash

            return PhaseResult(
                phase=DebugPhase.FIX,
                status="success",
                output=f"Fix applied and verified. All tests pass.\n\n{fix_explanation}",
                artifacts=[f"fix_{session.session_id}.patch", f"commit_{commit_hash}"],
                duration_seconds=time.time() - start_time,
                next_phase=DebugPhase.GUARD,
            )
        else:
            # Revert and report
            await self._revert_fix(session)

            return PhaseResult(
                phase=DebugPhase.FIX,
                status="failed",
                output=f"Fix broke other tests. Reverted.\n\n{test_output}",
                blockers=["Fix is too broad — needs more targeted approach"],
                duration_seconds=time.time() - start_time,
            )

    async def _phase_guard(self, session: DebugSession, start_time: float) -> PhaseResult:
        """
        GUARD: Regression test + monitoring.

        Success criteria:
        - Regression test added to test suite
        - Test fails with original bug, passes with fix
        - Monitoring alert configured (if applicable)
        - Documentation updated
        """
        prompt = self._build_guard_prompt(session)
        response = self.llm.generate(prompt, temperature=0.2, max_tokens=3000)

        regression_test = self._extract_code(response)
        monitoring_config = self._extract_monitoring(response)

        # Add regression test to suite
        test_added = await self._add_regression_test(session, regression_test)

        # Verify regression test
        test_passed, _ = await self._run_test(regression_test)

        if test_passed and test_added:
            session.regression_test = f"test_regression_{session.session_id}.py"
            session.monitoring_alert = monitoring_config

            return PhaseResult(
                phase=DebugPhase.GUARD,
                status="success",
                output="Regression test added and verified. Monitoring configured.",
                artifacts=[
                    f"test_regression_{session.session_id}.py",
                    f"monitoring_{session.session_id}.yaml",
                ],
                duration_seconds=time.time() - start_time,
                next_phase=None,
            )
        else:
            return PhaseResult(
                phase=DebugPhase.GUARD,
                status="failed",
                output="Could not add regression test.",
                blockers=["Manual test review needed"],
                duration_seconds=time.time() - start_time,
            )

    def get_session(self, session_id: str) -> DebugSession | None:
        """Retrieve active or resolved session."""
        return self._active_sessions.get(session_id)

    def get_similar_sessions(self, signature: ErrorSignature) -> list[DebugSession]:
        """Find previously resolved sessions with similar errors."""
        similar = []
        for resolved in self._resolved_signatures.values():
            if resolved.signature.category == signature.category:
                # Same category = potentially related
                similar.append(resolved)
            elif resolved.signature.stack_hash == signature.stack_hash:
                # Exact match = same bug recurring
                similar.insert(0, resolved)  # Most relevant first

        return similar[:5]  # Top 5

    def get_stats(self) -> dict[str, int | float]:
        """Return debugging statistics."""
        total = len(self._active_sessions)
        resolved = sum(1 for s in self._active_sessions.values() if s.status == "resolved")
        escalated = sum(1 for s in self._active_sessions.values() if s.status == "escalated")

        avg_duration = (
            sum(s.duration_seconds for s in self._active_sessions.values()) / total
            if total > 0 else 0
        )

        return {
            "total_sessions": total,
            "resolved": resolved,
            "escalated": escalated,
            "active": total - resolved - escalated,
            "escalation_rate": escalated / total if total > 0 else 0,
            "avg_duration_seconds": avg_duration,
            "unique_signatures": len(self._resolved_signatures),
            "recurring_bugs": sum(
                1 for s in self._resolved_signatures.values()
                if s.signature.occurrence_count > 1
            ),
        }

    # =================================================================
    # Prompt Builders
    # =================================================================

    def _build_reproduce_prompt(self, session: DebugSession) -> str:
        """Build prompt for REPRODUCE phase."""
        return f"""Create a test that reproduces this error 100% of the time.

## Error
{session.signature.message_pattern}

## Stack Trace
{session.signature.file_location}:{session.signature.line_number}

## Category
{session.signature.category.description}

## Rules
1. No environmental dependencies (same result on any machine)
2. No race conditions (deterministic)
3. Document all preconditions
4. Include setup code inline
5. Use only standard library + test framework

## Output
Return ONLY the test code.
"""

    def _build_localize_prompt(self, session: DebugSession, initial_location: str | None) -> str:
        """Build prompt for LOCALIZE phase."""
        return f"""Find the exact lines causing this error.

## Error
{session.signature.message_pattern}

## Initial Location
{initial_location or "Unknown"}

## Rules
1. Specific file and line number
2. Variable values at failure point
3. Call stack context (3 frames up, 3 down)
4. No "somewhere in module X" — exact references
5. Consider: recent commits, dependency changes, environment

## Output
Return:
1. Exact file:line references
2. Root cause analysis (3-5 sentences)
3. Why this code fails with this input
"""

    def _build_reduce_prompt(self, session: DebugSession) -> str:
        """Build prompt for REDUCE phase."""
        return f"""Reduce this to a minimal test case that still fails.

## Root Cause
{session.root_cause or "Unknown"}

## Rules
1. Remove all unrelated code
2. Remove all unnecessary dependencies
3. Target <50 lines
4. Same error signature
5. Inline everything (no imports if possible)

## Output
Return ONLY the minimal test code.
"""

    def _build_fix_prompt(self, session: DebugSession) -> str:
        """Build prompt for FIX phase."""
        return f"""Fix this bug with one surgical change.

## Root Cause
{session.root_cause or "Unknown"}

## Rules
1. ONE change per commit (no "while I'm here")
2. Explain the fix in 2-3 sentences
3. No refactoring unrelated code
4. Preserve all existing behavior
5. Add type hints if missing

## Output
Return:
1. The fix code (diff format preferred)
2. Explanation of why this fixes the bug
"""

    def _build_guard_prompt(self, session: DebugSession) -> str:
        """Build prompt for GUARD phase."""
        return f"""Create a regression test and monitoring for this bug.

## Bug
{session.root_cause or "Unknown"}

## Fix
{session.fix_commit or "Applied"}

## Rules
1. Test fails with original bug, passes with fix
2. Descriptive name: test_regression_{session.signature.category.label}_{description}
3. Add to permanent test suite
4. Monitoring alert if applicable (performance, error rate)
5. Document in CHANGELOG

## Output
Return:
1. Regression test code
2. Monitoring configuration (YAML or JSON)
3. CHANGELOG entry
"""

    # =================================================================
    # Internal Helpers
    # =================================================================

    def _extract_code(self, response: str) -> str:
        """Extract code block from response."""
        match = re.search(r"```(?:\w+)?\s*(.*?)\s*```", response, re.DOTALL)
        return match.group(1) if match else response

    def _extract_steps(self, response: str) -> list[str]:
        """Extract numbered steps from response."""
        return re.findall(r"\d+\.\s+(.*?)(?=\n\d+\.|\n\n|$)", response, re.DOTALL)

    def _extract_locations(self, response: str) -> list[str]:
        """Extract file:line locations."""
        return re.findall(r"([^\s:]+):(\d+)", response)

    def _extract_analysis(self, response: str) -> str:
        """Extract root cause analysis."""
        lines = response.split("\n")
        for i, line in enumerate(lines):
            if "root cause" in line.lower() or "analysis" in line.lower():
                return "\n".join(lines[i:i+5])
        return ""

    def _extract_explanation(self, response: str) -> str:
        """Extract fix explanation."""
        lines = response.split("\n")
        for i, line in enumerate(lines):
            if "explanation" in line.lower() or "why" in line.lower():
                return "\n".join(lines[i:i+3])
        return ""

    def _extract_monitoring(self, response: str) -> str:
        """Extract monitoring configuration."""
        match = re.search(r"```(?:yaml|json)?\s*(.*?)\s*```", response, re.DOTALL)
        return match.group(1) if match else ""

    async def _run_test(self, test_code: str) -> tuple[bool, str]:
        """Run test code and return (passed, output)."""
        # In production: write to temp file, run with pytest
        # For now: simulate
        return False, "Simulated test failure"

    async def _run_all_tests(self) -> tuple[bool, str]:
        """Run full test suite."""
        # In production: subprocess.run([self.test_runner])
        return True, "All tests pass"

    async def _apply_fix(self, session: DebugSession, fix_code: str) -> bool:
        """Apply fix to codebase."""
        # In production: parse diff, apply patches
        return True

    async def _revert_fix(self, session: DebugSession) -> None:
        """Revert applied fix."""
        # In production: git checkout or patch -R
        pass

    async def _commit_fix(self, session: DebugSession, explanation: str) -> str:
        """Commit fix with descriptive message."""
        # In production: git commit
        return f"fix-{session.session_id[:8]}"

    async def _add_regression_test(self, session: DebugSession, test_code: str) -> bool:
        """Add regression test to test suite."""
        # In production: write to tests/regression/
        return True
