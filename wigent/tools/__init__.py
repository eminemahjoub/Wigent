# ════════════════════════════════════════
# wigent — Tools Package
# Role: All agent capabilities — file, shell, search, code
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Tool implementations that the agent can invoke.

Sub-modules:
    file_reader   — read, read_file_lines, read_multiple_files, get_file_info, detect_encoding
    file_writer   — write, create, append, edit_file_lines, apply_diff, backup, restore
    file_lister   — list_directory, get_project_structure, list_files, find_files, get_recent_files
    file_search   — search_in_files, search_by_regex, find_function, find_imports, search_and_replace
    shell         — run_command
    tool_schemas  — TOOL_SCHEMAS list for OpenAI function‑calling API
"""

# ── file_reader ──────────────────────────────────────────────────────────
from wigent.tools.file_reader import (
    read_file,
    read_file_lines,
    read_multiple_files,
    get_file_info,
    detect_encoding,
)

# ── file_writer ──────────────────────────────────────────────────────────
from wigent.tools.file_writer import (
    write_file,
    create_file,
    append_to_file,
    edit_file_lines,
    apply_diff,
    backup_file,
    restore_backup,
)

# ── file_lister ──────────────────────────────────────────────────────────
from wigent.tools.file_lister import (
    list_directory,
    get_project_structure,
    list_files,
    find_files,
    get_recent_files,
)

# ── file_search ──────────────────────────────────────────────────────────
from wigent.tools.file_search import (
    search_in_files,
    search_by_regex,
    find_function,
    find_imports,
    search_and_replace,
)

# ── shell ────────────────────────────────────────────────────────────────
from wigent.tools.shell import run_command

# ── schemas ──────────────────────────────────────────────────────────────
from wigent.tools.tool_schemas import TOOL_SCHEMAS

__all__ = [
    # file_reader
    "read_file",
    "read_file_lines",
    "read_multiple_files",
    "get_file_info",
    "detect_encoding",
    # file_writer
    "write_file",
    "create_file",
    "append_to_file",
    "edit_file_lines",
    "apply_diff",
    "backup_file",
    "restore_backup",
    # file_lister
    "list_directory",
    "get_project_structure",
    "list_files",
    "find_files",
    "get_recent_files",
    # file_search
    "search_in_files",
    "search_by_regex",
    "find_function",
    "find_imports",
    "search_and_replace",
    # shell
    "run_command",
    # schemas
    "TOOL_SCHEMAS",
]
