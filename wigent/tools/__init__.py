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
    bash_executor — execute_command, execute_script, run_python, get_command_preview, kill_process, run_command
    code_search   — search_codebase, search_by_pattern, find_definition, find_references, get_file_symbols, get_imports_graph, find_similar_code
    ast_analyzer  — parse_file, get_functions, get_classes, get_imports, get_complexity, get_docstrings
    tool_schemas  — TOOL_SCHEMAS list for OpenAI function‑calling API
"""

# ── file_reader ──────────────────────────────────────────────────────────
from wigent.tools.file_reader import (
    read_file,
    read_file_lines,
    read_multiple_files,
    get_file_info,
    detect_encoding,
    get_file_summary,
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

# ── bash_executor ────────────────────────────────────────────────────────
from wigent.tools.bash_executor import (
    execute_command,
    execute_script,
    run_python,
    get_command_preview,
    kill_process,
    run_command,
)

# ── code_search ──────────────────────────────────────────────────────────
from wigent.tools.code_search import (
    search_codebase,
    search_by_pattern,
    find_definition,
    find_references,
    get_file_symbols,
    get_imports_graph,
    find_similar_code,
)

# ── ast_analyzer ─────────────────────────────────────────────────────────
from wigent.tools.ast_analyzer import (
    parse_file,
    get_functions,
    get_classes,
    get_imports,
    get_complexity,
    get_docstrings,
)

# ── git_tool ─────────────────────────────────────────────────────────────
from wigent.tools.git_tool import (
    check_is_git_repo,
    get_repo_root,
    get_status,
    get_diff,
    get_log,
    get_current_branch,
    list_branches,
    stage_files,
    unstage_files,
    commit,
    create_branch,
    get_blame,
    get_file_history,
    stash_changes,
    pop_stash,
    list_stashes,
)

# ── browser_mcp ─────────────────────────────────────────────────────────
from wigent.tools.browser_mcp import (
    BrowserMCP,
    BrowserSnapshot,
    BrowserState,
    ConsoleEntry,
    NetworkRequest,
    PerformanceMetrics,
    launch_browser,
)

# ── visual_diff ─────────────────────────────────────────────────────────
from wigent.tools.visual_diff import (
    VisualDiff,
    VisualDiffReport,
    PixelDiff,
    PixelDiffRegion,
    LayoutDiff,
    LayoutChange,
    DiffSeverity,
)

# ── schemas ──────────────────────────────────────────────────────────────
from wigent.tools.tool_schemas import TOOL_SCHEMAS

__all__ = [
    # visual_diff
    "VisualDiff",
    "VisualDiffReport",
    "PixelDiff",
    "PixelDiffRegion",
    "LayoutDiff",
    "LayoutChange",
    "DiffSeverity",
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
    # bash_executor
    "execute_command",
    "execute_script",
    "run_python",
    "get_command_preview",
    "kill_process",
    "run_command",
    # code_search
    "search_codebase",
    "search_by_pattern",
    "find_definition",
    "find_references",
    "get_file_symbols",
    "get_imports_graph",
    "find_similar_code",
    # ast_analyzer
    "parse_file",
    "get_functions",
    "get_classes",
    "get_imports",
    "get_complexity",
    "get_docstrings",
    # schemas
    "TOOL_SCHEMAS",
    # file_reader
    "get_file_summary",
    # browser_mcp
    "BrowserMCP",
    "BrowserSnapshot",
    "BrowserState",
    "ConsoleEntry",
    "NetworkRequest",
    "PerformanceMetrics",
    "launch_browser",
    # git_tool
    "check_is_git_repo",
    "get_repo_root",
    "get_status",
    "get_diff",
    "get_log",
    "get_current_branch",
    "list_branches",
    "stage_files",
    "unstage_files",
    "commit",
    "create_branch",
    "get_blame",
    "get_file_history",
    "stash_changes",
    "pop_stash",
    "list_stashes",
]
