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
            "name": "get_file_summary",
            "description": "Return a lightweight summary of a file: size, line count, language, last modified time, and the first N characters of content. Use this instead of read_file when you only need a preview — saves tokens.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative or absolute path inside the workspace.",
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "Maximum characters to include in the summary (default 2000).",
                    },
                },
                "required": ["path"],
            },
        },
    },
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
    # ── bash_executor ──────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "execute_command",
            "description": "Execute a shell command safely (no shell=True). Uses shlex.split() for parsing, mandatory 30s timeout, and sandbox classification. Blocked commands are rejected immediately.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command string to execute (e.g. 'ls -la').",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Working directory (default: workspace root).",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Maximum execution time in seconds (default 30, max 120).",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_script",
            "description": "Write content to a temp file and execute it. Use this for multi-line scripts or when pipes/redirects are needed. Requires approval.",
            "parameters": {
                "type": "object",
                "properties": {
                    "script_content": {
                        "type": "string",
                        "description": "Shell script content to execute.",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Maximum execution time in seconds (default 30).",
                    },
                },
                "required": ["script_content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": "Execute Python code in an isolated subprocess. Writes code to a temp .py file and runs with python3.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python source code to execute.",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Maximum execution time in seconds (default 30).",
                    },
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_command_preview",
            "description": "Preview a command without executing it. Shows parsed arguments and classification (blocked/warn/safe).",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command string to preview.",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kill_process",
            "description": "Terminate a running process by PID. Sends SIGKILL by default.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pid": {
                        "type": "integer",
                        "description": "Process ID to terminate.",
                    },
                    "force": {
                        "type": "boolean",
                        "description": "If true sends SIGKILL, otherwise SIGTERM (default true).",
                    },
                },
                "required": ["pid"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "[DEPRECATED] Use execute_command instead. Execute a shell command with 30s timeout.",
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
    # ── code_search ──────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "search_codebase",
            "description": "Full-text search across the codebase using ripgrep (Python fallback). Returns ranked matches with file/line/column and context. Skips binaries and respects .gitignore.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Literal string to search for.",
                    },
                    "root_path": {
                        "type": "string",
                        "description": "Directory to search in (default workspace root).",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_by_pattern",
            "description": "Regex search across the codebase. Returns matches with file/line/column and surrounding context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Python regex pattern to search for.",
                    },
                    "root_path": {
                        "type": "string",
                        "description": "Directory to search in (default workspace root).",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_definition",
            "description": "Find the definition of a symbol (function, class, variable) across the codebase. Uses Python AST for Python files, regex fallback for others.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Symbol name to find (exact match).",
                    },
                    "root_path": {
                        "type": "string",
                        "description": "Directory to search in (default workspace root).",
                    },
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_references",
            "description": "Find all usages of a symbol, excluding its definition line. Uses ripgrep for fast full-codebase search.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Symbol name to find references for.",
                    },
                    "root_path": {
                        "type": "string",
                        "description": "Directory to search in (default workspace root).",
                    },
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_file_symbols",
            "description": "List all functions, classes, methods, and variables defined in a single file. Uses AST for Python files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Relative or absolute path to the file.",
                    },
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_imports_graph",
            "description": "Build a full import dependency graph for the project. Returns nodes, directed edges, orphan modules, and hub modules (most imported).",
            "parameters": {
                "type": "object",
                "properties": {
                    "root_path": {
                        "type": "string",
                        "description": "Project root directory (default workspace root).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_similar_code",
            "description": "Find code blocks similar to a given snippet using token-frequency ranking. Results sorted by Jaccard similarity score.",
            "parameters": {
                "type": "object",
                "properties": {
                    "snippet": {
                        "type": "string",
                        "description": "Code snippet text to match against the codebase.",
                    },
                    "root_path": {
                        "type": "string",
                        "description": "Directory to search in (default workspace root).",
                    },
                },
                "required": ["snippet"],
            },
        },
    },
    # ── ast_analyzer ─────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "parse_file",
            "description": "Parse a Python file via AST and return full analysis: functions, classes, imports, complexity, docstrings, and line counts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative or absolute path to a Python file.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_functions",
            "description": "Return all function definitions in a Python file, with args, decorators, complexity, and docstrings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative or absolute path to a Python file.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_classes",
            "description": "Return all class definitions in a Python file, with methods, bases, decorators, and docstrings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative or absolute path to a Python file.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_imports",
            "description": "Return all import statements from a Python file, distinguishing direct vs from imports.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative or absolute path to a Python file.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_complexity",
            "description": "Compute cyclomatic complexity for every function in a Python file. Results sorted by complexity descending.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative or absolute path to a Python file.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_docstrings",
            "description": "Extract all docstrings from a Python file — module, class, function, and method docstrings with parent context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative or absolute path to a Python file.",
                    },
                },
                "required": ["path"],
            },
        },
    },
# ---- git_tool ----------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "check_is_git_repo",
            "description": "Check whether a directory is inside a git repository (searches parent directories).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path to check (default workspace root).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_repo_root",
            "description": "Find the root directory of the git repository containing the given path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path inside the repo (default workspace root).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_status",
            "description": "Return the working tree status with staged/unstaged entries, branch name, and ahead/behind counts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory inside the workspace (default workspace root).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_diff",
            "description": "Return a structured diff of staged or unstaged changes. Includes hunks, insertions/deletions counts, and raw unified diff string.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory inside the workspace (default workspace root).",
                    },
                    "staged": {
                        "type": "boolean",
                        "description": "If True, diff staged changes vs HEAD. If False, diff unstaged working tree changes (default false).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_log",
            "description": "Return the recent commit history with author, timestamp, message, and changed files count.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory inside the workspace (default workspace root).",
                    },
                    "n": {
                        "type": "integer",
                        "description": "Maximum number of commits to return (default 10, max 500).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_branch",
            "description": "Return the name of the currently active branch with its latest commit SHA.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory inside the workspace (default workspace root).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_branches",
            "description": "List all local (and optionally remote) branches with current branch indicator and commit SHA.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory inside the workspace (default workspace root).",
                    },
                    "include_remote": {
                        "type": "boolean",
                        "description": "Include remote-tracking branches (default false).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stage_files",
            "description": "Stage files (git add) for the next commit. If no file_patterns given, stages all changes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory inside the workspace (default workspace root).",
                    },
                    "file_patterns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of file paths or glob patterns to stage. Omit to stage all.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "unstage_files",
            "description": "Unstage files (git restore --staged). If no file_patterns given, unstages everything.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory inside the workspace (default workspace root).",
                    },
                    "file_patterns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of file paths to unstage. Omit to unstage all.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "commit",
            "description": "Create a git commit. NEVER commits without approved=True. When approved=False, returns a preview of staged changes. Pass approved=True only after user confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory inside the workspace (default workspace root).",
                    },
                    "message": {
                        "type": "string",
                        "description": "Commit message.",
                    },
                    "approved": {
                        "type": "boolean",
                        "description": "MUST be True to actually commit. Default False (returns preview only).",
                    },
                    "author_name": {
                        "type": "string",
                        "description": "Override author name (optional).",
                    },
                    "author_email": {
                        "type": "string",
                        "description": "Override author email (optional).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_branch",
            "description": "Create and switch to a new branch. Optionally specify a base branch or commit to fork from.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory inside the workspace (default workspace root).",
                    },
                    "name": {
                        "type": "string",
                        "description": "Name for the new branch.",
                    },
                    "base_branch": {
                        "type": "string",
                        "description": "Branch or commit to fork from (default: current HEAD).",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_blame",
            "description": "Get blame/annotate information for a file. Optionally filter to a specific line number.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory inside the workspace (default workspace root).",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to blame (relative to repo root).",
                    },
                    "line": {
                        "type": "integer",
                        "description": "If set, only return blame for this specific line (1-indexed).",
                    },
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_file_history",
            "description": "Return the commit history for a single file — who changed what and when.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory inside the workspace (default workspace root).",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "File path relative to repo root.",
                    },
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stash_changes",
            "description": "Stash working directory changes. Optionally include untracked files and a stash message.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory inside the workspace (default workspace root).",
                    },
                    "message": {
                        "type": "string",
                        "description": "Optional stash message.",
                    },
                    "include_untracked": {
                        "type": "boolean",
                        "description": "Also stash untracked files (git stash -u) (default false).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pop_stash",
            "description": "Pop (apply and drop) a stash entry by index (0 = most recent).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory inside the workspace (default workspace root).",
                    },
                    "index": {
                        "type": "integer",
                        "description": "Stash index to pop (0 = most recent, default 0).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_stashes",
            "description": "List all stash entries with index, message, and commit SHA.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory inside the workspace (default workspace root).",
                    },
                },
                "required": [],
            },
        },
    },
]

__all__ = ["TOOL_SCHEMAS"]
