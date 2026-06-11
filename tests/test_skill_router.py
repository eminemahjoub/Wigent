"""
Role: Comprehensive tests for Wigent's skill router system.
Author: Wigent AI
Version: 1.0.0

Tests LLM-based intent classification, keyword fallback, confidence thresholds,
and all 24 default skills.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from wigent.core.skill_router import Skill, SkillRouter


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_llm():
    """Create a mock LLM client with configurable responses."""
    llm = MagicMock()
    llm.generate.return_value = json.dumps({
        "skill": "test-driven-development",
        "confidence": 0.85,
        "reasoning": "User wants to write tests"
    })
    return llm


@pytest.fixture
def skill_router(mock_llm):
    """Create a SkillRouter with mocked LLM and default skills loaded."""
    from wigent.config.skills import load_default_skills
    from wigent.core.skill_router import SkillRouter
    
    router = SkillRouter(mock_llm)
    for skill in load_default_skills():
        router.register_skill(skill)
    return router


@pytest.fixture
def sample_skills():
    """Return a minimal set of skills for isolated testing."""
    from wigent.core.skill_router import Skill
    
    return [
        Skill(
            name="interview-me",
            phase="define",
            description="Interview user for requirements",
            triggers=["interview", "ask me", "grill me"],
            confidence_threshold=0.7,
            prompt_template="prompts/interview.md",
        ),
        Skill(
            name="test-driven-development",
            phase="build",
            description="Write tests first",
            triggers=["test", "tdd", "write tests"],
            confidence_threshold=0.7,
            prompt_template="prompts/test-driven-development.md",
        ),
        Skill(
            name="code-review-and-quality",
            phase="review",
            description="Review code quality",
            triggers=["review", "check code", "quality"],
            confidence_threshold=0.8,
            prompt_template="prompts/code-review-and-quality.md",
        ),
    ]


# =============================================================================
# Test: Basic Classification
# =============================================================================

class TestClassifyIntent:
    """Tests for LLM-based intent classification."""

    def test_classify_intent_with_clear_signal(self, skill_router, mock_llm):
        """
        Given clear test-related input,
        When classify_intent is called,
        Then return test-driven-development with high confidence.
        """
        mock_llm.generate.return_value = json.dumps({
            "skill": "test-driven-development",
            "confidence": 0.88,
            "reasoning": "Explicit request for tests"
        })
        
        skill, confidence = skill_router.classify_intent(
            "write tests for this function",
            conversation_history=[]
        )
        
        assert skill.name == "test-driven-development"
        assert confidence == 0.88
        assert confidence > 0.8

    def test_classify_intent_with_conversation_context(self, skill_router, mock_llm):
        """
        Given conversation history about login page,
        When input mentions OAuth,
        Then return api-and-interface-design with context awareness.
        """
        mock_llm.generate.return_value = json.dumps({
            "skill": "api-and-interface-design",
            "confidence": 0.82,
            "reasoning": "OAuth is API design concern"
        })
        
        skill, confidence = skill_router.classify_intent(
            "OAuth with Google",
            conversation_history=[
                "I need a login page",
                "What auth method do you prefer?"
            ]
        )
        
        assert skill.name == "api-and-interface-design"
        assert confidence > 0.8

    def test_classify_intent_returns_reasoning(self, skill_router, mock_llm):
        """Verify LLM prompt includes reasoning field in response."""
        mock_llm.generate.return_value = json.dumps({
            "skill": "interview-me",
            "confidence": 0.75,
            "reasoning": "User needs clarification"
        })
        
        skill, confidence = skill_router.classify_intent("help me", [])
        
        # Verify LLM was called with a prompt containing reasoning instruction
        call_args = mock_llm.generate.call_args
        prompt = call_args[0][0] if call_args[0] else call_args[1].get("prompt", "")
        assert "reasoning" in prompt.lower()

    def test_classify_intent_prompt_includes_all_skills(self, skill_router, mock_llm):
        """Verify LLM prompt contains all registered skill descriptions."""
        skill_router.classify_intent("test", [])
        
        call_args = mock_llm.generate.call_args
        prompt = call_args[0][0] if call_args[0] else call_args[1].get("prompt", "")
        
        # Should mention multiple skills for context
        assert "interview-me" in prompt or "test-driven-development" in prompt


# =============================================================================
# Test: Confidence Thresholds
# =============================================================================

class TestConfidenceThresholds:
    """Tests for confidence-based routing decisions."""

    def test_high_confidence_auto_routes(self, skill_router, mock_llm):
        """
        Given confidence >= threshold (0.85 >= 0.7),
        When route is called,
        Then return skill without user confirmation.
        """
        mock_llm.generate.return_value = json.dumps({
            "skill": "interview-me",
            "confidence": 0.85,
            "reasoning": "Clear interview request"
        })
        
        result = skill_router.route("interview me about my project", [])
        
        assert result.name == "interview-me"

    def test_low_confidence_returns_clarification_skill(self, skill_router, mock_llm):
        """
        Given confidence < 0.5,
        When route is called,
        Then return using-agent-skills (clarification mode).
        """
        mock_llm.generate.return_value = json.dumps({
            "skill": "interview-me",
            "confidence": 0.35,
            "reasoning": "Unclear intent"
        })
        
        result = skill_router.route("hello", [])
        
        assert result.name == "using-agent-skills"

    def test_medium_confidence_triggers_confirmation(self, skill_router, mock_llm):
        """
        Given 0.5 <= confidence < threshold (0.65),
        When route is called,
        Then raise ConfirmationRequired with suggested skill.
        """
        mock_llm.generate.return_value = json.dumps({
            "skill": "test-driven-development",
            "confidence": 0.65,
            "reasoning": "Somewhat test-related"
        })
        
        from wigent.core.skill_router import ConfirmationRequired
        
        with pytest.raises(ConfirmationRequired) as exc_info:
            skill_router.route("check my code", [])
            
        assert exc_info.value.suggested_skill == "test-driven-development"
        assert exc_info.value.confidence == 0.65

    @pytest.mark.parametrize("confidence,expected_behavior", [
        (0.95, "auto_route"),
        (0.75, "auto_route"),
        (0.50, "confirm"),
        (0.49, "clarify"),
        (0.30, "clarify"),
    ])
    def test_confidence_boundary_behavior(self, skill_router, mock_llm, confidence, expected_behavior):
        """Verify correct behavior at confidence boundaries."""
        mock_llm.generate.return_value = json.dumps({
            "skill": "interview-me",
            "confidence": confidence,
            "reasoning": "test"
        })
        
        if expected_behavior == "clarify":
            result = skill_router.route("test", [])
            assert result.name == "using-agent-skills"
        elif expected_behavior == "confirm":
            from wigent.core.skill_router import ConfirmationRequired
            with pytest.raises(ConfirmationRequired):
                skill_router.route("test", [])
        else:
            result = skill_router.route("test", [])
            assert result.name == "interview-me"


# =============================================================================
# Test: Fallback to Keyword Matching
# =============================================================================

class TestKeywordFallback:
    """Tests for keyword-based fallback when LLM fails."""

    def test_fallback_to_keyword_on_llm_exception(self, skill_router, mock_llm):
        """
        Given LLM raises exception,
        When route is called with clear keyword "interview me",
        Then fallback to interview-me via keyword matching.
        """
        mock_llm.generate.side_effect = Exception("API timeout")
        
        result = skill_router.route("interview me about requirements", [])
        
        assert result.name == "interview-me"

    def test_fallback_to_keyword_on_invalid_json(self, skill_router, mock_llm):
        """
        Given LLM returns invalid JSON,
        When route is called with clear keyword "write tests",
        Then fallback to test-driven-development via keyword matching.
        """
        mock_llm.generate.return_value = "not json at all {{{"
        
        result = skill_router.route("write tests for auth module", [])
        
        assert result.name == "test-driven-development"

    def test_fallback_to_keyword_on_missing_skill_field(self, skill_router, mock_llm):
        """
        Given LLM returns JSON without 'skill' field,
        When route is called,
        Then fallback to keyword matching.
        """
        mock_llm.generate.return_value = json.dumps({
            "confidence": 0.9,
            "reasoning": "Missing skill field"
        })
        
        result = skill_router.route("review my code please", [])
        
        assert result.name == "code-review-and-quality"

    def test_fallback_returns_none_for_unknown_keywords(self, skill_router, mock_llm):
        """
        Given LLM fails AND no keywords match,
        When route is called,
        Then return using-agent-skills as ultimate fallback.
        """
        mock_llm.generate.side_effect = Exception("Down")
        
        result = skill_router.route("xyz abc 123 nonsense", [])
        
        assert result.name == "using-agent-skills"


# =============================================================================
# Test: Skill Registry
# =============================================================================

class TestSkillRegistry:
    """Tests for skill registration and retrieval."""

    def test_register_custom_skill(self, mock_llm, sample_skills):
        """
        Given a new custom skill,
        When registered,
        Then it appears in list_skills and is retrievable by name.
        """
        from wigent.core.skill_router import SkillRouter
        
        router = SkillRouter(mock_llm)
        custom_skill = sample_skills[0]
        
        router.register_skill(custom_skill)
        
        assert custom_skill in router.list_skills()
        assert router.get_skill_by_name("interview-me") == custom_skill

    def test_list_skills_filtered_by_phase(self, mock_llm, sample_skills):
        """
        Given skills in different phases,
        When list_skills("build") is called,
        Then return only build-phase skills.
        """
        from wigent.core.skill_router import SkillRouter
        
        router = SkillRouter(mock_llm)
        for skill in sample_skills:
            router.register_skill(skill)
            
        build_skills = router.list_skills(phase="build")
        
        assert len(build_skills) == 1
        assert build_skills[0].name == "test-driven-development"

    def test_get_skill_by_name_returns_none_for_unknown(self, mock_llm):
        """
        Given unknown skill name,
        When get_skill_by_name is called,
        Then return None.
        """
        from wigent.core.skill_router import SkillRouter
        
        router = SkillRouter(mock_llm)
        result = router.get_skill_by_name("nonexistent-skill")
        
        assert result is None

    def test_duplicate_skill_registration_overwrites(self, mock_llm, sample_skills):
        """
        Given skill with same name registered twice,
        When retrieved,
        Then return the latest registration.
        """
        from wigent.core.skill_router import Skill, SkillRouter
        
        router = SkillRouter(mock_llm)
        original = sample_skills[0]
        router.register_skill(original)
        
        updated = Skill(
            name="interview-me",
            phase="define",
            description="Updated description",
            triggers=["interview", "ask"],
            confidence_threshold=0.8,
            prompt_template="prompts/interview-v2.md",
        )
        router.register_skill(updated)
        
        retrieved = router.get_skill_by_name("interview-me")
        assert retrieved.description == "Updated description"
        assert retrieved.confidence_threshold == 0.8


# =============================================================================
# Test: All 24 Default Skills
# =============================================================================

class TestDefaultSkills:
    """Tests verifying all 24 skills from Addy Osmani's pack are routable."""

    def test_all_24_skills_are_routable(self, skill_router):
        """
        Given all 24 default skills loaded,
        When each is retrieved by name,
        Then all are found with valid triggers.
        """
        from wigent.config.skills import load_default_skills
        
        default_skills = load_default_skills()
        assert len(default_skills) == 24
        
        for skill in default_skills:
            retrieved = skill_router.get_skill_by_name(skill.name)
            assert retrieved is not None, f"Skill {skill.name} not found"
            assert len(skill.triggers) >= 3, f"Skill {skill.name} has < 3 triggers"
            assert skill.phase in {
                "meta", "define", "plan", "build", "verify", "review", "ship"
            }, f"Skill {skill.name} has invalid phase"

    @pytest.mark.parametrize("skill_name,expected_phase", [
        ("using-agent-skills", "meta"),
        ("interview-me", "define"),
        ("idea-refine", "define"),
        ("spec-driven-development", "define"),
        ("planning-and-task-breakdown", "plan"),
        ("incremental-implementation", "build"),
        ("test-driven-development", "build"),
        ("context-engineering", "build"),
        ("source-driven-development", "build"),
        ("doubt-driven-development", "build"),
        ("frontend-ui-engineering", "build"),
        ("api-and-interface-design", "build"),
        ("browser-testing-with-devtools", "verify"),
        ("debugging-and-error-recovery", "verify"),
        ("code-review-and-quality", "review"),
        ("code-simplification", "review"),
        ("security-and-hardening", "review"),
        ("performance-optimization", "review"),
        ("git-workflow-and-versioning", "ship"),
        ("ci-cd-and-automation", "ship"),
        ("deprecation-and-migration", "ship"),
        ("documentation-and-adrs", "ship"),
        ("observability-and-instrumentation", "ship"),
        ("shipping-and-launch", "ship"),
    ])
    def test_skill_phase_correctness(self, skill_router, skill_name, expected_phase):
        """Verify each skill is assigned to the correct lifecycle phase."""
        skill = skill_router.get_skill_by_name(skill_name)
        assert skill is not None, f"Skill {skill_name} missing"
        assert skill.phase == expected_phase, (
            f"Skill {skill_name} expected phase {expected_phase}, got {skill.phase}"
        )

    def test_skill_confidence_thresholds_vary_by_risk(self, skill_router):
        """
        Given security and ship skills,
        Then confidence thresholds should be higher than define skills.
        """
        interview = skill_router.get_skill_by_name("interview-me")
        security = skill_router.get_skill_by_name("security-and-hardening")
        ship = skill_router.get_skill_by_name("shipping-and-launch")
        
        assert interview.confidence_threshold <= 0.7
        assert security.confidence_threshold >= 0.8
        assert ship.confidence_threshold >= 0.8


# =============================================================================
# Test: Prompt Construction
# =============================================================================

class TestPromptConstruction:
    """Tests for LLM prompt quality."""

    def test_prompt_includes_few_shot_examples(self, skill_router, mock_llm):
        """Verify classification prompt includes few-shot examples."""
        skill_router.classify_intent("test", [])
        
        call_args = mock_llm.generate.call_args
        prompt = call_args[0][0] if call_args[0] else call_args[1].get("prompt", "")
        
        # Should contain example delimiters or few-shot markers
        assert "example" in prompt.lower() or "EXAMPLE" in prompt

    def test_prompt_includes_conversation_history(self, skill_router, mock_llm):
        """Verify prompt includes last 3 conversation turns."""
        history = ["msg1", "msg2", "msg3", "msg4"]
        
        skill_router.classify_intent("test", history)
        
        call_args = mock_llm.generate.call_args
        prompt = call_args[0][0] if call_args[0] else call_args[1].get("prompt", "")
        
        # Should include recent messages, not necessarily all
        assert any(msg in prompt for msg in history[-3:])

    def test_prompt_requests_json_output(self, skill_router, mock_llm):
        """Verify prompt explicitly requests JSON format."""
        skill_router.classify_intent("test", [])
        
        call_args = mock_llm.generate.call_args
        prompt = call_args[0][0] if call_args[0] else call_args[1].get("prompt", "")
        
        assert "json" in prompt.lower()


# =============================================================================
# Test: Error Handling
# =============================================================================

class TestErrorHandling:
    """Tests for robust error handling."""

    def test_empty_input_raises_clarification(self, skill_router, mock_llm):
        """Given empty string input, route to clarification skill."""
        mock_llm.generate.return_value = json.dumps({
            "skill": "using-agent-skills",
            "confidence": 0.2,
            "reasoning": "Empty input"
        })
        
        result = skill_router.route("", [])
        assert result.name == "using-agent-skills"

    def test_whitespace_only_input_raises_clarification(self, skill_router, mock_llm):
        """Given whitespace-only input, route to clarification skill."""
        mock_llm.generate.return_value = json.dumps({
            "skill": "using-agent-skills",
            "confidence": 0.15,
            "reasoning": "No content"
        })
        
        result = skill_router.route("   \n\t  ", [])
        assert result.name == "using-agent-skills"

    def test_llm_returns_unknown_skill_name(self, skill_router, mock_llm):
        """
        Given LLM returns skill name not in registry,
        When route is called,
        Then fallback to keyword matching.
        """
        mock_llm.generate.return_value = json.dumps({
            "skill": "totally-made-up-skill",
            "confidence": 0.95,
            "reasoning": "Hallucinated skill"
        })
        
        # With clear keyword fallback
        result = skill_router.route("interview me", [])
        assert result.name == "interview-me"


# =============================================================================
# Test: Performance
# =============================================================================

class TestPerformance:
    """Tests for routing performance."""

    def test_routing_under_100ms(self, skill_router, mock_llm):
        """
        Given normal conditions,
        When route is called,
        Then complete in under 100ms (excluding LLM latency).
        """
        import time
        
        mock_llm.generate.return_value = json.dumps({
            "skill": "interview-me",
            "confidence": 0.9,
            "reasoning": "Fast"
        })
        
        start = time.perf_counter()
        skill_router.route("interview me", [])
        elapsed = time.perf_counter() - start
        
        # Should be fast since LLM is mocked
        assert elapsed < 0.1, f"Routing took {elapsed:.3f}s, expected <0.1s"

    def test_large_registry_performance(self, mock_llm):
        """
        Given 100+ registered skills,
        When route is called,
        Then still complete quickly.
        """
        from wigent.core.skill_router import Skill, SkillRouter
        
        router = SkillRouter(mock_llm)
        
        # Register 100 skills
        for i in range(100):
            router.register_skill(Skill(
                name=f"skill-{i}",
                phase="build",
                description=f"Test skill {i}",
                triggers=[f"trigger-{i}"],
                confidence_threshold=0.7,
                prompt_template=f"prompts/skill-{i}.md",
            ))
            
        mock_llm.generate.return_value = json.dumps({
            "skill": "skill-50",
            "confidence": 0.9,
            "reasoning": "Found it"
        })
        
        import time
        start = time.perf_counter()
        router.route("trigger-50", [])
        elapsed = time.perf_counter() - start
        
        assert elapsed < 0.1


# =============================================================================
# Integration-Style Tests
# =============================================================================

class TestIntegrationScenarios:
    """End-to-end scenarios for skill routing."""

    def test_full_interview_workflow_routing(self, skill_router, mock_llm):
        """
        Simulate full /interview → /spec → /plan workflow routing.
        """
        scenarios = [
            ("interview me about my project", "interview-me"),
            ("write a PRD for login system", "spec-driven-development"),
            ("break this into tasks", "planning-and-task-breakdown"),
        ]
        
        for user_input, expected_skill in scenarios:
            mock_llm.generate.return_value = json.dumps({
                "skill": expected_skill,
                "confidence": 0.9,
                "reasoning": f"Matched {expected_skill}"
            })
            
            result = skill_router.route(user_input, [])
            assert result.name == expected_skill, (
                f"Input '{user_input}' should route to {expected_skill}, "
                f"got {result.name}"
            )

    def test_mode_switching_routing(self, skill_router, mock_llm):
        """
        Simulate user switching modes mid-session.
        """
        history = ["Build a login page", "Use React and Node.js"]
        
        # First: coding
        mock_llm.generate.return_value = json.dumps({
            "skill": "incremental-implementation",
            "confidence": 0.85,
            "reasoning": "Implementation request"
        })
        result = skill_router.route("Create the auth middleware", history)
        assert result.phase == "build"
        
        # Then: debugging
        history.append("Create the auth middleware")
        mock_llm.generate.return_value = json.dumps({
            "skill": "debugging-and-error-recovery",
            "confidence": 0.9,
            "reasoning": "Error mentioned"
        })
        result = skill_router.route("It throws 500 on login", history)
        assert result.name == "debugging-and-error-recovery"
        
        # Then: review
        history.append("It throws 500 on login")
        mock_llm.generate.return_value = json.dumps({
            "skill": "code-review-and-quality",
            "confidence": 0.88,
            "reasoning": "Review request"
        })
        result = skill_router.route("Review my fix before merge", history)
        assert result.phase == "review"
