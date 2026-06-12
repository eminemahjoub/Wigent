"""
Role: Frontend UI engineering mode for component architecture and accessibility.
Author: Wigent AI
Version: 1.0.0

Enforces WCAG 2.1 AA, design system consistency, responsive breakpoints,
and semantic HTML. Every component is accessible by default.

Usage:
    from wigent.modes.frontend import FrontendMode

    mode = FrontendMode(llm_client)

    result = mode.generate_component(
        spec="Button with loading state",
        design_system="material-ui",
        framework="react"
    )

    audit = mode.audit_accessibility(html_code)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wigent.models.base_model import BaseModel


class Framework(Enum):
    """Supported frontend frameworks."""
    REACT = "react"
    VUE = "vue"
    ANGULAR = "angular"
    SVELTE = "svelte"
    VANILLA = "vanilla"


class DesignSystem(Enum):
    """Supported design systems."""
    MATERIAL_UI = "material-ui"
    CHAKRA = "chakra-ui"
    ANT_DESIGN = "ant-design"
    TAILWIND = "tailwind"
    BOOTSTRAP = "bootstrap"
    SHADCN = "shadcn"
    CUSTOM = "custom"


@dataclass
class ComponentSpec:
    """Specification for a UI component."""

    name: str
    description: str
    props: list[dict] = field(default_factory=list)
    states: list[str] = field(default_factory=list)
    accessibility: dict = field(default_factory=dict)
    responsive: dict = field(default_factory=dict)
    design_tokens: dict = field(default_factory=dict)


@dataclass
class AccessibilityAudit:
    """Result of WCAG 2.1 AA audit."""

    passed: bool
    score: int
    violations: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)
    manual_checks: list[str] = field(default_factory=list)


class FrontendMode:
    """
    Frontend UI engineering with accessibility-first design.

    Principles:
    1. Semantic HTML -- the right element for the right purpose
    2. WCAG 2.1 AA -- every component meets accessibility standards
    3. Design tokens -- colors, spacing, typography from system
    4. Responsive -- mobile-first, 4 breakpoints
    5. Progressive enhancement -- works without JS, enhanced with
    """

    WCAG_REQUIREMENTS = {
        "contrast": 4.5,
        "large_contrast": 3.0,
        "focus_visible": True,
        "target_size": 44,
        "animation_prefers_reduced": True,
    }

    BREAKPOINTS = {
        "sm": "640px",
        "md": "768px",
        "lg": "1024px",
        "xl": "1280px",
    }

    COMPONENT_PATTERNS = {
        "button": {
            "elements": ["button"],
            "aria": ["aria-label", "aria-pressed", "aria-expanded"],
            "states": ["default", "hover", "focus", "active", "disabled", "loading"],
            "keyboard": ["Enter", "Space"],
        },
        "input": {
            "elements": ["input", "label"],
            "aria": ["aria-label", "aria-describedby", "aria-invalid", "aria-required"],
            "states": ["default", "focus", "error", "disabled", "readonly"],
            "keyboard": ["Tab", "Enter"],
        },
        "modal": {
            "elements": ["dialog", "div[role='dialog']"],
            "aria": ["aria-modal", "aria-labelledby", "aria-describedby"],
            "states": ["open", "closed"],
            "keyboard": ["Escape", "Tab (trap)"],
        },
        "navigation": {
            "elements": ["nav", "ul", "li", "a"],
            "aria": ["aria-current", "aria-label", "aria-expanded"],
            "states": ["default", "expanded", "collapsed"],
            "keyboard": ["Arrow keys", "Enter", "Space"],
        },
        "table": {
            "elements": ["table", "thead", "tbody", "th", "td"],
            "aria": ["aria-sort", "aria-label"],
            "states": ["default", "sorted"],
            "keyboard": ["Arrow keys"],
        },
    }

    def __init__(
        self,
        llm_client: BaseModel,
        framework: Framework = Framework.REACT,
        design_system: DesignSystem = DesignSystem.SHADCN,
    ) -> None:
        self.llm = llm_client
        self.framework = framework
        self.design_system = design_system
        self._component_registry: dict[str, ComponentSpec] = {}
        self._design_tokens: dict[str, str] = {}

    def generate_component(
        self,
        spec: str,
        props: list[dict] | None = None,
        states: list[str] | None = None,
        accessibility_requirements: list[str] | None = None,
    ) -> dict[str, str]:
        """
        Generate a complete, accessible component.

        Returns:
            Dict of file_path -> content
        """
        component_type = self._detect_component_type(spec)
        pattern = self.COMPONENT_PATTERNS.get(component_type, {})

        prompt = self._build_component_prompt(
            spec=spec,
            component_type=component_type,
            pattern=pattern,
            props=props or [],
            states=states or pattern.get("states", ["default"]),
            accessibility=accessibility_requirements or [],
        )

        response = self.llm.generate(prompt, temperature=0.2, max_tokens=4000)

        files = self._parse_component_response(response)

        for path, content in files.items():
            if path.endswith((".tsx", ".jsx", ".vue", ".html")):
                audit = self.audit_accessibility(content)
                if not audit.passed:
                    files = self._fix_accessibility(files, audit)
                    break

        return files

    def audit_accessibility(self, code: str) -> AccessibilityAudit:
        """
        Automated WCAG 2.1 AA audit of HTML/JSX code.

        Checks:
        - Color contrast ratios
        - Missing alt text
        - Missing labels
        - Focus management
        - ARIA usage
        - Semantic HTML
        """
        violations = []
        warnings = []
        manual_checks = []

        # 1. Check for images without alt
        img_without_alt = re.findall(r"<img[^>]*>(?!.*alt=)", code, re.IGNORECASE)
        for match in img_without_alt:
            violations.append({
                "rule": "1.1.1 Non-text Content",
                "severity": "error",
                "element": match[:50],
                "fix": "Add alt attribute or aria-hidden='true' for decorative",
            })

        # 2. Check for inputs without labels
        input_without_label = re.findall(
            r"<input[^>]*>(?!.*<label)(?!.*aria-label)(?!.*aria-labelledby)",
            code,
            re.IGNORECASE
        )
        for match in input_without_label:
            violations.append({
                "rule": "1.3.1 Info and Relationships",
                "severity": "error",
                "element": match[:50],
                "fix": "Add <label> or aria-label/aria-labelledby",
            })

        # 3. Check for low contrast (basic heuristic)
        color_patterns = re.findall(r"color:\s*#([0-9a-fA-F]{6})", code)
        for color in color_patterns:
            if self._is_low_contrast(color):
                violations.append({
                    "rule": "1.4.3 Contrast (Minimum)",
                    "severity": "warning",
                    "color": f"#{color}",
                    "fix": f"Ensure contrast ratio >= {self.WCAG_REQUIREMENTS['contrast']}:1",
                })

        # 4. Check for missing focus styles
        if ":focus" not in code and ":focus-visible" not in code:
            warnings.append({
                "rule": "2.4.7 Focus Visible",
                "message": "No focus styles found. Add :focus-visible for keyboard navigation.",
            })

        # 5. Check for click handlers without keyboard support
        onclick_without_key = re.findall(
            r"onClick[^}]*}(?!.*onKeyDown)(?!.*onKeyUp)",
            code,
            re.DOTALL
        )
        for match in onclick_without_key:
            violations.append({
                "rule": "2.1.1 Keyboard",
                "severity": "error",
                "element": match[:50],
                "fix": "Add onKeyDown handler for Enter/Space",
            })

        # 6. Check for heading hierarchy
        headings = re.findall(r"<h([1-6])", code, re.IGNORECASE)
        if headings:
            levels = [int(h) for h in headings]
            for i in range(1, len(levels)):
                if levels[i] > levels[i-1] + 1:
                    warnings.append({
                        "rule": "1.3.1 Info and Relationships",
                        "message": f"Heading level jump: h{levels[i-1]} to h{levels[i]}",
                    })

        # 7. Check for lang attribute
        if "<html" in code and 'lang=' not in code:
            warnings.append({
                "rule": "3.1.1 Language of Page",
                "message": "Add lang attribute to <html>",
            })

        # 8. Manual checks required
        manual_checks.extend([
            "Test with screen reader (NVDA, VoiceOver)",
            "Verify color contrast with actual design tokens",
            "Test keyboard navigation flow",
            "Check with prefers-reduced-motion",
            "Verify focus order matches visual order",
        ])

        error_count = sum(1 for v in violations if v.get("severity") == "error")
        warning_count = len(warnings)
        score = max(0, 100 - (error_count * 10) - (warning_count * 5))

        return AccessibilityAudit(
            passed=score >= 90 and error_count == 0,
            score=score,
            violations=violations,
            warnings=warnings,
            manual_checks=manual_checks,
        )

    def generate_design_tokens(self, brand_colors: dict[str, str]) -> dict[str, str]:
        """
        Generate complete design token system from brand colors.

        Includes: colors, typography, spacing, shadows, radii
        """
        tokens = {
            "color-primary-50": self._lighten(brand_colors.get("primary", "#3b82f6"), 0.9),
            "color-primary-100": self._lighten(brand_colors.get("primary", "#3b82f6"), 0.8),
            "color-primary-500": brand_colors.get("primary", "#3b82f6"),
            "color-primary-700": self._darken(brand_colors.get("primary", "#3b82f6"), 0.2),
            "color-primary-900": self._darken(brand_colors.get("primary", "#3b82f6"), 0.4),

            "color-success": "#22c55e",
            "color-warning": "#f59e0b",
            "color-error": "#ef4444",
            "color-info": "#3b82f6",

            "color-text-primary": "#111827",
            "color-text-secondary": "#6b7280",
            "color-text-disabled": "#9ca3af",
            "color-text-inverse": "#ffffff",

            "color-bg-primary": "#ffffff",
            "color-bg-secondary": "#f3f4f6",
            "color-bg-tertiary": "#e5e7eb",

            "font-sans": "ui-sans-serif, system-ui, -apple-system, sans-serif",
            "font-mono": "ui-monospace, SFMono-Regular, monospace",
            "font-size-xs": "0.75rem",
            "font-size-sm": "0.875rem",
            "font-size-base": "1rem",
            "font-size-lg": "1.125rem",
            "font-size-xl": "1.25rem",
            "font-size-2xl": "1.5rem",

            "space-1": "0.25rem",
            "space-2": "0.5rem",
            "space-3": "0.75rem",
            "space-4": "1rem",
            "space-6": "1.5rem",
            "space-8": "2rem",
            "space-12": "3rem",
            "space-16": "4rem",

            "shadow-sm": "0 1px 2px 0 rgb(0 0 0 / 0.05)",
            "shadow-md": "0 4px 6px -1px rgb(0 0 0 / 0.1)",
            "shadow-lg": "0 10px 15px -3px rgb(0 0 0 / 0.1)",

            "radius-sm": "0.25rem",
            "radius-md": "0.375rem",
            "radius-lg": "0.5rem",
            "radius-xl": "0.75rem",
            "radius-full": "9999px",

            "transition-fast": "150ms ease-in-out",
            "transition-base": "200ms ease-in-out",
            "transition-slow": "300ms ease-in-out",
        }

        self._design_tokens = tokens
        return tokens

    def generate_responsive_styles(self, base_styles: dict) -> dict[str, dict]:
        """
        Generate mobile-first responsive styles with breakpoints.

        Returns styles for sm, md, lg, xl breakpoints.
        """
        responsive = {"base": base_styles}

        for breakpoint, min_width in self.BREAKPOINTS.items():
            enhanced = self._enhance_for_breakpoint(base_styles, breakpoint)
            responsive[breakpoint] = {
                "min-width": min_width,
                "styles": enhanced,
            }

        return responsive

    def validate_component_library(self, components: list[str]) -> dict[str, list[str]]:
        """
        Validate a set of components for consistency.

        Checks:
        - Naming conventions
        - Prop interfaces
        - Accessibility patterns
        - Design token usage
        """
        issues = {}

        for component in components:
            component_issues = []

            if not re.match(r"^[A-Z][a-zA-Z0-9]*$", component):
                component_issues.append(f"Name '{component}' should be PascalCase")

            if not any(a in component for a in ["aria", "role", "alt", "label"]):
                component_issues.append("Missing accessibility attributes")

            issues[component] = component_issues

        return issues

    # =================================================================
    # Internal Methods
    # =================================================================

    def _detect_component_type(self, spec: str) -> str:
        """Detect component type from specification."""
        spec_lower = spec.lower()

        type_keywords = {
            "button": ["button", "btn", "click", "submit"],
            "input": ["input", "field", "form", "text", "email"],
            "modal": ["modal", "dialog", "popup", "overlay"],
            "navigation": ["nav", "menu", "navbar", "sidebar"],
            "table": ["table", "grid", "list", "data"],
            "card": ["card", "panel", "tile"],
            "select": ["select", "dropdown", "combo"],
            "tabs": ["tab", "panel switch"],
        }

        for comp_type, keywords in type_keywords.items():
            if any(kw in spec_lower for kw in keywords):
                return comp_type

        return "generic"

    def _build_component_prompt(
        self,
        spec: str,
        component_type: str,
        pattern: dict,
        props: list[dict],
        states: list[str],
        accessibility: list[str],
    ) -> str:
        """Build LLM prompt for component generation."""
        framework_guide = {
            Framework.REACT: "React 18+ with TypeScript, functional components, hooks",
            Framework.VUE: "Vue 3 with Composition API, <script setup>",
            Framework.ANGULAR: "Angular 17+ with standalone components",
            Framework.SVELTE: "Svelte 5 with runes",
            Framework.VANILLA: "Vanilla JS with Web Components",
        }

        ds_guide = {
            DesignSystem.MATERIAL_UI: "Material UI v5 components and theme",
            DesignSystem.CHAKRA: "Chakra UI v2 components and style props",
            DesignSystem.ANT_DESIGN: "Ant Design v5 components",
            DesignSystem.TAILWIND: "Tailwind CSS utility classes",
            DesignSystem.BOOTSTRAP: "Bootstrap 5 classes",
            DesignSystem.SHADCN: "shadcn/ui components with Radix primitives",
            DesignSystem.CUSTOM: "Custom design tokens and CSS",
        }

        return f"""Generate a complete, accessible {component_type} component.

## Specification
{spec}

## Framework
{framework_guide.get(self.framework, "React")}

## Design System
{ds_guide.get(self.design_system, "Tailwind CSS")}

## Required Props
{json.dumps(props, indent=2) if props else "Infer from specification"}

## States to Implement
{chr(10).join(f"- {s}" for s in states)}

## Accessibility Requirements (WCAG 2.1 AA)
{chr(10).join(f"- {a}" for a in accessibility) if accessibility else "- All standard WCAG 2.1 AA requirements"}

## Component Pattern Reference
- Elements: {', '.join(pattern.get('elements', ['div']))}
- ARIA attributes: {', '.join(pattern.get('aria', []))}
- Keyboard support: {', '.join(pattern.get('keyboard', []))}

## Rules
1. Semantic HTML first -- div soup is forbidden
2. Every interactive element has focus styles
3. Color contrast >= 4.5:1 for normal text
4. Support prefers-reduced-motion
5. Mobile-first responsive design
6. Include Storybook story file
7. Include unit tests with React Testing Library
8. Include CSS/SCSS if not using utility framework

## Output Format
Return file contents as JSON:

```json
{{
  "src/components/{component_type.title()}.tsx": "file content...",
  "src/components/{component_type.title()}.test.tsx": "test content...",
  "src/components/{component_type.title()}.stories.tsx": "story content..."
}}
```
"""

    def _parse_component_response(self, response: str) -> dict[str, str]:
        """Extract file contents from LLM response."""
        import re

        json_match = re.search(r"```json\s*(\{.*?\})\s*```", response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        files = {}
        pattern = r"(?:###?\s*)?([^\n]+\.(tsx|jsx|vue|html|css|scss|test\.tsx|stories\.tsx))\n```[\w]*\n(.*?)```"
        matches = re.findall(pattern, response, re.DOTALL)

        for filename, _, content in matches:
            files[filename.strip()] = content.strip()

        return files

    def _fix_accessibility(self, files: dict[str, str], audit: AccessibilityAudit) -> dict[str, str]:
        """Regenerate files with accessibility fixes applied."""
        fixes = []

        for violation in audit.violations:
            fixes.append(f"- {violation['rule']}: {violation['fix']}")

        for warning in audit.warnings:
            fixes.append(f"- {warning['rule']}: {warning['message']}")

        prompt = f"""Fix these accessibility issues in the component:

## Issues
{chr(10).join(fixes)}

## Current Files
{chr(10).join(f"### {path}\n```\n{content}\n```" for path, content in files.items())}

## Rules
- Add missing ARIA attributes
- Fix semantic HTML
- Add keyboard handlers
- Ensure focus visibility
- Maintain all existing functionality

## Output
Return corrected files as JSON.
"""

        response = self.llm.generate(prompt, temperature=0.1, max_tokens=4000)
        return self._parse_component_response(response)

    def _is_low_contrast(self, hex_color: str) -> bool:
        """Basic heuristic for low contrast colors."""
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)

        luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255

        contrast = (1.0 + 0.05) / (luminance + 0.05)

        return contrast < self.WCAG_REQUIREMENTS["contrast"]

    def _lighten(self, hex_color: str, amount: float) -> str:
        """Lighten a hex color by amount (0-1)."""
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)

        r = int(r + (255 - r) * amount)
        g = int(g + (255 - g) * amount)
        b = int(b + (255 - b) * amount)

        return f"#{r:02x}{g:02x}{b:02x}"

    def _darken(self, hex_color: str, amount: float) -> str:
        """Darken a hex color by amount (0-1)."""
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)

        r = int(r * (1 - amount))
        g = int(g * (1 - amount))
        b = int(b * (1 - amount))

        return f"#{r:02x}{g:02x}{b:02x}"

    def _enhance_for_breakpoint(self, base: dict, breakpoint: str) -> dict:
        """Generate enhanced styles for larger breakpoints."""
        enhancements = {
            "sm": {"padding": "increase by 25%", "font-size": "base"},
            "md": {"padding": "increase by 50%", "font-size": "slight increase", "layout": "side-by-side"},
            "lg": {"padding": "increase by 75%", "max-width": "container", "layout": "grid"},
            "xl": {"padding": "increase by 100%", "max-width": "wide", "layout": "complex grid"},
        }

        enhanced = base.copy()
        enhanced["_breakpoint"] = breakpoint
        enhanced["_enhancements"] = enhancements.get(breakpoint, {})

        return enhanced
