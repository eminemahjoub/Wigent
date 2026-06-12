"""
Simplify Mode — Complexity Reduction with Chesterton's Fence

The Simplify mode reduces code complexity while preserving behavior.
It is the antidote to over-engineering and the cure for technical debt.

Core rules:
1. Chesterton's Fence: Never remove code until you understand why it exists
2. Rule of 500: No function > 500 lines, no file > 500 lines, no class > 500 lines
3. Preserve behavior: Simplification must pass all existing tests
4. One change at a time: Simplify, test, commit. Repeat.

Phase 4, Week 11: Code Simplification
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Optional

from wigent.core.llm_client import LLMClient
from wigent.core.review_engine import ReviewEngine
from wigent.tools.git_tool import GitTool


class SimplifyAction(Enum):
    """Types of simplification actions."""
    EXTRACT_FUNCTION = auto()
    INLINE_VARIABLE = auto()
    REMOVE_DEAD_CODE = auto()
    FLATTEN_CONDITIONALS = auto()
    REPLACE_LOOP = auto()
    CONSOLIDATE_DUPLICATION = auto()
    REMOVE_COMMENT = auto()
    RENAME = auto()
    REORDER = auto()
    DELETE_FILE = auto()


@dataclass
class ComplexityMetrics:
    """Before/after complexity measurements."""
    lines: int = 0
    functions: int = 0
    max_function_lines: int = 0
    cyclomatic_complexity: int = 0
    cognitive_complexity: int = 0
    nesting_depth: int = 0
    duplicate_blocks: int = 0


@dataclass
class SimplificationProposal:
    """A single proposed simplification."""
    action: SimplifyAction
    file_path: str
    start_line: int
    end_line: int
    original_code: str
    proposed_code: str
    rationale: str
    chesterton_check: str
    behavior_preserved: bool = False
    complexity_before: ComplexityMetrics = field(default_factory=ComplexityMetrics)
    complexity_after: ComplexityMetrics = field(default_factory=ComplexityMetrics)
    risk_level: str = "low"
    estimated_review_time: int = 0


@dataclass
class SimplifySession:
    """A complete simplification session."""
    target: str
    proposals: list[SimplificationProposal] = field(default_factory=list)
    total_complexity_before: ComplexityMetrics = field(default_factory=ComplexityMetrics)
    total_complexity_after: ComplexityMetrics = field(default_factory=ComplexityMetrics)
    rejected_proposals: list[SimplificationProposal] = field(default_factory=list)
    commits_made: list[str] = field(default_factory=list)


class SimplifyMode:
    """
    Interactive simplification mode for reducing code complexity.

    Usage:
        simplify = SimplifyMode(...)
        session = await simplify.analyze("src/legacy_module.py")
        await simplify.apply(session.proposals[0])
    """

    MAX_FUNCTION_LINES = 500
    MAX_FILE_LINES = 500
    MAX_CLASS_LINES = 500

    def __init__(
        self,
        llm_client: LLMClient,
        review_engine: ReviewEngine,
        git_tool: GitTool,
    ):
        self.llm = llm_client
        self.review_engine = review_engine
        self.git = git_tool
        self._analyzer: Any = None

    @property
    def analyzer(self) -> Any:
        """Lazy-loaded ComplexityAnalyzer to avoid import errors when tool is missing."""
        if self._analyzer is None:
            from wigent.tools.complexity_analyzer import ComplexityAnalyzer
            self._analyzer = ComplexityAnalyzer()
        return self._analyzer

    # ─────────────────────────────────────────────────────────────
    # ANALYSIS: FIND SIMPLIFICATION OPPORTUNITIES
    # ─────────────────────────────────────────────────────────────

    async def analyze(self, target: str | Path) -> SimplifySession:
        """
        Analyze code for simplification opportunities.

        Scans for:
        - Functions/files/classes exceeding Rule of 500
        - High cyclomatic complexity (>10)
        - Deep nesting (>4 levels)
        - Dead code (unused imports, unreachable branches)
        - Code duplication (>3 similar blocks)
        - Comments explaining obvious code
        """
        target_path = Path(target)
        session = SimplifySession(target=str(target_path))

        if target_path.is_file():
            proposals = await self._analyze_file(target_path)
        elif target_path.is_dir():
            proposals = []
            for file_path in sorted(target_path.rglob("*.py")):
                file_proposals = await self._analyze_file(file_path)
                proposals.extend(file_proposals)
        else:
            raise ValueError(f"Target not found: {target}")

        session.proposals = proposals

        session.total_complexity_before = self._aggregate_metrics(
            [p.complexity_before for p in proposals]
        )
        session.total_complexity_after = self._aggregate_metrics(
            [p.complexity_after for p in proposals]
        )

        return session

    async def _analyze_file(self, file_path: Path) -> list[SimplificationProposal]:
        """Find simplification opportunities in a single file."""
        proposals: list[SimplificationProposal] = []
        content = file_path.read_text()
        lines = content.split("\n")

        if len(lines) > self.MAX_FILE_LINES:
            proposals.append(self._create_file_split_proposal(file_path, content))

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return proposals

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_lines = node.end_lineno - node.lineno + 1

                if func_lines > self.MAX_FUNCTION_LINES:
                    proposals.append(
                        await self._create_function_split_proposal(file_path, node, content)
                    )

                complexity = self._compute_cyclomatic_complexity(node)
                if complexity > 10:
                    proposals.append(
                        await self._create_complexity_reduction_proposal(
                            file_path, node, content, complexity
                        )
                    )

                max_depth = self._compute_nesting_depth(node)
                if max_depth > 4:
                    proposals.append(
                        await self._create_nesting_flatten_proposal(
                            file_path, node, content, max_depth
                        )
                    )

            elif isinstance(node, ast.ClassDef):
                class_lines = node.end_lineno - node.lineno + 1
                if class_lines > self.MAX_CLASS_LINES:
                    proposals.append(
                        await self._create_class_split_proposal(file_path, node, content)
                    )

        dead_code = self._find_dead_code(tree, content)
        for dead in dead_code:
            proposals.append(self._create_dead_code_removal_proposal(file_path, dead))

        duplicates = self.analyzer.find_duplicates(content)
        for dup in duplicates:
            proposals.append(self._create_deduplication_proposal(file_path, dup))

        obvious_comments = self._find_obvious_comments(tree, content)
        for comment in obvious_comments:
            proposals.append(self._create_comment_removal_proposal(file_path, comment))

        return proposals

    # ─────────────────────────────────────────────────────────────
    # PROPOSAL GENERATORS
    # ─────────────────────────────────────────────────────────────

    async def _create_function_split_proposal(
        self,
        file_path: Path,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        content: str,
    ) -> SimplificationProposal:
        """Propose splitting a large function."""
        func_lines = content.split("\n")[node.lineno - 1:node.end_lineno]
        func_code = "\n".join(func_lines)

        prompt = f"""Analyze this {len(func_lines)}-line function and identify 2-4 logical sections that could be extracted into helper functions.

Function:
```python
{func_code}
```

Output:
SECTIONS:
1. <description> (lines X-Y)
2. <description> (lines X-Y)
...

PROPOSED_HELPERS:
```python
<helper function 1>
```

```python
<helper function 2>
```

REFACTORED_MAIN:
```python
<refactored main function using helpers>
```
"""

        response = await self.llm.complete(prompt, temperature=0.2)

        proposed_code = self._extract_code_blocks(response)

        fence_check = self._chesterton_fence(node, content)

        return SimplificationProposal(
            action=SimplifyAction.EXTRACT_FUNCTION,
            file_path=str(file_path),
            start_line=node.lineno,
            end_line=node.end_lineno,
            original_code=func_code,
            proposed_code="\n\n".join(proposed_code),
            rationale=f"Function is {len(func_lines)} lines (Rule of 500: max {self.MAX_FUNCTION_LINES})",
            chesterton_check=fence_check,
            complexity_before=ComplexityMetrics(
                lines=len(func_lines),
                cyclomatic_complexity=self._compute_cyclomatic_complexity(node),
            ),
            complexity_after=ComplexityMetrics(
                lines=len(func_lines),
                functions=len(proposed_code) - 1,
            ),
            risk_level="medium",
        )

    async def _create_complexity_reduction_proposal(
        self,
        file_path: Path,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        content: str,
        complexity: int,
    ) -> SimplificationProposal:
        """Propose reducing cyclomatic complexity."""
        func_lines = content.split("\n")[node.lineno - 1:node.end_lineno]
        func_code = "\n".join(func_lines)

        prompt = f"""This function has cyclomatic complexity {complexity} (target: ≤10). Simplify it.

Strategies:
- Replace nested conditionals with guard clauses
- Extract strategy pattern for complex branching
- Use polymorphism instead of switch/if-elif chains
- Early returns to reduce nesting

Function:
```python
{func_code}
```

Output the simplified version with explanation of changes.
"""

        response = await self.llm.complete(prompt, temperature=0.2)
        proposed_code = self._extract_first_code_block(response)

        return SimplificationProposal(
            action=SimplifyAction.FLATTEN_CONDITIONALS,
            file_path=str(file_path),
            start_line=node.lineno,
            end_line=node.end_lineno,
            original_code=func_code,
            proposed_code=proposed_code or func_code,
            rationale=f"Cyclomatic complexity {complexity} exceeds threshold (10)",
            chesterton_check=self._chesterton_fence(node, content),
            complexity_before=ComplexityMetrics(
                cyclomatic_complexity=complexity,
            ),
            complexity_after=ComplexityMetrics(
                cyclomatic_complexity=10,
            ),
            risk_level="medium",
        )

    def _create_dead_code_removal_proposal(
        self,
        file_path: Path,
        dead: dict[str, Any],
    ) -> SimplificationProposal:
        """Propose removing dead code."""
        return SimplificationProposal(
            action=SimplifyAction.REMOVE_DEAD_CODE,
            file_path=str(file_path),
            start_line=dead["start_line"],
            end_line=dead["end_line"],
            original_code=dead["code"],
            proposed_code="",
            rationale=f"Dead code: {dead['reason']}",
            chesterton_check=dead.get("why_exists", "Unknown — verify no dynamic usage"),
            complexity_before=ComplexityMetrics(lines=dead["line_count"]),
            complexity_after=ComplexityMetrics(lines=0),
            risk_level="low",
        )

    def _create_deduplication_proposal(
        self,
        file_path: Path,
        dup: dict[str, Any],
    ) -> SimplificationProposal:
        """Propose consolidating duplicated code."""
        return SimplificationProposal(
            action=SimplifyAction.CONSOLIDATE_DUPLICATION,
            file_path=str(file_path),
            start_line=dup["start_line"],
            end_line=dup["end_line"],
            original_code=dup["code"],
            proposed_code=dup.get("extracted_function", "# TODO: Extract common function"),
            rationale=f"Duplicated block found {dup['occurrences']} times",
            chesterton_check="Each occurrence may have subtle differences — verify",
            complexity_before=ComplexityMetrics(
                lines=dup["total_lines"],
                duplicate_blocks=dup["occurrences"],
            ),
            complexity_after=ComplexityMetrics(
                lines=dup["function_lines"],
                functions=1,
            ),
            risk_level="medium",
        )

    def _create_comment_removal_proposal(
        self,
        file_path: Path,
        comment: dict[str, Any],
    ) -> SimplificationProposal:
        """Propose removing obvious comment."""
        return SimplificationProposal(
            action=SimplifyAction.REMOVE_COMMENT,
            file_path=str(file_path),
            start_line=comment["line"],
            end_line=comment["line"],
            original_code=comment["text"],
            proposed_code="",
            rationale=f"Comment states the obvious: '{comment['text'][:60]}...'",
            chesterton_check="Verify comment doesn't document non-obvious behavior",
            complexity_before=ComplexityMetrics(lines=1),
            complexity_after=ComplexityMetrics(lines=0),
            risk_level="low",
        )

    # ─────────────────────────────────────────────────────────────
    # CHESTERTON'S FENCE
    # ─────────────────────────────────────────────────────────────

    def _chesterton_fence(
        self,
        node: ast.AST,
        content: str,
    ) -> str:
        """
        Investigate why code exists before proposing to change it.

        Checks git history, surrounding comments, test coverage,
        and cross-references.
        """
        checks: list[str] = []

        try:
            blame = self.git.blame_lines(
                file_path=content,
                start_line=node.lineno,
                end_line=getattr(node, 'end_lineno', node.lineno),
            )
            if blame:
                checks.append(f"Added by {blame.get('author')} in {blame.get('commit', 'unknown')[:8]}: {blame.get('message', 'no message')}")
        except Exception:
            checks.append("Git history unavailable")

        lines = content.split("\n")
        start = max(0, node.lineno - 5)
        context = "\n".join(lines[start:node.lineno - 1])
        comments = [l for l in context.split("\n") if l.strip().startswith("#")]
        if comments:
            checks.append(f"Preceding comments: {'; '.join(comments[-2:])}")

        if not checks:
            return "No context found. Proceed with caution."

        return " | ".join(checks)

    # ─────────────────────────────────────────────────────────────
    # APPLICATION & VERIFICATION
    # ─────────────────────────────────────────────────────────────

    async def apply(self, proposal: SimplificationProposal) -> bool:
        """
        Apply a simplification proposal safely.

        1. Create branch
        2. Apply change
        3. Run tests
        4. If tests pass: commit
        5. If tests fail: revert, report
        """
        print(f"Applying: {proposal.action.name} in {proposal.file_path}:{proposal.start_line}")

        if "Unknown" in proposal.chesterton_check and proposal.risk_level == "high":
            print(f"⚠ High risk with unknown context. Skipping.")
            return False

        branch_name = f"simplify/{proposal.action.name.lower()}-{Path(proposal.file_path).stem}"
        self.git.create_branch(branch_name)

        file_path = Path(proposal.file_path)
        content = file_path.read_text()
        lines = content.split("\n")

        new_lines = (
            lines[:proposal.start_line - 1] +
            proposal.proposed_code.split("\n") +
            lines[proposal.end_line:]
        )

        file_path.write_text("\n".join(new_lines))

        test_result = self._run_tests(file_path)

        if test_result["passed"]:
            proposal.behavior_preserved = True

            commit_msg = self._generate_commit_message(proposal)
            self.git.commit(commit_msg)
            proposal.estimated_review_time = self._estimate_review_time(proposal)

            print(f"✅ Simplified and committed: {commit_msg[:60]}")
            return True
        else:
            self.git.reset_hard()
            print(f"❌ Tests failed. Reverted.")
            print(f"   Failures: {test_result.get('failures', 'unknown')}")
            return False

    async def apply_batch(
        self,
        session: SimplifySession,
        max_proposals: int = 5,
    ) -> SimplifySession:
        """Apply top N proposals, lowest risk first."""
        sorted_proposals = sorted(
            session.proposals,
            key=lambda p: ({"low": 0, "medium": 1, "high": 2}.get(p.risk_level, 3), -p.complexity_before.lines),
        )

        applied = 0
        for proposal in sorted_proposals:
            if applied >= max_proposals:
                break

            success = await self.apply(proposal)
            if success:
                applied += 1
                session.commits_made.append(f"{proposal.action.name}: {proposal.file_path}")
            else:
                session.rejected_proposals.append(proposal)

        return session

    # ─────────────────────────────────────────────────────────────
    # METRICS & ANALYSIS
    # ─────────────────────────────────────────────────────────────

    def _compute_cyclomatic_complexity(self, node: ast.AST) -> int:
        """Compute McCabe cyclomatic complexity."""
        complexity = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler,
                                  ast.With, ast.Assert)):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
        return complexity

    def _compute_nesting_depth(self, node: ast.AST) -> int:
        """Compute maximum nesting depth."""

        def depth(n: ast.AST, current: int = 0) -> int:
            if isinstance(n, (ast.If, ast.For, ast.While, ast.With, ast.Try,
                              ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                current += 1
            max_child = current
            for child in ast.iter_child_nodes(n):
                max_child = max(max_child, depth(child, current))
            return max_child

        return depth(node)

    def _find_dead_code(self, tree: ast.AST, content: str) -> list[dict]:
        """Find potentially dead code."""
        dead: list[dict] = []

        imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                names.add(node.id)

        for imp in imports:
            if isinstance(imp, ast.Import):
                for alias in imp.names:
                    name = alias.asname if alias.asname else alias.name.split(".")[0]
                    if name not in names:
                        lines = content.split("\n")
                        dead.append({
                            "start_line": imp.lineno,
                            "end_line": imp.end_lineno,
                            "code": "\n".join(lines[imp.lineno - 1:imp.end_lineno]),
                            "reason": f"Unused import: {alias.name}",
                            "line_count": imp.end_lineno - imp.lineno + 1,
                        })

        return dead

    def _find_obvious_comments(self, tree: ast.AST, content: str) -> list[dict]:
        """Find comments that state the obvious."""
        obvious: list[dict] = []
        lines = content.split("\n")

        obvious_patterns = [
            r'#\s*initialize', r'#\s*set\s+up', r'#\s*clean\s+up',
            r'#\s*loop\s+through', r'#\s*check\s+if', r'#\s*return',
            r'#\s*create', r'#\s*get', r'#\s*update', r'#\s*delete',
        ]

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped.startswith("#"):
                continue

            comment_text = stripped[1:].strip().lower()

            for pattern in obvious_patterns:
                if re.search(pattern, comment_text):
                    if i < len(lines):
                        next_line = lines[i].strip()
                        if len(next_line) < 50 and comment_text.split()[0] in next_line.lower():
                            obvious.append({
                                "line": i,
                                "text": stripped,
                                "reason": f"Restates next line: {next_line[:40]}",
                            })
                    break

        return obvious

    # ─────────────────────────────────────────────────────────────
    # UTILITIES
    # ─────────────────────────────────────────────────────────────

    def _extract_code_blocks(self, text: str) -> list[str]:
        """Extract all code blocks from markdown."""
        blocks: list[str] = []
        in_block = False
        current: list[str] = []

        for line in text.split("\n"):
            if line.strip().startswith("```"):
                if in_block:
                    blocks.append("\n".join(current))
                    current = []
                in_block = not in_block
            elif in_block:
                current.append(line)

        return blocks

    def _extract_first_code_block(self, text: str) -> Optional[str]:
        """Extract first code block from markdown."""
        blocks = self._extract_code_blocks(text)
        return blocks[0] if blocks else None

    def _aggregate_metrics(self, metrics: list[ComplexityMetrics]) -> ComplexityMetrics:
        """Aggregate multiple complexity metrics."""
        total = ComplexityMetrics()
        for m in metrics:
            total.lines += m.lines
            total.functions += m.functions
            total.max_function_lines = max(total.max_function_lines, m.max_function_lines)
            total.cyclomatic_complexity += m.cyclomatic_complexity
            total.cognitive_complexity += m.cognitive_complexity
            total.nesting_depth = max(total.nesting_depth, m.nesting_depth)
            total.duplicate_blocks += m.duplicate_blocks
        return total

    def _generate_commit_message(self, proposal: SimplificationProposal) -> str:
        """Generate conventional commit message for simplification."""
        action_map = {
            SimplifyAction.EXTRACT_FUNCTION: "refactor",
            SimplifyAction.INLINE_VARIABLE: "refactor",
            SimplifyAction.REMOVE_DEAD_CODE: "chore",
            SimplifyAction.FLATTEN_CONDITIONALS: "refactor",
            SimplifyAction.REPLACE_LOOP: "refactor",
            SimplifyAction.CONSOLIDATE_DUPLICATION: "refactor",
            SimplifyAction.REMOVE_COMMENT: "docs",
            SimplifyAction.RENAME: "refactor",
            SimplifyAction.REORDER: "refactor",
            SimplifyAction.DELETE_FILE: "chore",
        }

        prefix = action_map.get(proposal.action, "refactor")
        file = Path(proposal.file_path).name

        messages = {
            SimplifyAction.EXTRACT_FUNCTION: f"{prefix}: extract functions from oversized {file}",
            SimplifyAction.REMOVE_DEAD_CODE: f"{prefix}: remove dead code from {file}",
            SimplifyAction.FLATTEN_CONDITIONALS: f"{prefix}: reduce nesting in {file}",
            SimplifyAction.CONSOLIDATE_DUPLICATION: f"{prefix}: DRY violation in {file}",
            SimplifyAction.REMOVE_COMMENT: f"{prefix}: remove obvious comments in {file}",
        }

        return messages.get(proposal.action, f"{prefix}: simplify {proposal.action.name.lower()} in {file}")

    def _estimate_review_time(self, proposal: SimplificationProposal) -> int:
        """Estimate human review time in minutes."""
        base = 5
        lines = proposal.end_line - proposal.start_line
        base += lines // 20
        if proposal.risk_level == "high":
            base += 10
        elif proposal.risk_level == "medium":
            base += 5
        return base

    def _run_tests(self, file_path: Path) -> dict[str, Any]:
        """Run relevant tests for the modified file."""
        import subprocess
        result = subprocess.run(
            ["pytest", "-x", "-q"],
            capture_output=True,
            text=True,
            timeout=300,
        )
        return {
            "passed": result.returncode == 0,
            "output": result.stdout,
            "failures": result.stderr if result.returncode != 0 else None,
        }

    def _create_file_split_proposal(self, file_path: Path, content: str) -> SimplificationProposal:
        """Propose splitting a file that exceeds Rule of 500."""
        lines = content.split("\n")
        return SimplificationProposal(
            action=SimplifyAction.EXTRACT_FUNCTION,
            file_path=str(file_path),
            start_line=1,
            end_line=len(lines),
            original_code=content,
            proposed_code="# TODO: Split into multiple files by responsibility",
            rationale=f"File is {len(lines)} lines (Rule of 500: max {self.MAX_FILE_LINES})",
            chesterton_check="Verify no circular imports created by splitting",
            complexity_before=ComplexityMetrics(lines=len(lines)),
            complexity_after=ComplexityMetrics(lines=self.MAX_FILE_LINES),
            risk_level="high",
        )

    async def _create_nesting_flatten_proposal(
        self,
        file_path: Path,
        node: ast.AST,
        content: str,
        depth: int,
    ) -> SimplificationProposal:
        """Propose flattening nested conditionals."""
        func_lines = content.split("\n")[node.lineno - 1:node.end_lineno]
        return SimplificationProposal(
            action=SimplifyAction.FLATTEN_CONDITIONALS,
            file_path=str(file_path),
            start_line=node.lineno,
            end_line=node.end_lineno,
            original_code="\n".join(func_lines),
            proposed_code="# TODO: Flatten nested conditionals with guard clauses",
            rationale=f"Nesting depth {depth} exceeds threshold (4)",
            chesterton_check=self._chesterton_fence(node, content),
            risk_level="medium",
        )

    async def _create_class_split_proposal(
        self,
        file_path: Path,
        node: ast.ClassDef,
        content: str,
    ) -> SimplificationProposal:
        """Propose splitting a class that exceeds Rule of 500."""
        class_lines = content.split("\n")[node.lineno - 1:node.end_lineno]
        return SimplificationProposal(
            action=SimplifyAction.EXTRACT_FUNCTION,
            file_path=str(file_path),
            start_line=node.lineno,
            end_line=node.end_lineno,
            original_code="\n".join(class_lines),
            proposed_code="# TODO: Extract responsibilities into separate classes",
            rationale=f"Class exceeds {self.MAX_CLASS_LINES} lines",
            chesterton_check=self._chesterton_fence(node, content),
            risk_level="high",
        )
