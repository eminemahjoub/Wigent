# ════════════════════════════════════════
# wigent — Tool Schemas
# Role: OpenAI‑format function‑calling schemas for every tool
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Complete set of tool definitions in OpenAI function‑calling format.

Usage:
    from wigent.tools.tool_schemas import TOOL_SCHEMAS

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        tools=TOOL_SCHEMAS,
    )
"""

from __future__ import annotations

from typing import Final


TOOL_SCHEMAS: Final[list[dict]] = [
    # ── file_reader ─────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the full content of a file inside the workspace. Returns content, encoding, line count, and size.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative or absolute path inside the workspace.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file_lines",
            "description": "Read a range of lines from a file (1-indexed). Useful for reading specific sections without loading the entire file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative or absolute path inside the workspace.",
                    },
                    "start": {
                        "type": "integer",
                        "description": "First line number (1-indexed, default 1).",
                    },
                    "end": {
                        "type": "integer",
                        "description": "Last line number inclusive. If omitted, reads to end of file.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_multiple_files",
            "description": "Batch-read multiple files in a single call. Returns a dict mapping each path to its content and metadata.",
            "parameters": {
                "type": "object",
                "properties": {
                    "paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of relative or absolute paths inside the workspace.",
                    },
                },
                "required": ["paths"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_file_info",
            "description": "Return metadata about a file or directory: size, type, modified time, and detected encoding.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative or absolute path inside the workspace.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    # ── file_writer ─────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file. Creates parent directories automatically. Creates a timestamped backup before overwriting existing files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative or absolute path inside the workspace.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Text content to write.",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_file",
            "description": "Create a brand new file. Fails with an error if the file already exists to prevent accidental overwrites.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative or absolute path inside the workspace.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Text content to write.",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "append_to_file",
            "description": "Append text to the end of an existing file. Fails if the file does not exist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative or absolute path inside the workspace.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Text content to append.",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file_lines",
            "description": "Replace a range of lines (1-indexed) in a file with new content. Creates a backup before modifying.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative or absolute path inside the workspace.",
                    },
                    "start": {
                        "type": "integer",
                        "description": "First line to replace (1-indexed).",
                    },
                    "end": {
                        "type": "integer",
                        "description": "Last line to replace (inclusive).",
                    },
                    "new_content": {
                        "type": "string",
                        "description": "Replacement text (may span multiple lines).",
                    },
                },
                "required": ["path", "start", "end", "new_content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_diff",
            "description": "Apply a unified-diff string to a file. Creates a backup before making changes. Only hunks that match the current file content are applied.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative or absolute path inside the workspace.",
                    },
                    "diff_string": {
                        "type": "string",
                        "description": "A valid unified diff (diff -u format) with @@ hunk headers.",
                    },
                },
                "required": ["path", "diff_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "backup_file",
            "description": "Create a timestamped backup of a file in the .wigent_backups directory. Returns the backup path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative or absolute path inside the workspace.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "restore_backup",
            "description": "Restore the most recent backup of a file. Overwrites the current file with the backed-up version.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative or absolute path inside the workspace.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    # ── file_lister ─────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "Produce a tree-formatted listing of a directory with emoji icons and file sizes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative directory path (default '.').",
                    },
                    "depth": {
                        "type": "integer",
                        "description": "Maximum recursion depth. -1 = unlimited, 0 = top-level only (default -1).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_project_structure",
            "description": "Produce a full project structure tree starting from the given path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "root": {
                        "type": "string",
                        "description": "Relative subdirectory path (default '.').",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files matching a glob pattern inside the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Base directory path (default '.').",
                    },
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern (e.g. '*.py', '**/*.ts'). Default '*'.",
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "Search subdirectories recursively (default true).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_files",
            "description": "Find files matching a glob pattern via recursive search.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern (supports ** for recursion).",
                    },
                    "root": {
                        "type": "string",
                        "description": "Base directory path (default '.').",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_files",
            "description": "Return the N most recently modified files in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "root": {
                        "type": "string",
                        "description": "Base directory path (default '.').",
                    },
                    "n": {
                        "type": "integer",
                        "description": "Maximum number of files to return (default 10).",
                    },
                },
                "required": [],
            },
        },
    },
    # ── file_search ─────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "search_in_files",
            "description": "Search for a literal string across all workspace files. Uses ripgrep if available, falls back to Python search.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "String to search for (literal, not regex).",
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory path to search in (default '.').",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_by_regex",
            "description": "Search for a regex pattern across all workspace files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Python regular expression pattern.",
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory path to search in (default '.').",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_function",
            "description": "Find function or class definitions matching a name. Uses Python AST for accurate parsing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Function or class name (partial match supported).",
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory path to search in (default '.').",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_imports",
            "description": "Find import statements referencing a module across Python files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "module_name": {
                        "type": "string",
                        "description": "Module name or fragment (e.g. 'os', 'numpy', 'wigent').",
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory path to search in (default '.').",
                    },
                },
                "required": ["module_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_and_replace",
            "description": "Search for a pattern and replace it across files. Preview mode by default — set preview=false to apply changes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "find": {
                        "type": "string",
                        "description": "String or regex pattern to find.",
                    },
                    "replace": {
                        "type": "string",
                        "description": "Replacement text (supports backreferences like \\1).",
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory or file path (default '.').",
                    },
                    "preview": {
                        "type": "boolean",
                        "description": "When true, only show matches without modifying files (default true).",
                    },
                },
                "required": ["find", "replace"],
            },
        },
    },
    # ── shell ───────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Execute a shell command inside the workspace directory with a 30-second timeout. Returns combined stdout and stderr.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute.",
                    },
                },
                "required": ["command"],
            },
        },
    },
]

__all__ = ["TOOL_SCHEMAS"]
