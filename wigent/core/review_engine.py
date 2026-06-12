"""
Review Engine — Chunking, Orchestration & Finding Aggregation

The brain behind the Reviewer mode. Handles:
- Intelligent code chunking (~100 lines with context awareness)
- Finding deduplication and cross-referencing
- Review state management for large PRs
- Integration with git blame for author attribution

This is the programmatic core. The Reviewer mode is the CLI wrapper.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Optional

class ChunkStrategy(Enum):
    """How to split code into reviewable chunks."""
    FIXED_LINES = auto()      # Simple ~100 line blocks
    AST_BOUNDARIES = auto()   # Respect function/class boundaries
    SEMANTIC = auto()         # Group related logic (imports, tests, etc.)
    HYBRID = auto()           # AST-aware with fallback to fixed


@dataclass
class CodeRange:
    """A range of code with metadata."""
    start_line: int
    end_line: int
    content: str
    ast_node_type: Optional[str] = None
    parent_context: Optional[str] = None
    is_new: bool = True
    change_type: str = "added"


@dataclass
class ReviewChunk:
    """A chunk ready for review."""
    file_path: str
    start_line: int
    end_line: int
    content: str
    language: Optional[str] = None
    strategy: ChunkStrategy = ChunkStrategy.FIXED_LINES
    is_new: bool = True
    change_type: str = "added"

    imports: list[str] = field(default_factory=list)
    function_signatures: list[str] = field(default_factory=list)
    class_context: Optional[str] = None
    preceding_context: str = ""
    following_context: str = ""

    findings: list["ReviewFinding"] = field(default_factory=list)
    chunk_hash: str = ""

    def __post_init__(self):
        if not self.chunk_hash:
            self.chunk_hash = hashlib.sha256(
                f"{self.file_path}:{self.start_line}:{self.content}".encode()
            ).hexdigest()[:16]

    @property
    def line_count(self) -> int:
        return self.end_line - self.start_line + 1


@dataclass
class ReviewFinding:
    """A single review finding."""
    severity: "ReviewSeverity"
    axis: "ReviewAxis"
    file_path: str
    line_number: int
    message: str
    suggestion: Optional[str] = None
    cwe: Optional[str] = None
    code_snippet: str = ""

    chunk_hash: str = ""
    chunk_start: int = 0
    chunk_end: int = 0
    author: Optional[str] = None
    commit_hash: Optional[str] = None

    related_findings: list[str] = field(default_factory=list)

    @property
    def unique_id(self) -> str:
        return hashlib.sha256(
            f"{self.file_path}:{self.line_number}:{self.message[:50]}".encode()
        ).hexdigest()[:16]


@dataclass
class FileChange:
    """A single file's changes from a git diff."""
    file_path: str
    change_type: str
    old_path: Optional[str] = None
    hunks: list[CodeRange] = field(default_factory=list)
    language: Optional[str] = None


class ReviewEngine:
    """
    Core engine for code review preparation and aggregation.

    Stateless — all state passed through data structures. Thread-safe
    for parallel review of multiple chunks.
    """

    LANGUAGE_MAP = {
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
        ".r": "r",
        ".sql": "sql",
        ".md": "markdown",
        ".yml": "yaml",
        ".yaml": "yaml",
        ".json": "json",
        ".toml": "toml",
        ".sh": "bash",
        ".dockerfile": "dockerfile",
    }

    def __init__(
        self,
        max_chunk_lines: int = 100,
        context_lines: int = 5,
        strategy: ChunkStrategy = ChunkStrategy.HYBRID,
    ):
        self.max_chunk_lines = max_chunk_lines
        self.context_lines = context_lines
        self.strategy = strategy

        self._parsers: dict[str, Parser] = {}
        self._languages: dict[str, Language] = {}

    # ─────────────────────────────────────────────────────────────
    # CHUNKING: FILE → REVIEWABLE CHUNKS
    # ─────────────────────────────────────────────────────────────

    def chunk_file(
        self,
        content: str,
        file_path: str,
        strategy: Optional[ChunkStrategy] = None,
    ) -> list[ReviewChunk]:
        strategy = strategy or self.strategy
        language = self._detect_language(file_path)

        if strategy == ChunkStrategy.FIXED_LINES:
            return self._chunk_fixed(content, file_path, language)

        elif strategy == ChunkStrategy.AST_BOUNDARIES:
            if language == "python":
                return self._chunk_ast_python(content, file_path)
            else:
                return self._chunk_fixed(content, file_path, language)

        elif strategy == ChunkStrategy.SEMANTIC:
            return self._chunk_semantic(content, file_path, language)

        elif strategy == ChunkStrategy.HYBRID:
            if language == "python":
                ast_chunks = self._chunk_ast_python(content, file_path)
                return self._split_oversized(ast_chunks)
            else:
                return self._chunk_fixed(content, file_path, language)

        return self._chunk_fixed(content, file_path, language)

    def chunk_diff(
        self,
        file_change: FileChange,
        strategy: Optional[ChunkStrategy] = None,
    ) -> list[ReviewChunk]:
        chunks = []

        for hunk in file_change.hunks:
            expanded_start = max(1, hunk.start_line - self.context_lines)
            expanded_end = hunk.end_line + self.context_lines

            if hunk.end_line - hunk.start_line + 1 > self.max_chunk_lines:
                sub_hunks = self._split_hunk(hunk)
                for sub in sub_hunks:
                    chunk = ReviewChunk(
                        file_path=file_change.file_path,
                        start_line=sub.start_line,
                        end_line=sub.end_line,
                        content=sub.content,
                        language=file_change.language,
                        strategy=strategy or self.strategy,
                        is_new=sub.is_new,
                    )
                    chunks.append(chunk)
            else:
                chunk = ReviewChunk(
                    file_path=file_change.file_path,
                    start_line=expanded_start,
                    end_line=expanded_end,
                    content=hunk.content,
                    language=file_change.language,
                    strategy=strategy or self.strategy,
                    is_new=hunk.is_new,
                )
                chunks.append(chunk)

        return self._enrich_chunks(chunks)

    # ─────────────────────────────────────────────────────────────
    # CHUNKING STRATEGIES
    # ─────────────────────────────────────────────────────────────

    def _chunk_fixed(
        self,
        content: str,
        file_path: str,
        language: Optional[str],
    ) -> list[ReviewChunk]:
        """Simple fixed-size chunking with overlap."""
        lines = content.split("\n")
        chunks = []

        overlap = 10
        step = self.max_chunk_lines - overlap

        i = 0
        while i < len(lines):
            start = max(0, i - overlap) if i > 0 else 0
            end = min(i + self.max_chunk_lines, len(lines))

            chunk_lines = lines[start:end]
            chunk_content = "\n".join(chunk_lines)

            if not chunk_content.strip():
                i += step
                continue

            chunk = ReviewChunk(
                file_path=file_path,
                start_line=start + 1,
                end_line=end,
                content=chunk_content,
                language=language,
                strategy=ChunkStrategy.FIXED_LINES,
                preceding_context="\n".join(lines[max(0, start - self.context_lines):start]) if start > 0 else "",
                following_context="\n".join(lines[end:min(len(lines), end + self.context_lines)]),
            )
            chunks.append(chunk)

            i += step

        return chunks

    def _chunk_ast_python(self, content: str, file_path: str) -> list[ReviewChunk]:
        """AST-aware chunking for Python using tree-sitter."""
        try:
            parser = self._get_parser("python")
            tree = parser.parse(content.encode())
            root = tree.root_node

            chunks = []
            current_chunk_lines: list[str] = []
            current_start = 1

            for child in root.children:
                node_start = child.start_point[0] + 1
                node_end = child.end_point[0] + 1

                node_lines = content.split("\n")[child.start_point[0]:child.end_point[0] + 1]
                node_content = "\n".join(node_lines)

                if current_chunk_lines and \
                   (sum(len(l.split("\n")) for l in current_chunk_lines) + len(node_lines) > self.max_chunk_lines):

                    chunk_content = "\n".join(current_chunk_lines)
                    chunk_end = current_start + len(current_chunk_lines) - 1

                    chunks.append(ReviewChunk(
                        file_path=file_path,
                        start_line=current_start,
                        end_line=chunk_end,
                        content=chunk_content,
                        language="python",
                        strategy=ChunkStrategy.AST_BOUNDARIES,
                    ))

                    current_chunk_lines = self._get_overlap_lines(current_chunk_lines)
                    current_start = chunk_end - len(current_chunk_lines) + 1

                current_chunk_lines.extend(node_lines)

            if current_chunk_lines:
                chunks.append(ReviewChunk(
                    file_path=file_path,
                    start_line=current_start,
                    end_line=current_start + len(current_chunk_lines) - 1,
                    content="\n".join(current_chunk_lines),
                    language="python",
                    strategy=ChunkStrategy.AST_BOUNDARIES,
                ))

            return chunks

        except Exception:
            return self._chunk_fixed(content, file_path, "python")

    def _chunk_semantic(
        self,
        content: str,
        file_path: str,
        language: Optional[str],
    ) -> list[ReviewChunk]:
        """Semantic grouping: imports, constants, classes, functions, tests."""
        lines = content.split("\n")
        chunks = []

        sections = self._identify_sections(lines, language)

        for section in sections:
            if section.end_line - section.start_line + 1 <= self.max_chunk_lines:
                chunks.append(ReviewChunk(
                    file_path=file_path,
                    start_line=section.start_line,
                    end_line=section.end_line,
                    content="\n".join(lines[section.start_line - 1:section.end_line]),
                    language=language,
                    strategy=ChunkStrategy.SEMANTIC,
                    ast_node_type=section.ast_node_type,
                ))
            else:
                sub_chunks = self._split_section(section, lines, file_path, language)
                chunks.extend(sub_chunks)

        return chunks

    def _identify_sections(
        self,
        lines: list[str],
        language: Optional[str],
    ) -> list[CodeRange]:
        """Identify semantic sections in code."""
        sections: list[CodeRange] = []
        current_section: Optional[CodeRange] = None

        patterns = {
            "import": r'^(import |from \w+ import)',
            "class": r'^class\s+\w+',
            "function": r'^(def\s+\w+|async\s+def\s+\w+)',
            "test": r'^(def\s+test_|class\s+Test)',
            "constant": r'^[A-Z_]+\s*=',
            "decorator": r'^@',
        }

        for i, line in enumerate(lines, 1):
            matched = False

            for section_type, pattern in patterns.items():
                if re.match(pattern, line.strip()):
                    if current_section:
                        current_section.end_line = i - 1
                        sections.append(current_section)

                    current_section = CodeRange(
                        start_line=i,
                        end_line=i,
                        content="",
                        ast_node_type=section_type,
                    )
                    matched = True
                    break

            if not matched and current_section:
                current_section.end_line = i

        if current_section:
            sections.append(current_section)

        sections = self._merge_decorators(sections)

        return sections

    def _merge_decorators(self, sections: list[CodeRange]) -> list[CodeRange]:
        """Attach decorators to their target functions/classes."""
        merged: list[CodeRange] = []
        i = 0
        while i < len(sections):
            if sections[i].ast_node_type == "decorator" and i + 1 < len(sections):
                sections[i + 1].start_line = sections[i].start_line
                i += 1
            else:
                merged.append(sections[i])
                i += 1
        return merged

    # ─────────────────────────────────────────────────────────────
    # CHUNK UTILITIES
    # ─────────────────────────────────────────────────────────────

    def _split_hunk(self, hunk: CodeRange) -> list[CodeRange]:
        """Split a large hunk into smaller reviewable pieces."""
        lines = hunk.content.split("\n")
        sub_hunks: list[CodeRange] = []

        step = self.max_chunk_lines - self.context_lines

        i = 0
        while i < len(lines):
            end = min(i + self.max_chunk_lines, len(lines))
            sub_lines = lines[i:end]

            sub_hunks.append(CodeRange(
                start_line=hunk.start_line + i,
                end_line=hunk.start_line + end - 1,
                content="\n".join(sub_lines),
                is_new=hunk.is_new,
            ))

            i += step

        return sub_hunks

    def _split_oversized(self, chunks: list[ReviewChunk]) -> list[ReviewChunk]:
        """Split chunks that exceed max lines."""
        result: list[ReviewChunk] = []
        for chunk in chunks:
            if chunk.line_count <= self.max_chunk_lines:
                result.append(chunk)
            else:
                sub_chunks = self._chunk_fixed(
                    chunk.content, chunk.file_path, chunk.language
                )
                result.extend(sub_chunks)
        return result

    def _split_section(
        self,
        section: CodeRange,
        lines: list[str],
        file_path: str,
        language: Optional[str],
    ) -> list[ReviewChunk]:
        """Split a large semantic section (e.g., big class)."""
        section_lines = lines[section.start_line - 1:section.end_line]
        content = "\n".join(section_lines)

        sub_chunks = self._chunk_fixed(content, file_path, language)

        for chunk in sub_chunks:
            chunk.start_line += section.start_line - 1
            chunk.end_line += section.start_line - 1
            chunk.strategy = ChunkStrategy.SEMANTIC

        return sub_chunks

    def _get_overlap_lines(self, lines: list[str]) -> list[str]:
        """Get last few lines for overlap context."""
        overlap: list[str] = []
        for line in reversed(lines):
            overlap.insert(0, line)
            if line.strip().startswith(("def ", "class ", "async def ")):
                break
            if len(overlap) >= 10:
                break
        return overlap

    def _enrich_chunks(self, chunks: list[ReviewChunk]) -> list[ReviewChunk]:
        """Add cross-chunk context: imports, signatures, etc."""
        if not chunks:
            return chunks

        first = chunks[0]
        if first.start_line <= 5:
            first.imports = self._extract_imports(first.content)

        for chunk in chunks:
            chunk.function_signatures = self._extract_signatures(chunk.content)

        for i, chunk in enumerate(chunks):
            if i > 0:
                prev_lines = chunks[i - 1].content.split("\n")[-self.context_lines:]
                chunk.preceding_context = "\n".join(prev_lines)
            if i < len(chunks) - 1:
                next_lines = chunks[i + 1].content.split("\n")[:self.context_lines]
                chunk.following_context = "\n".join(next_lines)

        return chunks

    def _extract_imports(self, content: str) -> list[str]:
        """Extract import statements from code."""
        imports: list[str] = []
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")):
                imports.append(stripped)
        return imports

    def _extract_signatures(self, content: str) -> list[str]:
        """Extract function/class signatures for context."""
        sigs: list[str] = []
        for line in content.split("\n"):
            stripped = line.strip()
            if re.match(r'^(def |class |async def )', stripped):
                sigs.append(stripped)
        return sigs

    # ─────────────────────────────────────────────────────────────
    # FINDING AGGREGATION
    # ─────────────────────────────────────────────────────────────

    def aggregate_findings(
        self,
        all_chunks: list[ReviewChunk],
    ) -> dict[str, Any]:
        """
        Aggregate findings across all chunks into actionable report.

        Groups related findings, identifies patterns, suggests batch fixes.
        """
        all_findings: list[ReviewFinding] = []
        for chunk in all_chunks:
            all_findings.extend(chunk.findings)

        by_axis: dict[str, list[ReviewFinding]] = {}
        for f in all_findings:
            axis = f.axis.value
            by_axis.setdefault(axis, []).append(f)

        by_file: dict[str, list[ReviewFinding]] = {}
        for f in all_findings:
            by_file.setdefault(f.file_path, []).append(f)

        patterns = self._find_patterns(all_findings)

        hot_spots = sorted(
            [(path, len(findings)) for path, findings in by_file.items()],
            key=lambda x: x[1],
            reverse=True,
        )[:5]

        return {
            "total_findings": len(all_findings),
            "by_axis": {k: len(v) for k, v in by_axis.items()},
            "by_file": {k: len(v) for k, v in by_file.items()},
            "patterns": patterns,
            "hot_spots": hot_spots,
            "critical_count": sum(
                1 for f in all_findings
                if f.severity.name in ("CRITICAL", "MAJOR")
            ),
        }

    def _find_patterns(self, findings: list[ReviewFinding]) -> list[dict]:
        """Find repeated issues that suggest systemic problems."""
        patterns: list[dict] = []

        message_groups: dict[str, list[ReviewFinding]] = {}
        for f in findings:
            normalized = re.sub(r'\b\d+\b', 'N', f.message.lower())
            normalized = re.sub(r'[^\w\s]', '', normalized)
            key = normalized[:50]

            message_groups.setdefault(key, []).append(f)

        for key, group in message_groups.items():
            if len(group) >= 3:
                patterns.append({
                    "description": group[0].message,
                    "occurrences": len(group),
                    "files": list(set(f.file_path for f in group)),
                    "axis": group[0].axis.value,
                    "suggested_batch_fix": group[0].suggestion,
                })

        return patterns

    # ─────────────────────────────────────────────────────────────
    # CROSS-REFERENCE & DEDUPLICATION
    # ─────────────────────────────────────────────────────────────

    def deduplicate_findings(
        self,
        findings: list[ReviewFinding],
        threshold: float = 0.85,
    ) -> list[ReviewFinding]:
        """
        Remove near-duplicate findings using message similarity.
        """
        unique: list[ReviewFinding] = []

        for f in findings:
            is_duplicate = False
            for u in unique:
                if self._finding_similarity(f, u) >= threshold:
                    if f.severity.value < u.severity.value:
                        u.severity = f.severity
                    is_duplicate = True
                    break

            if not is_duplicate:
                unique.append(f)

        return unique

    def _finding_similarity(self, a: ReviewFinding, b: ReviewFinding) -> float:
        """Calculate similarity between two findings."""
        if a.file_path == b.file_path and abs(a.line_number - b.line_number) <= 3:
            location_score = 0.5
        else:
            location_score = 0.0

        msg_sim = self._string_similarity(a.message, b.message)

        axis_bonus = 0.1 if a.axis == b.axis else 0.0

        return min(1.0, location_score + msg_sim + axis_bonus)

    def _string_similarity(self, a: str, b: str) -> float:
        """Simple Jaccard similarity for strings."""
        set_a = set(a.lower().split())
        set_b = set(b.lower().split())

        if not set_a or not set_b:
            return 0.0

        intersection = len(set_a & set_b)
        union = len(set_a | set_b)

        return intersection / union if union > 0 else 0.0

    def cross_reference_findings(
        self,
        findings: list[ReviewFinding],
    ) -> list[ReviewFinding]:
        """Link related findings across chunks/files."""
        for i, f1 in enumerate(findings):
            for f2 in findings[i + 1:]:
                if f1.file_path == f2.file_path and abs(f1.line_number - f2.line_number) <= 5:
                    if f1.unique_id not in f2.related_findings:
                        f2.related_findings.append(f1.unique_id)
                    if f2.unique_id not in f1.related_findings:
                        f1.related_findings.append(f2.unique_id)

        return findings

    # ─────────────────────────────────────────────────────────────
    # GIT INTEGRATION
    # ─────────────────────────────────────────────────────────────

    def annotate_with_blame(
        self,
        findings: list[ReviewFinding],
        git_tool: Any,
    ) -> list[ReviewFinding]:
        """Add author/commit info to findings via git blame."""
        by_file: dict[str, list[ReviewFinding]] = {}
        for f in findings:
            by_file.setdefault(f.file_path, []).append(f)

        for file_path, file_findings in by_file.items():
            try:
                blame_info = git_tool.blame_lines(file_path)
                for f in file_findings:
                    line_blame = blame_info.get(f.line_number, {})
                    f.author = line_blame.get("author")
                    f.commit_hash = line_blame.get("commit")
            except Exception:
                pass

        return findings

    # ─────────────────────────────────────────────────────────────
    # LANGUAGE DETECTION
    # ─────────────────────────────────────────────────────────────

    def _detect_language(self, file_path: str) -> Optional[str]:
        """Detect programming language from file path."""
        path = Path(file_path)
        ext = path.suffix.lower()

        if path.name == "Dockerfile":
            return "dockerfile"
        if path.name.endswith(".dockerfile"):
            return "dockerfile"
        if path.name == "Makefile":
            return "makefile"

        return self.LANGUAGE_MAP.get(ext)

    def _get_parser(self, language: str) -> "Parser":
        """Get or create tree-sitter parser for language."""
        if language not in self._parsers:
            if language == "python":
                from tree_sitter import Language, Parser
                import tree_sitter_python as tspython
                lang = Language(tspython.language())
                parser = Parser(lang)
                self._parsers[language] = parser
                self._languages[language] = lang
            else:
                raise ValueError(f"Parser not available for: {language}")

        return self._parsers[language]

    # ─────────────────────────────────────────────────────────────
    # BATCH OPERATIONS
    # ─────────────────────────────────────────────────────────────

    def prepare_batch_review(
        self,
        file_changes: list[FileChange],
    ) -> list[ReviewChunk]:
        """Prepare all chunks for a batch review of multiple files."""
        all_chunks: list[ReviewChunk] = []

        for change in file_changes:
            if change.change_type == "deleted":
                continue

            chunks = self.chunk_diff(change)
            all_chunks.extend(chunks)

        all_chunks.sort(key=lambda c: (c.file_path, c.start_line))

        return all_chunks

    def estimate_review_cost(self, chunks: list[ReviewChunk]) -> dict[str, Any]:
        """Estimate token cost for reviewing all chunks."""
        total_lines = sum(c.line_count for c in chunks)
        total_chars = sum(len(c.content) for c in chunks)

        estimated_tokens = total_chars // 4

        total_reviews = len(chunks) * 5

        input_cost = (estimated_tokens * total_reviews * 3) / 1_000_000
        output_cost = (estimated_tokens * total_reviews * 0.3 * 15) / 1_000_000

        return {
            "chunks": len(chunks),
            "total_lines": total_lines,
            "estimated_input_tokens": estimated_tokens * total_reviews,
            "estimated_output_tokens": int(estimated_tokens * total_reviews * 0.3),
            "estimated_cost_usd": round(input_cost + output_cost, 4),
        }


# ─────────────────────────────────────────────────────────────────
# DIFF PARSING
# ─────────────────────────────────────────────────────────────────

class DiffParser:
    """Parse git diff output into structured FileChange objects."""

    def parse(self, diff_text: str) -> list[FileChange]:
        """Parse unified diff format."""
        if not diff_text.strip():
            return []

        changes: list[FileChange] = []
        current_file: Optional[FileChange] = None
        current_hunk: Optional[CodeRange] = None

        lines = diff_text.split("\n")
        i = 0

        while i < len(lines):
            line = lines[i]

            if line.startswith("diff --git"):
                if current_file:
                    if current_hunk:
                        current_file.hunks.append(current_hunk)
                    changes.append(current_file)

                match = re.match(r'diff --git a/(.+) b/(.+)', line)
                if match:
                    old_path, new_path = match.groups()
                    current_file = FileChange(
                        file_path=new_path,
                        change_type="modified",
                        old_path=old_path,
                    )
                    current_hunk = None

            elif line.startswith("new file mode"):
                if current_file:
                    current_file.change_type = "added"

            elif line.startswith("deleted file mode"):
                if current_file:
                    current_file.change_type = "deleted"

            elif line.startswith("rename from"):
                if current_file:
                    current_file.change_type = "renamed"

            elif line.startswith("@@"):
                if current_file and current_hunk:
                    current_file.hunks.append(current_hunk)

                match = re.match(r'@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@', line)
                if match and current_file:
                    start = int(match.group(1))
                    count = int(match.group(2)) if match.group(2) else 1
                    current_hunk = CodeRange(
                        start_line=start,
                        end_line=start + count - 1,
                        content="",
                        is_new=True,
                    )

            elif current_hunk and line.startswith(("+", "-", " ")):
                if current_hunk.content:
                    current_hunk.content += "\n"
                current_hunk.content += line

            i += 1

        if current_file:
            if current_hunk:
                current_file.hunks.append(current_hunk)
            changes.append(current_file)

        engine = ReviewEngine()
        for change in changes:
            change.language = engine._detect_language(change.file_path)

        return changes
