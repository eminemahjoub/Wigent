# ════════════════════════════════════════
# wigent — File Search
# Role: Full-text search with ripgrep, regex, and structured code queries
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Search across workspace files — string, regex, function definitions,
import references, and search‑and‑replace with preview."""

from __future__ import annotations

import ast
import os
import re
import subprocess
import logging
from typing import Any

from wigent.tools._safe_path import resolve_path

logger = logging.getLogger(__name__)

# Directories always excluded from search.
_EXCLUDED_DIRS = frozenset({
    ".git", ".wigent_backups", "__pycache__", "node_modules",
    "venv", ".venv", ".env", ".mypy_cache", ".ruff_cache",
    ".pytest_cache", ".nox", ".tox", "dist", "build", ".next",
})


# ── ripgrep search ───────────────────────────────────────────────────────


def search_in_files(query: str, path: str = ".") -> dict[str, Any]:
    """Search for a literal string across files using ripgrep.

    Falls back to a pure‑Python search if ``rg`` is not installed.

    Args:
        query: String to search for (literal, not a regex).
        path: Relative or absolute path inside the workspace.

    Returns:
        A dict with keys: ``success`` (bool), ``matches`` (list of dicts),
        ``count`` (int), ``engine`` (``"rg"`` | ``"python"``), ``error``.
    """
    resolved, err = resolve_path(path)
    if err:
        raise ValueError(err)

    if not os.path.isdir(resolved):
        resolved = os.path.dirname(resolved)

    # Try ripgrep first.
    try:
        return _search_with_rg(query, resolved)
    except FileNotFoundError:
        logger.info("ripgrep not available, falling back to Python search")
        return _search_python(query, resolved)


def _search_with_rg(query: str, root: str) -> dict[str, Any]:
    """Run ripgrep and parse results."""
    excludes = [f"--glob=!{d}/**" for d in _EXCLUDED_DIRS]
    cmd = ["rg", "--line-number", "--heading", "--no-messages", query, root] + excludes

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return {"success": False, "matches": [], "count": 0, "engine": "rg", "error": "Search timed out (30s)"}

    if result.returncode not in (0, 1):
        return {"success": False, "matches": [], "count": 0, "engine": "rg", "error": result.stderr.strip() or f"rg exited with code {result.returncode}"}

    if not result.stdout.strip():
        return {"success": True, "matches": [], "count": 0, "engine": "rg", "error": None}

    matches = _parse_rg_output(result.stdout, root)
    return {"success": True, "matches": matches, "count": len(matches), "engine": "rg", "error": None}


def _parse_rg_output(output: str, root: str) -> list[dict[str, Any]]:
    """Parse ripgrep's ``--heading --line-number`` output."""
    matches: list[dict[str, Any]] = []
    current_file: str | None = None

    for line in output.splitlines():
        # Heading line (file path).
        if line.startswith(root) or (current_file is None and ":" not in line.split(":")[0]):
            # Could be a heading.
            candidate = line.strip()
            if os.path.isfile(candidate):
                from wigent.config import settings
                try:
                    current_file = os.path.relpath(candidate, settings.workspace_path)
                except ValueError:
                    current_file = candidate
                continue

        # Content line with line number.
        if current_file and ":" in line:
            parts = line.split(":", 1)
            if parts[0].isdigit():
                line_no = int(parts[0])
                content = parts[1] if len(parts) > 1 else ""
                matches.append({
                    "file": current_file,
                    "line": line_no,
                    "content": content.strip(),
                })

    return matches


# ── Python fallback search ───────────────────────────────────────────────


def _search_python(query: str, root: str) -> dict[str, Any]:
    """Pure‑Python line‑by‑line search fallback."""
    matches: list[dict[str, Any]] = []
    from wigent.config import settings
    ws = settings.workspace_path

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune excluded dirs.
        dirnames[:] = [d for d in dirnames if d not in _EXCLUDED_DIRS]

        for fname in filenames:
            fpath = os.path.join(dirpath, fname)
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    for i, line in enumerate(f, 1):
                        if query in line:
                            try:
                                rel = os.path.relpath(fpath, ws)
                            except ValueError:
                                rel = fpath
                            matches.append({
                                "file": rel,
                                "line": i,
                                "content": line.rstrip(),
                            })
            except (OSError, PermissionError):
                continue

    return {"success": True, "matches": matches, "count": len(matches), "engine": "python", "error": None}


# ── regex search ─────────────────────────────────────────────────────────


def search_by_regex(pattern: str, path: str = ".") -> dict[str, Any]:
    """Search for a regex pattern across files.

    Args:
        pattern: A Python regular expression.
        path: Relative or absolute path inside the workspace.

    Returns:
        Results dict with ``matches`` containing ``file``, ``line``,
        ``content``, and ``groups`` (capture groups if any).
    """
    resolved, err = resolve_path(path)
    if err:
        raise ValueError(err)

    if not os.path.isdir(resolved):
        resolved = os.path.dirname(resolved)

    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        return {"success": False, "matches": [], "count": 0, "error": f"Invalid regex: {exc}"}

    matches: list[dict[str, Any]] = []
    from wigent.config import settings
    ws = settings.workspace_path

    for dirpath, dirnames, filenames in os.walk(resolved):
        dirnames[:] = [d for d in dirnames if d not in _EXCLUDED_DIRS]
        for fname in filenames:
            fpath = os.path.join(dirpath, fname)
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    for i, line in enumerate(f, 1):
                        m = compiled.search(line)
                        if m:
                            try:
                                rel = os.path.relpath(fpath, ws)
                            except ValueError:
                                rel = fpath
                            matches.append({
                                "file": rel,
                                "line": i,
                                "content": line.rstrip(),
                                "groups": list(m.groups()) if m.groups() else None,
                            })
            except (OSError, PermissionError):
                continue

    return {"success": True, "matches": matches, "count": len(matches), "error": None}


# ── structured code search ───────────────────────────────────────────────


def find_function(name: str, path: str = ".") -> dict[str, Any]:
    """Find function or class definitions matching *name*.

    Uses Python's ``ast`` module for accurate parsing; falls back to
    regex for other languages.

    Args:
        name: Function or class name (partial match supported).
        path: Relative or absolute path inside the workspace.

    Returns:
        Results dict with ``matches`` containing ``file``, ``line``,
        ``kind`` (``"function"`` | ``"class"``), and ``signature``.
    """
    resolved, err = resolve_path(path)
    if err:
        raise ValueError(err)

    if not os.path.isdir(resolved):
        resolved = os.path.dirname(resolved)

    matches: list[dict[str, Any]] = []
    from wigent.config import settings
    ws = settings.workspace_path

    for dirpath, dirnames, filenames in os.walk(resolved):
        dirnames[:] = [d for d in dirnames if d not in _EXCLUDED_DIRS]
        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(dirpath, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    source = f.read()
                tree = ast.parse(source, filename=fpath)
            except (SyntaxError, OSError):
                continue

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if name.lower() in node.name.lower():
                        try:
                            rel = os.path.relpath(fpath, ws)
                        except ValueError:
                            rel = fpath
                        matches.append({
                            "file": rel,
                            "line": node.lineno,
                            "kind": "async_function" if isinstance(node, ast.AsyncFunctionDef) else "function",
                            "name": node.name,
                            "signature": _format_fn_signature(node),
                        })
                elif isinstance(node, ast.ClassDef):
                    if name.lower() in node.name.lower():
                        try:
                            rel = os.path.relpath(fpath, ws)
                        except ValueError:
                            rel = fpath
                        matches.append({
                            "file": rel,
                            "line": node.lineno,
                            "kind": "class",
                            "name": node.name,
                            "signature": f"class {node.name}(...)" if node.bases else f"class {node.name}",
                        })

    return {"success": True, "matches": matches, "count": len(matches), "error": None}


def _format_fn_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
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


def find_imports(module_name: str, path: str = ".") -> dict[str, Any]:
    """Find import statements referencing a module.

    Args:
        module_name: Module name or fragment (e.g. ``"os"``, ``"numpy"``).
        path: Relative or absolute path inside the workspace.

    Returns:
        Results dict with ``matches`` containing ``file``, ``line``,
        ``import_statement`` (full import line).
    """
    resolved, err = resolve_path(path)
    if err:
        raise ValueError(err)

    if not os.path.isdir(resolved):
        resolved = os.path.dirname(resolved)

    matches: list[dict[str, Any]] = []
    from wigent.config import settings
    ws = settings.workspace_path

    import_re = re.compile(
        rf"^(import {re.escape(module_name)}(?:\.\w+)*"
        rf"|from {re.escape(module_name)}(?:\.\w+)* import )",
        re.MULTILINE,
    )

    for dirpath, dirnames, filenames in os.walk(resolved):
        dirnames[:] = [d for d in dirnames if d not in _EXCLUDED_DIRS]
        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(dirpath, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()
                for m in import_re.finditer(content):
                    line_no = content[: m.start()].count("\n") + 1
                    try:
                        rel = os.path.relpath(fpath, ws)
                    except ValueError:
                        rel = fpath
                    matches.append({
                        "file": rel,
                        "line": line_no,
                        "import_statement": m.group(0).strip(),
                    })
            except (OSError, UnicodeDecodeError):
                continue

    return {"success": True, "matches": matches, "count": len(matches), "error": None}


# ── search and replace ───────────────────────────────────────────────────


def search_and_replace(
    find: str,
    replace: str,
    path: str = ".",
    preview: bool = True,
) -> dict[str, Any]:
    """Search for a pattern and replace it across files.

    Operates on a preview‑first basis: set ``preview=False`` to actually
    write changes (after confirmation).

    Args:
        find: String or regex pattern to find.
        replace: Replacement text (supports backreferences like ``\\1``).
        path: Directory or file path inside the workspace.
        preview: When True (default), only show matches without modifying.

    Returns:
        A dict with keys: ``success``, ``preview`` (bool), ``changes``
        (list of ``{file, line, old, new}``), ``dry_run`` (bool),
        ``error``.
    """
    resolved, err = resolve_path(path)
    if err:
        raise ValueError(err)

    if not os.path.isdir(resolved) and not os.path.isfile(resolved):
        return {"success": False, "preview": preview, "changes": [], "dry_run": True, "error": f"Path not found: {path}"}

    try:
        compiled = re.compile(find)
    except re.error as exc:
        return {"success": False, "preview": preview, "changes": [], "dry_run": True, "error": f"Invalid regex: {exc}"}

    changes: list[dict[str, Any]] = []
    from wigent.config import settings
    ws = settings.workspace_path

    files_to_process: list[str] = []
    if os.path.isfile(resolved):
        files_to_process.append(resolved)
    else:
        for dirpath, dirnames, filenames in os.walk(resolved):
            dirnames[:] = [d for d in dirnames if d not in _EXCLUDED_DIRS]
            for fname in filenames:
                files_to_process.append(os.path.join(dirpath, fname))

    for fpath in files_to_process:
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except (OSError, PermissionError):
            continue

        new_content, count = compiled.subn(replace, content)
        if count == 0:
            continue

        try:
            rel = os.path.relpath(fpath, ws)
        except ValueError:
            rel = fpath

        changes.append({
            "file": rel,
            "matches": count,
            "preview_content": new_content if preview else None,
        })

        if not preview:
            try:
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(new_content)
            except OSError as exc:
                changes[-1]["error"] = str(exc)

    dry_run = preview
    return {
        "success": True,
        "preview": preview,
        "changes": changes,
        "files_affected": len(changes),
        "dry_run": dry_run,
        "error": None,
    }


__all__ = [
    "search_in_files",
    "search_by_regex",
    "find_function",
    "find_imports",
    "search_and_replace",
]
