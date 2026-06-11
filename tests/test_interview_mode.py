"""
Role: Comprehensive tests for Wigent's interview mode.
Author: Wigent AI
Version: 1.0.0

Tests confidence tracking, question sequencing, spec generation,
vague answer handling, and session persistence.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from wigent.modes.interview import InterviewMode


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_llm():
    """Create a mock LLM client."""
    return MagicMock()


@pytest.fixture
def interview_mode(mock_llm):
    """Create an InterviewMode instance with mocked LLM."""
    from wigent.modes.interview import InterviewMode
    
    return InterviewMode(llm_client=mock_llm)


@pytest.fixture
def sample_answers():
    """Return sample detailed answers for confidence testing."""
    return {
        "technical": "I want a React frontend with PostgreSQL database and REST API for user management",
        "constraints": "It needs to handle 10,000 concurrent users with p95 latency under 200ms",
        "users": "Our customers are small business owners who need invoicing",
        "vague": "I don't know, whatever you think is best",
        "contradiction": "Actually, forget React, I want Vue now",
    }


# =============================================================================
# Test: Initialization & First Question
# =============================================================================

class TestInterviewInitialization:
    """Tests for interview start behavior."""

    def test_interview_starts_with_first_question(self, interview_mode):
        """
        Given a new interview session,
        When started,
        Then ask 'What problem are you trying to solve?'
        """
        result = interview_mode.start()
        
        assert "What problem are you trying to solve?" in result
        assert interview_mode.question_count == 1
        assert interview_mode.confidence == 10

    def test_interview_initializes_empty_history(self, interview_mode):
        """Verify fresh interview has no captured data."""
        assert interview_mode.captured_facts == []
        assert interview_mode.remaining_gaps == []
        assert interview_mode.answers == {}

    def test_interview_has_max_15_questions(self, interview_mode):
        """Verify hard limit is enforced."""
        assert interview_mode.MAX_QUESTIONS == 15


# =============================================================================
# Test: Confidence Calculation
# =============================================================================

class TestConfidenceCalculation:
    """Tests for confidence scoring after each answer."""

    def test_technical_details_boost_confidence(self, interview_mode, sample_answers):
        """
        Given answer with specific technologies,
        When processed,
        Then confidence increases by ~45% (3 technologies × 15%).
        """
        initial = interview_mode.confidence  # 10%
        
        interview_mode.process_answer(sample_answers["technical"])
        
        # React (+15%), PostgreSQL (+15%), REST API (+15%)
        assert interview_mode.confidence >= initial + 45
        assert interview_mode.confidence == 55  # 10 + 45

    def test_constraints_boost_confidence(self, interview_mode, sample_answers):
        """
        Given answer with performance/security/scale constraints,
        When processed,
        Then confidence increases by 10%.
        """
        initial = interview_mode.confidence
        
        interview_mode.process_answer(sample_answers["constraints"])
        
        assert interview_mode.confidence == initial + 10  # 10 + 10 = 20

    def test_user_personas_boost_confidence(self, interview_mode, sample_answers):
        """
        Given answer with user personas,
        When processed,
        Then confidence increases by 10%.
        """
        initial = interview_mode.confidence
        
        interview_mode.process_answer(sample_answers["users"])
        
        assert interview_mode.confidence == initial + 10  # 10 + 10 = 20

    def test_combined_signals_boost_confidence(self, interview_mode, sample_answers):
        """
        Given answer with multiple signal types,
        When processed,
        Then confidence increases additively.
        """
        # Technical + constraints + users = 15 + 10 + 10 = 35
        combined = (
            "Small business owners need an invoicing app. "
            "React frontend, PostgreSQL, REST API. "
            "Must handle 10,000 users with sub-200ms latency."
        )
        
        interview_mode.process_answer(combined)
        
        # At least: React(15) + PostgreSQL(15) + REST(15) + constraint(10) + users(10) = 65
        # Starting from 10: 10 + 65 = 75
        assert interview_mode.confidence >= 75

    def test_vague_answer_does_not_increase_confidence(self, interview_mode, sample_answers):
        """
        Given vague answer like 'I don't know',
        When processed,
        Then confidence increases by 0% and triggers specific follow-up.
        """
        initial = interview_mode.confidence
        
        result = interview_mode.process_answer(sample_answers["vague"])
        
        assert interview_mode.confidence == initial  # No change
        assert "more specific" in result.lower() or "help me understand" in result.lower()

    def test_vague_answer_triggers_follow_up_question(self, interview_mode, sample_answers):
        """Verify vague answer generates a more specific follow-up."""
        result = interview_mode.process_answer(sample_answers["vague"])
        
        # Should ask a more targeted question, not accept vagueness
        assert "?" in result
        assert interview_mode.question_count <= 15

    def test_confidence_caps_at_95_percent(self, interview_mode):
        """
        Given multiple highly detailed answers,
        When confidence would exceed 95%,
        Then cap at 95% and require user confirmation.
        """
        # Simulate 6 highly detailed answers
        detailed_answers = [
            "React frontend with TypeScript, Redux state management, and Material UI components",
            "Node.js backend with Express, PostgreSQL database, Redis caching layer",
            "Small business owners aged 25-45, primarily mobile users, need invoice generation",
            "Must handle 50,000 concurrent users, p95 latency under 100ms, 99.99% uptime",
            "OAuth 2.0 with Google and Microsoft, JWT tokens with 1-hour expiry, RBAC",
            "Deploy on AWS with ECS, CloudFront CDN, RDS Multi-AZ, automated backups",
        ]
        
        for answer in detailed_answers:
            interview_mode.process_answer(answer)
            
        assert interview_mode.confidence <= 95
        assert interview_mode.confidence >= 90  # Should be very high

    def test_contradiction_reduces_confidence(self, interview_mode, sample_answers):
        """
        Given answer that contradicts previous answer,
        When processed,
        Then confidence decreases by 5% and flag is raised.
        """
        interview_mode.process_answer("I want React for the frontend")
        initial = interview_mode.confidence
        
        result = interview_mode.process_answer(sample_answers["contradiction"])
        
        assert interview_mode.confidence == initial - 5
        assert "contradiction" in result.lower() or "earlier" in result.lower()


# =============================================================================
# Test: Question Sequencing
# =============================================================================

class TestQuestionSequencing:
    """Tests for the 4-round question strategy."""

    def test_round_1_questions_are_problem_focused(self, interview_mode):
        """
        Given first 3 questions,
        Then they focus on problem, users, and urgency.
        """
        questions = []
        for _ in range(3):
            questions.append(interview_mode.get_current_question())
            interview_mode.process_answer("Test answer with React and PostgreSQL")
            
        assert any("problem" in q.lower() for q in questions)
        assert any("user" in q.lower() or "who" in q.lower() for q in questions)

    def test_round_2_questions_are_scope_focused(self, interview_mode):
        """
        Given questions 4-7,
        Then they focus on features, constraints, tech, integrations.
        """
        # Fast-forward to question 4
        for i in range(3):
            interview_mode.process_answer(
                f"Answer {i+1} with React, PostgreSQL, and 10k users constraint"
            )
            
        q4 = interview_mode.get_current_question()
        
        assert any(keyword in q4.lower() for keyword in [
            "feature", "must-have", "constraint", "technology", "integrat"
        ])

    def test_round_3_asks_why_at_least_twice(self, interview_mode):
        """
        Given Round 3 (questions 8-12),
        Then at least two questions ask 'why'.
        """
        # Fast-forward to question 8
        for i in range(7):
            interview_mode.process_answer(
                f"Detailed answer {i+1} with React, PostgreSQL, 10k users, "
                f"small business owners, OAuth, AWS"
            )
            
        why_count = 0
        for _ in range(5):
            q = interview_mode.get_current_question()
            if "why" in q.lower():
                why_count += 1
            interview_mode.process_answer("Because users need it")
            
        assert why_count >= 2

    def test_question_count_increments_correctly(self, interview_mode):
        """Verify question counter increments with each answer."""
        assert interview_mode.question_count == 1  # After start()
        
        interview_mode.process_answer("Answer 1")
        assert interview_mode.question_count == 2
        
        interview_mode.process_answer("Answer 2")
        assert interview_mode.question_count == 3

    def test_questions_are_under_20_words(self, interview_mode):
        """Verify each generated question is concise."""
        for _ in range(5):
            question = interview_mode.get_current_question()
            word_count = len(question.split())
            assert word_count <= 20, f"Question too long ({word_count} words): {question}"
            interview_mode.process_answer("Test answer")

    def test_single_question_per_turn(self, interview_mode):
        """Verify only one question mark per response."""
        for _ in range(5):
            response = interview_mode.get_current_question()
            question_count = response.count("?")
            assert question_count == 1, (
                f"Expected 1 question, got {question_count}: {response}"
            )
            interview_mode.process_answer("Test answer")


# =============================================================================
# Test: Spec Generation
# =============================================================================

class TestSpecGeneration:
    """Tests for final spec output."""

    def test_spec_output_contains_all_sections(self, interview_mode):
        """
        Given interview at 95% confidence,
        When spec is generated,
        Then output contains all required sections.
        """
        # Build up to 95% confidence with detailed answers
        detailed_answers = [
            "Small business owners need an invoicing app to track payments",
            "Users are freelancers and small agencies aged 25-50",
            "Must-have: invoice creation, PDF export, payment tracking, client management",
            "React frontend, Node.js backend, PostgreSQL, deployed on AWS",
            "Handle 10,000 users, p95 < 200ms, SOC2 compliance, daily backups",
            "Integrate with Stripe for payments, QuickBooks for accounting",
        ]
        
        for answer in detailed_answers:
            interview_mode.process_answer(answer)
            
        spec = interview_mode.generate_spec()
        
        required_sections = [
            "# Spec:",
            "## Problem Statement",
            "## Users",
            "## Must-Have Features",
            "## Technical Constraints",
            "## Preferred Technologies",
            "## Out of Scope",
            "## Confidence:",
            "## Questions Asked:",
        ]
        
        for section in required_sections:
            assert section in spec, f"Missing section: {section}"

    def test_spec_includes_confidence_score(self, interview_mode):
        """Verify spec includes the final confidence percentage."""
        for _ in range(6):
            interview_mode.process_answer(
                "Detailed answer with React, PostgreSQL, 10k users, "
                "small business, OAuth, AWS, Stripe"
            )
            
        spec = interview_mode.generate_spec()
        
        assert "Confidence: 95%" in spec or "Confidence: 9" in spec

    def test_spec_includes_question_count(self, interview_mode):
        """Verify spec tracks how many questions were asked."""
        for i in range(5):
            interview_mode.process_answer(f"Answer {i+1} with technical details")
            
        spec = interview_mode.generate_spec()
        
        assert "Questions Asked:" in spec

    def test_spec_problem_statement_is_specific(self, interview_mode):
        """Verify problem statement is not generic."""
        interview_mode.process_answer(
            "Freelancers waste 5 hours/week manually creating invoices in Excel"
        )
        interview_mode.process_answer("Freelancers and small agencies")
        interview_mode.process_answer(
            "Automated invoice generation, PDF export, payment reminders"
        )
        interview_mode.process_answer("React, Node.js, PostgreSQL")
        interview_mode.process_answer("10k users, p95 < 200ms")
        interview_mode.process_answer("Stripe integration")
        
        spec = interview_mode.generate_spec()
        
        # Problem statement should mention specific pain, not be generic
        assert "waste" in spec or "manually" in spec or "hours" in spec

    def test_spec_out_of_scope_is_non_empty(self, interview_mode):
        """Verify spec includes at least one out-of-scope item."""
        for _ in range(6):
            interview_mode.process_answer(
                "Detailed answer with React, PostgreSQL, 10k users, "
                "small business, OAuth, AWS"
            )
            
        spec = interview_mode.generate_spec()
        
        # Find Out of Scope section and verify it's not empty
        scope_section = spec.split("## Out of Scope")[1].split("##")[0]
        assert len(scope_section.strip()) > 20  # More than just a header


# =============================================================================
# Test: Completion Conditions
# =============================================================================

class TestCompletionConditions:
    """Tests for interview termination."""

    def test_interview_completes_at_95_confidence(self, interview_mode):
        """
        Given 6 highly detailed answers,
        When confidence reaches 95%,
        Then interview completes and asks for confirmation.
        """
        detailed_answers = [
            "React with TypeScript, Redux, Material UI for small business dashboard",
            "Node.js, Express, PostgreSQL, Redis caching, REST API",
            "Freelancers and agencies, mobile-first, need invoicing and expense tracking",
            "50k concurrent users, p95 < 100ms, 99.99% uptime, GDPR compliant",
            "OAuth 2.0, JWT 1-hour expiry, RBAC with admin/manager/viewer roles",
            "AWS ECS, CloudFront, RDS Multi-AZ, automated CI/CD, monitoring with Datadog",
        ]
        
        for answer in detailed_answers:
            result = interview_mode.process_answer(answer)
            
        assert interview_mode.confidence >= 90
        # Should indicate readiness to generate spec
        assert "ready" in result.lower() or "generate" in result.lower()

    def test_max_15_questions_hard_limit(self, interview_mode):
        """
        Given 15 questions with low-confidence answers,
        When limit reached,
        Then force completion with warning.
        """
        vague_answers = ["I'm not sure"] * 14
        
        for answer in vague_answers:
            interview_mode.process_answer(answer)
            
        # 15th answer should trigger forced completion
        result = interview_mode.process_answer("Still vague")
        
        assert interview_mode.question_count == 15
        assert "warning" in result.lower() or "forced" in result.lower() or "spec" in result.lower()

    def test_user_can_trigger_early_completion(self, interview_mode):
        """
        Given user says 'generate spec' or 'done',
        Then complete interview regardless of confidence.
        """
        interview_mode.process_answer("I need a login system")
        interview_mode.process_answer("My team members")
        
        result = interview_mode.process_answer("generate spec now")
        
        assert "spec" in result.lower() or interview_mode.is_complete

    def test_user_can_abort_interview(self, interview_mode):
        """
        Given user says 'stop' or 'exit',
        Then abort and save partial results.
        """
        interview_mode.process_answer("I need an app")
        
        result = interview_mode.process_answer("stop")
        
        assert interview_mode.is_aborted
        assert "saved" in result.lower() or "partial" in result.lower()


# =============================================================================
# Test: Session Persistence
# =============================================================================

class TestSessionPersistence:
    """Tests for save/resume functionality."""

    def test_interview_saves_current_state(self, interview_mode):
        """
        Given interview in progress,
        When save is called,
        Then serialize question count, confidence, answers, gaps.
        """
        interview_mode.process_answer("React app for invoicing")
        interview_mode.process_answer("Small business owners")
        
        state = interview_mode.save_state()
        
        assert state["question_count"] == 3  # Started at 1, 2 answers
        assert state["confidence"] > 10
        assert len(state["answers"]) == 2
        assert "captured_facts" in state
        assert "remaining_gaps" in state

    def test_interview_resumes_from_history(self, interview_mode):
        """
        Given saved state,
        When resume is called,
        Then restore and continue from last question.
        """
        # Simulate partial interview
        interview_mode.process_answer("React app for invoicing")
        saved = interview_mode.save_state()
        
        # Create new instance and resume
        from wigent.modes.interview import InterviewMode
        
        new_interview = InterviewMode(llm_client=MagicMock())
        result = new_interview.resume_from_state(saved)
        
        assert new_interview.question_count == saved["question_count"]
        assert new_interview.confidence == saved["confidence"]
        assert "Welcome back" in result or "continue" in result.lower()

    def test_resume_includes_summary(self, interview_mode):
        """Verify resume message summarizes what was captured."""
        interview_mode.process_answer("React app for invoicing")
        interview_mode.process_answer("Small business owners")
        saved = interview_mode.save_state()
        
        from wigent.modes.interview import InterviewMode
        
        new_interview = InterviewMode(llm_client=MagicMock())
        result = new_interview.resume_from_state(saved)
        
        assert "React" in result or "invoicing" in result or "business" in result

    def test_never_restarts_from_question_1(self, interview_mode):
        """Verify resumed interview continues, never restarts."""
        interview_mode.process_answer("React app")
        interview_mode.process_answer("Small business")
        saved = interview_mode.save_state()
        
        from wigent.modes.interview import InterviewMode
        
        new_interview = InterviewMode(llm_client=MagicMock())
        new_interview.resume_from_state(saved)
        
        assert new_interview.question_count > 1
        # Should ask next question, not question 1
        next_q = new_interview.get_current_question()
        assert "What problem" not in next_q  # That's question 1


# =============================================================================
# Test: Edge Cases
# =============================================================================

class TestEdgeCases:
    """Tests for boundary conditions and error handling."""

    def test_empty_answer_handling(self, interview_mode):
        """Given empty string answer, handle gracefully."""
        result = interview_mode.process_answer("")
        
        assert interview_mode.question_count <= 15
        assert "?" in result  # Should still ask a question

    def test_very_long_answer_handling(self, interview_mode):
        """Given extremely long answer, process without error."""
        long_answer = "React " * 1000 + "PostgreSQL " * 1000
        
        result = interview_mode.process_answer(long_answer)
        
        assert interview_mode.confidence > 10  # Should detect technologies

    def test_special_characters_in_answer(self, interview_mode):
        """Given answer with special characters, handle safely."""
        special = "I want a <script>alert('xss')</script> app with 中文内容"
        
        result = interview_mode.process_answer(special)
        
        assert interview_mode.question_count <= 15
        assert "?" in result

    def test_multiple_technologies_detected(self, interview_mode):
        """Verify regex correctly identifies multiple tech keywords."""
        answer = "Using React, Vue, Angular, Svelte, and Solid for frontend comparison"
        
        interview_mode.process_answer(answer)
        
        # Should detect at least 3 frameworks
        assert interview_mode.confidence >= 10 + 45  # 10 base + 3×15

    def test_no_false_positives_on_common_words(self, interview_mode):
        """
        Given answer with words that look like tech but aren't,
        Then don't incorrectly boost confidence.
        """
        initial = interview_mode.confidence
        
        # "Java" is coffee, "python" is snake, "go" is verb
        interview_mode.process_answer("I want to go get java and see a python")
        
        # Should not boost for these without context
        # (Implementation may vary — this tests for reasonable behavior)
        assert interview_mode.confidence <= initial + 15  # At most one false positive


# =============================================================================
# Integration Test: Full Interview Flow
# =============================================================================

class TestFullInterviewFlow:
    """End-to-end interview simulation."""

    def test_complete_interview_to_spec(self, interview_mode):
        """
        Simulate a complete interview from start to spec.
        """
        # Start
        result = interview_mode.start()
        assert "What problem" in result
        
        # Round 1: Problem & Context
        result = interview_mode.process_answer(
            "Freelancers waste hours manually creating invoices in spreadsheets"
        )
        assert "Who" in result or "user" in result.lower()
        
        result = interview_mode.process_answer(
            "Freelancers and small agencies, mostly solo operators"
        )
        assert "must-have" in result.lower() or "feature" in result.lower()
        
        result = interview_mode.process_answer(
            "Invoice creation, client management, payment tracking, PDF export"
        )
        
        # Round 2: Scope & Constraints
        assert any(k in result.lower() for k in ["technology", "tech", "framework"])
        
        result = interview_mode.process_answer(
            "React frontend, Node.js backend, PostgreSQL database"
        )
        
        result = interview_mode.process_answer(
            "Handle 5,000 users, p95 under 300ms, GDPR compliant"
        )
        
        # Should be approaching completion
        if interview_mode.confidence >= 95:
            spec = interview_mode.generate_spec()
            assert "# Spec:" in spec
            assert "## Problem Statement" in spec
        else:
            # Continue with more details
            result = interview_mode.process_answer(
                "Integrate with Stripe for payments and QuickBooks for accounting"
            )
            spec = interview_mode.generate_spec()
            assert "# Spec:" in spec
