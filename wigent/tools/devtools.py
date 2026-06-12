"""
DevTools Utilities -- High-Level Browser Verification Primitives

Provides agent-friendly abstractions over BrowserMCP for common
verification workflows: form testing, navigation flows, responsive
checks, and accessibility audits.

These are the tools the agent calls directly during Verify phase.
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from wigent.tools.browser_mcp import (
    BrowserMCP,
    BrowserSnapshot,
    ConsoleEntry,
    NetworkRequest,
    PerformanceMetrics,
)


class Severity(Enum):
    PASS = "pass"
    WARNING = "warning"
    ERROR = "error"
    INFO = "info"


@dataclass
class AuditResult:
    """Single audit check result."""
    rule: str
    severity: Severity
    message: str
    element: Optional[str] = None
    line_number: Optional[int] = None
    fix_suggestion: Optional[str] = None
    wcag_reference: Optional[str] = None


@dataclass
class AuditReport:
    """Complete audit of a page or flow."""
    url: str
    timestamp: float
    summary: dict[str, int] = field(default_factory=dict)
    results: list[AuditResult] = field(default_factory=list)
    snapshot: Optional[BrowserSnapshot] = None
    performance: Optional[PerformanceMetrics] = None

    @property
    def passed(self) -> bool:
        return not any(r.severity == Severity.ERROR for r in self.results)

    @property
    def error_count(self) -> int:
        return sum(1 for r in self.results if r.severity == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for r in self.results if r.severity == Severity.WARNING)


class DevTools:
    """
    High-level DevTools interface for agent verification workflows.

    Wraps BrowserMCP with domain-specific operations that map
    directly to agent skills: "test this form", "check responsive",
    "audit accessibility", etc.
    """

    def __init__(self, browser: BrowserMCP):
        self.browser = browser
        self._flow_history: list[BrowserSnapshot] = []

    # ─────────────────────────────────────────────────────────────
    # FORM TESTING
    # ─────────────────────────────────────────────────────────────

    async def test_form(
        self,
        url: str,
        fields: dict[str, str],
        submit_selector: str = "button[type=submit]",
        expected_result: Optional[Callable[[BrowserSnapshot], bool]] = None,
    ) -> AuditReport:
        """
        Fill and submit a form, verify outcome.

        Args:
            url: Page containing the form
            fields: {css_selector: value_to_fill}
            submit_selector: Button to click to submit
            expected_result: Optional predicate on post-submit snapshot
        """
        report = AuditReport(url=url, timestamp=0)

        # Navigate to form
        await self.browser.navigate(url)

        # Fill each field
        for selector, value in fields.items():
            exists = await self.browser.verify_element_exists(selector)
            if not exists:
                report.results.append(AuditResult(
                    rule="form_field_exists",
                    severity=Severity.ERROR,
                    message=f"Form field not found: {selector}",
                    element=selector,
                ))
                return report

            await self.browser.fill_input(selector, value)
            report.results.append(AuditResult(
                rule="form_field_fill",
                severity=Severity.PASS,
                message=f"Filled {selector}",
                element=selector,
            ))

        # Submit
        submit_exists = await self.browser.verify_element_exists(submit_selector)
        if not submit_exists:
            report.results.append(AuditResult(
                rule="submit_button_exists",
                severity=Severity.ERROR,
                message=f"Submit button not found: {submit_selector}",
                element=submit_selector,
            ))
            return report

        await self.browser.click_element(submit_selector)

        # Wait for navigation or DOM update
        await self._wait_for_stable_state()

        # Verify result
        snapshot = await self.browser.capture_snapshot()
        self._flow_history.append(snapshot)

        if expected_result and not expected_result(snapshot):
            report.results.append(AuditResult(
                rule="form_submit_result",
                severity=Severity.ERROR,
                message="Form submission did not produce expected result",
            ))
        else:
            report.results.append(AuditResult(
                rule="form_submit_result",
                severity=Severity.PASS,
                message="Form submitted successfully",
            ))

        # Check for console errors during form interaction
        has_errors, errors = await self.browser.verify_no_console_errors()
        if not has_errors:
            for err in errors:
                report.results.append(AuditResult(
                    rule="console_error",
                    severity=Severity.WARNING,
                    message=f"Console error during form test: {err.message}",
                ))

        report.snapshot = snapshot
        report.timestamp = snapshot.timestamp
        report.summary = self._compute_summary(report.results)

        return report

    # ─────────────────────────────────────────────────────────────
    # NAVIGATION FLOW TESTING
    # ─────────────────────────────────────────────────────────────

    async def test_navigation_flow(
        self,
        steps: list[dict[str, Any]],
    ) -> list[AuditReport]:
        """
        Test a multi-step user flow (e.g., login -> dashboard -> settings).

        Each step: {"action": "navigate|click|fill|assert", ...}

        Returns one AuditReport per step.
        """
        reports = []

        for i, step in enumerate(steps):
            action = step.get("action")
            report = AuditReport(url="", timestamp=0)

            if action == "navigate":
                url = step["url"]
                await self.browser.navigate(url)
                report.url = url

            elif action == "click":
                selector = step["selector"]
                exists = await self.browser.verify_element_exists(selector)
                if not exists:
                    report.results.append(AuditResult(
                        rule="element_exists",
                        severity=Severity.ERROR,
                        message=f"Click target not found: {selector}",
                        element=selector,
                    ))
                else:
                    await self.browser.click_element(selector)
                    report.results.append(AuditResult(
                        rule="element_click",
                        severity=Severity.PASS,
                        message=f"Clicked {selector}",
                        element=selector,
                    ))

            elif action == "fill":
                selector = step["selector"]
                value = step["value"]
                await self.browser.fill_input(selector, value)
                report.results.append(AuditResult(
                    rule="element_fill",
                    severity=Severity.PASS,
                    message=f"Filled {selector}",
                    element=selector,
                ))

            elif action == "assert":
                assertion_type = step.get("type", "text_present")
                if assertion_type == "text_present":
                    text = step["text"]
                    found = await self.browser.verify_text_present(text)
                    if not found:
                        report.results.append(AuditResult(
                            rule="assert_text_present",
                            severity=Severity.ERROR,
                            message=f"Expected text not found: '{text}'",
                        ))
                    else:
                        report.results.append(AuditResult(
                            rule="assert_text_present",
                            severity=Severity.PASS,
                            message=f"Found text: '{text}'",
                        ))

                elif assertion_type == "element_visible":
                    selector = step["selector"]
                    visible = await self.browser.verify_element_visible(selector)
                    if not visible:
                        report.results.append(AuditResult(
                            rule="assert_element_visible",
                            severity=Severity.ERROR,
                            message=f"Element not visible: {selector}",
                            element=selector,
                        ))
                    else:
                        report.results.append(AuditResult(
                            rule="assert_element_visible",
                            severity=Severity.PASS,
                            message=f"Element visible: {selector}",
                            element=selector,
                        ))

            # Capture snapshot after each step
            snapshot = await self.browser.capture_snapshot()
            self._flow_history.append(snapshot)
            report.snapshot = snapshot
            report.timestamp = snapshot.timestamp
            report.summary = self._compute_summary(report.results)
            reports.append(report)

        return reports

    # ─────────────────────────────────────────────────────────────
    # RESPONSIVE TESTING
    # ─────────────────────────────────────────────────────────────

    async def test_responsive(
        self,
        url: str,
        breakpoints: Optional[list[tuple[int, int]]] = None,
    ) -> list[AuditReport]:
        """
        Test page at multiple viewport sizes.

        Default breakpoints: mobile (375x667), tablet (768x1024),
        desktop (1920x1080).
        """
        default = [
            (375, 667),    # iPhone SE
            (768, 1024),   # iPad
            (1920, 1080),  # Desktop
        ]
        breakpoints = breakpoints or default

        reports = []

        for width, height in breakpoints:
            await self.browser.navigate(url)

            snapshot = await self.browser.capture_snapshot()

            report = AuditReport(url=url, timestamp=snapshot.timestamp)
            report.snapshot = snapshot

            # Check for horizontal scroll (layout overflow)
            has_overflow = await self._check_horizontal_overflow()
            if has_overflow:
                report.results.append(AuditResult(
                    rule="responsive_overflow",
                    severity=Severity.ERROR,
                    message=f"Horizontal overflow at {width}x{height}",
                ))
            else:
                report.results.append(AuditResult(
                    rule="responsive_overflow",
                    severity=Severity.PASS,
                    message=f"No overflow at {width}x{height}",
                ))

            # Check tap target sizes (mobile only)
            if width <= 768:
                small_taps = await self._check_tap_target_sizes()
                if small_taps:
                    report.results.append(AuditResult(
                        rule="responsive_tap_targets",
                        severity=Severity.WARNING,
                        message=f"{len(small_taps)} tap targets < 44x44px",
                    ))

            report.summary = self._compute_summary(report.results)
            reports.append(report)

        return reports

    async def _check_horizontal_overflow(self) -> bool:
        """Check if page has horizontal scrollbar."""
        result = await self.browser._send_command("Runtime.evaluate", {
            "expression": (
                "document.documentElement.scrollWidth > "
                "document.documentElement.clientWidth"
            ),
            "returnByValue": True,
        })
        return result.get("result", {}).get("value", False)

    async def _check_tap_target_sizes(self) -> list[dict]:
        """Find tap targets smaller than 44x44px (WCAG 2.5.5)."""
        result = await self.browser._send_command("Runtime.evaluate", {
            "expression": """
                [...document.querySelectorAll('a, button, input, select, textarea, [onclick]')]
                    .map(el => {
                        const rect = el.getBoundingClientRect();
                        return {
                            tag: el.tagName,
                            width: rect.width,
                            height: rect.height,
                            tooSmall: rect.width < 44 || rect.height < 44
                        };
                    })
                    .filter(item => item.tooSmall)
            """,
            "returnByValue": True,
        })
        return result.get("result", {}).get("value", [])

    # ─────────────────────────────────────────────────────────────
    # ACCESSIBILITY AUDIT
    # ─────────────────────────────────────────────────────────────

    async def audit_accessibility(self, url: str) -> AuditReport:
        """
        Run automated accessibility checks (WCAG 2.1 AA baseline).

        Uses CDP Accessibility domain + custom checks.
        """
        await self.browser.navigate(url)
        snapshot = await self.browser.capture_snapshot()

        report = AuditReport(url=url, timestamp=snapshot.timestamp)
        report.snapshot = snapshot

        # Check 1: Images without alt text
        missing_alt = await self._find_images_without_alt()
        for img in missing_alt:
            report.results.append(AuditResult(
                rule="a11y_image_alt",
                severity=Severity.ERROR,
                message=f"Image missing alt text: {img.get('src', 'unknown')}",
                element=f"img[src='{img.get('src', '')}']",
                wcag_reference="WCAG 1.1.1 (A)",
                fix_suggestion="Add descriptive alt attribute",
            ))

        # Check 2: Form inputs without labels
        unlabeled = await self._find_unlabeled_inputs()
        for inp in unlabeled:
            report.results.append(AuditResult(
                rule="a11y_form_label",
                severity=Severity.ERROR,
                message=f"Input missing label: {inp.get('name', 'unknown')}",
                element=f"input[name='{inp.get('name', '')}']",
                wcag_reference="WCAG 1.3.1 (A), 3.3.2 (A)",
                fix_suggestion="Add associated <label> or aria-label",
            ))

        # Check 3: Color contrast (simplified -- real impl needs computed styles)
        low_contrast = await self._check_color_contrast()
        for elem in low_contrast:
            report.results.append(AuditResult(
                rule="a11y_color_contrast",
                severity=Severity.WARNING,
                message=f"Potential low contrast: {elem}",
                wcag_reference="WCAG 1.4.3 (AA)",
                fix_suggestion="Ensure 4.5:1 contrast ratio for normal text",
            ))

        # Check 4: Missing lang attribute
        has_lang = await self._check_html_lang()
        if not has_lang:
            report.results.append(AuditResult(
                rule="a11y_html_lang",
                severity=Severity.ERROR,
                message="HTML element missing lang attribute",
                wcag_reference="WCAG 3.1.1 (A)",
                fix_suggestion='Add lang="en" (or appropriate language)',
            ))

        # Check 5: Keyboard navigation (focusable elements)
        focusable = await self._check_focusable_elements()
        if not focusable:
            report.results.append(AuditResult(
                rule="a11y_focusable",
                severity=Severity.WARNING,
                message="No focusable elements detected -- verify keyboard navigation",
                wcag_reference="WCAG 2.1.1 (A)",
            ))

        # Check 6: Skip link
        has_skip_link = await self._check_skip_link()
        if not has_skip_link:
            report.results.append(AuditResult(
                rule="a11y_skip_link",
                severity=Severity.INFO,
                message="No skip navigation link detected",
                wcag_reference="WCAG 2.4.1 (A)",
                fix_suggestion="Add 'Skip to main content' link as first focusable element",
            ))

        report.summary = self._compute_summary(report.results)
        return report

    async def _find_images_without_alt(self) -> list[dict]:
        """Find all img elements missing alt attribute."""
        result = await self.browser._send_command("Runtime.evaluate", {
            "expression": """
                [...document.querySelectorAll('img:not([alt])')]
                    .map(img => ({src: img.src, width: img.width, height: img.height}))
            """,
            "returnByValue": True,
        })
        return result.get("result", {}).get("value", [])

    async def _find_unlabeled_inputs(self) -> list[dict]:
        """Find inputs not associated with a label."""
        result = await self.browser._send_command("Runtime.evaluate", {
            "expression": """
                [...document.querySelectorAll('input, select, textarea')]
                    .filter(el => {
                        const id = el.id;
                        const aria = el.getAttribute('aria-label') || el.getAttribute('aria-labelledby');
                        const placeholder = el.placeholder;
                        const hasLabel = id && document.querySelector(`label[for="${id}"]`);
                        return !hasLabel && !aria && !placeholder;
                    })
                    .map(el => ({tag: el.tagName, name: el.name, type: el.type}))
            """,
            "returnByValue": True,
        })
        return result.get("result", {}).get("value", [])

    async def _check_color_contrast(self) -> list[str]:
        """Simplified contrast check -- real impl needs getComputedStyle."""
        result = await self.browser._send_command("Runtime.evaluate", {
            "expression": """
                const issues = [];
                const elements = document.querySelectorAll('p, span, a, button, h1, h2, h3, h4, h5, h6');
                for (const el of elements) {
                    const style = window.getComputedStyle(el);
                    const color = style.color;
                    const bg = style.backgroundColor;
                    if (color.includes('rgb(200') && bg.includes('255')) {
                        issues.push(el.tagName + (el.className ? '.' + el.className : ''));
                    }
                }
                issues.slice(0, 10);
            """,
            "returnByValue": True,
        })
        return result.get("result", {}).get("value", [])

    async def _check_html_lang(self) -> bool:
        """Check if html element has lang attribute."""
        result = await self.browser._send_command("Runtime.evaluate", {
            "expression": "document.documentElement.hasAttribute('lang')",
            "returnByValue": True,
        })
        return result.get("result", {}).get("value", False)

    async def _check_focusable_elements(self) -> bool:
        """Check if page has keyboard-focusable elements."""
        result = await self.browser._send_command("Runtime.evaluate", {
            "expression": """
                document.querySelectorAll('a, button, input, select, textarea, [tabindex]:not([tabindex="-1"])')
                    .length > 0
            """,
            "returnByValue": True,
        })
        return result.get("result", {}).get("value", False)

    async def _check_skip_link(self) -> bool:
        """Check for skip navigation link."""
        result = await self.browser._send_command("Runtime.evaluate", {
            "expression": """
                [...document.querySelectorAll('a')]
                    .some(a => a.textContent.toLowerCase().includes('skip'))
            """,
            "returnByValue": True,
        })
        return result.get("result", {}).get("value", False)

    # ─────────────────────────────────────────────────────────────
    # PERFORMANCE AUDIT
    # ─────────────────────────────────────────────────────────────

    async def audit_performance(
        self,
        url: str,
        budgets: Optional[dict[str, float]] = None,
    ) -> AuditReport:
        """
        Audit page against performance budgets.

        Default budgets (mobile 3G):
        - LCP: 2500ms
        - FID: 100ms
        - CLS: 0.1
        - TTFB: 600ms
        """
        default_budgets = {
            "lcp": 2500,
            "fid": 100,
            "cls": 0.1,
            "ttfb": 600,
        }
        budgets = {**default_budgets, **(budgets or {})}

        await self.browser.navigate(url)

        # Wait a moment for metrics to stabilize
        import asyncio
        await asyncio.sleep(2)

        perf = await self.browser.capture_performance_metrics()
        snapshot = await self.browser.capture_snapshot()

        report = AuditReport(url=url, timestamp=snapshot.timestamp)
        report.performance = perf
        report.snapshot = snapshot

        # Check each budget
        if perf.lcp and perf.lcp > budgets["lcp"]:
            report.results.append(AuditResult(
                rule="perf_lcp",
                severity=Severity.ERROR,
                message=f"LCP {perf.lcp:.0f}ms exceeds budget {budgets['lcp']:.0f}ms",
                fix_suggestion="Optimize largest content element, use preload hints",
            ))
        elif perf.lcp:
            report.results.append(AuditResult(
                rule="perf_lcp",
                severity=Severity.PASS,
                message=f"LCP {perf.lcp:.0f}ms within budget",
            ))

        if perf.fid and perf.fid > budgets["fid"]:
            report.results.append(AuditResult(
                rule="perf_fid",
                severity=Severity.ERROR,
                message=f"FID {perf.fid:.0f}ms exceeds budget {budgets['fid']:.0f}ms",
                fix_suggestion="Reduce main-thread JavaScript execution",
            ))
        elif perf.fid:
            report.results.append(AuditResult(
                rule="perf_fid",
                severity=Severity.PASS,
                message=f"FID {perf.fid:.0f}ms within budget",
            ))

        if perf.cls and perf.cls > budgets["cls"]:
            report.results.append(AuditResult(
                rule="perf_cls",
                severity=Severity.ERROR,
                message=f"CLS {perf.cls:.3f} exceeds budget {budgets['cls']}",
                fix_suggestion="Set explicit dimensions on images, avoid inserting content above existing",
            ))
        elif perf.cls is not None:
            report.results.append(AuditResult(
                rule="perf_cls",
                severity=Severity.PASS,
                message=f"CLS {perf.cls:.3f} within budget",
            ))

        if perf.ttfb and perf.ttfb > budgets["ttfb"]:
            report.results.append(AuditResult(
                rule="perf_ttfb",
                severity=Severity.WARNING,
                message=f"TTFB {perf.ttfb:.0f}ms exceeds budget {budgets['ttfb']:.0f}ms",
                fix_suggestion="Optimize server response time, use CDN",
            ))
        elif perf.ttfb:
            report.results.append(AuditResult(
                rule="perf_ttfb",
                severity=Severity.PASS,
                message=f"TTFB {perf.ttfb:.0f}ms within budget",
            ))

        # JS heap check
        if perf.js_heap_used and perf.js_heap_total:
            usage_ratio = perf.js_heap_used / perf.js_heap_total
            if usage_ratio > 0.8:
                report.results.append(AuditResult(
                    rule="perf_heap",
                    severity=Severity.WARNING,
                    message=f"JS heap {usage_ratio*100:.0f}% full -- potential memory leak",
                    fix_suggestion="Review event listeners, closures, and detached DOM nodes",
                ))

        report.summary = self._compute_summary(report.results)
        return report

    # ─────────────────────────────────────────────────────────────
    # SECURITY AUDIT
    # ─────────────────────────────────────────────────────────────

    async def audit_security(self, url: str) -> AuditReport:
        """Check basic security headers and practices."""
        await self.browser.navigate(url)
        snapshot = await self.browser.capture_snapshot()

        report = AuditReport(url=url, timestamp=snapshot.timestamp)
        report.snapshot = snapshot

        # Check for HTTPS
        if not url.startswith("https://") and not url.startswith("http://localhost"):
            report.results.append(AuditResult(
                rule="sec_https",
                severity=Severity.ERROR,
                message="Site not served over HTTPS",
                fix_suggestion="Enable TLS/SSL on all production endpoints",
            ))

        # Check for mixed content
        mixed = await self._check_mixed_content()
        if mixed:
            report.results.append(AuditResult(
                rule="sec_mixed_content",
                severity=Severity.ERROR,
                message=f"{len(mixed)} mixed content resources detected",
                fix_suggestion="Load all resources over HTTPS",
            ))

        # Check for inline scripts (CSP bypass risk)
        inline_scripts = await self._check_inline_scripts()
        if inline_scripts:
            report.results.append(AuditResult(
                rule="sec_inline_scripts",
                severity=Severity.WARNING,
                message=f"{len(inline_scripts)} inline scripts detected",
                fix_suggestion="Move scripts to external files, implement strict CSP",
            ))

        # Check for exposed secrets in DOM
        secrets = await self._check_exposed_secrets()
        for secret in secrets:
            report.results.append(AuditResult(
                rule="sec_exposed_secret",
                severity=Severity.ERROR,
                message=f"Potential secret exposed in DOM: {secret['type']}",
                fix_suggestion="Never render secrets in HTML -- use secure API endpoints",
            ))

        report.summary = self._compute_summary(report.results)
        return report

    async def _check_mixed_content(self) -> list[str]:
        """Find HTTP resources on HTTPS page."""
        result = await self.browser._send_command("Runtime.evaluate", {
            "expression": """
                [...document.querySelectorAll('script, link, img, iframe, audio, video')]
                    .map(el => el.src || el.href)
                    .filter(url => url && url.startsWith('http:'))
            """,
            "returnByValue": True,
        })
        return result.get("result", {}).get("value", [])

    async def _check_inline_scripts(self) -> list[dict]:
        """Find inline script tags."""
        result = await self.browser._send_command("Runtime.evaluate", {
            "expression": """
                [...document.querySelectorAll('script:not([src])')]
                    .map(el => ({content: el.textContent.slice(0, 100)}))
            """,
            "returnByValue": True,
        })
        return result.get("result", {}).get("value", [])

    async def _check_exposed_secrets(self) -> list[dict]:
        """Scan DOM for patterns that look like API keys, tokens, etc."""
        result = await self.browser._send_command("Runtime.evaluate", {
            "expression": """
                const html = document.documentElement.innerHTML;
                const patterns = [
                    {type: 'AWS Key', regex: /AKIA[0-9A-Z]{16}/g},
                    {type: 'GitHub Token', regex: /ghp_[a-zA-Z0-9]{36}/g},
                    {type: 'Generic API Key', regex: /api[_-]?key['\\s]*[:=]['\\s]*['"][a-zA-Z0-9]{16,}['"]/gi},
                    {type: 'Private Key', regex: /-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----/g},
                ];
                const found = [];
                for (const p of patterns) {
                    const matches = html.match(p.regex);
                    if (matches) {
                        found.push({type: p.type, count: matches.length});
                    }
                }
                found;
            """,
            "returnByValue": True,
        })
        return result.get("result", {}).get("value", [])

    # ─────────────────────────────────────────────────────────────
    # REPORTING & UTILITIES
    # ─────────────────────────────────────────────────────────────

    def _compute_summary(self, results: list[AuditResult]) -> dict[str, int]:
        """Count results by severity."""
        summary = {"pass": 0, "warning": 0, "error": 0, "info": 0}
        for r in results:
            summary[r.severity.value] = summary.get(r.severity.value, 0) + 1
        return summary

    async def _wait_for_stable_state(self, timeout: float = 5.0) -> None:
        """Wait for DOM to stabilize (no mutations for 500ms)."""
        import asyncio
        await asyncio.sleep(0.5)

    def get_flow_history(self) -> list[BrowserSnapshot]:
        """Get all snapshots captured during the current session."""
        return list(self._flow_history)

    def export_report(self, report: AuditReport, path: Path) -> None:
        """Save audit report as JSON."""
        data = {
            "url": report.url,
            "timestamp": report.timestamp,
            "summary": report.summary,
            "passed": report.passed,
            "results": [
                {
                    "rule": r.rule,
                    "severity": r.severity.value,
                    "message": r.message,
                    "element": r.element,
                    "fix_suggestion": r.fix_suggestion,
                    "wcag_reference": r.wcag_reference,
                }
                for r in report.results
            ],
        }
        path.write_text(json.dumps(data, indent=2))

    def export_har(self, path: Path) -> None:
        """Export captured network trace as HAR file."""
        har = {
            "log": {
                "version": "1.2",
                "creator": {"name": "Wigent DevTools", "version": "1.0"},
                "entries": [
                    {
                        "startedDateTime": req.request_id,
                        "request": {
                            "method": req.method,
                            "url": req.url,
                            "headers": [{"name": k, "value": v} for k, v in req.request_headers.items()],
                        },
                        "response": {
                            "status": req.status,
                            "statusText": req.status_text,
                            "headers": [{"name": k, "value": v} for k, v in req.response_headers.items()],
                        },
                    }
                    for req in self.browser._network_buffer
                ],
            }
        }
        path.write_text(json.dumps(har, indent=2))
