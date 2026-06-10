# ════════════════════════════════════════
# wigent — Code Search
# Role: Advanced codebase search with ripgrep, symbol resolution, and
#        import-graph analysis
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Code intelligence tools — text/regex search, symbol definitions,
references, file symbols, import graphs, and similar‑code discovery."""

from __future__ import annotations

import ast
import json
import logging
import os
import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterator

from wigent.tools._safe_path import resolve_path

logger = logging.getLogger(__name__)

_EXCLUDED_DIRS = frozenset({
    ".git", ".wigent_backups", "__pycache__", "node_modules",
    "venv", ".venv", ".env", ".mypy_cache", ".ruff_cache",
    ".pytest_cache", ".nox", ".tox", "dist", "build", ".next",
    ".eggs", "*.egg-info", ".svn", ".hg", ".bzr",
})

_BINARY_EXTENSIONS = frozenset({
    ".pyc", ".pyo", ".so", ".dll", ".dylib", ".exe", ".bin",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp",
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".mp3", ".mp4", ".avi", ".mov", ".wav", ".flac",
    ".min.js", ".min.css",
})


# ── data types ────────────────────────────────────────────────────────────


@dataclass
class SearchMatch:
    file: str
    line: int
    column: int = 0
    content: str = ""
    context_before: list[str] = field(default_factory=list)
    context_after: list[str] = field(default_factory=list)
    match_type: str = "text"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SymbolDef:
    name: str
    kind: str
    file: str
    line: int
    column: int
    signature: str = ""
    parent: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ImportEdge:
    source: str
    target: str
    line: int
    import_type: str  # "direct" | "from" | "wildcard"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SearchResult:
    success: bool
    matches: list[SearchMatch] = field(default_factory=list)
    count: int = 0
    engine: str = "python"
    error: str | None = None
    timed_out: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "matches": [m.to_dict() for m in self.matches],
            "count": self.count,
            "engine": self.engine,
            "error": self.error,
            "timed_out": self.timed_out,
        }


# ── helpers ───────────────────────────────────────────────────────────────


def _has_ripgrep() -> bool:
    """Check if rg is available and respects .gitignore."""
    try:
        result = subprocess.run(["rg", "--version"], capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _is_binary(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    if ext in _BINARY_EXTENSIONS:
        return True
    if ext == "":
        try:
            with open(path, "rb") as f:
                chunk = f.read(8192)
            return b"\0" in chunk
        except OSError:
            return True
    return False


def _walk_files(root: str) -> Iterator[str]:
    """Yield non-binary file paths, respecting excluded dirs."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _EXCLUDED_DIRS and not d.startswith(".")]
        for fname in filenames:
            fpath = os.path.join(dirpath, fname)
            if _is_binary(fpath):
                continue
            yield fpath


def _read_file(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def _rel_path(path: str) -> str:
    from wigent.config import settings
    try:
        return os.path.relpath(path, settings.workspace_path)
    except ValueError:
        return path


def _collect_context(lines: list[str], line_idx: int, radius: int = 2) -> tuple[list[str], list[str]]:
    before = lines[max(0, line_idx - radius):line_idx]
    after = lines[line_idx + 1:line_idx + 1 + radius]
    return before, after


# ── scoring ───────────────────────────────────────────────────────────────


def _rank_matches(matches: list[SearchMatch], query: str) -> list[SearchMatch]:
    query_lower = query.lower()
    def score(m: SearchMatch) -> int:
        s = 0
        fname = os.path.basename(m.file).lower()
        content_lower = m.content.lower()
        if query_lower in fname:
            s += 100
        word = re.search(rf"\b{re.escape(query_lower)}\b", content_lower)
        if word:
            s += 50
        if content_lower.startswith(query_lower):
            s += 30
        if query_lower in m.content.lower():
            s += len(re.findall(re.escape(query_lower), m.content, re.IGNORECASE)) * 10
        return -s
    matches.sort(key=score)
    return matches


# ── search_codebase ───────────────────────────────────────────────────────


def search_codebase(query: str, root_path: str = ".") -> dict[str, Any]:
    """Full‑text search using ripgrep with context, ranking, and binary skip.

    Args:
        query: Literal string to search for.
        root_path: Directory to search within.

    Returns:
        SearchResult dict with ranked matches, each with file/line/column/context.
    """
    resolved, err = resolve_path(root_path)
    if err:
        return SearchResult(success=False, error=err).to_dict()

    if not os.path.isdir(resolved):
        resolved = os.path.dirname(resolved)

    if _has_ripgrep():
        return _search_with_rg(query, resolved).to_dict()
    else:
        return _search_python(query, resolved).to_dict()


def _search_with_rg(query: str, root: str) -> SearchResult:
    excludes = sum((["--glob", f"!{d}/**"] for d in _EXCLUDED_DIRS), [])
    cmd = [
        "rg", "--line-number", "--column", "--heading", "--no-messages",
        "--context", "2", "--color", "never",
    ] + excludes + [query, root]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return SearchResult(success=False, timed_out=True, error="Search timed out (30s)")

    if result.returncode not in (0, 1):
        return SearchResult(success=False, error=result.stderr.strip() or f"rg exited with {result.returncode}")

    if not result.stdout.strip():
        return SearchResult(success=True, engine="rg")

    return _parse_rg_context_output(result.stdout, root)


def _parse_rg_context_output(output: str, root: str) -> SearchResult:
    matches: list[SearchMatch] = []
    current_file: str | None = None

    for line in output.splitlines():
        if current_file is None and not line.startswith(" "):
            candidate = line.strip()
            if os.path.isfile(candidate):
                current_file = _rel_path(candidate)
                continue

        if line.startswith("--"):
            current_file = None
            continue

        if current_file and line.startswith(" "):
            continue

        if current_file and ":" in line:
            parts = line.split(":", 2)
            if len(parts) >= 3 and parts[0].isdigit() and parts[1].isdigit():
                matches.append(SearchMatch(
                    file=current_file,
                    line=int(parts[0]),
                    column=int(parts[1]),
                    content=parts[2].strip(),
                ))

    matches = _rank_matches(matches, "")
    return SearchResult(success=True, matches=matches, count=len(matches), engine="rg")


def _search_python(query: str, root: str) -> SearchResult:
    matches: list[SearchMatch] = []
    query_lower = query.lower()

    for fpath in _walk_files(root):
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except OSError:
            continue

        for i, line in enumerate(lines):
            if query.lower() in line.lower():
                before, after = _collect_context(lines, i)
                matches.append(SearchMatch(
                    file=_rel_path(fpath),
                    line=i + 1,
                    column=line.lower().index(query_lower) + 1,
                    content=line.rstrip(),
                    context_before=[l.rstrip() for l in before],
                    context_after=[l.rstrip() for l in after],
                ))

    matches = _rank_matches(matches, query)
    return SearchResult(success=True, matches=matches, count=len(matches), engine="python")


# ── search_by_pattern (regex) ─────────────────────────────────────────────


def search_by_pattern(pattern: str, root_path: str = ".") -> dict[str, Any]:
    """Regex search across codebase with context.

    Args:
        pattern: Python regex pattern.
        root_path: Directory to search.

    Returns:
        SearchResult dict.
    """
    resolved, err = resolve_path(root_path)
    if err:
        return SearchResult(success=False, error=err).to_dict()
    if not os.path.isdir(resolved):
        resolved = os.path.dirname(resolved)

    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        return SearchResult(success=False, error=f"Invalid regex: {exc}").to_dict()

    if _has_ripgrep():
        return _search_regex_rg(compiled, resolved).to_dict()

    matches: list[SearchMatch] = []
    for fpath in _walk_files(resolved):
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except OSError:
            continue
        for i, line in enumerate(lines):
            m = compiled.search(line)
            if m:
                before, after = _collect_context(lines, i)
                matches.append(SearchMatch(
                    file=_rel_path(fpath),
                    line=i + 1,
                    column=m.start() + 1,
                    content=line.rstrip(),
                    context_before=[l.rstrip() for l in before],
                    context_after=[l.rstrip() for l in after],
                ))

    return SearchResult(success=True, matches=matches, count=len(matches), engine="python").to_dict()


def _search_regex_rg(compiled: re.Pattern, root: str) -> SearchResult:
    excludes = sum((["--glob", f"!{d}/**"] for d in _EXCLUDED_DIRS), [])
    cmd = [
        "rg", "--line-number", "--column", "--heading", "--no-messages",
        "--context", "2", "--color", "never", "--engine", "auto",
    ] + excludes + [compiled.pattern, root]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return SearchResult(success=False, timed_out=True, error="Regex search timed out (30s)")

    if result.returncode not in (0, 1):
        return SearchResult(success=False, error=result.stderr.strip() or f"rg exited with {result.returncode}")

    if not result.stdout.strip():
        return SearchResult(success=True, engine="rg")

    return _parse_rg_context_output(result.stdout, root)


# ── find_definition ───────────────────────────────────────────────────────


def find_definition(symbol: str, root_path: str = ".") -> dict[str, Any]:
    """Find the definition of a symbol (function, class, variable) using AST.

    Args:
        symbol: Name of the symbol to locate.
        root_path: Directory to search.

    Returns:
        Dict with ``definitions`` list (each with file/line/column/kind/signature).
    """
    resolved, err = resolve_path(root_path)
    if err:
        return {"success": False, "definitions": [], "count": 0, "error": err}

    if not os.path.isdir(resolved):
        resolved = os.path.dirname(resolved)

    definitions: list[SymbolDef] = []
    var_pattern = re.compile(rf"^\s*(?:{re.escape(symbol)}\s*[:=]|(?:let|var|const)\s+{re.escape(symbol)}\b)")

    for fpath in _walk_files(resolved):
        if fpath.endswith(".py"):
            defs = _find_definitions_ast(fpath, symbol)
            definitions.extend(defs)
        else:
            source = _read_file(fpath)
            if source is None:
                continue
            lines = source.splitlines()
            for i, line in enumerate(lines):
                m = var_pattern.match(line)
                if m:
                    definitions.append(SymbolDef(
                        name=symbol,
                        kind="variable",
                        file=_rel_path(fpath),
                        line=i + 1,
                        column=m.start() + 1,
                    ))

    return {
        "success": True,
        "definitions": [d.to_dict() for d in definitions],
        "count": len(definitions),
        "error": None,
    }


def _find_definitions_ast(fpath: str, symbol: str) -> list[SymbolDef]:
    source = _read_file(fpath)
    if source is None:
        return []
    try:
        tree = ast.parse(source, filename=fpath)
    except SyntaxError:
        return []

    defs: list[SymbolDef] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == symbol:
            sig = _format_fn_sig(node)
            defs.append(SymbolDef(
                name=node.name,
                kind="async_function" if isinstance(node, ast.AsyncFunctionDef) else "function",
                file=_rel_path(fpath),
                line=node.lineno,
                column=node.col_offset + 1,
                signature=sig,
            ))
        elif isinstance(node, ast.ClassDef) and node.name == symbol:
            defs.append(SymbolDef(
                name=node.name,
                kind="class",
                file=_rel_path(fpath),
                line=node.lineno,
                column=node.col_offset + 1,
                signature=f"class {node.name}(...)" if node.bases else f"class {node.name}",
            ))
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == symbol:
                    defs.append(SymbolDef(
                        name=target.id,
                        kind="variable",
                        file=_rel_path(fpath),
                        line=node.lineno,
                        column=node.col_offset + 1,
                    ))
    return defs


def _format_fn_sig(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args = node.args
    positional = [a.arg for a in args.args]
    kwonly = [a.arg for a in args.kwonlyargs]
    parts = positional[:]
    if args.vararg:
        parts.append(f"*{args.vararg.arg}")
    parts.extend(kwonly)
    if args.kwarg:
        parts.append(f"**{args.kwarg.arg}")
    prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
    return f"{prefix}{node.name}({', '.join(parts)})"


# ── find_references ───────────────────────────────────────────────────────


def find_references(symbol: str, root_path: str = ".") -> dict[str, Any]:
    """Find all references (usages) of a symbol across the codebase.

    Uses ripgrep for non‑definition occurrences. Excludes the definition
    lines themselves.

    Args:
        symbol: Symbol name to search for.
        root_path: Directory to search.

    Returns:
        Dict with ``references`` list (each with file/line/column/context).
    """
    resolved, err = resolve_path(root_path)
    if err:
        return {"success": False, "references": [], "count": 0, "error": err}

    if not os.path.isdir(resolved):
        resolved = os.path.dirname(resolved)

    definitions = find_definition(symbol, root_path)
    def_locations = {(d["file"], d["line"]) for d in definitions.get("definitions", [])}

    search_result = search_codebase(symbol, root_path)
    if not search_result["success"]:
        return {"success": False, "references": [], "count": 0, "error": search_result.get("error")}

    refs = []
    for m in search_result.get("matches", []):
        if (m["file"], m["line"]) not in def_locations:
            refs.append(m)

    return {
        "success": True,
        "references": refs,
        "count": len(refs),
        "definition_count": len(def_locations),
        "error": None,
    }


# ── get_file_symbols ──────────────────────────────────────────────────────


def get_file_symbols(file_path: str) -> dict[str, Any]:
    """List all functions and classes defined in a file.

    Args:
        file_path: Relative or absolute path to a file.

    Returns:
        Dict with ``symbols`` list.
    """
    resolved, err = resolve_path(file_path)
    if err:
        return {"success": False, "symbols": [], "count": 0, "error": err}

    if not os.path.isfile(resolved):
        return {"success": False, "symbols": [], "count": 0, "error": f"Not a file: {file_path}"}

    if resolved.endswith(".py"):
        return _file_symbols_ast(resolved)

    symbols: list[SymbolDef] = []
    source = _read_file(resolved)
    if source is None:
        return {"success": False, "symbols": [], "count": 0, "error": "Could not read file"}

    lines = source.splitlines()
    patterns = [
        (re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)"), "function"),
        (re.compile(r"^\s*(?:export\s+)?class\s+(\w+)"), "class"),
        (re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*="), "variable"),
        (re.compile(r"^\s*(?:export\s+)?(?:def|class)\s+(\w+)"), "definition"),
    ]
    for i, line in enumerate(lines):
        for pat, kind in patterns:
            m = pat.search(line)
            if m:
                symbols.append(SymbolDef(
                    name=m.group(1),
                    kind=kind,
                    file=_rel_path(resolved),
                    line=i + 1,
                    column=m.start() + 1,
                ))
                break

    return {
        "success": True,
        "symbols": [s.to_dict() for s in symbols],
        "count": len(symbols),
        "error": None,
    }


def _file_symbols_ast(fpath: str) -> dict[str, Any]:
    source = _read_file(fpath)
    if source is None:
        return {"success": False, "symbols": [], "count": 0, "error": "Could not read file"}
    try:
        tree = ast.parse(source, filename=fpath)
    except SyntaxError as exc:
        return {"success": False, "symbols": [], "count": 0, "error": f"Syntax error: {exc}"}

    symbols: list[SymbolDef] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            sig = _format_fn_sig(node)
            symbols.append(SymbolDef(
                name=node.name,
                kind="async_function" if isinstance(node, ast.AsyncFunctionDef) else "function",
                file=_rel_path(fpath),
                line=node.lineno,
                column=node.col_offset + 1,
                signature=sig,
            ))
            _walk_methods(node, symbols, fpath)
        elif isinstance(node, ast.ClassDef):
            symbols.append(SymbolDef(
                name=node.name,
                kind="class",
                file=_rel_path(fpath),
                line=node.lineno,
                column=node.col_offset + 1,
                signature=f"class {node.name}(...)" if node.bases else f"class {node.name}",
            ))
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    sig = _format_fn_sig(item)
                    symbols.append(SymbolDef(
                        name=item.name,
                        kind="method",
                        file=_rel_path(fpath),
                        line=item.lineno,
                        column=item.col_offset + 1,
                        signature=sig,
                        parent=node.name,
                    ))

    return {
        "success": True,
        "symbols": [s.to_dict() for s in symbols],
        "count": len(symbols),
        "error": None,
    }


def _walk_methods(node: ast.FunctionDef | ast.AsyncFunctionDef, symbols: list[SymbolDef], fpath: str) -> None:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            sig = _format_fn_sig(child)
            symbols.append(SymbolDef(
                name=child.name,
                kind="nested_function",
                file=_rel_path(fpath),
                line=child.lineno,
                column=child.col_offset + 1,
                signature=sig,
                parent=node.name,
            ))


# ── get_imports_graph ─────────────────────────────────────────────────────


def get_imports_graph(root_path: str = ".") -> dict[str, Any]:
    """Build an import dependency graph for the project.

    Parses all Python files and extracts their imports, then returns a
    graph structure with nodes and edges.

    Args:
        root_path: Project root directory.

    Returns:
        Dict with ``nodes`` (unique modules), ``edges`` (ImportEdge list),
        ``orphans`` (modules with no imports), ``hub_modules`` (most imported).
    """
    resolved, err = resolve_path(root_path)
    if err:
        return {"success": False, "nodes": [], "edges": [], "error": err}

    if not os.path.isdir(resolved):
        resolved = os.path.dirname(resolved)

    edges: list[ImportEdge] = []
    module_files: dict[str, str] = {}
    import_count: dict[str, int] = defaultdict(int)

    for fpath in _walk_files(resolved):
        if not fpath.endswith(".py"):
            continue
        source = _read_file(fpath)
        if source is None:
            continue

        try:
            tree = ast.parse(source, filename=fpath)
        except SyntaxError:
            continue

        source_mod = _file_to_module(fpath, resolved)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target = alias.name.split(".")[0] if alias.name else ""
                    if target:
                        edges.append(ImportEdge(
                            source=source_mod,
                            target=target,
                            line=node.lineno,
                            import_type="direct",
                        ))
                        import_count[target] += 1
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    target = node.module.split(".")[0]
                    if target:
                        edges.append(ImportEdge(
                            source=source_mod,
                            target=target,
                            line=node.lineno,
                            import_type="from",
                        ))
                        import_count[target] += 1

        module_files[source_mod] = fpath

    nodes_set = set()
    for e in edges:
        nodes_set.add(e.source)
        nodes_set.add(e.target)

    nodes = sorted(nodes_set)
    orphans = [n for n in nodes if n not in import_count]

    sorted_imports = sorted(import_count.items(), key=lambda x: -x[1])
    hub_modules = [{"module": m, "imported_by": c} for m, c in sorted_imports[:10]]

    return {
        "success": True,
        "nodes": nodes,
        "edges": [e.to_dict() for e in edges],
        "orphans": orphans,
        "hub_modules": hub_modules,
        "total_files": len(module_files),
        "total_edges": len(edges),
        "error": None,
    }


def _file_to_module(fpath: str, root: str) -> str:
    rel = os.path.relpath(fpath, root)
    mod = rel.replace(os.sep, "/").removesuffix(".py").removesuffix("/__init__")
    mod = mod.replace("/", ".")
    return mod


# ── find_similar_code ─────────────────────────────────────────────────────


def find_similar_code(snippet: str, root_path: str = ".") -> dict[str, Any]:
    """Find code blocks similar to a given snippet using token‑frequency ranking.

    Tokenises the snippet and the codebase files, then ranks by Jaccard
    similarity of token sets.

    Args:
        snippet: Code snippet text to match.
        root_path: Directory to search.

    Returns:
        Dict with ``results`` ranked by similarity.
    """
    resolved, err = resolve_path(root_path)
    if err:
        return {"success": False, "results": [], "count": 0, "error": err}

    if not os.path.isdir(resolved):
        resolved = os.path.dirname(resolved)

    snippet_tokens = _tokenise(snippet)
    if not snippet_tokens:
        return {"success": False, "results": [], "count": 0, "error": "Snippet is empty or yields no tokens"}

    scored: list[tuple[float, str, int, str]] = []

    for fpath in _walk_files(resolved):
        source = _read_file(fpath)
        if source is None:
            continue
        lines = source.splitlines()

        for i, line in enumerate(lines):
            line_tokens = _tokenise(line.strip())
            if not line_tokens:
                continue
            intersection = len(snippet_tokens & line_tokens)
            union = len(snippet_tokens | line_tokens)
            similarity = intersection / union if union > 0 else 0.0
            if similarity > 0.15:
                scored.append((similarity, _rel_path(fpath), i + 1, line.strip()))

    scored.sort(key=lambda x: -x[0])

    results = [
        {"file": f, "line": l, "similarity": round(s, 4), "content": c}
        for s, f, l, c in scored[:50]
    ]

    return {
        "success": True,
        "results": results,
        "count": len(results),
        "snippet_tokens": len(snippet_tokens),
        "error": None,
    }


def _tokenise(text: str) -> set[str]:
    tokens = set()
    for match in re.finditer(r"[A-Za-z_]\w*", text):
        tokens.add(match.group().lower())
    return tokens


__all__ = [
    "search_codebase",
    "search_by_pattern",
    "find_definition",
    "find_references",
    "get_file_symbols",
    "get_imports_graph",
    "find_similar_code",
    "SearchMatch",
    "SearchResult",
    "SymbolDef",
    "ImportEdge",
]
