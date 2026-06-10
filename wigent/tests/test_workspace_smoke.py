from __future__ import annotations

import subprocess
from pathlib import Path

from wigent.core.workspace import WorkspaceDetector, ProjectInfo
from wigent.core.project_context import ProjectContext


def test_workspace_detector_imports():
    assert WorkspaceDetector is not None


def test_detects_python_project(tmp_path: Path):
    (tmp_path / "setup.py").touch()
    detector = WorkspaceDetector()
    info = detector.detect_project_type(tmp_path)
    assert info.type == "python"
    assert info.language == "python"


def test_detects_node_project(tmp_path: Path):
    pkg = tmp_path / "package.json"
    pkg.write_text('{"name": "test", "version": "1.0.0"}')
    detector = WorkspaceDetector()
    info = detector.detect_project_type(tmp_path)
    assert info.type == "node"


def test_detects_react_project(tmp_path: Path):
    pkg = tmp_path / "package.json"
    pkg.write_text('{"name":"test","dependencies":{"react":"18.0.0"}}')
    detector = WorkspaceDetector()
    info = detector.detect_project_type(tmp_path)
    assert info.framework == "react"


def test_finds_project_root(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    sub = tmp_path / "src" / "deep"
    sub.mkdir(parents=True)
    detector = WorkspaceDetector()
    root = detector.find_project_root(sub)
    assert root == tmp_path


def test_project_context_imports():
    assert ProjectContext is not None


def test_project_context_loads(tmp_path: Path):
    ctx = ProjectContext()
    result = ctx.load_context(tmp_path)
    assert result is not None


def test_agent_rules_loading(tmp_path: Path):
    rules_dir = tmp_path / ".agent" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "context.md").write_text("# Test Project Rules")

    ctx = ProjectContext()
    ctx.load_context(tmp_path)
    rules = ctx.read_agent_rules()
    assert "context" in rules
    assert "Test Project" in str(rules)


def test_detects_django(tmp_path: Path):
    (tmp_path / "manage.py").touch()
    (tmp_path / "requirements.txt").write_text("django==5.0")
    detector = WorkspaceDetector()
    info = detector.detect_project_type(tmp_path)
    assert info.type == "django"


def test_detects_rust(tmp_path: Path):
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"')
    detector = WorkspaceDetector()
    info = detector.detect_project_type(tmp_path)
    assert info.type == "rust"
    assert info.package_manager == "cargo"


def test_detects_go(tmp_path: Path):
    (tmp_path / "go.mod").write_text("module test")
    detector = WorkspaceDetector()
    info = detector.detect_project_type(tmp_path)
    assert info.type == "go"


def test_is_git_repo(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    detector = WorkspaceDetector()
    assert detector.is_git_repo(tmp_path) is True


def test_not_git_repo(tmp_path: Path):
    detector = WorkspaceDetector()
    assert detector.is_git_repo(tmp_path) is False


def test_project_tree_building(tmp_path: Path):
    (tmp_path / "src" / "main.py").parent.mkdir(parents=True)
    (tmp_path / "src" / "main.py").write_text("print('hello')")
    (tmp_path / "README.md").write_text("# Test")
    ctx = ProjectContext()
    ctx.load_context(tmp_path)
    tree = ctx.get_file_tree(max_depth=3)
    assert "src/" in tree
    assert "main.py" in tree


def test_recent_commits_when_not_git(tmp_path: Path):
    ctx = ProjectContext()
    commits = ctx.get_recent_commits(n=3)
    assert commits == []


def test_detects_unknown_project(tmp_path: Path):
    detector = WorkspaceDetector()
    info = detector.detect_project_type(tmp_path)
    assert info.type == "unknown"


def test_get_tech_stack(tmp_path: Path):
    (tmp_path / "package.json").write_text('{"name":"x","dependencies":{"react":"18"}}')
    (tmp_path / "tsconfig.json").touch()
    detector = WorkspaceDetector()
    stack = detector.get_tech_stack(tmp_path)
    assert stack["type"] == "react"
    assert stack["framework"] == "react"
    assert stack["language"] == "typescript"
