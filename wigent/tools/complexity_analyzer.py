"""
Complexity Analyzer — Static Analysis for Code Quality Metrics

Provides quantitative measurements that drive:
- Simplify mode (what needs reduction)
- Review engine (performance axis findings)
- Benchmarks (track complexity over time)

Metrics: cyclomatic, cognitive, halstead, duplication, nesting, fan-in/out
"""

from __future__ import annotations

import ast
import hashlib
import io
import json
import math
import re
import tokenize
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Optional


class MetricType(Enum):
    """Categories of complexity metrics."""
    STRUCTURAL = auto()
    CONTROL_FLOW = auto()
    COGNITIVE = auto()
    HALSTEAD = auto()
    DEPENDENCY = auto()
    DUPLICATION = auto()


@dataclass
class FunctionMetrics:
    """Metrics for a single function/method."""
    name: str
    file_path: str
    start_line: int
    end_line: int

    lines: int = 0
    blank_lines: int = 0
    comment_lines: int = 0

    cyclomatic_complexity: int = 1
    decision_points: int = 0
    nesting_depth: int = 0
    max_nesting: int = 0
    return_count: int = 0
    branch_count: int = 0
    loop_count: int = 0

    cognitive_complexity: int = 0
    argument_count: int = 0
    local_variable_count: int = 0

    halstead_length: int = 0
    halstead_vocabulary: int = 0
    halstead_volume: float = 0.0
    halstead_difficulty: float = 0.0
    halstead_effort: float = 0.0
    halstead_time: float = 0.0
    halstead_bugs: float = 0.0

    fan_in: int = 0
    fan_out: int = 0
    external_calls: list[str] = field(default_factory=list)

    is_async: bool = False
    is_generator: bool = False
    has_decorators: bool = False
    is_recursive: bool = False


@dataclass
class FileMetrics:
    """Metrics for a single file."""
    file_path: str
    language: str = "python"

    total_lines: int = 0
    code_lines: int = 0
    blank_lines: int = 0
    comment_lines: int = 0

    function_count: int = 0
    class_count: int = 0
    import_count: int = 0

    functions: list[FunctionMetrics] = field(default_factory=list)

    max_function_complexity: int = 0
    avg_function_complexity: float = 0.0
    max_function_lines: int = 0
    avg_function_lines: float = 0.0

    duplicate_blocks: int = 0
    duplicate_lines: int = 0

    maintainability_index: float = 0.0


@dataclass
class DuplicationBlock:
    """A detected duplicated code block."""
    hash: str
    code: str
    occurrences: list[tuple[str, int, int]]
    token_count: int = 0
    is_whitespace_normalized: bool = False

    @property
    def total_lines(self) -> int:
        return sum(end - start + 1 for _, start, end in self.occurrences)

    @property
    def file_count(self) -> int:
        return len(set(f for f, _, _ in self.occurrences))


@dataclass
class ProjectMetrics:
    """Aggregated metrics across the project."""
    files: list[FileMetrics] = field(default_factory=list)
    total_lines: int = 0
    total_functions: int = 0
    total_classes: int = 0

    most_complex_functions: list[FunctionMetrics] = field(default_factory=list)
    largest_functions: list[FunctionMetrics] = field(default_factory=list)
    most_duplicated: list[DuplicationBlock] = field(default_factory=list)

    complexity_histogram: dict[int, int] = field(default_factory=dict)
    lines_histogram: dict[int, int] = field(default_factory=dict)

    complexity_trend: list[tuple[str, float]] = field(default_factory=list)


@dataclass
class Token:
    """A code token for duplication detection."""
    type: str
    value: str
    start_line: int
    end_line: int


class ComplexityAnalyzer:
    """
    Static code analyzer for complexity metrics and duplication detection.

    Uses AST parsing for Python, regex/tokenization for other languages.
    Integrates with Simplify mode and Review engine for data-driven
    quality decisions.
    """

    COMPLEXITY_HIGH = 10
    COMPLEXITY_CRITICAL = 20
    FUNCTION_LINES_HIGH = 50
    FUNCTION_LINES_CRITICAL = 100
    NESTING_HIGH = 4
    COGNITIVE_HIGH = 15

    MIN_DUPLICATE_TOKENS = 20
    MIN_DUPLICATE_LINES = 5

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or Path.cwd()
        self._function_calls: dict[str, list[str]] = defaultdict(list)
        self._function_callers: dict[str, list[str]] = defaultdict(list)
        self._all_functions: list[FunctionMetrics] = []

    # ─────────────────────────────────────────────────────────────
    # PUBLIC API
    # ─────────────────────────────────────────────────────────────

    def analyze_file(self, file_path: str | Path) -> FileMetrics:
        """Analyze a single file and return comprehensive metrics."""
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        content = path.read_text()
        language = self._detect_language(path)

        if language == "python":
            return self._analyze_python_file(path, content)
        else:
            return self._analyze_generic_file(path, content, language)

    def analyze_project(self, pattern: str = "**/*.py") -> ProjectMetrics:
        """Analyze all matching files in the project."""
        self._function_calls.clear()
        self._function_callers.clear()
        self._all_functions.clear()

        project = ProjectMetrics()

        for file_path in self.project_root.glob(pattern):
            try:
                file_metrics = self.analyze_file(file_path)
                project.files.append(file_metrics)
                project.total_lines += file_metrics.total_lines
                project.total_functions += file_metrics.function_count
                project.total_classes += file_metrics.class_count

                for func in file_metrics.functions:
                    cc = func.cyclomatic_complexity
                    project.complexity_histogram[cc] = \
                        project.complexity_histogram.get(cc, 0) + 1

                    fl = func.lines
                    bucket = (fl // 10) * 10
                    project.lines_histogram[bucket] = \
                        project.lines_histogram.get(bucket, 0) + 1

                self._all_functions.extend(file_metrics.functions)

            except Exception as e:
                print(f"Warning: Could not analyze {file_path}: {e}")

        project.most_complex_functions = sorted(
            self._all_functions,
            key=lambda f: f.cyclomatic_complexity,
            reverse=True,
        )[:20]

        project.largest_functions = sorted(
            self._all_functions,
            key=lambda f: f.lines,
            reverse=True,
        )[:20]

        self._compute_dependency_metrics(project)

        return project

    def find_duplicates(
        self,
        content: str,
        file_path: Optional[str] = None,
        min_tokens: Optional[int] = None,
        min_lines: Optional[int] = None,
    ) -> list[DuplicationBlock]:
        """
        Find duplicated code blocks using token-based fingerprinting.
        """
        min_tokens = min_tokens or self.MIN_DUPLICATE_TOKENS
        min_lines = min_lines or self.MIN_DUPLICATE_LINES

        tokens = self._tokenize_python(content) if file_path and file_path.endswith(".py") \
            else self._tokenize_generic(content)

        if len(tokens) < min_tokens:
            return []

        normalized = self._normalize_tokens(tokens)

        window_size = min_tokens
        hashes: dict[str, list[tuple[int, int]]] = defaultdict(list)

        for i in range(len(normalized) - window_size + 1):
            window = normalized[i:i + window_size]
            window_hash = self._hash_tokens(window)
            hashes[window_hash].append((i, i + window_size))

        clusters: list[DuplicationBlock] = []
        for hash_val, positions in hashes.items():
            if len(positions) < 2:
                continue

            merged = self._merge_positions(positions)

            for cluster in merged:
                start, end = cluster
                original_start = tokens[start].start_line
                original_end = tokens[end - 1].end_line

                if original_end - original_start + 1 < min_lines:
                    continue

                code_lines = content.split("\n")[original_start - 1:original_end]
                code = "\n".join(code_lines)

                clusters.append(DuplicationBlock(
                    hash=hash_val,
                    code=code,
                    occurrences=[(str(file_path or "unknown"), original_start, original_end)],
                    token_count=end - start,
                ))

        return clusters

    def find_duplicates_project(
        self,
        pattern: str = "**/*.py",
    ) -> list[DuplicationBlock]:
        """Find all duplicates across the project."""
        all_blocks: dict[str, DuplicationBlock] = {}

        for file_path in self.project_root.glob(pattern):
            try:
                content = file_path.read_text()
                dups = self.find_duplicates(content, str(file_path))

                for dup in dups:
                    if dup.hash in all_blocks:
                        existing = all_blocks[dup.hash]
                        for occ in dup.occurrences:
                            if occ not in existing.occurrences:
                                existing.occurrences.append(occ)
                    else:
                        all_blocks[dup.hash] = dup

            except Exception:
                continue

        return [
            block for block in all_blocks.values()
            if len(block.occurrences) >= 2
        ]

    def get_hotspots(self, project: ProjectMetrics) -> list[dict]:
        """
        Identify files that are high-risk for changes.
        """
        hotspots = []

        for file_metrics in project.files:
            dup_ratio = (file_metrics.duplicate_lines /
                         max(file_metrics.total_lines, 1)) * 100
            score = (
                file_metrics.max_function_complexity * 0.4 +
                file_metrics.avg_function_complexity * 0.3 +
                dup_ratio * 0.3
            )

            hotspots.append({
                "file": file_metrics.file_path,
                "score": round(score, 2),
                "max_complexity": file_metrics.max_function_complexity,
                "avg_complexity": round(file_metrics.avg_function_complexity, 2),
                "duplicate_lines": file_metrics.duplicate_lines,
                "risk_level": "high" if score > 20 else "medium" if score > 10 else "low",
            })

        return sorted(hotspots, key=lambda x: x["score"], reverse=True)

    def compare_complexity(self, before: FileMetrics, after: FileMetrics) -> dict[str, Any]:
        """Compare two versions of a file for complexity delta."""
        return {
            "file": before.file_path,
            "total_lines_delta": after.total_lines - before.total_lines,
            "max_complexity_delta": after.max_function_complexity - before.max_function_complexity,
            "avg_complexity_delta": round(after.avg_function_complexity - before.avg_function_complexity, 2),
            "duplicate_lines_delta": after.duplicate_lines - before.duplicate_lines,
            "maintainability_delta": round(after.maintainability_index - before.maintainability_index, 2),
            "improved": after.maintainability_index > before.maintainability_index,
            "functions_added": after.function_count - before.function_count,
            "functions_removed": before.function_count - after.function_count,
        }

    # ─────────────────────────────────────────────────────────────
    # PYTHON ANALYSIS
    # ─────────────────────────────────────────────────────────────

    def _analyze_python_file(self, file_path: Path, content: str) -> FileMetrics:
        """Deep AST-based analysis for Python files."""
        metrics = FileMetrics(file_path=str(file_path), language="python")

        lines = content.split("\n")
        metrics.total_lines = len(lines)
        metrics.blank_lines = sum(1 for l in lines if not l.strip())
        metrics.comment_lines = sum(1 for l in lines if l.strip().startswith("#"))
        metrics.code_lines = metrics.total_lines - metrics.blank_lines - metrics.comment_lines

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return metrics

        metrics.import_count = len([
            node for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
        ])

        classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
        metrics.class_count = len(classes)

        functions = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_metrics = self._analyze_function(node, str(file_path), content)
                functions.append(func_metrics)
                self._track_calls(func_metrics, node)

        metrics.functions = functions
        metrics.function_count = len(functions)

        if functions:
            metrics.max_function_complexity = max(f.cyclomatic_complexity for f in functions)
            metrics.avg_function_complexity = sum(f.cyclomatic_complexity for f in functions) / len(functions)
            metrics.max_function_lines = max(f.lines for f in functions)
            metrics.avg_function_lines = sum(f.lines for f in functions) / len(functions)

        dups = self.find_duplicates(content, str(file_path))
        metrics.duplicate_blocks = len(dups)
        metrics.duplicate_lines = sum(dup.total_lines for dup in dups)

        metrics.maintainability_index = self._compute_maintainability_index(metrics)

        return metrics

    def _analyze_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        file_path: str,
        content: str,
    ) -> FunctionMetrics:
        """Analyze a single function/method."""
        lines = content.split("\n")[node.lineno - 1:node.end_lineno]

        func = FunctionMetrics(
            name=node.name,
            file_path=file_path,
            start_line=node.lineno,
            end_line=node.end_lineno,
            lines=node.end_lineno - node.lineno + 1,
            is_async=isinstance(node, ast.AsyncFunctionDef),
            has_decorators=len(node.decorator_list) > 0,
        )

        for line in lines:
            stripped = line.strip()
            if not stripped:
                func.blank_lines += 1
            elif stripped.startswith("#"):
                func.comment_lines += 1

        func.argument_count = len(node.args.args) + len(node.args.kwonlyargs)
        if node.args.vararg:
            func.argument_count += 1
        if node.args.kwarg:
            func.argument_count += 1

        local_vars: set[str] = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                local_vars.add(child.id)
        func.local_variable_count = len(local_vars)

        func.cyclomatic_complexity = self._compute_cyclomatic(node)
        func.decision_points = func.cyclomatic_complexity - 1

        func.max_nesting = self._compute_nesting_depth(node)
        func.nesting_depth = func.max_nesting

        func.return_count = len([
            child for child in ast.walk(node)
            if isinstance(child, (ast.Return, ast.Yield, ast.YieldFrom))
        ])
        func.is_generator = any(
            isinstance(child, (ast.Yield, ast.YieldFrom))
            for child in ast.walk(node)
        )

        func.branch_count = len([
            child for child in ast.walk(node)
            if isinstance(child, (ast.If, ast.IfExp))
        ])
        func.loop_count = len([
            child for child in ast.walk(node)
            if isinstance(child, (ast.For, ast.While))
        ])

        func.cognitive_complexity = self._compute_cognitive_complexity(node)

        halstead = self._compute_halstead(node)
        func.halstead_length = halstead["length"]
        func.halstead_vocabulary = halstead["vocabulary"]
        func.halstead_volume = halstead["volume"]
        func.halstead_difficulty = halstead["difficulty"]
        func.halstead_effort = halstead["effort"]
        func.halstead_time = halstead["time"]
        func.halstead_bugs = halstead["bugs"]

        func.is_recursive = self._is_recursive(node)

        return func

    def _compute_cyclomatic(self, node: ast.AST) -> int:
        """Compute McCabe cyclomatic complexity."""
        complexity = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                complexity += 1
            elif isinstance(child, ast.With):
                complexity += len(child.items)
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
            elif isinstance(child, ast.comprehension):
                complexity += 1
                if child.ifs:
                    complexity += len(child.ifs)
        return complexity

    def _compute_nesting_depth(self, node: ast.AST) -> int:
        """Compute maximum nesting depth of control structures."""

        def depth(n: ast.AST, current: int = 0) -> int:
            if isinstance(n, (ast.If, ast.For, ast.While, ast.With, ast.Try,
                              ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                              ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
                current += 1

            max_child = current
            for child in ast.iter_child_nodes(n):
                max_child = max(max_child, depth(child, current))
            return max_child

        return max(0, depth(node) - 1)

    def _compute_cognitive_complexity(self, node: ast.AST) -> int:
        """
        Compute cognitive complexity (SonarQube-style).
        """

        def cognitive(n: ast.AST, nesting: int = 0) -> int:
            score = 0

            if isinstance(n, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                score += 1 + nesting
                for child in ast.iter_child_nodes(n):
                    if isinstance(child, (ast.If, ast.While, ast.For, ast.With, ast.Try)):
                        score += cognitive(child, nesting + 1)
                    else:
                        score += cognitive(child, nesting)

            elif isinstance(n, ast.With):
                score += 1 + nesting
                for child in ast.iter_child_nodes(n):
                    score += cognitive(child, nesting)

            elif isinstance(n, ast.BoolOp):
                score += len(n.values) - 1

            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for child in ast.walk(n):
                    if isinstance(child, ast.Call):
                        if isinstance(child.func, ast.Name) and child.func.id == n.name:
                            score += 1

            else:
                for child in ast.iter_child_nodes(n):
                    score += cognitive(child, nesting)

            return score

        return cognitive(node)

    def _compute_halstead(self, node: ast.AST) -> dict[str, float]:
        """Compute Halstead software science metrics."""
        operators: Counter = Counter()
        operands: Counter = Counter()

        for child in ast.walk(node):
            if isinstance(child, ast.operator):
                operators[type(child).__name__] += 1
            elif isinstance(child, ast.unaryop):
                operators[type(child).__name__] += 1
            elif isinstance(child, ast.cmpop):
                operators[type(child).__name__] += 1
            elif isinstance(child, ast.boolop):
                operators[type(child).__name__] += 1
            elif isinstance(child, ast.Name):
                operands[child.id] += 1
            elif isinstance(child, ast.Constant):
                operands[str(child.value)] += 1

        n1 = len(operators)
        n2 = len(operands)
        N1 = sum(operators.values())
        N2 = sum(operands.values())

        n = n1 + n2
        N = N1 + N2

        if n == 0:
            return {"length": 0, "vocabulary": 0, "volume": 0.0,
                    "difficulty": 0.0, "effort": 0.0, "time": 0.0, "bugs": 0.0}

        volume = N * math.log2(n) if n > 0 else 0.0
        difficulty = (n1 / 2) * (N2 / n2) if n2 > 0 else 0.0
        effort = difficulty * volume
        time = effort / 18
        bugs = volume / 3000

        return {
            "length": N,
            "vocabulary": n,
            "volume": round(volume, 2),
            "difficulty": round(difficulty, 2),
            "effort": round(effort, 2),
            "time": round(time, 2),
            "bugs": round(bugs, 3),
        }

    def _is_recursive(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        """Check if function calls itself."""
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name) and child.func.id == node.name:
                    return True
        return False

    def _track_calls(self, func: FunctionMetrics, node: ast.AST) -> None:
        """Track function calls for fan-in/out analysis."""
        func_key = f"{func.file_path}:{func.name}"

        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    callee = child.func.id
                    func.external_calls.append(callee)
                    func.fan_out += 1
                    self._function_calls[func_key].append(callee)
                    self._function_callers[callee].append(func_key)

    # ─────────────────────────────────────────────────────────────
    # GENERIC FILE ANALYSIS
    # ─────────────────────────────────────────────────────────────

    def _analyze_generic_file(self, file_path: Path, content: str, language: str) -> FileMetrics:
        """Basic analysis for non-Python files."""
        metrics = FileMetrics(file_path=str(file_path), language=language)

        lines = content.split("\n")
        metrics.total_lines = len(lines)
        metrics.blank_lines = sum(1 for l in lines if not l.strip())
        metrics.comment_lines = self._count_comment_lines(lines, language)
        metrics.code_lines = metrics.total_lines - metrics.blank_lines - metrics.comment_lines

        if language in ("javascript", "typescript", "jsx", "tsx"):
            metrics.function_count = len(re.findall(
                r'\bfunction\s+\w+|const\s+\w+\s*=.*=>|async\s+\w+', content
            ))
        elif language in ("go", "rust", "java", "kotlin"):
            metrics.function_count = len(re.findall(
                r'\bfunc\s+\w+|\bfn\s+\w+|\b\w+\s*\([^)]*\)\s*\{', content
            ))

        dups = self.find_duplicates(content, str(file_path))
        metrics.duplicate_blocks = len(dups)
        metrics.duplicate_lines = sum(dup.total_lines for dup in dups)

        return metrics

    def _count_comment_lines(self, lines: list[str], language: str) -> int:
        """Count comment lines for various languages."""
        comment_patterns = {
            "python": r'^\s*#',
            "javascript": r'^\s*//|^\s*/\*',
            "typescript": r'^\s*//|^\s*/\*',
            "go": r'^\s*//',
            "rust": r'^\s*//',
            "java": r'^\s*//|^\s*/\*',
            "c": r'^\s*//|^\s*/\*',
            "cpp": r'^\s*//|^\s*/\*',
        }

        pattern = comment_patterns.get(language, r'^\s*#')
        return sum(1 for l in lines if re.match(pattern, l.strip()))

    # ─────────────────────────────────────────────────────────────
    # TOKENIZATION & DUPLICATION
    # ─────────────────────────────────────────────────────────────

    def _tokenize_python(self, content: str) -> list[Token]:
        """Tokenize Python code using the tokenize module."""
        tokens: list[Token] = []
        try:
            for tok in tokenize.generate_tokens(io.StringIO(content).readline):
                tokens.append(Token(
                    type=tokenize.tok_name.get(tok.type, str(tok.type)),
                    value=tok.string,
                    start_line=tok.start[0],
                    end_line=tok.end[0],
                ))
        except tokenize.TokenError:
            pass
        return tokens

    def _tokenize_generic(self, content: str) -> list[Token]:
        """Simple regex-based tokenization for other languages."""
        pattern = r'([a-zA-Z_]\w*|\d+\.?\d*|"[^"]*"|\'[^\']*\'|//.*|/\*.*?\*/|==|!=|<=|>=|&&|\|\||[+\-*/=<>!&|])'

        tokens: list[Token] = []
        for match in re.finditer(pattern, content, re.DOTALL):
            val = match.group(1)
            newlines = val.count("\n")
            tokens.append(Token(
                type=self._classify_token(val),
                value=val,
                start_line=1,
                end_line=1 + newlines,
            ))

        return tokens

    def _classify_token(self, value: str) -> str:
        """Classify a token for normalization."""
        if value.startswith(('"', "'")):
            return "STRING"
        if value and value[0].isdigit():
            return "NUMBER"
        if value in ("//", "/*", "*/", "#"):
            return "COMMENT"
        if value in ("==", "!=", "<=", ">=", "&&", "||", "+", "-", "*", "/", "=", "<", ">", "!", "&", "|"):
            return "OPERATOR"
        if value in ("(", ")", "{", "}", "[", "]", ";", ",", "."):
            return "PUNCT"
        return "IDENT"

    def _normalize_tokens(self, tokens: list[Token]) -> list[str]:
        """Normalize tokens for duplication detection."""
        normalized: list[str] = []
        for tok in tokens:
            if tok.type == "COMMENT":
                continue
            elif tok.type == "STRING":
                normalized.append("STRING_LITERAL")
            elif tok.type == "NUMBER":
                normalized.append("NUMBER_LITERAL")
            elif tok.type == "IDENT":
                if tok.value in ("if", "else", "for", "while", "return", "def", "class",
                                 "import", "from", "try", "except", "with", "async", "await"):
                    normalized.append(tok.value)
                else:
                    normalized.append("IDENT")
            else:
                normalized.append(tok.value)
        return normalized

    def _hash_tokens(self, tokens: list[str]) -> str:
        """Hash a token sequence for duplicate detection."""
        return hashlib.sha256(" ".join(tokens).encode()).hexdigest()[:16]

    def _merge_positions(self, positions: list[tuple[int, int]]) -> list[tuple[int, int]]:
        """Merge overlapping or adjacent token positions."""
        if not positions:
            return []

        sorted_pos = sorted(positions, key=lambda x: x[0])
        merged: list[list[int]] = [list(sorted_pos[0])]

        for start, end in sorted_pos[1:]:
            last = merged[-1]
            if start <= last[1] + 1:
                last[1] = max(last[1], end)
            else:
                merged.append([start, end])

        return [(m[0], m[1]) for m in merged]

    # ─────────────────────────────────────────────────────────────
    # MAINTAINABILITY INDEX
    # ─────────────────────────────────────────────────────────────

    def _compute_maintainability_index(self, metrics: FileMetrics) -> float:
        """
        Compute Microsoft Maintainability Index (0-100).

        Formula: 171 - 5.2 * ln(Halstead Volume) - 0.23 * CC - 16.2 * ln(Lines)
        """
        if not metrics.functions:
            return 100.0

        total_volume = sum(f.halstead_volume for f in metrics.functions)
        avg_cc = metrics.avg_function_complexity
        lines = metrics.total_lines

        if total_volume <= 0 or lines <= 0:
            return 100.0

        raw_mi = 171 - 5.2 * math.log(total_volume) - 0.23 * avg_cc - 16.2 * math.log(lines)

        return round(max(0, min(100, raw_mi)), 2)

    # ─────────────────────────────────────────────────────────────
    # DEPENDENCY ANALYSIS
    # ─────────────────────────────────────────────────────────────

    def _compute_dependency_metrics(self, project: ProjectMetrics) -> None:
        """Compute fan-in/out for all functions after full project scan."""
        for file_metrics in project.files:
            for func in file_metrics.functions:
                func.fan_in = len(self._function_callers.get(func.name, []))

    # ─────────────────────────────────────────────────────────────
    # LANGUAGE DETECTION
    # ─────────────────────────────────────────────────────────────

    def _detect_language(self, file_path: Path) -> str:
        """Detect programming language from file extension."""
        ext = file_path.suffix.lower()
        mapping = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".jsx": "jsx",
            ".tsx": "tsx",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
            ".kt": "kotlin",
            ".rb": "ruby",
            ".php": "php",
            ".cpp": "cpp",
            ".c": "c",
            ".h": "c",
            ".swift": "swift",
            ".scala": "scala",
        }
        return mapping.get(ext, "unknown")

    # ─────────────────────────────────────────────────────────────
    # REPORTING
    # ─────────────────────────────────────────────────────────────

    def generate_report(self, project: ProjectMetrics) -> str:
        """Generate human-readable complexity report."""
        lines = [
            "# Complexity Analysis Report",
            "",
            f"**Files analyzed:** {len(project.files)}",
            f"**Total lines:** {project.total_lines:,}",
            f"**Total functions:** {project.total_functions}",
            f"**Total classes:** {project.total_classes}",
            "",
            "## Hotspots",
            "",
        ]

        lines.append("### Most Complex Functions")
        for i, func in enumerate(project.most_complex_functions[:10], 1):
            lines.append(
                f"{i}. `{func.name}` in `{func.file_path}:{func.start_line}` "
                f"(CC: {func.cyclomatic_complexity}, "
                f"{func.lines} lines, "
                f"cognitive: {func.cognitive_complexity})"
            )
        lines.append("")

        lines.append("### Largest Functions")
        for i, func in enumerate(project.largest_functions[:10], 1):
            lines.append(
                f"{i}. `{func.name}` in `{func.file_path}:{func.start_line}` "
                f"({func.lines} lines)"
            )
        lines.append("")

        if project.most_duplicated:
            lines.append("### Duplication")
            lines.append(f"Found {len(project.most_duplicated)} duplicated blocks")
            for dup in project.most_duplicated[:5]:
                lines.append(
                    f"- {dup.token_count} tokens in {dup.file_count} files, "
                    f"{len(dup.occurrences)} occurrences"
                )
            lines.append("")

        lines.append("### Complexity Distribution")
        for cc in sorted(project.complexity_histogram.keys()):
            count = project.complexity_histogram[cc]
            bar = "█" * min(count, 50)
            lines.append(f"CC={cc:2d}: {count:4d} {bar}")
        lines.append("")

        return "\n".join(lines)

    def export_json(self, project: ProjectMetrics, path: Path) -> None:
        """Export metrics as JSON."""
        data = {
            "summary": {
                "files": len(project.files),
                "total_lines": project.total_lines,
                "total_functions": project.total_functions,
                "total_classes": project.total_classes,
            },
            "hotspots": {
                "most_complex": [
                    {
                        "name": f.name,
                        "file": f.file_path,
                        "line": f.start_line,
                        "complexity": f.cyclomatic_complexity,
                        "lines": f.lines,
                    }
                    for f in project.most_complex_functions[:20]
                ],
                "largest": [
                    {
                        "name": f.name,
                        "file": f.file_path,
                        "line": f.start_line,
                        "lines": f.lines,
                    }
                    for f in project.largest_functions[:20]
                ],
            },
            "duplication": [
                {
                    "hash": d.hash,
                    "occurrences": len(d.occurrences),
                    "files": d.file_count,
                    "tokens": d.token_count,
                    "total_lines": d.total_lines,
                }
                for d in project.most_duplicated[:20]
            ],
            "complexity_histogram": dict(project.complexity_histogram),
            "files": [
                {
                    "path": f.file_path,
                    "lines": f.total_lines,
                    "functions": f.function_count,
                    "max_complexity": f.max_function_complexity,
                    "avg_complexity": round(f.avg_function_complexity, 2),
                    "maintainability": f.maintainability_index,
                }
                for f in project.files
            ],
        }
        path.write_text(json.dumps(data, indent=2))
