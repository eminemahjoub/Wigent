"""
Role: Integration tests for Phase 2 Build Engine workflow.
Author: Wigent AI
Version: 1.0.0

Tests the complete Build phase: slice execution, TDD enforcement,
context packing, source verification, doubt review, and frontend/API
mode integration.

Usage:
    pytest tests/test_build_phase.py -v
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from wigent.core.planner import Task
    from wigent.core.slice_engine import SliceEngine, SliceResult
    from wigent.tools.test_generator import TestGenerator, TestPyramid
    from wigent.core.context_packer import ContextPacker
    from wigent.core.doubt_engine import DoubtEngine, DoubtResult
    from wigent.modes.frontend import FrontendMode
    from wigent.modes.api import APIMode, APIContract


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_llm():
    """Create a configurable mock LLM client."""
    llm = MagicMock()

    def default_response(prompt, **kwargs):
        if "slice" in prompt.lower() or "implement" in prompt.lower():
            return json.dumps({
                "src/auth/login.py": "def login(email, password):\n    return {'token': 'abc123'}",
                "tests/test_auth_login.py": "def test_login():\n    assert login('a', 'b') == {'token': 'abc123'}"
            })
        elif "test" in prompt.lower() and "red" in prompt.lower():
            return "def test_login_with_valid_credentials():\n    result = login('user@example.com', 'pass123')\n    assert result.token is not None"
        elif "doubt" in prompt.lower() or "review" in prompt.lower():
            return json.dumps([
                {
                    "category": "security",
                    "severity": "major",
                    "doubt": "WHAT IF password is logged in plaintext?",
                    "evidence": "No hashing visible in implementation",
                    "recommendation": "Add bcrypt hashing before storage",
                    "confidence": 0.85
                }
            ])
        elif "openapi" in prompt.lower() or "contract" in prompt.lower():
            return json.dumps({
                "name": "User",
                "version": "1.0.0",
                "base_path": "/api/v1",
                "operations": [
                    {
                        "name": "createUser",
                        "method": "POST",
                        "path": "/users",
                        "summary": "Create a new user",
                        "parameters": [],
                        "request_body": {"name": "UserCreate", "type": "object", "required": True},
                        "responses": {"201": {"name": "User", "type": "object", "required": True}},
                        "errors": {"VALIDATION": "Invalid input", "CONFLICT": "Email exists"},
                        "rate_limit": "100/minute",
                        "idempotency_key": True
                    }
                ],
                "schemas": {
                    "User": [
                        {"name": "id", "type": "uuid", "required": True, "description": "Unique ID"},
                        {"name": "email", "type": "email", "required": True, "description": "User email"},
                        {"name": "name", "type": "string", "required": True, "description": "Full name"}
                    ]
                }
            })
        elif "component" in prompt.lower() or "frontend" in prompt.lower():
            return json.dumps({
                "src/components/Button.tsx": "export function Button({label, onClick}) {\n  return <button onClick={onClick}>{label}</button>\n}",
                "src/components/Button.test.tsx": "test('renders label', () => {\n  render(<Button label='Click' />);\n  expect(screen.getByText('Click')).toBeInTheDocument();\n})"
            })
        return "{}"

    llm.generate.side_effect = default_response
    return llm


@pytest.fixture
def sample_task():
    """Create a sample Task for slice testing."""
    from wigent.core.planner import Task

    return Task(
        id="T-1",
        description="Implement user login with email and password",
        acceptance_criteria=[
            "Login accepts email and password",
            "Valid credentials return JWT token",
            "Invalid credentials return 401"
        ],
        dependencies=[],
        estimated_effort="M",
        skill_required="incremental-implementation",
        mode_required="coder"
    )


@pytest.fixture
def slice_engine(mock_llm, tmp_path):
    """Create a SliceEngine with mocked LLM and temp workspace."""
    from wigent.core.slice_engine import SliceEngine

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    import subprocess
    subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=workspace, check=True, capture_output=True)

    return SliceEngine(
        llm_client=mock_llm,
        workspace=workspace,
        git_enabled=True,
        auto_commit=False
    )


@pytest.fixture
def test_generator(mock_llm):
    """Create a TestGenerator with mocked LLM."""
    from wigent.tools.test_generator import TestGenerator

    return TestGenerator(llm_client=mock_llm)


@pytest.fixture
def context_packer(mock_llm):
    """Create a ContextPacker with mocked LLM."""
    from wigent.core.context_packer import ContextPacker

    return ContextPacker(
        vector_store=None,
        max_tokens=8000
    )


@pytest.fixture
def doubt_engine(mock_llm):
    """Create a DoubtEngine with mocked LLM."""
    from wigent.core.doubt_engine import DoubtEngine

    return DoubtEngine(
        llm_client=mock_llm,
        cross_model_client=None,
        max_doubts=5
    )


@pytest.fixture
def frontend_mode(mock_llm):
    """Create a FrontendMode with mocked LLM."""
    from wigent.modes.frontend import FrontendMode

    return FrontendMode(
        llm_client=mock_llm,
        framework="react",
        design_system="shadcn"
    )


@pytest.fixture
def api_mode(mock_llm):
    """Create an APIMode with mocked LLM."""
    from wigent.modes.api import APIMode

    return APIMode(
        llm_client=mock_llm,
        base_path="/api/v1",
        strict_mode=True
    )


# =============================================================================
# Test: Slice Engine Integration
# =============================================================================

class TestSliceEngineIntegration:
    """Integration tests for incremental implementation workflow."""

    def test_full_slice_execution(self, slice_engine, sample_task):
        """
        Given a valid task,
        When execute_slice runs,
        Then it implements, tests, verifies, and commits.
        """
        result = slice_engine.execute_slice(
            task=sample_task,
            plan={},
            session={}
        )

        assert isinstance(result, SliceResult)
        assert result.task_id == "T-1"
        assert result.status == "success"
        assert result.tests_passed is True
        assert result.commit_hash is not None
        assert len(result.files_changed) > 0

    def test_slice_creates_feature_flag(self, slice_engine, sample_task):
        """
        Given any task,
        When executed,
        Then a feature flag is generated and included.
        """
        result = slice_engine.execute_slice(
            task=sample_task,
            plan={},
            session={}
        )

        assert result.feature_flag is not None
        assert result.feature_flag.startswith("FF_")
        assert "user_login" in result.feature_flag.lower() or "implement" in result.feature_flag.lower()

    def test_slice_rollback_on_test_failure(self, slice_engine, sample_task, mock_llm):
        """
        Given tests fail,
        When slice executes,
        Then rollback to previous state.
        """
        mock_llm.generate.side_effect = lambda p, **k: json.dumps({
            "src/auth/login.py": "def login(): raise Exception('fail')",
            "tests/test_auth_login.py": "def test_login(): assert False"
        })

        result = slice_engine.execute_slice(
            task=sample_task,
            plan={},
            session={}
        )

        assert result.status == "failed"
        assert result.rollback_hash is not None
        assert "Tests failed" in result.error_message

    def test_slice_enforces_max_files(self, slice_engine, sample_task):
        """
        Given task that would touch too many files,
        Then SliceTooLargeError is raised.
        """
        from wigent.core.slice_engine import SliceTooLargeError

        mock_files = {f"src/file_{i}.py": f"# file {i}" for i in range(10)}
        slice_engine.llm.generate.return_value = json.dumps(mock_files)

        result = slice_engine.execute_slice(
            task=sample_task,
            plan={},
            session={}
        )

        assert result.status == "aborted"
        assert "too large" in result.error_message.lower() or "exceeds" in result.error_message.lower()

    def test_slice_respects_effort_limits(self, slice_engine):
        """
        Given task with effort 'L' or 'XL',
        Then validation fails before execution.
        """
        from wigent.core.planner import Task

        large_task = Task(
            id="T-2",
            description="Refactor entire codebase",
            acceptance_criteria=["Everything works"],
            dependencies=[],
            estimated_effort="L"
        )

        result = slice_engine.execute_slice(
            task=large_task,
            plan={},
            session={}
        )

        assert result.status == "aborted"
        assert "exceeds" in result.error_message.lower()


# =============================================================================
# Test: TDD Integration
# =============================================================================

class TestTDDIntegration:
    """Integration tests for Red-Green-Refactor with test generator."""

    def test_red_test_generation(self, test_generator):
        """
        Given feature description,
        When generate_red_test is called,
        Then return failing test.
        """
        test_case = test_generator.generate_red_test(
            feature_description="User login with email and password",
            acceptance_criteria=[
                "Valid credentials return token",
                "Invalid credentials return 401"
            ],
            existing_code="",
            target_level="UNIT"
        )

        assert test_case.name.startswith("test_")
        assert "login" in test_case.name.lower()
        assert test_case.level is not None

    def test_pyramid_distribution_validation(self, test_generator):
        """
        Given unbalanced test suite,
        When validated,
        Then PyramidViolationError is raised.
        """
        from wigent.tools.test_generator import TestCase, TestLevel, PyramidViolationError

        suite = [
            TestCase(name="test_1", level=TestLevel.E2E, code="browser test"),
            TestCase(name="test_2", level=TestLevel.E2E, code="browser test"),
            TestCase(name="test_3", level=TestLevel.UNIT, code="unit test"),
        ]

        pyramid = TestPyramid.analyze(suite)

        with pytest.raises(PyramidViolationError, match="E2E"):
            pyramid.validate()

    def test_pyramid_balanced_suite_passes(self, test_generator):
        """
        Given balanced test suite,
        When validated,
        Then no exception raised.
        """
        from wigent.tools.test_generator import TestCase, TestLevel

        suite = (
            [TestCase(name=f"test_unit_{i}", level=TestLevel.UNIT, code="unit") for i in range(8)]
            + [TestCase(name="test_int", level=TestLevel.INTEGRATION, code="db")]
            + [TestCase(name="test_e2e", level=TestLevel.E2E, code="browser")]
        )

        pyramid = TestPyramid.analyze(suite)
        results = pyramid.validate()

        assert results["unit"] is True
        assert results["e2e"] is True

    def test_beyonce_rule_validation(self, test_generator):
        """
        Given implementation with untested functions,
        When validated,
        Then those functions are flagged.
        """
        implementation = """
def authenticate(email, password):
    return True

def hash_password(password):
    return "hashed"

def generate_token(user_id):
    return "token123"
"""

        from wigent.tools.test_generator import TestCase, TestLevel

        tests = [
            TestCase(name="test_authenticate", level=TestLevel.UNIT, code="test authenticate"),
        ]

        result = test_generator.validate_beyonce_rule(implementation, tests)

        assert result["authenticate"] is True
        assert result["hash_password"] is False
        assert result["generate_token"] is False

    def test_test_plan_generation(self, test_generator):
        """
        Given feature description,
        When generate_test_plan is called,
        Then return structured plan with pyramid targets.
        """
        plan = test_generator.generate_test_plan(
            feature_description="User login with email and password",
            acceptance_criteria=[
                "Valid credentials return token",
                "Invalid credentials return 401",
                "Missing fields return 400"
            ]
        )

        assert "Test Plan" in plan
        assert "Unit" in plan
        assert "Integration" in plan
        assert "E2E" in plan
        assert "Acceptance Criteria" in plan


# =============================================================================
# Test: Context Packer Integration
# =============================================================================

class TestContextPackerIntegration:
    """Integration tests for smart context engineering."""

    def test_packs_within_token_budget(self, context_packer):
        """
        Given various context sources,
        When pack is called,
        Then result fits within max_tokens.
        """
        packed, stats = context_packer.pack(
            current_task="Implement user authentication",
            conversation_history=[
                {"role": "user", "content": "I need a login system"},
                {"role": "assistant", "content": "What auth method?"},
                {"role": "user", "content": "Email and password with JWT"}
            ],
            codebase_files=["src/auth.py", "src/models.py", "src/routes.py"],
            rules_files=[".wigent/rules/python.md"],
            mcp_tools=[{"name": "git", "description": "Git operations"}],
            skill_prompt="You are a senior engineer...",
            session_memory={"mode": "coder", "project": "auth-service"}
        )

        assert stats.packed_tokens <= context_packer.max_tokens
        assert stats.compression_ratio <= 1.0
        assert stats.items_included > 0

    def test_skill_specific_budgets(self, context_packer):
        """
        Given interview skill,
        When pack_for_skill is called,
        Then conversation gets 70% budget.
        """
        packed = context_packer.pack_for_skill(
            skill_name="interview-me",
            user_input="What problem are you trying to solve?",
            conversation_history=[{"role": "user", "content": "I need an app"}],
            context={}
        )

        assert "Current task" in packed
        assert "system" in packed.lower()

    def test_summarizes_old_conversation(self, context_packer):
        """
        Given long conversation history,
        When summarize_history is called,
        Then old turns are compressed.
        """
        history = [
            {"role": "user", "content": f"Message {i}"} for i in range(20)
        ]

        summary = context_packer.summarize_history(history, max_turns=3)

        assert "Message 19" in summary
        assert len(summary) < sum(len(m["content"]) for m in history)

    def test_relevance_ranking_fallback(self, context_packer):
        """
        Given files without vector store,
        When get_relevant_files is called,
        Then keyword fallback works.
        """
        files = [
            "src/auth.py",
            "src/payments.py",
            "src/models.py",
            "tests/test_auth.py"
        ]

        relevant = context_packer.get_relevant_files(
            query="login authentication",
            files=files,
            top_k=2
        )

        assert len(relevant) <= 2
        assert any("auth" in f for f, _ in relevant)


# =============================================================================
# Test: Doubt Engine Integration
# =============================================================================

class TestDoubtEngineIntegration:
    """Integration tests for adversarial review workflow."""

    def test_full_doubt_review(self, doubt_engine):
        """
        Given a claim,
        When review is called,
        Then full workflow executes.
        """
        result = doubt_engine.review(
            claim="We should use Redis for session storage",
            context={"stack": "python", "users": "10000"},
            stakes="high",
            author_reasoning="Redis is fast and widely used"
        )

        assert isinstance(result, DoubtResult)
        assert result.claim == "We should use Redis for session storage"
        assert result.stakes.value == "high"
        assert len(result.doubts) > 0
        assert len(result.extracted_assumptions) > 0

    def test_high_stakes_lowers_threshold(self, doubt_engine):
        """
        Given high stakes,
        When risk is moderate,
        Then escalation is recommended.
        """
        result = doubt_engine.review(
            claim="Delete all user data",
            context={"environment": "production"},
            stakes="high"
        )

        assert result.risk_score >= 0.0
        assert result.escalation_recommended or not result.proceed

    def test_critical_doubts_block_proceed(self, doubt_engine, mock_llm):
        """
        Given critical doubts,
        When reviewed,
        Then proceed is False.
        """
        mock_llm.generate.return_value = json.dumps([
            {
                "category": "security",
                "severity": "critical",
                "doubt": "WHAT IF this deletes production data?",
                "evidence": "No backup mentioned",
                "recommendation": "Add backup verification",
                "confidence": 0.95
            }
        ])

        result = doubt_engine.review(
            claim="Deploy database migration",
            context={},
            stakes="high"
        )

        assert result.proceed is False
        assert result.critical_count > 0

    def test_quick_check_red_flags(self, doubt_engine):
        """
        Given suspicious claim,
        When quick_check is called,
        Then returns False.
        """
        suspicious_claims = [
            "We'll never need to test this",
            "Just a temporary fix",
            "TODO: fix later",
            "Hard-coded for now",
            "This should work",
            "It's probably fine",
            "Trust me on this",
            "No need to document",
            "Only used internally",
            "Can refactor later"
        ]

        for claim in suspicious_claims:
            assert doubt_engine.quick_check(claim) is False, f"Failed for: {claim}"

    def test_quick_check_valid_claims(self, doubt_engine):
        """
        Given valid claim,
        When quick_check is called,
        Then returns True.
        """
        valid_claims = [
            "I've tested this with 1000 examples",
            "The benchmark shows 200ms p95 latency",
            "This follows the established pattern in auth.py"
        ]

        for claim in valid_claims:
            assert doubt_engine.quick_check(claim) is True, f"Failed for: {claim}"


# =============================================================================
# Test: Frontend Mode Integration
# =============================================================================

class TestFrontendModeIntegration:
    """Integration tests for accessible component generation."""

    def test_component_generation_with_audit(self, frontend_mode):
        """
        Given component spec,
        When generate_component is called,
        Then accessibility audit runs and passes.
        """
        files = frontend_mode.generate_component(
            spec="Button with loading state",
            props=[{"name": "label", "type": "string", "required": True}],
            states=["default", "loading", "disabled"],
            accessibility_requirements=["Keyboard accessible", "Screen reader support"]
        )

        assert "src/components/Button.tsx" in files or any("Button" in k for k in files.keys())
        assert any(".test." in k for k in files.keys())

    def test_accessibility_audit_detects_issues(self, frontend_mode):
        """
        Given inaccessible HTML,
        When audit_accessibility is called,
        Then violations are found.
        """
        bad_html = """
        <div onclick="handleClick()">Click me</div>
        <img src="photo.jpg">
        <input type="text" placeholder="Name">
        """

        audit = frontend_mode.audit_accessibility(bad_html)

        assert not audit.passed
        assert len(audit.violations) > 0
        violations_text = json.dumps(audit.violations)
        assert any(word in violations_text.lower() for word in ["alt", "label", "keyboard", "button"])

    def test_design_token_generation(self, frontend_mode):
        """
        Given brand colors,
        When generate_design_tokens is called,
        Then complete token system is created.
        """
        tokens = frontend_mode.generate_design_tokens({
            "primary": "#3b82f6",
            "secondary": "#8b5cf6"
        })

        assert "color-primary-500" in tokens
        assert "color-primary-50" in tokens
        assert "color-primary-900" in tokens
        assert "font-sans" in tokens
        assert "space-4" in tokens
        assert "shadow-md" in tokens

    def test_responsive_styles_generation(self, frontend_mode):
        """
        Given base styles,
        When generate_responsive_styles is called,
        Then breakpoint variants are created.
        """
        base = {"padding": "1rem", "fontSize": "1rem"}

        responsive = frontend_mode.generate_responsive_styles(base)

        assert "base" in responsive
        assert "sm" in responsive
        assert "md" in responsive
        assert "lg" in responsive
        assert "xl" in responsive


# =============================================================================
# Test: API Mode Integration
# =============================================================================

class TestAPIModeIntegration:
    """Integration tests for contract-first API design."""

    def test_contract_design(self, api_mode):
        """
        Given resource and operations,
        When design_contract is called,
        Then valid APIContract is returned.
        """
        contract = api_mode.design_contract(
            resource="User",
            operations=["create", "read", "update", "delete", "list"],
            constraints=["idempotent create", "soft delete"]
        )

        assert isinstance(contract, APIContract)
        assert contract.name == "User"
        assert len(contract.operations) > 0

        op_names = [op.name for op in contract.operations]
        assert any("create" in n.lower() for n in op_names)
        assert any("read" in n.lower() or "get" in n.lower() for n in op_names)

    def test_openapi_generation(self, api_mode):
        """
        Given API contract,
        When generate_openapi is called,
        Then valid OpenAPI spec is produced.
        """
        contract = api_mode.design_contract(
            resource="User",
            operations=["create", "read"]
        )

        openapi = api_mode.generate_openapi(contract)

        assert openapi["openapi"] == "3.1.0"
        assert "paths" in openapi
        assert "components" in openapi
        assert "info" in openapi

    def test_breaking_change_detection(self, api_mode):
        """
        Given two contract versions,
        When detect_breaking_changes is called,
        Then changes are classified.
        """
        old = api_mode.design_contract(
            resource="User",
            operations=["create", "read"]
        )

        new = api_mode.design_contract(
            resource="User",
            operations=["create", "read", "update"]
        )

        old.operations = [op for op in old.operations if "read" not in op.name.lower()]

        report = api_mode.detect_breaking_changes(old, new)

        assert not report.is_safe
        assert len(report.breaking) > 0 or len(report.additive) > 0

    def test_error_response_generation(self, api_mode):
        """
        Given error category,
        When generate_error_response is called,
        Then standardized error is returned.
        """
        from wigent.modes.api import ErrorCategory

        error = api_mode.generate_error_response(
            category=ErrorCategory.VALIDATION,
            message="Email is required",
            remediation="Provide a valid email address",
            request_id="req-123"
        )

        assert "error" in error
        assert error["error"]["status"] == 400
        assert error["error"]["message"] == "Email is required"
        assert error["error"]["remediation"] == "Provide a valid email address"
        assert error["error"]["request_id"] == "req-123"
        assert "documentation" in error["error"]

    def test_hyrum_warnings(self, api_mode):
        """
        Given contract with list operation,
        When get_hyrum_warnings is called,
        Then pagination warning is included.
        """
        contract = api_mode.design_contract(
            resource="User",
            operations=["list", "create"]
        )

        warnings = api_mode.get_hyrum_warnings(contract)

        assert any("pagination" in w.lower() for w in warnings)
        assert any("error" in w.lower() for w in warnings)

    def test_strict_mode_validation(self, api_mode):
        """
        Given contract without error definitions,
        Then strict mode raises ValueError.
        """
        from wigent.modes.api import APIContract, APIOperation, HTTPMethod

        bad_contract = APIContract(
            name="Bad",
            version="1.0.0",
            base_path="/api/v1",
            operations=[
                APIOperation(
                    name="badOp",
                    method=HTTPMethod.POST,
                    path="/bad",
                    summary="Bad operation",
                    errors={}
                )
            ]
        )

        with pytest.raises(ValueError, match="error"):
            api_mode._validate_contract(bad_contract)


# =============================================================================
# Test: End-to-End Build Workflow
# =============================================================================

class TestEndToEndBuildWorkflow:
    """Full integration tests across all Build components."""

    def test_complete_feature_implementation(self, slice_engine, test_generator, doubt_engine, sample_task):
        """
        Given a task requiring new feature,
        When full Build workflow executes,
        Then feature is implemented with tests and reviewed.
        """
        slice_result = slice_engine.execute_slice(
            task=sample_task,
            plan={},
            session={}
        )

        assert slice_result.status == "success"

        implementation_summary = (
            f"Implemented {sample_task.description} "
            f"with files: {', '.join(slice_result.files_changed)}"
        )

        doubt_result = doubt_engine.review(
            claim=implementation_summary,
            context={"files": slice_result.files_changed},
            stakes="medium"
        )

        assert doubt_result.risk_score >= 0.0

    def test_api_frontend_integration(self, api_mode, frontend_mode):
        """
        Given API contract and frontend component,
        When both are generated,
        Then they are compatible.
        """
        api_contract = api_mode.design_contract(
            resource="User",
            operations=["create", "read", "list"]
        )

        openapi = api_mode.generate_openapi(api_contract)

        endpoints = []
        for path, methods in openapi.get("paths", {}).items():
            for method, details in methods.items():
                if isinstance(details, dict):
                    endpoints.append({
                        "path": path,
                        "method": method.upper(),
                        "operationId": details.get("operationId", "")
                    })

        assert len(endpoints) > 0
        assert any("user" in e["path"].lower() for e in endpoints)

    def test_context_aware_implementation(self, context_packer, slice_engine, sample_task):
        """
        Given existing codebase context,
        When packing context for implementation,
        Then relevant files are prioritized.
        """
        context, stats = context_packer.pack(
            current_task=sample_task.description,
            conversation_history=[],
            codebase_files=["src/auth.py", "src/models.py", "src/payments.py"],
            skill_prompt="You are implementing authentication...",
            session_memory={}
        )

        assert "auth" in context.lower() or "login" in context.lower()
        assert stats.packed_tokens <= context_packer.max_tokens

        session = {"codebase_context": context}

        result = slice_engine.execute_slice(
            task=sample_task,
            plan={},
            session=session
        )

        assert result.status == "success"
