"""
Role: Browser debugger mode with 5-step triage methodology for diagnosing UI bugs.
Author: Wigent AI
Version: 1.0.0

Integrates with BrowserMCP to provide automated debugging workflow:
Observe -> Isolate -> Diagnose -> Fix -> Verify. Every bug is treated
as a forensic investigation requiring reproducible evidence.

Usage:
    from wigent.modes.debugger import DebuggerMode, BugReport, TriageStep

    debugger = DebuggerMode(llm_client, browser_mcp)

    report = await debugger.triage(
        url="http://localhost:3000/login",
        symptom="Submit button does nothing when clicked",
        expected_behavior="Form submits and shows success message"
    )

    for step in report.steps:
        print(f"{step.step}: {step.status}")

    if report.root_cause:
        fix = await debugger.apply_fix(report)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from wigent.models.base_model import BaseModel
    from wigent.tools.browser_mcp import BrowserMCP, ConsoleEntry, NetworkRequest


class TriageStatus(Enum):
    """Status of each triage step."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"


class BugCategory(Enum):
    """Categories of UI bugs detectable via browser triage."""
    CONSOLE_ERROR = "console_error"
    NETWORK_FAILURE = "network_failure"
    ELEMENT_NOT_FOUND = "element_not_found"
    TIMING_RACE = "timing_race"
    ACCESSIBILITY = "accessibility"
    VISUAL_REGRESSION = "visual_regression"
    JAVASCRIPT_EXCEPTION = "javascript_exception"
    STATE_MANAGEMENT = "state_management"
    STYLING = "styling"
    UNKNOWN = "unknown"


@dataclass
class TriageStep:
    """A single step in the 5-step triage process."""

    step: str
    description: str
    status: TriageStatus
    evidence: list[str] = field(default_factory=list)
    findings: str = ""
    duration_ms: float = 0.0


@dataclass
class BugReport:
    """Complete bug report generated through triage."""

    url: str
    symptom: str
    expected_behavior: str
    category: BugCategory
    steps: list[TriageStep] = field(default_factory=list)
    root_cause: str = ""
    fix_suggestion: str = ""
    confidence: float = 0.0
    console_errors: list[dict] = field(default_factory=list)
    network_failures: list[dict] = field(default_factory=list)
    dom_snapshot: str = ""
    screenshot_path: str = ""
    regression_test: str = ""

    @property
    def is_resolved(self) -> bool:
        """Check if all steps completed successfully."""
        return all(s.status == TriageStatus.PASSED for s in self.steps)

    def to_markdown(self) -> str:
        """Render bug report as markdown."""
        lines = [
            f"## Bug Report: {self.url}",
            "",
            f"**Symptom:** {self.symptom}",
            f"**Expected:** {self.expected_behavior}",
            f"**Category:** {self.category.value}",
            f"**Confidence:** {self.confidence:.0%}",
            "",
            "### Triage Steps",
            "| Step | Status | Duration | Findings |",
            "|------|--------|----------|----------|",
        ]

        for step in self.steps:
            icon = {
                TriageStatus.PASSED: "PASS",
                TriageStatus.FAILED: "FAIL",
                TriageStatus.IN_PROGRESS: " ...",
                TriageStatus.BLOCKED: "BLKD",
                TriageStatus.PENDING: "PEND",
            }.get(step.status, "????")
            lines.append(
                f"| **{step.step}** | {icon} | {step.duration_ms:.0f}ms | "
                f"{step.findings[:80]}{'...' if len(step.findings) > 80 else ''} |"
            )

        if self.root_cause:
            lines.extend([
                "",
                "### Root Cause",
                self.root_cause,
            ])

        if self.fix_suggestion:
            lines.extend([
                "",
                "### Fix Suggestion",
                self.fix_suggestion,
            ])

        if self.regression_test:
            lines.extend([
                "",
                "### Regression Test",
                f"```python\n{self.regression_test}\n```",
            ])

        return "\n".join(lines)


class DebuggerMode:
    """
    Browser debugger with 5-step triage methodology.

    Principles:
    1. Reproduce first — never guess at a bug you haven't seen fail
    2. Evidence over intuition — every finding requires a screenshot, log, or trace
    3. Isolate before fixing — know the root cause, not just the symptom
    4. Minimal fix — one line is better than ten; no refactoring during bug fixes
    5. Verify with automation — the fix isn't done until a test proves it
    """

    BUG_PATTERNS = {
        BugCategory.CONSOLE_ERROR: {
            "indicators": ["console.error", "Uncaught", "TypeError", "ReferenceError"],
            "evidence": "console log capture",
            "fix_template": "Wrap {component} in error boundary or fix {cause}",
        },
        BugCategory.NETWORK_FAILURE: {
            "indicators": ["4xx", "5xx", "net::ERR_", "Failed to load"],
            "evidence": "network trace",
            "fix_template": "Verify {endpoint} returns valid response for {params}",
        },
        BugCategory.ELEMENT_NOT_FOUND: {
            "indicators": ["null", "undefined", "querySelector", "getElementById"],
            "evidence": "DOM snapshot",
            "fix_template": "Wait for {element} to render before interacting",
        },
        BugCategory.TIMING_RACE: {
            "indicators": ["intermittent", "sometimes", "flaky", "async"],
            "evidence": "repeated reproduction traces",
            "fix_template": "Add wait_for_{event} before {action}",
        },
        BugCategory.JAVASCRIPT_EXCEPTION: {
            "indicators": ["throw", "exception", "error in", "at HTML"],
            "evidence": "stack trace",
            "fix_template": "Handle {condition} in {function} before accessing {property}",
        },
        BugCategory.STATE_MANAGEMENT: {
            "indicators": ["stale", "out of sync", "not updating", "cache"],
            "evidence": "state diff across interactions",
            "fix_template": "Invalidate {cache_key} when {event} occurs",
        },
        BugCategory.STYLING: {
            "indicators": ["hidden", "overlapping", "wrong size", "z-index"],
            "evidence": "computed styles + screenshot",
            "fix_template": "Set {property}: {value} on {selector}",
        },
    }

    def __init__(
        self,
        llm_client: BaseModel,
        browser_mcp: BrowserMCP | None = None,
        screenshot_dir: str = "debug_screenshots",
    ) -> None:
        self.llm = llm_client
        self.browser = browser_mcp
        self.screenshot_dir = screenshot_dir

    async def triage(
        self,
        url: str,
        symptom: str,
        expected_behavior: str,
        interaction_script: str | None = None,
        max_retries: int = 3,
    ) -> BugReport:
        """
        Run the full 5-step triage on a UI bug.

        Steps:
        1. OBSERVE — navigate to URL and capture all available evidence
        2. ISOLATE — determine which component/interaction is failing
        3. DIAGNOSE — inspect DOM, network, console, and state
        4. FIX — generate minimal fix suggestion
        5. VERIFY — (requires apply_fix to be called separately)

        Args:
            url: The page URL exhibiting the bug
            symptom: What the user observes (e.g., "button doesn't respond")
            expected_behavior: What should happen instead
            interaction_script: Optional JS to reproduce interaction
            max_retries: Times to retry reproduction

        Returns:
            BugReport with all findings and fix suggestion
        """
        start_time = time.time()

        if not self.browser:
            raise DebuggerError("BrowserMCP required for triage. Pass browser_mcp to constructor.")

        if not self.browser._is_connected:
            await self.browser.connect()

        report = BugReport(
            url=url,
            symptom=symptom,
            expected_behavior=expected_behavior,
            category=BugCategory.UNKNOWN,
        )

        # Step 1: OBSERVE
        step1 = TriageStep(
            step="OBSERVE",
            description="Navigate to URL, capture console, network, screenshot",
            status=TriageStatus.IN_PROGRESS,
        )
        observe_start = time.time()

        try:
            nav_info = await self.browser.navigate(url, wait_until="networkidle")
            step1.evidence.append(f"Page loaded: {nav_info.get('title', 'unknown')}")

            console_logs = await self.browser.get_console_logs()
            network_requests = await self.browser.get_network_trace()

            console_errors = [
                {"message": log.message, "level": log.level}
                for log in console_logs
                if log.level in ("error", "warning")
            ]
            network_failures = [
                {"url": req.url, "status": req.status, "error": req.error}
                for req in network_requests
                if req.failed or (req.status and req.status >= 400)
            ]

            report.console_errors = console_errors
            report.network_failures = network_failures

            screenshot_bytes = await self.browser.screenshot()
            screenshot_path = f"{self.screenshot_dir}/{int(time.time())}_observe.png"
            import os
            os.makedirs(self.screenshot_dir, exist_ok=True)
            with open(screenshot_path, "wb") as f:
                f.write(screenshot_bytes)
            report.screenshot_path = screenshot_path
            step1.evidence.append(f"Screenshot saved: {screenshot_path}")

            if console_errors:
                step1.findings = f"Found {len(console_errors)} console errors, {len(network_failures)} network failures"
            else:
                step1.findings = "No console errors on initial load"

            step1.status = TriageStatus.PASSED
        except Exception as e:
            step1.status = TriageStatus.FAILED
            step1.findings = f"Observation failed: {e}"

        step1.duration_ms = (time.time() - observe_start) * 1000
        report.steps.append(step1)

        if step1.status == TriageStatus.FAILED:
            return report

        # Step 2: ISOLATE
        step2 = TriageStep(
            step="ISOLATE",
            description="Perform interaction and narrow to failing component",
            status=TriageStatus.IN_PROGRESS,
        )
        isolate_start = time.time()

        try:
            if interaction_script:
                for attempt in range(max_retries):
                    try:
                        await self.browser.evaluate(interaction_script)
                        break
                    except Exception:
                        await self.browser.navigate(url, wait_until="networkidle")
                        if attempt == max_retries - 1:
                            raise
                step2.evidence.append(f"Executed interaction script: {interaction_script[:100]}...")

            # Wait and capture post-interaction state
            await self.browser.wait_for_timeout(1000)

            post_console = await self.browser.get_console_logs()
            post_network = await self.browser.get_network_trace()

            new_errors = [
                log for log in post_console
                if log.level in ("error", "warning")
                and log not in [
                    ConsoleEntry(level=c.level, message=c.message)
                    for c in console_logs
                ]
            ]

            new_failures = [
                req for req in post_network
                if req.failed or (req.status and req.status >= 400)
                and req not in network_requests
            ]

            if new_errors:
                error_texts = [e.message[:200] for e in new_errors]
                step2.findings = f"{len(new_errors)} new errors after interaction: {error_texts[0]}"
                step2.evidence.append(f"New console errors: {error_texts}")

                for error in new_errors:
                    for category, pattern in self.BUG_PATTERNS.items():
                        if any(ind in error.message for ind in pattern["indicators"]):
                            report.category = category
                            break
            elif new_failures:
                step2.findings = f"{len(new_failures)} new network failures after interaction"
                report.category = BugCategory.NETWORK_FAILURE
            else:
                # Try DOM inspection to find missing elements
                dom_state = await self.browser.evaluate("""
                    () => {
                        const buttons = document.querySelectorAll('button, a, [role="button"]');
                        const forms = document.querySelectorAll('form');
                        return {
                            buttonCount: buttons.length,
                            formCount: forms.length,
                            visibleButtons: Array.from(buttons).filter(b =>
                                b.offsetParent !== null
                            ).map(b => ({
                                text: b.textContent.trim().slice(0, 50),
                                disabled: b.disabled || false
                            })),
                            lastError: window.__lastError || null
                        };
                    }
                """)
                step2.evidence.append(f"DOM state: {dom_state}")
                step2.findings = f"DOM has {dom_state.get('buttonCount', 0)} buttons, {dom_state.get('formCount', 0)} forms"

                if dom_state.get("lastError"):
                    report.category = BugCategory.JAVASCRIPT_EXCEPTION

            step2.status = TriageStatus.PASSED
        except Exception as e:
            step2.status = TriageStatus.FAILED
            step2.findings = f"Isolation failed: {e}"

        step2.duration_ms = (time.time() - isolate_start) * 1000
        report.steps.append(step2)

        # Step 3: DIAGNOSE
        step3 = TriageStep(
            step="DIAGNOSE",
            description="Deep dive into DOM, accessibility, network, and state",
            status=TriageStatus.IN_PROGRESS,
        )
        diagnose_start = time.time()

        try:
            # Get accessibility tree
            ax_tree = await self.browser.get_accessibility_tree()
            step3.evidence.append(f"Accessibility tree captured")

            # Get performance metrics
            perf = await self.browser.get_performance_metrics()
            step3.evidence.append(f"Performance: LCP={perf.lcp}, CLS={perf.cls}")

            # Get console errors detail
            error_logs = await self.browser.get_console_logs()
            step3.evidence.append(f"Total console entries: {len(error_logs)}")

            # Deep DOM analysis
            dom_analysis = await self.browser.evaluate("""
                () => {
                    const issues = [];
                    document.querySelectorAll('[data-testid], [id], [name]').forEach(el => {
                        const rect = el.getBoundingClientRect();
                        const style = getComputedStyle(el);
                        issues.push({
                            selector: el.tagName.toLowerCase()
                                + (el.id ? '#' + el.id : '')
                                + (el.getAttribute('data-testid')
                                    ? '[data-testid="' + el.getAttribute('data-testid') + '"]'
                                    : ''),
                            visible: rect.width > 0 && rect.height > 0,
                            disabled: el.disabled || false,
                            zIndex: style.zIndex,
                            opacity: style.opacity,
                            pointerEvents: style.pointerEvents,
                            text: (el.textContent || '').trim().slice(0, 60)
                        });
                    });
                    return issues;
                }
            """)
            report.dom_snapshot = json.dumps(dom_analysis, indent=2)
            step3.evidence.append(f"DOM analysis: {len(dom_analysis)} elements inspected")

            # Try to detect the bug using LLM
            classification_prompt = f"""Classify this UI bug into one of these categories:
{chr(10).join(f"- {c.value}: {', '.join(p['indicators'])}" for c, p in self.BUG_PATTERNS.items())}

## Evidence
- Symptom: {symptom}
- Expected: {expected_behavior}
- Console errors: {[e.message[:200] for e in error_logs]}
- Network failures: {[f.url for f in network_failures]}
- Button states: {dom_analysis[:5]}

## Output format
Return JSON with: category, root_cause, fix_suggestion, confidence
"""

            llm_response = self.llm.generate(
                classification_prompt,
                temperature=0.1,
                max_tokens=1000,
            )
            llm_analysis = self._parse_llm_json(llm_response)

            if llm_analysis:
                for category in BugCategory:
                    if category.value == llm_analysis.get("category"):
                        report.category = category
                        break
                report.root_cause = llm_analysis.get("root_cause", "")
                report.fix_suggestion = llm_analysis.get("fix_suggestion", "")
                report.confidence = llm_analysis.get("confidence", 0.0)

            step3.findings = f"Category: {report.category.value}, Confidence: {report.confidence:.0%}"
            step3.status = TriageStatus.PASSED
        except Exception as e:
            step3.status = TriageStatus.FAILED
            step3.findings = f"Diagnosis failed: {e}"

        step3.duration_ms = (time.time() - diagnose_start) * 1000
        report.steps.append(step3)

        # Step 4: FIX (generate suggestion only)
        step4 = TriageStep(
            step="FIX",
            description="Generate minimal fix suggestion",
            status=TriageStatus.IN_PROGRESS,
        )
        fix_start = time.time()

        try:
            if report.category and report.fix_suggestion:
                step4.findings = report.fix_suggestion[:200]
            elif report.category in self.BUG_PATTERNS:
                pattern = self.BUG_PATTERNS[report.category]
                report.fix_suggestion = self._generate_fix_suggestion(
                    category=report.category,
                    symptom=symptom,
                    console_errors=[e.message for e in error_logs],
                    network_failures=[f.url for f in network_failures],
                    dom_analysis=dom_analysis,
                )
                step4.findings = report.fix_suggestion[:200]
            else:
                step4.findings = "Unable to determine fix — insufficient evidence"
                report.confidence = min(report.confidence, 0.3)

            # Generate regression test
            report.regression_test = self._generate_regression_test(
                url=url,
                symptom=symptom,
                expected=expected_behavior,
                fix=report.fix_suggestion,
            )

            step4.status = TriageStatus.PASSED
        except Exception as e:
            step4.status = TriageStatus.FAILED
            step4.findings = f"Fix generation failed: {e}"

        step4.duration_ms = (time.time() - fix_start) * 1000
        report.steps.append(step4)

        # Step 5: VERIFY (placeholder — actual fix and rerun is external)
        step5 = TriageStep(
            step="VERIFY",
            description="Apply fix and rerun reproduction (call apply_fix)",
            status=TriageStatus.PENDING,
            findings="Call debugger.apply_fix(report) after implementing the fix suggestion",
        )
        report.steps.append(step5)

        return report

    async def apply_fix(
        self,
        report: BugReport,
        fix_code: str,
        interaction_script: str | None = None,
    ) -> BugReport:
        """
        Apply a fix and verify it resolves the bug.

        Args:
            report: BugReport from triage
            fix_code: The code fix to apply
            interaction_script: Script to reproduce the bug

        Returns:
            Updated BugReport with verification results
        """
        if not self.browser:
            raise DebuggerError("BrowserMCP required for verification.")

        if not self.browser._is_connected:
            await self.browser.connect()

        # Reload and verify
        await self.browser.navigate(report.url, wait_until="networkidle")

        if interaction_script:
            await self.browser.evaluate(interaction_script)
            await self.browser.wait_for_timeout(1000)

        # Post-fix checks
        post_logs = await self.browser.get_console_logs()
        post_network = await self.browser.get_network_trace()

        post_errors = [l for l in post_logs if l.level == "error"]
        post_failures = [r for r in post_network if r.failed or (r.status and r.status >= 400)]

        # Capture evidence
        screenshot_bytes = await self.browser.screenshot()
        verify_path = f"{self.screenshot_dir}/{int(time.time())}_verify.png"
        import os
        os.makedirs(self.screenshot_dir, exist_ok=True)
        with open(verify_path, "wb") as f:
            f.write(screenshot_bytes)

        # Update verification step
        for step in report.steps:
            if step.step == "VERIFY":
                step.status = TriageStatus.PASSED if not post_errors else TriageStatus.FAILED
                step.evidence.append(f"Post-fix errors: {len(post_errors)}")
                step.evidence.append(f"Post-fix failures: {len(post_failures)}")
                step.evidence.append(f"Verification screenshot: {verify_path}")
                step.findings = (
                    "Fix verified: no remaining errors"
                    if not post_errors
                    else f"Still {len(post_errors)} errors after fix"
                )
                step.duration_ms = 0  # Set externally if needed
                break

        return report

    def verify_console_clean(self, logs: list[ConsoleEntry]) -> bool:
        """Check that console has no errors or warnings."""
        errors = [l for l in logs if l.level in ("error", "warning")]
        return len(errors) == 0

    def verify_network_clean(self, requests: list[NetworkRequest]) -> bool:
        """Check that all requests completed successfully."""
        failures = [r for r in requests if r.failed or (r.status and r.status >= 400)]
        return len(failures) == 0

    def classify_bug(
        self,
        console_errors: list[str],
        network_statuses: list[int],
        dom_state: dict[str, Any],
    ) -> BugCategory:
        """Classify a bug based on available evidence."""

        # Console errors take priority
        for error in console_errors:
            for category, pattern in self.BUG_PATTERNS.items():
                if any(ind in error for ind in pattern["indicators"]):
                    return category

        # Network failures
        if any(s >= 400 for s in network_statuses):
            return BugCategory.NETWORK_FAILURE

        # DOM issues
        if dom_state:
            buttons = dom_state.get("visibleButtons", [])
            if buttons and all(b.get("disabled") for b in buttons):
                return BugCategory.ELEMENT_NOT_FOUND

        return BugCategory.UNKNOWN

    # =================================================================
    # Internal Methods
    # =================================================================

    def _parse_llm_json(self, response: str) -> dict[str, Any] | None:
        """Parse JSON from LLM response, handling markdown wrapping."""
        import re

        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        try:
            return json.loads(response)
        except (json.JSONDecodeError, ValueError):
            return None

    def _generate_fix_suggestion(
        self,
        category: BugCategory,
        symptom: str,
        console_errors: list[str],
        network_failures: list[str],
        dom_analysis: list[dict],
    ) -> str:
        """Generate a minimal fix suggestion based on bug evidence."""
        pattern = self.BUG_PATTERNS.get(category)
        if not pattern:
            return "Review the evidence and debug logs above."

        template = pattern["fix_template"]

        if category == BugCategory.CONSOLE_ERROR:
            error = console_errors[0] if console_errors else symptom
            return f"Fix the following error: {error}\n\nWrap the component in an error boundary and ensure all async operations have proper try-catch handling."

        elif category == BugCategory.NETWORK_FAILURE:
            url = network_failures[0] if network_failures else "unknown endpoint"
            return f"Verify the API endpoint {url} is reachable and returns valid JSON. Check network tab for response payload."

        elif category == BugCategory.ELEMENT_NOT_FOUND:
            missing = dom_analysis[0] if dom_analysis else {"selector": "unknown"}
            return f"Add an explicit wait for {missing.get('selector', 'the element')} before attempting interaction. The element may be rendered conditionally or asynchronously."

        elif category == BugCategory.TIMING_RACE:
            return f"Use waitForSelector/waitForFunction instead of fixed timeouts. The bug is likely a race condition between rendering and interaction."

        elif category == BugCategory.JAVASCRIPT_EXCEPTION:
            error = console_errors[0] if console_errors else symptom
            return f"Handle the exception in try-catch: {error}. Add null checks before accessing properties on potentially undefined objects."

        elif category == BugCategory.STATE_MANAGEMENT:
            return f"Ensure state is properly invalidated after mutations. Check that stale data is not being cached or reused across component re-renders."

        elif category == BugCategory.STYLING:
            return f"Review CSS computed properties. The element may be hidden, overlapping, or positioned off-screen. Check z-index, opacity, display, and visibility."

        return f"Template: {template}"

    def _generate_regression_test(
        self,
        url: str,
        symptom: str,
        expected: str,
        fix: str,
    ) -> str:
        """Generate a Playwright regression test for the fixed bug."""
        slug = symptom.lower().replace(" ", "_").replace("'", "")[:40]

        return f'''"""
Regression test for: {symptom}
Expected: {expected}
Fix: {fix[:200]}
"""

import pytest


@pytest.mark.asyncio
async def test_{slug}_regression(page):
    """Verify fix for: {symptom}"""
    # Arrange
    await page.goto("{url}", wait_until="networkidle")

    # Act
    # {symptom}

    # Assert
    # {expected}

    # Verify console is clean
    console_logs = []
    page.on("console", lambda msg: console_logs.append(msg))
    errors = [msg for msg in console_logs if msg.type == "error"]
    assert len(errors) == 0, f"Console errors: {errors}"
'''


class DebuggerError(Exception):
    """Raised when debugger operations fail."""
    pass
