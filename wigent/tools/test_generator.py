"""
Role: Test-driven development tool for generating and validating tests.
Author: Wigent AI
Version: 1.0.0

Enforces TDD workflow: Red -> Green -> Refactor.
Generates tests following the test pyramid (80% unit, 15% integration, 5% E2E).
Applies the Beyonce Rule: "If you liked it, you should have put a test on it."

Usage:
    from wigent.tools.test_generator import TestGenerator, TestLevel, TestPyramid

    generator = TestGenerator(llm_client)

    # Red: Generate failing test
    red_test = generator.generate_red_test(
        feature_description="User login with email and password",
        acceptance_criteria=[...],
        existing_code=current_module,
    )

    # Green: Make it pass (implementation)
    # Refactor: Improve without changing behavior

    # Validate pyramid distribution
    pyramid = TestPyramid.analyze(test_suite)
    pyramid.validate()  # Raises if distribution violates 80/15/5
"""

from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wigent.models.base_model import BaseModel


class TestLevel(Enum):
    """Test pyramid levels with target percentages."""
    UNIT = ("unit", 0.80, "<100ms, no I/O, single concern")
    INTEGRATION = ("integration", 0.15, "<5s, real DB/API, boundary crossing")
    E2E = ("e2e", 0.05, "<30s, full stack, user journey")

    def __init__(self, label: str, target: float, description: str):
        self.label = label
        self.target = target
        self.description = description


@dataclass
class TestCase:
    """A single test case with metadata for pyramid classification."""

    name: str
    level: TestLevel
    code: str
    target_function: str | None = None
    mocks: list[str] = field(default_factory=list)
    fixtures: list[str] = field(default_factory=list)
    estimated_duration_ms: int = 0
    covers_criteria: list[str] = field(default_factory=list)

    def classify_pyramid_level(self) -> TestLevel:
        """
        Auto-classify test level based on code analysis.

        Heuristics:
        - E2E: contains browser, page, click, navigate, screenshot
        - Integration: contains DB, API, client, request, database
        - Unit: everything else (default)
        """
        code_lower = self.code.lower()

        e2e_markers = ["browser", "page.", "click(", "navigate", "screenshot", "playwright", "selenium"]
        integration_markers = ["db.", "database", "client.", "request(", "api.", "http", "postgres", "redis"]

        if any(m in code_lower for m in e2e_markers):
            return TestLevel.E2E
        elif any(m in code_lower for m in integration_markers):
            return TestLevel.INTEGRATION
        else:
            return TestLevel.UNIT


@dataclass
class TestPyramid:
    """Represents the test pyramid distribution for a suite."""

    unit_count: int = 0
    integration_count: int = 0
    e2e_count: int = 0

    @classmethod
    def analyze(cls, test_cases: list[TestCase]) -> TestPyramid:
        """Analyze a test suite and compute pyramid distribution."""
        pyramid = cls()
        for test in test_cases:
            level = test.classify_pyramid_level()
            if level == TestLevel.UNIT:
                pyramid.unit_count += 1
            elif level == TestLevel.INTEGRATION:
                pyramid.integration_count += 1
            else:
                pyramid.e2e_count += 1
        return pyramid

    @property
    def total(self) -> int:
        return self.unit_count + self.integration_count + self.e2e_count

    @property
    def unit_ratio(self) -> float:
        return self.unit_count / self.total if self.total > 0 else 0

    @property
    def integration_ratio(self) -> float:
        return self.integration_count / self.total if self.total > 0 else 0

    @property
    def e2e_ratio(self) -> float:
        return self.e2e_count / self.total if self.total > 0 else 0

    def validate(self, tolerance: float = 0.10) -> dict[str, bool]:
        """
        Validate pyramid distribution against targets.

        Args:
            tolerance: Acceptable deviation from target (default 10%)

        Returns:
            Dict of level -> is_valid

        Raises:
            PyramidViolationError: if distribution is severely off
        """
        if self.total == 0:
            raise PyramidViolationError("No tests found -- Beyonce Rule violated!")

        results = {}
        checks = [
            (TestLevel.UNIT, self.unit_ratio),
            (TestLevel.INTEGRATION, self.integration_ratio),
            (TestLevel.E2E, self.e2e_ratio),
        ]

        for level, actual in checks:
            target = level.target
            lower_bound = max(0, target - tolerance)
            upper_bound = min(1, target + tolerance + 0.15)

            is_valid = lower_bound <= actual <= upper_bound
            results[level.label] = is_valid

        # Hard limits: E2E must never exceed 10%, Unit must never be <60%
        if self.e2e_ratio > 0.10:
            results["e2e"] = False
            raise PyramidViolationError(
                f"E2E tests at {self.e2e_ratio:.1%} -- exceeds 10% hard limit. "
                f"Move tests down the pyramid (E2E -> Integration -> Unit)."
            )

        if self.unit_ratio < 0.60:
            results["unit"] = False
            raise PyramidViolationError(
                f"Unit tests at {self.unit_ratio:.1%} -- below 60% minimum. "
                f"Extract business logic for unit testing."
            )

        return results

    def to_markdown(self) -> str:
        """Render pyramid as markdown visualization."""
        unit_bar = "|" * int(self.unit_ratio * 50)
        int_bar = "|" * int(self.integration_ratio * 50)
        e2e_bar = "|" * int(self.e2e_ratio * 50)

        return f"""## Test Pyramid Distribution

| Level | Target | Actual | Bar | Count |
|-------|--------|--------|-----|-------|
| Unit | 80% | {self.unit_ratio:.1%} | {unit_bar:<50} | {self.unit_count} |
| Integration | 15% | {self.integration_ratio:.1%} | {int_bar:<50} | {self.integration_count} |
| E2E | 5% | {self.e2e_ratio:.1%} | {e2e_bar:<50} | {self.e2e_count} |

**Total:** {self.total} tests
**Status:** {"Balanced" if self.unit_ratio >= 0.60 and self.e2e_ratio <= 0.10 else "Imbalanced"}
"""


class TestGenerator:
    """
    Generates tests following TDD principles and test pyramid targets.

    Principles:
    1. Red-Green-Refactor: test fails first, then implement, then improve
    2. Beyonce Rule: every behavior has a test
    3. DAMP over DRY: tests should read like documentation
    4. Test sizes: Unit <100ms, Integration <5s, E2E <30s
    5. Mock at boundaries, not implementation
    """

    def __init__(
        self,
        llm_client: BaseModel,
        framework: str = "pytest",
        style: str = "arrange-act-assert",
    ) -> None:
        self.llm = llm_client
        self.framework = framework
        self.style = style
        self._generated_tests: list[TestCase] = []
        self._coverage_targets: dict[str, float] = {
            "unit": 0.90,
            "integration": 0.70,
            "e2e": 0.30,
        }

    def generate_red_test(
        self,
        feature_description: str,
        acceptance_criteria: list[str],
        existing_code: str = "",
        target_level: TestLevel = TestLevel.UNIT,
    ) -> TestCase:
        """
        Generate a failing test (Red phase of TDD).

        The test should:
        1. Import the function/module under test
        2. Call it with valid inputs
        3. Assert the expected output
        4. FAIL because implementation doesn't exist yet

        Args:
            feature_description: What the feature should do
            acceptance_criteria: List of testable criteria
            existing_code: Current code context
            target_level: Target pyramid level

        Returns:
            TestCase that will fail until implemented
        """
        prompt = self._build_red_prompt(
            feature_description=feature_description,
            acceptance_criteria=acceptance_criteria,
            existing_code=existing_code,
            target_level=target_level,
        )

        response = self.llm.generate(prompt, temperature=0.2, max_tokens=3000)
        test_code = self._extract_code(response)

        test_case = TestCase(
            name=f"test_{self._slugify(feature_description)}",
            level=target_level,
            code=test_code,
            covers_criteria=acceptance_criteria,
        )

        self._generated_tests.append(test_case)
        return test_case

    def generate_green_test(
        self,
        red_test: TestCase,
        implementation: str,
    ) -> TestCase:
        """
        Update test to pass with implementation (Green phase).

        The test should:
        1. Still test the same behavior
        2. Now PASS with the implementation
        3. Not test implementation details

        Args:
            red_test: The original failing test
            implementation: The code that makes it pass

        Returns:
            Updated TestCase that passes
        """
        prompt = f"""Refine this test to work with the implementation.

## Original Test (Red)
```python
{red_test.code}
```

## Implementation
```python
{implementation}
```

## Rules
1. Keep the same test structure and assertions
2. Fix any import or naming issues
3. Add mocks for external dependencies
4. Ensure it passes with the implementation
5. Do NOT test implementation details -- test behavior

Output ONLY the updated test code.
"""

        response = self.llm.generate(prompt, temperature=0.1, max_tokens=3000)
        test_code = self._extract_code(response)

        return TestCase(
            name=red_test.name,
            level=red_test.level,
            code=test_code,
            target_function=red_test.target_function,
            covers_criteria=red_test.covers_criteria,
        )

    def generate_refactor_tests(
        self,
        green_test: TestCase,
        refactored_implementation: str,
    ) -> list[TestCase]:
        """
        Generate additional tests for edge cases during Refactor phase.

        These tests ensure the refactoring didn't break behavior.

        Args:
            green_test: The passing test
            refactored_implementation: The refactored code

        Returns:
            List of additional TestCases for edge cases
        """
        prompt = f"""Generate edge case tests for this refactored implementation.

## Original Test
```python
{green_test.code}
```

## Refactored Implementation
```python
{refactored_implementation}
```

## Edge Cases to Cover
1. Empty/null inputs
2. Boundary values (max length, zero, negative)
3. Error conditions (exceptions, timeouts)
4. Concurrency (if applicable)
5. Idempotency (same input -> same output)

## Rules
- One test per edge case
- Descriptive names: test_{scenario}_{expected}
- Use parametrize for similar cases
- Mock external dependencies
- Keep tests fast (<100ms each)

Output ONLY test code.
"""

        response = self.llm.generate(prompt, temperature=0.2, max_tokens=4000)
        test_codes = self._extract_multiple_tests(response)

        return [
            TestCase(
                name=f"{green_test.name}_edge_{i}",
                level=green_test.level,
                code=code,
                covers_criteria=green_test.covers_criteria,
            )
            for i, code in enumerate(test_codes)
        ]

    def validate_beyonce_rule(
        self,
        implementation_code: str,
        test_suite: list[TestCase],
    ) -> dict[str, bool]:
        """
        Check that every public function/class has at least one test.

        The Beyonce Rule: "If you liked it, you should have put a test on it."

        Returns:
            Dict of function_name -> has_test
        """
        # Extract public functions from implementation
        tree = ast.parse(implementation_code)
        public_functions = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if not node.name.startswith("_"):
                    public_functions.append(node.name)

        # Extract tested functions from test suite
        tested_functions = set()
        for test in test_suite:
            # Look for function names in test code
            for func in public_functions:
                if func in test.code:
                    tested_functions.add(func)

        return {
            func: func in tested_functions
            for func in public_functions
        }

    def suggest_pyramid_rebalancing(
        self,
        current_pyramid: TestPyramid,
    ) -> list[str]:
        """
        Suggest actions to rebalance the test pyramid.

        Returns:
            List of actionable recommendations
        """
        suggestions = []

        if current_pyramid.e2e_ratio > 0.10:
            excess_e2e = current_pyramid.e2e_count - int(current_pyramid.total * 0.05)
            suggestions.append(
                f"Move {excess_e2e} E2E tests down to Integration: "
                "Replace browser automation with API client calls"
            )

        if current_pyramid.integration_ratio > 0.25:
            excess_int = current_pyramid.integration_count - int(current_pyramid.total * 0.15)
            suggestions.append(
                f"Move {excess_int} Integration tests down to Unit: "
                "Mock database/external dependencies"
            )

        if current_pyramid.unit_ratio < 0.70:
            needed_unit = int(current_pyramid.total * 0.80) - current_pyramid.unit_count
            suggestions.append(
                f"Add {needed_unit} Unit tests: "
                "Extract business logic from integration tests"
            )

        if not suggestions:
            suggestions.append("Pyramid is well-balanced. Maintain current distribution.")

        return suggestions

    def generate_test_plan(
        self,
        feature_description: str,
        acceptance_criteria: list[str],
    ) -> str:
        """
        Generate a test plan document before writing any code.

        This is the "Red" planning phase -- define what needs testing.
        """
        return f"""# Test Plan: {feature_description}

## Acceptance Criteria -> Tests Mapping

| Criterion | Test Level | Test Name | Mock Strategy |
|-----------|------------|-----------|---------------|
{chr(10).join(f"| {c[:50]}... | Unit | test_{self._slugify(c[:30])} | TBD |" for c in acceptance_criteria)}

## Test Pyramid Target
- Unit: 80% ({len(acceptance_criteria) * 4} tests estimated)
- Integration: 15% ({max(1, len(acceptance_criteria) // 2)} tests estimated)
- E2E: 5% ({max(1, len(acceptance_criteria) // 5)} tests estimated)

## Mock Boundaries
- [ ] Database -> mock repository
- [ ] External API -> mock client
- [ ] File system -> tmp_path fixture
- [ ] Random/Time -> freeze_time, seeded random

## Fixtures Needed
- [ ] Setup common test data
- [ ] Teardown cleanup

## Beyonce Rule Checklist
- [ ] Every public function has >=1 test
- [ ] Every acceptance criterion has >=1 test
- [ ] Every error path has >=1 test
- [ ] Every edge case is documented (even if not tested)
"""

    # =================================================================
    # Internal Methods
    # =================================================================

    def _build_red_prompt(
        self,
        feature_description: str,
        acceptance_criteria: list[str],
        existing_code: str,
        target_level: TestLevel,
    ) -> str:
        """Build prompt for Red phase test generation."""
        level_guidance = {
            TestLevel.UNIT: "No I/O, no external dependencies, <100ms",
            TestLevel.INTEGRATION: "Real DB/API calls, <5s, test boundaries",
            TestLevel.E2E: "Full stack, browser automation, <30s",
        }

        return f"""Generate a FAILING test for this feature (Red phase of TDD).

## Feature
{feature_description}

## Acceptance Criteria
{chr(10).join(f"- {c}" for c in acceptance_criteria)}

## Test Level
{target_level.label.upper()} -- {target_level.description}
Guidance: {level_guidance[target_level]}

## Existing Code Context
```python
{existing_code[:2000] if existing_code else "# No existing code"}
```

## Rules (DAMP over DRY)
1. Test name should be a complete sentence: test_{what}_{expected}
2. Arrange-Act-Assert structure with comments
3. ONE assertion per test (if possible)
4. Descriptive variable names, not `x`, `y`, `z`
5. Setup code inline, not in fixtures (for readability)
6. This test MUST fail -- implementation doesn't exist yet

## Output
Return ONLY the test code. No explanation.
"""

    def _extract_code(self, response: str) -> str:
        """Extract code block from LLM response."""
        import re

        # Try markdown code block
        match = re.search(r"```python\s*(.*?)\s*```", response, re.DOTALL)
        if match:
            return match.group(1).strip()

        # Try plain code block
        match = re.search(r"```\s*(.*?)\s*```", response, re.DOTALL)
        if match:
            return match.group(1).strip()

        # Return whole response if no code blocks
        return response.strip()

    def _extract_multiple_tests(self, response: str) -> list[str]:
        """Extract multiple test functions from response."""
        import re

        # Split on def test_ markers
        tests = re.split(r"(?=def test_)", response)
        return [t.strip() for t in tests if t.strip().startswith("def test_")]

    def _slugify(self, text: str) -> str:
        """Convert text to valid Python function name."""
        slug = re.sub(r"[^\w\s-]", "", text.lower())
        slug = re.sub(r"[-\s]+", "_", slug)
        return slug[:50].strip("_")


class PyramidViolationError(Exception):
    """Raised when test pyramid distribution violates targets."""
    pass
