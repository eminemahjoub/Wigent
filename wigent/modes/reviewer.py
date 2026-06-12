"""
Reviewer Mode — 5-Axis Code Quality Gate

The Reviewer is the last line of defense before any code merges.
It enforces structured, evidence-based review across five axes:
correctness, readability, maintainability, performance, security.

Every review is ~100 lines max per chunk. Every finding has a severity.
Nothing ships without passing review.

Phase 4 Entry Point: Review Engine
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import AsyncIterator, Callable, Optional

from wigent.core.llm_client import LLMClient
from wigent.core.review_engine import ReviewEngine, ReviewChunk, ReviewFinding
from wigent.core.skill_router import SkillRouter
from wigent.safety.validator import SafetyValidator
from wigent.tools.git_tool import GitTool


class ReviewSeverity(Enum):
    """Finding severity with merge-blocking rules."""
    CRITICAL = auto()   # Merge blocked. Fix required.
    MAJOR = auto()      # Merge blocked. Fix or explicit override.
    MINOR = auto()      # Merge warning. Fix recommended.
    NIT = auto()        # Style suggestion. Non-blocking.
    PRAISE = auto()     # Positive finding. Encourage patterns.


class ReviewAxis(Enum):
    """The five axes of review."""
    CORRECTNESS = "correctness"       # Does it work? Logic, edge cases, tests
    READABILITY = "readability"       # Can a human understand it quickly?
    MAINTAINABILITY = "maintainability"  # Will future devs hate this?
    PERFORMANCE = "performance"       # Is it fast? Memory efficient?
    SECURITY = "security"             # Is it safe? OWASP, injection, secrets?


@dataclass
class ReviewConfig:
    """Per-review configuration."""
    axes: list[ReviewAxis] = field(default_factory=lambda: list(ReviewAxis))
    max_chunk_lines: int = 100
    severity_threshold: ReviewSeverity = ReviewSeverity.MAJOR
    require_tests_for_new_code: bool = True
    require_docstrings_for_public_api: bool = True
    auto_fix_nits: bool = False
    custom_rules: list[str] = field(default_factory=list)


@dataclass
class ReviewSummary:
    """Aggregated review results."""
    total_files: int = 0
    total_chunks: int = 0
    total_findings: int = 0
    findings_by_severity: dict[str, int] = field(default_factory=dict)
    findings_by_axis: dict[str, int] = field(default_factory=dict)
    merge_blocked: bool = False
    block_reasons: list[str] = field(default_factory=list)
    review_time_seconds: float = 0.0


class ReviewerMode:
    """
    CLI interface for the 5-axis review system.

    Usage:
        reviewer = ReviewerMode(...)
        await reviewer.review_pr("feature/login-system")
        await reviewer.review_file("src/auth.py")
        await reviewer.review_diff(git_diff_output)
    """

    def __init__(
        self,
        llm_client: LLMClient,
        review_engine: ReviewEngine,
        git_tool: GitTool,
        safety_validator: SafetyValidator,
        skill_router: SkillRouter,
        config: Optional[ReviewConfig] = None,
    ):
        self.llm = llm_client
        self.engine = review_engine
        self.git = git_tool
        self.safety = safety_validator
        self.router = skill_router
        self.config = config or ReviewConfig(
            axes=list(ReviewAxis),
            max_chunk_lines=100,
        )

    # ─────────────────────────────────────────────────────────────
    # PUBLIC API: ENTRY POINTS
    # ─────────────────────────────────────────────────────────────

    async def review_pr(self, branch_or_pr: str) -> ReviewSummary:
        """
        Review an entire PR/branch.

        1. Get diff from target branch
        2. Chunk into ~100 line pieces
        3. Review each chunk across all axes
        4. Aggregate and report
        """
        print(f"🔍 Reviewing PR: {branch_or_pr}")

        # Get diff
        diff = self.git.get_pr_diff(branch_or_pr)
        if not diff:
            print("⚠ No diff found. Is this branch merged?")
            return ReviewSummary()

        return await self.review_diff(diff)

    async def review_file(self, file_path: str | Path) -> ReviewSummary:
        """Review a single file (useful for pre-commit hook)."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        content = path.read_text()
        chunks = self.engine.chunk_file(content, str(path))

        return await self._review_chunks(chunks, source=str(path))

    async def review_diff(self, diff_text: str) -> ReviewSummary:
        """
        Review a git diff directly.

        Parses added/modified files, chunks them, reviews each.
        """
        import time
        start = time.time()

        # Parse diff into file changes
        file_changes = self.git.parse_diff(diff_text)

        all_chunks: list[ReviewChunk] = []
        for change in file_changes:
            chunks = self.engine.chunk_diff(change)
            all_chunks.extend(chunks)

        summary = await self._review_chunks(all_chunks, source="diff")
        summary.review_time_seconds = time.time() - start

        return summary

    async def review_staged(self) -> ReviewSummary:
        """Review currently staged changes (pre-commit hook)."""
        diff = self.git.get_staged_diff()
        if not diff:
            print("⚠ No staged changes to review.")
            return ReviewSummary()

        return await self.review_diff(diff)

    # ─────────────────────────────────────────────────────────────
    # CORE REVIEW LOOP
    # ─────────────────────────────────────────────────────────────

    async def _review_chunks(
        self,
        chunks: list[ReviewChunk],
        source: str,
    ) -> ReviewSummary:
        """Review all chunks and aggregate results."""
        summary = ReviewSummary()
        summary.total_chunks = len(chunks)

        # Group chunks by file for reporting
        files_seen: set[str] = set()

        for i, chunk in enumerate(chunks, 1):
            print(f"  Reviewing chunk {i}/{len(chunks)}: {chunk.file_path}:{chunk.start_line}-{chunk.end_line}")

            files_seen.add(chunk.file_path)

            # Run 5-axis review on this chunk
            findings = await self._review_chunk(chunk)

            # Store findings
            chunk.findings = findings
            summary.total_findings += len(findings)

            for finding in findings:
                # Aggregate by severity
                sev_name = finding.severity.name
                summary.findings_by_severity[sev_name] = \
                    summary.findings_by_severity.get(sev_name, 0) + 1

                # Aggregate by axis
                axis_name = finding.axis.value
                summary.findings_by_axis[axis_name] = \
                    summary.findings_by_axis.get(axis_name, 0) + 1

                # Check merge blocking
                if finding.severity in (ReviewSeverity.CRITICAL, ReviewSeverity.MAJOR):
                    summary.merge_blocked = True
                    reason = f"{finding.severity.name}: {finding.axis.value} — {finding.message[:80]}"
                    if reason not in summary.block_reasons:
                        summary.block_reasons.append(reason)

        summary.total_files = len(files_seen)

        # Print summary
        self._print_summary(summary)

        return summary

    async def _review_chunk(self, chunk: ReviewChunk) -> list[ReviewFinding]:
        """Run all configured axes against a single chunk."""
        findings: list[ReviewFinding] = []

        for axis in self.config.axes:
            axis_findings = await self._review_axis(chunk, axis)
            findings.extend(axis_findings)

        # Deduplicate: same line, same message = one finding
        findings = self._deduplicate_findings(findings)

        # Sort by severity (critical first)
        severity_order = {
            ReviewSeverity.CRITICAL: 0,
            ReviewSeverity.MAJOR: 1,
            ReviewSeverity.MINOR: 2,
            ReviewSeverity.NIT: 3,
            ReviewSeverity.PRAISE: 4,
        }
        findings.sort(key=lambda f: severity_order.get(f.severity, 99))

        return findings

    async def _review_axis(
        self,
        chunk: ReviewChunk,
        axis: ReviewAxis,
    ) -> list[ReviewFinding]:
        """Review a single chunk against one axis."""
        # Build axis-specific prompt
        prompt = self._build_axis_prompt(chunk, axis)

        # Get LLM review
        response = await self.llm.complete(prompt, temperature=0.1)

        # Parse findings from structured response
        findings = self._parse_findings(response, axis, chunk)

        # Validate: no hallucinated line numbers
        findings = self._validate_findings(findings, chunk)

        return findings

    # ─────────────────────────────────────────────────────────────
    # AXIS-SPECIFIC PROMPTS
    # ─────────────────────────────────────────────────────────────

    def _build_axis_prompt(self, chunk: ReviewChunk, axis: ReviewAxis) -> str:
        """Build focused prompt for a specific review axis."""

        base_context = f"""You are a senior code reviewer performing a {axis.value.upper()} review.

File: {chunk.file_path}
Lines: {chunk.start_line}-{chunk.end_line}
Language: {chunk.language or "unknown"}

## Code Under Review
```{chunk.language or ""}
{chunk.content}
```
"""

        axis_prompts = {
            ReviewAxis.CORRECTNESS: f"""{base_context}

## CORRECTNESS Review
Check for:
- Logic errors, off-by-one, boundary conditions
- Null/None safety, type consistency
- Error handling completeness
- Test coverage for new paths
- Algorithmic correctness

For each issue found, output:
```
SEVERITY: [CRITICAL|MAJOR|MINOR|NIT]
LINE: <line_number>
MESSAGE: <specific issue and why it's wrong>
SUGGESTION: <concrete fix>
```

If no issues found, output: "PASS: No correctness concerns."
""",

            ReviewAxis.READABILITY: f"""{base_context}

## READABILITY Review
Check for:
- Clear naming (variables, functions, classes)
- Function length and single responsibility
- Comment quality (why, not what)
- Consistent style with surrounding code
- Avoidance of clever/obscure patterns

For each issue found, output:
```
SEVERITY: [CRITICAL|MAJOR|MINOR|NIT]
LINE: <line_number>
MESSAGE: <readability issue>
SUGGESTION: <how to improve>
```

If no issues found, output: "PASS: Code is clear and readable."
""",

            ReviewAxis.MAINTAINABILITY: f"""{base_context}

## MAINTAINABILITY Review
Check for:
- Code duplication (DRY violations)
- Tight coupling, hidden dependencies
- Magic numbers/strings without constants
- Future extensibility (open/closed principle)
- Documentation for public APIs

For each issue found, output:
```
SEVERITY: [CRITICAL|MAJOR|MINOR|NIT]
LINE: <line_number>
MESSAGE: <maintainability concern>
SUGGESTION: <refactoring approach>
```

If no issues found, output: "PASS: Code is maintainable."
""",

            ReviewAxis.PERFORMANCE: f"""{base_context}

## PERFORMANCE Review
Check for:
- Unnecessary computation or I/O
- Memory leaks or excessive allocation
- N+1 queries, unbounded loops
- Blocking operations in async paths
- Missing caching opportunities

For each issue found, output:
```
SEVERITY: [CRITICAL|MAJOR|MINOR|NIT]
LINE: <line_number>
MESSAGE: <performance issue>
SUGGESTION: <optimization approach>
```

If no issues found, output: "PASS: No performance concerns."
""",

            ReviewAxis.SECURITY: f"""{base_context}

## SECURITY Review
Check for:
- Injection vulnerabilities (SQL, XSS, command)
- Hardcoded secrets or credentials
- Insecure deserialization
- Missing input validation
- Unsafe file operations
- OWASP Top 10 patterns

For each issue found, output:
```
SEVERITY: [CRITICAL|MAJOR|MINOR|NIT]
LINE: <line_number>
MESSAGE: <security vulnerability>
SUGGESTION: <secure alternative>
CWE: <CWE-ID if applicable>
```

If no issues found, output: "PASS: No security concerns."
""",
        }

        return axis_prompts.get(axis, base_context)

    # ─────────────────────────────────────────────────────────────
    # FINDING PARSING & VALIDATION
    # ─────────────────────────────────────────────────────────────

    def _parse_findings(
        self,
        response: str,
        axis: ReviewAxis,
        chunk: ReviewChunk,
    ) -> list[ReviewFinding]:
        """Parse structured findings from LLM response."""
        findings = []

        # Split into individual findings
        raw_findings = re.split(r'\n(?=SEVERITY:)', response.strip())

        for raw in raw_findings:
            raw = raw.strip()
            if not raw or "PASS:" in raw:
                continue

            # Extract fields with regex
            severity_match = re.search(r'SEVERITY:\s*(\w+)', raw)
            line_match = re.search(r'LINE:\s*(\d+)', raw)
            message_match = re.search(r'MESSAGE:\s*(.+?)(?=SUGGESTION:|CWE:|$)', raw, re.DOTALL)
            suggestion_match = re.search(r'SUGGESTION:\s*(.+?)(?=CWE:|$)', raw, re.DOTALL)
            cwe_match = re.search(r'CWE:\s*(\w+[-\d]*)', raw)

            if not severity_match or not message_match:
                continue

            severity_str = severity_match.group(1).upper()
            try:
                severity = ReviewSeverity[severity_str]
            except KeyError:
                severity = ReviewSeverity.MINOR

            line_num = int(line_match.group(1)) if line_match else chunk.start_line

            finding = ReviewFinding(
                severity=severity,
                axis=axis,
                file_path=chunk.file_path,
                line_number=line_num,
                message=message_match.group(1).strip(),
                suggestion=suggestion_match.group(1).strip() if suggestion_match else None,
                cwe=cwe_match.group(1) if cwe_match else None,
                chunk_start=chunk.start_line,
                chunk_end=chunk.end_line,
            )

            findings.append(finding)

        return findings

    def _validate_findings(
        self,
        findings: list[ReviewFinding],
        chunk: ReviewChunk,
    ) -> list[ReviewFinding]:
        """Ensure findings reference valid lines in the chunk."""
        valid = []
        for f in findings:
            # Clamp line number to chunk bounds
            f.line_number = max(chunk.start_line, min(f.line_number, chunk.end_line))
            valid.append(f)
        return valid

    def _deduplicate_findings(self, findings: list[ReviewFinding]) -> list[ReviewFinding]:
        """Remove duplicate findings (same line, similar message)."""
        seen: set[tuple] = set()
        unique = []

        for f in findings:
            key = (f.file_path, f.line_number, f.axis.value, f.message[:50])
            if key not in seen:
                seen.add(key)
                unique.append(f)

        return unique

    # ─────────────────────────────────────────────────────────────
    # REPORTING
    # ─────────────────────────────────────────────────────────────

    def _print_summary(self, summary: ReviewSummary) -> None:
        """Print formatted review summary to console."""
        print("\n" + "=" * 60)
        print("  REVIEW SUMMARY")
        print("=" * 60)
        print(f"  Files reviewed:     {summary.total_files}")
        print(f"  Chunks reviewed:    {summary.total_chunks}")
        print(f"  Total findings:     {summary.total_findings}")
        print(f"  Review time:        {summary.review_time_seconds:.1f}s")
        print()

        if summary.findings_by_severity:
            print("  By Severity:")
            for sev, count in sorted(
                summary.findings_by_severity.items(),
                key=lambda x: {"CRITICAL": 0, "MAJOR": 1, "MINOR": 2, "NIT": 3, "PRAISE": 4}.get(x[0], 99)
            ):
                icon = {"CRITICAL": "🔴", "MAJOR": "🟠", "MINOR": "🟡", "NIT": "🔵", "PRAISE": "🟢"}.get(sev, "⚪")
                print(f"    {icon} {sev:12s}: {count}")

        print()

        if summary.findings_by_axis:
            print("  By Axis:")
            for axis, count in summary.findings_by_axis.items():
                print(f"    • {axis:15s}: {count}")

        print()

        if summary.merge_blocked:
            print("  ❌ MERGE BLOCKED")
            print("  Reasons:")
            for reason in summary.block_reasons[:5]:
                print(f"    • {reason}")
            if len(summary.block_reasons) > 5:
                print(f"    ... and {len(summary.block_reasons) - 5} more")
        else:
            print("  ✅ MERGE APPROVED")

        print("=" * 60)

    def export_report(self, summary: ReviewSummary, path: Path) -> None:
        """Export review summary as JSON."""
        data = {
            "total_files": summary.total_files,
            "total_chunks": summary.total_chunks,
            "total_findings": summary.total_findings,
            "findings_by_severity": summary.findings_by_severity,
            "findings_by_axis": summary.findings_by_axis,
            "merge_blocked": summary.merge_blocked,
            "block_reasons": summary.block_reasons,
            "review_time_seconds": summary.review_time_seconds,
        }
        path.write_text(json.dumps(data, indent=2))

    # ─────────────────────────────────────────────────────────────
    # INTERACTIVE COMMANDS
    # ─────────────────────────────────────────────────────────────

    async def interactive_review(self) -> None:
        """Interactive mode for manual review sessions."""
        print("🔍 Wigent Reviewer — Interactive Mode")
        print("Commands: /review <file|pr|staged>, /config, /help, /quit")

        while True:
            try:
                cmd = input("\nreviewer> ").strip()

                if cmd == "/quit":
                    break
                elif cmd == "/help":
                    self._print_help()
                elif cmd == "/config":
                    self._print_config()
                elif cmd.startswith("/review "):
                    target = cmd[8:].strip()
                    if target == "staged":
                        await self.review_staged()
                    elif Path(target).exists():
                        await self.review_file(target)
                    else:
                        await self.review_pr(target)
                else:
                    print("Unknown command. Type /help for available commands.")

            except KeyboardInterrupt:
                print("\nUse /quit to exit.")
            except Exception as e:
                print(f"Error: {e}")

    def _print_help(self) -> None:
        print("""
Available commands:
  /review <file>     Review a specific file
  /review staged     Review currently staged changes
  /review <branch>   Review a PR/branch
  /config            Show current review configuration
  /help              Show this help
  /quit              Exit reviewer mode
""")

    def _print_config(self) -> None:
        print(f"""
Current Configuration:
  Axes: {[a.value for a in self.config.axes]}
  Max chunk lines: {self.config.max_chunk_lines}
  Severity threshold: {self.config.severity_threshold.name}
  Require tests: {self.config.require_tests_for_new_code}
  Require docstrings: {self.config.require_docstrings_for_public_api}
  Auto-fix nits: {self.config.auto_fix_nits}
""")


# ─────────────────────────────────────────────────────────────────
# CLI ENTRY POINT
# ─────────────────────────────────────────────────────────────────

def main():
    """CLI entry point for reviewer mode."""
    import argparse

    parser = argparse.ArgumentParser(description="Wigent Code Reviewer")
    parser.add_argument("target", nargs="?", help="File, branch, or 'staged'")
    parser.add_argument("--axes", nargs="+", choices=[a.value for a in ReviewAxis],
                       default=[a.value for a in ReviewAxis],
                       help="Review axes to run")
    parser.add_argument("--max-lines", type=int, default=100,
                       help="Max lines per chunk")
    parser.add_argument("--threshold", choices=["CRITICAL", "MAJOR", "MINOR"],
                       default="MAJOR", help="Minimum blocking severity")
    parser.add_argument("--interactive", "-i", action="store_true",
                       help="Interactive mode")

    args = parser.parse_args()

    # In real implementation, would initialize from config/registry
    reviewer = ReviewerMode(
        llm_client=LLMClient(),
        review_engine=ReviewEngine(),
        git_tool=GitTool(),
        safety_validator=SafetyValidator(),
        skill_router=SkillRouter(),
        config=ReviewConfig(
            axes=[ReviewAxis(a) for a in args.axes],
            max_chunk_lines=args.max_lines,
            severity_threshold=ReviewSeverity[args.threshold],
        ),
    )

    if args.interactive or not args.target:
        asyncio.run(reviewer.interactive_review())
    elif args.target == "staged":
        summary = asyncio.run(reviewer.review_staged())
        exit(1 if summary.merge_blocked else 0)
    else:
        path = Path(args.target)
        if path.exists():
            summary = asyncio.run(reviewer.review_file(path))
        else:
            summary = asyncio.run(reviewer.review_pr(args.target))
        exit(1 if summary.merge_blocked else 0)


if __name__ == "__main__":
    main()
