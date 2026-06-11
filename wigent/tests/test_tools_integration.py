from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Bypass wigent/__init__.py to avoid model import chain.
from wigent.config import settings
from wigent.tools.file_reader import read_file, read_file_lines, get_file_info, get_file_summary
from wigent.tools.file_writer import write_file, create_file, append_to_file, backup_file, restore_backup
from wigent.tools.file_lister import list_directory, list_files, find_files, get_recent_files
from wigent.tools.file_search import search_in_files, search_by_regex, find_function, find_imports, search_and_replace
from wigent.tools.bash_executor import execute_command, get_command_preview, kill_process
from wigent.tools.code_search import search_codebase, search_by_pattern as cs_search_by_pattern
from wigent.tools.ast_analyzer import parse_file, get_functions, get_classes, get_complexity, get_docstrings
from wigent.tools.git_tool import check_is_git_repo, get_status, get_diff, get_log, get_current_branch
from wigent.tools.tool_schemas import TOOL_SCHEMAS
from wigent.tools._safe_path import resolve_path, ensure_parent


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_workspace():
    path = tempfile.mkdtemp(prefix="wigent_tools_")
    (Path(path) / "hello.py").write_text("def greet(name):\n    return f'Hello {name}'\n")
    (Path(path) / "main.py").write_text("from hello import greet\n\nprint(greet('World'))\n")
    (Path(path) / "notes.txt").write_text("Hello World\nThis is a test file.\n")
    (Path(path) / "data.csv").write_text("id,name,value\n1,foo,100\n2,bar,200\n")
    with patch.object(settings, '_workspace_abs', path):
        yield path
    import shutil
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def tmp_empty():
    path = tempfile.mkdtemp(prefix="wigent_empty_")
    with patch.object(settings, '_workspace_abs', path):
        yield path
    import shutil
    shutil.rmtree(path, ignore_errors=True)


# ── Helpers ──────────────────────────────────────────────────────────────

def _list_tool_names() -> list[str]:
    return [s["function"]["name"] for s in TOOL_SCHEMAS]


# ── File Reader ─────────────────────────────────────────────────────────

class TestFileReader:
    def test_read_file(self, tmp_workspace):
        result = read_file(os.path.join(tmp_workspace, "hello.py"))
        assert result["success"] is True
        assert "def greet" in result["content"]
        assert result["line_count"] == 2

    def test_read_file_nonexistent(self, tmp_workspace):
        with pytest.raises(ValueError):
            read_file(os.path.join(tmp_workspace, "nope.py"))

    def test_read_file_lines(self, tmp_workspace):
        result = read_file_lines(os.path.join(tmp_workspace, "hello.py"), start=1, end=1)
        assert result["success"] is True
        assert len(result["lines"]) == 1
        assert "def greet" in result["lines"][0]

    def test_get_file_info(self, tmp_workspace):
        result = get_file_info(os.path.join(tmp_workspace, "hello.py"))
        assert result["exists"] is True
        assert result["is_file"] is True
        assert result["size_bytes"] > 0

    def test_get_file_summary(self, tmp_workspace):
        result = get_file_summary(os.path.join(tmp_workspace, "hello.py"))
        assert result["file"] is not None
        assert result["language"] == "Python"


# ── File Writer ─────────────────────────────────────────────────────────

class TestFileWriter:
    def test_write_file_creates(self, tmp_empty):
        path = os.path.join(tmp_empty, "new.txt")
        result = write_file(path, "hello world")
        assert result["success"] is True
        assert result["action"] == "created"
        assert Path(path).read_text() == "hello world"

    def test_write_file_updates(self, tmp_empty):
        path = os.path.join(tmp_empty, "existing.txt")
        Path(path).write_text("old")
        result = write_file(path, "new")
        assert result["success"] is True
        assert result["action"] == "updated"

    def test_create_file(self, tmp_empty):
        path = os.path.join(tmp_empty, "fresh.txt")
        result = create_file(path, "fresh")
        assert result["success"] is True
        assert Path(path).read_text() == "fresh"

    def test_create_file_existing_fails(self, tmp_empty):
        path = os.path.join(tmp_empty, "exists.txt")
        Path(path).write_text("exists")
        result = create_file(path, "fail")
        assert result["success"] is False

    def test_append_to_file(self, tmp_empty):
        path = os.path.join(tmp_empty, "log.txt")
        Path(path).write_text("line1\n")
        result = append_to_file(path, "line2\n")
        assert result["success"] is True
        assert Path(path).read_text() == "line1\nline2\n"

    def test_backup_and_restore(self, tmp_empty):
        path = os.path.join(tmp_empty, "backup_test.txt")
        Path(path).write_text("original")
        backup = backup_file(path)
        assert backup["success"] is True
        Path(path).write_text("modified")
        restore = restore_backup(path)
        assert restore["success"] is True
        assert Path(path).read_text() == "original"


# ── File Lister ─────────────────────────────────────────────────────────

class TestFileLister:
    def test_list_directory(self, tmp_workspace):
        result = list_directory(tmp_workspace)
        assert result["success"] is True
        assert result["entries"] >= 4

    def test_list_files_glob(self, tmp_workspace):
        result = list_files(tmp_workspace, pattern="*.py")
        assert result["success"] is True
        py_files = [f for f in result["files"] if f.endswith(".py")]
        assert len(py_files) >= 2

    def test_find_files(self, tmp_workspace):
        result = find_files("*.txt", tmp_workspace)
        assert result["success"] is True
        assert len(result["files"]) >= 1

    def test_get_recent_files(self, tmp_workspace):
        result = get_recent_files(tmp_workspace, n=5)
        assert result["success"] is True
        assert len(result["files"]) >= 4


# ── File Search ─────────────────────────────────────────────────────────

class TestFileSearch:
    def test_search_in_files(self, tmp_workspace):
        result = search_in_files("Hello World", tmp_workspace)
        assert result["success"] is True
        assert result["count"] >= 1

    def test_search_by_regex(self, tmp_workspace):
        result = search_by_regex(r"def\s+\w+", tmp_workspace)
        assert result["success"] is True
        assert result["count"] >= 1

    def test_find_function(self, tmp_workspace):
        result = find_function("greet", tmp_workspace)
        assert result["success"] is True
        assert result["count"] >= 1

    def test_find_imports(self, tmp_workspace):
        result = find_imports("hello", tmp_workspace)
        assert result["success"] is True
        assert result["count"] >= 1

    def test_search_and_replace_preview(self, tmp_workspace):
        path = os.path.join(tmp_workspace, "notes.txt")
        result = search_and_replace("Hello", "Hi", path, preview=True)
        assert result["success"] is True
        assert result["dry_run"] is True
        assert result["files_affected"] >= 1


# ── Bash Executor ───────────────────────────────────────────────────────

class TestBashExecutor:
    def test_execute_command(self, tmp_empty):
        result = execute_command("echo hello", cwd=tmp_empty)
        assert result["success"] is True
        assert "hello" in result["stdout"]

    def test_execute_command_failure(self, tmp_empty):
        result = execute_command("false", cwd=tmp_empty)
        assert result["success"] is False
        assert result["exit_code"] != 0

    def test_get_command_preview(self):
        result = get_command_preview("ls -la")
        assert result["command"] == "ls -la"
        assert "safe" in result

    def test_kill_process_invalid(self):
        result = kill_process(999999999)
        assert result["success"] is False
        assert "error" in result


# ── Code Search ─────────────────────────────────────────────────────────

class TestCodeSearch:
    def test_search_codebase(self, tmp_workspace):
        result = search_codebase("greet", tmp_workspace)
        assert result["success"] is True
        assert result["count"] >= 1

    def test_search_by_pattern_regex(self, tmp_workspace):
        result = cs_search_by_pattern(r"print\(.*\)", tmp_workspace)
        assert result["success"] is True
        assert result["count"] >= 1


# ── AST Analyzer ────────────────────────────────────────────────────────

class TestAstAnalyzer:
    def test_parse_file(self, tmp_workspace):
        result = parse_file(os.path.join(tmp_workspace, "hello.py"))
        assert result["success"] is True
        assert result["function_count"] >= 1

    def test_get_functions(self, tmp_workspace):
        result = get_functions(os.path.join(tmp_workspace, "hello.py"))
        assert result["success"] is True
        names = [f["name"] for f in result["functions"]]
        assert "greet" in names

    def test_get_classes(self, tmp_workspace):
        result = get_classes(os.path.join(tmp_workspace, "hello.py"))
        assert result["success"] is True

    def test_get_complexity(self, tmp_workspace):
        result = get_complexity(os.path.join(tmp_workspace, "hello.py"))
        assert result["success"] is True

    def test_get_docstrings(self, tmp_workspace):
        result = get_docstrings(os.path.join(tmp_workspace, "hello.py"))
        assert result["success"] is True


# ── Git Tool ───────────────────────────────────────────────────────────

class TestGitTool:
    def test_check_is_git_repo_not_repo(self, tmp_empty):
        pytest.importorskip("git")
        result = check_is_git_repo(tmp_empty)
        assert result["is_git_repo"] is False

    def test_check_is_git_repo_in_repo(self, tmp_workspace):
        pytest.importorskip("git")
        import subprocess
        subprocess.run(["git", "init"], cwd=tmp_workspace, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_workspace, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_workspace, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=tmp_workspace, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_workspace, capture_output=True)

        result = check_is_git_repo(tmp_workspace)
        assert result["success"] is True
        assert result["is_git_repo"] is True

    def test_get_current_branch(self, tmp_workspace):
        pytest.importorskip("git")
        import subprocess
        subprocess.run(["git", "init"], cwd=tmp_workspace, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_workspace, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_workspace, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=tmp_workspace, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_workspace, capture_output=True)

        result = get_current_branch(tmp_workspace)
        assert result["success"] is True or result.get("branch") is not None

    def test_get_status(self, tmp_workspace):
        pytest.importorskip("git")
        import subprocess
        subprocess.run(["git", "init"], cwd=tmp_workspace, capture_output=True)
        result = get_status(tmp_workspace)
        assert result["success"] is True

    def test_get_log(self, tmp_workspace):
        pytest.importorskip("git")
        import subprocess
        subprocess.run(["git", "init"], cwd=tmp_workspace, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_workspace, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_workspace, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=tmp_workspace, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_workspace, capture_output=True)

        result = get_log(tmp_workspace, n=5)
        assert result["success"] is True
        assert result["count"] >= 1

    def test_get_diff(self, tmp_workspace):
        pytest.importorskip("git")
        import subprocess
        subprocess.run(["git", "init"], cwd=tmp_workspace, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_workspace, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_workspace, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=tmp_workspace, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_workspace, capture_output=True)
        Path(tmp_workspace, "new.txt").write_text("uncommitted\n")
        result = get_diff(tmp_workspace)
        assert result["success"] is True


# ── Tool Schemas ────────────────────────────────────────────────────────

class TestToolSchemas:
    def test_all_tools_have_schemas(self):
        assert len(TOOL_SCHEMAS) >= 50
        for s in TOOL_SCHEMAS:
            assert "function" in s
            assert "name" in s["function"]
            assert "description" in s["function"]
            assert "parameters" in s["function"]

    def test_schemas_have_unique_names(self):
        names = _list_tool_names()
        assert len(names) == len(set(names))

    def test_critical_tools_present(self):
        names = _list_tool_names()
        for critical in ["read_file", "write_file", "execute_command", "search_codebase",
                          "parse_file", "get_status", "commit", "list_directory"]:
            assert critical in names, f"Missing: {critical}"


# ── Safe Path ───────────────────────────────────────────────────────────

class TestSafePath:
    def test_resolve_path_in_workspace(self, tmp_empty):
        path, err = resolve_path(tmp_empty)
        assert err is None

    def test_resolve_path_nonexistent(self, tmp_empty):
        path, err = resolve_path(os.path.join(tmp_empty, "nope"), require_existing=True)
        assert err is not None

    def test_ensure_parent(self, tmp_empty):
        nested = os.path.join(tmp_empty, "a", "b", "c.txt")
        err = ensure_parent(nested)
        assert err is None
        assert os.path.isdir(os.path.dirname(nested))
