# ════════════════════════════════════════
# wigent — AST Analyzer
# Role: Python source code analysis via the builtin ``ast`` module
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Python‑specific code analysis using the builtin AST parser.

Provides function/class listings, import extraction, complexity
calculation, and docstring harvesting for any Python file."""

from __future__ import annotations

import ast
import logging
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from typing import Any

from wigent.tools._safe_path import resolve_path

logger = logging.getLogger(__name__)


# ── data types ────────────────────────────────────────────────────────────


@dataclass
class FunctionInfo:
    name: str
    lineno: int
    end_lineno: int
    col_offset: int
    decorators: list[str] = field(default_factory=list)
    args: list[str] = field(default_factory=list)
    returns: str | None = None
    is_async: bool = False
    is_method: bool = False
    parent_class: str | None = None
    complexity: int = 1
    docstring: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ClassInfo:
    name: str
    lineno: int
    end_lineno: int
    col_offset: int
    bases: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)
    methods: list[FunctionInfo] = field(default_factory=list)
    docstring: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "methods": [m.to_dict() for m in self.methods],
            "method_count": len(self.methods),
        }


@dataclass
class ImportInfo:
    module: str
    names: list[str] = field(default_factory=list)
    alias: str | None = None
    lineno: int = 0
    import_type: str = "direct"  # "direct" | "from"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DocstringInfo:
    file: str
    lineno: int
    parent: str | None  # function/class/module name
    parent_type: str     # "module" | "function" | "class" | "method"
    text: str
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── helpers ───────────────────────────────────────────────────────────────


def _read_source(fpath: str) -> tuple[str | None, str | None]:
    try:
        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
            return f.read(), None
    except OSError as exc:
        return None, str(exc)


def _parse(source: str, fpath: str) -> tuple[ast.Module | None, str | None]:
    try:
        return ast.parse(source, filename=fpath), None
    except SyntaxError as exc:
        return None, f"Syntax error in {fpath}: {exc}"


def _get_docstring(node: ast.AST) -> str | None:
    doc = ast.get_docstring(node, clean=False)
    return doc if doc else None


def _summarise_docstring(doc: str | None) -> str:
    if not doc:
        return ""
    first_line = doc.strip().split("\n")[0]
    return first_line[:120]


def _collect_decorators(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> list[str]:
    decos: list[str] = []
    for d in node.decorator_list:
        if isinstance(d, ast.Name):
            decos.append(d.id)
        elif isinstance(d, ast.Attribute):
            decos.append(f"{_attr_name(d)}")
        elif isinstance(d, ast.Call):
            if isinstance(d.func, ast.Name):
                decos.append(f"{d.func.id}(...)")
            elif isinstance(d.func, ast.Attribute):
                decos.append(f"{_attr_name(d.func)}(...)")
    return decos


def _attr_name(node: ast.Attribute) -> str:
    parts: list[str] = [node.attr]
    current = node.value
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts))


# ── cyclomatic complexity ─────────────────────────────────────────────────


_COMPLEXITY_NODES = (
    ast.If,
    ast.While,
    ast.For,
    ast.AsyncFor,
    ast.And,
    ast.Or,
    ast.Try,
    ast.ExceptHandler,
    ast.With,
    ast.AsyncWith,
    ast.Assert,
    ast.Raise,
    ast.Return,
    ast.Continue,
    ast.Break,
)


def _cyclomatic_complexity(node: ast.AST) -> int:
    count = 0
    for child in ast.walk(node):
        if isinstance(child, _COMPLEXITY_NODES):
            count += 1
        elif isinstance(child, ast.IfExp):
            count += 1
        elif isinstance(child, ast.BoolOp):
            count += len(child.values) - 1
    return max(1, count)


# ── parse_file ────────────────────────────────────────────────────────────


def parse_file(path: str) -> dict[str, Any]:
    """Parse a Python file and return full AST analysis.

    Args:
        path: Relative or absolute path to a Python file.

    Returns:
        Dict with functions, classes, imports, complexity, docstrings,
        and file metadata.
    """
    resolved, err = resolve_path(path)
    if err:
        return {"success": False, "error": err}

    if not os.path.isfile(resolved):
        return {"success": False, "error": f"Not a file: {path}"}
    if not resolved.endswith(".py"):
        return {"success": False, "error": f"Not a Python file: {path}"}

    source, err = _read_source(resolved)
    if err:
        return {"success": False, "error": err}

    tree, err = _parse(source, resolved)
    if err:
        return {"success": False, "error": err}

    rel_path = _rel_path(resolved)
    functions = _extract_functions(tree)
    classes = _extract_classes(tree)
    imports = _extract_imports(tree)
    docstrings = _extract_docstrings(source, rel_path)

    file_complexity = _cyclomatic_complexity(tree)
    total_lines = len(source.splitlines())
    loc = sum(1 for l in source.splitlines() if l.strip() and not l.strip().startswith("#"))

    return {
        "success": True,
        "file": rel_path,
        "total_lines": total_lines,
        "lines_of_code": loc,
        "file_complexity": file_complexity,
        "functions": [f.to_dict() for f in functions],
        "function_count": len(functions),
        "classes": [c.to_dict() for c in classes],
        "class_count": len(classes),
        "imports": [i.to_dict() for i in imports],
        "import_count": len(imports),
        "docstrings": [d.to_dict() for d in docstrings],
        "docstring_count": len(docstrings),
        "error": None,
    }


# ── get_functions ─────────────────────────────────────────────────────────


def get_functions(path: str) -> dict[str, Any]:
    """Return all function definitions in a file.

    Args:
        path: Path to a Python file.

    Returns:
        Dict with ``functions`` list and ``count``.
    """
    result = parse_file(path)
    if not result["success"]:
        return result
    return {"success": True, "functions": result["functions"], "count": result["function_count"], "error": None}


# ── get_classes ───────────────────────────────────────────────────────────


def get_classes(path: str) -> dict[str, Any]:
    """Return all class definitions in a file with their methods.

    Args:
        path: Path to a Python file.

    Returns:
        Dict with ``classes`` list and ``count``.
    """
    result = parse_file(path)
    if not result["success"]:
        return result
    return {"success": True, "classes": result["classes"], "count": result["class_count"], "error": None}


# ── get_imports ───────────────────────────────────────────────────────────


def get_imports(path: str) -> dict[str, Any]:
    """Return all import statements from a Python file.

    Args:
        path: Path to a Python file.

    Returns:
        Dict with ``imports`` list and ``count``.
    """
    result = parse_file(path)
    if not result["success"]:
        return result
    return {"success": True, "imports": result["imports"], "count": result["import_count"], "error": None}


# ── get_complexity ────────────────────────────────────────────────────────


def get_complexity(path: str) -> dict[str, Any]:
    """Compute cyclomatic complexity for every function in a file.

    Also reports the overall file complexity.

    Args:
        path: Path to a Python file.

    Returns:
        Dict with per‑function complexity scores and overall file score.
    """
    resolved, err = resolve_path(path)
    if err:
        return {"success": False, "error": err, "functions": [], "file_complexity": 0}
    if not os.path.isfile(resolved) or not resolved.endswith(".py"):
        return {"success": False, "error": f"Not a Python file: {path}", "functions": [], "file_complexity": 0}

    source, err = _read_source(resolved)
    if err:
        return {"success": False, "error": err, "functions": [], "file_complexity": 0}
    tree, err = _parse(source, resolved)
    if err:
        return {"success": False, "error": err, "functions": [], "file_complexity": 0}

    file_complexity = _cyclomatic_complexity(tree)
    funcs: list[dict[str, Any]] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.append({
                "name": node.name,
                "line": node.lineno,
                "complexity": _cyclomatic_complexity(node),
                "is_async": isinstance(node, ast.AsyncFunctionDef),
            })

    funcs.sort(key=lambda f: -f["complexity"])
    return {"success": True, "functions": funcs, "file_complexity": file_complexity, "error": None}


# ── get_docstrings ────────────────────────────────────────────────────────


def get_docstrings(path: str) -> dict[str, Any]:
    """Extract all docstrings from a Python file.

    Captures module, class, function, and method docstrings.

    Args:
        path: Path to a Python file.

    Returns:
        Dict with ``docstrings`` list and ``count``.
    """
    resolved, err = resolve_path(path)
    if err:
        return {"success": False, "docstrings": [], "count": 0, "error": err}
    if not os.path.isfile(resolved) or not resolved.endswith(".py"):
        return {"success": False, "docstrings": [], "count": 0, "error": f"Not a Python file: {path}"}

    source, err = _read_source(resolved)
    if err:
        return {"success": False, "docstrings": [], "count": 0, "error": err}
    if source is None:
        return {"success": False, "docstrings": [], "count": 0, "error": "Could not read file"}

    rel_path = _rel_path(resolved)
    docstrings = _extract_docstrings(source, rel_path)
    return {"success": True, "docstrings": [d.to_dict() for d in docstrings], "count": len(docstrings), "error": None}


# ── internal extractors ───────────────────────────────────────────────────


def _extract_functions(tree: ast.Module) -> list[FunctionInfo]:
    funcs: list[FunctionInfo] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            complexity = _cyclomatic_complexity(node)
            funcs.append(FunctionInfo(
                name=node.name,
                lineno=node.lineno,
                end_lineno=node.end_lineno or node.lineno,
                col_offset=node.col_offset + 1,
                decorators=_collect_decorators(node),
                args=[a.arg for a in node.args.args],
                returns=ast.unparse(node.returns) if node.returns else None,
                is_async=isinstance(node, ast.AsyncFunctionDef),
                is_method=_is_method(node),
                parent_class=_get_parent_class(node),
                complexity=complexity,
                docstring=_get_docstring(node),
            ))
    # Deduplicate — ast.walk visits nested functions too
    seen = set()
    unique = []
    for f in funcs:
        key = (f.name, f.lineno)
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique


def _is_method(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for parent in ast.walk(node):
        if isinstance(parent, ast.ClassDef):
            for child in parent.body:
                if child is node:
                    return True
    return False


def _get_parent_class(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    for parent in ast.walk(node):
        if isinstance(parent, ast.ClassDef):
            for child in parent.body:
                if child is node:
                    return parent.name
    return None


def _extract_classes(tree: ast.Module) -> list[ClassInfo]:
    classes: list[ClassInfo] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            methods = []
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.append(FunctionInfo(
                        name=item.name,
                        lineno=item.lineno,
                        end_lineno=item.end_lineno or item.lineno,
                        col_offset=item.col_offset + 1,
                        decorators=_collect_decorators(item),
                        args=[a.arg for a in item.args.args],
                        returns=ast.unparse(item.returns) if item.returns else None,
                        is_async=isinstance(item, ast.AsyncFunctionDef),
                        is_method=True,
                        parent_class=node.name,
                        complexity=_cyclomatic_complexity(item),
                        docstring=_get_docstring(item),
                    ))
            classes.append(ClassInfo(
                name=node.name,
                lineno=node.lineno,
                end_lineno=node.end_lineno or node.lineno,
                col_offset=node.col_offset + 1,
                bases=[ast.unparse(b) for b in node.bases] if node.bases else [],
                decorators=_collect_decorators(node),
                methods=methods,
                docstring=_get_docstring(node),
            ))
    return classes


def _extract_imports(tree: ast.Module) -> list[ImportInfo]:
    imports: list[ImportInfo] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(ImportInfo(
                    module=alias.name,
                    alias=alias.asname,
                    lineno=node.lineno,
                    import_type="direct",
                ))
        elif isinstance(node, ast.ImportFrom):
            names = []
            for alias in node.names:
                if alias.name == "*":
                    names.append("*")
                else:
                    n = alias.name
                    if alias.asname:
                        n = f"{alias.name} as {alias.asname}"
                    names.append(n)
            imports.append(ImportInfo(
                module=node.module or "",
                names=names,
                lineno=node.lineno,
                import_type="from",
            ))
    return imports


def _extract_docstrings(source: str, rel_path: str) -> list[DocstringInfo]:
    docs: list[DocstringInfo] = []
    tree, _ = _parse(source, rel_path)
    if tree is None:
        return docs

    module_doc = _get_docstring(tree)
    if module_doc:
        docs.append(DocstringInfo(
            file=rel_path,
            lineno=1,
            parent=None,
            parent_type="module",
            text=module_doc,
            summary=_summarise_docstring(module_doc),
        ))

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            doc = _get_docstring(node)
            if doc:
                docs.append(DocstringInfo(
                    file=rel_path,
                    lineno=node.lineno,
                    parent=node.name,
                    parent_type="class",
                    text=doc,
                    summary=_summarise_docstring(doc),
                ))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = _get_docstring(node)
            if doc:
                parent_type = "method" if _is_method(node) else "function"
                docs.append(DocstringInfo(
                    file=rel_path,
                    lineno=node.lineno,
                    parent=node.name,
                    parent_type=parent_type,
                    text=doc,
                    summary=_summarise_docstring(doc),
                ))

    return docs


def _rel_path(path: str) -> str:
    from wigent.config import settings
    try:
        return os.path.relpath(path, settings.workspace_path)
    except ValueError:
        return path


__all__ = [
    "parse_file",
    "get_functions",
    "get_classes",
    "get_imports",
    "get_complexity",
    "get_docstrings",
    "FunctionInfo",
    "ClassInfo",
    "ImportInfo",
    "DocstringInfo",
]
