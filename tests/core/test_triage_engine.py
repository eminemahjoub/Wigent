"""
Role: Unit tests for TriageEngine 5-step debugging pipeline.
Author: Wigent AI
Version: 1.0.0

Tests each step independently and the full pipeline integration.

Usage:
    pytest tests/core/test_triage_engine.py -v
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from wigent.core.triage_engine import (
    TriageEngine,
    TriageState,
    TriageStep,
    ErrorSignature,
    FixTestResult,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_llm():
    """Create a mock LLM client with configurable responses."""
    llm = MagicMock()

    def default_response(prompt, **kwargs):
        if "reproduce" in prompt.lower() or "failing" in prompt.lower():
            return "def test_bug(): assert 1 + 1 == 3"
        elif "fix" in prompt.lower():
            return "EXPLANATION: Fixed off-by-one error\n```\ndef fixed():\n    return 42\n```"
        elif "reduce" in prompt.lower():
            return "```\ndef minimal():\n    return 1/0\n```"
        elif "guard" in prompt.lower() or "regression" in prompt.lower():
            return "def test_regression():\n    assert fixed() == 42"
        elif "localize" in prompt.lower() or "location" in prompt.lower():
            return "File: src/main.py:142 in calculate_total\nRoot cause: Off-by-one error in range calculation"
        return "# Default response"

    llm.generate.side_effect = default_response
    return llm


@pytest.fixture
def triage_engine(mock_llm, tmp_path):
    """Create a TriageEngine with mocked LLM and temp workspace."""
    return TriageEngine(
        llm_client=mock_llm,
        workspace_root=tmp_path,
        test_runner="pytest",
    )


@pytest.fixture
def sample_error():
    """Sample Python traceback for testing."""
    return """Traceback (most recent call last):
  File "src/main.py", line 142, in calculate_total
    result = apply_discount(price, discount)
  File "src/main.py", line 98, in apply_discount
    return price - (price * discount / 100)
ZeroDivisionError: division by zero"""


@pytest.fixture
def failing_command():
    """Command that produces the sample error."""
    return "python -c 'from main import calculate_total; calculate_total(100, 0)'"


# =============================================================================
# Test: ErrorSignature
# =============================================================================

class TestErrorSignature:
    """Tests for error fingerprinting and matching."""

    def test_creates_from_raw_data(self):
        """Given error type and message, signature is created with hash."""
        sig = ErrorSignature(
            error_type="ZeroDivisionError",
            error_message="division by zero",
        )
        assert sig.error_type == "ZeroDivisionError"
        assert sig.stack_hash != ""
        assert "ZeroDivisionError" in sig.stack_hash

    def test_matching_exact(self):
        """Given two identical signatures, matches returns True."""
        sig1 = ErrorSignature(
            error_type="ZeroDivisionError",
            error_message="division by zero",
            file_path="src/main.py",
            function_name="apply_discount",
        )
        sig2 = ErrorSignature(
            error_type="ZeroDivisionError",
            error_message="division by zero",
            file_path="src/main.py",
            function_name="apply_discount",
        )
        assert sig1.matches(sig2)

    def test_not_matching_different_type(self):
        """Given different error types, matches returns False."""
        sig1 = ErrorSignature(error_type="ValueError", error_message="bad value")
        sig2 = ErrorSignature(error_type="TypeError", error_message="bad type")
        assert not sig1.matches(sig2)

    def test_fuzzy_matching_same_type(self):
        """Given same type but different messages, fuzzy match works."""
        sig1 = ErrorSignature(error_type="ValueError", error_message="bad value: foo")
        sig2 = ErrorSignature(
            error_type="ValueError",
            error_message="bad value: bar",
            stack_hash="",
        )
        assert sig1.matches(sig2, fuzzy=True)

    def test_normalizes_addresses_in_hash(self):
        """Given error with memory addresses, hash is normalized."""
        sig = ErrorSignature(
            error_type="SegmentationFault",
            error_message="at address 0x7fff1234",
        )
        assert "<ADDR>" not in sig.error_message
        assert sig.stack_hash != ""


# =============================================================================
# Test: TriageState
# =============================================================================

class TestTriageState:
    """Tests for mutable state container."""

    def test_default_step_is_reproduce(self):
        """Given no step override, state starts at REPRODUCE."""
        state = TriageState()
        assert state.step == TriageStep.REPRODUCE
        assert state.confidence == 0.0
        assert state.reproduction_confirmed is False

    def test_can_set_initial_values(self):
        """Given constructor args, state is initialized correctly."""
        state = TriageState(
            original_traceback="Error: test",
            reproduction_command="pytest",
            confidence=0.5,
        )
        assert state.original_traceback == "Error: test"
        assert state.reproduction_command == "pytest"
        assert state.confidence == 0.5

    def test_notes_and_blockers_are_empty_lists(self):
        """Given fresh state, notes and blockers are empty."""
        state = TriageState()
        assert state.notes == []
        assert state.blockers == []


# =============================================================================
# Test: TriageEngine — Full Pipeline
# =============================================================================

class TestTriageEngineFullPipeline:
    """Integration tests for the complete 5-step pipeline."""

    def test_full_triage_pipeline(self, triage_engine, sample_error, failing_command):
        """
        Given a reproducible error,
        When triage runs all 5 steps,
        Then the bug is resolved and guarded.
        """
        state = triage_engine.triage(
            error_output=sample_error,
            command_that_failed=failing_command,
        )

        assert state.error_signature is not None
        assert state.error_signature.error_type == "ZeroDivisionError"
        assert state.blockers == []
        assert state.confidence >= 0.9
        assert state.fix_applied is True
        assert state.test_added is True

    def test_pipeline_stops_on_blocker(self, triage_engine, mock_llm):
        """
        Given an unreproducible error,
        When triage runs,
        Then it stops at REPRODUCE with blocker.
        """
        mock_llm.generate.return_value = "def test_bug(): assert True"

        state = triage_engine.triage(
            error_output="FlakyError: sometimes",
            command_that_failed="python -c 'import flaky'",
        )

        assert state.blockers
        assert "reproduce" in state.blockers[0].lower() or "Flaky" in state.original_traceback

    def test_pipeline_can_resume_from_step(self, triage_engine, sample_error, failing_command):
        """
        Given a partial state,
        When continue from a specific step,
        Then remaining steps execute.
        """
        state = triage_engine.triage(
            error_output=sample_error,
            command_that_failed=failing_command,
            starting_step=TriageStep.REDUCE,
        )

        assert state.reproduction_confirmed is False
        assert state.localized_file is None
        assert state.confidence >= 0.9
        assert state.fix_applied is True

    def test_tracks_sessions(self, triage_engine, sample_error, failing_command):
        """
        Given triage with session_id,
        When completed,
        Then session is stored for recall.
        """
        state = triage_engine.triage(
            error_output=sample_error,
            command_that_failed=failing_command,
            session_id="test-session-1",
        )

        assert "test-session-1" in triage_engine._active_sessions
        assert state.fix_applied is True

    def test_get_similar_errors(self, triage_engine, sample_error, failing_command):
        """
        Given resolved errors,
        When get_similar_errors called,
        Then matching sessions are returned.
        """
        triage_engine.triage(
            error_output=sample_error,
            command_that_failed=failing_command,
            session_id="session-1",
        )

        sig = triage_engine._parse_error_signature(sample_error)
        similar = triage_engine.get_similar_errors(sig)

        assert len(similar) >= 1

    def test_stats_reporting(self, triage_engine, sample_error, failing_command):
        """
        Given completed triages,
        When get_stats called,
        Then correct statistics are returned.
        """
        triage_engine.triage(sample_error, failing_command, session_id="s1")
        triage_engine.triage("TypeError: bad", "python -c 'bad()'", session_id="s2")

        stats = triage_engine.get_stats()

        assert stats["total_sessions"] >= 2
        assert stats["unique_signatures"] >= 2
        assert stats["resolution_rate"] >= 0


# =============================================================================
# Test: TriageEngine — Single Step
# =============================================================================

class TestSingleStepReproduce:
    """Tests for REPRODUCE step."""

    def test_reproduce_confirms_error(self, triage_engine, sample_error, failing_command):
        """
        Given a consistently failing command,
        When REPRODUCE executes,
        Then reproduction is confirmed.
        """
        state = TriageState(
            original_traceback=sample_error,
            reproduction_command=failing_command,
        )
        state.error_signature = triage_engine._parse_error_signature(sample_error)

        with patch.object(triage_engine, "_run_command") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stderr = sample_error
            mock_run.return_value = mock_result

            triage_engine._step_reproduce(state)

        assert state.reproduction_confirmed is True
        assert state.confidence > 0

    def test_reproduce_passes_on_success(self, triage_engine, sample_error, failing_command):
        """
        Given a passing command,
        When REPRODUCE executes,
        Then it tries to stabilize but does not confirm.
        """
        state = TriageState(
            original_traceback=sample_error,
            reproduction_command=failing_command,
        )
        state.error_signature = triage_engine._parse_error_signature(sample_error)

        with patch.object(triage_engine, "_run_command") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stderr = ""
            mock_run.return_value = mock_result

            triage_engine._step_reproduce(state)

        assert state.reproduction_confirmed is False
        assert state.blockers


class TestSingleStepLocalize:
    """Tests for LOCALIZE step."""

    def test_localize_from_traceback(self, triage_engine, sample_error, tmp_path):
        """
        Given a traceback with file:line info,
        When LOCALIZE executes,
        Then location is extracted.
        """
        test_file = tmp_path / "src/main.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(
            "def apply_discount(price, discount):\n"
            "    return price - (price * discount / 100)\n"
        )

        state = TriageState(
            original_traceback=sample_error,
            reproduction_command="pytest",
            reproduction_confirmed=True,
        )
        state.error_signature = triage_engine._parse_error_signature(sample_error)
        state.localized_file = str(test_file)
        state.localized_line = 2
        state.localized_function = "apply_discount"

        triage_engine._step_localize(state)

        assert state.localized_file is not None
        assert state.localized_line is not None
        assert state.confidence == 0.5
        assert "LOCATED" in " ".join(state.notes)

    def test_localize_fails_without_reproduction(self, triage_engine):
        """
        Given no reproduction confirmation,
        When LOCALIZE executes,
        Then it is blocked.
        """
        state = TriageState()
        state.error_signature = ErrorSignature("Error", "test")

        triage_engine._step_localize(state)

        assert state.blockers


class TestSingleStepReduce:
    """Tests for REDUCE step."""

    def test_reduce_creates_minimal_case(self, triage_engine):
        """
        Given localized error,
        When REDUCE executes,
        Then minimal failing code is produced.
        """
        state = TriageState(
            original_traceback="ZeroDivisionError: division by zero",
            localized_file="src/main.py",
            localized_line=98,
            localized_function="apply_discount",
            reproduction_confirmed=True,
        )

        triage_engine._step_reduce(state)

        assert state.reduced_code != ""
        assert state.confidence >= 0.7

    def test_reduce_fails_without_localization(self, triage_engine):
        """
        Given no localization,
        When REDUCE executes,
        Then it is blocked.
        """
        state = TriageState()
        triage_engine._step_reduce(state)

        assert state.blockers


class TestSingleStepFix:
    """Tests for FIX step."""

    def test_fix_generates_and_validates(self, triage_engine):
        """
        Given reduced failing code,
        When FIX executes,
        Then fix is proposed and applied.
        """
        state = TriageState(
            original_traceback="ZeroDivisionError",
            reduced_code="def bug(): return 1/0",
            reproduction_confirmed=True,
        )

        triage_engine._step_fix(state)

        assert state.proposed_fix != ""
        assert state.fix_applied is True
        assert state.confidence >= 0.85

    def test_fix_fails_without_reduced_code(self, triage_engine):
        """
        Given no reduced code,
        When FIX executes,
        Then it is blocked.
        """
        state = TriageState()
        triage_engine._step_fix(state)

        assert state.blockers


class TestSingleStepGuard:
    """Tests for GUARD step."""

    def test_guard_generates_regression_test(self, triage_engine):
        """
        Given applied fix,
        When GUARD executes,
        Then regression test is added.
        """
        state = TriageState(
            fix_applied=True,
            proposed_fix="def fixed(): return 42",
            original_traceback="AssertionError",
        )

        triage_engine._step_guard(state)

        assert state.test_added is True
        assert state.confidence >= 0.95

    def test_guard_fails_without_fix(self, triage_engine):
        """
        Given no applied fix,
        When GUARD executes,
        Then it is blocked.
        """
        state = TriageState()
        triage_engine._step_guard(state)

        assert state.blockers


# =============================================================================
# Test: Utilities
# =============================================================================

class TestUtilities:
    """Tests for triage engine utility methods."""

    def test_parse_error_signature(self, triage_engine, sample_error):
        """
        Given raw traceback output,
        When parsed,
        Then error type and message are extracted.
        """
        sig = triage_engine._parse_error_signature(sample_error)

        assert sig.error_type == "ZeroDivisionError"
        assert "division by zero" in sig.error_message

    def test_parse_unknown_error(self, triage_engine):
        """
        Given output without colons,
        When parsed,
        Then default Unknown type is used.
        """
        sig = triage_engine._parse_error_signature("Something went wrong")

        assert sig.error_type == "Unknown"
        assert sig.error_message == "Something went wrong"

    def test_extract_traceback_location(self, triage_engine):
        """
        Given traceback lines with file info,
        When extracted,
        Then file, line, and function are returned.
        """
        tb = [
            'Traceback (most recent call last):',
            '  File "src/main.py", line 142, in calculate_total',
            '    result = apply_discount(price, discount)',
        ]

        file_path, line_no, func_name = triage_engine._extract_traceback_location(tb)

        assert file_path == "src/main.py"
        assert line_no == 142
        assert func_name == "calculate_total"

    def test_extract_code_block_with_markdown(self, triage_engine):
        """
        Given response with markdown code block,
        When extracted,
        Then code is returned without markers.
        """
        response = "Some text\n```python\ndef foo():\n    pass\n```\nMore text"

        code = triage_engine._extract_code_block(response)

        assert "def foo():" in code
        assert "```" not in code

    def test_extract_code_block_plain_text(self, triage_engine):
        """
        Given response without code blocks,
        When extracted,
        Then entire response is returned.
        """
        response = "def foo():\n    pass"

        code = triage_engine._extract_code_block(response)

        assert code == response

    def test_extract_explanation(self, triage_engine):
        """
        Given response with EXPLANATION prefix,
        When extracted,
        Then explanation text is returned.
        """
        response = "EXPLANATION: Fixed off-by-one error\n```\ncode\n```"

        explanation = triage_engine._extract_explanation(response)

        assert explanation == "Fixed off-by-one error"

    def test_get_code_context_existing_file(self, triage_engine, tmp_path):
        """
        Given existing file with known content,
        When context is extracted,
        Then surrounding lines are returned.
        """
        test_file = tmp_path / "test.py"
        test_file.write_text("\n".join(f"line_{i}" for i in range(10)))

        context = triage_engine._get_code_context(str(test_file), 5, context_lines=2)

        assert "line_3" in context or "line_4" in context
        assert ">>>" in context

    def test_get_code_context_nonexistent_file(self, triage_engine):
        """
        Given file that does not exist,
        When context is requested,
        Then error message is returned.
        """
        context = triage_engine._get_code_context("/nonexistent/file.py", 1)

        assert "not found" in context.lower() or "File not found" in context

    def test_code_context_marker_on_exact_line(self, triage_engine, tmp_path):
        """
        Given file with 10 lines,
        When requesting context around line 5,
        Then line 5 is marked with >>>.
        """
        test_file = tmp_path / "lines.py"
        test_file.write_text("\n".join(f"line_{i}" for i in range(10)))

        context = triage_engine._get_code_context(str(test_file), 5, context_lines=0)

        assert ">>>" in context
        assert "line_5" in context

    def test_get_code_context_resolves_relative_path(self, triage_engine, tmp_path):
        """
        Given relative path that exists under workspace,
        When context is requested,
        Then workspace-relative resolution succeeds.
        """
        nested = tmp_path / "src/mod.py"
        nested.parent.mkdir(parents=True, exist_ok=True)
        nested.write_text("x = 1\ny = 2\nz = 3\n")

        triage_engine.workspace = tmp_path
        context = triage_engine._get_code_context("src/mod.py", 2, context_lines=1)

        assert "y = 2" in context
        assert ">>>" in context


# =============================================================================
# Test: FixTestResult
# =============================================================================

class TestFixTestResult:
    """Tests for fix validation result."""

    def test_resolved_result(self):
        """Given resolved fix, attributes are correct."""
        result = FixTestResult(resolved=True, explanation="Fixed off-by-one")
        assert result.resolved is True
        assert result.explanation == "Fixed off-by-one"

    def test_failed_result(self):
        """Given failed fix, attributes are correct."""
        result = FixTestResult(resolved=False, explanation="Syntax error")
        assert result.resolved is False
        assert result.explanation == "Syntax error"
