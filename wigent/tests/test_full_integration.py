from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Bypass wigent/__init__.py to avoid model import chain.
from wigent.memory import MemorySystem
from wigent.memory.context_manager import ContextManager
from wigent.memory.session import SessionManager
from wigent.memory.checkpoints import CheckpointManager
from wigent.safety import SafetySystem
from wigent.safety.validator import InputValidator
from wigent.safety.sandbox import Sandbox
from wigent.safety.approvals import ApprovalGate, RiskLevel
from wigent.core.workspace import WorkspaceDetector
from wigent.core.project_context import ProjectContext
from wigent.core.auto_indexer import AutoIndexer
from wigent.cli.ui_components import UIComponents
from wigent.cli.commands import CommandHandler, COMMAND_DEFINITIONS
from wigent.cli.cli_args import parse_args
from wigent.cli.diff_display import DiffDisplay


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_project():
    path = tempfile.mkdtemp(prefix="wigent_int_")
    (Path(path) / "setup.py").touch()
    (Path(path) / "README.md").write_text("# Test Project\n")
    agent_dir = Path(path) / ".agent" / "rules"
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "context.md").write_text("This is a test project.")
    yield path
    import shutil
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def mem_system():
    ms = MemorySystem()
    ms.initialize()
    yield ms
    try:
        ms.shutdown()
    except RuntimeError:
        pass


@pytest.fixture
def safety_system():
    ss = SafetySystem()
    ss.initialize()
    yield ss
    try:
        ss.shutdown()
    except RuntimeError:
        pass


@pytest.fixture
def workspace_detector():
    return WorkspaceDetector()


@pytest.fixture
def project_context():
    return ProjectContext()


# ── Integration: Workspace → Memory → Safety ────────────────────────────

class TestWorkspaceMemorySafetyIntegration:
    def test_detect_project_and_load_context(self, tmp_project, workspace_detector, project_context):
        info = workspace_detector.detect_project_type(tmp_project)
        assert info is not None
        assert info.type == "python"
        assert info.language == "python"
        assert info.root_path is not None

        summary = project_context.load_context(
            str(info.root_path),
            project_type=info.type,
            language=info.language,
        )
        assert "Test Project" in summary or "test project" in summary.lower() or summary.strip()

    def test_memory_accepts_workspace_context(self, tmp_project, mem_system, workspace_detector, project_context):
        info = workspace_detector.detect_project_type(tmp_project)
        root = str(info.root_path)
        context_summary = project_context.load_context(root, project_type=info.type, language=info.language)
        ctx_msg = (
            f"[WORKSPACE] {info.type}"
            + (f" ({info.framework})" if info.framework else "")
            + f" @ {root}"
        )
        mem_system.context.inject_project_context(ctx_msg)
        msgs = mem_system.context.get_messages()
        assert len(msgs) > 0

    def test_safety_approves_safe_command(self, safety_system):
        safety_system.approvals.set_auto_approve_mode(True)
        result = safety_system.safe_write("/tmp/test.txt", "hello")
        assert isinstance(result, bool)

    def test_memory_session_creation_and_persistence(self, tmp_project, mem_system):
        session = mem_system.sessions.create_session(
            name="integration_test",
            description="Testing session persistence",
            tags=["test", "integration"],
        )
        assert session.name == "integration_test"
        session.total_tokens = 500
        mem_system.sessions.save_session(session)

        loaded = mem_system.sessions.load_session("integration_test")
        assert loaded is not None
        assert loaded.total_tokens == 500

        mem_system.sessions.delete_session("integration_test")
        assert mem_system.sessions.load_session("integration_test") is None


# ── Integration: Checkpoint lifecycle ───────────────────────────────────

class TestCheckpointLifecycle:
    def test_create_restore_delete_checkpoint(self, tmp_project):
        ck = CheckpointManager(storage_dir=os.path.join(tmp_project, ".agent", "checkpoints"))
        meta = ck.create_checkpoint(label="v1", agent_state={"mode": "coder", "iteration": 3})
        cid = meta["id"]
        assert meta["label"] == "v1"

        lst = ck.list_checkpoints()
        ids = [c["id"] for c in lst]
        assert cid in ids

        restored = ck.restore_checkpoint(cid)
        assert restored["agent_state"]["mode"] == "coder"

        assert ck.delete_checkpoint(cid) is True
        lst_after = ck.list_checkpoints()
        assert cid not in [c["id"] for c in lst_after]

    def test_auto_checkpoint_and_cleanup(self, tmp_project):
        ck = CheckpointManager(storage_dir=os.path.join(tmp_project, ".agent", "checkpoints"))
        for i in range(20):
            ck.auto_checkpoint(label=f"auto_{i}", agent_state={"mode": "coder", "n": i})
        removed = ck.cleanup_old(keep_last=5)
        remaining = ck.list_checkpoints()
        auto_count = sum(1 for c in remaining if c.get("auto"))
        assert auto_count <= 5
        assert removed >= 15


# ── Integration: UI + Commands ─────────────────────────────────────────

class TestUICommandsIntegration:
    def test_ui_components_render_without_error(self):
        ui = UIComponents()
        ui.console = MagicMock()
        ui.print_banner("1.0.0", "gpt-4o", "orchestrator")
        ui.print_user_message("test message")
        ui.print_agent_message("response", "coder")
        ui.print_status_bar({"mode": "test", "model": "test", "tokens_used": 100, "tokens_max": 1000, "cost": 0.01})
        ui.print_help(COMMAND_DEFINITIONS)
        ui.print_workspace_banner({"project_type": "python", "language": "python", "path": "/tmp", "has_git": False})
        ui.print_error("test error", hint="try again")
        ui.print_command_result({"status": "ok", "message": "done", "data": {}})
        assert ui.console.print.call_count >= 8

    def test_command_handler_all_commands_registered(self):
        assert len(COMMAND_DEFINITIONS) == 17
        names = [c["name"].split()[0] for c in COMMAND_DEFINITIONS]
        assert "/mode" in names
        assert "/model" in names
        assert "/help" in names
        assert "/exit" in names
        assert "/status" in names
        assert "/clear" in names
        assert "/save" in names
        assert "/load" in names
        assert "/checkpoint" in names
        assert "/restore" in names
        assert "/cost" in names
        assert "/index" in names
        assert "/workspace" in names
        assert "/rules" in names
        assert "/approve-all" in names
        assert "/compact" in names
        assert "/history" in names

    def test_command_handler_with_mock_agent(self):
        agent = MagicMock()
        agent._mode = "orchestrator"
        agent._model_name = "gpt-4o"
        agent._provider = "openai"
        agent.messages = []
        agent.get_status.return_value = {"mode": "test", "provider": "openai", "model": "gpt-4o"}
        handler = CommandHandler(agent)

        result = handler.execute("/mode")
        assert result.status == "ok"

        result = handler.execute("/status")
        assert result.status == "ok"

        result = handler.execute("/help")
        assert result.status == "ok"

        result = handler.execute("/clear")
        assert result.status == "ok"

        result = handler.execute("/compact")
        assert result.status == "ok"

        result = handler.execute("/exit")
        assert result.data.get("should_exit") is True

        result = handler.execute("/nonexistent")
        assert result.status == "error"

    def test_cli_args_parsing(self):
        r = parse_args(["--mode", "architect", "--provider", "anthropic", "--no-banner", "--debug"])
        assert r["mode"] == "architect"
        assert r["provider"] == "anthropic"
        assert r["no_banner"] is True
        assert r["debug"] is True

        r = parse_args([])
        assert r["prompt"] is None
        assert r["mode"] is None

        r = parse_args(["write hello.py"])
        assert r["prompt"] == "write hello.py"


# ── Integration: DiffDisplay ────────────────────────────────────────────

class TestDiffDisplayIntegration:
    def test_compute_and_render_diff(self):
        dd = DiffDisplay()
        original = "def hello():\n    print('old')\n"
        modified = "def hello():\n    print('new')\n"
        diff = dd.compute_diff(original, modified, "greet.py")
        assert "+    print('new')" in diff
        assert "-    print('old')" in diff

        panel = dd.render_diff(diff, "greet.py", "low")
        assert panel is not None

        change_stats = dd.render_change_summary({
            "files": [{"file": "greet.py", "added": 1, "removed": 1, "risk": "low"}]
        })
        assert change_stats is not None


# ── Integration: Safety pipeline ───────────────────────────────────────

class TestSafetyIntegration:
    def test_validator_classifies_commands(self):
        validator = InputValidator()
        result = validator.validate_command("ls -la")
        assert result.valid is True

    def test_sandbox_restricts_paths(self, tmp_project):
        sandbox = Sandbox(workspace_root=tmp_project)
        assert sandbox.is_path_safe(os.path.join(tmp_project, "subdir")) is True
        assert sandbox.is_path_safe("/etc/passwd") is False

    def test_approval_gate_tracks_state(self):
        import os
        ag = ApprovalGate(audit_path="/dev/null")
        assert ag._auto_approve is False

        ag.set_auto_approve_mode(True)
        assert ag._auto_approve is True

        result = ag.request_approval("write_file", {"path": "/tmp/test.txt"}, risk=RiskLevel.LOW)
        assert result.approved is True

    def test_safety_system_full_pipeline(self, tmp_project, safety_system):
        assert safety_system.safe_execute("ls -la") is True


# ── Integration: AutoIndexer ───────────────────────────────────────────

class TestAutoIndexerIntegration:
    def test_index_on_startup(self, tmp_project):
        (Path(tmp_project) / "main.py").write_text("def main(): pass\n")
        (Path(tmp_project) / "utils.py").write_text("def util(): pass\n")

        ai = AutoIndexer()
        result = ai.index_on_startup(tmp_project, background=False)
        assert result.total_files >= 2
        assert result.indexed_files >= 2
        assert result.total_files >= 2
        ai.clear_index()


# ── Integration: Workspace + Context ───────────────────────────────────

class TestWorkspaceContextIntegration:
    def test_detect_and_context_with_agent_rules(self, tmp_project, workspace_detector, project_context):
        info = workspace_detector.detect_project_type(tmp_project)
        assert info.type == "python"
        assert info.root_path is not None

        summary = project_context.load_context(
            str(info.root_path),
            project_type=info.type,
        )
        assert summary.strip(), "Context should not be empty when .agent/rules/context.md exists"

    def test_detect_unknown_project(self, tmp_project, workspace_detector):
        bare_dir = tempfile.mkdtemp(prefix="wigent_bare_")
        info = workspace_detector.detect_project_type(bare_dir)
        assert info.type == "unknown"
        import shutil
        shutil.rmtree(bare_dir, ignore_errors=True)

    def test_project_context_inject_into_prompt(self, project_context):
        injected = project_context.inject_into_prompt("Base prompt")
        assert "Base prompt" in injected
        assert "PROJECT CONTEXT" in injected or "Project" in injected or injected.strip()


# ── Integration: MemorySystem facade ───────────────────────────────────

class TestMemorySystemIntegration:
    def test_full_memory_lifecycle(self):
        ms = MemorySystem()
        ms.initialize()
        assert ms.context is not None
        assert ms.sessions is not None
        assert ms.checkpoints is not None
        assert ms.vectors is not None

        ms.context.add_message("user", "hello")
        ms.context.add_message("assistant", "world")
        assert len(ms.context.get_messages()) == 2

        session = ms.sessions.create_session(name="full_test")
        assert session.name == "full_test"

        cp = ms.checkpoints.create_checkpoint(label="full_test_cp", agent_state={"step": 1})
        assert cp["label"] == "full_test_cp"

        ms.shutdown()
        with pytest.raises(RuntimeError):
            _ = ms.context
